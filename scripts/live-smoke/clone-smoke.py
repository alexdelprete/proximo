#!/usr/bin/env python3
"""Live MUTATE->verify of Proximo's pve_clone (with target storage) + pve_delete_guest end-to-end
through Proximo's stack against a REAL host, driven by a least-privilege scoped token.

Flow (asserting POST-STATE, not just HTTP 200):
  1. PLAN clone SMOKE_SRC_VMID -> SMOKE_NEW_VMID  (assert the plan discloses the target storage)
  2. EXECUTE a FULL clone with storage=SMOKE_STORE -> assert the clone's boot disk actually landed on
     SMOKE_STORE (the whole point of the target-storage param: keep the clone off the source storage)
  3. EXECUTE delete_guest(purge) on the clone -> assert the guest is gone AND its disk was purged
     from SMOKE_STORE (no orphan volume)

SAFETY: SMOKE_NEW_VMID must be a free, throwaway id the token is scoped to allocate (PVE 8 also needs
SDN.Use on the target bridge to attach the cloned NIC). The clone's disks go ONLY to SMOKE_STORE
(isolate it from production). Self-cleaning via try/finally.

ONE-SHOT PER GRANT: PVE removes a guest's `/vms/<id>` ACL when the guest is destroyed, so step 3's
delete strips the grant on SMOKE_NEW_VMID. Re-grant the token on that VMID before each re-run, e.g.:
    pveum acl modify /vms/<SMOKE_NEW_VMID> --roles ProximoTest --tokens '<user>@<realm>!<id>'

Run (example):
    set -a; . /path/to/proximo.env; set +a
    SMOKE_SRC_VMID=100 SMOKE_NEW_VMID=199 SMOKE_STORE=test \
        PROXIMO_TOKEN_PATH=/path/to/scoped-token \
        uv run python scripts/live-smoke/clone-smoke.py
"""
from __future__ import annotations

import os
import sys
import time

from proximo.config_edit import guest_config_get
from proximo.provisioning import clone_guest, delete_guest, plan_clone
from proximo.server import _svc
from proximo.storage import storage_content

SRC = os.environ.get("SMOKE_SRC_VMID", "").strip()
NEW = os.environ.get("SMOKE_NEW_VMID", "").strip()
STORE = os.environ.get("SMOKE_STORE", "").strip()
KIND = os.environ.get("SMOKE_KIND", "qemu").strip()

if not (SRC and NEW and STORE):
    sys.exit("SMOKE_SRC_VMID, SMOKE_NEW_VMID, and SMOKE_STORE are required. Refusing to guess.")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from safety import assert_test_target, load_allowlist  # noqa: E402  (sibling live-smoke module)

# Optional pool assignment (OFF by default): pool-create needs Pool.Allocate on the pool, which the
# scoped token lacks — the per-VMID grant (VM.Allocate on /vms/<NEW>) is self-sufficient. Set SMOKE_POOL
# only if the token is also granted Pool.Allocate on that pool.
POOL = os.environ.get("SMOKE_POOL", "").strip()

# Independent SECOND safety layer (beneath token scoping): default-deny unless the source, the NEW id,
# and the storage are all allowlisted test targets. NEW is the create+PURGE target — the catastrophe
# surface on a node that also runs prod — so the guard MUST refuse a prod id before any allocate/purge.
_AL = load_allowlist(os.environ)
assert_test_target(_AL, vmid=SRC)
assert_test_target(_AL, vmid=NEW, storage=STORE)


def _exists(api, vmid: str) -> bool:
    try:
        api.guest_status(vmid, KIND, None)
        return True
    except Exception:
        return False


def _wait(pred, timeout: int = 240) -> bool:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if pred():
            return True
        time.sleep(3)
    return pred()


def _boot_disk(api) -> str:
    return str(guest_config_get(api, NEW, KIND, None).get("scsi0", "")) if _exists(api, NEW) else ""


def _orphan_on_store(api) -> bool:
    return any(f"/vm-{NEW}-disk" in str(c.get("volid", "")) for c in storage_content(api, STORE))


def main() -> int:
    _, api, _, _ = _svc()
    r: dict[str, bool] = {}
    assert not _exists(api, NEW), f"{KIND}/{NEW} already exists — choose a free SMOKE_NEW_VMID; aborting"

    p = plan_clone(api, SRC, NEW, KIND, None, STORE)
    r["plan_discloses_target_storage"] = any(STORE in b for b in p.blast_radius)
    print(f"[1] PLAN risk={p.risk}  discloses target storage '{STORE}' = {r['plan_discloses_target_storage']}")

    try:
        print(f"\n[2] FULL clone {SRC} -> {NEW} storage={STORE} ...")
        clone_guest(api, SRC, NEW, KIND, None, name="proximoclonesmoke", full=True, storage=STORE,
                    pool=POOL or None)
        r["clone_materialized"] = _wait(
            lambda: _exists(api, NEW) and "lock" not in guest_config_get(api, NEW, KIND, None))
        disk = _boot_disk(api)
        r["clone_disk_on_target_storage"] = disk.startswith(f"{STORE}:")
        print(f"    boot disk = {disk}  (on '{STORE}': {r['clone_disk_on_target_storage']})")

        print(f"\n[3] delete_guest {NEW} purge -> guest gone + disk purged ...")
        delete_guest(api, NEW, KIND, None, purge=True)
        r["guest_deleted"] = _wait(lambda: not _exists(api, NEW))
        time.sleep(2)
        r["disk_purged"] = not _orphan_on_store(api)
        print(f"    gone={r['guest_deleted']}  no orphan disk on '{STORE}'={r['disk_purged']}")
    finally:
        if _exists(api, NEW):
            print(f"    [cleanup] force delete_guest {NEW} ...")
            try:
                delete_guest(api, NEW, KIND, None, purge=True, force=True)
                _wait(lambda: not _exists(api, NEW), timeout=120)
            except Exception as e:
                print(f"    [cleanup] FAILED: {e!r} — MANUAL: qm destroy {NEW} --purge")

    ok = all(r.values())
    print("\n" + "=" * 62)
    print(f"clone + delete_guest MUTATE->verify ({SRC}->{NEW} on '{STORE}'): {'PASS' if ok else 'FAIL'}")
    for k, v in r.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
