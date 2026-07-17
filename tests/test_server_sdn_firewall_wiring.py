"""Server-level integration for the SDN vnet-scoped FIREWALL + IP MAPPINGS plane
(Wave 7b, full-surface campaign).

Proves the trust gate holds across the new wiring:
- every read is an audited call at the exact path, recorded to the ledger;
- every mutation is dry-run by default (confirm=False => status="plan", op NOT called);
- a confirm=True call routes to the real op and records to the ledger;
- risk ladder through the SERVER wrapper (not just the bare plan factory): options_set is
  conditional HIGH/MEDIUM, rule add/update/remove are MEDIUM floor, ip create/update are
  LOW, ip delete is MEDIUM;
- LIVE/IMMEDIATE framing (no "inert until apply" language) present on every mutation plan.

Backend is faked; the ledger is real (tmp_path) so PLAN->PROVE is exercised end to end.
Mirrors the `_wire()`/`_FakeApi` idiom in tests/test_server_sdn_wiring.py.
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
        self._get_return: object = []

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
    cfg = ProximoConfig(api_base_url="https://x:8006/api2/json", node="pve",
                        token_path="/run/x", audit_log_path=log)
    api = _FakeApi()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, SimpleNamespace(), ledger))
    return cfg, api, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# --- reads --------------------------------------------------------------------------------


def test_options_get_is_audited_read(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = {"enable": 1}
    out = server.pve_sdn_vnet_firewall_options_get("myvnet")
    assert api.gets == ["/cluster/sdn/vnets/myvnet/firewall/options"]
    assert out == {"enable": 1}
    assert any(e.get("action") == "pve_sdn_vnet_firewall_options_get" for e in _entries(log))


def test_rules_list_is_audited_read(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"pos": 0, "action": "ACCEPT"}]
    out = server.pve_sdn_vnet_firewall_rules_list("myvnet")
    assert api.gets == ["/cluster/sdn/vnets/myvnet/firewall/rules"]
    assert out == [{"pos": 0, "action": "ACCEPT"}]
    assert any(e.get("action") == "pve_sdn_vnet_firewall_rules_list" for e in _entries(log))


def test_rule_get_is_audited_read(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = {"pos": 2, "action": "DROP"}
    out = server.pve_sdn_vnet_firewall_rule_get("myvnet", 2)
    assert api.gets == ["/cluster/sdn/vnets/myvnet/firewall/rules/2"]
    assert out == {"pos": 2, "action": "DROP"}
    assert any(e.get("action") == "pve_sdn_vnet_firewall_rule_get" for e in _entries(log))


# --- options_set (conditional HIGH/MEDIUM) ------------------------------------------------


def test_options_set_dry_run_high_on_enable_then_confirm(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = {}
    dry = server.pve_sdn_vnet_firewall_options_set("myvnet", options={"enable": True})
    assert dry["status"] == "plan" and dry["risk"] == "high"
    assert api.puts == []
    server.pve_sdn_vnet_firewall_options_set("myvnet", options={"enable": True}, confirm=True)
    assert api.puts == [("/cluster/sdn/vnets/myvnet/firewall/options", {"enable": True})]


def test_options_set_dry_run_disable_enable_is_loosening_text_through_server(tmp_path, monkeypatch):
    """Finding 2 fix, exercised through the actual server wrapper (not just the bare plan
    factory): a protection-REMOVING call (enable=False) must get the loosening warning, not
    the tightening/cut-traffic line."""
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = {"enable": 1}
    dry = server.pve_sdn_vnet_firewall_options_set("myvnet", options={"enable": False})
    assert dry["status"] == "plan" and dry["risk"] == "high"
    blast = " ".join(dry["blast_radius"]).lower()
    assert "removes" in blast and "protection" in blast
    assert "cut all forwarded traffic" not in blast


def test_options_set_dry_run_medium_on_log_level(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = {}
    dry = server.pve_sdn_vnet_firewall_options_set("myvnet", options={"log_level_forward": "info"})
    assert dry["status"] == "plan" and dry["risk"] == "medium"


def test_options_set_blast_never_says_inert(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = {}
    dry = server.pve_sdn_vnet_firewall_options_set("myvnet", options={"enable": True})
    blast = " ".join(dry["blast_radius"]).lower()
    assert "inert" not in blast


# --- rule_add (MEDIUM floor) ---------------------------------------------------------------


def test_rule_add_dry_run_medium_then_confirm(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_vnet_firewall_rule_add("myvnet", "accept", dport="22")
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert api.posts == []
    server.pve_sdn_vnet_firewall_rule_add("myvnet", "accept", dport="22", confirm=True)
    assert api.posts == [("/cluster/sdn/vnets/myvnet/firewall/rules",
                          {"action": "ACCEPT", "type": "in", "dport": "22"})]
    assert any(e.get("action") == "pve_sdn_vnet_firewall_rule_add" for e in _entries(log))


# --- rule_update (MEDIUM floor, digest re-fetch through the wrapper) -----------------------


def test_rule_update_dry_run_then_confirm_default_no_digest_succeeds(tmp_path, monkeypatch):
    """Finding 1 fix: this schema's reads never expose a digest (schema-verified) — the
    default confirm=True path with no digest supplied must SUCCEED, not raise. This is the
    exact break the Wave 7b review reproduced against the old fetch-or-fail design."""
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = [{"pos": 0, "action": "ACCEPT", "type": "in"}]  # schema-true, no digest
    dry = server.pve_sdn_vnet_firewall_rule_update("myvnet", 0, action="drop")
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert "digest" not in dry["current"]
    server.pve_sdn_vnet_firewall_rule_update("myvnet", 0, action="drop", confirm=True)
    assert api.puts == [("/cluster/sdn/vnets/myvnet/firewall/rules/0", {"action": "DROP"})]


def test_rule_update_caller_supplied_digest_forwarded_byte_exact(tmp_path, monkeypatch):
    """digest stays an OPTIONAL caller-supplied passthrough — forwarded byte-exact when
    given, never derived from a plan-side read (there is nothing to derive it from)."""
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = [{"pos": 0, "action": "ACCEPT", "type": "in"}]
    server.pve_sdn_vnet_firewall_rule_update(
        "myvnet", 0, action="drop", digest="caller-supplied-digest-77", confirm=True,
    )
    assert api.puts == [("/cluster/sdn/vnets/myvnet/firewall/rules/0",
                         {"action": "DROP", "digest": "caller-supplied-digest-77"})]


def test_rule_update_only_touches_passed_fields(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = [{"pos": 0, "action": "ACCEPT", "type": "in"}]  # schema-true, no digest
    server.pve_sdn_vnet_firewall_rule_update("myvnet", 0, comment="only this", confirm=True)
    assert api.puts == [("/cluster/sdn/vnets/myvnet/firewall/rules/0",
                         {"comment": "only this"})]


# --- rule_remove (MEDIUM floor, digest pinning) --------------------------------------------


def test_rule_remove_dry_run_then_confirm_default_no_digest_succeeds(tmp_path, monkeypatch):
    """Finding 1 fix: the exact break the Wave 7b review reproduced — schema-true fixture (no
    digest field anywhere), default confirm=True with no digest supplied must SUCCEED."""
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"pos": 0, "action": "ACCEPT", "type": "in"}]  # schema-true, no digest
    dry = server.pve_sdn_vnet_firewall_rule_remove("myvnet", 0)
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert "digest" not in dry["current"]
    server.pve_sdn_vnet_firewall_rule_remove("myvnet", 0, confirm=True)
    assert api.dels == [("/cluster/sdn/vnets/myvnet/firewall/rules/0", {})]
    assert any(e.get("action") == "pve_sdn_vnet_firewall_rule_remove" for e in _entries(log))


def test_rule_remove_caller_supplied_digest_forwarded_byte_exact(tmp_path, monkeypatch):
    """digest stays an OPTIONAL caller-supplied passthrough — forwarded byte-exact when
    given, never derived from a plan-side read (there is nothing to derive it from)."""
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"pos": 0, "action": "ACCEPT", "type": "in"}]
    server.pve_sdn_vnet_firewall_rule_remove("myvnet", 0, digest="caller-supplied-digest-88", confirm=True)
    assert api.dels == [("/cluster/sdn/vnets/myvnet/firewall/rules/0",
                         {"digest": "caller-supplied-digest-88"})]
    assert any(e.get("action") == "pve_sdn_vnet_firewall_rule_remove" for e in _entries(log))


# --- vnet ip mappings (LOW/LOW/MEDIUM, no plan-time api read) ------------------------------


def test_ip_create_dry_run_low_then_confirm(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_vnet_ip_create("myvnet", "myzone", "10.0.0.5", mac="aa:bb:cc:dd:ee:ff")
    assert dry["status"] == "plan" and dry["risk"] == "low"
    assert api.posts == []
    server.pve_sdn_vnet_ip_create("myvnet", "myzone", "10.0.0.5", mac="aa:bb:cc:dd:ee:ff", confirm=True)
    assert api.posts == [("/cluster/sdn/vnets/myvnet/ips",
                          {"ip": "10.0.0.5", "vnet": "myvnet", "zone": "myzone",
                           "mac": "aa:bb:cc:dd:ee:ff"})]
    assert any(e.get("action") == "pve_sdn_vnet_ip_create" for e in _entries(log))


def test_ip_update_dry_run_low_then_confirm(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_vnet_ip_update("myvnet", "myzone", "10.0.0.5", vmid="100")
    assert dry["status"] == "plan" and dry["risk"] == "low"
    server.pve_sdn_vnet_ip_update("myvnet", "myzone", "10.0.0.5", vmid="100", confirm=True)
    assert api.puts == [("/cluster/sdn/vnets/myvnet/ips",
                         {"ip": "10.0.0.5", "vnet": "myvnet", "zone": "myzone", "vmid": "100"})]


def test_ip_delete_dry_run_medium_then_confirm(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_vnet_ip_delete("myvnet", "myzone", "10.0.0.5")
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert api.dels == []
    server.pve_sdn_vnet_ip_delete("myvnet", "myzone", "10.0.0.5", confirm=True)
    assert api.dels == [("/cluster/sdn/vnets/myvnet/ips",
                         {"ip": "10.0.0.5", "vnet": "myvnet", "zone": "myzone"})]
    assert any(e.get("action") == "pve_sdn_vnet_ip_delete" for e in _entries(log))


def test_ip_mutations_never_read_before_planning(tmp_path, monkeypatch):
    """No GET exists for /ips at all — the plan factories for all 3 IP mutations must never
    call api._get()."""
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    server.pve_sdn_vnet_ip_create("myvnet", "myzone", "10.0.0.5")
    server.pve_sdn_vnet_ip_update("myvnet", "myzone", "10.0.0.5")
    server.pve_sdn_vnet_ip_delete("myvnet", "myzone", "10.0.0.5")
    assert api.gets == []
