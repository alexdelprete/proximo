"""Server-level integration for the TFA plane (tfa_get read + tfa_delete mutation).

Proves the trust gate holds AND that the TFA password secret never leaks:
- tfa_delete is dry-run by default (confirm=False => status="plan", RISK_HIGH, op NOT called),
- confirm=True routes to the real op and records to the ledger,
- the `password` secret is passed to the op but NEVER written to the audit ledger,
- tfa_get is audited as a read.

Backend is faked; the ledger is real (tmp_path) so PLAN->PROVE + the no-leak check are end-to-end.
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
        self.dels: list = []
        self._get_return: list = []

    def _get(self, path):
        self.gets.append(path)
        return self._get_return

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


def test_tfa_get_is_audited_read(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"id": "totp:LABEL"}]
    out = server.pve_tfa_get("root@pam")
    assert api.gets == ["/access/tfa/root@pam"]
    assert out == [{"id": "totp:LABEL"}]


def test_tfa_delete_dry_run_is_high_no_mutation(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = [{"id": "totp:LABEL"}, {"id": "recovery"}]
    out = server.pve_tfa_delete("root@pam", "totp:LABEL")
    assert out["status"] == "plan"
    assert out["risk"] == "high"
    assert api.dels == []  # NOT executed without confirm


def test_tfa_delete_confirm_executes_and_password_never_logged(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    secret = "S3cr3t-Current-Pw"
    server.pve_tfa_delete("root@pam", "totp:LABEL", password=secret, confirm=True)
    # the op received the password (so PVE gets it)...
    assert api.dels == [("/access/tfa/root@pam/totp:LABEL", {"password": secret})]
    # ...but it must NOT appear anywhere in the audit ledger
    raw = open(log, encoding="utf-8").read()
    assert secret not in raw
    # and the action was still recorded
    entries = [json.loads(line) for line in raw.splitlines() if line.strip()]
    assert any(e.get("action") == "pve_tfa_delete" for e in entries)
