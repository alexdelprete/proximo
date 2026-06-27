"""Server-level integration for the PMG (Proxmox Mail Gateway) tool group.

Proves the trust gate holds across the PMG wiring, exactly mirroring the PBS wiring
tests in test_server_new_wiring.py:
- reads are audited as non-mutations,
- mutations are dry-run by default (confirm=False => status="plan", _post NOT called),
- a confirm=True call records "planned" BEFORE it executes ("no plan, no mutation"),
- the mutation outcome is "ok" (synchronous) and _post is called exactly once.

Backends are faked; the ledger is real (tmp_path) so PLAN->PROVE is exercised end to end.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig


class _FakeApi:
    """Records the HTTP verbs the PVE tool layer uses; nothing actually executes."""

    def __init__(self):
        self.config = SimpleNamespace(node="pve")
        self.gets: list = []
        self.posts: list = []

    def _get(self, path):
        self.gets.append(path)
        return []

    def _post(self, path, data=None):
        self.posts.append((path, data))
        return None


class _FakePmg:
    """The separate PMG backend — its own verb recorder (params-aware _get).

    config.username mirrors PmgConfig default ("root@pam") — quarantine
    blocklist ops now default pmail to api.config.username when none is
    supplied (PMG 9.1 live-verified: pmail is required for root@pam).

    W3: added _delete and _put recorders so DELETE/PUT wiring tests work
    without AttributeError.
    """

    def __init__(self):
        self.config = SimpleNamespace(node="pmg", username="root@pam")
        self.gets: list = []
        self.posts: list = []
        self.deletes: list = []
        self.puts: list = []

    def _get(self, path, params=None):
        self.gets.append((path, params))
        return {}

    def _post(self, path, data=None):
        self.posts.append((path, data))
        return None

    def _delete(self, path, params=None):
        self.deletes.append((path, params))
        return None

    def _put(self, path, data=None):
        self.puts.append((path, data))
        return None


def _wire(tmp_path, monkeypatch):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log,
    )
    api = _FakeApi()
    pmg = _FakePmg()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, SimpleNamespace(), ledger))
    monkeypatch.setattr(server, "_pmg", lambda: (SimpleNamespace(node="pmg"), pmg))
    return cfg, api, pmg, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# --- Read tools audited as non-mutations ------------------------------------

def test_pmg_relay_config_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    server.pmg_relay_config()
    # PMG 9.1 live-verified: relay config lives at /config/mail (not /config/relay)
    assert pmg.gets and pmg.gets[0][0] == "/config/mail"
    assert any(e["action"] == "pmg_relay_config" and not e["mutation"]
               for e in _entries(log))


def test_pmg_domains_list_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    # Patch _get to return a list so domains_list doesn't return {}
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_domains_list()
    assert any(g[0] == "/config/domains" for g in pmg.gets)
    assert any(e["action"] == "pmg_domains_list" and not e["mutation"]
               for e in _entries(log))


def test_pmg_statistics_mail_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    server.pmg_statistics_mail()
    assert pmg.gets and pmg.gets[0][0] == "/statistics/mail"
    assert any(e["action"] == "pmg_statistics_mail" and not e["mutation"]
               for e in _entries(log))


def test_pmg_quarantine_spam_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_quarantine_spam()
    # PMG 9.1 live-verified: spam quarantine list is at /quarantine/spam (not /quarantine/mails)
    assert any(g[0] == "/quarantine/spam" for g in pmg.gets)
    assert any(e["action"] == "pmg_quarantine_spam" and not e["mutation"]
               for e in _entries(log))


def test_pmg_node_status_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    server.pmg_node_status(node="pmg")
    assert any("/nodes/pmg/status" == g[0] for g in pmg.gets)
    assert any(e["action"] == "pmg_node_status" and not e["mutation"]
               for e in _entries(log))


def test_pmg_doctor_read_calls_two_gets_and_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    # Patch _get to handle both the dict return (version) and list return (users)
    def _fake_get(path, params=None):
        pmg.gets.append((path, params))
        if path == "/version":
            return {"version": "9.1.0"}
        return []  # /access/users returns a list
    pmg._get = _fake_get
    result = server.pmg_doctor(node="pmg")
    # PMG 9.1 live-verified: doctor fetches /version and /access/users
    paths = [g[0] for g in pmg.gets]
    assert "/version" in paths
    assert "/access/users" in paths
    # result is a dict with both keys
    assert "version" in result
    assert "permissions" in result
    assert any(e["action"] == "pmg_doctor" and not e["mutation"] for e in _entries(log))


# --- W2: 8 new read-audited tests -------------------------------------------

def test_pmg_statistics_domains_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_statistics_domains()
    assert any(g[0] == "/statistics/domains" for g in pmg.gets)
    assert any(e["action"] == "pmg_statistics_domains" and not e["mutation"]
               for e in _entries(log))


def test_pmg_statistics_virus_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_statistics_virus()
    assert any(g[0] == "/statistics/virus" for g in pmg.gets)
    assert any(e["action"] == "pmg_statistics_virus" and not e["mutation"]
               for e in _entries(log))


def test_pmg_statistics_spamscores_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_statistics_spamscores()
    assert any(g[0] == "/statistics/spamscores" for g in pmg.gets)
    assert any(e["action"] == "pmg_statistics_spamscores" and not e["mutation"]
               for e in _entries(log))


def test_pmg_statistics_recent_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_statistics_recent(hours=3)
    assert any(g[0] == "/statistics/recent" for g in pmg.gets)
    assert any(e["action"] == "pmg_statistics_recent" and not e["mutation"]
               for e in _entries(log))


def test_pmg_quarantine_blocklist_list_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_quarantine_blocklist_list()
    assert any(g[0] == "/quarantine/blocklist" for g in pmg.gets)
    assert any(e["action"] == "pmg_quarantine_blocklist_list" and not e["mutation"]
               for e in _entries(log))


def test_pmg_postfix_qshape_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    server.pmg_postfix_qshape(node="pmg")
    assert any("/nodes/pmg/postfix/qshape" == g[0] for g in pmg.gets)
    assert any(e["action"] == "pmg_postfix_qshape" and not e["mutation"]
               for e in _entries(log))


def test_pmg_spam_config_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    server.pmg_spam_config()
    assert any("/config/spam" == g[0] for g in pmg.gets)
    assert any(e["action"] == "pmg_spam_config" and not e["mutation"]
               for e in _entries(log))


def test_pmg_service_status_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    server.pmg_service_status(service="postfix", node="pmg")
    assert any("/nodes/pmg/services/postfix/state" == g[0] for g in pmg.gets)
    assert any(e["action"] == "pmg_service_status" and not e["mutation"]
               for e in _entries(log))


# --- W2: 3 new mutation dry-run tests ---------------------------------------

def test_pmg_quarantine_blocklist_add_dry_run_does_not_call_post(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_quarantine_blocklist_add("spam@evil.com")
    assert out["status"] == "plan"
    assert pmg.posts == []
    assert any(e["action"] == "pmg_quarantine_blocklist_add" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_quarantine_action_dry_run_does_not_call_post(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_quarantine_action("deliver", "abc123")
    assert out["status"] == "plan"
    assert out["risk"] == "medium"
    assert pmg.posts == []
    assert any(e["action"] == "pmg_quarantine_action" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_postfix_flush_dry_run_does_not_call_post(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_postfix_flush(node="pmg")
    assert out["status"] == "plan"
    assert out["risk"] == "low"
    assert pmg.posts == []
    assert any(e["action"] == "pmg_postfix_flush" and e["outcome"] == "planned"
               for e in _entries(log))


# --- W2: 3 new mutation confirm tests ---------------------------------------

def test_pmg_quarantine_blocklist_add_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_quarantine_blocklist_add("spam@evil.com", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    assert pmg.posts[0][0] == "/quarantine/blocklist"
    assert pmg.posts[0][1].get("address") == "spam@evil.com"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_quarantine_blocklist_add"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_quarantine_action_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_quarantine_action("mark-seen", "abc123", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    assert pmg.posts[0][0] == "/quarantine/content"
    assert pmg.posts[0][1].get("action") == "mark-seen"
    assert pmg.posts[0][1].get("id") == "abc123"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_quarantine_action"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_postfix_flush_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_postfix_flush(node="pmg", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    assert pmg.posts[0][0] == "/nodes/pmg/postfix/flush_queues"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_postfix_flush"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


# --- MCP surface: PMG tools are exposed -------------------------------------

async def test_pmg_tools_registered_with_fastmcp():
    tools = {t.name for t in await server.mcp.list_tools()}
    pmg_tools = {
        "pmg_doctor",
        "pmg_node_status",
        "pmg_relay_config",
        "pmg_domains_list",
        "pmg_statistics_mail",
        "pmg_quarantine_spam",
        # W2 reads
        "pmg_statistics_domains",
        "pmg_statistics_virus",
        "pmg_statistics_spamscores",
        "pmg_statistics_recent",
        "pmg_quarantine_blocklist_list",
        "pmg_postfix_qshape",
        "pmg_spam_config",
        "pmg_service_status",
        # W2 mutations
        "pmg_quarantine_blocklist_add",
        "pmg_quarantine_action",
        "pmg_postfix_flush",
        # W3 reads
        "pmg_quarantine_welcomelist_list",
        # W3 mutations
        "pmg_domain_create",
        "pmg_domain_delete",
        "pmg_transport_create",
        "pmg_transport_delete",
        "pmg_mynetworks_add",
        "pmg_mynetworks_remove",
        "pmg_spam_config_update",
        "pmg_quarantine_welcomelist_add",
        "pmg_quarantine_welcomelist_remove",
        "pmg_quarantine_blocklist_remove",
        "pmg_service_control",
        # W4 reads
        "pmg_tracker_list",
        "pmg_tracker_detail",
        "pmg_quarantine_virus",
        "pmg_quarantine_attachment",
        "pmg_quarantine_virusstatus",
        "pmg_quarantine_spamstatus",
        "pmg_quarantine_spamusers",
        "pmg_statistics_mailcount",
        "pmg_statistics_sender",
        "pmg_statistics_receiver",
        "pmg_node_syslog",
        "pmg_node_rrddata",
        "pmg_tasks_list",
        # W4 mutations
        "pmg_backup_create",
        # W5a reads (RuleDB)
        "pmg_ruledb_rules_list",
        "pmg_ruledb_rule_get",
        "pmg_ruledb_rule_from_list",
        "pmg_ruledb_rule_to_list",
        "pmg_ruledb_rule_what_list",
        "pmg_ruledb_rule_when_list",
        "pmg_ruledb_rule_actions_list",
        "pmg_who_groups_list",
        "pmg_who_group_get",
        "pmg_who_group_objects",
        "pmg_what_groups_list",
        "pmg_what_group_get",
        "pmg_what_group_objects",
        "pmg_when_groups_list",
        "pmg_when_group_get",
        "pmg_when_group_objects",
        "pmg_action_objects_list",
        "pmg_ruledb_digest",
        # W5b mutations (object-group CRUD + who-object CRUD)
        "pmg_who_group_create",
        "pmg_who_group_update",
        "pmg_who_group_delete",
        "pmg_what_group_create",
        "pmg_what_group_update",
        "pmg_what_group_delete",
        "pmg_when_group_create",
        "pmg_when_group_update",
        "pmg_when_group_delete",
        "pmg_who_object_add",
        "pmg_who_object_update",
        "pmg_who_object_delete",
        # W5c mutations (WHAT-object / WHEN-object / ACTION CRUD)
        "pmg_what_object_add",
        "pmg_what_object_update",
        "pmg_what_object_delete",
        "pmg_when_object_add",
        "pmg_when_object_update",
        "pmg_when_object_delete",
        "pmg_action_bcc_create",
        "pmg_action_bcc_update",
        "pmg_action_field_create",
        "pmg_action_field_update",
        "pmg_action_notification_create",
        "pmg_action_notification_update",
        "pmg_action_disclaimer_create",
        "pmg_action_disclaimer_update",
        "pmg_action_removeattachments_create",
        "pmg_action_removeattachments_update",
        "pmg_action_delete",
        # W5d mutations (rule CRUD + rule↔group attach/detach)
        "pmg_ruledb_rule_create",
        "pmg_ruledb_rule_update",
        "pmg_ruledb_rule_delete",
        "pmg_ruledb_rule_from_attach",
        "pmg_ruledb_rule_from_detach",
        "pmg_ruledb_rule_to_attach",
        "pmg_ruledb_rule_to_detach",
        "pmg_ruledb_rule_what_attach",
        "pmg_ruledb_rule_what_detach",
        "pmg_ruledb_rule_when_attach",
        "pmg_ruledb_rule_when_detach",
        "pmg_ruledb_rule_action_attach",
        "pmg_ruledb_rule_action_detach",
    }
    assert pmg_tools <= tools, f"missing from MCP surface: {pmg_tools - tools}"
    assert len(pmg_tools) == 103


# --- W3: read tool audited as non-mutation ----------------------------------

def test_pmg_quarantine_welcomelist_list_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_quarantine_welcomelist_list()
    assert any(g[0] == "/quarantine/welcomelist" for g in pmg.gets)
    assert any(e["action"] == "pmg_quarantine_welcomelist_list" and not e["mutation"]
               for e in _entries(log))


# --- W3: mutation dry-runs (confirm=False) never call _post/_put/_delete ----

def test_pmg_domain_create_dry_run_does_not_call_post(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_domain_create("example.com")
    assert out["status"] == "plan"
    assert pmg.posts == []
    assert any(e["action"] == "pmg_domain_create" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_domain_delete_dry_run_does_not_call_delete(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_domain_delete("example.com")
    assert out["status"] == "plan"
    assert pmg.deletes == []
    assert any(e["action"] == "pmg_domain_delete" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_transport_create_dry_run_does_not_call_post(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_transport_create("example.com", "relay.example.com")
    assert out["status"] == "plan"
    assert pmg.posts == []
    assert any(e["action"] == "pmg_transport_create" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_transport_delete_dry_run_does_not_call_delete(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_transport_delete("example.com")
    assert out["status"] == "plan"
    assert pmg.deletes == []
    assert any(e["action"] == "pmg_transport_delete" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_mynetworks_add_dry_run_does_not_call_post(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_mynetworks_add("10.0.0.0/8")
    assert out["status"] == "plan"
    assert pmg.posts == []
    assert any(e["action"] == "pmg_mynetworks_add" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_mynetworks_remove_dry_run_does_not_call_delete(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_mynetworks_remove("10.0.0.0/8")
    assert out["status"] == "plan"
    assert pmg.deletes == []
    assert any(e["action"] == "pmg_mynetworks_remove" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_spam_config_update_dry_run_does_not_call_put(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_spam_config_update(bounce_score=5)
    assert out["status"] == "plan"
    assert pmg.puts == []
    assert any(e["action"] == "pmg_spam_config_update" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_quarantine_welcomelist_add_dry_run_does_not_call_post(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_quarantine_welcomelist_add("good@example.com")
    assert out["status"] == "plan"
    assert pmg.posts == []
    assert any(e["action"] == "pmg_quarantine_welcomelist_add" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_quarantine_welcomelist_remove_dry_run_does_not_call_delete(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_quarantine_welcomelist_remove("good@example.com")
    assert out["status"] == "plan"
    assert pmg.deletes == []
    assert any(e["action"] == "pmg_quarantine_welcomelist_remove" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_quarantine_blocklist_remove_dry_run_does_not_call_delete(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_quarantine_blocklist_remove("spam@evil.com")
    assert out["status"] == "plan"
    assert pmg.deletes == []
    assert any(e["action"] == "pmg_quarantine_blocklist_remove" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_service_control_dry_run_does_not_call_post(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_service_control("postfix", "restart")
    assert out["status"] == "plan"
    assert out["risk"] == "medium"
    assert pmg.posts == []
    assert any(e["action"] == "pmg_service_control" and e["outcome"] == "planned"
               for e in _entries(log))


# --- W3: mutation confirm (confirm=True) records planned then ok -------------

def test_pmg_domain_create_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_domain_create("example.com", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    assert pmg.posts[0][0] == "/config/domains"
    assert pmg.posts[0][1].get("domain") == "example.com"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_domain_create"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_domain_delete_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_domain_delete("example.com", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.deletes) == 1
    assert "/config/domains/example.com" in pmg.deletes[0][0]
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_domain_delete"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_transport_create_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_transport_create("example.com", "relay.example.com", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    assert pmg.posts[0][0] == "/config/transport"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_transport_create"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_transport_delete_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_transport_delete("example.com", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.deletes) == 1
    assert "/config/transport/example.com" in pmg.deletes[0][0]
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_transport_delete"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_mynetworks_add_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_mynetworks_add("10.0.0.0/8", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    assert pmg.posts[0][0] == "/config/mynetworks"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_mynetworks_add"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_mynetworks_remove_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_mynetworks_remove("10.0.0.0/8", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.deletes) == 1
    # CIDR is URL-encoded: / → %2F
    assert "10.0.0.0%2F8" in pmg.deletes[0][0]
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_mynetworks_remove"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_spam_config_update_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_spam_config_update(bounce_score=5, confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.puts) == 1
    assert pmg.puts[0][0] == "/config/spam"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_spam_config_update"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_quarantine_welcomelist_add_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_quarantine_welcomelist_add("good@example.com", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    assert pmg.posts[0][0] == "/quarantine/welcomelist"
    assert pmg.posts[0][1].get("address") == "good@example.com"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_quarantine_welcomelist_add"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_quarantine_welcomelist_remove_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_quarantine_welcomelist_remove("good@example.com", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.deletes) == 1
    assert pmg.deletes[0][0] == "/quarantine/welcomelist"
    assert pmg.deletes[0][1].get("address") == "good@example.com"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_quarantine_welcomelist_remove"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_quarantine_blocklist_remove_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_quarantine_blocklist_remove("spam@evil.com", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.deletes) == 1
    assert pmg.deletes[0][0] == "/quarantine/blocklist"
    assert pmg.deletes[0][1].get("address") == "spam@evil.com"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_quarantine_blocklist_remove"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_service_control_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_service_control("postfix", "restart", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    posted_path = pmg.posts[0][0]
    assert "postfix" in posted_path
    assert "restart" in posted_path
    assert "/nodes/" in posted_path
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_service_control"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


# --- W4: 13 new read-audited tests ------------------------------------------

def test_pmg_tracker_list_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_tracker_list(node="pmg")
    assert any(g[0] == "/nodes/pmg/tracker" for g in pmg.gets)
    assert any(e["action"] == "pmg_tracker_list" and not e["mutation"]
               for e in _entries(log))


def test_pmg_tracker_detail_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_tracker_detail("msg-abc123", node="pmg")
    assert any("msg-abc123" in g[0] for g in pmg.gets)
    assert any(e["action"] == "pmg_tracker_detail" and not e["mutation"]
               for e in _entries(log))


def test_pmg_quarantine_virus_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_quarantine_virus()
    assert any(g[0] == "/quarantine/virus" for g in pmg.gets)
    assert any(e["action"] == "pmg_quarantine_virus" and not e["mutation"]
               for e in _entries(log))


def test_pmg_quarantine_attachment_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_quarantine_attachment()
    assert any(g[0] == "/quarantine/attachment" for g in pmg.gets)
    assert any(e["action"] == "pmg_quarantine_attachment" and not e["mutation"]
               for e in _entries(log))


def test_pmg_quarantine_virusstatus_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_quarantine_virusstatus()
    assert any(g[0] == "/quarantine/virusstatus" for g in pmg.gets)
    assert any(e["action"] == "pmg_quarantine_virusstatus" and not e["mutation"]
               for e in _entries(log))


def test_pmg_quarantine_spamstatus_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_quarantine_spamstatus()
    assert any(g[0] == "/quarantine/spamstatus" for g in pmg.gets)
    assert any(e["action"] == "pmg_quarantine_spamstatus" and not e["mutation"]
               for e in _entries(log))


def test_pmg_quarantine_spamusers_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_quarantine_spamusers()
    assert any(g[0] == "/quarantine/spamusers" for g in pmg.gets)
    assert any(e["action"] == "pmg_quarantine_spamusers" and not e["mutation"]
               for e in _entries(log))


def test_pmg_statistics_mailcount_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_statistics_mailcount()
    assert any(g[0] == "/statistics/mailcount" for g in pmg.gets)
    assert any(e["action"] == "pmg_statistics_mailcount" and not e["mutation"]
               for e in _entries(log))


def test_pmg_statistics_sender_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_statistics_sender()
    assert any(g[0] == "/statistics/sender" for g in pmg.gets)
    assert any(e["action"] == "pmg_statistics_sender" and not e["mutation"]
               for e in _entries(log))


def test_pmg_statistics_receiver_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_statistics_receiver()
    assert any(g[0] == "/statistics/receiver" for g in pmg.gets)
    assert any(e["action"] == "pmg_statistics_receiver" and not e["mutation"]
               for e in _entries(log))


def test_pmg_node_syslog_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_node_syslog(node="pmg")
    assert any("/nodes/pmg/syslog" == g[0] for g in pmg.gets)
    assert any(e["action"] == "pmg_node_syslog" and not e["mutation"]
               for e in _entries(log))


def test_pmg_node_rrddata_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_node_rrddata(timeframe="day", node="pmg")
    assert any("/nodes/pmg/rrddata" == g[0] for g in pmg.gets)
    assert any(e["action"] == "pmg_node_rrddata" and not e["mutation"]
               for e in _entries(log))


def test_pmg_tasks_list_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_tasks_list(node="pmg")
    assert any("/nodes/pmg/tasks" == g[0] for g in pmg.gets)
    assert any(e["action"] == "pmg_tasks_list" and not e["mutation"]
               for e in _entries(log))


# --- W4: backup_create mutation (dry-run + confirm) -------------------------

def test_pmg_backup_create_dry_run_does_not_call_post(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_backup_create(node="pmg")
    assert out["status"] == "plan"
    assert out["risk"] == "low"
    assert pmg.posts == []
    assert any(e["action"] == "pmg_backup_create" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_backup_create_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_backup_create(node="pmg", notify="never", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    assert pmg.posts[0][0] == "/nodes/pmg/backup"
    assert pmg.posts[0][1].get("notify") == "never"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_backup_create"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


# --- W5a: 18 new RuleDB read-audited tests -----------------------------------

def test_pmg_ruledb_rules_list_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_ruledb_rules_list()
    assert any(g[0] == "/config/ruledb/rules" for g in pmg.gets)
    assert any(e["action"] == "pmg_ruledb_rules_list" and not e["mutation"]
               for e in _entries(log))


def test_pmg_ruledb_rule_get_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    server.pmg_ruledb_rule_get("100")
    assert any("/config/ruledb/rules/100/config" == g[0] for g in pmg.gets)
    assert any(e["action"] == "pmg_ruledb_rule_get" and not e["mutation"]
               for e in _entries(log))


def test_pmg_ruledb_rule_from_list_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_ruledb_rule_from_list("100")
    assert any(g[0] == "/config/ruledb/rules/100/from" for g in pmg.gets)
    assert any(e["action"] == "pmg_ruledb_rule_from_list" and not e["mutation"]
               for e in _entries(log))


def test_pmg_ruledb_rule_to_list_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_ruledb_rule_to_list("100")
    assert any(g[0] == "/config/ruledb/rules/100/to" for g in pmg.gets)
    assert any(e["action"] == "pmg_ruledb_rule_to_list" and not e["mutation"]
               for e in _entries(log))


def test_pmg_ruledb_rule_what_list_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_ruledb_rule_what_list("100")
    assert any(g[0] == "/config/ruledb/rules/100/what" for g in pmg.gets)
    assert any(e["action"] == "pmg_ruledb_rule_what_list" and not e["mutation"]
               for e in _entries(log))


def test_pmg_ruledb_rule_when_list_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_ruledb_rule_when_list("100")
    assert any(g[0] == "/config/ruledb/rules/100/when" for g in pmg.gets)
    assert any(e["action"] == "pmg_ruledb_rule_when_list" and not e["mutation"]
               for e in _entries(log))


def test_pmg_ruledb_rule_actions_list_read_is_audited(tmp_path, monkeypatch):
    # PMG 9.1 live-verified: /rules/{id}/actions returns 501; actions extracted
    # from /rules/{id}/config instead.
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or {}
    )
    server.pmg_ruledb_rule_actions_list("100")
    assert any(g[0] == "/config/ruledb/rules/100/config" for g in pmg.gets)
    assert any(e["action"] == "pmg_ruledb_rule_actions_list" and not e["mutation"]
               for e in _entries(log))


def test_pmg_who_groups_list_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_who_groups_list()
    assert any(g[0] == "/config/ruledb/who" for g in pmg.gets)
    assert any(e["action"] == "pmg_who_groups_list" and not e["mutation"]
               for e in _entries(log))


def test_pmg_who_group_get_read_is_audited(tmp_path, monkeypatch):
    # PMG 9.1 live-verified: ogroup must be a numeric ID ('2'), not a name.
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    server.pmg_who_group_get("2")
    assert any("/config/ruledb/who/2/config" == g[0] for g in pmg.gets)
    assert any(e["action"] == "pmg_who_group_get" and not e["mutation"]
               for e in _entries(log))


def test_pmg_who_group_objects_read_is_audited(tmp_path, monkeypatch):
    # PMG 9.1 live-verified: ogroup must be a numeric ID ('2'), not a name.
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_who_group_objects("2")
    assert any(g[0] == "/config/ruledb/who/2/objects" for g in pmg.gets)
    assert any(e["action"] == "pmg_who_group_objects" and not e["mutation"]
               for e in _entries(log))


def test_pmg_what_groups_list_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_what_groups_list()
    assert any(g[0] == "/config/ruledb/what" for g in pmg.gets)
    assert any(e["action"] == "pmg_what_groups_list" and not e["mutation"]
               for e in _entries(log))


def test_pmg_what_group_get_read_is_audited(tmp_path, monkeypatch):
    # PMG 9.1 live-verified: ogroup must be a numeric ID ('8'), not a name.
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    server.pmg_what_group_get("8")
    assert any("/config/ruledb/what/8/config" == g[0] for g in pmg.gets)
    assert any(e["action"] == "pmg_what_group_get" and not e["mutation"]
               for e in _entries(log))


def test_pmg_what_group_objects_read_is_audited(tmp_path, monkeypatch):
    # PMG 9.1 live-verified: ogroup must be a numeric ID ('8'), not a name.
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_what_group_objects("8")
    assert any(g[0] == "/config/ruledb/what/8/objects" for g in pmg.gets)
    assert any(e["action"] == "pmg_what_group_objects" and not e["mutation"]
               for e in _entries(log))


def test_pmg_when_groups_list_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_when_groups_list()
    assert any(g[0] == "/config/ruledb/when" for g in pmg.gets)
    assert any(e["action"] == "pmg_when_groups_list" and not e["mutation"]
               for e in _entries(log))


def test_pmg_when_group_get_read_is_audited(tmp_path, monkeypatch):
    # PMG 9.1 live-verified: ogroup must be a numeric ID ('4'), not a name.
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    server.pmg_when_group_get("4")
    assert any("/config/ruledb/when/4/config" == g[0] for g in pmg.gets)
    assert any(e["action"] == "pmg_when_group_get" and not e["mutation"]
               for e in _entries(log))


def test_pmg_when_group_objects_read_is_audited(tmp_path, monkeypatch):
    # PMG 9.1 live-verified: ogroup must be a numeric ID ('4'), not a name.
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_when_group_objects("4")
    assert any(g[0] == "/config/ruledb/when/4/objects" for g in pmg.gets)
    assert any(e["action"] == "pmg_when_group_objects" and not e["mutation"]
               for e in _entries(log))


def test_pmg_action_objects_list_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    pmg._get = lambda path, params=None: (
        pmg.gets.append((path, params)) or []
    )
    server.pmg_action_objects_list()
    assert any(g[0] == "/config/ruledb/action/objects" for g in pmg.gets)
    assert any(e["action"] == "pmg_action_objects_list" and not e["mutation"]
               for e in _entries(log))


def test_pmg_ruledb_digest_read_is_audited(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    server.pmg_ruledb_digest()
    assert any("/config/ruledb/digest" == g[0] for g in pmg.gets)
    assert any(e["action"] == "pmg_ruledb_digest" and not e["mutation"]
               for e in _entries(log))


# --- W5b: 24 mutation wiring tests (dry-run + confirm × 12 tools) -----------

def test_pmg_who_group_create_dry_run_does_not_call_post(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_who_group_create("MyGroup")
    assert out["status"] == "plan"
    assert pmg.posts == []
    assert any(e["action"] == "pmg_who_group_create" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_who_group_create_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_who_group_create("MyGroup", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    assert pmg.posts[0][0] == "/config/ruledb/who"
    assert pmg.posts[0][1].get("name") == "MyGroup"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_who_group_create"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_who_group_update_dry_run_does_not_call_put(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_who_group_update("2", name="Renamed")
    assert out["status"] == "plan"
    assert pmg.puts == []
    assert any(e["action"] == "pmg_who_group_update" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_who_group_update_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_who_group_update("2", name="Renamed", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.puts) == 1
    assert pmg.puts[0][0] == "/config/ruledb/who/2/config"
    assert pmg.puts[0][1].get("name") == "Renamed"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_who_group_update"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_who_group_delete_dry_run_does_not_call_delete(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_who_group_delete("2")
    assert out["status"] == "plan"
    assert pmg.deletes == []
    assert any(e["action"] == "pmg_who_group_delete" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_who_group_delete_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_who_group_delete("2", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.deletes) == 1
    assert pmg.deletes[0][0] == "/config/ruledb/who/2"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_who_group_delete"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_what_group_create_dry_run_does_not_call_post(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_what_group_create("ContentGroup")
    assert out["status"] == "plan"
    assert pmg.posts == []
    assert any(e["action"] == "pmg_what_group_create" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_what_group_create_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_what_group_create("ContentGroup", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    assert pmg.posts[0][0] == "/config/ruledb/what"
    assert pmg.posts[0][1].get("name") == "ContentGroup"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_what_group_create"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_what_group_update_dry_run_does_not_call_put(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_what_group_update("8", name="Renamed")
    assert out["status"] == "plan"
    assert pmg.puts == []
    assert any(e["action"] == "pmg_what_group_update" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_what_group_update_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_what_group_update("8", name="Renamed", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.puts) == 1
    assert pmg.puts[0][0] == "/config/ruledb/what/8/config"
    assert pmg.puts[0][1].get("name") == "Renamed"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_what_group_update"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_what_group_delete_dry_run_does_not_call_delete(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_what_group_delete("8")
    assert out["status"] == "plan"
    assert pmg.deletes == []
    assert any(e["action"] == "pmg_what_group_delete" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_what_group_delete_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_what_group_delete("8", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.deletes) == 1
    assert pmg.deletes[0][0] == "/config/ruledb/what/8"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_what_group_delete"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_when_group_create_dry_run_does_not_call_post(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_when_group_create("OfficeHours")
    assert out["status"] == "plan"
    assert pmg.posts == []
    assert any(e["action"] == "pmg_when_group_create" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_when_group_create_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_when_group_create("OfficeHours", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    assert pmg.posts[0][0] == "/config/ruledb/when"
    assert pmg.posts[0][1].get("name") == "OfficeHours"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_when_group_create"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_when_group_update_dry_run_does_not_call_put(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_when_group_update("4", name="BusinessHours")
    assert out["status"] == "plan"
    assert pmg.puts == []
    assert any(e["action"] == "pmg_when_group_update" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_when_group_update_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_when_group_update("4", name="BusinessHours", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.puts) == 1
    assert pmg.puts[0][0] == "/config/ruledb/when/4/config"
    assert pmg.puts[0][1].get("name") == "BusinessHours"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_when_group_update"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_when_group_delete_dry_run_does_not_call_delete(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_when_group_delete("4")
    assert out["status"] == "plan"
    assert pmg.deletes == []
    assert any(e["action"] == "pmg_when_group_delete" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_when_group_delete_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_when_group_delete("4", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.deletes) == 1
    assert pmg.deletes[0][0] == "/config/ruledb/when/4"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_when_group_delete"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_who_object_add_dry_run_does_not_call_post(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_who_object_add("2", "email", email="bad@evil.com")
    assert out["status"] == "plan"
    assert pmg.posts == []
    assert any(e["action"] == "pmg_who_object_add" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_who_object_add_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_who_object_add("2", "email", email="bad@evil.com", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    assert pmg.posts[0][0] == "/config/ruledb/who/2/email"
    assert pmg.posts[0][1].get("email") == "bad@evil.com"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_who_object_add"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_who_object_update_dry_run_does_not_call_put(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_who_object_update("2", "email", "5", email="new@evil.com")
    assert out["status"] == "plan"
    assert pmg.puts == []
    assert any(e["action"] == "pmg_who_object_update" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_who_object_update_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_who_object_update("2", "email", "5", email="new@evil.com", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.puts) == 1
    assert pmg.puts[0][0] == "/config/ruledb/who/2/email/5"
    assert pmg.puts[0][1].get("email") == "new@evil.com"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_who_object_update"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_who_object_delete_dry_run_does_not_call_delete(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_who_object_delete("2", "5")
    assert out["status"] == "plan"
    assert pmg.deletes == []
    assert any(e["action"] == "pmg_who_object_delete" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_who_object_delete_confirm_records_planned_then_ok(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_who_object_delete("2", "5", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.deletes) == 1
    assert pmg.deletes[0][0] == "/config/ruledb/who/2/objects/5"
    outcomes = [e["outcome"] for e in _entries(log)
                if e["action"] == "pmg_who_object_delete"]
    assert "planned" in outcomes
    assert "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


# --- W5c: WHAT-object CRUD wiring ------------------------------------------

def test_pmg_what_object_add_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_what_object_add("8", "filenamefilter", filename="*.exe")
    assert out["status"] == "plan"
    assert pmg.posts == []
    assert any(e["action"] == "pmg_what_object_add" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_what_object_add_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_what_object_add("8", "filenamefilter", filename="*.exe", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    assert pmg.posts[0][0] == "/config/ruledb/what/8/filenamefilter"
    assert pmg.posts[0][1].get("filename") == "*.exe"
    outcomes = [e["outcome"] for e in _entries(log) if e["action"] == "pmg_what_object_add"]
    assert "planned" in outcomes and "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


def test_pmg_what_object_update_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_what_object_update("8", "contenttype", "5", contenttype="text/plain")
    assert out["status"] == "plan"
    assert pmg.puts == []


def test_pmg_what_object_update_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_what_object_update("8", "contenttype", "5",
                                         contenttype="text/plain", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.puts) == 1
    assert pmg.puts[0][0] == "/config/ruledb/what/8/contenttype/5"
    assert pmg.puts[0][1].get("contenttype") == "text/plain"


def test_pmg_what_object_delete_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_what_object_delete("8", "5")
    assert out["status"] == "plan"
    assert pmg.deletes == []


def test_pmg_what_object_delete_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_what_object_delete("8", "5", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.deletes) == 1
    assert pmg.deletes[0][0] == "/config/ruledb/what/8/objects/5"


# --- W5c: WHEN-object CRUD wiring ------------------------------------------

def test_pmg_when_object_add_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_when_object_add("4", "08:00", "17:00")
    assert out["status"] == "plan"
    assert pmg.posts == []


def test_pmg_when_object_add_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_when_object_add("4", "08:00", "17:00", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    assert pmg.posts[0][0] == "/config/ruledb/when/4/timeframe"
    assert pmg.posts[0][1].get("start") == "08:00"
    assert pmg.posts[0][1].get("end") == "17:00"


def test_pmg_when_object_update_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_when_object_update("4", "7", start="09:00", end="17:00")
    assert out["status"] == "plan"
    assert pmg.puts == []


def test_pmg_when_object_update_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    # Both start and end are required — PMG 9.1 timeframe PUT rejects partial updates.
    out = server.pmg_when_object_update("4", "7", start="09:00", end="17:00", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.puts) == 1
    assert pmg.puts[0][0] == "/config/ruledb/when/4/timeframe/7"
    assert pmg.puts[0][1].get("start") == "09:00"
    assert pmg.puts[0][1].get("end") == "17:00"


def test_pmg_when_object_delete_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_when_object_delete("4", "7")
    assert out["status"] == "plan"
    assert pmg.deletes == []


def test_pmg_when_object_delete_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_when_object_delete("4", "7", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.deletes) == 1
    assert pmg.deletes[0][0] == "/config/ruledb/when/4/objects/7"


# --- W5c: ACTION CRUD wiring -----------------------------------------------

def test_pmg_action_bcc_create_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_action_bcc_create("copy-admin", "admin@example.com")
    assert out["status"] == "plan"
    assert pmg.posts == []


def test_pmg_action_bcc_create_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_action_bcc_create("copy-admin", "admin@example.com", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    assert pmg.posts[0][0] == "/config/ruledb/action/bcc"
    assert pmg.posts[0][1].get("name") == "copy-admin"
    assert pmg.posts[0][1].get("target") == "admin@example.com"


def test_pmg_action_bcc_update_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_action_bcc_update("13_26", target="new@example.com")
    assert out["status"] == "plan"
    assert pmg.puts == []


def test_pmg_action_bcc_update_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_action_bcc_update("13_26", target="new@example.com", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.puts) == 1
    assert pmg.puts[0][0] == "/config/ruledb/action/bcc/13_26"
    assert pmg.puts[0][1].get("target") == "new@example.com"


def test_pmg_action_field_create_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_action_field_create("add-tag", "X-Spam", "yes")
    assert out["status"] == "plan"
    assert pmg.posts == []


def test_pmg_action_field_create_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_action_field_create("add-tag", "X-Spam", "yes", confirm=True)
    assert out["status"] == "ok"
    assert pmg.posts[0][0] == "/config/ruledb/action/field"
    assert pmg.posts[0][1].get("field") == "X-Spam"
    assert pmg.posts[0][1].get("value") == "yes"


def test_pmg_action_field_update_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_action_field_update("5_10", "tag", "X-Spam", "no")
    assert out["status"] == "plan"
    assert pmg.puts == []


def test_pmg_action_field_update_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    # name+field+value all required — PMG 9.1 field action PUT rejects partial updates.
    out = server.pmg_action_field_update("5_10", "tag", "X-Spam", "no", confirm=True)
    assert out["status"] == "ok"
    assert pmg.puts[0][0] == "/config/ruledb/action/field/5_10"
    assert pmg.puts[0][1].get("name") == "tag"
    assert pmg.puts[0][1].get("field") == "X-Spam"
    assert pmg.puts[0][1].get("value") == "no"


def test_pmg_action_notification_create_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_action_notification_create(
        "notify-admin", "admin@example.com", "Alert", "Mail matched.")
    assert out["status"] == "plan"
    assert pmg.posts == []


def test_pmg_action_notification_create_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_action_notification_create(
        "notify-admin", "admin@example.com", "Alert", "Mail matched.", confirm=True)
    assert out["status"] == "ok"
    assert pmg.posts[0][0] == "/config/ruledb/action/notification"
    assert pmg.posts[0][1].get("to") == "admin@example.com"
    assert pmg.posts[0][1].get("body") == "Mail matched."


def test_pmg_action_notification_update_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_action_notification_update(
        "7_14", "n", "a@a.com", "New subject", "b"
    )
    assert out["status"] == "plan"
    assert pmg.puts == []


def test_pmg_action_notification_update_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    # name+to+subject+body_text all required — PMG 9.1 notification PUT rejects partial updates.
    out = server.pmg_action_notification_update(
        "7_14", "n", "a@a.com", "New subject", "b", confirm=True
    )
    assert out["status"] == "ok"
    assert pmg.puts[0][0] == "/config/ruledb/action/notification/7_14"
    assert pmg.puts[0][1].get("subject") == "New subject"
    assert pmg.puts[0][1].get("body") == "b"


def test_pmg_action_disclaimer_create_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_action_disclaimer_create("footer", "Confidential")
    assert out["status"] == "plan"
    assert pmg.posts == []


def test_pmg_action_disclaimer_create_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_action_disclaimer_create("footer", "Confidential",
                                               add_separator=True, confirm=True)
    assert out["status"] == "ok"
    assert pmg.posts[0][0] == "/config/ruledb/action/disclaimer"
    assert pmg.posts[0][1].get("disclaimer") == "Confidential"
    assert pmg.posts[0][1].get("add-separator") is True


def test_pmg_action_disclaimer_update_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_action_disclaimer_update("2_9", disclaimer="New text")
    assert out["status"] == "plan"
    assert pmg.puts == []


def test_pmg_action_disclaimer_update_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_action_disclaimer_update("2_9", disclaimer="New text", confirm=True)
    assert out["status"] == "ok"
    assert pmg.puts[0][0] == "/config/ruledb/action/disclaimer/2_9"
    assert pmg.puts[0][1].get("disclaimer") == "New text"


def test_pmg_action_removeattachments_create_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_action_removeattachments_create("strip-attach", "[removed]")
    assert out["status"] == "plan"
    assert pmg.posts == []


def test_pmg_action_removeattachments_create_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_action_removeattachments_create(
        "strip-attach", "[removed]", all_=True, confirm=True)
    assert out["status"] == "ok"
    assert pmg.posts[0][0] == "/config/ruledb/action/removeattachments"
    assert pmg.posts[0][1].get("text") == "[removed]"
    assert pmg.posts[0][1].get("all") is True


def test_pmg_action_removeattachments_update_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_action_removeattachments_update("3_5", text="[stripped]")
    assert out["status"] == "plan"
    assert pmg.puts == []


def test_pmg_action_removeattachments_update_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_action_removeattachments_update(
        "3_5", text="[stripped]", confirm=True)
    assert out["status"] == "ok"
    assert pmg.puts[0][0] == "/config/ruledb/action/removeattachments/3_5"
    assert pmg.puts[0][1].get("text") == "[stripped]"


def test_pmg_action_delete_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_action_delete("13_26")
    assert out["status"] == "plan"
    assert pmg.deletes == []
    assert any(e["action"] == "pmg_action_delete" and e["outcome"] == "planned"
               for e in _entries(log))


def test_pmg_action_delete_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_action_delete("13_26", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.deletes) == 1
    assert pmg.deletes[0][0] == "/config/ruledb/action/objects/13_26"
    outcomes = [e["outcome"] for e in _entries(log) if e["action"] == "pmg_action_delete"]
    assert "planned" in outcomes and "ok" in outcomes
    assert outcomes.index("planned") < outcomes.index("ok")


# --- W5d: rule CRUD wiring --------------------------------------------------

def test_pmg_ruledb_rule_create_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_create("my-rule", 50)
    assert out["status"] == "plan"
    assert pmg.posts == []


def test_pmg_ruledb_rule_create_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_create("my-rule", 50, active=False, confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    assert pmg.posts[0][0] == "/config/ruledb/rules"
    assert pmg.posts[0][1].get("name") == "my-rule"
    assert pmg.posts[0][1].get("priority") == 50
    # active defaults False — must be present in body
    assert pmg.posts[0][1].get("active") is False


def test_pmg_ruledb_rule_update_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_update("100", name="renamed")
    assert out["status"] == "plan"
    assert pmg.puts == []


def test_pmg_ruledb_rule_update_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_update("100", name="renamed", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.puts) == 1
    assert pmg.puts[0][0] == "/config/ruledb/rules/100/config"
    assert pmg.puts[0][1].get("name") == "renamed"


def test_pmg_ruledb_rule_delete_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_delete("100")
    assert out["status"] == "plan"
    assert pmg.deletes == []


def test_pmg_ruledb_rule_delete_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_delete("100", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.deletes) == 1
    assert pmg.deletes[0][0] == "/config/ruledb/rules/100"


# --- W5d: attach/detach wiring ----------------------------------------------

def test_pmg_ruledb_rule_from_attach_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_from_attach("100", "2")
    assert out["status"] == "plan"
    assert pmg.posts == []


def test_pmg_ruledb_rule_from_attach_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_from_attach("100", "2", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    assert pmg.posts[0][0] == "/config/ruledb/rules/100/from"
    assert pmg.posts[0][1].get("ogroup") == "2"


def test_pmg_ruledb_rule_from_detach_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_from_detach("100", "2")
    assert out["status"] == "plan"
    assert pmg.deletes == []


def test_pmg_ruledb_rule_from_detach_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_from_detach("100", "2", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.deletes) == 1
    assert pmg.deletes[0][0] == "/config/ruledb/rules/100/from/2"


def test_pmg_ruledb_rule_to_attach_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_to_attach("100", "3")
    assert out["status"] == "plan"
    assert pmg.posts == []


def test_pmg_ruledb_rule_to_attach_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_to_attach("100", "3", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    assert pmg.posts[0][0] == "/config/ruledb/rules/100/to"
    assert pmg.posts[0][1].get("ogroup") == "3"


def test_pmg_ruledb_rule_to_detach_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_to_detach("100", "3")
    assert out["status"] == "plan"
    assert pmg.deletes == []


def test_pmg_ruledb_rule_to_detach_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_to_detach("100", "3", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.deletes) == 1
    assert pmg.deletes[0][0] == "/config/ruledb/rules/100/to/3"


def test_pmg_ruledb_rule_what_attach_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_what_attach("100", "8")
    assert out["status"] == "plan"
    assert pmg.posts == []


def test_pmg_ruledb_rule_what_attach_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_what_attach("100", "8", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    assert pmg.posts[0][0] == "/config/ruledb/rules/100/what"
    assert pmg.posts[0][1].get("ogroup") == "8"


def test_pmg_ruledb_rule_what_detach_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_what_detach("100", "8")
    assert out["status"] == "plan"
    assert pmg.deletes == []


def test_pmg_ruledb_rule_what_detach_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_what_detach("100", "8", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.deletes) == 1
    assert pmg.deletes[0][0] == "/config/ruledb/rules/100/what/8"


def test_pmg_ruledb_rule_when_attach_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_when_attach("100", "4")
    assert out["status"] == "plan"
    assert pmg.posts == []


def test_pmg_ruledb_rule_when_attach_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_when_attach("100", "4", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    assert pmg.posts[0][0] == "/config/ruledb/rules/100/when"
    assert pmg.posts[0][1].get("ogroup") == "4"


def test_pmg_ruledb_rule_when_detach_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_when_detach("100", "4")
    assert out["status"] == "plan"
    assert pmg.deletes == []


def test_pmg_ruledb_rule_when_detach_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_when_detach("100", "4", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.deletes) == 1
    assert pmg.deletes[0][0] == "/config/ruledb/rules/100/when/4"


def test_pmg_ruledb_rule_action_attach_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_action_attach("100", "13")
    assert out["status"] == "plan"
    assert pmg.posts == []


def test_pmg_ruledb_rule_action_attach_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_action_attach("100", "13", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.posts) == 1
    # PMG 9.1 live-verified: singular /action (not /actions — that path returns 501)
    assert pmg.posts[0][0] == "/config/ruledb/rules/100/action"
    assert pmg.posts[0][1].get("ogroup") == "13"


def test_pmg_ruledb_rule_action_detach_dry_run(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_action_detach("100", "13")
    assert out["status"] == "plan"
    assert pmg.deletes == []


def test_pmg_ruledb_rule_action_detach_confirm(tmp_path, monkeypatch):
    _, _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_ruledb_rule_action_detach("100", "13", confirm=True)
    assert out["status"] == "ok"
    assert len(pmg.deletes) == 1
    # PMG 9.1 live-verified: singular /action (not /actions — that path returns 501)
    assert pmg.deletes[0][0] == "/config/ruledb/rules/100/action/13"
