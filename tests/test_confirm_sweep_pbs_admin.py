"""Confirm=True sweep — PBS admin job views + node odds + pull/push wrapper welds
(src/proximo/tools/pbs_admin.py, Wave 5c — CLOSES the PBS plane) + the http-proxy-userinfo-
never-raw-in-ledger promise (module docstring fact #10).

Mirrors the `_wire()`/`_Pbs` idiom in tests/test_confirm_sweep_pbs_s3.py (itself mirroring
tests/test_server_plan.py:110-131): `_svc` is monkeypatched (the ONE shared audit ledger lives
behind it — `_ledger()` reads `_svc()[3]`) and `_pbs` is monkeypatched to a fake PbsBackend. This
file duplicates its own `_Pbs`/`_wire` rather than importing another confirm-sweep module's —
same self-contained convention every confirm-sweep module in this repo follows.

Each homogeneous confirm=True call proves the three welds:
  1. return shape — status is "ok" (never "plan", never "submitted") — every mutation on this
     plane declares returns:null per the live schema (module docstring facts #1/#4);
  2. the fake PbsBackend captured the underlying call (verb + path + EXACT payload, full dict
     equality — no subset matching);
  3. the ledger recorded a confirmed mutation — structural asserts only, never exact prose.

THE HEADLINE WELD: an http-proxy value carrying embedded `user:pass@` userinfo must never appear
RAW in the on-disk ledger for pbs_node_config_set — read RAW BYTES, not parsed JSON — while the
real PBS call (the fake's captured payload) DOES carry the raw value, because the mutation must
actually work (mirrors pbs_s3.py's/pbs_metrics.py's secret-never-in-ledger idiom, but for a
MASKED-not-fully-redacted field: host:port stays visible, only the userinfo portion is masked).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.backends import ProximoError
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
    behind it); pbs_admin.py's tools never touch this backend."""

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


_PROXY_SECRET_SENTINEL = "sentinel-proxy-password"  # noqa: S105 (test sentinel, not a real credential)

# ---------------------------------------------------------------------------
# Homogeneous sweep — table-driven: "confirm=True reaches the right verb/path/data on the
# PbsBackend and records a confirmed mutation". All three mutations on this plane declare
# returns:null per the live schema (module docstring facts #1/#4) — outcome is ALWAYS "ok",
# never "submitted".
# ---------------------------------------------------------------------------

_SWEEP_CASES = [
    pytest.param(
        "pbs_node_config_set",
        dict(description="updated node description"),
        "ok", "puts", "/nodes/localhost/config",
        {"description": "updated node description"},
        id="node_config_set",
    ),
    pytest.param(
        "pbs_pull",
        dict(store="local1", remote_store="remote1"),
        "ok", "posts", "/pull",
        {"store": "local1", "remote-store": "remote1"},
        id="pull",
    ),
    pytest.param(
        "pbs_push",
        dict(store="local1", remote="myremote", remote_store="remote1"),
        "ok", "posts", "/push",
        {"store": "local1", "remote": "myremote", "remote-store": "remote1"},
        id="push",
    ),
]


