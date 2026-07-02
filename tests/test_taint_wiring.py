"""Stage S2 — taint wired into `_audited` (the choke point every read AND every tools/*.py
mutation passes through) and into the manual-audit-path exec tool `pve_agent_exec`.

Design: `.scratch/taint-design-v2-2026-07-02.md` §Component 1 & 2. Harness mirrors
test_contain.py/test_lease.py/test_envelope.py's `_wire_server`/`_wire_with_backends` idiom: a
REAL `AuditLedger` backed by `tmp_path`, `proximo.server._svc` monkeypatched to return it, so
`server._audited(...)` (and the real tool functions) exercise the genuine code path.

`ct_exec`/`ct_psql` are NOT re-tested here for taint-marking/fencing beyond a couple of
end-to-end sanity checks: their guest-output-carrying execution already flows through
`_audited(mutation=True)` (see server.py ~487, ~540), so the `_audited`-level tests below cover
them by construction. `pve_agent_exec` is the one true manual-audit-path exception (never calls
`_audited` — see server.py:722-724) and gets its own direct section.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import proximo.server as server
from proximo import taint
from proximo.audit import AuditLedger
from proximo.backends import ExecResult, ProximoError
from proximo.config import ProximoConfig


def _wire_server(tmp_path, monkeypatch):
    """Wire proximo.server with a real ledger (tmp_path) and no live backends."""
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json",
        node="pve",
        token_path=str(tmp_path / "pve-token"),
        audit_log_path=log,
        audit_keyed=False,
    )
    led = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, None, None, led))
    return led, log


class _FakeApi:
    """Minimal API spy for pve_agent_exec's manual-audit path."""

    def __init__(self, *, exited=True, exitcode=0, out_data="guest output", err_data=""):
        self.agent_execs: list = []
        self.agent_exec_statuses: list = []
        self._exited = exited
        self._exitcode = exitcode
        self._out_data = out_data
        self._err_data = err_data

    def agent_exec(self, vmid, node, command):
        self.agent_execs.append((vmid, node, command))
        return {"pid": 4242}

    def agent_exec_status(self, vmid, node, pid):
        self.agent_exec_statuses.append((vmid, node, pid))
        return {
            "exited": self._exited,
            "exitcode": self._exitcode,
            "out-data": self._out_data,
            "err-data": self._err_data,
        }


class _RaisingApi:
    def agent_exec(self, vmid, node, command):
        raise ProximoError("guest exec blew up: attacker-controlled-stderr-lookalike")


def _wire_with_backends(tmp_path, monkeypatch, *, api, enable_agent=True,
                        agent_allowlist=frozenset({"101"})):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log, audit_keyed=False,
        enable_agent=enable_agent, agent_allowlist=agent_allowlist,
    )
    led = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, None, led))
    return cfg, led, log


def _entries(log_path) -> list[dict]:
    return [json.loads(ln) for ln in Path(log_path).read_text().splitlines() if ln.strip()]


_TAINT_ENV = (taint.TAINT_TRACK_ENV, taint.FORBID_ENV, taint.REQUIRE_CONSENT_ENV, taint.FENCE_ENV)


@pytest.fixture(autouse=True)
def _clean_taint_env(monkeypatch):
    for var in _TAINT_ENV:
        monkeypatch.delenv(var, raising=False)
    yield


# === `_audited` — READ path ======================================================================


def test_adversarial_read_with_tracking_on_sets_marker_and_ledger_detail(tmp_path, monkeypatch):
    monkeypatch.setenv(taint.TAINT_TRACK_ENV, "1")
    led, log = _wire_server(tmp_path, monkeypatch)
    audit_dir = str(tmp_path)
    assert taint.is_tainted(audit_dir) is False

    result = server._audited("ct_logs", "lxc/105", lambda: {"stdout": "guest bytes"},
                             detail={"unit": "sshd"})

    assert result == {"stdout": "guest bytes"}  # fence is OFF -> unchanged shape
    assert taint.is_tainted(audit_dir) is True
    assert taint.taint_sources(audit_dir) == ["ct_logs"]

    entries = _entries(log)
    assert len(entries) == 1
    assert entries[0]["action"] == "ct_logs"
    assert entries[0]["detail"]["unit"] == "sshd"  # existing detail preserved
    assert entries[0]["detail"]["untrusted"] is True
    assert entries[0]["detail"]["content_trust"] == "adversarial"


