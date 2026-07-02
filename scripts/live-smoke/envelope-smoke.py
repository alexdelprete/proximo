#!/usr/bin/env python3
"""Live verification of Proximo's autonomy ENVELOPE (`envelope.py`) — the FORBID + RATE walls that
guard every mutation seam — end-to-end through the real `pve_snapshot_create`/`pve_snapshot_delete`
tools against a REAL host + a throwaway SMOKE_VMID.

Why this script exists: the envelope (`PROXIMO_FORBID` / `PROXIMO_RATE_MAX` / `PROXIMO_RATE_WINDOW`)
is unit-proven exhaustively (`tests/test_envelope.py`, including a 20-thread concurrency barrier) but
had ZERO live-smoke coverage before this — no script under `scripts/live-smoke/` ever set
`PROXIMO_FORBID` or `PROXIMO_RATE_MAX`, so the newest trust-spine wall was 100% unit-proven and 0%
live-proven. This closes that gap for the two headline behaviors:

  [1] FORBID wall — a forbidden action is refused BEFORE it reaches the backend (no mutation).
  [2] RATE wall   — the (N+1)th mutating attempt inside the window is refused, proven under REAL
                    concurrent calls (a `threading.Barrier` releases every caller simultaneously —
                    the same shape as `test_envelope.py::test_rate_concurrency_barrier`, but here
                    every call is a real `pve_snapshot_create` against live PVE, not a stubbed
                    lambda).

Both walls fire BEFORE the real backend call (`enforce_envelope`, called from `_audited`), so a
BLOCKED attempt never touches PVE — only the ALLOWED rate-budget slots create a real (uniquely
named) snapshot, and those are the only things this script has to clean up.

Flow (asserting POST-STATE, not just the exception type):
  [1] set `PROXIMO_FORBID=pve_snapshot_create` -> `pve_snapshot_create(confirm=True)` on a probe
      snapshot name -> assert `ProximoError` mentioning "forbidden", assert the probe snapshot never
      appeared, assert the ledger recorded `outcome="blocked:forbidden"`. Restore `PROXIMO_FORBID`.
  [2] set `PROXIMO_RATE_MAX=<small>` + `PROXIMO_RATE_WINDOW=<generous>`; clear any reservation file
      this box already has on disk (see CAVEAT) for a deterministic run; fire more callers than the
      budget at a `Barrier`, each creating a DIFFERENT snapshot name simultaneously -> assert EXACTLY
      `rate_max` succeed (`status == "submitted"`) and the rest raise `ProximoError` mentioning "rate
      budget"; await the successful tasks; assert those snapshots really exist; assert the ledger
      recorded `outcome="blocked:rate_budget"` for at least one refusal. Restore
      `PROXIMO_RATE_MAX`/`PROXIMO_RATE_WINDOW`, then delete every snapshot [2] created.

SAFETY: bounded by the `safety.py` allowlist (the same second layer every mutate smoke uses) to the
throwaway `SMOKE_VMID`. [1] never reaches the backend at all. [2] creates/deletes only
uniquely-named scratch snapshots on `SMOKE_VMID`; self-cleaning via try/finally. Any pre-existing
`PROXIMO_FORBID` / `PROXIMO_RATE_MAX` / `PROXIMO_RATE_WINDOW` in the calling env is saved and
restored (never left clobbered), so this script is safe to run in an env that already configures the
envelope for other reasons.

CAVEAT (read before re-running back-to-back): the rate wall's budget is a REAL per-box reservation
file (`<dirname(audit.path)>/.proximo-rate/<sha256(base_url)[:16]>.rate`) that persists across runs
for `PROXIMO_RATE_WINDOW` seconds — that persistence IS the feature under test. This script clears
its own box's reservation file immediately before [2] so back-to-back runs are deterministic; that
is setup on the exact counter this smoke proves, not a change to unrelated production data. Do not
run this concurrently with other mutating traffic against the same `PROXIMO_API_BASE_URL` — it
shares that box's real reservation file and will contend for its real budget. The other opt-in gates
(CONTAIN/SCOPE/LEASE/CONSENT) are assumed unconfigured for this run; if any of them ARE configured in
your env, they fire before the envelope check and may block this script's own probes for a different
reason — that's correct layering, not a bug here.

Run (example):
    set -a; . /path/to/proximo.env; set +a
    SMOKE_VMID=9900 PROXIMO_TOKEN_PATH=/path/to/scoped-token \
        uv run python scripts/live-smoke/envelope-smoke.py

Optional tuning (all have defaults — see the constants below):
    SMOKE_ENVELOPE_RATE_MAX     rate budget to configure for the test window (default 2)
    SMOKE_ENVELOPE_RATE_EXTRA   extra concurrent callers beyond the budget    (default 3)
    SMOKE_ENVELOPE_RATE_WINDOW  rate window in seconds                       (default 60)
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time

from proximo.backends import ProximoError
from proximo.envelope import _RESERVATION_SUBDIR, _box_key
from proximo.server import _svc, pve_snapshot_create, pve_snapshot_delete

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from safety import assert_test_target, load_allowlist  # noqa: E402  (sibling live-smoke module)

VMID = os.environ.get("SMOKE_VMID", "").strip()
KIND = os.environ.get("SMOKE_KIND", "qemu").strip()
RATE_MAX = int(os.environ.get("SMOKE_ENVELOPE_RATE_MAX", "2"))
RATE_EXTRA = int(os.environ.get("SMOKE_ENVELOPE_RATE_EXTRA", "3"))  # extra callers beyond the budget
RATE_WINDOW = int(os.environ.get("SMOKE_ENVELOPE_RATE_WINDOW", "60"))
N_CALLERS = RATE_MAX + RATE_EXTRA
FORBID_SNAP = "proximoenvelopesmoke-forbid-probe"
RATE_SNAPS = [f"proximoenvelopesmoke-rate-{i}" for i in range(N_CALLERS)]

if not VMID:
    sys.exit("SMOKE_VMID is required (a throwaway VMID the token is scoped to). Refusing to guess.")

# Independent SECOND safety layer (beneath token scoping): default-deny unless VMID is an allowlisted
# test target. Set PROXIMO_SMOKE_TEST_VMIDS / PROXIMO_SMOKE_VMID_RANGE. See safety.py.
assert_test_target(load_allowlist(os.environ), vmid=VMID)

# Never clobber envelope config the calling env already carries for other reasons — save now,
# restore in every finally below.
_SAVED_ENV = {k: os.environ.get(k) for k in ("PROXIMO_FORBID", "PROXIMO_RATE_MAX", "PROXIMO_RATE_WINDOW")}


def _restore_env() -> None:
    for k, v in _SAVED_ENV.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _snaps(api) -> set[str]:
    return {s.get("name", "") for s in api.snapshot_list(VMID, KIND, None)}


def _wait_task(api, upid, timeout: int = 90) -> bool:
    if not isinstance(upid, str) or not upid.startswith("UPID:"):
        return True  # sync / no-op result
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if api.task_status(upid, None).get("status") == "stopped":
            return True
        time.sleep(2)
    return False


def _tail(path: str, n: int = 300) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()[-n:]
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def main() -> int:
    _, api, _, ledger = _svc()
    r: dict[str, bool] = {}

    assert FORBID_SNAP not in _snaps(api), f"probe snapshot {FORBID_SNAP} already exists — aborting"
    for n in RATE_SNAPS:
        assert n not in _snaps(api), f"probe snapshot {n} already exists — aborting"

    try:
        # === [1] FORBID wall =====================================================================
        print("\n[1] FORBID wall: PROXIMO_FORBID=pve_snapshot_create -> attempt create ...")
        os.environ["PROXIMO_FORBID"] = "pve_snapshot_create"
        blocked, err_msg = False, ""
        try:
            pve_snapshot_create(VMID, FORBID_SNAP, KIND, confirm=True)
        except ProximoError as e:
            blocked, err_msg = True, str(e)
        os.environ.pop("PROXIMO_FORBID", None)  # clear immediately, before anything else runs

        r["forbid_raised"] = blocked and "forbidden" in err_msg.lower()
        r["forbid_no_mutation"] = FORBID_SNAP not in _snaps(api)
        tail1 = _tail(ledger.path)
        r["forbid_ledger_recorded"] = any(
            e.get("action") == "pve_snapshot_create" and e.get("outcome") == "blocked:forbidden"
            for e in tail1)
        print(f"    raised={blocked}  msg={err_msg!r}")
        print(f"    no mutation={r['forbid_no_mutation']}  ledger recorded={r['forbid_ledger_recorded']}")

        # === [2] RATE wall (real concurrency) ===================================================
        print(f"\n[2] RATE wall: PROXIMO_RATE_MAX={RATE_MAX} window={RATE_WINDOW}s, "
              f"{N_CALLERS} concurrent callers ...")
        base_url = os.environ.get("PROXIMO_API_BASE_URL", "").strip().rstrip("/")
        if not base_url:
            sys.exit("PROXIMO_API_BASE_URL must be set (the rate wall needs a resolvable box identity)")
        rate_path = os.path.join(os.path.dirname(ledger.path), _RESERVATION_SUBDIR,
                                  f"{_box_key(base_url)}.rate")
        if os.path.exists(rate_path):
            print(f"    clearing stale reservation file {rate_path} (deterministic re-run; see CAVEAT)")
            os.remove(rate_path)

        os.environ["PROXIMO_RATE_MAX"] = str(RATE_MAX)
        os.environ["PROXIMO_RATE_WINDOW"] = str(RATE_WINDOW)

        barrier = threading.Barrier(N_CALLERS)
        results: dict[str, tuple[str, object]] = {}
        results_lock = threading.Lock()

        def worker(name: str) -> None:
            barrier.wait()
            try:
                resp = pve_snapshot_create(VMID, name, KIND, confirm=True)
                outcome = "ok" if resp.get("status") == "submitted" else f"unexpected:{resp!r}"
                payload: object = resp.get("result")
            except ProximoError as e:
                msg = str(e).lower()
                outcome = "blocked" if "rate budget" in msg else f"unexpected-error:{e}"
                payload = None
            with results_lock:
                results[name] = (outcome, payload)

        threads = [threading.Thread(target=worker, args=(n,)) for n in RATE_SNAPS]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # Restore the rate env immediately after the barrier settles — cleanup below must not be
        # gated by the very budget we just deliberately exhausted.
        _restore_env()

        succeeded = [n for n, (o, _) in results.items() if o == "ok"]
        blocked_names = [n for n, (o, _) in results.items() if o == "blocked"]
        weird = {n: o for n, (o, _) in results.items() if o not in ("ok", "blocked")}

        r["rate_all_threads_reported"] = len(results) == N_CALLERS
        r["rate_exact_budget_succeeded"] = len(succeeded) == RATE_MAX
        r["rate_rest_blocked"] = len(blocked_names) == N_CALLERS - RATE_MAX
        r["rate_no_unexpected_outcomes"] = weird == {}
        print(f"    succeeded={len(succeeded)} (want {RATE_MAX})  blocked={len(blocked_names)} "
              f"(want {N_CALLERS - RATE_MAX})  weird={weird}")

        for n in succeeded:
            _wait_task(api, results[n][1])
        r["rate_succeeded_snapshots_exist"] = all(n in _snaps(api) for n in succeeded)
        print(f"    succeeded snapshots present = {r['rate_succeeded_snapshots_exist']}")

        tail2 = _tail(ledger.path)
        r["rate_ledger_recorded_block"] = any(
            e.get("action") == "pve_snapshot_create" and e.get("outcome") == "blocked:rate_budget"
            for e in tail2)
        print(f"    ledger recorded a blocked:rate_budget entry = {r['rate_ledger_recorded_block']}")
    finally:
        _restore_env()  # belt-and-suspenders: restore even if an assertion above raised
        for n in RATE_SNAPS:
            if n in _snaps(api):
                print(f"\n[cleanup] deleting {n} ...")
                try:
                    resp = pve_snapshot_delete(VMID, n, KIND, confirm=True)
                    _wait_task(api, resp.get("result"))
                except Exception as e:
                    print(f"    [cleanup] FAILED: {e!r} — MANUAL: qm/pct delsnapshot {VMID} {n}")

    r["cleaned_up"] = not any(n in _snaps(api) for n in RATE_SNAPS) and FORBID_SNAP not in _snaps(api)

    ok = all(r.values())
    print("\n" + "=" * 64)
    print(f"autonomy-envelope (FORBID + RATE) live-verify on {KIND}/{VMID}: {'PASS' if ok else 'FAIL'}")
    for k, v in r.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
