"""Server-level trust-gate proof for the new ACME cert-order tools.

Mirrors test_server_new_wiring.py: backends faked, ledger real (tmp_path) so PLAN->PROVE runs
end to end. Proves each new tool is dry-run by default (status="plan", op NOT called), records a
"planned" entry before executing on confirm, async order/renew/revoke record "submitted" (never
"ok"), and the revoke surfaces HIGH.
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

    def _get(self, path):
        self.gets.append(path)
        return {}  # empty node config

    def _post(self, path, data=None):
        self.posts.append((path, data))
        return "UPID:post"

    def _put(self, path, data=None):
        self.puts.append((path, data))
        return "UPID:put"

    def _delete(self, path, params=None):
        self.dels.append((path, params))
        return "UPID:del"


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


_CERT = "/nodes/pve/certificates/acme/certificate"


# --- domains_set (config) ---------------------------------------------------

def test_domains_set_dry_run_is_medium_no_write(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    out = server.pve_node_acme_domains_set("le", ["node.example.com"], plugin="technitium")
    assert out["status"] == "plan"
    assert out["risk"] == "medium"
    assert api.puts == []  # nothing written on a dry-run
    assert any(e["action"] == "pve_node_acme_domains_set" and e["outcome"] == "planned"
               for e in _entries(log))


def test_domains_set_confirm_writes_node_config(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    out = server.pve_node_acme_domains_set("le", ["node.example.com"],
                                           plugin="technitium", confirm=True)
    assert out["status"] == "ok"
    assert len(api.puts) == 1
    path, body = api.puts[0]
    assert path == "/nodes/pve/config"
    assert body["acme"] == "account=le"
    assert body["acmedomain0"] == "domain=node.example.com,plugin=technitium"
    outcomes = {e["outcome"] for e in _entries(log) if e["action"] == "pve_node_acme_domains_set"}
    assert {"planned", "ok"} <= outcomes


# --- order / renew / revoke -------------------------------------------------

def test_order_dry_run_is_medium_no_post(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    out = server.pve_acme_cert_order()
    assert out["status"] == "plan"
    assert out["risk"] == "medium"
    assert api.posts == []


def test_order_confirm_submits_upid(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    out = server.pve_acme_cert_order(confirm=True)
    assert out["status"] == "submitted"          # async — never "ok"
    assert out["result"] == "UPID:post"
    assert api.posts == [(_CERT, {})]
    outcomes = {e["outcome"] for e in _entries(log) if e["action"] == "pve_acme_cert_order"}
    assert {"planned", "submitted"} <= outcomes
    assert "ok" not in outcomes


def test_order_force_passes_force(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    server.pve_acme_cert_order(force=True, confirm=True)
    assert api.posts == [(_CERT, {"force": 1})]


def test_renew_confirm_submits(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    out = server.pve_acme_cert_renew(confirm=True)
    assert out["status"] == "submitted"
    assert api.puts == [(_CERT, {})]


def test_revoke_dry_run_is_high(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pve_acme_cert_revoke()
    assert out["status"] == "plan"
    assert out["risk"] == "high"
    assert api.dels == []


def test_revoke_confirm_submits(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    out = server.pve_acme_cert_revoke(confirm=True)
    assert out["status"] == "submitted"
    assert api.dels and api.dels[0][0] == _CERT
    outcomes = {e["outcome"] for e in _entries(log) if e["action"] == "pve_acme_cert_revoke"}
    assert {"planned", "submitted"} <= outcomes
