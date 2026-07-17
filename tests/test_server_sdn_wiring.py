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


# ---------------------------------------------------------------------------
# Wave 7a — gap-fill reads + node-status + global control plane wiring
# ---------------------------------------------------------------------------


def test_sdn_zone_get_is_audited_read(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = {"zone": "myzone", "type": "simple"}
    out = server.pve_sdn_zone_get("myzone")
    assert api.gets == ["/cluster/sdn/zones/myzone"]
    assert out == {"zone": "myzone", "type": "simple"}
    assert any(e.get("action") == "pve_sdn_zone_get" for e in _entries(log))


def test_sdn_zone_get_forwards_pending_running(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = {}
    server.pve_sdn_zone_get("myzone", pending=True, running=False)
    assert api.gets == ["/cluster/sdn/zones/myzone?pending=1&running=0"]


def test_sdn_vnet_get_is_audited_read(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = {"vnet": "myvnet"}
    out = server.pve_sdn_vnet_get("myvnet")
    assert api.gets == ["/cluster/sdn/vnets/myvnet"]
    assert out == {"vnet": "myvnet"}


def test_sdn_subnet_get_is_audited_read(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = {"subnet": "myzone-10.0.0.0-24"}
    out = server.pve_sdn_subnet_get("myvnet", "myzone-10.0.0.0-24")
    assert api.gets == ["/cluster/sdn/vnets/myvnet/subnets/myzone-10.0.0.0-24"]
    assert out == {"subnet": "myzone-10.0.0.0-24"}


def test_sdn_dry_run_is_audited_read(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = {"frr-diff": "x"}
    out = server.pve_sdn_dry_run()
    assert api.gets == ["/cluster/sdn/dry-run?node=pve"]
    assert out == {"frr-diff": "x"}


def test_sdn_dry_run_explicit_node(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = {}
    server.pve_sdn_dry_run(node="node2")
    assert api.gets == ["/cluster/sdn/dry-run?node=node2"]


def test_sdn_zone_status_list_is_audited_read(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = [{"zone": "z1", "status": "available"}]
    out = server.pve_sdn_zone_status_list()
    assert api.gets == ["/nodes/pve/sdn/zones"]
    assert out == [{"zone": "z1", "status": "available"}]


def test_sdn_zone_bridges_is_audited_read(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = [{"name": "vmbr1", "ports": []}]
    out = server.pve_sdn_zone_bridges("myzone")
    assert api.gets == ["/nodes/pve/sdn/zones/myzone/bridges"]
    assert out == [{"name": "vmbr1", "ports": []}]


def test_sdn_zone_content_is_audited_read(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = [{"vnet": "vn1"}]
    out = server.pve_sdn_zone_content("myzone")
    assert api.gets == ["/nodes/pve/sdn/zones/myzone/content"]
    assert out == [{"vnet": "vn1"}]


def test_sdn_zone_ip_vrf_is_audited_read(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = [{"ip": "10.0.0.0/24", "nexthops": ["10.0.0.1"]}]
    out = server.pve_sdn_zone_ip_vrf("myzone")
    assert api.gets == ["/nodes/pve/sdn/zones/myzone/ip-vrf"]
    assert out == [{"ip": "10.0.0.0/24", "nexthops": ["10.0.0.1"]}]


def test_sdn_vnet_mac_vrf_is_audited_read(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = [{"ip": "10.0.0.5", "mac": "aa:bb:cc:dd:ee:ff"}]
    out = server.pve_sdn_vnet_mac_vrf("myvnet")
    assert api.gets == ["/nodes/pve/sdn/vnets/myvnet/mac-vrf"]
    assert out == [{"ip": "10.0.0.5", "mac": "aa:bb:cc:dd:ee:ff"}]


# --- global SDN control plane: lock / rollback -------------------------------


def test_sdn_lock_acquire_dry_run_medium_then_confirm(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_lock_acquire()
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert api.posts == []
    server.pve_sdn_lock_acquire(allow_pending=True, confirm=True)
    assert api.posts == [("/cluster/sdn/lock", {"allow-pending": True})]
    entry = next(e for e in _entries(log) if e["action"] == "pve_sdn_lock_acquire" and e["outcome"] == "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
    assert entry["detail"]["allow_pending"] is True


def test_sdn_lock_acquire_confirm_returns_token_never_in_ledger_detail(tmp_path, monkeypatch):
    """SECRET HANDLING: the returned token must be in `result`, never in the ledger detail."""
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._post = lambda path, data=None: "super-secret-lock-token"
    out = server.pve_sdn_lock_acquire(confirm=True)
    assert out["status"] == "ok"
    assert out["result"] == "super-secret-lock-token"
    for e in _entries(log):
        assert "super-secret-lock-token" not in json.dumps(e)


def test_sdn_lock_release_dry_run_then_confirm(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_lock_release(lock_token="tok-1")
    assert dry["status"] == "plan" and dry["risk"] == "low"
    server.pve_sdn_lock_release(lock_token="tok-1", confirm=True)
    assert api.dels == [("/cluster/sdn/lock", {"lock-token": "tok-1"})]
    entry = next(e for e in _entries(log) if e["action"] == "pve_sdn_lock_release" and e["outcome"] == "ok")
    assert entry["detail"]["confirmed"] is True
    # lock_token must NEVER be written into the ledger detail
    assert "tok-1" not in json.dumps(entry)


def test_sdn_lock_release_force_dry_run_is_high(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_lock_release(force=True)
    assert dry["status"] == "plan" and dry["risk"] == "high"
    server.pve_sdn_lock_release(force=True, confirm=True)
    assert api.dels == [("/cluster/sdn/lock", {"force": True})]


def test_sdn_rollback_dry_run_medium_then_confirm(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = []
    dry = server.pve_sdn_rollback()
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert api.posts == []
    server.pve_sdn_rollback(lock_token="tok-9", confirm=True)
    assert api.posts == [("/cluster/sdn/rollback", {"lock-token": "tok-9"})]
    entry = next(e for e in _entries(log) if e["action"] == "pve_sdn_rollback" and e["outcome"] == "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
    assert "tok-9" not in json.dumps(entry)


# --- sdn_apply extension: lock_token/release_lock -----------------------------


def test_sdn_apply_extension_confirm_forwards_lock_params(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = []
    dry = server.pve_sdn_apply()
    assert dry["status"] == "plan" and dry["risk"] == "high"
    server.pve_sdn_apply(lock_token="tok-5", release_lock=False, confirm=True)
    assert api.puts == [("/cluster/sdn", {"lock-token": "tok-5", "release-lock": False})]
    entry = next(e for e in _entries(log) if e["action"] == "pve_sdn_apply" and e["outcome"] == "submitted")
    assert "tok-5" not in json.dumps(entry)


def test_sdn_apply_extension_no_lock_args_matches_original_call(tmp_path, monkeypatch):
    """Omitting both new params: the wire call must stay byte-for-byte what it was before the
    extension — PUT /cluster/sdn with data=None (no second positional arg)."""
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = []
    server.pve_sdn_apply(confirm=True)
    assert api.puts == [("/cluster/sdn", None)]
