#!/usr/bin/env python3
"""Live PROOF of PDM cross-remote (datacenter-to-datacenter) migration through Proximo.

This is the ONE fleet-control op the 2026-07-06 fleet smoke (pdm-fleet-smoke.py) could
not reach — it needs a SECOND PDM-registered remote that is a *different* cluster from the
source. `remote-migrate` proxies PVE's cross-cluster migration: it copies the guest's disk
and config over the network from the source remote to the target remote (no shared storage
between them — that is the whole point of a cross-DC move).

Proves: `pdm_pve_{qemu,lxc}_remote_migrate` end-to-end — dry-run first (PLAN), executed
(confirm=True), task-waited on the remote-qualified UPID, placement asserted (guest present
on the TARGET remote; absent from the SOURCE when delete=True), PROVE-verified.

MUTATES A REAL GUEST and (with SMOKE_DELETE=1, the default) DESTROYS it on the source.
Point it ONLY at a throwaway guest on a TEST remote (the sealed nested lab). The guest must
ALREADY EXIST (PDM cannot create one).

Run (example — sealed nested lab; source=labclu via the pve-test1 remote, target=pve-test4):
    PROXIMO_PDM_BASE_URL=https://<pdm-host>:8443 \
    PROXIMO_PDM_TOKEN_PATH=/path/to/pdm-RW-token \
    PROXIMO_PDM_FINGERPRINT=<sha256-pin> \
    PROXIMO_API_BASE_URL=https://<pve-test1>:8006/api2/json \
    PROXIMO_TOKEN_PATH=/path/to/lab-token PROXIMO_FINGERPRINT=<sha256-pin> \
    PROXIMO_AUDIT_LOG=/tmp/pdm-remote-migrate-smoke.log \
    SMOKE_REMOTE=pve-test1 SMOKE_VMID=31411 SMOKE_KIND=qemu \
    SMOKE_TARGET_REMOTE=pve-test4 \
    SMOKE_TARGET_BRIDGE=vmbr0:vmbr0 SMOKE_TARGET_STORAGE=local-lvm \
    uv run python scripts/live-smoke/pdm-remote-migrate-smoke.py

PROXIMO_API_BASE_URL/PROXIMO_TOKEN_PATH are needed only so the trust funnel can build its
ledger (_svc); the PDM tools never call that PVE backend — the mutations go to PDM.

Env knobs:
  SMOKE_TARGET_BRIDGE   required  source→target bridge map, e.g. 'vmbr0:vmbr0'
  SMOKE_TARGET_STORAGE  required  source→target storage map, e.g. 'local-lvm' or 'labshared:local-lvm'
  SMOKE_TARGET_VMID     optional  vmid on the target (defaults to the same vmid)
  SMOKE_ONLINE          optional  online migrate (running guest); default offline
  SMOKE_DELETE          optional  remove the source guest after the move; DEFAULT 1 (a real move)
"""
from __future__ import annotations

import os
import sys
import time

REMOTE = os.environ.get("SMOKE_REMOTE", "").strip()
VMID = os.environ.get("SMOKE_VMID", "").strip()
KIND = os.environ.get("SMOKE_KIND", "qemu").strip()
TARGET_REMOTE = os.environ.get("SMOKE_TARGET_REMOTE", "").strip()
TARGET_BRIDGE = os.environ.get("SMOKE_TARGET_BRIDGE", "").strip()
TARGET_STORAGE = os.environ.get("SMOKE_TARGET_STORAGE", "").strip()
TARGET_VMID = os.environ.get("SMOKE_TARGET_VMID", "").strip() or None
ONLINE = os.environ.get("SMOKE_ONLINE", "").strip() in ("1", "true", "yes")
DELETE = os.environ.get("SMOKE_DELETE", "1").strip() in ("1", "true", "yes")


