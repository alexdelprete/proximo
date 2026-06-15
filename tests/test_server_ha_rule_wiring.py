"""Server-level integration for the HA-rule plane (ha_rule create / update / delete).

Proves the trust gate holds across the new HA-rule wiring:
- every mutation is dry-run by default (confirm=False => status="plan", op NOT called),
- a confirm=True call routes to the real op and records to the ledger,
- the pre-classified risk (RISK_MEDIUM — HA placement constraint) surfaces through the server.

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


def test_ha_rule_create_dry_run_medium_then_confirm(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    dry = server.pve_ha_rule_create("pin-web", "node-affinity", "vm:100", nodes="pve1")
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert api.posts == []
    server.pve_ha_rule_create("pin-web", "node-affinity", "vm:100", nodes="pve1", confirm=True)
    assert api.posts == [("/cluster/ha/rules",
                          {"rule": "pin-web", "type": "node-affinity", "resources": "vm:100",
                           "nodes": "pve1"})]
    assert any(e.get("action") == "pve_ha_rule_create" for e in _entries(log))


def test_ha_rule_create_resource_affinity_confirm(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    server.pve_ha_rule_create("keep-apart", "resource-affinity", "vm:100,ct:101",
                              affinity="negative", confirm=True)
    assert api.posts == [("/cluster/ha/rules",
                          {"rule": "keep-apart", "type": "resource-affinity",
                           "resources": "vm:100,ct:101", "affinity": "negative"})]


def test_ha_rule_update_dry_run_then_confirm(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = [{"rule": "pin-web", "type": "node-affinity"}]
    dry = server.pve_ha_rule_update("pin-web", comment="x")
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert api.puts == []
    server.pve_ha_rule_update("pin-web", comment="x", confirm=True)
    # `type` is auto-fetched from the current rule (PVE's PUT discriminator requirement)
    assert api.puts == [("/cluster/ha/rules/pin-web", {"comment": "x", "type": "node-affinity"})]


def test_ha_rule_delete_dry_run_then_confirm(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = [{"rule": "pin-web", "type": "node-affinity"}]
    dry = server.pve_ha_rule_delete("pin-web")
    assert dry["status"] == "plan"
    assert api.dels == []
    server.pve_ha_rule_delete("pin-web", confirm=True)
    assert api.dels == [("/cluster/ha/rules/pin-web", None)]


def test_ha_rule_update_delete_shown_in_dry_run(tmp_path, monkeypatch):
    # the server must pass `delete` into the plan so a dry-run discloses what confirm will unset
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = [{"rule": "pin-web", "type": "node-affinity"}]
    dry = server.pve_ha_rule_update("pin-web", delete=["strict"])
    assert dry["status"] == "plan"
    blob = (dry["change"] + " " + " ".join(dry["blast_radius"])).lower()
    assert "strict" in blob or "delete" in blob
    assert api.puts == []  # still a dry-run
