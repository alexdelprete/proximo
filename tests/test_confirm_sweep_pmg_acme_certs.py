"""Confirm=True sweep — PMG ACME accounts/plugins + node cert order/renew/revoke + custom-cert
upload wrapper welds (src/proximo/pmg.py + src/proximo/tools/pmg_mail.py, Wave 9g, full-surface
campaign) + THE SECRET CONTRACT proof for all THREE secret shapes (`eab-hmac-key`/`eab-kid`,
plugin `data`, custom-cert `key`).

Mirrors the `_wire()`/`_Pmg` idiom already established in `tests/test_confirm_sweep_pmg_pbs.py`
(itself mirroring `tests/test_confirm_sweep_pbs_node.py`'s own `_Pbs` template): `_svc` is
monkeypatched (the ONE shared audit ledger lives behind it — `_ledger()` reads `_svc()[3]`) and
`_pmg` is monkeypatched to a fake PmgBackend. This file duplicates its own `_Pmg`/`_wire` rather
than importing another confirm-sweep module's — same self-contained convention every
confirm-sweep module in this repo follows. New file (no prior confirm-sweep coverage existed for
these 19 methods) per the Wave 9g dispatch brief.

Each homogeneous confirm=True call proves the three welds every confirm-sweep module proves:
  1. return shape — status is the EXECUTED shape ("ok"/"submitted"), never "plan";
  2. the fake PmgBackend captured the underlying call (verb + path + EXACT payload, full dict
     equality — no subset matching);
  3. the ledger recorded a confirmed mutation — structural asserts only, never exact prose.

THE HEADLINE WELD (three secret shapes, per the dispatch brief's own §5 framing):
  - ACME account `eab-hmac-key`/`eab-kid`: never-in-ledger on `account_create` (the only verb
    that accepts them); DEFENSIVE strip on account list/get reads (neither read schema confirms
    the fields, but stripped anyway — silence is not evidence of absence).
  - ACME plugin `data` (base64 DNS-API credential blob): never-in-ledger on create/update;
    DEFENSIVE strip on plugin list/get reads (PMG's own list is schema-confirmed THIN/id-only —
    a real divergence from PBS's own MANDATORY strip, since PBS's list DOES echo `data`).
  - Custom-cert `key` (PEM private key): UNCONDITIONALLY redacted — never enters the plan
    factory, the response's own PLAN preview, or the ledger, even though the mutation's real
    call to PMG DOES carry the raw key (the mutation must actually work).
Sentinel values are low-entropy (all-lowercase, hyphenated) per this repo's fixture-sentinel
discipline (CLAUDE.md: a mixed-case test-sentinel password failed CI on v0.13.0).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig

_EAB_HMAC_KEY_SENTINEL = "sentinel-eab-hmac-key-value"  # noqa: S105 (test sentinel, not a real credential)
_EAB_KID_SENTINEL = "sentinel-eab-kid-value"
_PLUGIN_DATA_SENTINEL = "sentinel-plugin-dns-api-credential-blob"  # noqa: S105 (test sentinel)
_CERT_KEY_SENTINEL = "sentinel-cert-private-key-pem-placeholder"  # noqa: S105 (test sentinel)
_CERT_BODY_SENTINEL = "sentinel-cert-chain-pem-placeholder"

_ACCOUNT_CREATE_STRING = "sentinel-account-create-response-string"
_ACCOUNT_UPDATE_STRING = "sentinel-account-update-response-string"
_ACCOUNT_DELETE_STRING = "sentinel-account-delete-response-string"
_CERT_ORDER_STRING = "sentinel-cert-order-response-string"
_CERT_RENEW_STRING = "sentinel-cert-renew-response-string"
_CERT_REVOKE_STRING = "sentinel-cert-revoke-response-string"

_CUSTOM_UPLOAD_RESPONSE = {
    "filename": "api.pem", "fingerprint": ":".join(["ab"] * 32),
    "issuer": "sentinel-ca", "subject": "sentinel-node",
}


class _Pmg:
    """Path-aware fake PmgBackend: records every _get/_post/_put/_delete call.

    `_get` returns a fixed, secret-free account/plugin config for the CAPTURE reads
    (`plan_acme_account_update`/`_delete`, `plan_acme_plugin_update`/`_delete`) and an empty cert
    list for `/nodes/{node}/certificates/info` (the revoke/custom-upload CAPTURE-evidence read);
    every other GET path defaults to `[]`/`{}`. `_post`/`_put`/`_delete` return the
    schema-confirmed ambiguous strings for account create/update/delete and node cert
    order/renew/revoke, `null` for plugin create/update/delete and custom-cert delete, and the
    rich typed object for custom-cert upload.
    """

    def __init__(self, account_get_return=None, plugin_get_return=None, cert_info_return=None,
                 custom_upload_return=None):
        self._account_get_return = account_get_return or {
            "directory": "https://acme-v02.api.letsencrypt.org/directory",
        }
        self._plugin_get_return = plugin_get_return or {"plugin": "p1", "type": "dns"}
        self._cert_info_return = cert_info_return if cert_info_return is not None else []
        self._custom_upload_return = custom_upload_return or dict(_CUSTOM_UPLOAD_RESPONSE)
        self.gets: list[tuple[str, dict | None]] = []
        self.posts: list[tuple[str, dict | None]] = []
        self.puts: list[tuple[str, dict | None]] = []
        self.deletes: list[tuple[str, dict | None]] = []

    def _get(self, path, params=None):
        self.gets.append((path, params))
        if path == "/config/acme/account/default":
            return self._account_get_return
        if path == "/config/acme/plugins/p1":
            return self._plugin_get_return
        if path == "/nodes/pmg/certificates/info":
            return self._cert_info_return
        return []

    def _post(self, path, data=None):
        self.posts.append((path, data))
        if path == "/config/acme/account":
            return _ACCOUNT_CREATE_STRING
        if path == "/config/acme/plugins":
            return None
        if path == "/nodes/pmg/certificates/acme/api":
            return _CERT_ORDER_STRING
        if path == "/nodes/pmg/certificates/custom/api":
            return dict(self._custom_upload_return)
        return None

    def _put(self, path, data=None):
        self.puts.append((path, data))
        if path == "/config/acme/account/default":
            return _ACCOUNT_UPDATE_STRING
        if path == "/config/acme/plugins/p1":
            return None
        if path == "/nodes/pmg/certificates/acme/api":
            return _CERT_RENEW_STRING
        return None

    def _delete(self, path, params=None):
        self.deletes.append((path, params))
        if path == "/config/acme/account/default":
            return _ACCOUNT_DELETE_STRING
        if path == "/nodes/pmg/certificates/acme/api":
            return _CERT_REVOKE_STRING
        return None


class _Api:
    """Minimal PVE API stub — only needed so server._svc() resolves (the ONE shared ledger lives
    behind it); pmg.py's/tools/pmg_mail.py's tools never touch this backend."""

    def __init__(self):
        self.config = SimpleNamespace(node="pve")


def _wire(tmp_path, monkeypatch, **pmg_kwargs):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log,
    )
    api = _Api()
    pmg = _Pmg(**pmg_kwargs)
    exec_ = SimpleNamespace()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, exec_, ledger))
    monkeypatch.setattr(server, "_pmg", lambda: (SimpleNamespace(node="pmg"), pmg))
    return cfg, pmg, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _confirmed_entry(log: str, action: str, outcome: str) -> dict:
    entries = [e for e in _entries(log) if e["action"] == action and e["outcome"] == outcome]
    assert len(entries) == 1, f"expected exactly one {action!r}/{outcome!r} ledger entry, got {entries}"
    return entries[0]


# ---------------------------------------------------------------------------
# Homogeneous sweep — table-driven: "confirm=True reaches the right verb/path/data on the
# PmgBackend and records a confirmed mutation".
# ---------------------------------------------------------------------------

_SWEEP_CASES = [
    pytest.param(
        "pmg_acme_account_create",
        dict(contact="mailto:a@example.com"),
        "submitted", "posts", "/config/acme/account",
        {"contact": "mailto:a@example.com"},
        id="account_create",
    ),
    pytest.param(
        "pmg_acme_account_update",
        dict(name="default", contact="mailto:new@example.com"),
        "submitted", "puts", "/config/acme/account/default",
        {"contact": "mailto:new@example.com"},
        id="account_update",
    ),
    pytest.param(
        "pmg_acme_account_delete",
        dict(name="default"),
        "submitted", "deletes", "/config/acme/account/default",
        None,
        id="account_delete",
    ),
    pytest.param(
        "pmg_acme_plugin_create",
        dict(plugin_id="p1", plugin_type="dns"),
        "ok", "posts", "/config/acme/plugins",
        {"id": "p1", "type": "dns"},
        id="plugin_create",
    ),
    pytest.param(
        "pmg_acme_plugin_update",
        dict(plugin_id="p1", disable=True),
        "ok", "puts", "/config/acme/plugins/p1",
        {"disable": True},
        id="plugin_update",
    ),
    pytest.param(
        "pmg_acme_plugin_delete",
        dict(plugin_id="p1"),
        "ok", "deletes", "/config/acme/plugins/p1",
        None,
        id="plugin_delete",
    ),
    pytest.param(
        "pmg_node_cert_acme_order",
        dict(cert_type="api"),
        "submitted", "posts", "/nodes/pmg/certificates/acme/api",
        {},
        id="cert_acme_order",
    ),
    pytest.param(
        "pmg_node_cert_acme_renew",
        dict(cert_type="api"),
        "submitted", "puts", "/nodes/pmg/certificates/acme/api",
        {},
        id="cert_acme_renew",
    ),
    pytest.param(
        "pmg_node_cert_acme_revoke",
        dict(cert_type="api"),
        "submitted", "deletes", "/nodes/pmg/certificates/acme/api",
        None,
        id="cert_acme_revoke",
    ),
    pytest.param(
        "pmg_node_cert_custom_upload",
        dict(cert_type="api", certificates=_CERT_BODY_SENTINEL, key=_CERT_KEY_SENTINEL),
        "ok", "posts", "/nodes/pmg/certificates/custom/api",
        {"certificates": _CERT_BODY_SENTINEL, "key": _CERT_KEY_SENTINEL},
        id="cert_custom_upload",
    ),
    pytest.param(
        "pmg_node_cert_custom_delete",
        dict(cert_type="api"),
        "ok", "deletes", "/nodes/pmg/certificates/custom/api",
        None,
        id="cert_custom_delete",
    ),
]


@pytest.mark.parametrize(
    "tool_name,kwargs,expected_status,capture,path,data_exact", _SWEEP_CASES,
)
def test_confirm_true_executes_forwards_and_records(
    tmp_path, monkeypatch, tool_name, kwargs, expected_status, capture, path, data_exact,
):
    """confirm=True executes (never 'plan'), the fake captured the forwarded call, and the ledger
    recorded a confirmed mutation — the three welds every confirm-sweep module proves."""
    _, pmg, _, log = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)

    out = fn(confirm=True, **kwargs)

    # weld 1: return shape.
    assert out["status"] == expected_status
    assert out["status"] != "plan"

    # weld 2: the fake captured the underlying call at the expected verb + path.
    calls = getattr(pmg, capture)
    assert calls, f"{tool_name} confirm=True never reached pmg.{capture}"
    call_path, call_data = calls[-1]
    assert call_path == path
    if data_exact is not None:
        assert call_data == data_exact

    # weld 3: ledger structural asserts — never exact prose.
    entry = _confirmed_entry(log, tool_name, expected_status)
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


# ---------------------------------------------------------------------------
# Ambiguous-string returns (divergences #3/#4: PMG's account trio + cert trio ALL declare a bare
# STRING, unlike PBS's null-typed account trio / PVE's UPID-typed cert trio) — raw_result recorded
# in BOTH the response and the ledger detail.
# ---------------------------------------------------------------------------

def test_account_create_records_raw_result_both_places(tmp_path, monkeypatch):
    _, _, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_acme_account_create(contact="mailto:a@example.com", confirm=True)
    assert out["result"] == _ACCOUNT_CREATE_STRING
    entry = _confirmed_entry(log, "pmg_acme_account_create", "submitted")
    assert entry["detail"]["raw_result"] == _ACCOUNT_CREATE_STRING


def test_account_update_records_raw_result_both_places(tmp_path, monkeypatch):
    _, _, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_acme_account_update(name="default", contact="mailto:new@example.com", confirm=True)
    assert out["result"] == _ACCOUNT_UPDATE_STRING
    entry = _confirmed_entry(log, "pmg_acme_account_update", "submitted")
    assert entry["detail"]["raw_result"] == _ACCOUNT_UPDATE_STRING


def test_account_delete_records_raw_result_both_places(tmp_path, monkeypatch):
    _, _, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_acme_account_delete(name="default", confirm=True)
    assert out["result"] == _ACCOUNT_DELETE_STRING
    entry = _confirmed_entry(log, "pmg_acme_account_delete", "submitted")
    assert entry["detail"]["raw_result"] == _ACCOUNT_DELETE_STRING


def test_cert_order_records_raw_result_both_places(tmp_path, monkeypatch):
    _, _, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_node_cert_acme_order(cert_type="api", confirm=True)
    assert out["result"] == _CERT_ORDER_STRING
    entry = _confirmed_entry(log, "pmg_node_cert_acme_order", "submitted")
    assert entry["detail"]["raw_result"] == _CERT_ORDER_STRING


def test_cert_renew_records_raw_result_both_places(tmp_path, monkeypatch):
    _, _, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_node_cert_acme_renew(cert_type="api", confirm=True)
    assert out["result"] == _CERT_RENEW_STRING
    entry = _confirmed_entry(log, "pmg_node_cert_acme_renew", "submitted")
    assert entry["detail"]["raw_result"] == _CERT_RENEW_STRING


def test_cert_revoke_records_raw_result_both_places(tmp_path, monkeypatch):
    _, _, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_node_cert_acme_revoke(cert_type="api", confirm=True)
    assert out["result"] == _CERT_REVOKE_STRING
    entry = _confirmed_entry(log, "pmg_node_cert_acme_revoke", "submitted")
    assert entry["detail"]["raw_result"] == _CERT_REVOKE_STRING


def test_cert_custom_upload_returns_the_rich_public_object(tmp_path, monkeypatch):
    """divergence #9 — NOT ambiguous, a real typed object, outcome='ok'."""
    _, _, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_node_cert_custom_upload(
        cert_type="api", certificates=_CERT_BODY_SENTINEL, key=_CERT_KEY_SENTINEL, confirm=True,
    )
    assert out["status"] == "ok"
    assert out["result"]["fingerprint"] == _CUSTOM_UPLOAD_RESPONSE["fingerprint"]
    assert "key" not in out["result"]


