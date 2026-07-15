"""Confirm=True sweep — PBS ACME wrapper welds (src/proximo/tools/pbs_acme.py, Wave 3b) + the
secret-never-in-ledger promise for `eab_hmac_key` (account) and `data` (plugin).

Mirrors the `_wire()`/`_Pbs` idiom in tests/test_confirm_sweep_pbs_notifications.py (itself
mirroring tests/test_server_plan.py:110-131): `_svc` is monkeypatched (the ONE shared audit
ledger lives behind it — `_ledger()` reads `_svc()[3]`) and `_pbs` is monkeypatched to a fake
PbsBackend. This file duplicates its own `_Pbs`/`_wire` rather than importing another
confirm-sweep module's — same self-contained convention every confirm-sweep module in this repo
follows.

Each homogeneous confirm=True call proves the three welds:
  1. return shape — status is "ok" (never "plan") — every mutation on this plane is SYNCHRONOUS
     per the live schema (module docstring fact #9), unlike a PVE guest/storage mutation OR
     PVE's own ACME cert order/renew (which return a task UPID);
  2. the fake PbsBackend captured the underlying call (verb + path + EXACT payload, full dict
     equality — no subset matching);
  3. the ledger recorded a confirmed mutation — structural asserts only, never exact prose.

THE HEADLINE WELD (mirrors tests/test_confirm_sweep_pbs_notifications.py's own headline weld):
account `eab_hmac_key` and plugin `data` values must never appear raw in the on-disk ledger —
read RAW BYTES, not parsed JSON — for BOTH the mutation-kwarg path (change) and the CAPTURE-read
path (current, on update/delete's live GET) — while the real PBS call (the fake's captured
payload) DOES carry the raw value, because the mutation must actually work.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig


class _Pbs:
    """Path-aware fake PbsBackend: records every _get/_post/_put/_delete call."""

    def __init__(self, get_return=None):
        self._get_return = get_return
        self.gets: list[tuple[str, dict | None]] = []
        self.posts: list[tuple[str, dict | None]] = []
        self.puts: list[tuple[str, dict | None]] = []
        self.deletes: list[tuple[str, dict | None]] = []

    def _get(self, path, params=None):
        self.gets.append((path, params))
        return self._get_return

    def _post(self, path, data=None):
        self.posts.append((path, data))
        return None

    def _put(self, path, data=None):
        self.puts.append((path, data))
        return None

    def _delete(self, path, params=None):
        self.deletes.append((path, params))
        return None


class _Api:
    """Minimal PVE API stub — only needed so server._svc() resolves (the ONE shared ledger lives
    behind it); pbs_acme.py's tools never touch this backend."""

    def __init__(self):
        self.config = SimpleNamespace(node="pve")


def _wire(tmp_path, monkeypatch, get_return=None):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log,
    )
    api = _Api()
    pbs = _Pbs(get_return=get_return)
    exec_ = SimpleNamespace()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, exec_, ledger))
    monkeypatch.setattr(server, "_pbs", lambda: (SimpleNamespace(), pbs))
    return cfg, pbs, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _confirmed_entry(log: str, action: str, outcome: str) -> dict:
    entries = [e for e in _entries(log) if e["action"] == action and e["outcome"] == outcome]
    assert len(entries) == 1, f"expected exactly one {action!r}/{outcome!r} ledger entry, got {entries}"
    return entries[0]


# ---------------------------------------------------------------------------
# Homogeneous sweep — table-driven: "confirm=True reaches the right verb/path/data on the
# PbsBackend and records a confirmed mutation". Every mutation on this plane returns null
# (synchronous) per the live schema — outcome is ALWAYS "ok", never "submitted" (unlike PVE's
# ACME cert order/renew, which DO return a task UPID and record "submitted").
# ---------------------------------------------------------------------------

