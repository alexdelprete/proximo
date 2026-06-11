"""Cloud-init & Template pillar tests — fully mocked, no live Proxmox.

Mirrors test_backup.py / test_provisioning.py style:
- Op functions: tiny fake apis (SimpleNamespace with monkeypatched _get/_post).
- Plan functions: fake apis that supply _get and config.node.
- Validator-rejection tests use pytest.raises(ProximoError).
- No shared mutable state; every test is self-contained.

Secret-masking tests verify that sentinel values (e.g. cipassword="SENTINEL_PW_123") do
NOT appear anywhere in plan.as_dict() serialized to JSON — masking at display-time while
leaking in plan.current would NOT pass these tests.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from proximo.backends import ProximoError
from proximo.cloudinit import (
    _mask_secrets,
    capture_cloudinit_undo,
    cloudinit_get,
    cloudinit_set,
    plan_cloudinit_set,
    plan_template_convert,
    template_convert,
)
from proximo.planning import RISK_HIGH, RISK_MEDIUM

# ---------------------------------------------------------------------------
# Test helpers / fakes
# ---------------------------------------------------------------------------

_SENTINEL_PASSWORD = "SENTINEL_PW_123"  # noqa: S105 — test sentinel, not a real credential


def _fake_api(node: str = "pve"):
    """Minimal fake api with config.node and recorded _get/_post calls."""
    seen: dict = {}

    def fake_get(path):
        seen["get_path"] = path
        return seen.get("_get_return", {})

    def fake_post(path, data=None):
        seen["post_path"] = path
        seen["post_data"] = data
        return seen.get("_post_return", None)

    api = SimpleNamespace(
        config=SimpleNamespace(node=node),
        _get=fake_get,
        _post=fake_post,
        seen=seen,
    )
    return api


class _ConfigApi:
    """Fake api for plan functions that need _get to return VM config."""

    def __init__(self, config_data: dict | None, node: str = "pve",
                 raise_404: bool = False, raise_transient: bool = False):
        self.config = SimpleNamespace(node=node)
        self._config = config_data
        self._raise_404 = raise_404
        self._raise_transient = raise_transient
        self.get_calls: list = []

    def _get(self, path: str):
        self.get_calls.append(path)
        if self._raise_transient:
            raise RuntimeError("API timeout")
        if self._raise_404:
            err = RuntimeError("not found")
            err.response = SimpleNamespace(status_code=404)
            raise err
        return self._config


# ---------------------------------------------------------------------------
# _mask_secrets: core masking utility
# ---------------------------------------------------------------------------

def test_mask_secrets_masks_cipassword():
    d = {"ciuser": "admin", "cipassword": _SENTINEL_PASSWORD}
    result = _mask_secrets(d)
    assert result["cipassword"] == "***"
    assert result["ciuser"] == "admin"


def test_mask_secrets_leaves_non_secret_unchanged():
    d = {"ciuser": "bob", "sshkeys": "ssh-ed25519 AAAAB3 user@host", "nameserver": "8.8.8.8"}
    result = _mask_secrets(d)
    assert result == d


def test_mask_secrets_returns_copy_not_inplace():
    d = {"cipassword": _SENTINEL_PASSWORD}
    result = _mask_secrets(d)
    assert d["cipassword"] == _SENTINEL_PASSWORD   # original unchanged
    assert result["cipassword"] == "***"


def test_mask_secrets_empty_dict():
    assert _mask_secrets({}) == {}


# ---------------------------------------------------------------------------
# cloudinit_get: URL shape, key filtering, secret masking
# ---------------------------------------------------------------------------

def test_cloudinit_get_builds_correct_path():
    api = _fake_api()
    api.seen["_get_return"] = {"ciuser": "admin", "cores": 2, "memory": 1024}
    cloudinit_get(api, "200")
    assert api.seen["get_path"] == "/nodes/pve/qemu/200/config"


def test_cloudinit_get_uses_provided_node():
    api = _fake_api()
    api.seen["_get_return"] = {}
    cloudinit_get(api, "200", node="node2")
    assert "/nodes/node2/" in api.seen["get_path"]


def test_cloudinit_get_uses_config_node_when_none():
    api = _fake_api(node="mynode")
    api.seen["_get_return"] = {}
    cloudinit_get(api, "200")
    assert "/nodes/mynode/" in api.seen["get_path"]


def test_cloudinit_get_filters_to_ci_keys_only():
    api = _fake_api()
    api.seen["_get_return"] = {
        "ciuser": "admin",
        "sshkeys": "ssh-ed25519 AAA",
        "cores": 4,
        "memory": 2048,
        "scsi0": "local:100/vm-100-disk-0.raw",
        "net0": "virtio,bridge=vmbr0",
        "ipconfig0": "ip=dhcp",
    }
    result = cloudinit_get(api, "200")
    assert "ciuser" in result
    assert "sshkeys" in result
    assert "ipconfig0" in result
    assert "cores" not in result
    assert "memory" not in result
    assert "scsi0" not in result
    assert "net0" not in result


def test_cloudinit_get_masks_cipassword():
    api = _fake_api()
    api.seen["_get_return"] = {"ciuser": "admin", "cipassword": _SENTINEL_PASSWORD}
    result = cloudinit_get(api, "200")
    assert result["cipassword"] == "***"
    assert _SENTINEL_PASSWORD not in json.dumps(result)


def test_cloudinit_get_returns_empty_dict_when_no_ci_keys():
    api = _fake_api()
    api.seen["_get_return"] = {"cores": 2, "memory": 1024}
    result = cloudinit_get(api, "200")
    assert result == {}


def test_cloudinit_get_returns_empty_dict_when_none():
    api = _fake_api()
    api.seen["_get_return"] = None
    result = cloudinit_get(api, "200")
    assert result == {}


def test_cloudinit_get_rejects_lxc():
    api = _fake_api()
    with pytest.raises(ProximoError, match="QEMU-only"):
        cloudinit_get(api, "200", kind="lxc")


def test_cloudinit_get_rejects_bad_vmid():
    api = _fake_api()
    with pytest.raises(ProximoError):
        cloudinit_get(api, "not-a-number")


def test_cloudinit_get_rejects_bad_node():
    api = _fake_api()
    with pytest.raises(ProximoError):
        cloudinit_get(api, "200", node="bad node!")


# ---------------------------------------------------------------------------
# cloudinit_set: URL shape, data forwarding, key validation
# ---------------------------------------------------------------------------

def test_cloudinit_set_builds_correct_path():
    api = _fake_api()
    cloudinit_set(api, "200", {"ciuser": "alice"})
    assert api.seen["post_path"] == "/nodes/pve/qemu/200/config"


def test_cloudinit_set_uses_provided_node():
    api = _fake_api()
    cloudinit_set(api, "200", {"ciuser": "alice"}, node="node3")
    assert "/nodes/node3/" in api.seen["post_path"]


def test_cloudinit_set_sends_changes_as_post_data():
    api = _fake_api()
    cloudinit_set(api, "200", {"ciuser": "alice", "nameserver": "1.1.1.1"})
    assert api.seen["post_data"] == {"ciuser": "alice", "nameserver": "1.1.1.1"}


def test_cloudinit_set_accepts_ipconfig_keys():
    api = _fake_api()
    cloudinit_set(api, "200", {"ipconfig0": "ip=dhcp", "ipconfig1": "ip=10.0.0.5/24,gw=10.0.0.1"})
    assert api.seen["post_data"]["ipconfig0"] == "ip=dhcp"


def test_cloudinit_set_accepts_all_scalar_keys():
    api = _fake_api()
    valid_keys = {"ciuser": "u", "cipassword": "pw", "sshkeys": "k",  # noqa: S106
                  "nameserver": "8.8.8.8", "searchdomain": "example.com",
                  "citype": "nocloud", "cicustom": "meta=local:snippets/x.yaml"}
    cloudinit_set(api, "200", valid_keys)
    assert set(api.seen["post_data"].keys()) == set(valid_keys.keys())


def test_cloudinit_set_transmits_real_secret_value_to_api():
    """The SET path must send the REAL cipassword to PVE — not masked.

    This is the dual of 'masked in outputs': if someone accidentally masks the
    outbound POST data, the password gets set to '***' on PVE silently.
    Masking is read-side only; the mutation payload is transmitted as-is.
    """
    api = _fake_api()
    cloudinit_set(api, "200", {"cipassword": _SENTINEL_PASSWORD})
    # Real value must reach PVE — NOT masked
    assert api.seen["post_data"]["cipassword"] == _SENTINEL_PASSWORD


def test_cloudinit_set_rejects_unknown_key():
    api = _fake_api()
    with pytest.raises(ProximoError, match="unknown or unsupported"):
        cloudinit_set(api, "200", {"ciuser": "alice", "notacikey": "bad"})


def test_cloudinit_set_rejects_disk_key():
    api = _fake_api()
    with pytest.raises(ProximoError, match="unknown or unsupported"):
        cloudinit_set(api, "200", {"scsi0": "local:100/vm.raw"})


def test_cloudinit_set_rejects_empty_changes():
    api = _fake_api()
    with pytest.raises(ProximoError):
        cloudinit_set(api, "200", {})


def test_cloudinit_set_rejects_none_changes():
    api = _fake_api()
    with pytest.raises(ProximoError):
        cloudinit_set(api, "200", None)  # type: ignore[arg-type]


def test_cloudinit_set_rejects_lxc():
    api = _fake_api()
    with pytest.raises(ProximoError, match="QEMU-only"):
        cloudinit_set(api, "200", {"ciuser": "u"}, kind="lxc")


def test_cloudinit_set_rejects_bad_vmid():
    api = _fake_api()
    with pytest.raises(ProximoError):
        cloudinit_set(api, "abc", {"ciuser": "u"})


def test_cloudinit_set_rejects_bad_node():
    api = _fake_api()
    with pytest.raises(ProximoError):
        cloudinit_set(api, "200", {"ciuser": "u"}, node="bad/node")


def test_cloudinit_set_rejects_ipconfig_out_of_range():
    """ipconfig32 is outside the accepted range (0-31)."""
    api = _fake_api()
    with pytest.raises(ProximoError, match="unknown or unsupported"):
        cloudinit_set(api, "200", {"ipconfig32": "ip=dhcp"})


def test_cloudinit_set_returns_raw_result():
    """POST /config returns None for sync stores; do not validate or raise on None."""
    api = _fake_api()
    api.seen["_post_return"] = None
    result = cloudinit_set(api, "200", {"ciuser": "u"})
    assert result is None


# ---------------------------------------------------------------------------
# template_convert: URL shape, guard rails
# ---------------------------------------------------------------------------

def test_template_convert_builds_correct_path():
    api = _fake_api()
    template_convert(api, "300")
    assert api.seen["post_path"] == "/nodes/pve/qemu/300/template"


def test_template_convert_uses_provided_node():
    api = _fake_api()
    template_convert(api, "300", node="pve2")
    assert "/nodes/pve2/" in api.seen["post_path"]


def test_template_convert_uses_config_node_when_none():
    api = _fake_api(node="nodeX")
    template_convert(api, "300")
    assert "/nodes/nodeX/" in api.seen["post_path"]


def test_template_convert_sends_no_body():
    """The PVE endpoint takes no body params; we must not send junk data. [SR-6]"""
    api = _fake_api()
    template_convert(api, "300")
    assert api.seen.get("post_data") is None


def test_template_convert_returns_raw_result():
    """Return value is raw (None or UPID); do not validate. [SR-6]"""
    api = _fake_api()
    api.seen["_post_return"] = None
    assert template_convert(api, "300") is None


def test_template_convert_rejects_lxc():
    api = _fake_api()
    with pytest.raises(ProximoError, match="QEMU-only"):
        template_convert(api, "300", kind="lxc")


def test_template_convert_rejects_bad_vmid():
    api = _fake_api()
    with pytest.raises(ProximoError):
        template_convert(api, "abc")


def test_template_convert_rejects_bad_node():
    api = _fake_api()
    with pytest.raises(ProximoError):
        template_convert(api, "300", node="bad node!")


# ---------------------------------------------------------------------------
# capture_cloudinit_undo
# ---------------------------------------------------------------------------

def test_capture_undo_returns_prior_config():
    api = _ConfigApi({"ciuser": "alice", "sshkeys": "ssh-ed25519 AAA", "cores": 2})
    result = capture_cloudinit_undo(api, "200")
    assert "ciuser" in result["prior_ci_config"]
    assert "sshkeys" in result["prior_ci_config"]
    assert "cores" not in result["prior_ci_config"]   # non-CI keys filtered


def test_capture_undo_strips_secrets_from_prior():
    # Secret keys are STRIPPED from the undo record (not masked) so a revert can never re-apply a
    # masked placeholder like "***" as a real password. Non-secret fields are retained for revert.
    api = _ConfigApi({"ciuser": "alice", "cipassword": _SENTINEL_PASSWORD})
    result = capture_cloudinit_undo(api, "200")
    assert "cipassword" not in result["prior_ci_config"]   # stripped, not carried as "***"
    assert result["prior_ci_config"]["ciuser"] == "alice"  # non-secret field retained
    assert _SENTINEL_PASSWORD not in json.dumps(result)


def test_capture_undo_notes_secret_caveat():
    """If any secret key is present (even masked), a caveat must be noted."""
    api = _ConfigApi({"cipassword": _SENTINEL_PASSWORD})
    result = capture_cloudinit_undo(api, "200")
    assert result["secret_undo_caveat"] is not None
    assert "cipassword" in result["secret_undo_caveat"].lower() or "secret" in result["secret_undo_caveat"].lower()


def test_capture_undo_no_caveat_when_no_secrets():
    api = _ConfigApi({"ciuser": "alice", "sshkeys": "ssh-ed25519 AAA"})
    result = capture_cloudinit_undo(api, "200")
    assert result["secret_undo_caveat"] is None


# ---------------------------------------------------------------------------
# plan_cloudinit_set: PLAN-before-mutate + secret masking + diff surface
# ---------------------------------------------------------------------------

def test_plan_cloudinit_set_is_medium_risk():
    api = _ConfigApi({"ciuser": "old-user"})
    p = plan_cloudinit_set(api, "200", {"ciuser": "new-user"})
    assert p.risk == RISK_MEDIUM


def test_plan_cloudinit_set_action_name():
    api = _ConfigApi({})
    p = plan_cloudinit_set(api, "200", {"ciuser": "u"})
    assert p.action == "pve_cloudinit_set"


def test_plan_cloudinit_set_target_includes_vmid():
    api = _ConfigApi({})
    p = plan_cloudinit_set(api, "200", {"ciuser": "u"})
    assert "200" in p.target


def test_plan_cloudinit_set_blast_mentions_reboot():
    api = _ConfigApi({})
    p = plan_cloudinit_set(api, "200", {"ciuser": "u"})
    text = " ".join(p.blast_radius).lower()
    assert "reboot" in text or "regen" in text or "next" in text


def test_plan_cloudinit_set_blast_warns_lockout():
    api = _ConfigApi({})
    p = plan_cloudinit_set(api, "200", {"sshkeys": "ssh-ed25519 AAA"})
    text = " ".join(p.blast_radius).lower()
    assert "lock" in text or "access" in text


def test_plan_cloudinit_set_current_populated_from_live_read():
    api = _ConfigApi({"ciuser": "alice", "sshkeys": "ssh-ed25519 AAA"})
    p = plan_cloudinit_set(api, "200", {"ciuser": "bob"})
    assert p.current.get("ciuser") == "alice"


def test_plan_cloudinit_set_change_lists_keys():
    api = _ConfigApi({})
    p = plan_cloudinit_set(api, "200", {"ciuser": "bob", "nameserver": "1.1.1.1"})
    assert "ciuser" in p.change
    assert "nameserver" in p.change


def test_plan_cloudinit_set_rejects_unknown_key():
    api = _ConfigApi({})
    with pytest.raises(ProximoError, match="unknown or unsupported"):
        plan_cloudinit_set(api, "200", {"notacikey": "bad"})


def test_plan_cloudinit_set_rejects_empty_changes():
    api = _ConfigApi({})
    with pytest.raises(ProximoError):
        plan_cloudinit_set(api, "200", {})


def test_plan_cloudinit_set_rejects_lxc():
    api = _ConfigApi({})
    with pytest.raises(ProximoError, match="QEMU-only"):
        plan_cloudinit_set(api, "200", {"ciuser": "u"}, kind="lxc")


# --- SECRET MASKING in plan: the critical invariant ---

def test_plan_cloudinit_set_secret_not_in_blast_radius():
    """cipassword sentinel must NOT appear in blast_radius."""
    api = _ConfigApi({"cipassword": _SENTINEL_PASSWORD})
    p = plan_cloudinit_set(api, "200", {"cipassword": _SENTINEL_PASSWORD})
    text = " ".join(p.blast_radius)
    assert _SENTINEL_PASSWORD not in text


def test_plan_cloudinit_set_secret_not_in_current():
    """cipassword sentinel must NOT appear in plan.current (comes from cloudinit_get → masked)."""
    api = _ConfigApi({"cipassword": _SENTINEL_PASSWORD})
    p = plan_cloudinit_set(api, "200", {"cipassword": "newpassword123"})
    assert p.current.get("cipassword") == "***"
    assert _SENTINEL_PASSWORD not in json.dumps(p.current)


def test_plan_cloudinit_set_secret_not_in_plan_dict_serialized():
    """Full plan.as_dict() JSON must not contain the sentinel — masking must be complete."""
    api = _ConfigApi({"cipassword": _SENTINEL_PASSWORD})
    p = plan_cloudinit_set(api, "200", {"cipassword": _SENTINEL_PASSWORD})
    serialized = json.dumps(p.as_dict())
    assert _SENTINEL_PASSWORD not in serialized
    assert "***" in serialized


def test_plan_cloudinit_set_secret_notes_undo_caveat_when_password_in_changes():
    """When cipassword is in the changes, the plan must note the undo caveat."""
    api = _ConfigApi({})
    p = plan_cloudinit_set(api, "200", {"cipassword": "newpw"})
    text = " ".join(p.blast_radius).lower()
    assert "password" in text or "secret" in text or "undo" in text or "mask" in text


# --- Read failure honesty ---

def test_plan_cloudinit_set_transient_read_failure_discloses_uncertainty():
    api = _ConfigApi(None, raise_transient=True)
    p = plan_cloudinit_set(api, "200", {"ciuser": "u"})
    # Must still return a valid plan (not raise), but disclose the uncertainty.
    assert p.risk == RISK_MEDIUM
    text = " ".join(p.blast_radius + p.risk_reasons).lower()
    assert "could not" in text or "unavailable" in text or "failed" in text


def test_plan_cloudinit_set_read_failure_current_is_empty():
    api = _ConfigApi(None, raise_transient=True)
    p = plan_cloudinit_set(api, "200", {"ciuser": "u"})
    assert p.current == {}


def test_plan_cloudinit_set_reads_current_config():
    """Verify that the plan reads live config (safe read) and surfaces it."""
    api = _ConfigApi({"ciuser": "existing", "sshkeys": "ssh-rsa BBBB"})
    plan_cloudinit_set(api, "200", {"ciuser": "new"})
    assert len(api.get_calls) >= 1


# ---------------------------------------------------------------------------
# plan_template_convert: RISK_HIGH, irreversible, NO undo claim
# ---------------------------------------------------------------------------

def test_plan_template_convert_is_high_risk():
    api = _ConfigApi({"name": "myvm"})
    p = plan_template_convert(api, "300")
    assert p.risk == RISK_HIGH


def test_plan_template_convert_action_name():
    api = _ConfigApi({"name": "myvm"})
    p = plan_template_convert(api, "300")
    assert p.action == "pve_template_convert"


def test_plan_template_convert_target_includes_vmid():
    api = _ConfigApi({"name": "myvm"})
    p = plan_template_convert(api, "300")
    assert "300" in p.target


def test_plan_template_convert_blast_says_irreversible():
    api = _ConfigApi({"name": "myvm"})
    p = plan_template_convert(api, "300")
    text = " ".join(p.blast_radius).lower()
    assert "irreversible" in text or "one-way" in text or "no un-template" in text


def test_plan_template_convert_names_vm():
    api = _ConfigApi({"name": "my-important-vm"})
    p = plan_template_convert(api, "300")
    text = " ".join(p.blast_radius)
    assert "my-important-vm" in text


def test_plan_template_convert_note_explicitly_denies_undo():
    """The note field must clearly state there is no undo — no false recovery claim."""
    api = _ConfigApi({"name": "myvm"})
    p = plan_template_convert(api, "300")
    note_lower = p.note.lower()
    assert "no undo" in note_lower or "one-way" in note_lower or "irreversible" in note_lower


def test_plan_template_convert_blast_contains_no_undo_claim():
    """Blast radius must NOT contain language like 'you can revert' or 'undo is available'."""
    api = _ConfigApi({"name": "myvm"})
    p = plan_template_convert(api, "300")
    text = " ".join(p.blast_radius).lower()
    assert "you can revert" not in text
    assert "undo is available" not in text
    assert "undo snapshot" not in text


def test_plan_template_convert_not_found_stays_high_risk():
    api = _ConfigApi(None, raise_404=True)
    p = plan_template_convert(api, "300")
    assert p.risk == RISK_HIGH


def test_plan_template_convert_not_found_blast_says_will_fail():
    api = _ConfigApi(None, raise_404=True)
    p = plan_template_convert(api, "300")
    blast = " ".join(p.blast_radius).lower()
    assert "fail" in blast or "not found" in blast


def test_plan_template_convert_not_found_blast_not_contradictory():
    """When not found, must NOT also say 'IRREVERSIBLY converts' — nothing is converted."""
    api = _ConfigApi(None, raise_404=True)
    p = plan_template_convert(api, "300")
    blast = " ".join(p.blast_radius).lower()
    assert "irreversibly converts" not in blast


def test_plan_template_convert_transient_error_is_high_discloses_uncertainty():
    api = _ConfigApi(None, raise_transient=True)
    p = plan_template_convert(api, "300")
    assert p.risk == RISK_HIGH
    text = " ".join(p.blast_radius + p.risk_reasons).lower()
    assert "could not" in text or "failed" in text or "uncertainty" in text or "cannot confirm" in text


def test_plan_template_convert_rejects_lxc():
    api = _ConfigApi({})
    with pytest.raises(ProximoError, match="QEMU-only"):
        plan_template_convert(api, "300", kind="lxc")


def test_plan_template_convert_rejects_bad_vmid():
    api = _ConfigApi({})
    with pytest.raises(ProximoError):
        plan_template_convert(api, "abc")


def test_plan_template_convert_already_template_warns():
    """If VM already has template=1, the plan should surface that."""
    api = _ConfigApi({"name": "myvm", "template": 1})
    p = plan_template_convert(api, "300")
    text = " ".join(p.blast_radius).lower()
    assert "already" in text or "template" in text


# ---------------------------------------------------------------------------
# ipconfig range validation
# ---------------------------------------------------------------------------

def test_cloudinit_set_accepts_ipconfig_at_boundary_31():
    api = _fake_api()
    cloudinit_set(api, "200", {"ipconfig31": "ip=dhcp"})
    assert "ipconfig31" in api.seen["post_data"]


def test_cloudinit_set_accepts_ipconfig0():
    api = _fake_api()
    cloudinit_set(api, "200", {"ipconfig0": "ip=dhcp"})
    assert "ipconfig0" in api.seen["post_data"]


def test_cloudinit_set_rejects_ipconfig32():
    api = _fake_api()
    with pytest.raises(ProximoError, match="unknown or unsupported"):
        cloudinit_set(api, "200", {"ipconfig32": "ip=dhcp"})


def test_cloudinit_set_rejects_ipconfig_with_non_numeric_suffix():
    api = _fake_api()
    with pytest.raises(ProximoError, match="unknown or unsupported"):
        cloudinit_set(api, "200", {"ipconfigabc": "ip=dhcp"})