def test_adversarial_read_tracking_off_by_default_is_inert(tmp_path, monkeypatch):
    """No PROXIMO_TAINT_* env set -> default surface completely unchanged: no marker, no
    'untrusted' ledger key."""
    led, log = _wire_server(tmp_path, monkeypatch)
    audit_dir = str(tmp_path)

    result = server._audited("ct_logs", "lxc/105", lambda: {"stdout": "guest bytes"})

    assert result == {"stdout": "guest bytes"}
    assert taint.is_tainted(audit_dir) is False
    entries = _entries(log)
    assert "untrusted" not in entries[0]["detail"]
    assert "content_trust" not in entries[0]["detail"]


def test_nonadversarial_read_never_taints_even_with_tracking_on(tmp_path, monkeypatch):
    monkeypatch.setenv(taint.TAINT_TRACK_ENV, "1")
    led, log = _wire_server(tmp_path, monkeypatch)
    audit_dir = str(tmp_path)

    result = server._audited("pve_node_status", "node/pve", lambda: {"status": "online"})

    assert result == {"status": "online"}
    assert taint.is_tainted(audit_dir) is False
    entries = _entries(log)
    assert "untrusted" not in entries[0]["detail"]


def test_adversarial_read_that_raises_still_taints(tmp_path, monkeypatch):
    """Taint is set BEFORE fn() runs, so a read that RAISES still taints (error bodies can carry
    payload too) — and the error-path ledger entry also carries the untrusted stamp."""
    monkeypatch.setenv(taint.TAINT_TRACK_ENV, "1")
    led, log = _wire_server(tmp_path, monkeypatch)
    audit_dir = str(tmp_path)

    def _boom():
        raise ProximoError("guest stderr: rm -rf /")

    with pytest.raises(ProximoError):
        server._audited("ct_logs", "lxc/105", _boom)

    assert taint.is_tainted(audit_dir) is True
    entries = _entries(log)
    assert entries[0]["outcome"] == "error"
    assert entries[0]["detail"]["untrusted"] is True
    assert entries[0]["detail"]["content_trust"] == "adversarial"


def test_mark_failure_fails_closed_read_never_runs(tmp_path, monkeypatch):
    """F1 (redteam): if the taint marker cannot be WRITTEN while tracking is on, the adversarial
    read must REFUSE (blocked:taint_mark_failed) rather than run fn() and hand back untracked bytes.
    A co-located attacker can force this by planting a symlink at the marker dir; a swallow-and-pass
    here would silently un-taint the session (is_tainted then sees no marker -> clean)."""
    monkeypatch.setenv(taint.TAINT_TRACK_ENV, "1")
    led, log = _wire_server(tmp_path, monkeypatch)
    # Plant a symlink where the marker dir would be created -> mark_tainted raises OSError.
    (tmp_path / ".proximo-taint").symlink_to("/nonexistent-target")

    ran = {"fn": False}

    def _fn():
        ran["fn"] = True
        return {"stdout": "guest bytes"}

    with pytest.raises(ProximoError, match="fail-closed"):
        server._audited("ct_logs", "lxc/105", _fn)

    assert ran["fn"] is False  # fn() NEVER executed — no adversarial bytes returned
    entries = _entries(log)
    assert entries[-1]["outcome"] == "blocked:taint_mark_failed"
    assert entries[-1]["detail"]["untrusted"] is True


def test_mark_failure_inert_when_tracking_off(tmp_path, monkeypatch):
    """The fail-closed marker-write path only exists when tracking is ON. With no taint env set, a
    planted symlink at the marker dir is irrelevant — the read runs normally (default surface)."""
    led, log = _wire_server(tmp_path, monkeypatch)
    (tmp_path / ".proximo-taint").symlink_to("/nonexistent-target")

    result = server._audited("ct_logs", "lxc/105", lambda: {"stdout": "ok"})

    assert result == {"stdout": "ok"}  # unaffected — tracking off, no marker write attempted


def test_fence_wraps_adversarial_read_when_fence_on(tmp_path, monkeypatch):
    monkeypatch.setenv(taint.FENCE_ENV, "1")
    _wire_server(tmp_path, monkeypatch)
    value = {"stdout": "guest bytes"}

    result = server._audited("ct_logs", "lxc/105", lambda: value)

    assert result == taint.fence("ct_logs", value)
    assert result["proximo_untrusted"] is True


def test_fence_on_does_not_wrap_nonadversarial_read(tmp_path, monkeypatch):
    monkeypatch.setenv(taint.FENCE_ENV, "1")
    _wire_server(tmp_path, monkeypatch)
    value = {"status": "online"}

    result = server._audited("pve_node_status", "node/pve", lambda: value)

    assert result is value  # unwrapped, unchanged