@pytest.mark.parametrize(
    "tool_name,kwargs,expected_status,capture,path,data_exact", _SWEEP_CASES,
)
def test_confirm_true_executes_forwards_and_records(
    tmp_path, monkeypatch, tool_name, kwargs, expected_status, capture, path, data_exact,
):
    """confirm=True executes (never 'plan'/'submitted'), the fake captured the forwarded call,
    and the ledger recorded a confirmed mutation — the three welds every confirm-sweep module
    proves."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch, get_return={})
    fn = getattr(server, tool_name)

    out = fn(confirm=True, **kwargs)

    # weld 1: return shape — always "ok" on this plane (every mutation declares returns:null)
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


# ---------------------------------------------------------------------------
# Dry-run (confirm=False) — proves the PLAN path never touches the PbsBackend's write verbs, and
# that node_config_set's plan CAPTUREs current config via a live read.
# ---------------------------------------------------------------------------

def test_node_config_set_dry_run_reads_but_never_puts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"description": "old"})
    out = server.pbs_node_config_set(description="new", confirm=False)
    assert out["status"] == "plan"
    assert out["current"] == {"description": "old"}
    assert not pbs.puts


def test_node_config_set_empty_delete_rejected_dry_run(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={})
    with pytest.raises(ProximoError):
        server.pbs_node_config_set(delete=[], confirm=False)
    assert not pbs.puts


def test_node_config_set_empty_delete_rejected_confirm(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={})
    with pytest.raises(ProximoError):
        server.pbs_node_config_set(delete=[], confirm=True)
    assert not pbs.puts


def test_pull_dry_run_never_posts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_pull(store="local1", remote_store="remote1", confirm=False)
    assert out["status"] == "plan"
    assert not pbs.posts


def test_pull_dry_run_risk_escalates_with_remove_vanished(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_pull(
        store="local1", remote_store="remote1", remove_vanished=True, confirm=False,
    )
    assert out["risk"] == "high"
    assert not pbs.posts


def test_push_dry_run_never_posts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_push(store="local1", remote="myremote", remote_store="remote1", confirm=False)
    assert out["status"] == "plan"
    assert not pbs.posts


def test_push_dry_run_risk_escalates_with_remove_vanished(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_push(
        store="local1", remote="myremote", remote_store="remote1", remove_vanished=True,
        confirm=False,
    )
    assert out["risk"] == "high"
    assert not pbs.posts


# ---------------------------------------------------------------------------
# Reads — confirm the wrapper reaches the PbsBackend with the right path/params (no confirm=
# gate).
# ---------------------------------------------------------------------------

def test_gc_jobs_list_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_admin_gc_jobs_list()
    call_path, _ = pbs.gets[-1]
    assert call_path == "/admin/gc"


def test_gc_jobs_list_read_with_store_filter_embeds_target(tmp_path, monkeypatch):
    _, pbs, _, log = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_admin_gc_jobs_list(store="ds1")
    entry = _confirmed_entry(log, "pbs_admin_gc_jobs_list", "ok")
    assert "ds1" in entry["target"]


def test_prune_jobs_list_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_admin_prune_jobs_list()
    call_path, _ = pbs.gets[-1]
    assert call_path == "/admin/prune"


def test_sync_jobs_list_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_admin_sync_jobs_list(sync_direction="push")
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/admin/sync"
    assert call_params == {"sync-direction": "push"}


def test_verify_jobs_list_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_admin_verify_jobs_list()
    call_path, _ = pbs.gets[-1]
    assert call_path == "/admin/verify"


def test_traffic_control_status_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_admin_traffic_control_status()
    call_path, _ = pbs.gets[-1]
    assert call_path == "/admin/traffic-control"


def test_node_config_get_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={})
    server.pbs_node_config_get()
    call_path, _ = pbs.gets[-1]
    assert call_path == "/nodes/localhost/config"


def test_node_identity_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"pbs-instance-id": "abc"})
    server.pbs_node_identity()
    call_path, _ = pbs.gets[-1]
    assert call_path == "/nodes/localhost/identity"


def test_node_rrd_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=None)
    server.pbs_node_rrd(cf="AVERAGE", timeframe="hour")
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/nodes/localhost/rrd"
    assert call_params == {"cf": "AVERAGE", "timeframe": "hour"}


def test_node_report_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return="report text")
    out = server.pbs_node_report()
    assert out == "report text"
    call_path, _ = pbs.gets[-1]
    assert call_path == "/nodes/localhost/report"


def test_version_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"version": "4.2"})
    server.pbs_version()
    call_path, _ = pbs.gets[-1]
    assert call_path == "/version"


# ---------------------------------------------------------------------------
# THE HEADLINE WELD — http-proxy embedded userinfo credential never reaches the ledger raw
# (module docstring fact #10). Sentinel values are low-entropy/all-lowercase/hyphenated per this
# repo's fixture-sentinel discipline.
# ---------------------------------------------------------------------------

def test_node_config_set_confirm_never_writes_proxy_password_to_ledger(tmp_path, monkeypatch):
    """weld 1: the operator's real PBS call DOES carry the raw http-proxy value including
    userinfo (the mutation must actually work) — the fake captured it. weld 2: read the ledger
    file RAW (bytes, not parsed JSON) and assert the password substring appears NOWHERE — not in
    the 'planned' entry, not in the 'confirmed' entry, not anywhere in the file. host:port DOES
    remain visible (masking, not full redaction — module docstring fact #10's decision)."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch, get_return={})

    proxy_value = f"http://admin:{_PROXY_SECRET_SENTINEL}@proxy.example.com:3128"
    out = server.pbs_node_config_set(http_proxy=proxy_value, confirm=True)

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    # weld 1: the fake captured the underlying PUT with the RAW http-proxy value.
    assert pbs.puts, "pbs_node_config_set confirm=True never reached pbs._put"
    call_path, call_data = pbs.puts[-1]
    assert call_path == "/nodes/localhost/config"
    assert call_data["http-proxy"] == proxy_value

    # weld 2: ledger entries (parsed JSON) never carry the proxy password sentinel.
    entries = _entries(log)
    assert entries, "no ledger entries recorded at all"
    assert all(_PROXY_SECRET_SENTINEL not in json.dumps(e) for e in entries)

    # THE HEADLINE WELD: read the ledger file RAW (bytes) — the password must appear NOWHERE.
    raw = open(log, "rb").read()
    assert _PROXY_SECRET_SENTINEL.encode("utf-8") not in raw

    # host:port DOES remain visible in the plan entry — masking, not full redaction.
    assert b"proxy.example.com:3128" in raw


def test_node_config_set_dry_run_plan_never_carries_proxy_password(tmp_path, monkeypatch):
    """Even confirm=False (the returned PLAN dict itself, not just the ledger) must never carry
    the raw proxy password — the plan is returned directly to the calling agent."""
    _, _, _, _ = _wire(tmp_path, monkeypatch, get_return={})

    proxy_value = f"http://admin:{_PROXY_SECRET_SENTINEL}@proxy.example.com:3128"
    out = server.pbs_node_config_set(http_proxy=proxy_value, confirm=False)

    assert out["status"] == "plan"
    dumped = json.dumps(out)
    assert _PROXY_SECRET_SENTINEL not in dumped
    assert "proxy.example.com:3128" in dumped  # host:port IS visible — deliberately not stripped


def test_node_config_set_at_bearing_proxy_password_never_reaches_ledger(tmp_path, monkeypatch):
    """Wave 5c review Finding 3 regression proof, end-to-end: a password containing a literal @
    ('user:p@ss-tail@host') previously leaked its TAIL past the first @ into both the planned and
    confirmed ledger entries. RAW ledger bytes must carry NO fragment of the userinfo — neither
    the full sentinel nor the tail after its embedded @ — while host:port stays visible and the
    real PBS call still gets the RAW value."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch, get_return={})

    # The @ splits the sentinel: the old first-@ regex would leak everything after "p@".
    proxy_value = "http://admin:p@ss-tail-leak-sentinel@proxy.example.com:3128"
    out = server.pbs_node_config_set(http_proxy=proxy_value, confirm=True)

    assert out["status"] == "ok"
    # the real PBS call carries the RAW value — the mutation must actually work
    _, call_data = pbs.puts[-1]
    assert call_data["http-proxy"] == proxy_value

    raw = open(log, "rb").read()
    assert b"ss-tail-leak-sentinel" not in raw   # the tail the old regex leaked
    assert b"admin:p" not in raw                 # the head of the userinfo
    assert b"proxy.example.com:3128" in raw      # host:port stays visible (masking, not strip)


def test_node_config_set_at_bearing_proxy_password_never_in_dry_run_plan(tmp_path, monkeypatch):
    _, _, _, _ = _wire(tmp_path, monkeypatch, get_return={})
    out = server.pbs_node_config_set(
        http_proxy="http://admin:p@ss-tail-leak-sentinel@proxy.example.com:3128", confirm=False,
    )
    assert out["status"] == "plan"
    dumped = json.dumps(out)
    assert "ss-tail-leak-sentinel" not in dumped
    assert "admin:p" not in dumped


def test_node_config_set_capture_proxy_password_never_reaches_ledger(tmp_path, monkeypatch):
    """Defense-in-depth: the CAPTURE read (the current node config PBS returns) must never leak
    an existing proxy password into the ledger either, on BOTH confirm=False and confirm=True
    paths."""
    leaked = f"http://admin:{_PROXY_SECRET_SENTINEL}@old-proxy.example.com:3128"
    _, _, _, log = _wire(tmp_path, monkeypatch, get_return={"http-proxy": leaked})

    out = server.pbs_node_config_get()
    assert _PROXY_SECRET_SENTINEL not in json.dumps(out)

    out = server.pbs_node_config_set(description="new", confirm=False)
    assert out["status"] == "plan"
    assert _PROXY_SECRET_SENTINEL not in json.dumps(out)

    out = server.pbs_node_config_set(description="new", confirm=True)
    assert out["status"] == "ok"

    raw = open(log, "rb").read()
    assert _PROXY_SECRET_SENTINEL.encode("utf-8") not in raw
