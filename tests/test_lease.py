"""CONTAIN-LEASE leg (auto-expiring arm) — the fail-closed TTL on elevated write-authority.

`arm` installs the operator token to ``config.token_path``, so the destination's mtime IS the
arm-time stamp (verified empirically: `install -m 600` with no `-p` always stamps current mtime).
``lease_state()`` reads BOTH ``PROXIMO_ARM_TTL`` and ``PROXIMO_TOKEN_PATH`` from env fresh on every
call (no caching, no cfg-threading — see lease.py module docstring for why), mirroring the
discipline of contain.py/provenance.py. ``enforce_lease`` is wired at the same 5 mutation seams,
right after ``enforce_scope`` and before ``enforce_consent`` (decision D3).

Structure mirrors test_contain.py: `_wire_server`/`_wire_with_backends` harnesses, `_entries`
ledger reader, and BYPASS proofs for the manual-audit-path tools (pve_agent_exec, ct_exec/ct_psql).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.backends import ExecResult, ProximoError
from proximo.config import ProximoConfig
from proximo.lease import lease_state
from proximo.planning import RISK_NONE, Plan


def _wire_server(tmp_path, monkeypatch, *, token_path=None):
    """Wire proximo.server with a real ledger (tmp_path) and no live backends."""
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json",
        node="pve",
        token_path=token_path or str(tmp_path / "pve-token"),
        audit_log_path=log,
        audit_keyed=False,
    )
    led = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, None, None, led))
    return led, log


def _entries(log_path) -> list[dict]:
    return [json.loads(ln) for ln in Path(log_path).read_text().splitlines() if ln.strip()]


def _token(tmp_path, *, age_seconds=None) -> Path:
    """Create a token file, optionally back-dating its mtime by `age_seconds`."""
    token = tmp_path / "pve-token"
    token.write_text("user@pam!id=secret")
    if age_seconds is not None:
        stamp = __import__("time").time() - age_seconds
        os.utime(token, (stamp, stamp))
    return token


def _arm_env(monkeypatch, token_path, ttl):
    monkeypatch.setenv("PROXIMO_TOKEN_PATH", str(token_path))
    if ttl is None:
        monkeypatch.delenv("PROXIMO_ARM_TTL", raising=False)
    else:
        monkeypatch.setenv("PROXIMO_ARM_TTL", str(ttl))


# === Env-unset / disabled paths (zero behavior change) =======================================


def test_no_ttl_env_means_no_lease(tmp_path, monkeypatch):
    """PROXIMO_ARM_TTL unset -> mutation proceeds exactly as before (backward compat)."""
    token = _token(tmp_path)
    _wire_server(tmp_path, monkeypatch, token_path=str(token))
    monkeypatch.setenv("PROXIMO_TOKEN_PATH", str(token))
    monkeypatch.delenv("PROXIMO_ARM_TTL", raising=False)

    calls = []
    resp = server._audited("pve_guest_power", "lxc/100", lambda: calls.append(1) or {"ok": True},
                            mutation=True)
    assert calls == [1]
    assert resp == {"status": "ok", "result": {"ok": True}}


def test_ttl_zero_or_negative_means_no_lease(tmp_path, monkeypatch):
    """TTL<=0 is an explicit disable (contract §1) -> mutation proceeds."""
    token = _token(tmp_path)
    _wire_server(tmp_path, monkeypatch, token_path=str(token))
    for ttl in ("0", "-5"):
        _arm_env(monkeypatch, token, ttl)
        calls: list = []

        def _fn(calls=calls):
            calls.append(1)

        server._audited("pve_guest_power", "lxc/100", _fn, mutation=True)
        assert calls == [1]


# === Fresh vs expired ==========================================================================


def test_fresh_arm_within_ttl_proceeds(tmp_path, monkeypatch):
    """Token mtime = now, TTL=3600 -> well within lease -> mutation proceeds."""
    token = _token(tmp_path, age_seconds=5)
    _wire_server(tmp_path, monkeypatch, token_path=str(token))
    _arm_env(monkeypatch, token, 3600)

    calls = []
    server._audited("pve_guest_power", "lxc/100", lambda: calls.append(1), mutation=True)
    assert calls == [1]


def test_expired_arm_refused_before_backend_call(tmp_path, monkeypatch):
    """HEADLINE: token mtime = now-7200, TTL=3600 -> ProximoError, wrapped fn NEVER called, ledger
    outcome="blocked:lease_expired" with age_seconds/ttl in detail."""
    token = _token(tmp_path, age_seconds=7200)
    _led, log = _wire_server(tmp_path, monkeypatch, token_path=str(token))
    _arm_env(monkeypatch, token, 3600)

    calls = []
    with pytest.raises(ProximoError, match="lease expired"):
        server._audited("pve_guest_power", "lxc/100", lambda: calls.append(1), mutation=True)
    assert calls == []

    entries = _entries(log)
    assert len(entries) == 1
    assert entries[0]["action"] == "pve_guest_power"
    assert entries[0]["target"] == "lxc/100"
    assert entries[0]["mutation"] is True
    assert entries[0]["outcome"] == "blocked:lease_expired"
    assert entries[0]["detail"]["ttl"] == 3600
    assert entries[0]["detail"]["age_seconds"] >= 7200


# === Fail-closed footguns ======================================================================


def test_missing_token_file_fails_closed(tmp_path, monkeypatch):
    """TTL set, PROXIMO_TOKEN_PATH points at a nonexistent file -> refused (fail-closed)."""
    _wire_server(tmp_path, monkeypatch)
    missing = tmp_path / "does-not-exist"
    _arm_env(monkeypatch, missing, 3600)

    calls = []
    with pytest.raises(ProximoError, match="lease expired"):
        server._audited("pve_guest_power", "lxc/100", lambda: calls.append(1), mutation=True)
    assert calls == []


def test_ttl_env_set_but_token_path_unset_fails_closed(tmp_path, monkeypatch):
    """TTL set, PROXIMO_TOKEN_PATH deleted from env -> refused (proves the os.stat(None) guard)."""
    token = _token(tmp_path)
    _wire_server(tmp_path, monkeypatch, token_path=str(token))
    monkeypatch.setenv("PROXIMO_ARM_TTL", "3600")
    monkeypatch.delenv("PROXIMO_TOKEN_PATH", raising=False)

    calls = []
    with pytest.raises(ProximoError, match="lease expired"):
        server._audited("pve_guest_power", "lxc/100", lambda: calls.append(1), mutation=True)
    assert calls == []


def test_garbled_ttl_fails_closed(tmp_path, monkeypatch):
    """PROXIMO_ARM_TTL="abc" (non-int) -> refused (fail-closed)."""
    token = _token(tmp_path)
    _wire_server(tmp_path, monkeypatch, token_path=str(token))
    monkeypatch.setenv("PROXIMO_TOKEN_PATH", str(token))
    monkeypatch.setenv("PROXIMO_ARM_TTL", "abc")

    calls = []
    with pytest.raises(ProximoError, match="lease expired"):
        server._audited("pve_guest_power", "lxc/100", lambda: calls.append(1), mutation=True)
    assert calls == []


def test_future_mtime_fails_closed(tmp_path, monkeypatch):
    """Redteam F1 (HIGH): a token mtime AHEAD of the wall clock (clock skew — NTP step, VM
    migration, snapshot restore — or `touch -d <future>`) must fail CLOSED. Without the guard,
    `age = int(now - mtime)` goes negative, `age > ttl` is False, and even a 1s TTL reads 'fresh'
    for as long as the future stamp — a fail-OPEN with no adversary required. Note a max(0,...)
    clamp would NOT fix it (reads as age 0 = just-armed = still open)."""
    token = _token(tmp_path, age_seconds=-31_536_000)  # negative age => mtime ~1yr in the FUTURE
    _wire_server(tmp_path, monkeypatch, token_path=str(token))
    _arm_env(monkeypatch, token, 1)  # aggressive 1-second TTL

    # State-level: the future stamp reads EXPIRED (fail-closed), not fresh.
    assert lease_state().expired is True

    # End-to-end: the real mutation seam refuses and the wrapped fn never fires.
    calls = []
    with pytest.raises(ProximoError, match="lease expired"):
        server._audited("pve_guest_power", "lxc/100", lambda: calls.append(1), mutation=True)
    assert calls == []


def test_directory_token_path_fails_closed(tmp_path, monkeypatch):
    """Redteam F2 (MEDIUM): PROXIMO_TOKEN_PATH pointing at a DIRECTORY (operator typo — the config
    dir instead of the token file) must fail CLOSED. os.stat on a dir SUCCEEDS, skipping the
    `except`, and a dir's mtime is bumped by any unrelated entry churn inside it — not a valid
    arm-stamp. A fresh directory would otherwise read as a LIVE lease (fail-open); the S_ISREG guard
    refuses it."""
    d = tmp_path / "tokendir"
    d.mkdir()  # fresh mtime, well within TTL => without S_ISREG this is a fail-OPEN live lease
    _wire_server(tmp_path, monkeypatch, token_path=str(d))
    _arm_env(monkeypatch, d, 3600)

    assert lease_state().expired is True  # regular-file guard => fail-closed

    calls = []
    with pytest.raises(ProximoError, match="lease expired"):
        server._audited("pve_guest_power", "lxc/100", lambda: calls.append(1), mutation=True)
    assert calls == []


# === Reads / PLAN not gated ====================================================================


def test_reads_not_gated_when_expired(tmp_path, monkeypatch):
    """An expired lease still allows a READ (mutation=False) call — the read-only downgrade."""
    token = _token(tmp_path, age_seconds=7200)
    _wire_server(tmp_path, monkeypatch, token_path=str(token))
    _arm_env(monkeypatch, token, 3600)

    result = server._audited("pve_node_status", "pve", lambda: {"status": "running"})
    assert result == {"status": "running"}


def test_plan_dry_run_not_gated_when_expired(tmp_path, monkeypatch):
    """The dry-run PLAN path (_plan) still returns while the lease is expired — mutations only."""
    token = _token(tmp_path, age_seconds=7200)
    _wire_server(tmp_path, monkeypatch, token_path=str(token))
    _arm_env(monkeypatch, token, 3600)

    def _build():
        return Plan(
            action="x", target="lxc/100", change="would start", current={},
            blast_radius=[], risk=RISK_NONE, risk_reasons=[],
        )

    plan = server._plan("pve_guest_power", "lxc/100", _build)
    assert plan.change == "would start"


# === BYPASS proofs: manual-audit-path tools that don't run through _audited() ==================


class _FakeApi:
    def __init__(self):
        self.config = SimpleNamespace(node="pve")
        self.agent_execs: list = []
        self.agent_exec_statuses: list = []
        self.snapshot_creates: list = []
        self.task_statuses: list = []

    def agent_exec(self, vmid, node, command):
        self.agent_execs.append((vmid, node, command))
        return {"pid": 1}

    def agent_exec_status(self, vmid, node, pid):
        self.agent_exec_statuses.append((vmid, node, pid))
        return {"exited": True, "exitcode": 0, "out-data": "", "err-data": ""}

    def snapshot_create(self, vmid, snapname, kind="lxc", node=None, description=None):
        self.snapshot_creates.append((vmid, snapname))
        return "UPID:create"

    def task_status(self, upid, node=None):
        self.task_statuses.append(upid)
        return {"status": "stopped", "exitstatus": "OK"}


class _FakeExec:
    def __init__(self):
        self.ran: list = []

    def run(self, ctid, command, timeout=60):
        self.ran.append((ctid, command))
        return ExecResult(str(ctid), " ".join(command), 0, "out", "")

    def psql(self, ctid, sql, db="postgres", user="postgres", timeout=60):
        self.ran.append((ctid, sql))
        return ExecResult(str(ctid), sql, 0, "out", "")


def _wire_with_backends(tmp_path, monkeypatch, *, token_path=None, enable_agent=False,
                        agent_allowlist=frozenset(), enable_exec=False, ct_allowlist=frozenset()):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve",
        token_path=token_path or str(tmp_path / "pve-token"),
        audit_log_path=log, audit_keyed=False,
        enable_agent=enable_agent, agent_allowlist=agent_allowlist,
        enable_exec=enable_exec, ct_allowlist=ct_allowlist,
    )
    api = _FakeApi()
    exec_ = _FakeExec()
    led = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, exec_, led))
    return cfg, api, exec_, led, log


def test_pve_agent_exec_lease_gated(tmp_path, monkeypatch):
    """pve_agent_exec has a manual audit path (like containment/scope): expired lease ->
    ProximoError, and api.agent_exec is NEVER called."""
    token = _token(tmp_path, age_seconds=7200)
    _cfg, api, _exec, _led, log = _wire_with_backends(
        tmp_path, monkeypatch, token_path=str(token),
        enable_agent=True, agent_allowlist=frozenset({"101"}),
    )
    _arm_env(monkeypatch, token, 3600)

    with pytest.raises(ProximoError, match="lease expired"):
        server.pve_agent_exec("101", ["echo", "hi"], confirm=True)

    assert api.agent_execs == []
    assert api.agent_exec_statuses == []
    entries = _entries(log)
    blocked = [e for e in entries if e["outcome"] == "blocked:lease_expired"]
    assert len(blocked) == 1
    assert blocked[0]["action"] == "pve_agent_exec"
    assert blocked[0]["mutation"] is True


def test_ct_exec_lease_gated_before_auto_undo(tmp_path, monkeypatch):
    """ct_exec's auto-undo snapshot fires BEFORE _audited(mutation=True) — expired lease must
    refuse the WHOLE operation: api.snapshot_create NEVER fires AND the command never runs."""
    token = _token(tmp_path, age_seconds=7200)
    _cfg, api, exec_, _led, log = _wire_with_backends(
        tmp_path, monkeypatch, token_path=str(token),
        enable_exec=True, ct_allowlist=frozenset({"105"}),
    )
    _arm_env(monkeypatch, token, 3600)

    with pytest.raises(ProximoError, match="lease expired"):
        server.ct_exec("105", ["rm", "-rf", "/x"], snapshot=True, confirm=True)

    assert api.snapshot_creates == []
    assert exec_.ran == []
    entries = _entries(log)
    blocked = [e for e in entries if e["outcome"] == "blocked:lease_expired"]
    assert len(blocked) == 1
    assert blocked[0]["action"] == "ct_exec"


def test_ct_psql_lease_gated(tmp_path, monkeypatch):
    """Same proof for ct_psql (shares _auto_undo with ct_exec)."""
    token = _token(tmp_path, age_seconds=7200)
    _cfg, api, exec_, _led, log = _wire_with_backends(
        tmp_path, monkeypatch, token_path=str(token),
        enable_exec=True, ct_allowlist=frozenset({"105"}),
    )
    _arm_env(monkeypatch, token, 3600)

    with pytest.raises(ProximoError, match="lease expired"):
        server.ct_psql("105", "DELETE FROM t", snapshot=True, confirm=True)

    assert api.snapshot_creates == []
    assert exec_.ran == []
    entries = _entries(log)
    blocked = [e for e in entries if e["outcome"] == "blocked:lease_expired"]
    assert len(blocked) == 1
    assert blocked[0]["action"] == "ct_psql"


# === Compose: pin decision D3's order (containment -> scope -> lease -> consent) ===============


def test_lease_and_containment_and_scope_compose(tmp_path, monkeypatch):
    """With BOTH an expired lease AND a containment trip set, containment wins first (it runs
    before scope/lease in the pipeline) -> outcome "contained", never "blocked:lease_expired".
    With ONLY the lease expired (no trip, no scope), the lease gate fires -> "blocked:lease_expired".
    """
    token = _token(tmp_path, age_seconds=7200)
    _led, log = _wire_server(tmp_path, monkeypatch, token_path=str(token))
    _arm_env(monkeypatch, token, 3600)

    trip = tmp_path / "trip"
    trip.write_text("operator pulled the cord")
    monkeypatch.setenv("PROXIMO_CONTAIN_TRIP_PATH", str(trip))
    monkeypatch.delenv("PROXIMO_SCOPE_PATH", raising=False)

    calls = []
    with pytest.raises(ProximoError):
        server._audited("pve_guest_power", "lxc/100", lambda: calls.append(1), mutation=True)
    assert calls == []
    entries = _entries(log)
    assert len(entries) == 1
    assert entries[0]["outcome"] == "contained"

    # Now clear containment, leaving ONLY the expired lease.
    monkeypatch.delenv("PROXIMO_CONTAIN_TRIP_PATH", raising=False)
    calls2 = []
    with pytest.raises(ProximoError, match="lease expired"):
        server._audited("pve_guest_power", "lxc/100", lambda: calls2.append(1), mutation=True)
    assert calls2 == []
    entries2 = _entries(log)
    assert len(entries2) == 2
    assert entries2[1]["outcome"] == "blocked:lease_expired"


# === Structural guard ==========================================================================


async def test_no_tool_accepts_a_ttl_kwarg():
    """Structural invariant: no @tool()-decorated function may accept a ttl/lease/arm_ttl
    parameter — the lease TTL is out-of-band env ONLY (PROXIMO_ARM_TTL). Mirrors
    test_provenance.py's test_no_tool_accepts_a_scope_kwarg. Verified: no current tool has one, so
    no exemption list is needed — the guard just needs to keep catching a future accidental one.
    """
    import inspect

    tools = await server.mcp.list_tools()
    offenders = []
    for t in tools:
        fn = getattr(server, t.name, None)
        if fn is None or not callable(fn):
            continue
        sig = inspect.signature(fn)
        for pname in sig.parameters:
            if pname.lower() in ("ttl", "lease", "arm_ttl"):
                offenders.append(f"{t.name}({pname})")
    assert not offenders, f"tool(s) accept a caller-supplied lease/ttl param: {offenders}"