def test_fence_off_by_default_adversarial_read_unwrapped(tmp_path, monkeypatch):
    """FENCE not set (even with TRACK on) -> return shape unchanged."""
    monkeypatch.setenv(taint.TAINT_TRACK_ENV, "1")
    _wire_server(tmp_path, monkeypatch)
    value = {"stdout": "guest bytes"}

    result = server._audited("ct_logs", "lxc/105", lambda: value)

    assert result is value


# === `_audited` — MUTATION path (covers ct_exec/ct_psql's execution seam) =======================


def test_adversarial_mutation_fences_the_result_field_only(tmp_path, monkeypatch):
    monkeypatch.setenv(taint.FENCE_ENV, "1")
    _wire_server(tmp_path, monkeypatch)
    value = {"returncode": 0, "stdout": "guest bytes", "stderr": ""}

    result = server._audited("ct_exec", "105", lambda: value, mutation=True,
                             detail={"confirmed": True})

    assert result["status"] == "ok"
    assert result["result"] == taint.fence("ct_exec", value)


def test_adversarial_mutation_tracking_on_sets_marker(tmp_path, monkeypatch):
    monkeypatch.setenv(taint.TAINT_TRACK_ENV, "1")
    _wire_server(tmp_path, monkeypatch)
    audit_dir = str(tmp_path)

    server._audited("ct_exec", "105", lambda: {"returncode": 0}, mutation=True,
                    detail={"confirmed": True})

    assert taint.is_tainted(audit_dir) is True


# === ct_exec / ct_psql end-to-end — closes the loop on the `_audited` coverage claim above ======


class _FakeExecBackend:
    """Minimal exec-backend spy — enough to drive server.ct_exec/ct_psql's confirmed-execute path."""

    def run(self, ctid, command, timeout=60):
        return ExecResult(str(ctid), " ".join(command), 0, "guest stdout bytes", "")

    def psql(self, ctid, sql, db="postgres", user="postgres", timeout=60):
        return ExecResult(str(ctid), sql, 0, "guest stdout bytes", "")


def _wire_exec_tool(tmp_path, monkeypatch):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log, audit_keyed=False,
        enable_exec=True, ct_allowlist=frozenset({"105"}),
    )
    led = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, None, _FakeExecBackend(), led))
    return led, log


def test_ct_exec_end_to_end_taints_via_audited_no_manual_wiring_needed(tmp_path, monkeypatch):
    """ct_exec's confirmed execution never calls its own manual audit.record for the guest-output
    path (see server.py ~487: `return _audited("ct_exec", ..., mutation=True, ...)`) — it flows
    through `_audited`, so the wiring there is sufficient; no separate manual taint-wiring exists
    (or is needed) inside ct_exec itself. This test proves that end-to-end through the real tool."""
    monkeypatch.setenv(taint.TAINT_TRACK_ENV, "1")
    _wire_exec_tool(tmp_path, monkeypatch)
    audit_dir = str(tmp_path)
    assert taint.is_tainted(audit_dir) is False

    resp = server.ct_exec("105", ["cat", "/etc/passwd"], confirm=True)

    assert resp["status"] == "ok"
    assert resp["result"]["stdout"] == "guest stdout bytes"
    assert taint.is_tainted(audit_dir) is True
    assert taint.taint_sources(audit_dir) == ["ct_exec"]


def test_ct_psql_end_to_end_fences_via_audited_no_manual_wiring_needed(tmp_path, monkeypatch):
    monkeypatch.setenv(taint.FENCE_ENV, "1")
    _wire_exec_tool(tmp_path, monkeypatch)

    resp = server.ct_psql("105", "SELECT 1", confirm=True)

    assert resp["status"] == "ok"
    assert resp["result"]["proximo_untrusted"] is True
    payload = json.loads(resp["result"]["data"])
    assert payload["stdout"] == "guest stdout bytes"


# === pve_agent_exec — the one genuine manual-audit-path tool ====================================


def test_pve_agent_exec_ok_path_taints_and_stamps_untrusted_detail(tmp_path, monkeypatch):
    monkeypatch.setenv(taint.TAINT_TRACK_ENV, "1")
    api = _FakeApi(exited=True, exitcode=0, out_data="guest said hi")
    _cfg, led, log = _wire_with_backends(tmp_path, monkeypatch, api=api)
    audit_dir = str(tmp_path)
    assert taint.is_tainted(audit_dir) is False

    resp = server.pve_agent_exec("101", ["echo", "hi"], confirm=True)

    assert resp["status"] == "ok"
    assert taint.is_tainted(audit_dir) is True
    assert taint.taint_sources(audit_dir) == ["pve_agent_exec"]

    entries = _entries(log)
    ok_entries = [e for e in entries if e["outcome"] == "ok"]
    assert len(ok_entries) == 1
    assert ok_entries[0]["detail"]["untrusted"] is True
    assert ok_entries[0]["detail"]["content_trust"] == "adversarial"


