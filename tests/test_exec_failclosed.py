"""Fail-closed regression tests for the exec/audit core (2026-07-14 audit, Task 9).

The highest-value safety tests of the sweep: the paths where a real mistake means a mutation
runs when it should have refused. Covers server.py findings (2 high / 5 med):

- ct_psql: the undo-snapshot-unavailable fail-closed path (mirrors ct_exec's dedicated trio in
  tests/test_server_plan.py) and the exec-disabled refuse-BEFORE-planning gate.
- pve_agent_exec: its OWN wrapper-local taint-marker-write-failure guard (server.py ~822-833) —
  this tool never routes through `_audited()`, so it carries a hand-copied version of that
  guard that needs its own coverage — plus the 'agent exec returned no pid' malformed-response
  ValueError.
- `_wait_task`: its own deadline-timeout branch (the polled task never reaches status=='stopped'),
  distinct from the existing task_ok=False/None fixtures (which return 'stopped' immediately with
  a bad/missing exitstatus — a different code path).
- `audit_verify`: the off-box anchor's truncation/wipe alarm hint (fewer live entries than the
  pinned count), and fail-closed refusal when the anchor sink's own `last_pin()` raises.

Fakes are local and self-contained, mirroring tests/test_server_plan.py's `_wire()`/`_FakeApi`
idiom (extended here with the qemu-agent methods pve_agent_exec needs) and
tests/test_prove_anchor.py's `_wire_audit`/FileSink idiom for the audit_verify anchor tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.audit_anchor import AnchorError, FileSink
from proximo.backends import ExecResult, ProximoError
from proximo.config import ProximoConfig


class _FakeApi:
    """Same shape as test_server_plan.py's _FakeApi (guest status + snapshot/task machinery for
    the ct_exec/ct_psql auto-undo path), extended with the qemu-agent methods pve_agent_exec
    needs and a `task_never_stops` knob for _wait_task's own deadline branch."""

    def __init__(self, status=None, *, snapshot_raises=False, task_ok=True,
                 task_never_stops=False, agent_exec_returns=None,
                 agent_exec_status_returns=None):
        self._status = status or {"status": "running", "name": "web", "uptime": 500}
        self.config = SimpleNamespace(node="pve")
        self.created: list[tuple] = []
        self._snapshot_raises = snapshot_raises
        self._task_ok = task_ok
        self._task_never_stops = task_never_stops
        self.agent_execs: list = []
        self.agent_exec_statuses: list = []
        self._agent_exec_returns = agent_exec_returns if agent_exec_returns is not None else {"pid": 999}
        self._agent_exec_status_returns = agent_exec_status_returns or {
            "exited": True, "exitcode": 0, "out-data": "", "err-data": "",
        }

    def guest_status(self, vmid, kind="lxc", node=None):
        return self._status

    def snapshot_create(self, vmid, snapname, kind="lxc", node=None, description=None):
        if self._snapshot_raises:
            raise RuntimeError("storage does not support snapshots")
        self.created.append((vmid, snapname))
        return "UPID:create"

    def task_status(self, upid, node=None):
        if self._task_never_stops:
            return {"status": "running"}
        return {"status": "stopped", "exitstatus": "OK" if self._task_ok else "boom: task failed"}

    def agent_exec(self, vmid, node, command):
        self.agent_execs.append((vmid, node, command))
        return dict(self._agent_exec_returns)

    def agent_exec_status(self, vmid, node, pid):
        self.agent_exec_statuses.append((vmid, node, pid))
        return dict(self._agent_exec_status_returns)


class _FakeExec:
    def __init__(self):
        self.ran: list = []

    def run(self, ctid, command, timeout=60):
        self.ran.append((ctid, command))
        return ExecResult(str(ctid), " ".join(command), 0, "out", "")

    def psql(self, ctid, sql, db="postgres", user="postgres", timeout=60):
        self.ran.append((ctid, sql))
        return ExecResult(str(ctid), sql, 0, "out", "")