_SWEEP_CASES = [
    pytest.param(
        "pbs_acme_account_create",
        dict(contact="mailto:test@example.com", name="acct1", directory="https://d",
             tos_url="https://tos"),
        "ok", "posts", "/config/acme/account",
        {"contact": "mailto:test@example.com", "name": "acct1", "directory": "https://d",
         "tos_url": "https://tos"},
        id="account_create",
    ),
    pytest.param(
        "pbs_acme_account_update",
        dict(name="acct1", contact="mailto:new@example.com"),
        "ok", "puts", "/config/acme/account/acct1",
        {"contact": "mailto:new@example.com"},
        id="account_update",
    ),
    pytest.param(
        "pbs_acme_account_delete",
        dict(name="acct1", force=True),
        "ok", "deletes", "/config/acme/account/acct1",
        {"force": 1},
        id="account_delete",
    ),
    pytest.param(
        "pbs_acme_plugin_create",
        dict(plugin_id="plug1", plugin_type="dns", dns_api="cf", data="LIVEDATA", disable=True,
             validation_delay=60),
        "ok", "posts", "/config/acme/plugins",
        {"id": "plug1", "type": "dns", "api": "cf", "data": "LIVEDATA", "disable": True,
         "validation-delay": 60},
        id="plugin_create",
    ),
    pytest.param(
        "pbs_acme_plugin_update",
        dict(plugin_id="plug1", dns_api="route53", data="NEWDATA", disable=False,
             validation_delay=10, digest="d" * 64, delete=["disable"]),
        "ok", "puts", "/config/acme/plugins/plug1",
        {"api": "route53", "data": "NEWDATA", "disable": False, "validation-delay": 10,
         "digest": "d" * 64, "delete": ["disable"]},
        id="plugin_update",
    ),
    pytest.param(
        "pbs_acme_plugin_delete",
        dict(plugin_id="plug1"),
        "ok", "deletes", "/config/acme/plugins/plug1",
        None,
        id="plugin_delete",
    ),
    pytest.param(
        "pbs_acme_cert_order",
        dict(node="pbs1", force=True),
        "ok", "posts", "/nodes/pbs1/certificates/acme/certificate",
        {"force": 1},
        id="cert_order",
    ),
    pytest.param(
        "pbs_acme_cert_renew",
        dict(node="pbs1", force=True),
        "ok", "puts", "/nodes/pbs1/certificates/acme/certificate",
        {"force": 1},
        id="cert_renew",
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
    _, pbs, _, log = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)

    out = fn(confirm=True, **kwargs)

    # weld 1: return shape — always "ok" on this plane (every mutation returns null, synchronous)
    assert out["status"] == expected_status
    assert out["status"] != "plan"
    assert out["status"] != "submitted"

    # weld 2: the fake captured the underlying call at the expected verb + path, with the EXACT
    # forwarded payload (full dict equality — an accidental extra field now fails).
    calls = getattr(pbs, capture)
    assert calls, f"{tool_name} confirm=True never reached pbs.{capture}"
    call_path, call_data = calls[-1]
    assert call_path == path
    assert call_data == data_exact

    # weld 3: ledger structural asserts — never exact prose
    entry = _confirmed_entry(log, tool_name, expected_status)
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


def test_account_create_no_name_targets_collection(tmp_path, monkeypatch):
    """PBS lets the account name default server-side (module docstring fact #6) — the plan/ledger
    target must fall back to the collection path, not fabricate a name."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch)

    out = server.pbs_acme_account_create(contact="mailto:test@example.com", confirm=True)

    assert out["status"] == "ok"
    _, data = pbs.posts[-1]
    assert data == {"contact": "mailto:test@example.com"}
    entry = _confirmed_entry(log, "pbs_acme_account_create", "ok")
    assert entry["target"] == "pbs/config/acme/account"


def test_account_delete_no_force_sends_no_params(tmp_path, monkeypatch):
    """force=False (the default) must NOT send force=0/false — mirrors this codebase's
    established truthy-only-send convention for optional flags."""
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)

    out = server.pbs_acme_account_delete(name="acct1", confirm=True)

    assert out["status"] == "ok"
    _, params = pbs.deletes[-1]
    assert params is None


# ---------------------------------------------------------------------------
# Reads — confirm the wrapper reaches the PbsBackend with the right path/params (no confirm= gate).
# ---------------------------------------------------------------------------

def test_account_list_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_acme_account_list()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/config/acme/account"
    assert call_params is None


def test_account_get_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"directory": "https://d"})
    server.pbs_acme_account_get(name="acct1")
    call_path, _ = pbs.gets[-1]
    assert call_path == "/config/acme/account/acct1"


def test_directories_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_acme_directories()
    call_path, _ = pbs.gets[-1]
    assert call_path == "/config/acme/directories"


def test_tos_read_no_directory(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return="https://tos")
    server.pbs_acme_tos()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/config/acme/tos"
    assert call_params is None


def test_tos_read_with_directory(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return="https://tos")
    server.pbs_acme_tos(directory="https://acme-v02.example.com/directory")
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/config/acme/tos"
    assert call_params == {"directory": "https://acme-v02.example.com/directory"}


def test_challenge_schema_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_acme_challenge_schema()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/config/acme/challenge-schema"
    assert call_params is None


def test_plugins_list_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_acme_plugins_list()
    call_path, _ = pbs.gets[-1]
    assert call_path == "/config/acme/plugins"


def test_plugin_get_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"plugin": "plug1"})
    server.pbs_acme_plugin_get(plugin_id="plug1")
    call_path, _ = pbs.gets[-1]
    assert call_path == "/config/acme/plugins/plug1"


# ---------------------------------------------------------------------------
# THE HEADLINE WELD — secret-never-in-ledger, for account `eab_hmac_key` (mutation-kwarg path)
# and plugin `data` (both mutation-kwarg AND CAPTURE-read path). Sentinel values are low-entropy/
# all-lowercase/hyphenated per this repo's fixture-sentinel discipline (CLAUDE.md: "Test fixtures
# must use low-entropy sentinel values" — a mixed-case sentinel already failed the public
# gitleaks CI scan on v0.13.0).
# ---------------------------------------------------------------------------

_EAB_SENTINEL = "sentinel-eab-hmac-key-value"
_PLUGIN_DATA_SENTINEL = "sentinel-plugin-data-value"


def test_account_create_confirm_never_writes_eab_hmac_key_to_ledger(tmp_path, monkeypatch):
    """weld 1: the operator's real PBS call DOES carry the raw eab_hmac_key (the mutation must
    actually work) — the fake captured it. weld 2: read the ledger file RAW (bytes, not parsed
    JSON) and assert the secret substring appears NOWHERE — not in the 'planned' entry, not in
    the 'confirmed' entry, not anywhere in the file."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch)

    out = server.pbs_acme_account_create(
        contact="mailto:test@example.com", eab_hmac_key=_EAB_SENTINEL, confirm=True,
    )

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    assert pbs.posts, "account_create confirm=True never reached pbs._post"
    call_path, call_data = pbs.posts[-1]
    assert call_path == "/config/acme/account"
    assert _EAB_SENTINEL in json.dumps(call_data)

    entries = _entries(log)
    assert entries, "no ledger entries recorded at all"
    assert all(_EAB_SENTINEL not in json.dumps(e) for e in entries)

    raw = open(log, "rb").read()
    assert _EAB_SENTINEL.encode("utf-8") not in raw


