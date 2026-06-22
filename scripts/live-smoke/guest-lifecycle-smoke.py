#!/usr/bin/env python3
"""Live MUTATE->verify of Proximo's guest power + snapshot/config/rollback lifecycle, end-to-end
through Proximo's own stack against a REAL Proxmox host, driven by a least-privilege scoped token.

Exercises (asserting POST-STATE at every step, not just HTTP 200):
  pve_guest_power (start/stop)  ·  snapshot_create  ·  guest_config_set  ·  snapshot_rollback
  ·  snapshot_delete

The rollback step is the load-bearing assertion: it changes a real hardware field (`sockets`),
rolls back, and asserts the field actually REVERTED to baseline — proving the engine mutates
correctly, not merely that the call returned. (NOTE: it asserts on `sockets`, not `description`,
because PVE deliberately preserves description/tags across rollback — they are metadata, not
snapshotted state. Asserting on description would test a field PVE intentionally does not revert.)

Structure: baseline snapshot FIRST, rollback-to-baseline + delete LAST, so the cleanup mechanism is
itself two of the tools under test. Each async snapshot op is awaited via its task UPID (snapshot ops
hold a VM lock for the whole task — racing the lock 500s). try/finally guarantees teardown.

SAFETY: operates ONLY on the throwaway QEMU VM you name in SMOKE_VMID. Bound the token to that VM
(e.g. a role with VM.PowerMgmt/VM.Snapshot/VM.Snapshot.Rollback/VM.Config.* on /vms/<SMOKE_VMID>
ONLY) so it cannot touch production by construction. The VM must be STOPPED at baseline; it is left
stopped.

Run (example):
    set -a; . /path/to/proximo.env; set +a
    SMOKE_VMID=9900 PROXIMO_TOKEN_PATH=/path/to/scoped-token \
        uv run python scripts/live-smoke/guest-lifecycle-smoke.py
"""
from __future__ import annotations

import os
import sys
import time

from proximo.config_edit import guest_config_get, guest_config_set
from proximo.server import _svc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from safety import assert_test_target, load_allowlist  # noqa: E402  (sibling live-smoke module)

VMID = os.environ.get("SMOKE_VMID", "").strip()
KIND = os.environ.get("SMOKE_KIND", "qemu").strip()
# Real hardware field PVE snapshots + reverts (unlike description/tags). Toggle between two values.
SET_KEY = "sockets"
SET_VAL = "2"
SNAP = "proximolifesmoke"

if not VMID:
    sys.exit("SMOKE_VMID is required — a throwaway QEMU VMID the token is scoped to. Refusing to guess.")
if KIND != "qemu":
    sys.exit(f"this smoke asserts on a QEMU field ({SET_KEY}); SMOKE_KIND must be 'qemu', got {KIND!r}.")

# Independent SECOND safety layer (beneath token scoping): default-deny unless VMID is an allowlisted
# test target. Set PROXIMO_SMOKE_TEST_VMIDS / PROXIMO_SMOKE_VMID_RANGE. See safety.py.
assert_test_target(load_allowlist(os.environ), vmid=VMID)


def _snaps(api) -> set[str]:
    return {s.get("name", "") for s in api.snapshot_list(VMID, KIND, None)}


def _field(api):
    return guest_config_get(api, VMID, KIND, None).get(SET_KEY)


def _wait_task(api, upid: str | None, timeout: int = 120) -> bool:
    if not upid:
        return True
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        st = api.task_status(upid, None)
        if st.get("status") == "stopped":
            return st.get("exitstatus") in (None, "OK")
        time.sleep(2)
    return False


def _status(api) -> str:
    return str(api.guest_status(VMID, KIND, None).get("status", "unknown"))


def _wait_status(api, want: str, timeout: int = 60) -> bool:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if _status(api) == want:
            return True
        time.sleep(2)
    return _status(api) == want


def main() -> int:
    from proximo.planning import plan_power
    _, api, _, _ = _svc()
    r: dict[str, bool] = {}

    status0 = _status(api)
    field0 = _field(api)
    print(f"baseline: {KIND}/{VMID} status={status0} {SET_KEY}={field0!r}")
    assert status0 == "stopped", f"expected a stopped baseline, got {status0!r} — refusing to disturb a running guest"
    assert str(field0) != SET_VAL, f"{SET_KEY} already == {SET_VAL} — cannot prove reversion; aborting"
    assert SNAP not in _snaps(api), f"snapshot {SNAP} already exists — aborting (won't clobber)"

    # --- power: start -> running -> hard stop -> stopped ---
    print("\n[power] PLAN start:", end=" ")
    print(f"risk={plan_power(api, VMID, 'start', KIND, None).risk}")
    api.guest_power(VMID, "start", KIND, None)
    r["power_started_running"] = _wait_status(api, "running")
    print(f"        started -> running asserted = {r['power_started_running']}")
    api.guest_power(VMID, "stop", KIND, None)
    r["power_stopped"] = _wait_status(api, "stopped")
    print(f"        hard-stopped -> stopped asserted = {r['power_stopped']}")

    # --- snapshot / config / rollback / delete lifecycle ---
    try:
        print(f"\n[1] snapshot_create '{SNAP}' -> await task ...")
        upid = api.snapshot_create(VMID, SNAP, KIND, None, description="proximo lifecycle smoke")
        r["snapshot_created"] = _wait_task(api, upid) and SNAP in _snaps(api)
        print(f"    present = {SNAP in _snaps(api)}")

        print(f"\n[2] config_set {SET_KEY}={SET_VAL} ...")
        guest_config_set(api, VMID, {SET_KEY: SET_VAL}, KIND, None)
        r["config_set_applied"] = str(_field(api)) == SET_VAL
        print(f"    {SET_KEY} now = {_field(api)!r}")

        print(f"\n[3] snapshot_rollback '{SNAP}' -> must REVERT {SET_KEY} to baseline ...")
        ok_rb = _wait_task(api, api.snapshot_rollback(VMID, SNAP, KIND, None))
        r["rollback_reverted_state"] = ok_rb and _field(api) == field0 and str(_field(api)) != SET_VAL
        print(f"    {SET_KEY} after rollback = {_field(api)!r}  (== baseline {field0!r})")

        print(f"\n[4] snapshot_delete '{SNAP}' -> must be GONE ...")
        r["snapshot_deleted"] = _wait_task(api, api.snapshot_delete(VMID, SNAP, KIND, None)) and SNAP not in _snaps(api)
        print(f"    gone = {SNAP not in _snaps(api)}")
    finally:
        if SNAP in _snaps(api):
            print(f"    [cleanup] deleting leftover snapshot {SNAP} ...")
            try:
                _wait_task(api, api.snapshot_delete(VMID, SNAP, KIND, None, force=True))
            except Exception as e:
                print(f"    [cleanup] FAILED: {e!r} — MANUAL: qm delsnapshot {VMID} {SNAP}")
        if _field(api) != field0:
            print(f"    [cleanup] reverting {SET_KEY} to baseline ...")
            try:
                guest_config_set(api, VMID, {SET_KEY: str(field0) if field0 is not None else None}, KIND, None)
            except Exception as e:
                print(f"    [cleanup] FAILED: {e!r} — MANUAL: reset {SET_KEY} of {VMID} to {field0!r}")

    r["baseline_restored"] = _status(api) == status0 and _field(api) == field0 and SNAP not in _snaps(api)

    ok = all(r.values())
    print("\n" + "=" * 64)
    print(f"guest lifecycle MUTATE->verify on {KIND}/{VMID} (token-scoped): {'PASS' if ok else 'FAIL'}")
    for k, v in r.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
