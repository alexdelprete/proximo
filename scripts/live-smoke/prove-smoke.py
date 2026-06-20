#!/usr/bin/env python3
"""Live verification of Proximo's PROVE pillar (the tamper-evident audit ledger) + the confirm-gate,
end-to-end through the actual @mcp.tool `pve_*` wrappers against a REAL host. This is the one pillar
the per-plane smokes deliberately do NOT exercise (they call the lib functions directly); here we go
through the full tool stack so the ledger write + confirm-gate ARE in the live path.

Flow (asserting POST-STATE):
  1. confirm=False on a real mutation tool -> assert it returns a PLAN and performs NO mutation
  2. confirm=True -> assert the mutation actually happens AND the ledger grows AND still verifies
     (chain intact after a real destructive write)
  3. assert the mutation is RECORDED in the ledger under the right action
  4. TAMPER a COPY of the ledger -> assert verify() detects the break (tamper-evidence, live)
  5. clean up the mutation (also through a confirm=True tool, so delete is ledgered too); assert the
     real ledger still verifies

Uses pve_snapshot_create/delete on the throwaway SMOKE_VMID (bounded; the snapshot is the same safe op
the lifecycle smoke uses). Self-cleaning. The tamper test never touches the real ledger.

Run (example):
    set -a; . /path/to/proximo.env; set +a
    SMOKE_VMID=100 PROXIMO_TOKEN_PATH=/path/to/scoped-token \
        uv run python scripts/live-smoke/prove-smoke.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

from proximo.audit import AuditLedger
from proximo.server import _svc, audit_verify, pve_snapshot_create, pve_snapshot_delete

VMID = os.environ.get("SMOKE_VMID", "").strip()
KIND = "qemu"
SNAP = "proximoprovesmoke"

if not VMID:
    sys.exit("SMOKE_VMID is required (a throwaway QEMU VMID the token is scoped to). Refusing to guess.")


def main() -> int:
    _, api, _, ledger = _svc()
    path = ledger.path
    r: dict[str, bool] = {}

    def snaps() -> set[str]:
        return {s.get("name", "") for s in api.snapshot_list(VMID, KIND, None)}

    def wait(pred, timeout=90) -> bool:
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if pred():
                return True
            time.sleep(2)
        return pred()

    v0 = audit_verify()
    assert v0["ok"], f"ledger already broken before we start: {v0}"
    assert SNAP not in snaps(), f"snapshot {SNAP} already exists — aborting"
    n0 = v0["entries"]
    print(f"baseline: ledger entries={n0} ok={v0['ok']} keyed={v0['keyed']}")

    try:
        print("\n[1] confirm=False -> must be a PLAN, no mutation ...")
        dry = pve_snapshot_create(VMID, SNAP, KIND, confirm=False)
        r["dryrun_is_plan"] = dry.get("status") == "plan"
        r["dryrun_no_mutation"] = SNAP not in snaps()
        print(f"    status={dry.get('status')}  snapshot absent={r['dryrun_no_mutation']}")

        print("\n[2] confirm=True -> real mutation + ledger write ...")
        pve_snapshot_create(VMID, SNAP, KIND, confirm=True)
        r["snapshot_created"] = wait(lambda: SNAP in snaps())
        wait(lambda: "lock" not in api.guest_status(VMID, KIND, None))  # let the create task settle
        v1 = audit_verify()
        r["ledger_grew"] = v1["entries"] > n0
        r["ledger_valid_after_mutation"] = v1["ok"]
        print(f"    snapshot present={r['snapshot_created']}  ledger entries {n0}->{v1['entries']}  ok={v1['ok']}")

        print("\n[3] mutation RECORDED under the right action ...")
        tail = [json.loads(ln) for ln in open(path).read().splitlines()[-8:]]
        r["mutation_recorded"] = any(
            e.get("action") == "pve_snapshot_create" and e.get("outcome") in ("submitted", "ok")
            for e in tail)
        print(f"    pve_snapshot_create submitted-entry present = {r['mutation_recorded']}")

        print("\n[4] TAMPER a COPY of the ledger -> verify() must DETECT ...")
        lines = open(path).read().splitlines()
        objs = [json.loads(ln) for ln in lines]
        mid = max(0, len(objs) // 2)
        objs[mid]["target"] = str(objs[mid].get("target", "")) + "_TAMPERED"  # alter body, leave stored hash
        tmp_fd, tmp = tempfile.mkstemp(prefix="proximo-tamper-", suffix=".log")
        os.close(tmp_fd)
        with open(tmp, "w") as f:
            f.write("\n".join(json.dumps(o) for o in objs) + "\n")
        tv = AuditLedger(tmp, key=ledger.key).verify()
        os.unlink(tmp)
        r["tamper_detected"] = (not tv.ok) and tv.broken_at is not None
        print(f"    tampered copy verify ok={tv.ok} broken_at={tv.broken_at} ({tv.reason})")
    finally:
        if SNAP in snaps():
            print(f"\n[cleanup] pve_snapshot_delete {SNAP} (confirm=True, also ledgered) ...")
            try:
                pve_snapshot_delete(VMID, SNAP, KIND, confirm=True)
                wait(lambda: SNAP not in snaps())
            except Exception as e:
                print(f"    [cleanup] FAILED: {e!r} — MANUAL: qm delsnapshot {VMID} {SNAP}")

    r["ledger_valid_after_cleanup"] = audit_verify()["ok"]

    ok = all(r.values())
    print("\n" + "=" * 60)
    print(f"PROVE (audit ledger + confirm-gate) live-verify on {KIND}/{VMID}: {'PASS' if ok else 'FAIL'}")
    for k, v in r.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
