"""Confirm=True sweep — pve_guest wrapper welds.

Closes the coverage-audit gap (`.scratch/2026-07-14-tool-coverage-audit-findings.json`,
module `src/proximo/tools/pve_guest.py`, 8 high + 2 med confirmed findings): every tool
below has its confirm=False PLAN branch tested elsewhere (test_provisioning.py,
test_config_edit.py, test_cloudinit.py, test_disk_ops.py, test_storage.py) but its
confirm=True EXECUTE branch — the wrapper's own `_audited(...)` call — was never invoked
through the actual `server.pve_*` wrapper, only through the underlying op/plan functions,
bypassing the wrapper's own argument-forwarding and _audited() wiring.

Mirrors the `_wire()` idiom in tests/test_server_plan.py:110-131 (already re-used and
review-approved in tests/test_confirm_sweep_pve_firewall_network.py): `proximo.server._svc`
is monkeypatched to a fake api + a REAL AuditLedger in tmp_path, so a confirm=True call
proves three welds at once:
  1. return shape — status is the EXECUTED shape ("ok"/"submitted"), never "plan";
  2. the fake api captured the underlying call (verb + path + data) — reusing the fake
     idioms already established in test_provisioning.py/test_config_edit.py/
     test_cloudinit.py/test_disk_ops.py/test_storage.py;
  3. the ledger recorded a confirmed mutation — structural asserts only (action, mutation,
     outcome, detail.confirmed), never exact prose.

Three tools carry a unique weld beyond the generic three, called out explicitly by the
audit-fixes plan (Task 2):
  - pve_guest_config_revert IS the UNDO mechanism — the test asserts the CALLER-SUPPLIED
    prior_config values (not the live current state) actually reach the PUT body.
  - pve_cloudinit_set has a wrapper-LOCAL try/except (pve_guest.py:643-654) that degrades
    gracefully when undo-capture fails: outcome="ok:undo_unavailable" is recorded (never
    silent) and the mutation still proceeds. Both the normal and degrade paths are tested.
  - pve_disk_move's delete_source=True is the HIGH-risk "no easy undo" branch (docstring's
    own words) — the test asserts the 'delete' flag actually reaches the API body.

The fake api's `_get` is path-aware, reusing the idioms already established in the sibling
test modules: cluster/resource reads return one pre-existing guest (vmid 200, used as the
clone source / collision baseline), storage-status reads return numeric avail/total,
guest-config reads return a fixed config with a digest (so PUT/POST bodies that forward a
digest, or a revert that must restore PRIOR values over live-CURRENT ones, can be asserted
precisely). This lets every tool's _plan() build (which runs even on confirm=True — no
plan, no mutation) resolve without raising, while the mutation calls land in per-verb
capture lists.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from urllib.parse import quote

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig


class _FakeHttpResponse:
    """Minimal stand-in for the httpx-shaped response disk_resize's _client.request needs."""

    def __init__(self, data: str = "UPID:pve:00003:0:0:0:qmresize:100:root@pam:"):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return {"data": self._data}


