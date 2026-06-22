#!/usr/bin/env python3
"""Live MUTATE->verify of Proximo's disk_resize end-to-end through Proximo's stack against a REAL
host, driven by a least-privilege scoped token. Bounded entirely to an isolated test storage.

Flow (asserting POST-STATE at every step):
  1. allocate a scratch disk SMOKE_SLOT = SMOKE_STORE:1 (1 GiB) on throwaway SMOKE_VMID
  2. PLAN disk_resize '+1G'  -> assert RISK_MEDIUM (grow; disclosed NOT auto-undoable)
  3. EXECUTE disk_resize '+1G' -> assert the disk actually GREW to 2G (not just HTTP 200)
  4. SAFETY: PLAN + EXECUTE an absolute shrink ('1G' < 2G) -> assert PLAN is RISK_HIGH AND the op
     REFUSES (ProximoError) -- proving the grow-only guard fires on real iron
  5. detach + delete the scratch volume -> assert gone + slot free

SAFETY: the scratch disk lives only on SMOKE_STORE (isolate it from production; grant the token
Datastore.AllocateSpace there and nowhere else) attached to the throwaway SMOKE_VMID. Self-cleaning
via try/finally.

Run (example):
    set -a; . /path/to/proximo.env; set +a
    SMOKE_VMID=9900 SMOKE_STORE=test PROXIMO_TOKEN_PATH=/path/to/scoped-token \
        uv run python scripts/live-smoke/disk-resize-smoke.py
"""
from __future__ import annotations

import os
import sys
import time

from proximo.backends import ProximoError
from proximo.config_edit import guest_config_get
from proximo.disk_ops import disk_resize, plan_disk_resize
from proximo.server import _svc
from proximo.storage import content_delete, storage_content

VMID = os.environ.get("SMOKE_VMID", "").strip()
STORE = os.environ.get("SMOKE_STORE", "").strip()
SLOT = os.environ.get("SMOKE_SLOT", "scsi1").strip()
KIND = os.environ.get("SMOKE_KIND", "qemu").strip()

if not VMID or not STORE:
    sys.exit("SMOKE_VMID and SMOKE_STORE are required "
             "(a throwaway VMID + an isolated test storage). Refusing to guess.")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from safety import assert_test_target, load_allowlist  # noqa: E402  (sibling live-smoke module)

# Independent SECOND safety layer (beneath token scoping): default-deny unless both the VMID and
# the storage are allowlisted test targets. See safety.py.
assert_test_target(load_allowlist(os.environ), vmid=VMID, storage=STORE)


def _entry(api) -> str:
    return str(guest_config_get(api, VMID, KIND, None).get(SLOT, "") or "")


def _volid(api) -> str | None:
    e = _entry(api)
    return e.split(",", 1)[0].strip() if e else None


def _size(api) -> str | None:
    for part in _entry(api).split(","):
        part = part.strip()
        if part.startswith("size="):
            return part[5:]
    return None


def _put_cfg(api, body: dict):
    api._put(f"/nodes/{api.config.node}/{KIND}/{VMID}/config", body)


def _wait_task(api, upid, timeout: int = 90) -> bool:
    if not isinstance(upid, str) or not upid.startswith("UPID:"):
        return True  # sync op (empty/None return)
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if api.task_status(upid, None).get("status") == "stopped":
            return True
        time.sleep(2)
    return False


def main() -> int:
    _, api, _, _ = _svc()
    r: dict[str, bool] = {}

    assert not _entry(api), f"slot {SLOT} on {KIND}/{VMID} is occupied — choose a free SMOKE_SLOT; aborting"
    V = None
    try:
        print(f"[1] allocate scratch {SLOT} = {STORE}:1 (1 GiB) ...")
        _put_cfg(api, {SLOT: f"{STORE}:1"})
        time.sleep(2)
        V = _volid(api)
        sz0 = _size(api)
        print(f"    allocated {V}  size={sz0}")
        r["allocated_1g"] = bool(V) and V.startswith(f"{STORE}:") and sz0 == "1G"

        print("\n[2] PLAN disk_resize '+1G' ...")
        p = plan_disk_resize(api, VMID, SLOT, "+1G", KIND, None)
        r["plan_grow_medium"] = p.risk == "medium"
        print(f"    risk={p.risk}  blast={p.blast_radius}")

        print("\n[3] EXECUTE disk_resize '+1G' -> must GROW to 2G ...")
        _wait_task(api, disk_resize(api, VMID, SLOT, "+1G", KIND, None))
        time.sleep(2)
        sz1 = _size(api)
        r["grew_to_2g"] = sz1 == "2G"
        print(f"    size after grow = {sz1}  (== 2G: {r['grew_to_2g']})")

        print("\n[4] SAFETY: shrink '1G' (< 2G) must be BLOCKED at plan + op ...")
        ps = plan_disk_resize(api, VMID, SLOT, "1G", KIND, None)
        plan_blocks = ps.risk == "high"
        op_refused = False
        try:
            disk_resize(api, VMID, SLOT, "1G", KIND, None)
        except ProximoError:
            op_refused = True
        r["shrink_blocked"] = plan_blocks and op_refused
        print(f"    plan risk={ps.risk} (high={plan_blocks})  op refused={op_refused}")
        # confirm the shrink did NOT take effect
        r["shrink_no_effect"] = _size(api) == "2G"
        print(f"    size still 2G after refused shrink = {r['shrink_no_effect']}")
    finally:
        if V and _entry(api):
            print(f"\n[cleanup] detach {SLOT} + delete scratch volume {V} ...")
            try:
                _put_cfg(api, {"delete": SLOT})
                time.sleep(1)
                content_delete(api, STORE, V)
                time.sleep(2)
            except Exception as e:
                print(f"    [cleanup] note: {type(e).__name__} — trying direct unused-slot delete")
            # drop any dangling unused slot referencing the volume
            cfg = guest_config_get(api, VMID, KIND, None)
            for k, val in list(cfg.items()):
                if k.startswith("unused") and isinstance(val, str) and val.split(",", 1)[0].strip() == V:
                    try:
                        _put_cfg(api, {"delete": k})
                    except Exception:  # noqa: S110 — best-effort teardown of a scratch unused-disk ref
                        pass

    gone = V is not None and not any(c.get("volid") == V for c in storage_content(api, STORE))
    leftover = [k for k in guest_config_get(api, VMID, KIND, None) if k == SLOT or k.startswith("unused")]
    r["cleaned_up"] = gone and not leftover
    print(f"\n[cleanup] volume gone = {gone}  leftover slots = {leftover}")

    ok = all(r.values())
    print("\n" + "=" * 60)
    print(f"disk_resize MUTATE->verify on {KIND}/{VMID} ({STORE}-bounded): {'PASS' if ok else 'FAIL'}")
    for k, v in r.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
