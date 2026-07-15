"""Confirm=True sweep — pve_apt (Wave 1a, 2026-07-15 full-surface campaign).

Mirrors the `_wire()` idiom in tests/test_server_plan.py:110-131 (already re-used and
review-approved in tests/test_confirm_sweep_pve_firewall_network.py,
tests/test_confirm_sweep_pve_guest.py, and tests/test_confirm_sweep_pve_cluster_node_certs.py):
`proximo.server._svc` is monkeypatched to a fake api + a REAL AuditLedger in tmp_path, so a
confirm=True call proves three welds at once:
  1. return shape — status is the EXECUTED shape ("ok"/"submitted"), never "plan";
  2. the fake api captured the underlying call, EXACT payload (full tuple equality) — pve_apt.py
     calls typed methods directly (api.apt_update_refresh/apt_repository_set/apt_repository_add),
     not the generic _post/_put verbs, so the fake exposes those same typed methods (mirrors
     test_confirm_sweep_pve_cluster_node_certs.py's node_hosts_set/node_dns_set/node_startall
     typed-method captures);
  3. the ledger recorded a confirmed mutation — structural asserts only (action, mutation,
     outcome, detail.confirmed), never exact prose.

pve_apt_repository_set/pve_apt_repository_add also call api.apt_repositories_get(node) during
their CAPTURE-or-declare plan build (which runs on BOTH the dry-run and confirm=True paths) — the
fake answers with a small fixture dict so the plan build resolves without raising.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig


class _Api:
    """Fake PVE api exposing only the apt-plane typed methods pve_apt.py calls directly."""

    def __init__(self, node: str = "pve"):
        self.config = SimpleNamespace(node=node)
        self.apt_update_refreshes: list[tuple] = []
        self.apt_repository_sets: list[tuple] = []
        self.apt_repository_adds: list[tuple] = []

    def apt_repositories_get(self, node=None):
        # Small fixture — enough for the CAPTURE-or-declare plan builders to resolve without
        # raising; a "no match found" outcome is a valid, non-failing capture result.
        return {
            "files": [{"path": "/etc/apt/sources.list", "digest": "d1",
                       "repositories": [{"Enabled": 1}]}],
            "standard-repos": [{"handle": "no-subscription", "status": True}],
        }

    def apt_update_refresh(self, node=None, notify=None, quiet=None):
        self.apt_update_refreshes.append((node, notify, quiet))
        return "UPID:pve:00006:0:0:0:aptupdate:0:root@pam:"

    def apt_repository_set(self, path, index, node=None, enabled=None, digest=None):
        self.apt_repository_sets.append((path, index, node, enabled, digest))

    def apt_repository_add(self, handle, node=None, digest=None):
        self.apt_repository_adds.append((handle, node, digest))


def _wire(tmp_path, monkeypatch):
    """The `_wire()` idiom from tests/test_server_plan.py:110-131."""
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        ct_allowlist=frozenset({"*"}), audit_log_path=log,
    )
    api = _Api()
    exec_ = SimpleNamespace()  # unused by these wrappers
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
# pve_apt_update_refresh — typed-method capture, async (task UPID) outcome.
# ---------------------------------------------------------------------------


def test_update_refresh_confirm_executes_forwards_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_apt_update_refresh(notify=True, quiet=False, confirm=True)

    assert out["status"] == "submitted"
    assert out["status"] != "plan"

    assert api.apt_update_refreshes, "pve_apt_update_refresh confirm=True never reached api.apt_update_refresh"
    # exact: the wrapper calls api.apt_update_refresh(node, notify, quiet) positionally.
    assert api.apt_update_refreshes[-1] == (None, True, False)

    entry = _confirmed_entry(log, "pve_apt_update_refresh", "submitted")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
    assert entry["detail"]["notify"] is True
    assert entry["detail"]["quiet"] is False


def test_update_refresh_confirm_sync_reports_ok_not_submitted(tmp_path, monkeypatch):
    """apt_update_refresh() may return None (backends.py types it `str | None` defensively) rather
    than a task UPID — a fixed outcome="submitted" would falsely claim an in-flight task."""
    _, api, _, log = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "apt_update_refresh", lambda node=None, notify=None, quiet=None: None)

    out = server.pve_apt_update_refresh(confirm=True)

    assert out["status"] == "ok"
    assert out["status"] != "submitted"
    assert out["result"] is None

    entry = _confirmed_entry(log, "pve_apt_update_refresh", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


# ---------------------------------------------------------------------------
# pve_apt_repository_set — typed-method capture, synchronous ("ok") outcome.
# ---------------------------------------------------------------------------


def test_repository_set_confirm_executes_forwards_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_apt_repository_set(
        path="/etc/apt/sources.list", index=0, enabled=False, digest="abc123", confirm=True,
    )

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    assert api.apt_repository_sets, "pve_apt_repository_set confirm=True never reached api.apt_repository_set"
    # exact: the wrapper calls api.apt_repository_set(path, index, node, enabled, digest) positionally.
    assert api.apt_repository_sets[-1] == ("/etc/apt/sources.list", 0, None, False, "abc123")

    entry = _confirmed_entry(log, "pve_apt_repository_set", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
    assert entry["detail"]["path"] == "/etc/apt/sources.list"
    assert entry["detail"]["index"] == 0


# ---------------------------------------------------------------------------
# pve_apt_repository_add — typed-method capture, synchronous ("ok") outcome.
# ---------------------------------------------------------------------------


def test_repository_add_confirm_executes_forwards_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_apt_repository_add(handle="no-subscription", digest="def456", confirm=True)

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    assert api.apt_repository_adds, "pve_apt_repository_add confirm=True never reached api.apt_repository_add"
    # exact: the wrapper calls api.apt_repository_add(handle, node, digest) positionally.
    assert api.apt_repository_adds[-1] == ("no-subscription", None, "def456")

    entry = _confirmed_entry(log, "pve_apt_repository_add", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
    assert entry["detail"]["handle"] == "no-subscription"


@pytest.mark.parametrize(
    "tool_name,kwargs",
    [
        ("pve_apt_update_refresh", {}),
        ("pve_apt_repository_set", {"path": "/etc/apt/sources.list", "index": 0}),
        ("pve_apt_repository_add", {"handle": "no-subscription"}),
    ],
)
def test_confirm_true_never_returns_plan_status(tmp_path, monkeypatch, tool_name, kwargs):
    """Cross-check (table-driven, matching the sibling confirm-sweep files' style): every apt
    mutation's confirm=True path returns something other than "plan"."""
    _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)
    out = fn(confirm=True, **kwargs)
    assert out["status"] != "plan"
