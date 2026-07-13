"""The A2A face over the governed core — trust properties through ``call_governed``.

The A2A face exposes the FULL tool surface and routes every call through ``governed.call_governed``
— the same spine path an MCP client takes. These tests reuse the fake PVE backend harness (``_wire``,
also imported by test_a2a_integration.py) to prove, at the governed level:

* A mutating tool WITHOUT confirm → no mutation fires (PLAN-by-default), even on the "dangerous
  plane" the old 16-skill slice used to hide.
* WITH confirm=True → the mutation fires.
* The whole surface is reachable — a previously-EXCLUDED tool dispatches (governed, not curated out).

Param/existence/error mapping is pinned transport-agnostically in test_governed.py; the executor's
full async execute() path is covered in test_a2a_integration.py.
"""

from __future__ import annotations

from types import SimpleNamespace

import anyio

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.backends import ExecResult
from proximo.config import ProximoConfig
from proximo.governed import call_governed

# ---------------------------------------------------------------------------
# Shared helpers (mirror of test_server_plan._FakeApi / _wire)
# ---------------------------------------------------------------------------


class _FakeApi:
    def __init__(self, status: dict, *, snaps=None, task_ok=True):
        self._status = status
        self.config = SimpleNamespace(node="pve")
        self.powered: list[tuple] = []
        self.snaps = snaps if snaps is not None else []
        self.created: list[tuple] = []
        self.rolled: list[tuple] = []
        self.deleted: list[tuple] = []
        self._task_ok = task_ok
        self.guests: list[dict] = []
        self.gets: list = []
        self.posts: list = []
        self.dels: list = []

    def guest_status(self, vmid, kind="lxc", node=None):
        return self._status

    def guest_power(self, vmid, action, kind="lxc", node=None):
        self.powered.append((vmid, action))
        return {"ok": True}

    def snapshot_list(self, vmid, kind="lxc", node=None):
        return self.snaps

    def snapshot_create(self, vmid, snapname, kind="lxc", node=None, description=None):
        self.created.append((vmid, snapname))
        return "UPID:create"

    def snapshot_rollback(self, vmid, snapname, kind="lxc", node=None):
        self.rolled.append((vmid, snapname))
        return "UPID:rollback"

    def snapshot_delete(self, vmid, snapname, kind="lxc", node=None, force=False):
        self.deleted.append((vmid, snapname))
        return "UPID:delete"

    def task_status(self, upid, node=None):
        return {"status": "stopped", "exitstatus": "OK" if self._task_ok else "boom: task failed"}

    def node_status(self, node=None):
        return {"uptime": 1000, "memory": {"used": 1, "total": 100}}

    def node_storage(self, node=None):
        return [{"storage": "local", "used": 1, "total": 100}]

    def node_tasks(self, node=None, limit=50):
        return []

    def list_guests(self, node=None):
        return self.guests

    def _get(self, path):
        self.gets.append(path)
        return []

    def _post(self, path, data=None):
        self.posts.append((path, data))
        return "UPID:post"

    def _delete(self, path, params=None):
        self.dels.append((path, params))
        return "UPID:del"


class _FakeExec:
    def __init__(self):
        self.ran: list = []

    def run(self, ctid, command, timeout=60):
        self.ran.append((ctid, command))
        return ExecResult(str(ctid), " ".join(command), 0, "out", "")

    def psql(self, ctid, sql, db="postgres", user="postgres", timeout=60):
        self.ran.append((ctid, sql))
        return ExecResult(str(ctid), sql, 0, "out", "")


def _wire(tmp_path, monkeypatch, *, status=None, enable_exec=True, allowlist=("*",), task_ok=True):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        ct_allowlist=frozenset(allowlist), enable_exec=enable_exec, audit_log_path=log,
    )
    api = _FakeApi(status or {"status": "running", "name": "web", "uptime": 500}, task_ok=task_ok)
    exec_ = _FakeExec()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, exec_, ledger))
    return cfg, api, exec_, ledger, log


# ---------------------------------------------------------------------------
# PLAN-by-default and the full surface, through the governed path
# ---------------------------------------------------------------------------


def test_governed_mutating_no_confirm_plans_and_does_not_mutate(tmp_path, monkeypatch):
    _, api, _, _, _ = _wire(tmp_path, monkeypatch, status={"status": "running", "name": "w", "uptime": 9})
    anyio.run(call_governed, "pve_guest_power", {"vmid": "1975", "action": "stop"})
    assert api.powered == [], "no-confirm call must NOT mutate (PLAN-by-default over the governed path)"


def test_governed_mutating_confirm_true_executes(tmp_path, monkeypatch):
    _, api, _, _, _ = _wire(tmp_path, monkeypatch)
    anyio.run(call_governed, "pve_guest_power", {"vmid": "1975", "action": "stop", "confirm": True})
    assert api.powered == [("1975", "stop")], "explicit confirm=true must execute"


def test_governed_full_surface_reaches_formerly_excluded_tool(tmp_path, monkeypatch):
    # pve_delete_guest was EXCLUDED from the old 16-skill A2A slice. It is now governed, not hidden —
    # so it must be REACHABLE (never a 404). Whether the fake backend lets it plan or errors is not
    # the point; that the dangerous plane is on the surface at all is.
    from proximo.governed import GovernedError

    _wire(tmp_path, monkeypatch)
    try:
        anyio.run(call_governed, "pve_delete_guest", {"vmid": "1975"})
    except GovernedError as e:
        assert e.status != 404, "the dangerous plane must be reachable over A2A, not curated out"