class _Api:
    """Path-aware fake Proxmox api: records every _post/_put/_delete/_client.request call,
    and answers _get reads just enough for the PLAN builders (which always run first, even
    on confirm=True) to resolve without raising.

    One pre-existing guest (vmid 200) is returned for every cluster/resources read — used as
    the clone source and as a non-colliding baseline for create/clone vmid checks. Guest-config
    reads return a fixed dict carrying a digest, so digest-forwarding and (for config_revert)
    prior-vs-current divergence can be asserted precisely.
    """

    def __init__(self, node: str = "pve"):
        self.config = SimpleNamespace(node=node)
        self.gets: list[str] = []
        self.posts: list[tuple[str, dict | None]] = []
        self.puts: list[tuple[str, dict | None]] = []
        self.deletes: list[tuple[str, dict | None]] = []
        self.client_puts: list[tuple[str, dict | None]] = []

    def _get(self, path):
        self.gets.append(path)
        if "/cluster/resources" in path:
            return [{"vmid": 200}]
        if path.endswith("/status"):
            return {"avail": 500_000_000_000, "total": 1_000_000_000_000}
        if path.endswith("/config"):
            # live/current guest config — deliberately DIFFERENT from any prior_config a test
            # hands to pve_guest_config_revert, so a revert-forwards-prior (not current) bug
            # would be caught.
            return {"cores": 4, "memory": 1024, "digest": "cfg-digest-1"}
        return {}

    def _post(self, path, data=None):
        self.posts.append((path, data))
        return "UPID:pve:00001:0:0:0:task:100:root@pam:"

    def _put(self, path, data=None):
        self.puts.append((path, data))
        return None

    def _delete(self, path, params=None):
        self.deletes.append((path, params))
        return "UPID:pve:00002:0:0:0:task:100:root@pam:"

    def _auth_header(self):
        return {"Authorization": "PVEAPIToken=fake"}

    def _client_request(self, method, path, headers=None, data=None):
        self.client_puts.append((path, data))
        return _FakeHttpResponse()

    @property
    def _client(self):
        return SimpleNamespace(request=self._client_request)


def _wire(tmp_path, monkeypatch):
    """The `_wire()` idiom from tests/test_server_plan.py:110-131."""
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        ct_allowlist=frozenset({"*"}), audit_log_path=log,
    )
    api = _Api()
    exec_ = SimpleNamespace()  # unused by pve_guest's non-exec wrappers
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, exec_, ledger))
    return cfg, api, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _confirmed_entry(log: str, action: str, outcome: str) -> dict:
    entries = [e for e in _entries(log) if e["action"] == action and e["outcome"] == outcome]
    assert len(entries) == 1, f"expected exactly one {action!r}/{outcome!r} ledger entry, got {entries}"
    return entries[0]


# ---------------------------------------------------------------------------
# Homogeneous sweep — table-driven over the tools with no unique weld beyond
# "confirm=True reaches the right verb/path/data and records a confirmed mutation".
# ---------------------------------------------------------------------------

_SWEEP_CASES = [
    pytest.param(
        "pve_create_vm",
        dict(vmid="600", options={"cores": 2, "memory": 1024}),
        "submitted", "posts", "/nodes/pve/qemu",
        # create_vm() builds data={"vmid": vmid, **opts} verbatim.
        {"vmid": "600", "cores": 2, "memory": 1024},
        id="create_vm",
    ),
    pytest.param(
        "pve_clone",
        dict(vmid="200", newid="301", kind="lxc"),
        "submitted", "posts", "/nodes/pve/lxc/200/clone",
        # clone_guest(): full/name/pool/storage all default False/None here, so only
        # newid is ever added to data={"newid": newid}.
        {"newid": "301"},
        id="clone",
    ),
    pytest.param(
        "pve_guest_config_set",
        dict(vmid="150", changes={"cores": 4}, kind="lxc"),
        "ok", "puts", "/nodes/pve/lxc/150/config",
        # guest_config_set(): data=dict(to_set) + digest from the fixture's GET
        # (cfg-digest-1); to_delete is empty so no "delete" key.
        {"cores": 4, "digest": "cfg-digest-1"},
        id="guest_config_set",
    ),
    pytest.param(
        "pve_storage_content_delete",
        dict(storage="local", volid="local:iso/debian.iso"),
        "submitted", "deletes",
        f"/nodes/pve/storage/local/content/{quote('local:iso/debian.iso', safe='')}",
        # content_delete() calls api._delete(path) with NO params arg -> fake captures params=None.
        None,
        id="storage_content_delete",
    ),
    pytest.param(
        "pve_template_convert",
        dict(vmid="500", kind="qemu"),
        "submitted", "posts", "/nodes/pve/qemu/500/template",
        # template_convert() calls api._post(path) with NO data arg -> fake captures data=None.
        None,
        id="template_convert",
    ),
    pytest.param(
        "pve_disk_resize",
        dict(vmid="150", disk="scsi0", size="+10G", kind="qemu"),
        "submitted", "client_puts", "/nodes/pve/qemu/150/resize",
        # disk_resize(): '+10G' is an unambiguous relative grow (no probe read), so
        # data={"disk": disk, "size": size} verbatim.
        {"disk": "scsi0", "size": "+10G"},
        id="disk_resize",
    ),
    pytest.param(
        "pve_storage_download",
        dict(storage="local", content="iso", url="https://example.test/debian.iso",
             filename="debian.iso"),
        "submitted", "posts", "/nodes/pve/storage/local/download-url",
        # storage_download_url(): checksum/checksum_algorithm both None -> omitted.
        {"content": "iso", "url": "https://example.test/debian.iso", "filename": "debian.iso"},
        id="storage_download",
    ),
    pytest.param(
        "pve_disk_move",
        dict(vmid="150", disk="scsi0", target_storage="fast", kind="qemu", delete_source=False),
        "submitted", "posts", "/nodes/pve/qemu/150/move_disk",
        # disk_move() QEMU branch: data={"disk": disk, "storage": target_storage};
        # delete_source=False -> no "delete" key.
        {"disk": "scsi0", "storage": "fast"},
        id="disk_move_delete_source_false",
    ),
]