def _wire(tmp_path, monkeypatch, *, status=None, enable_exec=True, allowlist=("*",),
          snapshot_raises=False, task_ok=True, task_never_stops=False,
          enable_agent=False, agent_allowlist=("*",),
          agent_exec_returns=None, agent_exec_status_returns=None):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        ct_allowlist=frozenset(allowlist), enable_exec=enable_exec, audit_log_path=log,
        enable_agent=enable_agent, agent_allowlist=frozenset(agent_allowlist),
    )
    api = _FakeApi(status, snapshot_raises=snapshot_raises, task_ok=task_ok,
                   task_never_stops=task_never_stops, agent_exec_returns=agent_exec_returns,
                   agent_exec_status_returns=agent_exec_status_returns)
    exec_ = _FakeExec()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, exec_, ledger))
    return cfg, api, exec_, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# === A: ct_psql fail-closed (mirrors ct_exec's dedicated trio in test_server_plan.py) ========


def test_ct_psql_auto_undo_fail_closed_when_snapshot_fails(tmp_path, monkeypatch):
    """ct_psql's undo-snapshot-unavailable path had ZERO test coverage while its ct_exec sibling
    has three dedicated failure tests (test_server_plan.py). The SQL must NOT run when the undo
    net can't be hung."""
    _, api, exec_, _, log = _wire(tmp_path, monkeypatch, enable_exec=True, snapshot_raises=True)
    out = server.ct_psql("105", "DELETE FROM t", snapshot=True, confirm=True)
    assert out["status"] == "blocked:undo_unavailable"
    assert exec_.ran == []  # SQL must NOT run if the undo net can't be hung
    assert api.created == []
    assert any(e["outcome"] == "blocked:undo_unavailable" for e in _entries(log))


def test_ct_psql_disabled_refuses_before_planning(tmp_path, monkeypatch):
    """The safe default (exec disabled) must refuse ct_psql BEFORE a plan is built at all — no
    'planned' ledger entry — matching the coverage ct_exec already has for the identical gate
    (test_ct_exec_disabled_wins_over_plan)."""
    _, _, exec_, _, log = _wire(tmp_path, monkeypatch, enable_exec=False)
    out = server.ct_psql("105", "SELECT 1")
    assert out["status"] == "blocked:exec_disabled"  # safe default still refuses before planning
    assert exec_.ran == []
    entries = _entries(log)
    assert not any(e["outcome"] == "planned" for e in entries), (
        "ct_psql built a plan before checking enable_exec — refusal must precede planning"
    )


# === B: pve_agent_exec — its own manual-audit-path fail-closed guards ========================


def test_pve_agent_exec_taint_mark_failure_fails_closed(tmp_path, monkeypatch):
    """pve_agent_exec never routes through `_audited()` (it is the one manual-audit-path tool),
    so it carries its OWN copy of the taint-marker-write-failure guard (server.py ~822-833). A
    marker-write failure must refuse BEFORE the real guest exec fires, record
    blocked:taint_mark_failed, and re-raise — never hand back untracked guest output."""
    _, api, _, _, log = _wire(tmp_path, monkeypatch, enable_agent=True, agent_allowlist=("101",))
    monkeypatch.setattr(server, "taint_tracking_on", lambda: True)

    def _boom(*a, **k):
        raise OSError("marker dir unwritable")

    monkeypatch.setattr(server, "mark_tainted", _boom)

    with pytest.raises(ProximoError, match="fail-closed"):
        server.pve_agent_exec("101", ["echo", "hi"], confirm=True)

    assert api.agent_execs == []  # guest exec must NOT run
    blocked = [e for e in _entries(log) if e["outcome"] == "blocked:taint_mark_failed"]
    assert len(blocked) == 1
    assert blocked[0]["mutation"] is True
    assert blocked[0]["target"] == "qemu/101"


def test_pve_agent_exec_no_pid_raises_value_error(tmp_path, monkeypatch):
    """A malformed qemu-agent response (missing 'pid') must surface loudly — never silently
    treated as though a real process id had started."""
    _, api, _, _, log = _wire(tmp_path, monkeypatch, enable_agent=True, agent_allowlist=("101",),
                              agent_exec_returns={})
    with pytest.raises(ValueError, match="no pid"):
        server.pve_agent_exec("101", ["echo", "hi"], confirm=True)
    assert api.agent_execs == [("101", None, ["echo", "hi"])]  # the exec call itself DID fire
    errs = [e for e in _entries(log)
            if e["action"] == "pve_agent_exec" and e["outcome"] == "error"]
    assert len(errs) == 1  # the malformed response is still traced, not silently dropped


# === C: _wait_task — its own deadline-timeout branch =========================================
# Distinct from the existing task_ok=False/None fixtures, which report status=='stopped'
# immediately with a bad/missing exitstatus (server.py's "stopped but not OK" branch). This is
# the OTHER branch: the task never reports 'stopped' at all before the deadline.


