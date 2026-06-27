"""Server-level PLAN integration — dry-run by default, and the plan lands in the ledger.

Backends are faked; the ledger is real (in tmp_path) so we prove the PLAN->PROVE weld:
a confirm=False call must both return status="plan" AND write a "planned" audit entry,
and a confirm=True call must execute AND record that it was confirmed.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.backends import ExecResult
from proximo.config import ProximoConfig


class _FakeApi:
    def __init__(self, status: dict, *, snaps=None, snapshot_raises=False, task_ok=True):
        self._status = status
        self.config = SimpleNamespace(node="pve")  # new ops resolve `node or api.config.node`
        self.powered: list[tuple] = []
        self.snaps = snaps if snaps is not None else []
        self.created: list[tuple] = []
        self.rolled: list[tuple] = []
        self.deleted: list[tuple] = []
        self._snapshot_raises = snapshot_raises
        self._task_ok = task_ok
        # provisioning/storage/backup ops reach the HTTP verbs + list_guests
        self.guests: list[dict] = []
        self.gets: list = []
        self.posts: list = []
        self.dels: list = []

    def guest_status(self, vmid, kind="lxc", node=None):
        return self._status

    def guest_power(self, vmid, action, kind="lxc", node=None):
        self.powered.append((vmid, action))
        return {"ok": True}

    # snapshots (UNDO)
    def snapshot_list(self, vmid, kind="lxc", node=None):
        return self.snaps

    def snapshot_create(self, vmid, snapname, kind="lxc", node=None, description=None):
        if self._snapshot_raises:
            raise RuntimeError("storage does not support snapshots")
        self.created.append((vmid, snapname))
        return "UPID:create"

    def snapshot_rollback(self, vmid, snapname, kind="lxc", node=None):
        self.rolled.append((vmid, snapname))
        return "UPID:rollback"

    def snapshot_delete(self, vmid, snapname, kind="lxc", node=None, force=False):
        self.deleted.append((vmid, snapname))
        return "UPID:delete"

    def task_status(self, upid, node=None):
        return {"status": "stopped", "exitstatus": "OK" if self._task_ok else "boom: task failed"}

    # diagnose (node reads)
    def node_status(self, node=None):
        return {"uptime": 1000, "memory": {"used": 1, "total": 100}}

    def node_storage(self, node=None):
        return [{"storage": "local", "used": 1, "total": 100}]

    def node_tasks(self, node=None, limit=50):
        return []

    # provisioning/storage/backup reach these
    def list_guests(self, node=None):
        return self.guests

    def _get(self, path):
        self.gets.append(path)
        return []

    def _post(self, path, data=None):
        self.posts.append((path, data))
        return "UPID:post"

    def _delete(self, path, params=None):
        self.dels.append((path, params))
        return "UPID:del"


class _FakeExec:
    def __init__(self):
        self.ran: list = []

    def run(self, ctid, command, timeout=60):
        self.ran.append((ctid, command))
        return ExecResult(str(ctid), " ".join(command), 0, "out", "")

    def psql(self, ctid, sql, db="postgres", user="postgres", timeout=60):
        self.ran.append((ctid, sql))
        return ExecResult(str(ctid), sql, 0, "out", "")

    def logs(self, ctid, unit, lines=50):
        self.ran.append((ctid, unit))
        return ExecResult(str(ctid), f"journalctl -u {unit}", 0, "log lines", "")


def _wire(tmp_path, monkeypatch, *, status=None, enable_exec=True, allowlist=("*",),
          snaps=None, snapshot_raises=False, task_ok=True, redact_ledger=False):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        ct_allowlist=frozenset(allowlist), enable_exec=enable_exec, audit_log_path=log,
        redact_ledger=redact_ledger,
    )
    api = _FakeApi(status or {"status": "running", "name": "web", "uptime": 500},
                   snaps=snaps, snapshot_raises=snapshot_raises, task_ok=task_ok)
    exec_ = _FakeExec()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, exec_, ledger))
    return cfg, api, exec_, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# --- power ---

def test_power_dryrun_returns_plan_and_does_not_execute(tmp_path, monkeypatch):
    _, api, _, _, log = _wire(tmp_path, monkeypatch, status={"status": "running", "name": "w", "uptime": 500})
    out = server.pve_guest_power("1975", "stop")  # confirm defaults False
    assert out["status"] == "plan"
    assert out["risk"] == "high"
    assert out["change"] == "stop lxc 1975"
    assert api.powered == []  # nothing executed


def test_power_dryrun_records_planned_entry(tmp_path, monkeypatch):
    _, _, _, _, log = _wire(tmp_path, monkeypatch)
    server.pve_guest_power("1975", "stop")
    planned = [e for e in _entries(log) if e["outcome"] == "planned"]
    assert len(planned) == 1
    assert planned[0]["mutation"] is True
    assert planned[0]["detail"]["risk"] == "high"


def test_power_confirm_executes_and_records_confirmed(tmp_path, monkeypatch):
    _, api, _, _, log = _wire(tmp_path, monkeypatch)
    out = server.pve_guest_power("1975", "stop", confirm=True)
    assert api.powered == [("1975", "stop")]
    assert any(e["detail"].get("confirmed") for e in _entries(log))
    assert out != {"status": "plan"}


def test_oneshot_confirm_still_records_a_plan_first(tmp_path, monkeypatch):
    # The guarantee: NO mutation without a recorded plan — even a one-shot confirm=True call
    # must leave BOTH a "planned" and a "confirmed" entry for the target (PLAN before mutate).
    _, _, _, _, log = _wire(tmp_path, monkeypatch)
    server.pve_guest_power("1975", "stop", confirm=True)  # sole call, no prior dry-run
    outcomes = [e["outcome"] for e in _entries(log) if e["target"] == "lxc/1975:stop"]
    assert "planned" in outcomes, "one-shot confirm executed with no plan recorded"
    assert any(e["outcome"] == "submitted" and e["detail"].get("confirmed")
               for e in _entries(log)), "no confirmed execution entry"


def test_oneshot_confirm_exec_records_plan_first(tmp_path, monkeypatch):
    _, _, exec_, _, log = _wire(tmp_path, monkeypatch, enable_exec=True)
    server.ct_exec("105", ["echo", "hi"], confirm=True)
    outcomes = [e["outcome"] for e in _entries(log) if e["target"] == "105"]
    assert "planned" in outcomes
    assert exec_.ran == [("105", ["echo", "hi"])]


# --- ct_exec ---

def test_ct_exec_dryrun_returns_plan(tmp_path, monkeypatch):
    _, _, exec_, _, _ = _wire(tmp_path, monkeypatch, enable_exec=True)
    out = server.ct_exec("105", ["rm", "-rf", "/x"])
    assert out["status"] == "plan"
    assert out["risk"] == "high"
    assert "heuristic" in out["note"].lower()
    assert exec_.ran == []  # not executed


def test_ct_exec_confirm_executes(tmp_path, monkeypatch):
    _, _, exec_, _, _ = _wire(tmp_path, monkeypatch, enable_exec=True)
    out = server.ct_exec("105", ["echo", "hi"], confirm=True)
    assert out["status"] == "ok"
    assert out["result"]["returncode"] == 0
    assert exec_.ran == [("105", ["echo", "hi"])]


def test_ct_exec_disabled_wins_over_plan(tmp_path, monkeypatch):
    _, _, _, _, _ = _wire(tmp_path, monkeypatch, enable_exec=False)
    out = server.ct_exec("105", ["echo", "hi"])
    assert out["status"] == "blocked:exec_disabled"  # safe default still refuses before planning


# --- ct_psql ---

def test_ct_psql_dryrun_classifies_and_plans(tmp_path, monkeypatch):
    _, _, _, _, _ = _wire(tmp_path, monkeypatch, enable_exec=True)
    out = server.ct_psql("105", "DROP TABLE t", db="appdb")
    assert out["status"] == "plan"
    assert out["risk"] == "high"
    assert "appdb" in out["change"]


# === Redteam regressions (2026-06-07) ========================================

class _BrokenApi:
    """guest_status raises — simulates a bad vmid / unreachable PVE during planning."""

    def guest_status(self, vmid, kind="lxc", node=None):
        raise RuntimeError("boom")


def test_failed_dryrun_is_audited_then_reraised(tmp_path, monkeypatch):
    # MED-1: a dry-run whose live read fails must still leave an audit trail, not vanish.
    import pytest
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
                        ct_allowlist=frozenset({"*"}), enable_exec=True, audit_log_path=log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, _BrokenApi(), _FakeExec(), AuditLedger(log)))
    with pytest.raises(RuntimeError):
        server.pve_guest_power("9999", "stop")  # dry-run; guest_status raises
    errs = [e for e in _entries(log) if e["outcome"] == "error"]
    assert errs, "failed dry-run left no audit entry"
    assert errs[0]["detail"].get("phase") == "planning"


def test_planned_entry_records_live_state(tmp_path, monkeypatch):
    # MED-4: the previewed live state (current) must be on the ledger, not just risk/change.
    _, _, _, _, log = _wire(tmp_path, monkeypatch,
                            status={"status": "running", "name": "web", "uptime": 500})
    server.pve_guest_power("1975", "stop")
    planned = [e for e in _entries(log) if e["outcome"] == "planned"][0]
    assert planned["detail"]["current"]["status"] == "running"


# === UNDO pillar: snapshot tools + auto-undo =================================

def test_snapshot_list_is_read(tmp_path, monkeypatch):
    _, api, _, _, _ = _wire(tmp_path, monkeypatch, snaps=[{"name": "before_x"}])
    assert server.pve_snapshot_list("105") == [{"name": "before_x"}]


def test_snapshot_create_dryrun_then_confirm(tmp_path, monkeypatch):
    _, api, _, _, log = _wire(tmp_path, monkeypatch)
    out = server.pve_snapshot_create("105", "before_x")
    assert out["status"] == "plan" and api.created == []
    server.pve_snapshot_create("105", "before_x", confirm=True)
    assert api.created == [("105", "before_x")]
    assert any(e["outcome"] == "planned" for e in _entries(log))


def test_rollback_dryrun_is_high_and_confirm_executes(tmp_path, monkeypatch):
    _, api, _, _, _ = _wire(tmp_path, monkeypatch, snaps=[{"name": "before_x", "snaptime": 1700000000}])
    out = server.pve_rollback("105", "before_x")
    assert out["status"] == "plan"
    assert out["risk"] == "high"
    assert any("discard" in b.lower() for b in out["blast_radius"])
    server.pve_rollback("105", "before_x", confirm=True)
    assert api.rolled == [("105", "before_x")]


def test_snapshot_delete_dryrun_then_confirm(tmp_path, monkeypatch):
    _, api, _, _, _ = _wire(tmp_path, monkeypatch)
    assert server.pve_snapshot_delete("105", "before_x")["status"] == "plan"
    server.pve_snapshot_delete("105", "before_x", confirm=True)
    assert api.deleted == [("105", "before_x")]


def test_task_status_is_read(tmp_path, monkeypatch):
    _, _, _, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pve_task_status("UPID:pve:00001:0:0:0:vzsnapshot:105:root@pam:")
    assert out["status"] == "stopped"


def test_ct_exec_auto_undo_snapshots_then_runs(tmp_path, monkeypatch):
    _, api, exec_, _, log = _wire(tmp_path, monkeypatch, enable_exec=True)
    out = server.ct_exec("105", ["rm", "-rf", "/x"], snapshot=True, confirm=True)
    assert api.created and api.created[0][0] == "105"      # snapshot taken first
    assert exec_.ran == [("105", ["rm", "-rf", "/x"])]     # then the command ran
    assert out["status"] == "ok"
    assert out["result"]["undo_point"]["snapshot"].startswith("proximo_undo_")
    # honesty: the undo point must disclose it isn't auto-pruned + point at the reaper.
    assert "pve_snapshot_delete" in out["result"]["undo_point"]["note"]
    assert any(e["outcome"] == "undo_point" for e in _entries(log))


def test_ct_exec_auto_undo_fail_closed_when_snapshot_fails(tmp_path, monkeypatch):
    _, api, exec_, _, log = _wire(tmp_path, monkeypatch, enable_exec=True, snapshot_raises=True)
    out = server.ct_exec("105", ["rm", "-rf", "/x"], snapshot=True, confirm=True)
    assert out["status"] == "blocked:undo_unavailable"
    assert exec_.ran == []  # command must NOT run if the undo net can't be hung
    assert any(e["outcome"] == "blocked:undo_unavailable" for e in _entries(log))


def test_ct_exec_auto_undo_fail_closed_when_task_fails(tmp_path, monkeypatch):
    _, api, exec_, _, _ = _wire(tmp_path, monkeypatch, enable_exec=True, task_ok=False)
    out = server.ct_exec("105", ["rm", "-rf", "/x"], snapshot=True, confirm=True)
    assert out["status"] == "blocked:undo_unavailable"
    assert exec_.ran == []  # snapshot task failed -> fail closed


def test_ct_exec_without_snapshot_flag_does_not_snapshot(tmp_path, monkeypatch):
    _, api, exec_, _, _ = _wire(tmp_path, monkeypatch, enable_exec=True)
    server.ct_exec("105", ["echo", "hi"], confirm=True)  # snapshot defaults False
    assert api.created == []
    assert exec_.ran == [("105", ["echo", "hi"])]


def test_ct_psql_auto_undo_snapshots_then_runs(tmp_path, monkeypatch):
    _, api, exec_, _, _ = _wire(tmp_path, monkeypatch, enable_exec=True)
    out = server.ct_psql("105", "DELETE FROM t", snapshot=True, confirm=True)
    assert api.created and exec_.ran
    assert out["status"] == "ok"
    assert out["result"]["undo_point"]["snapshot"].startswith("proximo_undo_")


# === UNDO redteam hardening (2026-06-07) =====================================

def test_auto_undo_fail_closed_when_task_omits_exitstatus(tmp_path, monkeypatch):
    # A "stopped" task with no exitstatus must NOT be treated as success (fail-closed).
    _, api, exec_, _, _ = _wire(tmp_path, monkeypatch, enable_exec=True, task_ok=None)
    out = server.ct_exec("105", ["rm", "-rf", "/x"], snapshot=True, confirm=True)
    assert out["status"] == "blocked:undo_unavailable"
    assert exec_.ran == []


def test_ct_exec_allowlist_blocks_before_snapshot(tmp_path, monkeypatch):
    # A CTID outside the allowlist must be refused cleanly — and NO snapshot taken for it (no orphan/leak).
    _, api, exec_, _, _ = _wire(tmp_path, monkeypatch, enable_exec=True, allowlist=("100",))
    out = server.ct_exec("999", ["echo", "hi"], snapshot=True, confirm=True)
    assert out["status"] == "blocked:allowlist"
    assert api.created == []   # no orphaned snapshot for a forbidden CTID
    assert exec_.ran == []


def test_ct_psql_allowlist_blocks(tmp_path, monkeypatch):
    _, api, exec_, _, _ = _wire(tmp_path, monkeypatch, enable_exec=True, allowlist=("100",))
    assert server.ct_psql("999", "SELECT 1", confirm=True)["status"] == "blocked:allowlist"


def test_ct_psql_records_sql_body_by_default(tmp_path, monkeypatch):
    # Default = audit completeness: the executed SQL is in the ledger detail.
    _, _, _, _, log = _wire(tmp_path, monkeypatch, enable_exec=True)
    server.ct_psql("105", "DROP TABLE t", confirm=True)
    psql = [e for e in _entries(log) if e["action"] == "ct_psql"]
    assert any(e["detail"].get("sql") == "DROP TABLE t" for e in psql)


def test_ct_psql_redacts_sql_in_ledger_when_configured(tmp_path, monkeypatch):
    # Opt-in: the SQL body is NEVER persisted — only a verifiable fingerprint.
    _, _, _, _, log = _wire(tmp_path, monkeypatch, enable_exec=True, redact_ledger=True)
    server.ct_psql("105", "DROP TABLE secrets", confirm=True)
    psql = [e for e in _entries(log) if e["action"] == "ct_psql"]
    assert psql
    for e in psql:                                            # plan + exec entries
        assert "sql" not in e["detail"]                      # body never persisted
        assert "DROP TABLE secrets" not in json.dumps(e)      # nowhere in the entry (incl. plan change)
    assert any(len(e["detail"].get("sql_sha256", "")) == 64 for e in psql)  # fingerprint recorded


def test_ct_exec_records_command_by_default(tmp_path, monkeypatch):
    # Default = audit completeness: the executed argv is in the ledger detail.
    _, _, _, _, log = _wire(tmp_path, monkeypatch, enable_exec=True)
    server.ct_exec("105", ["psql", "-c", "select 1"], confirm=True)
    ex = [e for e in _entries(log) if e["action"] == "ct_exec"]
    assert any(e["detail"].get("command") == ["psql", "-c", "select 1"] for e in ex)


def test_ct_exec_redacts_command_in_ledger_when_configured(tmp_path, monkeypatch):
    # Opt-in: command args (which can carry secrets like --password) are NEVER persisted.
    _, _, _, _, log = _wire(tmp_path, monkeypatch, enable_exec=True, redact_ledger=True)
    server.ct_exec("105", ["mysql", "--password", "hunter2"], confirm=True)
    ex = [e for e in _entries(log) if e["action"] == "ct_exec"]
    assert ex
    for e in ex:                                              # plan + exec entries
        assert "command" not in e["detail"]                  # argv never persisted
        assert "hunter2" not in json.dumps(e)                 # the secret appears nowhere
    assert any(len(e["detail"].get("cmd_sha256", "")) == 64 for e in ex)  # fingerprint recorded


def test_async_snapshot_mutation_records_submitted_not_ok(tmp_path, monkeypatch):
    # The PROVE ledger must not claim an async op is "ok" (done) when it only started.
    _, api, _, _, log = _wire(tmp_path, monkeypatch, snaps=[{"name": "s1"}])
    server.pve_rollback("105", "s1", confirm=True)
    outcomes = [e["outcome"] for e in _entries(log) if e["action"] == "pve_rollback"]
    assert "submitted" in outcomes
    assert "ok" not in outcomes


# === Symmetric envelope contract (execute-path status key) ==================

def test_sync_mutation_envelope_status_is_ok(tmp_path, monkeypatch):
    """A synchronous mutation (confirm=True) must return status='ok' in the envelope.

    Verifies the symmetric contract: caller can uniformly read resp['status'] and it is
    always honest — sync ops say 'ok', async ops say 'submitted', never swapped. Tested at
    the `_audited` seam directly, since the mapping is a property of `_audited`, not of any
    one tool (every UPID-returning op, incl. pve_guest_power, is async → 'submitted'; the
    async side is covered by test_async_mutation_envelope_status_is_submitted).
    """
    _wire(tmp_path, monkeypatch)
    out = server._audited("unit_sync_mutation", "x", lambda: {"done": True},
                          mutation=True, detail={"confirmed": True})
    assert out["status"] == "ok", (
        "synchronous mutation must return status='ok' in the execute envelope"
    )
    assert "result" in out, "execute envelope must carry a 'result' key"


def test_async_mutation_envelope_status_is_submitted(tmp_path, monkeypatch):
    """An async mutation (confirm=True) must return status='submitted' in the envelope.

    Verifies the honesty guarantee: an in-flight async op must NEVER claim 'ok'
    (done) — only 'submitted' (started).  The ledger records 'submitted' for exactly
    the same reason; the envelope must mirror it.  Uses pve_rollback (outcome='submitted').
    """
    _, api, _, _, log = _wire(tmp_path, monkeypatch, snaps=[{"name": "s1"}])
    out = server.pve_rollback("105", "s1", confirm=True)
    assert out["status"] == "submitted", (
        "async mutation must return status='submitted' — never 'ok' for an in-flight op"
    )
    assert "result" in out, "execute envelope must carry a 'result' key"
    # The ledger and the envelope must agree on the outcome (PROVE coherence).
    ledger_outcomes = [e["outcome"] for e in _entries(log) if e["action"] == "pve_rollback"]
    assert "submitted" in ledger_outcomes, "ledger must also record 'submitted'"
    assert "ok" not in ledger_outcomes, "ledger must NOT claim an async op is 'ok'"


def test_plan_path_status_is_still_plan(tmp_path, monkeypatch):
    """The PLAN path (confirm=False) must still return status='plan' — unchanged by the
    envelope change.  The envelope only wraps the execute path (confirm=True).
    """
    _, _, _, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pve_guest_power("1975", "stop", confirm=False)
    assert out["status"] == "plan", "plan path must still return status='plan'"
    # No 'result' key on the plan response — the plan envelope is separate.
    assert "result" not in out, "plan response must NOT carry a 'result' key"


# === DIAGNOSE pillar ========================================================

def test_ct_diagnose_is_read_and_audited(tmp_path, monkeypatch):
    _, _, exec_, _, log = _wire(tmp_path, monkeypatch, enable_exec=True)
    out = server.ct_diagnose("105")
    assert "guest" in out and "probes" in out  # full report (exec on + allowlisted)
    assert any(e["action"] == "ct_diagnose" and not e["mutation"] for e in _entries(log))


def test_ct_diagnose_allowlist_gate_when_exec_on(tmp_path, monkeypatch):
    _, _, _, _, _ = _wire(tmp_path, monkeypatch, enable_exec=True, allowlist=("100",))
    assert server.ct_diagnose("999")["status"] == "blocked:allowlist"


def test_ct_diagnose_api_only_when_exec_disabled(tmp_path, monkeypatch):
    _, _, exec_, _, _ = _wire(tmp_path, monkeypatch, enable_exec=False)
    out = server.ct_diagnose("105")
    assert "guest" in out             # API part present
    assert "probes_skipped" in out    # in-container probes disclosed-skipped, not silently empty
    assert exec_.ran == []


def test_pve_diagnose_is_read_and_audited(tmp_path, monkeypatch):
    _, _, _, _, log = _wire(tmp_path, monkeypatch)
    out = server.pve_diagnose("pve")
    assert "storage" in out and "flags" in out
    assert any(e["action"] == "pve_diagnose" and not e["mutation"] for e in _entries(log))


# === MCP surface ============================================================

async def test_all_expected_tools_registered_with_fastmcp():
    # Direct-call tests stay green even if a @mcp.tool() decorator were dropped — assert the REAL
    # MCP surface (what a client sees) actually exposes every tool.
    tools = {t.name for t in await server.mcp.list_tools()}
    expected = {
        "pve_node_status", "pve_list_guests", "pve_guest_status", "pve_guest_power",
        "pve_snapshot_list", "pve_snapshot_create", "pve_rollback", "pve_snapshot_delete",
        "pve_task_status", "ct_exec", "ct_psql", "ct_logs", "ct_diagnose", "pve_diagnose",
        "audit_verify",
        # backup & restore
        "pve_backup", "pve_backup_list", "pve_backup_delete", "pve_restore",
        # provisioning
        "pve_create_container", "pve_create_vm", "pve_clone", "pve_delete_guest",
        # storage / iso / templates
        "pve_storage_content", "pve_storage_status", "pve_storage_download",
        "pve_storage_content_delete",
        # config edit
        "pve_guest_config_get", "pve_guest_config_set", "pve_guest_config_revert",
        # disk ops
        "pve_disk_resize", "pve_disk_move",
        # cloud-init / template
        "pve_cloudinit_get", "pve_cloudinit_set", "pve_template_convert",
        # access governance (reads)
        "pve_users_list", "pve_roles_list", "pve_acl_list", "pve_tokens_list",
        "pve_overbroad_grants",
        # access governance (mutations)
        "pve_acl_modify", "pve_token_create", "pve_token_revoke",
        # firewall (reads)
        "pve_firewall_rules_list", "pve_firewall_options_get", "pve_security_groups_list",
        "pve_ipset_list",
        # firewall (mutations)
        "pve_firewall_rule_add", "pve_firewall_rule_remove", "pve_firewall_rule_update",
        "pve_firewall_set_enabled",
        # network & SDN (reads)
        "pve_network_list", "pve_sdn_zones_list", "pve_sdn_vnets_list",
        # network & SDN (mutations)
        "pve_network_iface_create", "pve_network_iface_update", "pve_network_apply",
        "pve_sdn_apply",
        # cluster & HA (reads)
        "pve_cluster_status", "pve_cluster_resources", "pve_ha_groups_list",
        "pve_ha_resources_list",
        # cluster & HA (mutations)
        "pve_guest_migrate", "pve_ha_resource_add", "pve_ha_resource_remove",
        # backup schedules plane B (read)
        "pve_backup_job_list",
        # backup schedules plane B (mutations)
        "pve_backup_job_create", "pve_backup_job_update", "pve_backup_job_delete",
        "pve_replication_create", "pve_replication_update", "pve_replication_delete",
        "pbs_job_create", "pbs_job_update", "pbs_job_delete", "pbs_job_run",
        "pbs_realm_sync",
        # notifications & metrics plane E (reads)
        "pve_notification_endpoint_list", "pve_metrics_server_list",
        # notifications & metrics plane E (mutations)
        "pve_notification_endpoint_create", "pve_notification_endpoint_update",
        "pve_notification_endpoint_delete",
        "pve_notification_matcher_set", "pve_notification_matcher_delete",
        "pve_notification_test",
        "pve_metrics_server_set", "pve_metrics_server_delete",
        # hardware PCI/USB mappings plane F (read)
        "pve_hardware_list", "pve_mapping_pci_list", "pve_mapping_usb_list",
        # hardware PCI/USB mappings plane F (mutations)
        "pve_mapping_pci_create", "pve_mapping_pci_update", "pve_mapping_pci_delete",
        "pve_mapping_usb_create", "pve_mapping_usb_update", "pve_mapping_usb_delete",
        # ACME & TLS certs plane G (mutations)
        "pve_acme_account_create", "pve_acme_account_update", "pve_acme_account_delete",
        "pve_acme_plugin_create", "pve_acme_plugin_update", "pve_acme_plugin_delete",
        # qemu-agent plane (Wave 3)
        "pve_agent_exec", "pve_agent_info", "pve_agent_file_read",
        "pve_agent_file_write", "pve_agent_fs", "pve_agent_set_password",
        # node-lifecycle (Wave 4)
        "pve_node_disks_list", "pve_node_disk_smart",
        "pve_node_disk_wipe", "pve_node_disk_initgpt",
        "pve_node_storage_backend_list", "pve_node_storage_backend_create",
        "pve_node_storage_backend_delete",
        "pve_node_time_get", "pve_node_time_set",
        "pve_node_hosts_get", "pve_node_hosts_set",
        "pve_node_dns_set",
        "pve_node_cert_upload", "pve_node_cert_delete",
        "pve_node_startall", "pve_node_stopall", "pve_node_migrateall",
        # pbs-config-and-safety (Wave 5)
        "pbs_datastore_create", "pbs_datastore_update", "pbs_datastore_delete",
        "pbs_snapshot_protected_set", "pbs_snapshot_notes_set", "pbs_group_change_owner",
        "pbs_remote_create", "pbs_remote_update", "pbs_remote_delete",
        "pbs_traffic_control_upsert", "pbs_traffic_control_delete",
    }
    assert expected <= tools, f"missing from MCP surface: {expected - tools}"


# === new tool groups (backup / provisioning / storage): confirm-gate + PLAN->PROVE ==========

def test_pve_delete_guest_dry_run_plans_high_and_does_not_mutate(tmp_path, monkeypatch):
    _, api, _, _, log = _wire(tmp_path, monkeypatch, status={"status": "running", "name": "old"})
    out = server.pve_delete_guest("777", confirm=False)
    assert out["status"] == "plan"
    assert out["risk"] == "high"             # destroy is always HIGH
    assert api.dels == []                     # nothing deleted on a dry-run
    assert any(e["action"] == "pve_delete_guest" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pve_delete_guest_confirm_records_plan_before_executing(tmp_path, monkeypatch):
    _, api, _, _, log = _wire(tmp_path, monkeypatch, status={"status": "running", "name": "old"})
    out = server.pve_delete_guest("777", confirm=True)
    assert out["status"] == "submitted"
    assert out["result"] == "UPID:del"
    assert len(api.dels) == 1                  # the delete fired
    outcomes = {e["outcome"] for e in _entries(log) if e["action"] == "pve_delete_guest"}
    assert {"planned", "submitted"} <= outcomes  # no plan, no mutation — even on one-shot confirm


def test_pve_delete_guest_plan_surfaces_cascade(tmp_path, monkeypatch):
    """Dry-run pve_delete_guest for a found, running, force=False guest surfaces wont_proceed/running
    in resp['affected'] and carries 'complete'. Tests the full server → plan_delete → gather → compute
    seam without any live PVE connection.
    """
    import proximo.blast as B

    # Patch the four module-level readers that gather_guest_dependents calls
    monkeypatch.setattr(B, "cluster_resources", lambda api: [])
    monkeypatch.setattr(B, "guest_config_get", lambda api, vmid, kind, node=None: {})
    monkeypatch.setattr(B, "ha_resources_list", lambda api: [])
    monkeypatch.setattr(B, "pools_list", lambda api: [])

    # _wire injects a _FakeApi as the api; status=running so the running wont_proceed fires
    _wire(tmp_path, monkeypatch, status={"status": "running", "name": "test-vm"})

    resp = server.pve_delete_guest("9000", kind="qemu", confirm=False, force=False)
    assert resp["status"] == "plan"
    assert resp["risk"] == "high"
    # cascade fields must be present in the serialised plan dict
    assert "affected" in resp and isinstance(resp["affected"], list)
    assert "complete" in resp
    # a running guest without force must produce a wont_proceed/running entry
    assert any(
        a["category"] == "wont_proceed" and a["kind"] == "running"
        for a in resp["affected"]
    )


def test_pve_restore_overwrite_with_force_is_high_and_dry_runs(tmp_path, monkeypatch):
    _, api, _, _, _ = _wire(tmp_path, monkeypatch, status={"status": "stopped", "name": "victim"})
    out = server.pve_restore("102", "local:backup/vzdump-lxc-102.tar.zst", "local",
                             force=True, confirm=False)
    assert out["status"] == "plan"
    assert out["risk"] == "high"              # overwriting an existing guest
    assert api.posts == []                     # nothing restored on a dry-run


def test_pve_backup_stop_mode_plan_is_high(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    out = server.pve_backup("102", "local", mode="stop", confirm=False)
    assert out["status"] == "plan" and out["risk"] == "high"   # stop mode HALTS the guest


def test_pve_storage_content_delete_backup_volume_is_high(tmp_path, monkeypatch):
    _, api, _, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pve_storage_content_delete("local", "local:backup/vzdump-lxc-102.tar.zst",
                                            confirm=False)
    assert out["status"] == "plan" and out["risk"] == "high"
    assert api.dels == []


def test_pve_create_container_dry_run_then_confirm(tmp_path, monkeypatch):
    _, api, _, _, _ = _wire(tmp_path, monkeypatch)
    api.guests = []                            # vmid free -> "creates" path
    dry = server.pve_create_container("950", "local:vztmpl/debian-12.tar.zst", "local",
                                      confirm=False)
    assert dry["status"] == "plan"
    assert api.posts == []                     # dry-run does not create
    ok = server.pve_create_container("950", "local:vztmpl/debian-12.tar.zst", "local",
                                     confirm=True)
    assert ok["status"] == "submitted"
    assert ok["result"] == "UPID:post"
    assert len(api.posts) == 1


# --- ct_logs allowlist (server-layer, audit-accurate) ---

def test_ct_logs_allowlist_gate_at_server_layer(tmp_path, monkeypatch):
    """A forbidden CTID must ledger as blocked:allowlist (not a backend error) and never reach exec."""
    _, _, exec_, _, log = _wire(tmp_path, monkeypatch, enable_exec=True, allowlist=("100",))
    out = server.ct_logs("999", "nginx")
    assert out["status"] == "blocked:allowlist"
    assert exec_.ran == []
    assert any(e["action"] == "ct_logs" and e["outcome"] == "blocked:allowlist"
               and not e["mutation"]  # read-only tool: a blocked read must not ledger as a mutation
               for e in _entries(log))


def test_ct_logs_executes_for_permitted_ctid(tmp_path, monkeypatch):
    _, _, exec_, _, log = _wire(tmp_path, monkeypatch, enable_exec=True, allowlist=("100",))
    out = server.ct_logs("100", "nginx")
    assert out["returncode"] == 0 and out["stdout"] == "log lines"
    assert exec_.ran == [("100", "nginx")]
    assert any(e["action"] == "ct_logs" and e["outcome"] == "ok" and not e["mutation"]
               for e in _entries(log))


def test_ct_logs_exec_disabled_wins_over_allowlist(tmp_path, monkeypatch):
    """Check order is pinned: with exec off, a forbidden CTID ledgers blocked:exec_disabled
    (the true outer gate), never blocked:allowlist."""
    _, _, _, _, log = _wire(tmp_path, monkeypatch, enable_exec=False, allowlist=("100",))
    out = server.ct_logs("999", "nginx")
    assert out["status"] == "blocked:exec_disabled"
    entries = _entries(log)
    assert any(e["action"] == "ct_logs" and e["outcome"] == "blocked:exec_disabled"
               and not e["mutation"] for e in entries)
    assert not any(e["outcome"] == "blocked:allowlist" for e in entries)


# === registry-completeness: every MUTATING tool must be confirm-gated (PLAN-by-default) ===========

# The read-only surface: tools that legitimately take NO `confirm` gate. EVERYTHING ELSE must gate.
# This is the guardrail the whole thesis demands — a future MUTATING tool added without a confirm
# param fails here (it won't be in this set), forcing the author to gate it (or, if it's genuinely
# read-only, to consciously add it below). Counterpart to test_tool_count's count pin: that catches
# "a tool changed"; this catches "a dangerous tool is ungated".
_READ_ONLY_TOOLS = frozenset({
    "audit_verify", "ct_diagnose", "ct_logs",
    "pbs_datastore_get", "pbs_datastore_status", "pbs_datastores_list",
    "pbs_gc_status", "pbs_jobs_list", "pbs_namespaces_list",
    "pbs_remote_get", "pbs_remotes_list", "pbs_snapshots_list",
    "pbs_tasks_list", "pbs_traffic_controls_list",
    "pve_acl_list", "pve_backup_job_list", "pve_backup_list", "pve_cloudinit_get",
    "pve_cluster_resources",
    "pve_cluster_status", "pve_diagnose", "pve_doctor", "pve_firewall_alias_list",
    "pve_firewall_options_get", "pve_firewall_rules_list", "pve_group_get", "pve_groups_list",
    "pve_guest_config_get", "pve_guest_status", "pve_ha_groups_list", "pve_ha_resources_list",
    "pve_ha_rules_list", "pve_hardware_list", "pve_ipset_list", "pve_list_guests",
    "pve_mapping_pci_list", "pve_mapping_usb_list",
    "pve_metrics_server_list", "pve_network_list",
    "pve_node_certificates", "pve_node_dns", "pve_node_journal", "pve_node_rrddata",
    "pve_node_service_status", "pve_node_services_list", "pve_node_status", "pve_node_subscription",
    "pve_node_syslog", "pve_notification_endpoint_list", "pve_overbroad_grants",
    "pve_pool_get", "pve_pools_list", "pve_realm_get",
    "pve_realms_list", "pve_roles_list", "pve_sdn_subnet_list", "pve_sdn_vnets_list",
    "pve_sdn_zones_list", "pve_security_groups_list", "pve_snapshot_list", "pve_storage_config_get",
    "pve_storage_config_list", "pve_storage_content", "pve_storage_status", "pve_task_log",
    "pve_task_status", "pve_task_wait", "pve_tasks_list", "pve_tfa_get", "pve_tfa_list",
    "pve_tokens_list", "pve_user_get", "pve_users_list",
    # qemu-agent plane (Wave 3) — read-only tools (no confirm param)
    "pve_agent_info", "pve_agent_file_read",
    # node-lifecycle (Wave 4) — read-only tools (no confirm param)
    "pve_node_disks_list", "pve_node_disk_smart", "pve_node_storage_backend_list",
    "pve_node_time_get", "pve_node_hosts_get",
    # PMG (Wave 1) — read-only tools (no confirm param)
    "pmg_doctor", "pmg_node_status", "pmg_relay_config", "pmg_domains_list",
    "pmg_statistics_mail", "pmg_quarantine_spam",
    # PMG (Wave 2) — read-only tools (no confirm param)
    "pmg_statistics_domains", "pmg_statistics_virus", "pmg_statistics_spamscores",
    "pmg_statistics_recent", "pmg_quarantine_blocklist_list", "pmg_postfix_qshape",
    "pmg_spam_config", "pmg_service_status",
    # PMG (Wave 3) — read-only tools (no confirm param)
    "pmg_quarantine_welcomelist_list",
    # PMG (Wave 4) — read-only tools (no confirm param)
    "pmg_tracker_list", "pmg_tracker_detail",
    "pmg_quarantine_virus", "pmg_quarantine_attachment",
    "pmg_quarantine_virusstatus", "pmg_quarantine_spamstatus", "pmg_quarantine_spamusers",
    "pmg_statistics_mailcount", "pmg_statistics_sender", "pmg_statistics_receiver",
    "pmg_node_syslog", "pmg_node_rrddata", "pmg_tasks_list",
    # PMG (Wave 5a) — RuleDB read-only tools (no confirm param)
    "pmg_ruledb_rules_list", "pmg_ruledb_rule_get",
    "pmg_ruledb_rule_from_list", "pmg_ruledb_rule_to_list",
    "pmg_ruledb_rule_what_list", "pmg_ruledb_rule_when_list",
    "pmg_ruledb_rule_actions_list",
    "pmg_who_groups_list", "pmg_who_group_get", "pmg_who_group_objects",
    "pmg_what_groups_list", "pmg_what_group_get", "pmg_what_group_objects",
    "pmg_when_groups_list", "pmg_when_group_get", "pmg_when_group_objects",
    "pmg_action_objects_list", "pmg_ruledb_digest",
    # PDM (Proxmox Datacenter Manager) — all read-only tools (no confirm param)
    "pdm_ping", "pdm_version", "pdm_node_status", "pdm_remotes_list",
    "pdm_remote_version", "pdm_remote_config_get",
    "pdm_resources_list", "pdm_resources_status",
    "pdm_pve_resources", "pdm_pve_cluster_status", "pdm_pve_node_list",
    "pdm_pve_qemu_list", "pdm_pve_qemu_config", "pdm_pve_lxc_list", "pdm_pve_lxc_config",
    "pdm_pbs_remote_status", "pdm_pbs_datastores_list", "pdm_pbs_snapshots_list",
    "pdm_tasks_list", "pdm_acl_list", "pdm_roles_list", "pdm_users_list",
})


async def test_every_mutating_tool_is_confirm_gated():
    import inspect
    tools = await server.mcp.list_tools()
    ungated = {
        t.name for t in tools
        if "confirm" not in inspect.signature(getattr(server, t.name)).parameters
    }
    new_ungated = ungated - _READ_ONLY_TOOLS
    assert not new_ungated, (
        "Tool(s) with NO confirm gate that are not in the read-only allowlist. If a tool MUTATES it "
        "MUST take `confirm=` (dry-run-by-default is the trust thesis). If it is genuinely read-only, "
        f"add it to _READ_ONLY_TOOLS:\n  {sorted(new_ungated)}"
    )
    stale = _READ_ONLY_TOOLS - ungated
    assert not stale, (
        "Tool(s) in _READ_ONLY_TOOLS that now HAVE a confirm gate (or were removed). Update the set:\n"
        f"  {sorted(stale)}"
    )