@pytest.mark.parametrize(
    "tool_name,kwargs,expected_status,capture,path,data_exact", _SWEEP_CASES,
)
def test_confirm_true_executes_forwards_and_records(
    tmp_path, monkeypatch, tool_name, kwargs, expected_status, capture, path, data_exact,
):
    """confirm=True executes (never 'plan'), the fake captured the forwarded call, and the
    ledger recorded a confirmed mutation — the three welds the audit found untested."""
    _, api, _, log = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)

    out = fn(confirm=True, **kwargs)

    # weld 1: return shape is the EXECUTED shape, never "plan"
    assert out["status"] == expected_status
    assert out["status"] != "plan"

    # weld 2: the fake captured the underlying call at the expected verb + path, with the
    # EXACT forwarded payload (full dict equality — an accidental extra field now fails).
    calls = getattr(api, capture)
    assert calls, f"{tool_name} confirm=True never reached api.{capture}"
    call_path, call_data = calls[-1]
    assert call_path == path
    assert call_data == data_exact

    # weld 3: ledger structural asserts — never exact prose
    entry = _confirmed_entry(log, tool_name, expected_status)
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


# ---------------------------------------------------------------------------
# pve_guest_config_revert — unique weld: IS the UNDO mechanism. Assert the caller-supplied
# prior_config values (NOT the fake's live/current config) actually reach the PUT body.
# ---------------------------------------------------------------------------


