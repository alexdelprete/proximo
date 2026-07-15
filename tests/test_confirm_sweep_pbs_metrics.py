"""Confirm=True sweep — PBS metrics servers wrapper welds (src/proximo/tools/pbs_metrics.py,
Wave 5b) + the secret-never-in-ledger promise for `token` (influxdb-http only — influxdb-udp
carries no secret field at all, module docstring fact #2).

Mirrors the `_wire()`/`_Pbs` idiom in tests/test_confirm_sweep_pbs_s3.py (itself mirroring
tests/test_server_plan.py:110-131): `_svc` is monkeypatched (the ONE shared audit ledger lives
behind it — `_ledger()` reads `_svc()[3]`) and `_pbs` is monkeypatched to a fake PbsBackend. This
file duplicates its own `_Pbs`/`_wire` rather than importing another confirm-sweep module's —
same self-contained convention every confirm-sweep module in this repo follows.

Each homogeneous confirm=True call proves the three welds:
  1. return shape — status is "ok" (never "plan") — every mutation on this plane is SYNCHRONOUS
     per the live schema (module docstring facts #6 — all returns: null);
  2. the fake PbsBackend captured the underlying call (verb + path + EXACT payload, full dict
     equality — no subset matching);
  3. the ledger recorded a confirmed mutation — structural asserts only, never exact prose.

THE HEADLINE WELD: `token` (influxdb-http create/update) must never appear raw in the on-disk
ledger — read RAW BYTES, not parsed JSON — while the real PBS call (the fake's captured payload)
DOES carry the raw value, because the mutation must actually work.
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
    behind it); pbs_metrics.py's tools never touch this backend."""

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


_TOKEN_SENTINEL = "sentinel-influx-token-value"  # noqa: S105 (test sentinel, not a real credential)

# ---------------------------------------------------------------------------
# Homogeneous sweep — table-driven: "confirm=True reaches the right verb/path/data on the
# PbsBackend and records a confirmed mutation". Every mutation on this plane returns null
# (synchronous) — outcome is ALWAYS "ok" (module docstring fact #6), never "submitted".
# ---------------------------------------------------------------------------

_SWEEP_CASES = [
    pytest.param(
        "pbs_metrics_influxdb_http_create",
        dict(name="met1", url="https://influx.example.com:8086", token=_TOKEN_SENTINEL,
             bucket="mybucket"),
        "ok", "posts", "/config/metrics/influxdb-http",
        {"name": "met1", "url": "https://influx.example.com:8086", "token": _TOKEN_SENTINEL,
         "bucket": "mybucket"},
        id="influxdb_http_create",
    ),
    pytest.param(
        "pbs_metrics_influxdb_http_update",
        dict(name="met1", bucket="newbucket"),
        "ok", "puts", "/config/metrics/influxdb-http/met1",
        {"bucket": "newbucket"},
        id="influxdb_http_update",
    ),
    pytest.param(
        "pbs_metrics_influxdb_http_delete",
        dict(name="met1"),
        "ok", "deletes", "/config/metrics/influxdb-http/met1",
        {},
        id="influxdb_http_delete",
    ),
    pytest.param(
        "pbs_metrics_influxdb_udp_create",
        dict(name="udp1", host="192.0.2.10:8089"),
        "ok", "posts", "/config/metrics/influxdb-udp",
        {"name": "udp1", "host": "192.0.2.10:8089"},
        id="influxdb_udp_create",
    ),
    pytest.param(
        "pbs_metrics_influxdb_udp_update",
        dict(name="udp1", mtu=9000),
        "ok", "puts", "/config/metrics/influxdb-udp/udp1",
        {"mtu": 9000},
        id="influxdb_udp_update",
    ),
    pytest.param(
        "pbs_metrics_influxdb_udp_delete",
        dict(name="udp1"),
        "ok", "deletes", "/config/metrics/influxdb-udp/udp1",
        {},
        id="influxdb_udp_delete",
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
    _, pbs, _, log = _wire(tmp_path, monkeypatch, get_return={"name": "met1"})
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


# ---------------------------------------------------------------------------
# Dry-run (confirm=False) — proves the PLAN path never touches the PbsBackend's write verbs, and
# that update/delete plans CAPTURE current config via a live read.
# ---------------------------------------------------------------------------

def test_influxdb_http_create_dry_run_never_posts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_metrics_influxdb_http_create(
        name="met1", url="https://influx.example.com:8086", token=_TOKEN_SENTINEL, confirm=False,
    )
    assert out["status"] == "plan"
    assert not pbs.posts


def test_influxdb_http_update_dry_run_reads_but_never_puts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "met1", "bucket": "old"})
    out = server.pbs_metrics_influxdb_http_update(name="met1", bucket="new", confirm=False)
    assert out["status"] == "plan"
    assert out["current"] == {"name": "met1", "bucket": "old"}
    assert not pbs.puts


