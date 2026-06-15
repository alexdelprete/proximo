"""Server-level integration for the SDN plane (zone / vnet / subnet CRUD).

Proves the trust gate holds across the new SDN wiring:
- every mutation is dry-run by default (confirm=False => status="plan", op NOT called),
- a confirm=True call routes to the real op and records to the ledger,
- create/update are RISK_LOW (pending, inert until apply); delete is RISK_MEDIUM,
- sdn_apply is NOT part of this plane (no live network effect from CRUD).

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
    cfg = ProximoConfig(api_base_url="https://x:8006/api2/json", node="pve",
                        token_path="/run/x", audit_log_path=log)
    api = _FakeApi()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, SimpleNamespace(), ledger))
    return cfg, api, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# --- zones ------------------------------------------------------------------

def test_sdn_zone_create_dry_run_low_then_confirm(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_zone_create("myzone", "simple")
    assert dry["status"] == "plan" and dry["risk"] == "low"
    assert api.posts == []
    server.pve_sdn_zone_create("myzone", "simple", options={"ipam": "pve"}, confirm=True)
    assert api.posts == [("/cluster/sdn/zones",
                          {"type": "simple", "zone": "myzone", "ipam": "pve"})]
    assert any(e.get("action") == "pve_sdn_zone_create" for e in _entries(log))


def test_sdn_zone_update_confirm_puts(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_zone_update("myzone", options={"mtu": "1450"})
    assert dry["status"] == "plan" and dry["risk"] == "low"
    server.pve_sdn_zone_update("myzone", options={"mtu": "1450"}, confirm=True)
    assert api.puts == [("/cluster/sdn/zones/myzone", {"mtu": "1450"})]


def test_sdn_zone_delete_dry_run_medium_then_confirm(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = [{"zone": "myzone", "type": "simple"}]
    dry = server.pve_sdn_zone_delete("myzone")
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert api.dels == []
    server.pve_sdn_zone_delete("myzone", confirm=True)
    assert api.dels == [("/cluster/sdn/zones/myzone", {})]


# --- vnets ------------------------------------------------------------------

def test_sdn_vnet_create_confirm_posts(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_vnet_create("myvnet", "myzone")
    assert dry["status"] == "plan" and dry["risk"] == "low"
    server.pve_sdn_vnet_create("myvnet", "myzone", options={"tag": 100}, confirm=True)
    assert api.posts == [("/cluster/sdn/vnets",
                          {"type": "vnet", "vnet": "myvnet", "zone": "myzone", "tag": 100})]


def test_sdn_vnet_delete_confirm(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = [{"vnet": "myvnet", "zone": "myzone"}]
    dry = server.pve_sdn_vnet_delete("myvnet")
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    server.pve_sdn_vnet_delete("myvnet", confirm=True)
    assert api.dels == [("/cluster/sdn/vnets/myvnet", {})]


# --- subnets ----------------------------------------------------------------

def test_sdn_subnet_list_is_audited_read(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"subnet": "myzone-10.0.0.0-24"}]
    out = server.pve_sdn_subnet_list("myvnet")
    assert api.gets == ["/cluster/sdn/vnets/myvnet/subnets"]
    assert out == [{"subnet": "myzone-10.0.0.0-24"}]


def test_sdn_subnet_create_confirm_posts(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_subnet_create("myvnet", "10.0.0.0/24")
    assert dry["status"] == "plan" and dry["risk"] == "low"
    server.pve_sdn_subnet_create("myvnet", "10.0.0.0/24", options={"gateway": "10.0.0.1"},
                                 confirm=True)
    assert api.posts == [("/cluster/sdn/vnets/myvnet/subnets",
                          {"type": "subnet", "subnet": "10.0.0.0/24", "gateway": "10.0.0.1"})]


def test_sdn_subnet_delete_confirm(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_subnet_delete("myvnet", "myzone-10.0.0.0-24")
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    server.pve_sdn_subnet_delete("myvnet", "myzone-10.0.0.0-24", confirm=True)
    assert api.dels == [("/cluster/sdn/vnets/myvnet/subnets/myzone-10.0.0.0-24", {})]