# ---------------------------------------------------------------------------
# Dry-run (confirm=False) — proves the PLAN path never touches the PmgBackend's write verbs, and
# that update/delete plans CAPTURE current config via a live read.
# ---------------------------------------------------------------------------

def test_account_create_dry_run_never_posts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_acme_account_create(contact="mailto:a@example.com", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.posts


def test_account_update_dry_run_reads_but_never_puts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_acme_account_update(name="default", contact="mailto:new@example.com", confirm=False)
    assert out["status"] == "plan"
    assert out["current"]["directory"] == "https://acme-v02.api.letsencrypt.org/directory"
    assert not pmg.puts


def test_account_update_no_guard_dry_run_with_no_contact(tmp_path, monkeypatch):
    """Deliberate exception (divergence #11): omitting contact is a valid refresh, not an error."""
    _wire(tmp_path, monkeypatch)
    out = server.pmg_acme_account_update(name="default", confirm=False)
    assert out["status"] == "plan"
    assert "refresh" in out["change"].lower()


def test_account_delete_dry_run_reads_but_never_deletes(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_acme_account_delete(name="default", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.deletes


def test_plugin_create_dry_run_never_posts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_acme_plugin_create(plugin_id="p1", plugin_type="dns", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.posts


def test_plugin_update_dry_run_reads_but_never_puts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_acme_plugin_update(plugin_id="p1", disable=True, confirm=False)
    assert out["status"] == "plan"
    assert out["current"]["plugin"] == "p1"
    assert not pmg.puts


def test_plugin_delete_dry_run_reads_but_never_deletes(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_acme_plugin_delete(plugin_id="p1", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.deletes


def test_cert_order_dry_run_never_posts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_node_cert_acme_order(cert_type="api", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.posts


def test_cert_revoke_dry_run_reads_cert_info_but_never_deletes(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch, cert_info_return=[{"fingerprint": "AA:BB"}])
    out = server.pmg_node_cert_acme_revoke(cert_type="api", confirm=False)
    assert out["status"] == "plan"
    assert out["current"]["certificates"] == [{"fingerprint": "AA:BB"}]
    assert not pmg.deletes


def test_cert_custom_upload_dry_run_never_posts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_node_cert_custom_upload(
        cert_type="api", certificates=_CERT_BODY_SENTINEL, key=_CERT_KEY_SENTINEL, confirm=False,
    )
    assert out["status"] == "plan"
    assert not pmg.posts


def test_cert_custom_delete_dry_run_never_deletes(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_node_cert_custom_delete(cert_type="api", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.deletes


# ---------------------------------------------------------------------------
# Reads — confirm the wrapper reaches the PmgBackend with the right path (no confirm= gate).
# ---------------------------------------------------------------------------

def test_account_list_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_acme_account_list()
    call_path, _ = pmg.gets[-1]
    assert call_path == "/config/acme/account"


def test_account_get_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_acme_account_get(name="default")
    call_path, _ = pmg.gets[-1]
    assert call_path == "/config/acme/account/default"


def test_plugin_list_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_acme_plugin_list()
    call_path, _ = pmg.gets[-1]
    assert call_path == "/config/acme/plugins"


def test_plugin_get_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_acme_plugin_get(plugin_id="p1")
    call_path, _ = pmg.gets[-1]
    assert call_path == "/config/acme/plugins/p1"


def test_tos_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_acme_tos()
    call_path, _ = pmg.gets[-1]
    assert call_path == "/config/acme/tos"


def test_meta_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_acme_meta()
    call_path, _ = pmg.gets[-1]
    assert call_path == "/config/acme/meta"


def test_directories_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_acme_directories()
    call_path, _ = pmg.gets[-1]
    assert call_path == "/config/acme/directories"


def test_challenge_schema_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_acme_challenge_schema()
    call_path, _ = pmg.gets[-1]
    assert call_path == "/config/acme/challenge-schema"


# ---------------------------------------------------------------------------
# THE HEADLINE WELD #1 — ACME account eab-hmac-key/eab-kid: never-in-ledger on write, DEFENSIVE
# strip on read.
# ---------------------------------------------------------------------------

def test_account_create_confirm_never_writes_eab_secrets_to_ledger(tmp_path, monkeypatch):
    """weld 1: the real PMG call DOES carry both raw EAB secrets (the registration must actually
    work) — the fake captured them. weld 2: read the ledger file RAW (bytes, not parsed JSON) and
    assert NEITHER secret substring appears anywhere in the file."""
    _, pmg, _, log = _wire(tmp_path, monkeypatch)

    out = server.pmg_acme_account_create(
        contact="mailto:a@example.com", eab_hmac_key=_EAB_HMAC_KEY_SENTINEL,
        eab_kid=_EAB_KID_SENTINEL, confirm=True,
    )

    assert out["status"] == "submitted"

    # weld 1: the fake captured the underlying POST with BOTH raw secrets.
    assert pmg.posts, "pmg_acme_account_create confirm=True never reached pmg._post"
    call_path, call_data = pmg.posts[-1]
    assert call_path == "/config/acme/account"
    assert call_data["eab-hmac-key"] == _EAB_HMAC_KEY_SENTINEL
    assert call_data["eab-kid"] == _EAB_KID_SENTINEL

    # weld 2: ledger entries (parsed JSON) never carry either secret sentinel.
    entries = _entries(log)
    assert entries, "no ledger entries recorded at all"
    assert all(_EAB_HMAC_KEY_SENTINEL not in json.dumps(e) for e in entries)
    assert all(_EAB_KID_SENTINEL not in json.dumps(e) for e in entries)
    entry = _confirmed_entry(log, "pmg_acme_account_create", "submitted")
    assert "eab-hmac-key" not in entry["detail"]
    assert "eab-kid" not in entry["detail"]

    # THE HEADLINE WELD: read the ledger file RAW (bytes) — neither secret appears anywhere.
    raw = open(log, "rb").read()
    assert _EAB_HMAC_KEY_SENTINEL.encode("utf-8") not in raw
    assert _EAB_KID_SENTINEL.encode("utf-8") not in raw

    # MIRROR-IMAGE: contact IS present raw in the on-disk ledger (non-secret, deliberately visible).
    assert b"mailto:a@example.com" in raw


def test_account_create_dry_run_plan_never_carries_eab_secrets(tmp_path, monkeypatch):
    """Even confirm=False (the returned PLAN dict itself, not just the ledger) must never carry
    either raw EAB secret — the plan is returned directly to the calling agent."""
    _wire(tmp_path, monkeypatch)

    out = server.pmg_acme_account_create(
        contact="mailto:a@example.com", eab_hmac_key=_EAB_HMAC_KEY_SENTINEL,
        eab_kid=_EAB_KID_SENTINEL, confirm=False,
    )

    assert out["status"] == "plan"
    dumped = json.dumps(out)
    assert _EAB_HMAC_KEY_SENTINEL not in dumped
    assert _EAB_KID_SENTINEL not in dumped
    assert "mailto:a@example.com" in dumped  # contact IS visible — not secret


def test_account_list_strips_eab_secrets_at_read_layer_defensive(tmp_path, monkeypatch):
    """DEFENSIVE (neither read schema confirms these fields echo) — applied regardless, using the
    same mechanism as the mandatory-shape strips elsewhere in this campaign."""
    leaked_hmac = "sentinel-leaked-eab-hmac-from-account-list"
    leaked_kid = "sentinel-leaked-eab-kid-from-account-list"

    class _LeakyPmg(_Pmg):
        def _get(self, path, params=None):
            self.gets.append((path, params))
            if path == "/config/acme/account":
                return [{"name": "default", "eab-hmac-key": leaked_hmac, "eab-kid": leaked_kid}]
            return super()._get(path, params)

    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
                         audit_log_path=log)
    pmg = _LeakyPmg()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, _Api(), SimpleNamespace(), ledger))
    monkeypatch.setattr(server, "_pmg", lambda: (SimpleNamespace(node="pmg"), pmg))

    result = server.pmg_acme_account_list()
    dumped = json.dumps(result)
    assert leaked_hmac not in dumped
    assert leaked_kid not in dumped
    assert result[0]["name"] == "default"


def test_account_get_strips_eab_secrets_at_read_layer_defensive(tmp_path, monkeypatch):
    leaked_hmac = "sentinel-leaked-eab-hmac-from-account-get"
    leaked_kid = "sentinel-leaked-eab-kid-from-account-get"
    _, _, _, _ = _wire(
        tmp_path, monkeypatch,
        account_get_return={"directory": "https://example.com/directory",
                             "eab-hmac-key": leaked_hmac, "eab-kid": leaked_kid},
    )

    result = server.pmg_acme_account_get(name="default")
    dumped = json.dumps(result)
    assert leaked_hmac not in dumped
    assert leaked_kid not in dumped
    assert result["directory"] == "https://example.com/directory"


def test_account_update_capture_secrets_never_reach_ledger(tmp_path, monkeypatch):
    """Defense-in-depth: the CAPTURE read (acme_account_get already strips both EAB fields at the
    read layer, but wire the fake to return them anyway to prove the redaction-on-top-of-strip
    holds even if the read-layer strip regressed) must never leak into the ledger either, on
    BOTH confirm=False and confirm=True paths."""
    leaked_hmac = "sentinel-leaked-from-account-get-capture-hmac"
    leaked_kid = "sentinel-leaked-from-account-get-capture-kid"
    _, _, _, log = _wire(
        tmp_path, monkeypatch,
        account_get_return={"directory": "https://example.com/directory",
                             "eab-hmac-key": leaked_hmac, "eab-kid": leaked_kid},
    )

    out = server.pmg_acme_account_update(name="default", contact="mailto:new@example.com", confirm=False)
    assert out["status"] == "plan"
    assert leaked_hmac not in json.dumps(out)
    assert leaked_kid not in json.dumps(out)

    out = server.pmg_acme_account_update(name="default", contact="mailto:new@example.com", confirm=True)
    assert out["status"] == "submitted"

    raw = open(log, "rb").read()
    assert leaked_hmac.encode("utf-8") not in raw
    assert leaked_kid.encode("utf-8") not in raw


def test_account_delete_capture_secrets_never_reach_ledger(tmp_path, monkeypatch):
    """Mirrors test_account_update_capture_secrets_never_reach_ledger, exactly, for the _delete
    CAPTURE path: plan_acme_account_delete performs the identical acme_account_get CAPTURE read
    as plan_acme_account_update (pmg.py ~line 9719 vs ~9682) — same defense-in-depth applies:
    the read layer already strips both EAB fields, but the fake is wired to return them anyway to
    prove the redaction-on-top-of-strip holds even if the read-layer strip regressed. Must never
    leak into the ledger either, on BOTH confirm=False and confirm=True paths."""
    leaked_hmac = "sentinel-leaked-from-account-get-capture-hmac-delete"
    leaked_kid = "sentinel-leaked-from-account-get-capture-kid-delete"
    _, _, _, log = _wire(
        tmp_path, monkeypatch,
        account_get_return={"directory": "https://example.com/directory",
                             "eab-hmac-key": leaked_hmac, "eab-kid": leaked_kid},
    )

    out = server.pmg_acme_account_delete(name="default", confirm=False)
    assert out["status"] == "plan"
    assert leaked_hmac not in json.dumps(out)
    assert leaked_kid not in json.dumps(out)

    out = server.pmg_acme_account_delete(name="default", confirm=True)
    assert out["status"] == "submitted"

    raw = open(log, "rb").read()
    assert leaked_hmac.encode("utf-8") not in raw
    assert leaked_kid.encode("utf-8") not in raw


# ---------------------------------------------------------------------------
# THE HEADLINE WELD #2 — ACME plugin `data` (DNS-API credential blob): never-in-ledger on write,
# DEFENSIVE strip on read (a real divergence from PBS's own MANDATORY strip — PMG's list is
# schema-confirmed thin/id-only).
# ---------------------------------------------------------------------------

def test_plugin_create_confirm_never_writes_data_to_ledger(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(tmp_path, monkeypatch)

    out = server.pmg_acme_plugin_create(
        plugin_id="p1", plugin_type="dns", data=_PLUGIN_DATA_SENTINEL, confirm=True,
    )

    assert out["status"] == "ok"
    assert pmg.posts
    _, call_data = pmg.posts[-1]
    assert call_data["data"] == _PLUGIN_DATA_SENTINEL

    raw = open(log, "rb").read()
    assert _PLUGIN_DATA_SENTINEL.encode("utf-8") not in raw


def test_plugin_update_confirm_never_writes_data_to_ledger(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(tmp_path, monkeypatch)

    out = server.pmg_acme_plugin_update(plugin_id="p1", data=_PLUGIN_DATA_SENTINEL, confirm=True)

    assert out["status"] == "ok"
    assert pmg.puts
    _, call_data = pmg.puts[-1]
    assert call_data["data"] == _PLUGIN_DATA_SENTINEL

    raw = open(log, "rb").read()
    assert _PLUGIN_DATA_SENTINEL.encode("utf-8") not in raw


def test_plugin_create_dry_run_plan_never_carries_data(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)

    out = server.pmg_acme_plugin_create(
        plugin_id="p1", plugin_type="dns", data=_PLUGIN_DATA_SENTINEL, confirm=False,
    )

    assert out["status"] == "plan"
    dumped = json.dumps(out)
    assert _PLUGIN_DATA_SENTINEL not in dumped
    assert "p1" in dumped  # plugin_id IS visible — not secret


def test_plugin_list_strips_data_at_read_layer_defensive(tmp_path, monkeypatch):
    """DEFENSIVE — PMG's own list is schema-confirmed THIN/id-only (does NOT echo `data`), unlike
    PBS's rich list — stripped anyway per the mature post-9c-review discipline."""
    leaked_data = "sentinel-leaked-plugin-data-from-list"

    class _LeakyPmg(_Pmg):
        def _get(self, path, params=None):
            self.gets.append((path, params))
            if path == "/config/acme/plugins":
                return [{"plugin": "p1", "data": leaked_data}]
            return super()._get(path, params)

    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
                         audit_log_path=log)
    pmg = _LeakyPmg()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, _Api(), SimpleNamespace(), ledger))
    monkeypatch.setattr(server, "_pmg", lambda: (SimpleNamespace(node="pmg"), pmg))

    result = server.pmg_acme_plugin_list()
    dumped = json.dumps(result)
    assert leaked_data not in dumped
    assert result[0]["plugin"] == "p1"


def test_plugin_get_strips_data_at_read_layer_defensive(tmp_path, monkeypatch):
    leaked_data = "sentinel-leaked-plugin-data-from-get"
    _, _, _, _ = _wire(
        tmp_path, monkeypatch, plugin_get_return={"plugin": "p1", "data": leaked_data},
    )

    result = server.pmg_acme_plugin_get(plugin_id="p1")
    dumped = json.dumps(result)
    assert leaked_data not in dumped
    assert result["plugin"] == "p1"


def test_plugin_update_capture_data_never_reaches_ledger(tmp_path, monkeypatch):
    leaked_data = "sentinel-leaked-from-plugin-get-capture"
    _, _, _, log = _wire(
        tmp_path, monkeypatch, plugin_get_return={"plugin": "p1", "data": leaked_data},
    )

    out = server.pmg_acme_plugin_update(plugin_id="p1", disable=True, confirm=False)
    assert out["status"] == "plan"
    assert leaked_data not in json.dumps(out)

    out = server.pmg_acme_plugin_update(plugin_id="p1", disable=True, confirm=True)
    assert out["status"] == "ok"

    raw = open(log, "rb").read()
    assert leaked_data.encode("utf-8") not in raw


def test_plugin_delete_capture_data_never_reaches_ledger(tmp_path, monkeypatch):
    """Mirrors test_plugin_update_capture_data_never_reaches_ledger, exactly, for the _delete
    CAPTURE path: plan_acme_plugin_delete performs the identical acme_plugin_get CAPTURE read as
    plan_acme_plugin_update (pmg.py ~line 9840 vs ~9806) — same defense-in-depth applies. Must
    never leak into the ledger either, on BOTH confirm=False and confirm=True paths."""
    leaked_data = "sentinel-leaked-from-plugin-get-capture-delete"
    _, _, _, log = _wire(
        tmp_path, monkeypatch, plugin_get_return={"plugin": "p1", "data": leaked_data},
    )

    out = server.pmg_acme_plugin_delete(plugin_id="p1", confirm=False)
    assert out["status"] == "plan"
    assert leaked_data not in json.dumps(out)

    out = server.pmg_acme_plugin_delete(plugin_id="p1", confirm=True)
    assert out["status"] == "ok"

    raw = open(log, "rb").read()
    assert leaked_data.encode("utf-8") not in raw


# ---------------------------------------------------------------------------
# THE HEADLINE WELD #3 — custom-cert `key` (PEM private key): UNCONDITIONALLY redacted — never
# enters the plan preview or the ledger, even though the real PMG call DOES carry it.
# ---------------------------------------------------------------------------

def test_cert_custom_upload_confirm_never_writes_key_to_ledger(tmp_path, monkeypatch):
    """weld 1: the real PMG call DOES carry the raw key (the upload must actually work) — the
    fake captured it. weld 2: read the ledger file RAW (bytes) — the key never appears anywhere,
    while the PUBLIC cert body DOES."""
    _, pmg, _, log = _wire(tmp_path, monkeypatch)

    out = server.pmg_node_cert_custom_upload(
        cert_type="api", certificates=_CERT_BODY_SENTINEL, key=_CERT_KEY_SENTINEL, confirm=True,
    )

    assert out["status"] == "ok"

    # weld 1: the fake captured the underlying POST with the raw key.
    assert pmg.posts, "pmg_node_cert_custom_upload confirm=True never reached pmg._post"
    call_path, call_data = pmg.posts[-1]
    assert call_path == "/nodes/pmg/certificates/custom/api"
    assert call_data["key"] == _CERT_KEY_SENTINEL
    assert call_data["certificates"] == _CERT_BODY_SENTINEL

    # weld 2: ledger entries (parsed JSON) never carry the raw key.
    entries = _entries(log)
    assert entries, "no ledger entries recorded at all"
    assert all(_CERT_KEY_SENTINEL not in json.dumps(e) for e in entries)
    entry = _confirmed_entry(log, "pmg_node_cert_custom_upload", "ok")
    assert entry["detail"]["key"] == "[redacted]"

    # THE HEADLINE WELD: read the ledger file RAW (bytes) — the key never appears anywhere.
    raw = open(log, "rb").read()
    assert _CERT_KEY_SENTINEL.encode("utf-8") not in raw

    # MIRROR-IMAGE: the PUBLIC cert body IS present raw in the on-disk ledger (not a secret).
    assert _CERT_BODY_SENTINEL.encode("utf-8") in raw


def test_cert_custom_upload_dry_run_plan_never_carries_key(tmp_path, monkeypatch):
    """Even confirm=False (the returned PLAN dict itself) must never carry the raw key — the
    plan is returned directly to the calling agent. The key is never even a parameter to the
    plan factory (UNCONDITIONAL redaction, not a runtime scrub)."""
    _wire(tmp_path, monkeypatch)

    out = server.pmg_node_cert_custom_upload(
        cert_type="api", certificates=_CERT_BODY_SENTINEL, key=_CERT_KEY_SENTINEL, confirm=False,
    )

    assert out["status"] == "plan"
    assert out["key"] == "[redacted]"
    dumped = json.dumps(out)
    assert _CERT_KEY_SENTINEL not in dumped
    assert _CERT_BODY_SENTINEL[:20] in dumped  # cert body preview IS visible — not secret


def test_cert_custom_upload_ledger_detail_never_includes_the_raw_response(tmp_path, monkeypatch):
    """Defense-in-depth against a future schema surprise: even if PMG's own response somehow
    carried a stray `key`-shaped field, the ledger `detail` for this tool never includes `result`
    at all (only `{"key": "[redacted]", "confirmed": True}`) — so a leaked field in the RESPONSE
    still could not reach the on-disk ledger."""
    leaked_key = "sentinel-leaked-key-from-upload-response"
    _, _, _, log = _wire(
        tmp_path, monkeypatch,
        custom_upload_return={**_CUSTOM_UPLOAD_RESPONSE, "key": leaked_key},
    )

    out = server.pmg_node_cert_custom_upload(
        cert_type="api", certificates=_CERT_BODY_SENTINEL, key=_CERT_KEY_SENTINEL, confirm=True,
    )
    assert out["status"] == "ok"
    # the CALLER still sees whatever PMG actually returned (no second copy withheld from them).
    assert out["result"]["key"] == leaked_key

    entry = _confirmed_entry(log, "pmg_node_cert_custom_upload", "ok")
    assert "result" not in entry["detail"]
    raw = open(log, "rb").read()
    assert leaked_key.encode("utf-8") not in raw