def test_influxdb_http_delete_dry_run_reads_but_never_deletes(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "met1"})
    out = server.pbs_metrics_influxdb_http_delete(name="met1", confirm=False)
    assert out["status"] == "plan"
    assert out["current"] == {"name": "met1"}
    assert not pbs.deletes


def test_influxdb_udp_create_dry_run_never_posts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_metrics_influxdb_udp_create(name="udp1", host="192.0.2.10:8089", confirm=False)
    assert out["status"] == "plan"
    assert not pbs.posts


def test_influxdb_udp_update_dry_run_reads_but_never_puts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "udp1", "mtu": 1500})
    out = server.pbs_metrics_influxdb_udp_update(name="udp1", mtu=9000, confirm=False)
    assert out["status"] == "plan"
    assert out["current"] == {"name": "udp1", "mtu": 1500}
    assert not pbs.puts


def test_influxdb_udp_delete_dry_run_reads_but_never_deletes(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "udp1"})
    out = server.pbs_metrics_influxdb_udp_delete(name="udp1", confirm=False)
    assert out["status"] == "plan"
    assert out["current"] == {"name": "udp1"}
    assert not pbs.deletes


def test_influxdb_http_update_empty_delete_rejected_dry_run(tmp_path, monkeypatch):
    # Wave 5b review finding 1: delete=[] is REJECTED (ProximoError), not disclosed — httpx
    # drops an empty-list form value entirely, so confirm=True would never actually send it.
    # _plan() runs before the confirm check, so this raises on the dry-run path too.
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "met1"})
    with pytest.raises(ProximoError):
        server.pbs_metrics_influxdb_http_update(name="met1", delete=[], confirm=False)
    assert not pbs.puts


def test_influxdb_http_update_empty_delete_rejected_confirm(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "met1"})
    with pytest.raises(ProximoError):
        server.pbs_metrics_influxdb_http_update(name="met1", delete=[], confirm=True)
    assert not pbs.puts


def test_influxdb_udp_update_empty_delete_rejected_confirm(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "udp1"})
    with pytest.raises(ProximoError):
        server.pbs_metrics_influxdb_udp_update(name="udp1", delete=[], confirm=True)
    assert not pbs.puts


# ---------------------------------------------------------------------------
# Reads — confirm the wrapper reaches the PbsBackend with the right path/params (no confirm=
# gate).
# ---------------------------------------------------------------------------

def test_metrics_servers_list_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_metrics_servers_list()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/admin/metrics"
    assert call_params is None


def test_metrics_status_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={})
    server.pbs_metrics_status()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/status/metrics"
    assert call_params == {"history": False}


def test_metrics_status_history_and_start_time_forwarded(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={})
    server.pbs_metrics_status(history=True, start_time=1700000000)
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/status/metrics"
    assert call_params == {"history": True, "start-time": 1700000000}


def test_influxdb_http_list_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_metrics_influxdb_http_list()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/config/metrics/influxdb-http"
    assert call_params is None


def test_influxdb_http_get_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "met1"})
    server.pbs_metrics_influxdb_http_get(name="met1")
    call_path, _ = pbs.gets[-1]
    assert call_path == "/config/metrics/influxdb-http/met1"


def test_influxdb_udp_list_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_metrics_influxdb_udp_list()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/config/metrics/influxdb-udp"
    assert call_params is None


def test_influxdb_udp_get_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "udp1"})
    server.pbs_metrics_influxdb_udp_get(name="udp1")
    call_path, _ = pbs.gets[-1]
    assert call_path == "/config/metrics/influxdb-udp/udp1"


# ---------------------------------------------------------------------------
# THE HEADLINE WELD — secret-never-in-ledger for `token`, and the defensive read-layer strip
# proof (module docstring fact #1 — a REQUIRED strip, not merely defensive, since the live schema
# DOES return token unlike pbs_s3's documented-secret-free reads). Sentinel values are
# low-entropy/all-lowercase/hyphenated per this repo's fixture-sentinel discipline (CLAUDE.md: a
# mixed-case sentinel already failed the public gitleaks CI scan on v0.13.0).
# ---------------------------------------------------------------------------

