"""Confirm=True sweep — PMG DKIM + customscores (Wave 9e: src/proximo/pmg.py +
src/proximo/tools/pmg_mail.py).

Mirrors the `_wire()`/`_Pmg` idiom already established in `tests/test_confirm_sweep_pmg_routing.py`
(itself mirroring `tests/test_confirm_sweep_pmg_node.py`'s own `_Pbs`-derived template): `_svc` is
monkeypatched (the ONE shared audit ledger lives behind it — `_ledger()` reads `_svc()[3]`) and
`_pmg` is monkeypatched to a fake PmgBackend. This file duplicates its own `_Pmg`/`_wire` rather
than importing another confirm-sweep module's — same self-contained convention every confirm-sweep
module in this repo follows.

NO secret exists anywhere in this chunk (pmg.py's own Wave 9e module section fact #1 — DKIM's
private key is server-generated and never returned; customscores' `digest` is an optimistic-
concurrency token, not a secret) — so there is no raw-ledger-bytes sweep in this file (the 9c
idiom applies only where a real secret is in play).

Every 9e PLAN function that is PURE (no `api` parameter) never touches the fake backend on the
dry-run path; `plan_customscores_update`/`plan_customscores_delete`/`plan_dkim_selector_generate`
DO capture via the fake's `_get` (no secret involved, safe to read) — covered separately below.

Each confirm=True call proves the three welds every confirm-sweep module proves:
  1. return shape — status is "ok" (synchronous) or "submitted" (ambiguous string), never "plan";
  2. the fake PmgBackend captured the underlying call (verb + path + EXACT payload);
  3. the ledger recorded a confirmed mutation — structural asserts only, never exact prose.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig


class _Pmg:
    """Path-aware fake PmgBackend: records every _get/_post/_put/_delete call."""

    def __init__(self):
        self.gets: list[tuple[str, dict | None]] = []
        self.posts: list[tuple[str, dict | None]] = []
        self.puts: list[tuple[str, dict | None]] = []
        self.deletes: list[tuple[str, dict | None]] = []
        self.config = SimpleNamespace(node="pmg", username="root@pam")

    def _get(self, path, params=None):
        self.gets.append((path, params))
        return {}

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
    behind it); pmg.py's Wave 9e tools never touch this backend."""

    def __init__(self):
        self.config = SimpleNamespace(node="pve")


def _wire(tmp_path, monkeypatch):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log,
    )
    api = _Api()
    pmg = _Pmg()
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
# PmgBackend and records a confirmed mutation".  All outcomes here are "ok" (synchronous, null
# return) — pmg_customscores_apply's ambiguous-string outcome is covered separately below.
# ---------------------------------------------------------------------------

_SWEEP_CASES = [
    pytest.param(
        "pmg_dkim_domain_create",
        dict(domain="example.com", comment="primary"),
        "posts", "/config/dkim/domains",
        {"domain": "example.com", "comment": "primary"},
        id="dkim_domain_create",
    ),
    pytest.param(
        "pmg_dkim_domain_update",
        dict(domain="example.com", comment="updated"),
        "puts", "/config/dkim/domains/example.com",
        {"comment": "updated"},
        id="dkim_domain_update",
    ),
    pytest.param(
        "pmg_dkim_domain_delete",
        dict(domain="example.com"),
        "deletes", "/config/dkim/domains/example.com",
        None,
        id="dkim_domain_delete",
    ),
    pytest.param(
        "pmg_dkim_selector_generate",
        dict(selector="mail", keysize=2048),
        "posts", "/config/dkim/selector",
        {"selector": "mail", "keysize": 2048},
        id="dkim_selector_generate",
    ),
    pytest.param(
        "pmg_customscores_create",
        dict(name="MY_RULE", score=3.0),
        "posts", "/config/customscores",
        {"name": "MY_RULE", "score": 3.0},
        id="customscores_create",
    ),
    pytest.param(
        "pmg_customscores_update",
        dict(name="MY_RULE", score=4.0),
        "puts", "/config/customscores/MY_RULE",
        {"score": 4.0},
        id="customscores_update",
    ),
    pytest.param(
        "pmg_customscores_delete",
        dict(name="MY_RULE"),
        "deletes", "/config/customscores/MY_RULE",
        None,
        id="customscores_delete",
    ),
    pytest.param(
        "pmg_customscores_revert_all",
        dict(),
        "deletes", "/config/customscores",
        None,
        id="customscores_revert_all",
    ),
]


