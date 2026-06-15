"""Server-level integration for the firewall-completion plane (aliases / ipsets /
security-groups / options-set).

Proves the trust gate holds across the NEW firewall wiring:
- every new MUTATION is dry-run by default (confirm=False => status="plan", op NOT called),
- a confirm=True call routes to the real op and records to the ledger,
- reads are audited as non-mutations,
- the pre-classified risks surface through the server (alias update/delete MEDIUM;
  options policy/enable changes HIGH),
- the destructive-semantics footguns are honest through the server (ipset delete needs
  force; security-group delete needs the group empty).

Backend is faked; the ledger is real (tmp_path) so PLAN->PROVE is exercised end to end.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig


class _FakeApi:
    def __init__(self):
        self.config = SimpleNamespace(node="pve")
        self.gets: list = []
        self.posts: list = []
        self.puts: list = []
        self.dels: list = []
        self._get_return: list = []

    def _get(self, path):
        self.gets.append(path)
        return self._get_return

    def _post(self, path, data=None):
        self.posts.append((path, data))
        return None

    def _put(self, path, data=None):
        self.puts.append((path, data))
        return None

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
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, SimpleNamespace(), ledger))
    return cfg, api, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# --- Aliases ----------------------------------------------------------------


def test_alias_list_is_audited_read(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"name": "web", "cidr": "10.0.0.0/24"}]
    out = server.pve_firewall_alias_list()
    assert out == [{"name": "web", "cidr": "10.0.0.0/24"}]
    assert api.gets == ["/cluster/firewall/aliases"]
    # audited but not a mutation
    ents = _entries(log)
    assert any(e.get("action") == "pve_firewall_alias_list" for e in ents)


def test_alias_create_dry_run_is_low_plan_no_mutation(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pve_firewall_alias_create("web", "10.0.0.0/24")
    assert out["status"] == "plan"
    assert out["risk"] == "low"
    assert api.posts == []  # NOT executed without confirm


def test_alias_create_confirm_executes(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    server.pve_firewall_alias_create("web", "10.0.0.0/24", comment="x", confirm=True)
    assert api.posts == [("/cluster/firewall/aliases",
                          {"name": "web", "cidr": "10.0.0.0/24", "comment": "x"})]
    assert any(e.get("action") == "pve_firewall_alias_create" for e in _entries(log))


def test_alias_update_dry_run_is_medium_then_confirm_puts(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = [{"name": "web", "cidr": "10.0.0.0/24"}]
    dry = server.pve_firewall_alias_update("web", cidr="10.0.0.0/8")
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert api.puts == []
    server.pve_firewall_alias_update("web", cidr="10.0.0.0/8", confirm=True)
    assert api.puts == [("/cluster/firewall/aliases/web", {"cidr": "10.0.0.0/8"})]


def test_alias_delete_dry_run_then_confirm_deletes(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = [{"name": "web", "cidr": "10.0.0.0/24"}]
    dry = server.pve_firewall_alias_delete("web")
    assert dry["status"] == "plan"
    assert api.dels == []
    server.pve_firewall_alias_delete("web", confirm=True)
    assert api.dels == [("/cluster/firewall/aliases/web", {})]


# --- IP-sets ----------------------------------------------------------------


def test_ipset_create_dry_run_low_then_confirm(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    dry = server.pve_firewall_ipset_create("blocklist")
    assert dry["status"] == "plan" and dry["risk"] == "low"
    assert api.posts == []
    server.pve_firewall_ipset_create("blocklist", comment="bad", confirm=True)
    assert api.posts == [("/cluster/firewall/ipset", {"name": "blocklist", "comment": "bad"})]


def test_ipset_delete_dry_run_then_confirm_force(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = [{"cidr": "10.0.0.0/24"}]
    dry = server.pve_firewall_ipset_delete("blocklist", force=True)
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert api.dels == []
    server.pve_firewall_ipset_delete("blocklist", force=True, confirm=True)
    assert api.dels == [("/cluster/firewall/ipset/blocklist", {"force": 1})]


def test_ipset_entry_add_dry_run_then_confirm(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    dry = server.pve_firewall_ipset_entry_add("blocklist", "10.0.0.0/24")
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert api.posts == []
    server.pve_firewall_ipset_entry_add("blocklist", "10.0.0.0/24", confirm=True)
    assert api.posts == [("/cluster/firewall/ipset/blocklist", {"cidr": "10.0.0.0/24"})]


def test_ipset_entry_remove_dry_run_then_confirm(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    dry = server.pve_firewall_ipset_entry_remove("blocklist", "10.0.0.0/24")
    assert dry["status"] == "plan"
    assert api.dels == []
    server.pve_firewall_ipset_entry_remove("blocklist", "10.0.0.0/24", confirm=True)
    assert api.dels == [("/cluster/firewall/ipset/blocklist/10.0.0.0/24", {})]


# --- Security groups --------------------------------------------------------


def test_sg_create_dry_run_low_then_confirm(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    dry = server.pve_firewall_security_group_create("web-dmz")
    assert dry["status"] == "plan" and dry["risk"] == "low"
    assert api.posts == []
    server.pve_firewall_security_group_create("web-dmz", comment="dmz", confirm=True)
    assert api.posts == [("/cluster/firewall/groups", {"group": "web-dmz", "comment": "dmz"})]


def test_sg_delete_dry_run_medium_then_confirm(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = [{"pos": 0}]
    dry = server.pve_firewall_security_group_delete("web-dmz")
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert api.dels == []
    server.pve_firewall_security_group_delete("web-dmz", confirm=True)
    assert api.dels == [("/cluster/firewall/groups/web-dmz", {})]


# --- Options set ------------------------------------------------------------


def test_options_set_dry_run_high_then_confirm(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = {"policy_in": "ACCEPT"}
    dry = server.pve_firewall_options_set(options={"policy_in": "DROP"})
    assert dry["status"] == "plan" and dry["risk"] == "high"
    assert api.puts == []
    server.pve_firewall_options_set(options={"policy_in": "DROP"}, confirm=True)
    assert api.puts == [("/cluster/firewall/options", {"policy_in": "DROP"})]


def test_options_set_log_level_is_medium_dry_run(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = {}
    dry = server.pve_firewall_options_set(scope="node", options={"log_level_in": "info"})
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert api.puts == []
