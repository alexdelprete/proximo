"""Confirm=True sweep — pdm_fleet wrapper welds (src/proximo/tools/pdm_fleet.py).

Closes the coverage-audit gap (`.scratch/2026-07-14-tool-coverage-audit-findings.json`, module
`src/proximo/tools/pdm_fleet.py`): two findings.

1. (high) The confirm=True execution branch of `_migrate` and `_snapshot_delete` — the code
   that actually calls `pdm.guest_migrate` / `pdm.snapshot_delete` and records
   outcome="submitted" — was never exercised by any test, for either kind, across all 4 tool
   endpoints (pdm_pve_{qemu,lxc}_migrate, pdm_pve_{qemu,lxc}_snapshot_delete). Sibling tools with
   the identical shape (_power, _remote_migrate, _snapshot_create, _snapshot_rollback) already
   had confirm=True coverage in tests/test_pdm_fleet.py — these two did not.
2. (med) The lxc-kind top-level tools were never invoked with confirm=True at all — only their
   qemu siblings were (tests/test_pdm_fleet.py calls pdm_pve_qemu_remote_migrate etc., never the
   lxc entry points). pdm_pve_lxc_remote_migrate is added here to close that end-to-end wiring
   gap for the tool named explicitly in the findings.

Mirrors the `_wire()` idiom in tests/test_server_plan.py:110-131 (already re-used and
review-approved in tests/test_confirm_sweep_pve_backup.py and siblings), extended for the `_pdm`
seam exactly as tests/test_pdm_fleet.py's own `_wire()`/`_FakePdm` do: `proximo.server._pdm` is
monkeypatched to a fake PDM backend + a REAL AuditLedger in tmp_path, so each confirm=True call
proves three welds:
  1. return shape — status is the EXECUTED shape ("submitted"), never "plan" (every PDM fleet
     mutation is task-backed);
  2. the fake PDM backend captured the underlying call (verb-shaped tuple, reusing the
     `pdm.calls` idiom from tests/test_pdm_fleet.py's `_FakePdm`);
  3. the ledger recorded a confirmed mutation — structural asserts only (action, mutation,
     outcome, detail.confirmed), never exact prose.

A second group of dedicated tests, called out explicitly by the audit-fixes plan (Task 8):
`_pdm_wait_task`'s two fail-closed branches (pdm_fleet.py:44-56) — a task that finishes with
exitstatus != 'OK', and a task that never reaches status=='stopped' before the poll-retry
loop's deadline. Both back `_pdm_auto_undo`, the safety-snapshot-before-rollback primitive: the
comment at pdm_fleet.py:46 claims "Fail-closed: only an explicit exitstatus 'OK' passes," but
until now nothing proved it — the only existing failure test (test_rollback_fail_closed_when_
safety_snapshot_fails in test_pdm_fleet.py) makes snapshot_create itself raise, never letting it
succeed while the WAIT afterward reports failure or hangs. These tests drive the real caller
(the `pdm_pve_qemu_snapshot_rollback` tool, confirm=True) so what's asserted is what the caller
actually sees and what actually lands in the ledger — not `_pdm_wait_task` in isolation.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig


class _FakePdm:
    """Records mutation calls; guest_status feeds the planner, task_status the auto-undo wait.

    Same shape as tests/test_pdm_fleet.py's `_FakePdm` (same method set, same call-tuple verb
    tags), but Task 12 (tighten) widens each capture tuple to the FULL argument list the real
    caller passes -- not just the subset that sibling file's tuples happened to record -- so
    `assert pdm.calls[-1] == expected_call` (exact tuple equality) actually proves nothing extra
    (e.g. a `target_storage` PdmBackend.guest_migrate accepts per Task 8 Fix B, but pdm_fleet.py's
    _migrate() deliberately does NOT forward -- "Do NOT wire it into the tool layer") reaches the
    backend, matching the dict-exact welds on the PVE/PBS planes.
    """

    def __init__(self, status: str = "running"):
        self._status = status
        self.calls: list = []

    def guest_status(self, remote, kind, vmid):
        return {"status": self._status, "name": "web1"}

    def guest_power(self, remote, kind, vmid, action):
        self.calls.append(("power", remote, kind, vmid, action))
        return "UPID:power"

    def guest_migrate(self, remote, kind, vmid, target, online=False, target_storage=None):
        self.calls.append(("migrate", remote, kind, vmid, target, online, target_storage))
        return "UPID:migrate"

    def guest_remote_migrate(self, remote, kind, vmid, target_remote, target_bridge,
                             target_storage, target_vmid=None, online=False, delete=False):
        self.calls.append(("rmig", remote, kind, vmid, target_remote, target_bridge,
                           target_storage, target_vmid, online, delete))
        return "UPID:rmig"

    def snapshot_create(self, remote, kind, vmid, snapname, description=None, vmstate=False):
        self.calls.append(("snapc", remote, kind, vmid, snapname, description, vmstate))
        return "UPID:snapc"

    def snapshot_delete(self, remote, kind, vmid, snapname):
        self.calls.append(("snapd", remote, kind, vmid, snapname))
        return "UPID:snapd"

    def snapshot_rollback(self, remote, kind, vmid, snapname):
        self.calls.append(("rollback", remote, kind, vmid, snapname))
        return "UPID:rollback"

    def task_status(self, remote, upid):
        return {"status": "stopped", "exitstatus": "OK"}


def _wire(tmp_path, monkeypatch, pdm=None):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(api_base_url="https://x:8006/api2/json", node="pve",
                        token_path="/run/x", audit_log_path=log)
    ledger = AuditLedger(log)
    pdm = pdm or _FakePdm()
    monkeypatch.setattr(server, "_svc", lambda: (cfg, SimpleNamespace(), SimpleNamespace(), ledger))
    monkeypatch.setattr(server, "_pdm", lambda: (SimpleNamespace(), pdm))
    return pdm, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _confirmed_entry(log: str, action: str, outcome: str) -> dict:
    entries = [e for e in _entries(log) if e["action"] == action and e["outcome"] == outcome]
    assert len(entries) == 1, f"expected exactly one {action!r}/{outcome!r} ledger entry, got {entries}"
    return entries[0]


# ---------------------------------------------------------------------------
# Finding 1 (high) + Finding 2 (med) — table-driven over the previously-uncovered confirm=True
# execution paths: _migrate and _snapshot_delete for BOTH kinds, plus pdm_pve_lxc_remote_migrate
# (its qemu sibling is already covered by test_pdm_fleet.py::test_remote_migrate_confirm_
# reaches_backend, but the lxc entry point itself had zero confirm=True coverage anywhere).
# ---------------------------------------------------------------------------

_SWEEP_CASES = [
    pytest.param(
        "pdm_pve_qemu_migrate",
        dict(remote="dc1", vmid="100", target="node2"),
        # target_storage is never forwarded by _migrate() (Task 8 Fix B: "Do NOT wire it into
        # the tool layer") -- the trailing None is that absence, proven exact.
        ("migrate", "dc1", "qemu", "100", "node2", False, None),
        id="qemu_migrate",
    ),
    pytest.param(
        "pdm_pve_lxc_migrate",
        dict(remote="dc1", vmid="201", target="node2"),
        ("migrate", "dc1", "lxc", "201", "node2", False, None),
        id="lxc_migrate",
    ),
    pytest.param(
        "pdm_pve_qemu_migrate",
        dict(remote="dc1", vmid="100", target="node2", online=True),
        ("migrate", "dc1", "qemu", "100", "node2", True, None),
        id="qemu_migrate_online",
    ),
    pytest.param(
        "pdm_pve_qemu_snapshot_delete",
        dict(remote="dc1", vmid="100", snapname="snap1"),
        ("snapd", "dc1", "qemu", "100", "snap1"),
        id="qemu_snapshot_delete",
    ),
    pytest.param(
        "pdm_pve_lxc_snapshot_delete",
        dict(remote="dc1", vmid="201", snapname="snap1"),
        ("snapd", "dc1", "lxc", "201", "snap1"),
        id="lxc_snapshot_delete",
    ),
    pytest.param(
        "pdm_pve_lxc_remote_migrate",
        dict(remote="dc1", vmid="201", target_remote="dc2", target_bridge="vmbr0:vmbr0",
             target_storage="local:local"),
        # target_vmid=None, online=False are the tool's own defaults (not passed by this case).
        ("rmig", "dc1", "lxc", "201", "dc2", "vmbr0:vmbr0", "local:local", None, False, False),
        id="lxc_remote_migrate",
    ),
    # The remaining two lxc entry points named by the same med finding: their shared bodies
    # (_snapshot_create/_snapshot_rollback) are confirm=True-covered via the qemu siblings in
    # tests/test_pdm_fleet.py, but the lxc top-level wrappers themselves were never executed
    # with confirm=True anywhere — this is the end-to-end wiring proof.
    pytest.param(
        "pdm_pve_lxc_snapshot_create",
        dict(remote="dc1", vmid="201", snapname="snap1"),
        # description=None (not passed); vmstate is hardcoded False by the lxc wrapper itself
        # (containers have no RAM state -- pdm_pve_lxc_snapshot_create has no vmstate param).
        ("snapc", "dc1", "lxc", "201", "snap1", None, False),
        id="lxc_snapshot_create",
    ),
    # Happy path: _pdm_auto_undo's safety snapshot fires first (snapc) and _FakePdm.task_status
    # reports stopped/OK, satisfying _pdm_wait_task — so calls[-1] is the trailing rollback.
    # (The fail-closed variants of that wait live in the dedicated tests below.)
    pytest.param(
        "pdm_pve_lxc_snapshot_rollback",
        dict(remote="dc1", vmid="201", snapname="snap1"),
        ("rollback", "dc1", "lxc", "201", "snap1"),
        id="lxc_snapshot_rollback",
    ),
]


@pytest.mark.parametrize("tool_name,kwargs,expected_call", _SWEEP_CASES)
def test_confirm_true_executes_forwards_and_records(tmp_path, monkeypatch, tool_name, kwargs, expected_call):
    """confirm=True executes (never 'plan'), the fake PDM backend captured the forwarded call,
    and the ledger recorded a confirmed mutation — the three welds the audit found untested."""
    pdm, _, log = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)

    out = fn(confirm=True, **kwargs)

    # weld 1: return shape is the EXECUTED shape, never "plan" — every PDM fleet mutation is
    # task-backed, so the honest outcome is always "submitted", never "ok".
    assert out["status"] == "submitted"
    assert out["status"] != "plan"

    # weld 2: the fake PDM backend captured the underlying call
    assert pdm.calls, f"{tool_name} confirm=True never reached the fake PDM backend"
    assert pdm.calls[-1] == expected_call

    # weld 3: ledger structural asserts — never exact prose
    entry = _confirmed_entry(log, tool_name, "submitted")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


# ---------------------------------------------------------------------------
# `_pdm_wait_task` fail-closed branches (pdm_fleet.py:44-56), backing `_pdm_auto_undo`'s
# safety-snapshot-before-rollback. Driven through the real caller (pdm_pve_qemu_snapshot_rollback,
# confirm=True) so what's asserted is what a real confirm actually produces: the rollback itself
# must NEVER fire, the tool must return the fail-closed envelope, and the ledger must carry the
# blocked mutation with the resolved error type.
# ---------------------------------------------------------------------------

class _BadExitPdm(_FakePdm):
    """The safety snapshot_create call itself succeeds (returns a UPID) and the task DOES reach
    status=='stopped' — but with an exitstatus other than 'OK'. This is the branch at
    pdm_fleet.py:51-52: `if st.get("exitstatus") != "OK": raise RuntimeError(...)`."""

    def task_status(self, remote, upid):
        return {"status": "stopped", "exitstatus": "storage error: snapshot create failed"}


def test_wait_task_bad_exitstatus_blocks_rollback_and_records_fail_closed(tmp_path, monkeypatch):
    pdm, _, log = _wire(tmp_path, monkeypatch, pdm=_BadExitPdm())

    out = server.pdm_pve_qemu_snapshot_rollback("dc1", "100", "snap1", confirm=True)

    assert out["status"] == "blocked:undo_unavailable"
    # the safety snapshot was attempted (snapc) but the DESTRUCTIVE rollback must NEVER fire
    # when the task backing it did not confirm success.
    kinds = [c[0] for c in pdm.calls]
    assert "snapc" in kinds
    assert "rollback" not in kinds

    entry = _confirmed_entry(log, "pdm_pve_qemu_snapshot_rollback", "blocked:undo_unavailable")
    assert entry["mutation"] is True
    assert entry["detail"]["error"] == "RuntimeError"


class _HangingPdm(_FakePdm):
    """The safety snapshot task never reaches status=='stopped' — the poll-retry loop's own
    deadline branch (pdm_fleet.py:54-56)."""

    def task_status(self, remote, upid):
        return {"status": "running"}


def test_wait_task_never_finishes_blocks_rollback_and_records_fail_closed(tmp_path, monkeypatch):
    """The module's real defaults are a 120s timeout / 2s poll interval — control the clock so
    the deadline is crossed in a handful of calls instead of two real minutes of wall time.
    Only `time.monotonic`/`time.sleep` are patched (module-global, since pdm_fleet.py does a
    plain `import time`); nothing else on this call path reads the monotonic clock — the opt-in
    gates _pdm_auto_undo also clears (contain/scope/lease/envelope/consent) use time.time(), a
    different function, and are inert here anyway (none of their env vars are set)."""
    pdm, _, log = _wire(tmp_path, monkeypatch, pdm=_HangingPdm())

    clock = {"t": 0.0}

    def fake_monotonic():
        clock["t"] += 100.0  # jump well past the 120s deadline within 2-3 calls
        return clock["t"]

    monkeypatch.setattr(time, "monotonic", fake_monotonic)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)

    out = server.pdm_pve_qemu_snapshot_rollback("dc1", "100", "snap1", confirm=True)

    assert out["status"] == "blocked:undo_unavailable"
    kinds = [c[0] for c in pdm.calls]
    assert "snapc" in kinds
    assert "rollback" not in kinds

    entry = _confirmed_entry(log, "pdm_pve_qemu_snapshot_rollback", "blocked:undo_unavailable")
    assert entry["mutation"] is True
    assert entry["detail"]["error"] == "RuntimeError"
