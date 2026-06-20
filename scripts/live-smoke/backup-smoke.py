#!/usr/bin/env python3
"""Live MUTATE->verify of Proximo's pve_backup + pve_backup_delete end-to-end through Proximo's stack
against a REAL host, driven by a least-privilege scoped token.

Flow (asserting POST-STATE):
  1. PLAN backup (snapshot mode) -> assert RISK_LOW (online, no halt)
  2. EXECUTE vzdump backup of SMOKE_VMID to SMOKE_STORE -> assert a NEW backup archive for that VMID
     actually appears in the storage's backup list
  3. EXECUTE backup_delete on that archive -> assert it is GONE from the list

SAFETY: backs up an existing throwaway SMOKE_VMID to SMOKE_STORE (isolate it from production; the token
needs VM.Backup on the VM + Datastore.AllocateSpace on SMOKE_STORE, and SMOKE_STORE must have `backup`
content enabled). Only the archive this run creates is deleted. Self-cleaning via try/finally.

Run (example):
    set -a; . /path/to/proximo.env; set +a
    SMOKE_VMID=100 SMOKE_STORE=test PROXIMO_TOKEN_PATH=/path/to/scoped-token \
        uv run python scripts/live-smoke/backup-smoke.py
"""
from __future__ import annotations

import os
import sys
import time

from proximo.backup import backup_delete, backup_list, plan_backup, vzdump_backup
from proximo.server import _svc

VMID = os.environ.get("SMOKE_VMID", "").strip()
STORE = os.environ.get("SMOKE_STORE", "").strip()
KIND = os.environ.get("SMOKE_KIND", "qemu").strip()

if not (VMID and STORE):
    sys.exit("SMOKE_VMID and SMOKE_STORE are required. Refusing to guess.")


def _archives(api) -> dict[str, dict]:
    return {str(b.get("volid", "")): b for b in backup_list(api, STORE, None)
            if f"{KIND}-{VMID}-" in str(b.get("volid", ""))}


def _wait(pred, timeout: int = 300) -> bool:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if pred():
            return True
        time.sleep(5)
    return pred()


def main() -> int:
    _, api, _, _ = _svc()
    r: dict[str, bool] = {}

    p = plan_backup(VMID, STORE, "snapshot", KIND)
    r["plan_low_risk"] = p.risk == "low"
    print(f"[1] PLAN backup (snapshot) risk={p.risk}")

    before = set(_archives(api))
    print(f"    existing {KIND}/{VMID} archives on '{STORE}': {len(before)}")

    new_volid = None
    try:
        print(f"\n[2] vzdump backup {KIND}/{VMID} -> {STORE} (snapshot) ...")
        vzdump_backup(api, VMID, STORE, "snapshot", "zstd", None)
        r["backup_created"] = _wait(lambda: len(set(_archives(api)) - before) >= 1)
        fresh = sorted(set(_archives(api)) - before)
        new_volid = fresh[-1] if fresh else None
        print(f"    new archive = {new_volid}")

        print("\n[3] backup_delete the new archive -> must be GONE ...")
        if new_volid:
            backup_delete(api, STORE, new_volid, None)
            r["backup_deleted"] = _wait(lambda: new_volid not in _archives(api), timeout=120)
        print(f"    gone = {r.get('backup_deleted')}")
    finally:
        if new_volid and new_volid in _archives(api):
            print(f"    [cleanup] deleting leftover archive {new_volid} ...")
            try:
                backup_delete(api, STORE, new_volid, None)
                _wait(lambda: new_volid not in _archives(api), timeout=120)
            except Exception as e:
                print(f"    [cleanup] FAILED: {e!r} — MANUAL: delete {new_volid} from {STORE}")

    r["no_residue"] = (new_volid is None) or (new_volid not in _archives(api))
    ok = all(r.values())
    print("\n" + "=" * 58)
    print(f"backup + backup_delete MUTATE->verify ({KIND}/{VMID} on '{STORE}'): {'PASS' if ok else 'FAIL'}")
    for k, v in r.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
