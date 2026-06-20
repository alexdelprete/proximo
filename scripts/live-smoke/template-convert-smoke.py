#!/usr/bin/env python3
"""Live MUTATE->verify of Proximo's pve_template_convert end-to-end through Proximo's stack against a
REAL host, driven by a least-privilege scoped token.

template_convert is IRREVERSIBLE (no un-template endpoint), so this never touches a baseline VM — it
clones a throwaway first, converts the clone, and destroys it:
  1. FULL clone SMOKE_SRC_VMID -> SMOKE_NEW_VMID with storage=SMOKE_STORE (disposable, on test storage)
  2. assert the clone is NOT yet a template (baseline)
  3. PLAN template_convert -> assert RISK_HIGH (one-way, no undo claim)
  4. EXECUTE template_convert -> assert the guest is now a template (config `template == 1`)
  5. delete_guest(purge) the template -> assert gone

SAFETY: SMOKE_NEW_VMID must be a free throwaway id the token is scoped to allocate (+ SDN.Use on the
target bridge for the cloned NIC). Disks only on SMOKE_STORE. Self-cleaning via try/finally.
ONE-SHOT PER GRANT: the final destroy strips the `/vms/<id>` ACL — re-grant before re-running.

Run (example):
    set -a; . /path/to/proximo.env; set +a
    SMOKE_SRC_VMID=100 SMOKE_NEW_VMID=199 SMOKE_STORE=test \
        PROXIMO_TOKEN_PATH=/path/to/scoped-token \
        uv run python scripts/live-smoke/template-convert-smoke.py
"""
from __future__ import annotations

import os
import sys
import time

from proximo.cloudinit import plan_template_convert, template_convert
from proximo.config_edit import guest_config_get
from proximo.provisioning import clone_guest, delete_guest
from proximo.server import _svc

SRC = os.environ.get("SMOKE_SRC_VMID", "").strip()
NEW = os.environ.get("SMOKE_NEW_VMID", "").strip()
STORE = os.environ.get("SMOKE_STORE", "").strip()
KIND = "qemu"

if not (SRC and NEW and STORE):
    sys.exit("SMOKE_SRC_VMID, SMOKE_NEW_VMID, and SMOKE_STORE are required. Refusing to guess.")


def _exists(api) -> bool:
    try:
        api.guest_status(NEW, KIND, None)
        return True
    except Exception:
        return False


def _is_template(api) -> bool:
    return str(guest_config_get(api, NEW, KIND, None).get("template", "")) == "1"


def _wait(pred, timeout: int = 240) -> bool:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if pred():
            return True
        time.sleep(3)
    return pred()


def main() -> int:
    _, api, _, _ = _svc()
    r: dict[str, bool] = {}
    assert not _exists(api), f"{KIND}/{NEW} already exists — choose a free SMOKE_NEW_VMID; aborting"

    try:
        print(f"[1] FULL clone {SRC} -> {NEW} storage={STORE} (disposable) ...")
        clone_guest(api, SRC, NEW, KIND, None, name="proximotmplsmoke", full=True, storage=STORE)
        if not _wait(lambda: _exists(api) and "lock" not in guest_config_get(api, NEW, KIND, None)):
            print("    clone did not materialize — aborting")
            return 1
        r["not_template_before"] = not _is_template(api)
        print(f"    clone up; is_template (pre) = {_is_template(api)}")

        print("\n[2] PLAN template_convert -> expect RISK_HIGH (one-way) ...")
        p = plan_template_convert(api, NEW, None, KIND)
        r["plan_high_one_way"] = p.risk == "high"
        print(f"    risk={p.risk}")

        print("\n[3] EXECUTE template_convert -> guest becomes a template ...")
        template_convert(api, NEW, None, KIND)
        r["is_template_after"] = _wait(lambda: _is_template(api), timeout=60)
        print(f"    is_template (post) = {_is_template(api)}")

        print(f"\n[4] delete_guest {NEW} purge -> gone ...")
        delete_guest(api, NEW, KIND, None, purge=True)
        r["deleted"] = _wait(lambda: not _exists(api))
        print(f"    gone = {r['deleted']}")
    finally:
        if _exists(api):
            print(f"    [cleanup] force delete_guest {NEW} ...")
            try:
                delete_guest(api, NEW, KIND, None, purge=True, force=True)
                _wait(lambda: not _exists(api), timeout=120)
            except Exception as e:
                print(f"    [cleanup] FAILED: {e!r} — MANUAL: qm destroy {NEW} --purge")

    ok = all(r.values())
    print("\n" + "=" * 60)
    print(f"template_convert MUTATE->verify ({SRC}->{NEW} on '{STORE}'): {'PASS' if ok else 'FAIL'}")
    for k, v in r.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
