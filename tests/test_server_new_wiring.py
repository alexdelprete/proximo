"""Server-level integration for the 2026-06-08 tool groups (observability / tasks+pools / PBS).

Proves the trust gate holds across the NEW wiring, not just the original tools:
- every new MUTATION is dry-run by default (confirm=False => status="plan", op NOT called),
- a confirm=True call records a "planned" entry BEFORE it executes (no plan, no mutation),
- reads are audited as non-mutations,
- the pre-classified HIGH risks (lockout service ctl, task_stop, PBS gc/prune/snapshot_delete,
  namespace_delete with groups) actually surface as HIGH through the server,
- the pool_update(delete=True, no-members) footgun is refused through the server too,
- PBS ops route through the separate _pbs() backend and record to the SAME ledger,
- async ops record "submitted" (not "ok"); the whole new surface is exposed via FastMCP.

Backends are faked; the ledger is real (tmp_path) so PLAN->PROVE is exercised end to end.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.backends import ProximoError
from proximo.config import ProximoConfig


class _FakeApi:
    """Records the HTTP verbs the PVE tool layer uses; nothing actually executes."""

    def __init__(self):
        self.config = SimpleNamespace(node="pve")
        self.gets: list = []
        self.posts: list = []
        self.puts: list = []
        self.dels: list = []

    def _get(self, path):
        self.gets.append(path)
        return []

    def _post(self, path, data=None):
        self.posts.append((path, data))
        return "UPID:post"

    def _put(self, path, data=None):
        self.puts.append((path, data))
        return None

    def _delete(self, path, params=None):
        self.dels.append((path, params))
        return None


class _FakePbs:
    """The separate PBS backend — its own verb recorder (params-aware _get/_delete)."""

    def __init__(self):
        self.config = SimpleNamespace(base_url="https://pbs:8007/api2/json")
        self.gets: list = []
        self.posts: list = []
        self.dels: list = []

    def _get(self, path, params=None):
        self.gets.append((path, params))
        return []

    def _post(self, path, data=None):
        self.posts.append((path, data))
        return "UPID:pbs"

    def _delete(self, path, params=None):
        self.dels.append((path, params))
        return None


def _wire(tmp_path, monkeypatch):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log,
    )
    api = _FakeApi()
    pbs = _FakePbs()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, SimpleNamespace(), ledger))
    monkeypatch.setattr(server, "_pbs", lambda: (SimpleNamespace(), pbs))
    return cfg, api, pbs, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# --- Observability ----------------------------------------------------------

def test_node_service_control_lockout_restart_is_high_dry_run(tmp_path, monkeypatch):
    _, api, _, _, log = _wire(tmp_path, monkeypatch)
    out = server.pve_node_service_control("sshd", "restart")  # confirm defaults False
    assert out["status"] == "plan"
    assert out["risk"] == "high"             # lockout-class service
    assert api.posts == []                    # nothing executed on a dry-run
    assert any(e["action"] == "pve_node_service_control" and e["outcome"] == "planned"
               for e in _entries(log))


def test_node_service_control_confirm_records_plan_then_submits(tmp_path, monkeypatch):
    _, api, _, _, log = _wire(tmp_path, monkeypatch)
    out = server.pve_node_service_control("sshd", "restart", confirm=True)
    assert out["status"] == "submitted"
    assert out["result"] == "UPID:post"
    assert len(api.posts) == 1
    outcomes = {e["outcome"] for e in _entries(log)
                if e["action"] == "pve_node_service_control"}
    assert {"planned", "submitted"} <= outcomes   # no plan, no mutation — even one-shot
    assert "ok" not in outcomes                    # async => submitted, never "ok"


def test_node_dns_read_is_audited_non_mutation(tmp_path, monkeypatch):
    _, _, _, _, log = _wire(tmp_path, monkeypatch)
    server.pve_node_dns("pve")
    assert any(e["action"] == "pve_node_dns" and not e["mutation"] for e in _entries(log))


# --- Task control + pools ---------------------------------------------------

def test_task_stop_is_high_dry_run_no_mutation(tmp_path, monkeypatch):
    _, api, _, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pve_task_stop("UPID:pve:0:0:0:0:vzdump:102:root@pam:")
    assert out["status"] == "plan"
    assert out["risk"] == "high"
    assert api.dels == []


def test_pool_create_low_plan_then_confirm_executes(tmp_path, monkeypatch):
    _, api, _, _, log = _wire(tmp_path, monkeypatch)
    dry = server.pve_pool_create("team-a")
    assert dry["status"] == "plan" and dry["risk"] == "low"
    assert api.posts == []
    server.pve_pool_create("team-a", confirm=True)
    assert api.posts and api.posts[0][0] == "/pools"
    assert any(e["outcome"] == "planned" and e["action"] == "pve_pool_create"
               for e in _entries(log))


def test_pool_update_delete_no_members_is_refused_through_server(tmp_path, monkeypatch):
    # The footgun guard fires at plan time — the _plan gate audits the error and re-raises.
    _, api, _, _, log = _wire(tmp_path, monkeypatch)
    with pytest.raises(ProximoError):
        server.pve_pool_update("team-a", delete=True)   # no vms/storage
    assert api.puts == []                                 # nothing mutated
    assert any(e["outcome"] == "error" for e in _entries(log))


def test_pool_delete_dry_run_plans_and_does_not_mutate(tmp_path, monkeypatch):
    _, api, _, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pve_pool_delete("team-a")
    assert out["status"] == "plan"
    assert any("ACL" in b for b in out["blast_radius"])   # honesty: ACL-orphan disclosed
    assert api.dels == []


# --- PBS (routes through the separate _pbs() backend) -----------------------

def test_pbs_gc_start_is_high_dry_run_does_not_call_pbs(tmp_path, monkeypatch):
    _, _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_gc_start("test-datastore")
    assert out["status"] == "plan" and out["risk"] == "high"
    assert pbs.posts == []                                 # PBS backend untouched on dry-run


def test_pbs_gc_start_confirm_records_submitted_not_ok(tmp_path, monkeypatch):
    _, _, pbs, _, log = _wire(tmp_path, monkeypatch)
    out = server.pbs_gc_start("test-datastore", confirm=True)
    assert out["status"] == "submitted"
    assert out["result"] == "UPID:pbs"
    assert pbs.posts and pbs.posts[0][0] == "/admin/datastore/test-datastore/gc"
    outcomes = {e["outcome"] for e in _entries(log) if e["action"] == "pbs_gc_start"}
    assert {"planned", "submitted"} <= outcomes
    assert "ok" not in outcomes


def test_pbs_prune_dry_run_default_is_low_plan(tmp_path, monkeypatch):
    _, _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_prune("test-datastore", keep_last=3)        # dry_run defaults True
    assert out["status"] == "plan" and out["risk"] == "low"
    assert pbs.posts == []


def test_pbs_prune_real_delete_is_high_plan(tmp_path, monkeypatch):
    _, _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_prune("test-datastore", keep_last=3, dry_run=False)
    assert out["status"] == "plan" and out["risk"] == "high"   # real deletion of recovery points
    assert pbs.posts == []


def test_pbs_snapshot_delete_is_high_plan(tmp_path, monkeypatch):
    _, _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_snapshot_delete("test-datastore", "ct", "102", 1700000000)
    assert out["status"] == "plan" and out["risk"] == "high"
    assert pbs.dels == []


def test_pbs_namespace_delete_with_groups_is_high_plan(tmp_path, monkeypatch):
    _, _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_namespace_delete("test-datastore", "team/prod", delete_groups=True)
    assert out["status"] == "plan" and out["risk"] == "high"
    assert pbs.dels == []


def test_pbs_datastores_list_read_is_audited(tmp_path, monkeypatch):
    _, _, pbs, _, log = _wire(tmp_path, monkeypatch)
    server.pbs_datastores_list()
    assert pbs.gets and pbs.gets[0][0] == "/admin/datastore"
    assert any(e["action"] == "pbs_datastores_list" and not e["mutation"]
               for e in _entries(log))


# --- MCP surface: the new tools are actually exposed ------------------------

async def test_new_tools_registered_with_fastmcp():
    tools = {t.name for t in await server.mcp.list_tools()}
    new = {
        # observability
        "pve_node_services_list", "pve_node_service_status", "pve_node_rrddata",
        "pve_node_journal", "pve_node_syslog", "pve_node_dns", "pve_node_subscription",
        "pve_node_certificates", "pve_node_service_control",
        # tasks + pools
        "pve_tasks_list", "pve_task_log", "pve_pools_list", "pve_pool_get",
        "pve_task_stop", "pve_pool_create", "pve_pool_update", "pve_pool_delete",
        # PBS (original 11)
        "pbs_datastores_list", "pbs_datastore_status", "pbs_gc_status",
        "pbs_snapshots_list", "pbs_namespaces_list", "pbs_gc_start", "pbs_verify_start",
        "pbs_prune", "pbs_snapshot_delete", "pbs_namespace_create", "pbs_namespace_delete",
        # PBS coverage-gap reads (Wave B — 6 new)
        "pbs_remotes_list", "pbs_remote_get", "pbs_traffic_controls_list",
        "pbs_jobs_list", "pbs_tasks_list", "pbs_datastore_get",
    }
    assert new <= tools, f"missing from MCP surface: {new - tools}"
    assert len(new) == 34


def test_pbs_verify_start_dry_run_does_not_call_pbs(tmp_path, monkeypatch):
    _, _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_verify_start("test-datastore")
    assert out["status"] == "plan"            # non-destructive but still plan-gated
    assert pbs.posts == []


def test_pbs_namespace_create_dry_run_then_confirm(tmp_path, monkeypatch):
    _, _, pbs, _, log = _wire(tmp_path, monkeypatch)
    dry = server.pbs_namespace_create("test-datastore", "team-a")
    assert dry["status"] == "plan" and dry["risk"] == "low"
    assert pbs.posts == []
    server.pbs_namespace_create("test-datastore", "team-a", confirm=True)
    assert pbs.posts and pbs.posts[0][0] == "/admin/datastore/test-datastore/namespace"
    assert any(e["outcome"] == "planned" and e["action"] == "pbs_namespace_create"
               for e in _entries(log))
