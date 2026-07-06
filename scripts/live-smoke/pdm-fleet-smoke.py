#!/usr/bin/env python3
"""Live PROOF of the PDM fleet-control mutation plane through Proximo's full stack.

Proves the increment added 2026-07-06: governed guest lifecycle driven through PDM's
remote proxy — power, snapshot create/rollback(+auto safety-snapshot)/delete, and
in-cluster migrate — each dry-run-first (PLAN), executed (confirm=True), task-waited,
post-state asserted, and PROVE-verified. remote-migrate is NOT exercised here (needs a
second remote + compatible storage; prove it separately once this passes).

MUTATES A REAL GUEST. Point it ONLY at a throwaway guest on a TEST remote (the nested
lab pve-test*). The guest must ALREADY EXIST (PDM cannot create one — no create proxy).
The smoke restores the guest's original power state and deletes every snapshot it makes.

Run (example — the sealed nested lab pdm-test / pve-test1):
    PROXIMO_PDM_BASE_URL=https://<pdm-host>:8443 \
    PROXIMO_PDM_TOKEN_PATH=/path/to/pdm-RW-token \
    PROXIMO_PDM_FINGERPRINT=<sha256-pin> \
    PROXIMO_API_BASE_URL=https://<pve-test1>:8006/api2/json \
    PROXIMO_TOKEN_PATH=/path/to/lab-token PROXIMO_FINGERPRINT=<sha256-pin> \
    PROXIMO_AUDIT_LOG=/tmp/pdm-fleet-smoke.log \
    SMOKE_REMOTE=pve-test1 SMOKE_VMID=31410 SMOKE_KIND=lxc \
    SMOKE_TARGET_NODE=pve-test2 \
    uv run python scripts/live-smoke/pdm-fleet-smoke.py

PROXIMO_API_BASE_URL/PROXIMO_TOKEN_PATH are needed only so the trust funnel can build
its ledger (_svc); the PDM tools never call that PVE backend — the mutations go to PDM.
Set SMOKE_KEEP=1 to skip restoring the original power state. SMOKE_TARGET_NODE is
optional (skips the migrate proof if unset).
"""
from __future__ import annotations

import os
import sys
import time

REMOTE = os.environ.get("SMOKE_REMOTE", "").strip()
VMID = os.environ.get("SMOKE_VMID", "").strip()
KIND = os.environ.get("SMOKE_KIND", "lxc").strip()
TARGET_NODE = os.environ.get("SMOKE_TARGET_NODE", "").strip()
KEEP = os.environ.get("SMOKE_KEEP", "").strip() in ("1", "true", "yes")
SNAP = "proximosmoke"


