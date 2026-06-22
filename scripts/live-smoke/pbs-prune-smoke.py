#!/usr/bin/env python3
"""Live MUTATE->verify of proximo's PBS prune (self-seeding, self-cleaning).

  1. seed TWO host backups (backup-id=ci-prune) -> two recovery points in one group
  2. prune(keep_last=1, dry_run=True)  -> assert the plan marks exactly one for removal (keep=False)
  3. prune(keep_last=1, dry_run=False) -> assert exactly one snapshot remains in the group

Resolves the code's own 'Smoke-confirm' notes: hyphenated param names (keep-last) + decision shape.
GUARDED. Run with pbs-ci.env + PROXIMO_SMOKE_PBS_HOSTS=pbs-test.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pbs_smoke_lib import STORE, connect, seed_backup, snap_ids  # noqa: E402

from proximo.pbs import prune, snapshot_delete, snapshots_list  # noqa: E402

BID = "ci-prune"
_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str) -> None:
    _results.append((name, ok))
    print(f"{'✅' if ok else '❌'} {name}: {detail}")


def _mine(api) -> list[dict]:
    return [s for s in snapshots_list(api, STORE) if s.get("backup-id") == BID]


def main() -> int:
    api, cfg = connect()
    seed_backup(cfg, BID)
    time.sleep(2)            # distinct backup-time (PBS resolves to the second)
    seed_backup(cfg, BID)
    check("seeded_two", len(_mine(api)) >= 2, f"snapshots={snap_ids(_mine(api))}")
    try:
        plan = prune(api, STORE, keep_last=1, backup_type="host", backup_id=BID, dry_run=True)
        to_remove = [d for d in plan if not d.get("keep")]
        plan_repr = [(d.get("backup-time"), d.get("keep")) for d in plan]
        check("dry_run_plans_one_removal", len(to_remove) == 1, f"plan={plan_repr}")

        prune(api, STORE, keep_last=1, backup_type="host", backup_id=BID, dry_run=False)
        remaining = _mine(api)
        check("pruned_to_one", len(remaining) == 1, f"remaining={snap_ids(remaining)}")
    finally:
        for s in _mine(api):                    # self-clean
            snapshot_delete(api, STORE, s["backup-type"], s["backup-id"], s["backup-time"])

    passed = sum(1 for _, ok in _results if ok)
    ok = passed == len(_results)
    print(f"\nPBS prune MUTATE->verify ({STORE}): {'PASS' if ok else 'FAIL'}  {passed}/{len(_results)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
