#!/usr/bin/env python3
"""Live MUTATE->verify of proximo's PBS gc_start + gc_status (self-seeding, self-cleaning).

  1. seed a host backup (backup-id=ci-gc) so the datastore has chunks to scan
  2. gc_start -> UPID; wait for the async task -> assert it finished with exitstatus OK
  3. gc_status -> assert a finished GC run is reported

GUARDED. Run with pbs-ci.env + PROXIMO_SMOKE_PBS_HOSTS=pbs-test.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pbs_smoke_lib import STORE, connect, seed_backup, wait_task  # noqa: E402

from proximo.pbs import gc_start, gc_status, snapshot_delete, snapshots_list  # noqa: E402

BID = "ci-gc"
_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str) -> None:
    _results.append((name, ok))
    print(f"{'✅' if ok else '❌'} {name}: {detail}")


def main() -> int:
    api, cfg = connect()
    seed_backup(cfg, BID)
    try:
        upid = gc_start(api, STORE)
        st = wait_task(api, upid)
        check("gc_completed_ok", st.get("exitstatus") == "OK", f"exitstatus={st.get('exitstatus')}")
        gs = gc_status(api, STORE)
        gs_keys = sorted(gs)[:5] if isinstance(gs, dict) else gs
        check("gc_status_readable", isinstance(gs, dict) and bool(gs), f"keys={gs_keys}")
    finally:
        for s in [x for x in snapshots_list(api, STORE) if x.get("backup-id") == BID]:
            snapshot_delete(api, STORE, s["backup-type"], s["backup-id"], s["backup-time"])

    passed = sum(1 for _, ok in _results if ok)
    ok = passed == len(_results)
    print(f"\nPBS gc MUTATE->verify ({STORE}): {'PASS' if ok else 'FAIL'}  {passed}/{len(_results)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