def test_account_create_dry_run_plan_never_carries_eab_hmac_key(tmp_path, monkeypatch):
    """Even confirm=False (the returned PLAN dict itself, not just the ledger) must never carry
    the raw eab_hmac_key — the plan is returned directly to the calling agent."""
    _wire(tmp_path, monkeypatch)

    out = server.pbs_acme_account_create(
        contact="mailto:test@example.com", eab_hmac_key=_EAB_SENTINEL, confirm=False,
    )

    assert out["status"] == "plan"
    assert _EAB_SENTINEL not in json.dumps(out)


@pytest.mark.parametrize("tool_name,extra", [
    ("pbs_acme_plugin_create", dict(plugin_id="plug1", plugin_type="dns")),
    ("pbs_acme_plugin_update", dict(plugin_id="plug1")),
])
def test_plugin_mutation_confirm_never_writes_data_to_ledger(tmp_path, monkeypatch, tool_name, extra):
    """Same headline weld as account create, for both plugin mutation paths that accept a raw
    `data` kwarg."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)

    out = fn(data=_PLUGIN_DATA_SENTINEL, confirm=True, **extra)

    assert out["status"] == "ok"

    calls = pbs.posts if tool_name == "pbs_acme_plugin_create" else pbs.puts
    assert calls, f"{tool_name} confirm=True never reached the PbsBackend"
    call_path, call_data = calls[-1]
    assert _PLUGIN_DATA_SENTINEL in json.dumps(call_data)

    entries = _entries(log)
    assert entries
    assert all(_PLUGIN_DATA_SENTINEL not in json.dumps(e) for e in entries)

    raw = open(log, "rb").read()
    assert _PLUGIN_DATA_SENTINEL.encode("utf-8") not in raw


def test_plugin_create_dry_run_plan_never_carries_data(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)

    out = server.pbs_acme_plugin_create(
        plugin_id="plug1", plugin_type="dns", data=_PLUGIN_DATA_SENTINEL, confirm=False,
    )

    assert out["status"] == "plan"
    assert _PLUGIN_DATA_SENTINEL not in json.dumps(out)


# ---------------------------------------------------------------------------
# CAPTURE-read redaction proof — plugin update/delete's plan factories read the LIVE plugin
# config (which DOES carry `data` on a real PBS, module docstring fact #4) before building the
# plan. Wire the fake GET to return a data-BEARING config and prove Plan.current is redacted,
# all the way through to the on-disk ledger.
# ---------------------------------------------------------------------------

def test_plugin_update_confirm_never_writes_captured_data_to_ledger(tmp_path, monkeypatch):
    _, pbs, _, log = _wire(
        tmp_path, monkeypatch,
        get_return={"plugin": "plug1", "type": "dns", "data": _PLUGIN_DATA_SENTINEL},
    )

    out = server.pbs_acme_plugin_update(plugin_id="plug1", disable=True, confirm=True)

    assert out["status"] == "ok"
    entries = _entries(log)
    assert entries
    assert all(_PLUGIN_DATA_SENTINEL not in json.dumps(e) for e in entries)

    raw = open(log, "rb").read()
    assert _PLUGIN_DATA_SENTINEL.encode("utf-8") not in raw


def test_plugin_delete_confirm_never_writes_captured_data_to_ledger(tmp_path, monkeypatch):
    _, pbs, _, log = _wire(
        tmp_path, monkeypatch,
        get_return={"plugin": "plug1", "type": "dns", "data": _PLUGIN_DATA_SENTINEL},
    )

    out = server.pbs_acme_plugin_delete(plugin_id="plug1", confirm=True)

    assert out["status"] == "ok"
    entries = _entries(log)
    assert entries
    assert all(_PLUGIN_DATA_SENTINEL not in json.dumps(e) for e in entries)

    raw = open(log, "rb").read()
    assert _PLUGIN_DATA_SENTINEL.encode("utf-8") not in raw


def test_plugin_delete_dry_run_plan_never_carries_captured_data(tmp_path, monkeypatch):
    _wire(
        tmp_path, monkeypatch,
        get_return={"plugin": "plug1", "type": "dns", "data": _PLUGIN_DATA_SENTINEL},
    )

    out = server.pbs_acme_plugin_delete(plugin_id="plug1", confirm=False)

    assert out["status"] == "plan"
    assert _PLUGIN_DATA_SENTINEL not in json.dumps(out)


def test_account_update_confirm_never_writes_captured_eab_hmac_key_to_ledger(tmp_path, monkeypatch):
    """Defensive CAPTURE redaction, proven the same way — a live PBS never actually returns
    eab_hmac_key on account GET (module docstring fact #4), but the fake proves the mechanism
    works if it ever did."""
    _, pbs, _, log = _wire(
        tmp_path, monkeypatch,
        get_return={"directory": "https://d", "eab_hmac_key": _EAB_SENTINEL},
    )

    out = server.pbs_acme_account_update(name="acct1", contact="mailto:new@example.com", confirm=True)

    assert out["status"] == "ok"
    entries = _entries(log)
    assert entries
    assert all(_EAB_SENTINEL not in json.dumps(e) for e in entries)

    raw = open(log, "rb").read()
    assert _EAB_SENTINEL.encode("utf-8") not in raw


def test_account_delete_confirm_never_writes_captured_eab_hmac_key_to_ledger(tmp_path, monkeypatch):
    _, pbs, _, log = _wire(
        tmp_path, monkeypatch,
        get_return={"directory": "https://d", "eab_hmac_key": _EAB_SENTINEL},
    )

    out = server.pbs_acme_account_delete(name="acct1", confirm=True)

    assert out["status"] == "ok"
    entries = _entries(log)
    assert entries
    assert all(_EAB_SENTINEL not in json.dumps(e) for e in entries)

    raw = open(log, "rb").read()
    assert _EAB_SENTINEL.encode("utf-8") not in raw
