"""Server-level integration for the round-3 tool groups (storage-admin / users-groups / roles-realms).

Proves the trust gate holds across the new wiring — including the new wrinkle this round:
affected-set plans (user/group/role/realm delete) that READ the api AT PLAN TIME, and the
built-in role/realm REFUSE paths. Backends faked; ledger real (tmp_path).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig


class _FakeApi:
    """Path-aware fake: _get dispatches by path so affected-set plans hit their success branch."""

    def __init__(self):
        self.config = SimpleNamespace(node="pve")
        self.posts: list = []
        self.puts: list = []
        self.dels: list = []

    def _get(self, path):
        if "/access/users/" in path:
            return {"tokens": {"t1": {"privsep": 1}}, "groups": ["g1"], "enable": 1}
        if path == "/access/acl":
            return [{"path": "/", "roleid": "CustomRole", "ugid": "bob@pam", "type": "user"}]
        if "/access/groups/" in path:
            return {"members": ["bob@pam"], "comment": "x"}
        return []

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
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, SimpleNamespace(), AuditLedger(log)))
    return cfg, api, log


def _entries(log):
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_all_round3_tools_registered():
    import asyncio
    tools = {t.name for t in asyncio.run(server.mcp.list_tools())}
    new = {
        "pve_storage_config_list", "pve_storage_config_get", "pve_storage_create",
        "pve_storage_update", "pve_storage_delete",
        "pve_user_get", "pve_groups_list", "pve_group_get", "pve_user_create",
        "pve_user_update", "pve_user_delete", "pve_group_create", "pve_group_update",
        "pve_group_delete",
        "pve_realms_list", "pve_realm_get", "pve_tfa_list", "pve_role_create",
        "pve_role_update", "pve_role_delete", "pve_realm_create", "pve_realm_update",
        "pve_realm_delete",
    }
    assert new <= tools
    assert len(new) == 23


def test_storage_delete_high_plan_no_mutation(tmp_path, monkeypatch):
    _, api, _ = _wire(tmp_path, monkeypatch)
    out = server.pve_storage_delete("usb-20tb")
    assert out["status"] == "plan" and out["risk"] == "high"
    assert api.dels == []


def test_storage_config_list_read_audited(tmp_path, monkeypatch):
    _, _, log = _wire(tmp_path, monkeypatch)
    server.pve_storage_config_list()
    assert any(e["action"] == "pve_storage_config_list" and not e["mutation"]
               for e in _entries(log))


def test_user_delete_affected_set_plan_via_server(tmp_path, monkeypatch):
    # The new wrinkle: the plan READS api at plan time (tokens dict + acl) and stays HIGH.
    _, api, _ = _wire(tmp_path, monkeypatch)
    out = server.pve_user_delete("bob@pam")
    assert out["status"] == "plan" and out["risk"] == "high"
    blast = " ".join(out["blast_radius"])
    assert "token" in blast.lower()           # token count surfaced from the live-shaped read
    assert api.dels == []


def test_group_delete_affected_set_plan_via_server(tmp_path, monkeypatch):
    _, api, _ = _wire(tmp_path, monkeypatch)
    out = server.pve_group_delete("g1")
    assert out["status"] == "plan" and out["risk"] == "high"
    assert api.dels == []


def test_role_delete_builtin_refused_via_server(tmp_path, monkeypatch):
    _, api, _ = _wire(tmp_path, monkeypatch)
    out = server.pve_role_delete("Administrator")
    assert out["status"] == "plan" and out["risk"] == "high"
    assert any("refus" in b.lower() or "built" in b.lower() for b in out["blast_radius"])
    assert api.dels == []


def test_realm_delete_builtin_pam_refused_via_server(tmp_path, monkeypatch):
    _, api, _ = _wire(tmp_path, monkeypatch)
    out = server.pve_realm_delete("pam")
    assert out["status"] == "plan" and out["risk"] == "high"
    assert api.dels == []


def test_role_delete_custom_reads_acls_via_server(tmp_path, monkeypatch):
    _, api, _ = _wire(tmp_path, monkeypatch)
    out = server.pve_role_delete("CustomRole")
    assert out["status"] == "plan" and out["risk"] == "high"
    assert api.dels == []                      # plan only; nothing deleted


def test_group_create_confirm_executes_records_plan_first(tmp_path, monkeypatch):
    _, api, log = _wire(tmp_path, monkeypatch)
    server.pve_group_create("newgrp", confirm=True)
    assert api.posts and api.posts[0][0] == "/access/groups"
    outcomes = {e["outcome"] for e in _entries(log) if e["action"] == "pve_group_create"}
    assert {"planned", "ok"} <= outcomes


def test_realm_create_passes_options_through_via_server(tmp_path, monkeypatch):
    # 2026-06-09: type-specific options must reach the POST body or PVE rejects typed realms.
    _, api, _ = _wire(tmp_path, monkeypatch)
    server.pve_realm_create("myldap", "ldap",
                            options={"server1": "ldap.example.com", "base_dn": "dc=ex,dc=com"},
                            confirm=True)
    assert api.posts and api.posts[0][0] == "/access/domains"
    body = api.posts[0][1]
    assert body["server1"] == "ldap.example.com"
    assert body["base_dn"] == "dc=ex,dc=com"
    assert body["realm"] == "myldap" and body["type"] == "ldap"


def test_realm_update_passes_options_through_via_server(tmp_path, monkeypatch):
    _, api, _ = _wire(tmp_path, monkeypatch)
    server.pve_realm_update("myldap", options={"server1": "new.example.com"}, confirm=True)
    assert api.puts and api.puts[0][0] == "/access/domains/myldap"
    assert api.puts[0][1]["server1"] == "new.example.com"
