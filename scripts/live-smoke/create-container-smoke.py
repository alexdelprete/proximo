#!/usr/bin/env python3
"""Live MUTATE->verify of Proximo's pve_create_container + pve_delete_guest end-to-end through
Proximo's stack against a REAL host, driven by a least-privilege scoped token.

Flow (asserting POST-STATE):
  1. PLAN create -> preview (assert it does not report the id as already taken)
  2. EXECUTE create_container SMOKE_VMID from SMOKE_TEMPLATE on SMOKE_STORE -> assert the CT actually
     materializes (status readable)
  3. EXECUTE delete_guest(purge) -> assert the CT is gone

SAFETY: creates + destroys ONE throwaway LXC on SMOKE_STORE. Needs the token scoped to allocate
/vms/<SMOKE_VMID> + Datastore on SMOKE_STORE + SDN.Use on the target bridge, and an LXC template at
SMOKE_TEMPLATE. Self-cleaning via try/finally. ONE-SHOT PER GRANT (destroy strips the /vms/<id> ACL).

Run (example):
    set -a; . /path/to/proximo.env; set +a
    SMOKE_VMID=103 SMOKE_STORE=test \
        SMOKE_TEMPLATE='test:vztmpl/alpine-3.23-default_20260116_amd64.tar.xz' \
        PROXIMO_TOKEN_PATH=/path/to/scoped-token \
        uv run python scripts/live-smoke/create-container-smoke.py
"""
from __future__ import annotations

import os
import sys
import time

from proximo.config_edit import guest_config_get
from proximo.provisioning import create_container, delete_guest, plan_create
from proximo.server import _svc

VMID = os.environ.get("SMOKE_VMID", "").strip()
STORE = os.environ.get("SMOKE_STORE", "").strip()
TEMPLATE = os.environ.get("SMOKE_TEMPLATE", "").strip()
KIND = "lxc"

if not (VMID and STORE and TEMPLATE):
    sys.exit("SMOKE_VMID, SMOKE_STORE, and SMOKE_TEMPLATE are required. Refusing to guess.")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from safety import assert_test_target, load_allowlist  # noqa: E402  (sibling live-smoke module)

# Independent SECOND safety layer: default-deny unless the VMID (create+PURGE target) and STORE are
# allowlisted test targets — refuses a prod id before any allocate/purge.
_AL = load_allowlist(os.environ)
assert_test_target(_AL, vmid=VMID, storage=STORE)


def _exists(api) -> bool:
    try:
        api.guest_status(VMID, KIND, None)
        return True
    except Exception:
        return False


def _unlocked(api) -> bool:
    # CT create holds a 'create' lock until the template finishes extracting; deleting before it
    # clears 500s with "CT is locked (create)". Wait for the lock to clear.
    if not _exists(api):
        return False
    try:
        return "lock" not in guest_config_get(api, VMID, KIND, None)
    except Exception:
        return False


def _wait(pred, timeout: int = 180) -> bool:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if pred():
            return True
        time.sleep(3)
    return pred()


def main() -> int:
    _, api, _, _ = _svc()
    r: dict[str, bool] = {}
    assert not _exists(api), f"{KIND}/{VMID} already exists — choose a free SMOKE_VMID; aborting"

    p = plan_create(api, VMID, KIND, None)
    r["plan_id_free"] = not any("already" in b.lower() and "use" in b.lower() for b in p.blast_radius)
    print(f"[1] PLAN create risk={p.risk}  id-free={r['plan_id_free']}")

    try:
        print(f"\n[2] create_container {VMID} from {TEMPLATE} on {STORE} ...")
        create_container(api, VMID, TEMPLATE, STORE, None,
                         rootfs=f"{STORE}:1", hostname="proximoctsmoke", memory=256, cores=1,
                         net0="name=eth0,bridge=vmbr0", unprivileged=1)
        r["ct_created"] = _wait(lambda: _unlocked(api))   # exists AND create-lock cleared
        print(f"    CT exists + unlocked = {r['ct_created']}")

        print(f"\n[3] delete_guest {VMID} purge -> gone ...")
        delete_guest(api, VMID, KIND, None, purge=True)
        r["ct_deleted"] = _wait(lambda: not _exists(api))
        print(f"    gone = {r['ct_deleted']}")
    finally:
        if _exists(api):
            print(f"    [cleanup] waiting for unlock then force delete_guest {VMID} ...")
            try:
                _wait(lambda: _unlocked(api), timeout=120)
                delete_guest(api, VMID, KIND, None, purge=True, force=True)
                _wait(lambda: not _exists(api), timeout=120)
            except Exception as e:
                print(f"    [cleanup] FAILED: {e!r} — MANUAL: pct unlock {VMID}; pct destroy {VMID} --purge")

    ok = all(r.values())
    print("\n" + "=" * 58)
    print(f"create_container + delete_guest MUTATE->verify ({KIND}/{VMID}): {'PASS' if ok else 'FAIL'}")
    for k, v in r.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
