"""Server-seam integration for the blast engine — storage_delete/update PLAN through the real
tool path. Backends faked (path-aware), ledger real (tmp_path). Mirrors test_server_round3_wiring."""

from __future__ import annotations

import json
from types import SimpleNamespace

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig


class _FakeApi:
    def __init__(self, rows, configs, fail_config_for=()):
        self.config = SimpleNamespace(node="pve1")
        self._rows = rows
        self._configs = configs
        self._fail = set(fail_config_for)

    def _get(self, path):
        if path == "/cluster/resources":
            return self._rows
        if path.endswith("/config"):
            vmid = path.strip("/").split("/")[3]
            if vmid in self._fail:
                raise RuntimeError("node down")
            return self._configs[vmid]
        return []

    def _delete(self, path, params=None):
        return None

    def _put(self, path, data=None):
        return None


def _wire(tmp_path, monkeypatch, api):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(api_base_url="https://x:8006/api2/json", node="pve1",
                        token_path="/run/x", audit_log_path=log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, SimpleNamespace(), AuditLedger(log)))
    return log


def _entries(log):
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


_ROWS = [{"vmid": "101", "type": "qemu", "node": "pve1", "name": "web", "status": "running"}]
_CONFIGS = {"101": {"scsi0": "nas:101/d.qcow2,size=8G", "bootdisk": "scsi0"}}


def test_delete_plan_names_affected_and_ledger_records_it(tmp_path, monkeypatch):
    log = _wire(tmp_path, monkeypatch, _FakeApi(_ROWS, _CONFIGS))
    resp = server.pve_storage_delete("nas")               # dry-run (confirm defaults False)
    assert resp["status"] == "plan" and resp["risk"] == "high"
    assert resp["affected"][0]["resource"] == "qemu/101"  # as_dict carries affected (A2A path too)
    assert any("qemu/101" in line for line in resp["blast_radius"])
    planned = [e for e in _entries(log) if e.get("outcome") == "planned"]
    assert planned and planned[-1]["detail"]["affected"][0]["resource"] == "qemu/101"


def test_delete_plan_fail_closed_on_unreadable_guest(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch, _FakeApi(_ROWS, _CONFIGS, fail_config_for=("101",)))
    resp = server.pve_storage_delete("nas")
    assert resp["risk"] == "high"                         # never lowered
    assert resp["blast_radius"][0].startswith("⚠ INCOMPLETE")
    assert any(a["severity"] == "unknown" for a in resp["affected"])


def test_update_disable_plan_escalates_to_high(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch, _FakeApi(_ROWS, _CONFIGS))
    resp = server.pve_storage_update("nas", disable=True)
    assert resp["status"] == "plan" and resp["risk"] == "high"
    assert resp["affected"][0]["resource"] == "qemu/101"


class _AclApi:
    def __init__(self, acl, groups=None, members=None):
        self.config = SimpleNamespace(node="pve1")
        self._acl, self._groups, self._members = acl, groups or [], members or {}

    def _get(self, path):
        if path == "/access/acl":
            return list(self._acl)
        if path.startswith("/access/users/") and path.endswith("/token"):
            return []
        if path.startswith("/access/users/"):
            return {"groups": list(self._groups)}
        if path.startswith("/access/groups/"):
            return {"members": list(self._members.get(path.rsplit("/", 1)[1], []))}
        return []

    def _put(self, path, data=None):
        return None


def test_acl_modify_plan_affected_in_response_and_ledger(tmp_path, monkeypatch):
    acl = [{"path": "/", "ugid": "bob@pam", "roleid": "Administrator", "type": "user", "propagate": True}]
    log = _wire(tmp_path, monkeypatch, _AclApi(acl, groups=[]))
    resp = server.pve_acl_modify("/vms/100", "PVEVMUser", "bob@pam", kind="user")  # dry-run
    assert resp["status"] == "plan" and resp["risk"] == "high"
    assert any(a["change"] == "loses" and "Administrator" in a["roles"] for a in resp["affected"])
    planned = [e for e in _entries(log) if e.get("outcome") == "planned"]
    assert planned and "affected" in planned[-1]["detail"]


# --- firewall reach seam (Part A) -------------------------------------------

class _FwApi:
    """Fake api for the firewall rule_add seam: plan_firewall_rule_add is PURE (no read), so this
    only needs config + a no-op _post. A _get is supplied for the rule_remove/update paths."""

    def __init__(self, rules=None):
        self.config = SimpleNamespace(node="pve1")
        self._rules = rules or []

    def _get(self, path):
        return self._rules

    def _post(self, path, data=None):
        return None

    def _delete(self, path, params=None):
        return None

    def _put(self, path, data=None):
        return None


def test_firewall_rule_add_plan_affected_in_response_and_ledger(tmp_path, monkeypatch):
    log = _wire(tmp_path, monkeypatch, _FwApi())
    # ACCEPT/in from anywhere on SSH => maximal reach => HIGH; affected carries the per-rule reach.
    resp = server.pve_firewall_rule_add("ACCEPT", direction="in", scope="cluster",
                                        source="0.0.0.0/0", dport="22")  # dry-run
    assert resp["status"] == "plan" and resp["risk"] == "high"
    assert resp["affected"] and resp["affected"][0]["effect"] == "permits"
    assert resp["affected"][0]["severity"] == "high"
    assert any("PERMITS inbound" in line for line in resp["blast_radius"])
    # per-rule-reach framing present; never asserts "cluster exposed" as fact
    assert any("per-rule" in line.lower() for line in resp["blast_radius"])
    assert not any("your cluster is reachable" in line.lower() for line in resp["blast_radius"])
    planned = [e for e in _entries(log) if e.get("outcome") == "planned"]
    assert planned and planned[-1]["detail"]["affected"][0]["effect"] == "permits"


# --- network apply lockout seam (Part B) ------------------------------------

class _NetApplyApi:
    """Fake api for the network_apply seam: network_list returns ifaces; config carries the node +
    the api_base_url whose host the lockout engine parses as the management host."""

    def __init__(self, ifaces, mgmt_url="https://10.0.0.10:8006/api2/json"):
        self.config = SimpleNamespace(node="pve1", api_base_url=mgmt_url)
        self._ifaces = ifaces

    def _get(self, path):
        return self._ifaces

    def _put(self, path, data=None):
        return None


def test_network_apply_plan_names_mgmt_iface_and_ledger(tmp_path, monkeypatch):
    # the fake api's api_base_url host (10.0.0.10) is the mgmt host; vmbr0 (pending) holds it.
    log = _wire(tmp_path, monkeypatch,
                _NetApplyApi([{"iface": "vmbr0", "address": "10.0.0.10", "pending": 1}]))
    resp = server.pve_network_apply()  # dry-run
    assert resp["status"] == "plan" and resp["risk"] == "high"
    assert any(a.get("iface") == "vmbr0" for a in resp["affected"])
    assert any("10.0.0.10" in line for line in resp["blast_radius"])
    planned = [e for e in _entries(log) if e.get("outcome") == "planned"]
    assert planned and planned[-1]["detail"]["affected"][0]["iface"] == "vmbr0"
