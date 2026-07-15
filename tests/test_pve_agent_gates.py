"""`_agent_gate`'s blocked branch for the three qemu-agent WRITE-mutation tools that lacked it
(2026-07-14 audit, Task 9 — src/proximo/tools/pve_agent.py med finding).

The identical gate pattern (agent disabled -> blocked:agent_disabled; vmid not allowlisted ->
blocked:allowlist) IS already tested for pve_agent_exec/pve_agent_info/pve_agent_file_read in
tests/test_qemu_agent.py::TestServerGateHelpers, but pve_agent_file_write, pve_agent_fs, and
pve_agent_set_password had zero coverage of their own `_agent_gate` call sites. A regression that
flipped `mutation=True` -> `mutation=False` at one of those three call sites would mis-record a
blocked MUTATION as a non-mutation in the audit ledger and go undetected.
"""

from __future__ import annotations

import json

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig


class _FakeAgentApi:
    """The blocked branch must never reach any of these methods."""

    def __init__(self):
        self.agent_file_writes: list = []
        self.agent_simples: list = []
        self.agent_set_passwords: list = []

    def agent_file_write(self, vmid, node, file, content):
        self.agent_file_writes.append((vmid, node, file, content))
        return None

    def agent_simple(self, vmid, node, command):
        self.agent_simples.append((vmid, node, command))
        return {}

    def agent_set_password(self, vmid, node, username, password):
        self.agent_set_passwords.append((vmid, node, username, password))
        return None


def _wire_agent(tmp_path, monkeypatch, *, enable_agent=True, agent_allowlist=("*",)):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log, enable_agent=enable_agent,
        agent_allowlist=frozenset(agent_allowlist),
    )
    api = _FakeAgentApi()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, None, ledger))
    return cfg, api, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# === agent disabled ===========================================================================


def test_agent_file_write_blocked_when_agent_disabled(tmp_path, monkeypatch):
    _, api, _, log = _wire_agent(tmp_path, monkeypatch, enable_agent=False)
    out = server.pve_agent_file_write("101", "/etc/motd", "hi")
    assert out["status"] == "blocked:agent_disabled"
    assert api.agent_file_writes == []
    blocked = [e for e in _entries(log) if e["outcome"] == "blocked:agent_disabled"]
    assert len(blocked) == 1
    assert blocked[0]["mutation"] is True


def test_agent_fs_blocked_when_agent_disabled(tmp_path, monkeypatch):
    _, api, _, log = _wire_agent(tmp_path, monkeypatch, enable_agent=False)
    out = server.pve_agent_fs("101", "fstrim")
    assert out["status"] == "blocked:agent_disabled"
    assert api.agent_simples == []
    blocked = [e for e in _entries(log) if e["outcome"] == "blocked:agent_disabled"]
    assert len(blocked) == 1
    assert blocked[0]["mutation"] is True


def test_agent_set_password_blocked_when_agent_disabled(tmp_path, monkeypatch):
    _, api, _, log = _wire_agent(tmp_path, monkeypatch, enable_agent=False)
    out = server.pve_agent_set_password("101", "root", "sentinel-pw")
    assert out["status"] == "blocked:agent_disabled"
    assert api.agent_set_passwords == []
    blocked = [e for e in _entries(log) if e["outcome"] == "blocked:agent_disabled"]
    assert len(blocked) == 1
    assert blocked[0]["mutation"] is True


# === vmid not allowlisted ======================================================================


def test_agent_file_write_blocked_when_vmid_not_allowlisted(tmp_path, monkeypatch):
    _, api, _, log = _wire_agent(tmp_path, monkeypatch, agent_allowlist=("200",))
    out = server.pve_agent_file_write("101", "/etc/motd", "hi")
    assert out["status"] == "blocked:allowlist"
    assert api.agent_file_writes == []
    blocked = [e for e in _entries(log) if e["outcome"] == "blocked:allowlist"]
    assert len(blocked) == 1
    assert blocked[0]["mutation"] is True


def test_agent_fs_blocked_when_vmid_not_allowlisted(tmp_path, monkeypatch):
    _, api, _, log = _wire_agent(tmp_path, monkeypatch, agent_allowlist=("200",))
    out = server.pve_agent_fs("101", "fstrim")
    assert out["status"] == "blocked:allowlist"
    assert api.agent_simples == []
    blocked = [e for e in _entries(log) if e["outcome"] == "blocked:allowlist"]
    assert len(blocked) == 1
    assert blocked[0]["mutation"] is True


def test_agent_set_password_blocked_when_vmid_not_allowlisted(tmp_path, monkeypatch):
    _, api, _, log = _wire_agent(tmp_path, monkeypatch, agent_allowlist=("200",))
    out = server.pve_agent_set_password("101", "root", "sentinel-pw")
    assert out["status"] == "blocked:allowlist"
    assert api.agent_set_passwords == []
    blocked = [e for e in _entries(log) if e["outcome"] == "blocked:allowlist"]
    assert len(blocked) == 1
    assert blocked[0]["mutation"] is True