def test_wait_task_deadline_timeout_raises_without_hanging(monkeypatch):
    """Direct unit test of _wait_task's own timeout branch. Fakes the clock so the test does not
    spend real wall-clock time waiting out the deadline (mirrors tests/test_qemu_agent.py's
    `monkeypatch.setattr(server.time, "sleep", ...)` polling idiom)."""

    class _NeverStopsApi:
        def task_status(self, upid, node=None):
            return {"status": "running"}

    clock = {"t": 0.0}
    monkeypatch.setattr(server.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(server.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))

    with pytest.raises(ProximoError, match="timed out"):
        server._wait_task(_NeverStopsApi(), "UPID:x", timeout=5, interval=2)


def test_ct_exec_auto_undo_fail_closed_when_wait_task_deadline_times_out(tmp_path, monkeypatch):
    """The caller-visible failure: when the auto-undo snapshot task never reaches 'stopped'
    before the deadline, ct_exec must fail closed exactly as it does for a bad-exitstatus task —
    the command must NOT run. Fakes the clock so the (real, 120s-default) deadline doesn't
    actually block the test."""
    _, api, exec_, _, log = _wire(tmp_path, monkeypatch, enable_exec=True, task_never_stops=True)
    clock = {"t": 0.0}
    monkeypatch.setattr(server.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(server.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))

    out = server.ct_exec("105", ["rm", "-rf", "/x"], snapshot=True, confirm=True)
    assert out["status"] == "blocked:undo_unavailable"
    assert exec_.ran == []
    assert any(e["outcome"] == "blocked:undo_unavailable" for e in _entries(log))


# === D: audit_verify — off-box anchor alarm hints + fail-closed anchor-read refusal ===========


def _truncate_last_entry(log_path: Path) -> None:
    lines = log_path.read_text().splitlines()
    log_path.write_text(("\n".join(lines[:-1]) + "\n") if len(lines) > 1 else "")


def test_audit_verify_anchor_shrink_surfaces_truncation_alarm(monkeypatch, tmp_path):
    """Fewer LIVE entries than the pinned count is a genuine truncation/wipe signal, distinct
    from the benign forward-growth branch (already covered in test_prove_anchor.py). The
    existing truncation regression there (test_audit_verify_truncation_does_not_poison_pin)
    publishes the pin WITHOUT `entries=`, which collapses into the generic first-pin wording
    instead of this alarm — publish WITH entries= here to actually hit the shrink branch."""
    log_path = tmp_path / "audit.log"
    sink = FileSink(str(tmp_path / "anchor.json"))
    led = AuditLedger(str(log_path))
    led.record("a", target="t1")
    led.record("b", target="t2")
    led.record("c", target="t3")
    pinned = led.head()
    sink.publish(pinned, "t0", "pve", str(log_path), entries=3)  # pin BOTH head and count at 3

    _truncate_last_entry(log_path)  # ledger now has 2 entries and a different (shorter) head

    cfg = SimpleNamespace(expected_head=None, node="pve", anchor_sink=sink)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, None, None, led))

    out = server.audit_verify()

    assert out["anchor_hint"] is not None
    hint = out["anchor_hint"].lower()
    assert "truncation" in hint or "wipe" in hint
    assert sink.last_head() == pinned  # anti-poisoning: pin still not overwritten


def test_audit_verify_anchor_last_pin_failure_fails_closed(monkeypatch, tmp_path):
    """If the anchor sink's own last_pin() read raises AnchorError (sink unreachable), audit_verify
    must refuse (fail-closed) rather than silently skip the anchor check and report a green verify.
    Distinct from test_audit_verify_anchor_publish_failure_fails_closed (test_prove_anchor.py),
    which only breaks publish() — this breaks the earlier last_pin() read."""

    class _UnreadableSink(FileSink):
        def last_pin(self):
            raise AnchorError("sink unreachable")

    sink = _UnreadableSink(str(tmp_path / "anchor.json"))
    log_path = tmp_path / "audit.log"
    led = AuditLedger(str(log_path))
    led.record("a", target="t1")

    cfg = SimpleNamespace(expected_head=None, node="pve", anchor_sink=sink)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, None, None, led))

    with pytest.raises(ProximoError, match="(?i)anchor"):
        server.audit_verify()