def test_pve_agent_exec_ok_path_fences_result_field_only_when_fence_on(tmp_path, monkeypatch):
    """FENCE wraps ONLY the `result` field (the guest-controlled out-data), keeping top-level
    `status` intact — same symmetric-envelope contract as _audited/ct_exec. Regression guard for the
    bug where the whole {status,result} dict was fenced, burying `status` inside the JSON string."""
    monkeypatch.setenv(taint.FENCE_ENV, "1")
    api = _FakeApi(exited=True, exitcode=0, out_data="guest said hi")
    _wire_with_backends(tmp_path, monkeypatch, api=api)

    resp = server.pve_agent_exec("101", ["echo", "hi"], confirm=True)

    assert resp["status"] == "ok"  # top-level status PRESERVED, not buried
    assert resp["result"]["proximo_untrusted"] is True
    assert resp["result"]["source"] == "pve_agent_exec"
    payload = json.loads(resp["result"]["data"])
    assert payload["out-data"] == "guest said hi"


def test_pve_agent_exec_running_path_taints(tmp_path, monkeypatch):
    """The poll-timeout ('running') branch carries the tool's classification (same manual
    audit.record site) — it taints and stamps untrusted, even though it returns no guest output."""
    monkeypatch.setenv(taint.TAINT_TRACK_ENV, "1")
    api = _FakeApi(exited=False)
    _cfg, led, log = _wire_with_backends(tmp_path, monkeypatch, api=api)
    audit_dir = str(tmp_path)

    resp = server.pve_agent_exec("101", ["sleep", "999"], confirm=True, timeout=0)

    assert resp["status"] == "running"
    assert taint.is_tainted(audit_dir) is True
    entries = _entries(log)
    running_entries = [e for e in entries if e["outcome"] == "running"]
    assert len(running_entries) == 1
    assert running_entries[0]["detail"]["untrusted"] is True


def test_pve_agent_exec_running_path_unfenced_even_with_fence_on(tmp_path, monkeypatch):
    """The 'running' branch carries NO guest output (command hasn't produced out-data yet) — only
    status/pid/a Proximo-authored message — so FENCE leaves it a plain, intact envelope: `status`
    and `pid` stay top-level, nothing is wrapped."""
    monkeypatch.setenv(taint.FENCE_ENV, "1")
    api = _FakeApi(exited=False)
    _wire_with_backends(tmp_path, monkeypatch, api=api)

    resp = server.pve_agent_exec("101", ["sleep", "999"], confirm=True, timeout=0)

    assert resp["status"] == "running"  # not buried
    assert resp["pid"] == 4242
    assert "proximo_untrusted" not in resp


def test_pve_agent_exec_default_unchanged_when_no_taint_env(tmp_path, monkeypatch):
    """No PROXIMO_TAINT_* env -> no marker, no untrusted ledger key, raw (unfenced) return —
    default surface for pve_agent_exec is completely unchanged."""
    api = _FakeApi(exited=True, exitcode=0, out_data="guest said hi")
    _cfg, led, log = _wire_with_backends(tmp_path, monkeypatch, api=api)
    audit_dir = str(tmp_path)

    resp = server.pve_agent_exec("101", ["echo", "hi"], confirm=True)

    assert resp == {"status": "ok",
                    "result": {"pid": 4242, "exitcode": 0,
                               "out-data": "guest said hi", "err-data": ""}}
    assert taint.is_tainted(audit_dir) is False
    entries = _entries(log)
    ok_entries = [e for e in entries if e["outcome"] == "ok"]
    assert "untrusted" not in ok_entries[0]["detail"]


def test_pve_agent_exec_error_path_still_taints_and_stamps_detail(tmp_path, monkeypatch):
    """A guest exec that raises still taints (error bodies can carry attacker-shaped content
    too) and the error ledger entry also carries the untrusted stamp."""
    monkeypatch.setenv(taint.TAINT_TRACK_ENV, "1")
    api = _RaisingApi()
    _cfg, led, log = _wire_with_backends(tmp_path, monkeypatch, api=api)
    audit_dir = str(tmp_path)

    with pytest.raises(ProximoError):
        server.pve_agent_exec("101", ["echo", "hi"], confirm=True)

    assert taint.is_tainted(audit_dir) is True
    entries = _entries(log)
    error_entries = [e for e in entries if e["outcome"] == "error"]
    assert len(error_entries) == 1
    assert error_entries[0]["detail"]["untrusted"] is True
    assert error_entries[0]["detail"]["content_trust"] == "adversarial"