def test_influxdb_http_create_confirm_never_writes_token_to_ledger(tmp_path, monkeypatch):
    """weld 1: the operator's real PBS call DOES carry the raw token (the mutation must actually
    work) — the fake captured it. weld 2: read the ledger file RAW (bytes, not parsed JSON) and
    assert the secret substring appears NOWHERE — not in the 'planned' entry, not in the
    'confirmed' entry, not anywhere in the file."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch)

    out = server.pbs_metrics_influxdb_http_create(
        name="met1", url="https://influx.example.com:8086", token=_TOKEN_SENTINEL, confirm=True,
    )

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    # weld 1: the fake captured the underlying POST with the RAW token.
    assert pbs.posts, "pbs_metrics_influxdb_http_create confirm=True never reached pbs._post"
    call_path, call_data = pbs.posts[-1]
    assert call_path == "/config/metrics/influxdb-http"
    assert call_data["token"] == _TOKEN_SENTINEL

    # weld 2: ledger entries (parsed JSON) never carry the token sentinel.
    entries = _entries(log)
    assert entries, "no ledger entries recorded at all"
    assert all(_TOKEN_SENTINEL not in json.dumps(e) for e in entries)
    entry = _confirmed_entry(log, "pbs_metrics_influxdb_http_create", "ok")
    assert "token" not in entry["detail"]

    # THE HEADLINE WELD: read the ledger file RAW (bytes) — the secret must appear NOWHERE.
    raw = open(log, "rb").read()
    assert _TOKEN_SENTINEL.encode("utf-8") not in raw

    # MIRROR-IMAGE: url IS present raw in the on-disk ledger (non-secret, deliberately visible).
    assert b"https://influx.example.com:8086" in raw


def test_influxdb_http_update_confirm_never_writes_token_to_ledger(tmp_path, monkeypatch):
    _, pbs, _, log = _wire(tmp_path, monkeypatch, get_return={"name": "met1"})

    out = server.pbs_metrics_influxdb_http_update(name="met1", token=_TOKEN_SENTINEL, confirm=True)

    assert out["status"] == "ok"
    assert pbs.puts
    _, call_data = pbs.puts[-1]
    assert call_data["token"] == _TOKEN_SENTINEL

    raw = open(log, "rb").read()
    assert _TOKEN_SENTINEL.encode("utf-8") not in raw


def test_influxdb_http_update_capture_secret_never_reaches_ledger(tmp_path, monkeypatch):
    """Defense-in-depth: the CAPTURE read (schema says token DOES normally appear here per module
    docstring fact #1 — the read-layer strip in influxdb_http_get already removes it, but wire the
    fake to return one anyway to prove the redaction-on-top-of-strip holds even if the read-layer
    strip regressed) must never leak into the ledger either, on BOTH confirm=False and confirm=True
    paths."""
    leaked = "sentinel-leaked-from-a-get-that-should-have-been-stripped"
    _, _, _, log = _wire(tmp_path, monkeypatch, get_return={"name": "met1", "token": leaked})

    out = server.pbs_metrics_influxdb_http_update(name="met1", bucket="new", confirm=False)
    assert out["status"] == "plan"
    assert leaked not in json.dumps(out)

    out = server.pbs_metrics_influxdb_http_update(name="met1", bucket="new", confirm=True)
    assert out["status"] == "ok"

    raw = open(log, "rb").read()
    assert leaked.encode("utf-8") not in raw


def test_influxdb_http_delete_capture_secret_never_reaches_ledger(tmp_path, monkeypatch):
    leaked = "sentinel-leaked-from-delete-capture-read"
    _, _, _, log = _wire(tmp_path, monkeypatch, get_return={"name": "met1", "token": leaked})

    out = server.pbs_metrics_influxdb_http_delete(name="met1", confirm=True)

    assert out["status"] == "ok"
    raw = open(log, "rb").read()
    assert leaked.encode("utf-8") not in raw


def test_influxdb_http_create_dry_run_plan_never_carries_token(tmp_path, monkeypatch):
    """Even confirm=False (the returned PLAN dict itself, not just the ledger) must never carry
    the raw token — the plan is returned directly to the calling agent."""
    _, _, _, _ = _wire(tmp_path, monkeypatch)

    out = server.pbs_metrics_influxdb_http_create(
        name="met1", url="https://influx.example.com:8086", token=_TOKEN_SENTINEL, confirm=False,
    )

    assert out["status"] == "plan"
    dumped = json.dumps(out)
    assert _TOKEN_SENTINEL not in dumped
    assert "https://influx.example.com:8086" in dumped  # url IS visible — not secret


def test_influxdb_http_update_dry_run_plan_never_carries_token(tmp_path, monkeypatch):
    _, _, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "met1"})

    out = server.pbs_metrics_influxdb_http_update(name="met1", token=_TOKEN_SENTINEL, confirm=False)

    assert out["status"] == "plan"
    assert _TOKEN_SENTINEL not in json.dumps(out)


def test_influxdb_http_list_strips_token_at_read_layer(tmp_path, monkeypatch):
    """The base read function (not just the Plan factories) strips `token` — proven through the
    live tool wrapper, mirroring module docstring fact #1's "required, not defensive" framing."""
    leaked = "sentinel-leaked-token-from-list"
    _, _, _, _ = _wire(tmp_path, monkeypatch, get_return=[{"name": "met1", "token": leaked}])

    result = server.pbs_metrics_influxdb_http_list()
    assert leaked not in json.dumps(result)


def test_influxdb_http_get_strips_token_at_read_layer(tmp_path, monkeypatch):
    leaked = "sentinel-leaked-token-from-get"
    _, _, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "met1", "token": leaked})

    result = server.pbs_metrics_influxdb_http_get(name="met1")
    assert leaked not in json.dumps(result)
