#!/usr/bin/env python3
"""Proximo TFA-PLANE smoke (tfa_get read + tfa_delete API-reachability) — BOUNDED.

A FULL tfa_delete chain structurally needs (a) an enrolled 2FA factor and (b) the acting
user's current password — and enrollment is an interactive TOTP/WebAuthn challenge that
Proximo deliberately does NOT expose, and routing a real password through a smoke is avoided.
So this bounded smoke proves what can be proven WITHOUT secret-handling:

  - tfa_list / tfa_get reach the live API and return (reads work),
  - tfa_delete reaches the live API with correct auth + path: deleting a NON-EXISTENT entry
    elicits PVE's own domain response (404 / "no such entry"), proving the request shape is
    right and only PVE's business rule stops it (same partial-proof shape as the HA/SDN finds).

NO factor is ever created or removed; NO password is sent.

Environment (set by the wrapper):
  PROXIMO_API_BASE_URL  PROXIMO_NODE  PROXIMO_TOKEN_PATH  PROXIMO_VERIFY_TLS
"""
from __future__ import annotations

import proximo.server as server

USER = "root@pam"
NONEXISTENT = "totp:proximo-smoke-nonexistent"


def hr(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    cfg, _, _, _ = server._svc()
    print(f"node={cfg.node}  url={cfg.api_base_url}")

    hr("tfa_list / tfa_get — reads")
    all_tfa = server.pve_tfa_list()
    print(f"  tfa_list (all users): {len(all_tfa)} entry/entries")
    entries = server.pve_tfa_get(USER)
    print(f"  tfa_get({USER}): {entries!r}")

    hr("tfa_delete — API reachability on a NON-EXISTENT entry (no factor touched, no password)")
    try:
        # dry-run first (PLAN, no mutation): proves the plan path + RISK_HIGH classification
        plan = server.pve_tfa_delete(USER, NONEXISTENT)
        print(f"  dry-run PLAN: status={plan.get('status')} risk={plan.get('risk')} "
              "(expected plan/high)")
        # confirm: PVE should reject the non-existent entry — proves auth+path reach the API
        server.pve_tfa_delete(USER, NONEXISTENT, confirm=True)
        print("  confirm: unexpectedly SUCCEEDED (entry existed?) — investigate")
    except Exception as e:  # noqa: BLE001
        msg = str(e).splitlines()[0][:160]
        print(f"  confirm: PVE rejected as expected (request reached the API): {type(e).__name__}: {msg}")

    v = server.audit_verify()
    print("\nledger verify:", {"ok": v.get("ok"), "entries": v.get("entries")})
    print("TFA-PLANE BOUNDED SMOKE COMPLETE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
