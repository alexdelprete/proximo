"""Unit tests for ProximoAgentExecutor._dispatch (the trust-critical seam).

All tests exercise ``_dispatch`` directly — no A2A SDK plumbing required.
The ``_wire`` helper from ``test_server_plan`` is reused so the fake PVE
backend is consistent with the rest of the test suite.

Trust properties verified
-------------------------
* A mutating skill called WITHOUT confirm → returns a plan (status="plan");
  the fake API records NO mutating call (PLAN-by-default).
* Same skill WITH confirm=True → executes; the fake API records the call.
* Unknown skill id → A2AParamError.
* Missing required param → A2AParamError.
* Unknown param → A2AParamError.
* Mistyped param (int where string expected) → A2AParamError.
* A name from EXCLUDED_FROM_SLICE used as skill id → A2AParamError
  (those are server function names, not skill ids; they are absent from
  SKILLS_BY_ID).
* confirm passed as the string "true" → A2AParamError (no truthy coercion;
  the guard rejects non-bool confirm).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.a2a.executor import ProximoAgentExecutor
from proximo.a2a.skills import EXCLUDED_FROM_SLICE, A2AParamError
from proximo.audit import AuditLedger
from proximo.backends import ExecResult
from proximo.config import ProximoConfig

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
# Executor fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def executor() -> ProximoAgentExecutor:
    return ProximoAgentExecutor()


# ---------------------------------------------------------------------------
# Test: mutating skill WITHOUT confirm → plan returned, no mutation
# ---------------------------------------------------------------------------


def test_dispatch_mutating_no_confirm_returns_plan_and_no_mutation(tmp_path, monkeypatch, executor):
    """guest_power without confirm must return a plan dict and not call the API."""
    _, api, _, _, _ = _wire(tmp_path, monkeypatch, status={"status": "running", "name": "w", "uptime": 500})

    result = executor._dispatch("guest_power", {"vmid": "1975", "action": "stop"})

    assert result["status"] == "plan"
    assert api.powered == [], "mutation must NOT fire without confirm=true"


# ---------------------------------------------------------------------------
# Test: mutating skill WITH confirm=True → executes
# ---------------------------------------------------------------------------


def test_dispatch_mutating_confirm_true_executes(tmp_path, monkeypatch, executor):
    """guest_power with confirm=True must route through and record the API call."""
    _, api, _, _, _ = _wire(tmp_path, monkeypatch)

    result = executor._dispatch("guest_power", {"vmid": "1975", "action": "stop", "confirm": True})

    assert api.powered == [("1975", "stop")], "mutation must fire when confirm=true"
    # The real server returns a dict with an execution receipt (not {"status": "plan"}).
    # With the fake API, guest_power returns {"ok": True}; the key check is that
    # powered was recorded and the result is NOT a plan.
    assert result != {"status": "plan"}


# ---------------------------------------------------------------------------
# Test: unknown skill id → A2AParamError
# ---------------------------------------------------------------------------


def test_dispatch_unknown_skill_raises(executor):
    """A skill id not in SKILLS_BY_ID must raise A2AParamError."""
    with pytest.raises(A2AParamError, match="unknown skill"):
        executor._dispatch("does_not_exist", {})


# ---------------------------------------------------------------------------
# Test: missing required param → A2AParamError
# ---------------------------------------------------------------------------


def test_dispatch_missing_required_param_raises(tmp_path, monkeypatch, executor):
    """Calling guest_power without the required 'action' param must raise."""
    _wire(tmp_path, monkeypatch)

    with pytest.raises(A2AParamError, match="missing required param"):
        executor._dispatch("guest_power", {"vmid": "1975"})  # action is missing


# ---------------------------------------------------------------------------
# Test: unknown param → A2AParamError
# ---------------------------------------------------------------------------


def test_dispatch_unknown_param_raises(tmp_path, monkeypatch, executor):
    """Passing a param not declared in the skill contract must raise."""
    _wire(tmp_path, monkeypatch)

    with pytest.raises(A2AParamError, match="unknown param"):
        executor._dispatch("guest_power", {"vmid": "1975", "action": "stop", "banana": "split"})


# ---------------------------------------------------------------------------
# Test: mistyped param → A2AParamError
# ---------------------------------------------------------------------------


def test_dispatch_mistyped_param_raises(tmp_path, monkeypatch, executor):
    """Passing vmid as an integer (should be string) must raise a type error."""
    _wire(tmp_path, monkeypatch)

    with pytest.raises(A2AParamError, match="must be string"):
        executor._dispatch("guest_power", {"vmid": 1975, "action": "stop"})  # vmid is int, not str


# ---------------------------------------------------------------------------
# Test: EXCLUDED_FROM_SLICE name used as skill id → A2AParamError
# ---------------------------------------------------------------------------


def test_dispatch_excluded_name_as_skill_id_raises(executor):
    """Names in EXCLUDED_FROM_SLICE are server fn names, not skill ids.
    SKILLS_BY_ID will not contain them; the unknown-skill guard fires.
    """
    for excluded in EXCLUDED_FROM_SLICE:
        with pytest.raises(A2AParamError, match="unknown skill"):
            executor._dispatch(excluded, {})


# ---------------------------------------------------------------------------
# Test: confirm as string "true" → A2AParamError (no truthy coercion)
# ---------------------------------------------------------------------------


def test_dispatch_confirm_string_true_raises(tmp_path, monkeypatch, executor):
    """confirm='true' (a string) must be rejected — only bool True is valid."""
    _wire(tmp_path, monkeypatch)

    with pytest.raises(A2AParamError, match="boolean"):
        executor._dispatch("guest_power", {"vmid": "1975", "action": "stop", "confirm": "true"})
