#!/usr/bin/env python3
"""Live verify of proximo's PBS verify_start — proves REAL, SCOPED verification (self-seeding/cleaning).

A verify task returns exitstatus OK regardless of what it actually checked, so task-OK alone proves
nothing. PBS records per-snapshot verification state, so this smoke proves real work + honored scoping:

  1. seed TWO host backups: a target (ci-verify-t) and a decoy (ci-verify-d)
  2. verify_start SCOPED to backup-id=ci-verify-t -> wait for the async task (exitstatus OK)
  3. assert the TARGET snapshot now has verification.state == 'ok'  (it was actually verified)
  4. assert the DECOY snapshot has NO verification               (the backup-id scoping was honored)

GUARDED. Run with the PBS env + PROXIMO_SMOKE_PBS_HOSTS=<test-pbs-host>.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pbs_smoke_lib import STORE, connect, seed_backup, wait_task  # noqa: E402

from proximo.pbs import snapshot_delete, snapshots_list, verify_start  # noqa: E402

TARGET = "ci-verify-t"
DECOY = "ci-verify-d"
_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str) -> None:
    _results.append((name, ok))
    print(f"{'✅' if ok else '❌'} {name}: {detail}")


def _by_id(api, bid: str) -> dict | None:
    for s in snapshots_list(api, STORE):
        if s.get("backup-id") == bid:
            return s
    return None


def main() -> int:
    api, cfg = connect()
    seed_backup(cfg, TARGET)
    seed_backup(cfg, DECOY)
    try:
        upid = verify_start(api, STORE, backup_type="host", backup_id=TARGET)
        st = wait_task(api, upid)
        check("verify_task_ok", st.get("exitstatus") == "OK", f"exitstatus={st.get('exitstatus')}")

        tgt = (_by_id(api, TARGET) or {}).get("verification") or {}
        check("target_actually_verified", tgt.get("state") == "ok", f"target.verification={tgt or None}")

        dec = (_by_id(api, DECOY) or {}).get("verification")
        check("scoping_honored_decoy_untouched", dec is None, f"decoy.verification={dec}")
    finally:
        for bid in (TARGET, DECOY):              # self-clean
            s = _by_id(api, bid)
            if s:
                snapshot_delete(api, STORE, s["backup-type"], s["backup-id"], s["backup-time"])

    passed = sum(1 for _, ok in _results if ok)
    ok = passed == len(_results)
    print(f"\nPBS verify (real + scoped) ({STORE}): {'PASS' if ok else 'FAIL'}  {passed}/{len(_results)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