def test_guest_config_revert_confirm_forwards_prior_payload_to_api(tmp_path, monkeypatch):
    """pve_guest_config_revert confirm=True is the recovery path an operator reaches for
    after a bad pve_guest_config_set. The docstring's promise — 'prior_config is what makes
    the change revertible' — is only real if the PRIOR values (not whatever is live right
    now) land in the PUT body. The fake's live config (cores=4, memory=1024) deliberately
    differs from prior_config (cores=2, memory=512) so a bug that re-sent the current state
    instead of the caller-supplied prior would be caught."""
    _, api, _, log = _wire(tmp_path, monkeypatch)

    prior_config = {"cores": 2, "memory": 512}
    out = server.pve_guest_config_revert(
        vmid="777", prior_config=prior_config, kind="lxc", confirm=True,
    )

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    assert api.puts, "pve_guest_config_revert confirm=True never reached api._put"
    call_path, call_data = api.puts[-1]
    assert call_path == "/nodes/pve/lxc/777/config"
    # exact: the UNDO payload actually reaching the API is the caller-supplied PRIOR values
    # (cores/memory both on the "lxc" safe-set allowlist, so both are settable — none skipped)
    # plus the CURRENT digest for optimistic-locking, never the live/current cores=4/memory=1024
    # (per the fake's fixed config fixture) and no "delete" key (current keys == prior keys, so
    # nothing needs removing).
    assert call_data == {"cores": 2, "memory": 512, "digest": "cfg-digest-1"}

    entry = _confirmed_entry(log, "pve_guest_config_revert", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


# ---------------------------------------------------------------------------
# pve_cloudinit_set — unique weld: BOTH the normal undo-capture path AND the
# undo-capture-fails degrade branch (outcome="ok:undo_unavailable", mutation still proceeds).
# ---------------------------------------------------------------------------


def test_cloudinit_set_confirm_executes_captures_undo_and_records(tmp_path, monkeypatch):
    """Normal path: undo capture succeeds, outcome stays 'ok', and the mutation reaches
    the API with the caller's changes."""
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_cloudinit_set(vmid="500", changes={"ciuser": "admin"}, confirm=True)

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    assert api.posts, "pve_cloudinit_set confirm=True never reached api._post"
    call_path, call_data = api.posts[-1]
    assert call_path == "/nodes/pve/qemu/500/config"
    # exact: cloudinit_set() posts the validated changes dict verbatim — no digest, no
    # extra cloud-init keys smuggled in.
    assert call_data == {"ciuser": "admin"}

    assert "undo_record" in out
    assert out["undo_record"]["secret_undo_caveat"] is None

    entry = _confirmed_entry(log, "pve_cloudinit_set", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


def test_cloudinit_set_confirm_degrades_when_undo_capture_fails_but_still_mutates(
    tmp_path, monkeypatch,
):
    """The wrapper-local try/except (pve_guest.py:643-654) must NOT block the mutation when
    capture_cloudinit_undo raises: outcome degrades to 'ok:undo_unavailable' — recorded to
    the ledger, not silent — and the config POST still proceeds."""
    _, api, _, log = _wire(tmp_path, monkeypatch)

    def _boom(*args, **kwargs):
        raise RuntimeError("undo capture boom")

    monkeypatch.setattr("proximo.tools.pve_guest.capture_cloudinit_undo", _boom)

    out = server.pve_cloudinit_set(vmid="500", changes={"ciuser": "admin"}, confirm=True)

    # degraded status — distinct from both "plan" and the clean "ok" of the sibling test above
    assert out["status"] == "ok:undo_unavailable"
    assert out["status"] != "plan"

    # the mutation still proceeded despite the undo-capture failure — degrade, not block
    assert api.posts, "pve_cloudinit_set must still mutate when undo-capture fails"
    call_path, call_data = api.posts[-1]
    assert call_path == "/nodes/pve/qemu/500/config"
    # exact: the undo-capture failure must not leak into (or shrink) the forwarded payload.
    assert call_data == {"ciuser": "admin"}

    # the degrade is disclosed in the result, not papered over
    assert out["undo_record"]["prior_ci_config"] is None
    assert "undo capture failed" in out["undo_record"]["secret_undo_caveat"]

    entry = _confirmed_entry(log, "pve_cloudinit_set", "ok:undo_unavailable")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


# ---------------------------------------------------------------------------
# pve_disk_move delete_source=True — unique weld: the HIGH-risk "no easy undo" branch.
# Assert the 'delete' flag actually reaches the API body alongside the move.
# ---------------------------------------------------------------------------


def test_disk_move_confirm_delete_source_true_forwards_delete_flag_and_records(
    tmp_path, monkeypatch,
):
    """delete_source=True deletes the source copy after the move — the docstring calls it
    HIGH risk with 'no easy undo'. Assert the 'delete' flag actually lands in the API body
    (not just that some move happened), and that it still executes + records confirmed."""
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_disk_move(
        vmid="150", disk="scsi0", target_storage="fast", kind="lxc",
        delete_source=True, confirm=True,
    )

    assert out["status"] == "submitted"
    assert out["status"] != "plan"

    assert api.posts, "pve_disk_move confirm=True never reached api._post"
    call_path, call_data = api.posts[-1]
    assert call_path == "/nodes/pve/lxc/150/move_volume"
    # exact: the LXC branch uses 'volume' (not 'disk') + the delete flag, nothing else.
    assert call_data == {"volume": "scsi0", "storage": "fast", "delete": 1}

    entry = _confirmed_entry(log, "pve_disk_move", "submitted")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