def _need(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        print(f"[SKIP] {name} not set — skipping the PDM remote-migrate smoke.", file=sys.stderr)
        sys.exit(0)
    return v


def _ok(msg: str) -> None:
    print(f"  PASS  {msg}")


def main() -> None:
    for var in ("PROXIMO_PDM_BASE_URL", "PROXIMO_PDM_TOKEN_PATH", "PROXIMO_API_BASE_URL",
                "PROXIMO_TOKEN_PATH"):
        _need(var)
    if not (REMOTE and VMID and TARGET_REMOTE and TARGET_BRIDGE and TARGET_STORAGE):
        print("[SKIP] SMOKE_REMOTE, SMOKE_VMID, SMOKE_TARGET_REMOTE, SMOKE_TARGET_BRIDGE and "
              "SMOKE_TARGET_STORAGE are all required.", file=sys.stderr)
        sys.exit(0)

    from proximo import server

    _, pdm = server._pdm()
    dest_vmid = str(TARGET_VMID or VMID)

    def wait(remote: str, upid: str, label: str) -> None:
        """Wait for a proxied task; fail-closed on anything but exitstatus OK.

        remote-migrate is a copy-over-the-wire — allow a long budget (5 min).
        """
        for _ in range(150):
            st = pdm.task_status(remote, upid)
            if st.get("status") == "stopped":
                assert st.get("exitstatus") == "OK", f"{label}: task {upid} -> {st.get('exitstatus')!r}"
                return
            time.sleep(2)
        raise AssertionError(f"{label}: task {upid} did not finish in time")

    def present_on(remote: str, vmid: str) -> bool:
        """Is `vmid` visible on `remote`? Poll the cluster-resources aggregate (pvestatd
        refreshes on a ~10s cadence, so a read right after a migrate task can lag)."""
        for _ in range(20):
            for g in pdm.pve_resources(remote, kind="vm"):
                if str(g.get("vmid")) == str(vmid):
                    return True
            time.sleep(3)
        return False

    print(f"--- PDM remote-migrate smoke: {KIND}/{VMID} '{REMOTE}' -> '{TARGET_REMOTE}' "
          f"(as {dest_vmid}, online={ONLINE}, delete={DELETE}) ---")

    # Preflight: PDM reachable, BOTH remotes registered, source guest present, target vmid free.
    assert pdm.ping() == "pong", "PDM ping failed"
    remotes = [r.get("id") or r.get("name") for r in pdm.remotes_list()]
    for r in (REMOTE, TARGET_REMOTE):
        assert r in remotes, f"remote {r!r} not registered in PDM (have: {remotes})"
    assert REMOTE != TARGET_REMOTE, "source and target remote must differ for a cross-remote migrate"
    assert str(pdm.guest_status(REMOTE, KIND, VMID).get("status")), "source guest not found"
    _ok(f"preflight (both remotes registered, source {KIND}/{VMID} present)")

    remote_migrate = getattr(server, f"pdm_pve_{KIND}_remote_migrate")

    # 1) DRY-RUN — a PLAN, nothing executed.
    plan = remote_migrate(REMOTE, VMID, TARGET_REMOTE, TARGET_BRIDGE, TARGET_STORAGE,
                          target_vmid=TARGET_VMID, online=ONLINE, delete=DELETE)
    assert plan["status"] == "plan", f"remote-migrate plan: {plan}"
    _ok("remote-migrate: dry-run returns a PLAN (not executed)")

    # 2) EXECUTE — submit, wait on the remote-qualified UPID.
    out = remote_migrate(REMOTE, VMID, TARGET_REMOTE, TARGET_BRIDGE, TARGET_STORAGE,
                         target_vmid=TARGET_VMID, online=ONLINE, delete=DELETE, confirm=True)
    assert out["status"] == "submitted", f"remote-migrate execute: {out}"
    wait(REMOTE, out["result"], "remote-migrate")
    _ok(f"remote-migrate: task OK (UPID {out['result']})")

    # 3) PLACEMENT — guest now on the TARGET remote; gone from SOURCE when delete=True.
    assert present_on(TARGET_REMOTE, dest_vmid), \
        f"{KIND}/{dest_vmid} not present on target remote {TARGET_REMOTE!r} after migrate"
    _ok(f"placement: {KIND}/{dest_vmid} present on target remote '{TARGET_REMOTE}'")
    if DELETE:
        assert not present_on(REMOTE, VMID), \
            f"{KIND}/{VMID} still present on source {REMOTE!r} despite delete=True"
        _ok(f"placement: {KIND}/{VMID} removed from source remote '{REMOTE}' (delete=True)")

    # 4) PROVE — the ledger chain of the plan+submit verifies.
    v = server.audit_verify()
    assert bool(v.get("ok")), f"ledger verify failed: {v}"
    _ok(f"PROVE: audit ledger hash chain verified ({v.get('entries')} entries)")

    print("--- PDM remote-migrate smoke complete: cross-remote PLAN + PROVE live-proven ---")
    print(f"    NOTE: the migrated guest {KIND}/{dest_vmid} now lives on '{TARGET_REMOTE}' — "
          "delete it there to return the lab to a clean state.")


if __name__ == "__main__":
    main()
