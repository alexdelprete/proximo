#!/usr/bin/env python3
"""Live content-delete in-use-detection smoke (MUTATING, self-cleaning).

Verifies the content-delete blast radius against a real Proxmox: allocates a small scratch disk on a
test storage attached to a THROWAWAY VM, confirms `plan_content_delete` detects it as an in-use guest
disk (and still flags it after detach, via the `unused` slot), then deletes the volume through
Proximo's `content_delete` and cleans up — leaving the VM exactly as it started.

Operates ONLY on the VMID/storage you specify. Bound the token: it needs `VM.Config.Disk` on that VM
and `Datastore.AllocateSpace` on that storage, and should have neither anywhere else.

Env (in addition to the PROXIMO_* vars — see README.md):
  SMOKE_VMID    a throwaway QEMU VMID that has a SCSI controller (scsihw). REQUIRED.
  SMOKE_STORE   a test storage that supports `images` (isolate it from production). REQUIRED.
  SMOKE_SLOT    disk slot to allocate (default: scsi1 — must be free on the VM).
  SMOKE_SIZE    scratch disk size in GiB (default: 1).

Usage: set the PROXIMO_* env (see README), then:
  SMOKE_VMID=9900 SMOKE_STORE=your-test-store python3 scripts/live-smoke/content-delete-smoke.py
"""
from __future__ import annotations

import os
import sys
import time

from proximo.config_edit import guest_config_get
from proximo.server import _svc
from proximo.storage import content_delete, plan_content_delete, storage_content


def _volid(cfg: dict, slot: str) -> str | None:
    v = cfg.get(slot)
    return v.split(",", 1)[0].strip() if isinstance(v, str) else None


def _refs(cfg: dict, volid: str) -> list[str]:
    """Config keys whose value references `volid` (e.g. a dangling `unused` slot after the volume is gone)."""
    return [k for k, val in cfg.items()
            if isinstance(val, str) and val.split(",", 1)[0].strip() == volid]


def main() -> int:
    vmid = os.environ.get("SMOKE_VMID")
    store = os.environ.get("SMOKE_STORE")
    if not vmid or not store:
        print("set SMOKE_VMID=<throwaway qemu vmid> and SMOKE_STORE=<isolated test storage>", file=sys.stderr)
        return 2
    slot = os.environ.get("SMOKE_SLOT", "scsi1")
    size = os.environ.get("SMOKE_SIZE", "1")

    _, api, _, _ = _svc()
    cpath = f"/nodes/{api.config.node}/qemu/{vmid}/config"

    cfg0 = guest_config_get(api, vmid, "qemu", None)
    if not isinstance(cfg0, dict) or not cfg0:
        print(f"could not read config for vmid {vmid}", file=sys.stderr)
        return 2
    if slot in cfg0:
        print(f"slot {slot} is already in use on {vmid}; pick a free SMOKE_SLOT", file=sys.stderr)
        return 2
    boot0 = _volid(cfg0, "scsi0")
    ok: dict[str, bool] = {}
    volid: str | None = None

    try:
        # Disk-attach is intentionally NOT a Proximo config_set key (it refuses scsiN — a Datastore op,
        # not a safe config tweak), so test SETUP allocates via the raw API. PVE still enforces the
        # token's bound (VM.Config.Disk on the VM + Datastore on the storage). The op UNDER TEST is
        # plan_content_delete / content_delete, driven normally below.
        print(f"[1] allocate {slot} = {store}:{size} on vmid {vmid} ...")
        api._put(cpath, {slot: f"{store}:{size}"})
        time.sleep(2)
        volid = _volid(guest_config_get(api, vmid, "qemu", None), slot)
        ok["allocated_on_store"] = bool(volid) and volid.startswith(f"{store}:")
        print(f"    allocated: {volid}")
        if not ok["allocated_on_store"]:
            raise RuntimeError(f"scratch disk not on {store}: {volid!r}")

        print(f"[2] PLAN content_delete while ATTACHED ({slot}) -> expect in-use, names vmid {vmid} ...")
        p = plan_content_delete(api, store, volid)
        for line in p.blast_radius:
            print("   ", line)
        ok["in_use_attached"] = any(a.get("vmid") == str(vmid) for a in p.affected) and p.risk == "high"

        print(f"[3] detach {slot} (-> unused slot) and PLAN again -> still flagged in-use ...")
        api._put(cpath, {"delete": slot})
        time.sleep(1)
        p2 = plan_content_delete(api, store, volid)
        ok["in_use_unused_slot"] = any(a.get("vmid") == str(vmid) for a in p2.affected)

        print("[4] delete the scratch volume via Proximo content_delete ...")
        content_delete(api, store, volid)
        time.sleep(2)
        ok["volume_deleted"] = not any(c.get("volid") == volid for c in storage_content(api, store))
    finally:
        # Self-clean: drop any config key that still references our scratch volume (e.g. the dangling
        # `unused` slot content_delete leaves behind) and ensure the volume itself is gone. Touches only
        # OUR volume — pre-existing unused disks on the VM are left untouched.
        cfg = guest_config_get(api, vmid, "qemu", None) or {}
        for k in ([slot] if slot in cfg else []) + (_refs(cfg, volid) if volid else []):
            try:
                api._put(cpath, {"delete": k})
            except Exception as exc:
                print(f"    cleanup {k}: {type(exc).__name__}", file=sys.stderr)
        if volid:
            try:
                if any(c.get("volid") == volid for c in storage_content(api, store)):
                    content_delete(api, store, volid)
            except Exception as exc:
                print(f"    final volume cleanup ({volid}): {type(exc).__name__} — remove by hand if it lingers",
                      file=sys.stderr)

    cfg_final = guest_config_get(api, vmid, "qemu", None) or {}
    ok["boot_intact"] = _volid(cfg_final, "scsi0") == boot0
    ok["fully_clean"] = slot not in cfg_final and (not volid or not _refs(cfg_final, volid))

    print("\n" + "=" * 60)
    passed = all(ok.values())
    print(f"content-delete in-use smoke (vmid {vmid}, store {store}): {'PASS' if passed else 'FAIL'}")
    for k, v in ok.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
