#!/usr/bin/env python3
"""Live MUTATE->verify of proximo's PBS snapshot_delete (self-seeding, self-cleaning).

  1. seed a throwaway host backup (backup-id=ci-snapdel) into the test datastore
  2. snapshot_delete it through proximo -> assert it is GONE from snapshots_list

GUARDED (refuses non-allowlisted PBS host). Run with pbs-ci.env + PROXIMO_SMOKE_PBS_HOSTS=pbs-test.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pbs_smoke_lib import STORE, connect, seed_backup, snap_ids  # noqa: E402

from proximo.pbs import snapshot_delete, snapshots_list  # noqa: E402

BID = "ci-snapdel"
_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str) -> None:
    _results.append((name, ok))
    print(f"{'✅' if ok else '❌'} {name}: {detail}")


def _mine(api) -> list[dict]:
    return [s for s in snapshots_list(api, STORE) if s.get("backup-id") == BID]


def main() -> int:
    api, cfg = connect()
    seed_backup(cfg, BID)
    mine = _mine(api)
    check("seeded", len(mine) >= 1, f"snapshots={snap_ids(mine)}")
    snap = mine[0]
    try:
        snapshot_delete(api, STORE, snap["backup-type"], snap["backup-id"], snap["backup-time"])
        gone = not any(s.get("backup-time") == snap["backup-time"] for s in _mine(api))
        check("snapshot_deleted", gone, f"gone={gone}")
    finally:
        for s in _mine(api):                    # self-clean any residue
            snapshot_delete(api, STORE, s["backup-type"], s["backup-id"], s["backup-time"])

    passed = sum(1 for _, ok in _results if ok)
    ok = passed == len(_results)
    print(f"\nPBS snapshot_delete MUTATE->verify ({STORE}): {'PASS' if ok else 'FAIL'}  {passed}/{len(_results)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