@pytest.mark.parametrize(
    "tool_name,kwargs,capture,path,data_exact", _SWEEP_CASES,
)
def test_confirm_true_executes_forwards_and_records(
    tmp_path, monkeypatch, tool_name, kwargs, capture, path, data_exact,
):
    """confirm=True executes (never 'plan'), the fake captured the forwarded call, and the ledger
    recorded a confirmed mutation — the three welds every confirm-sweep module proves."""
    _, pmg, _, log = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)

    out = fn(confirm=True, **kwargs)

    # weld 1: return shape is the EXECUTED shape, never "plan" (all these mutations are synchronous)
    assert out["status"] == "ok"

    # weld 2: the fake captured the underlying call at the expected verb + path, with the EXACT
    # forwarded payload (full dict equality — an accidental extra field now fails).
    calls = getattr(pmg, capture)
    assert calls, f"{tool_name} confirm=True never reached pmg.{capture}"
    call_path, call_data = calls[-1]
    assert call_path == path
    assert call_data == data_exact

    # weld 3: ledger structural asserts — never exact prose
    entry = _confirmed_entry(log, tool_name, "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


# ---------------------------------------------------------------------------
# customscores_apply — the ambiguous-string return: confirm=True records outcome="submitted",
# mirroring pmg_node_network_reload's identical-ambiguity precedent (fact #6, pmg.py Wave 9e
# module section).
# ---------------------------------------------------------------------------

def test_customscores_apply_confirm_records_submitted_with_raw_result(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(pmg, "_put", lambda path, data=None: pmg.puts.append((path, data)) or "OK: applied")

    out = server.pmg_customscores_apply(confirm=True)

    assert out["status"] == "submitted"
    assert out["result"] == "OK: applied"
    assert pmg.puts[-1] == ("/config/customscores", {})
    entry = _confirmed_entry(log, "pmg_customscores_apply", "submitted")
    assert entry["mutation"] is True
    assert entry["detail"]["raw_result"] == "OK: applied"


def test_customscores_apply_forwards_digest_and_restart_daemon(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_customscores_apply(digest="abc123", restart_daemon=True, confirm=True)
    assert pmg.puts[-1] == ("/config/customscores", {"digest": "abc123", "restart-daemon": True})


def test_customscores_apply_dry_run_never_puts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_customscores_apply(confirm=False)
    assert out["status"] == "plan"
    assert not pmg.puts


# ---------------------------------------------------------------------------
# Dry-run: confirm=False never touches the backend (spot-check across verb shapes)
# ---------------------------------------------------------------------------

def test_dkim_domain_create_dry_run_never_posts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_dkim_domain_create(domain="example.com", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.posts


def test_dkim_selector_generate_dry_run_never_posts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_dkim_selector_generate(selector="mail", keysize=2048, confirm=False)
    assert out["status"] == "plan"
    assert not pmg.posts


def test_customscores_delete_dry_run_never_deletes(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_customscores_delete(name="MY_RULE", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.deletes


def test_customscores_revert_all_dry_run_never_deletes(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_customscores_revert_all(confirm=False)
    assert out["status"] == "plan"
    assert not pmg.deletes


# ---------------------------------------------------------------------------
# Direction-aware disclosure: the dry-run PLAN's blast_radius names the real consequence BEFORE
# confirm=True executes it (mirrors the 9a Critical "plan discloses every destructive component"
# class, extended to this chunk's own direction-aware families).
# ---------------------------------------------------------------------------

def test_dkim_selector_generate_plan_discloses_upstream_warning(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    out = server.pmg_dkim_selector_generate(selector="mail", keysize=2048, confirm=False)
    assert out["status"] == "plan"
    joined = " ".join(out["blast_radius"]).lower()
    assert "all future mail will be signed with the new key" in joined


def test_customscores_update_plan_discloses_raise_direction(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(pmg, "_get", lambda path, params=None: {"name": "MY_RULE", "score": 1.0})
    out = server.pmg_customscores_update(name="MY_RULE", score=5.0, confirm=False)
    assert out["status"] == "plan"
    joined = " ".join(out["blast_radius"]).lower()
    assert "raises" in joined
    assert "toward spam" in joined


def test_customscores_update_plan_discloses_lower_direction(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(pmg, "_get", lambda path, params=None: {"name": "MY_RULE", "score": 9.0})
    out = server.pmg_customscores_update(name="MY_RULE", score=1.0, confirm=False)
    assert out["status"] == "plan"
    joined = " ".join(out["blast_radius"]).lower()
    assert "lowers" in joined
    assert "toward ham" in joined


# ---------------------------------------------------------------------------
# Reads reach the fake PmgBackend and are audited as non-mutations (no PLAN/confirm ceremony).
# ---------------------------------------------------------------------------

_READ_CASES = [
    pytest.param("pmg_dkim_domains_list", dict(), "/config/dkim/domains", id="dkim_domains_list"),
    pytest.param(
        "pmg_dkim_domain_get", dict(domain="example.com"), "/config/dkim/domains/example.com",
        id="dkim_domain_get",
    ),
    pytest.param("pmg_dkim_selector_get", dict(), "/config/dkim/selector", id="dkim_selector_get"),
    pytest.param("pmg_dkim_selectors_list", dict(), "/config/dkim/selectors", id="dkim_selectors_list"),
    pytest.param("pmg_customscores_list", dict(), "/config/customscores", id="customscores_list"),
    pytest.param(
        "pmg_customscores_get", dict(name="MY_RULE"), "/config/customscores/MY_RULE",
        id="customscores_get",
    ),
]


@pytest.mark.parametrize("tool_name,kwargs,path", _READ_CASES)
def test_read_reaches_pmg_and_is_audited_as_non_mutation(tmp_path, monkeypatch, tool_name, kwargs, path):
    _, pmg, _, log = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)
    fn(**kwargs)
    assert any(g[0] == path for g in pmg.gets), f"{tool_name} never reached {path!r}: {pmg.gets}"
    assert any(e["action"] == tool_name and not e["mutation"] for e in _entries(log))