def _need(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        print(f"[SKIP] {name} not set — skipping the PDM fleet smoke.", file=sys.stderr)
        sys.exit(0)
    return v


def _ok(msg: str) -> None:
    print(f"  PASS  {msg}")


def main() -> None:
    for var in ("PROXIMO_PDM_BASE_URL", "PROXIMO_PDM_TOKEN_PATH", "PROXIMO_API_BASE_URL",
                "PROXIMO_TOKEN_PATH"):
        _need(var)
    if not REMOTE or not VMID:
        print("[SKIP] SMOKE_REMOTE and SMOKE_VMID (a throwaway guest) are required.", file=sys.stderr)
        sys.exit(0)

    from proximo import server

    _, pdm = server._pdm()

    def wait(upid: str, label: str) -> None:
        """Wait for a proxied task; fail-closed on anything but exitstatus OK."""
        for _ in range(90):
            st = pdm.task_status(REMOTE, upid)
            if st.get("status") == "stopped":
                assert st.get("exitstatus") == "OK", f"{label}: task {upid} -> {st.get('exitstatus')!r}"
                return
            time.sleep(2)
        raise AssertionError(f"{label}: task {upid} did not finish in time")

    def power(action: str) -> None:
        out = getattr(server, f"pdm_pve_{KIND}_power")(REMOTE, VMID, action, confirm=True)
        assert out["status"] == "submitted", f"power {action}: {out}"
        wait(out["result"], f"power {action}")

    def running() -> bool:
        return str(pdm.guest_status(REMOTE, KIND, VMID).get("status")) == "running"

    def node_of() -> str:
        # The per-guest status endpoint carries NO 'node' field — placement lives in the
        # cluster-resources aggregate. Poll it (pvestatd refreshes on a ~10s cadence, so a
        # read right after a migrate task completes can lag).
        for _ in range(15):
            for g in pdm.pve_resources(REMOTE, kind="vm"):
                if str(g.get("vmid")) == str(VMID) and g.get("node"):
                    return str(g.get("node"))
            time.sleep(2)
        return ""

    print(f"--- PDM fleet smoke: {KIND}/{VMID} on remote '{REMOTE}' ---")

    # Preflight: PDM reachable, remote registered, guest present.
    assert pdm.ping() == "pong", "PDM ping failed"
    remotes = [r.get("id") or r.get("name") for r in pdm.remotes_list()]
    assert REMOTE in remotes, f"remote {REMOTE!r} not registered in PDM (have: {remotes})"
    was_running = running()
    _ok(f"preflight (remote registered, guest present, running={was_running})")

    # 1) POWER — dry-run discloses, execute, post-state asserted.
    plan = getattr(server, f"pdm_pve_{KIND}_power")(REMOTE, VMID, "stop")
    assert plan["status"] == "plan" and plan["risk"] in {"high", "none"}, f"power plan: {plan}"
    _ok("power: dry-run returns a PLAN (not executed)")
    if not was_running:
        power("start")
        assert running(), "guest did not come up"
    power("stop")
    time.sleep(3)
    assert not running(), "guest did not stop"
    _ok("power stop: guest halted, task OK")
    power("start")
    time.sleep(3)
    assert running(), "guest did not restart"
    _ok("power start: guest running, task OK")

    # 2) SNAPSHOT create -> rollback(+auto safety-snapshot) -> delete.
    out = getattr(server, f"pdm_pve_{KIND}_snapshot_create")(REMOTE, VMID, SNAP, confirm=True)
    assert out["status"] == "submitted", f"snapshot create: {out}"
    wait(out["result"], "snapshot create")
    _ok(f"snapshot create '{SNAP}': task OK")

    out = getattr(server, f"pdm_pve_{KIND}_snapshot_rollback")(REMOTE, VMID, SNAP, confirm=True)
    assert out["status"] == "submitted", f"rollback: {out}"
    safety = out.get("safety_snapshot")
    assert safety, f"rollback did not record an auto safety-snapshot: {out}"
    wait(out["result"], "rollback")
    _ok(f"snapshot rollback: auto safety-snapshot '{safety}' taken first, rollback task OK")

    for name in (SNAP, safety):
        d = getattr(server, f"pdm_pve_{KIND}_snapshot_delete")(REMOTE, VMID, name, confirm=True)
        assert d["status"] == "submitted", f"snapshot delete {name}: {d}"
        wait(d["result"], f"snapshot delete {name}")
    _ok("snapshot delete: test snapshot + safety snapshot cleaned up")

    # 3) MIGRATE (optional) — move to the target node, assert, move back.
    if TARGET_NODE:
        # An online (qemu) migrate needs the guest running; the rollback above leaves it
        # stopped (a diskonly snapshot has no vmstate), so bring it up before proving migrate.
        if KIND == "qemu" and not running():
            power("start")
            time.sleep(3)
            assert running(), "guest did not come up before migrate"
            _ok("pre-migrate: guest started (online migrate needs a running guest)")
        home = node_of()
        out = getattr(server, f"pdm_pve_{KIND}_migrate")(REMOTE, VMID, TARGET_NODE,
                                                         online=(KIND == "qemu"), confirm=True)
        assert out["status"] == "submitted", f"migrate: {out}"
        wait(out["result"], "migrate")
        assert node_of() == TARGET_NODE, "migrate target mismatch"
        _ok(f"migrate: {KIND}/{VMID} now on '{TARGET_NODE}'")
        if home and home != TARGET_NODE:
            back = getattr(server, f"pdm_pve_{KIND}_migrate")(REMOTE, VMID, home,
                                                             online=(KIND == "qemu"), confirm=True)
            wait(back["result"], "migrate back")
            _ok(f"migrate back: restored to '{home}'")
    else:
        print("  SKIP  migrate: SMOKE_TARGET_NODE not set")

    # 4) Restore original power state (unless SMOKE_KEEP).
    if not KEEP and was_running != running():
        power("start" if was_running else "stop")
        _ok(f"restored original power state (running={was_running})")

    # 5) PROVE — the ledger chain of everything above verifies.
    v = server.audit_verify()
    assert bool(v.get("ok")), f"ledger verify failed: {v}"
    _ok(f"PROVE: audit ledger hash chain verified ({v.get('entries')} entries)")

    print("--- PDM fleet smoke complete: PLAN + PROVE + UNDO live-proven ---")


if __name__ == "__main__":
    main()
