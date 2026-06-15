#!/usr/bin/env python3
"""Proximo FIREWALL-OBJECTS-PLANE mutation smoke (aliases / ipsets / security-groups / options).

Live-proves the 2026-06-14 firewall completion plane against a real Proxmox VE node by
driving create -> read -> delete of PASSIVE firewall config objects through Proximo's own
MCP tools. These objects (aliases, ip-sets, security groups) change traffic ONLY when a
rule references them, so create/read/delete has zero connectivity effect — the same shape
as the governance plane that was already live-proven.

What it exercises (all cluster scope; firewall is NEVER enabled):
  - ALIASES:         create -> list-by-name -> update(cidr) -> delete -> confirm gone
  - IP-SETS:         create -> entry_add -> read entries -> entry_remove -> delete -> gone
  - SECURITY-GROUPS: create -> list-by-name -> delete -> confirm gone
  - OPTIONS:         options_get (read) + options_set PLAN dry-run only (NO live mutation —
                     a policy/enable change carries lockout risk, so it is never executed here)

Self-cleaning: a `finally` block removes any throwaway-named object that survives, gated on a
'did I create it' flag, with a LOUD manual-cleanup fallback. firewall_set_enabled is never called.

Environment (set by the wrapper script; see fwobjects-smoke.sh and README.md):
  PROXIMO_API_BASE_URL  PROXIMO_NODE  PROXIMO_TOKEN_PATH  PROXIMO_VERIFY_TLS
  SMOKE_ALIAS  SMOKE_IPSET  SMOKE_SG   (throwaway names; safe self-describing defaults)
"""
from __future__ import annotations

import os

import proximo.server as server

# Throwaway identifiers. Names must match PVE's [A-Za-z][A-Za-z0-9-_]+ constraint.
ALIAS: str = os.environ.get("SMOKE_ALIAS", "proximo-smoke-alias")
IPSET: str = os.environ.get("SMOKE_IPSET", "proximosmokeset")
SG: str = os.environ.get("SMOKE_SG", "proximo-smoke-grp")
CIDR_A = "203.0.113.0/24"   # TEST-NET-3 (RFC 5737) — never a real host
CIDR_B = "203.0.113.128/25"
ENTRY = "198.51.100.5"      # TEST-NET-2 — single host


def hr(title: str) -> None:
    print(f"\n=== {title} ===")


def alias_exists(name: str) -> bool:
    try:
        return any(a.get("name") == name for a in server.pve_firewall_alias_list(scope="cluster"))
    except Exception as e:  # noqa: BLE001 — a failed read must NOT be treated as "absent"
        print(f"  (alias-list read failed: {type(e).__name__}: {e})")
        return True  # fail-safe: assume it might exist so cleanup still attempts removal


def ipset_exists(name: str) -> bool:
    try:
        return any(s.get("name") == name for s in server.pve_ipset_list(scope="cluster"))
    except Exception as e:  # noqa: BLE001
        print(f"  (ipset-list read failed: {type(e).__name__}: {e})")
        return True


def sg_exists(name: str) -> bool:
    try:
        return any(g.get("group") == name for g in server.pve_security_groups_list())
    except Exception as e:  # noqa: BLE001
        print(f"  (sg-list read failed: {type(e).__name__}: {e})")
        return True


def main() -> int:
    cfg, api, _, _ = server._svc()
    print(f"node={cfg.node}  url={cfg.api_base_url}")
    print(f"throwaway: alias={ALIAS!r}  ipset={IPSET!r}  sg={SG!r}")

    alias_created = ipset_created = sg_created = False
    try:
        # ---- ALIASES: create -> list-by-name -> update -> delete ---------------------------
        hr("aliases — create / list-by-name / update(cidr) / delete")
        server.pve_firewall_alias_create(ALIAS, CIDR_A, comment="proximo smoke", confirm=True)
        alias_created = True
        found = next((a for a in server.pve_firewall_alias_list(scope="cluster")
                      if a.get("name") == ALIAS), None)
        print(f"  created; read-back cidr={found and found.get('cidr')}")
        server.pve_firewall_alias_update(ALIAS, cidr=CIDR_B, confirm=True)
        found2 = next((a for a in server.pve_firewall_alias_list(scope="cluster")
                       if a.get("name") == ALIAS), None)
        print(f"  updated; read-back cidr={found2 and found2.get('cidr')} (expected {CIDR_B})")
        server.pve_firewall_alias_delete(ALIAS, confirm=True)
        alias_created = alias_exists(ALIAS)
        print(f"  deleted; gone? {not alias_created}")

        # ---- IP-SETS: create -> entry_add -> read entries -> entry_remove -> delete ---------
        hr("ip-sets — create / entry_add / read / entry_remove / delete")
        server.pve_firewall_ipset_create(IPSET, comment="proximo smoke", confirm=True)
        ipset_created = True
        server.pve_firewall_ipset_entry_add(IPSET, ENTRY, comment="smoke entry", confirm=True)
        # verify the entry landed (read the set's content directly — no entries-list tool)
        entries = api._get(f"/cluster/firewall/ipset/{IPSET}") or []
        print(f"  created + entry added; members={[e.get('cidr') for e in entries]}")
        server.pve_firewall_ipset_entry_remove(IPSET, ENTRY, confirm=True)
        entries2 = api._get(f"/cluster/firewall/ipset/{IPSET}") or []
        print(f"  entry removed; members now={[e.get('cidr') for e in entries2]}")
        server.pve_firewall_ipset_delete(IPSET, confirm=True)
        ipset_created = ipset_exists(IPSET)
        print(f"  deleted; gone? {not ipset_created}")

        # ---- SECURITY GROUPS: create -> list-by-name -> delete -----------------------------
        hr("security-groups — create / list-by-name / delete")
        server.pve_firewall_security_group_create(SG, comment="proximo smoke", confirm=True)
        sg_created = True
        present = any(g.get("group") == SG for g in server.pve_security_groups_list())
        print(f"  created; present? {present}")
        server.pve_firewall_security_group_delete(SG, confirm=True)
        sg_created = sg_exists(SG)
        print(f"  deleted; gone? {not sg_created}")

        # ---- OPTIONS: read + PLAN dry-run only (never mutate firewall posture live) ---------
        hr("options — read + options_set PLAN dry-run (NO live mutation)")
        opts = server.pve_firewall_options_get(scope="cluster")
        print(f"  options_get keys={sorted(opts.keys())}")
        plan = server.pve_firewall_options_set(options={"policy_in": "DROP"})  # no confirm -> PLAN
        print(f"  options_set(policy_in=DROP) PLAN: status={plan.get('status')} risk={plan.get('risk')}"
              " (expected plan/high — proves lockout classification, executes nothing)")

    finally:
        hr("cleanup (guaranteed)")
        if alias_exists(ALIAS):
            server.pve_firewall_alias_delete(ALIAS, confirm=True)
            print(f"  removed leftover alias ({ALIAS!r})")
        if ipset_exists(IPSET):
            server.pve_firewall_ipset_delete(IPSET, force=True, confirm=True)
            print(f"  removed leftover ipset ({IPSET!r}, force)")
        if sg_exists(SG):
            server.pve_firewall_security_group_delete(SG, confirm=True)
            print(f"  removed leftover security group ({SG!r})")
        residue: list[str] = []
        if alias_exists(ALIAS):
            residue.append(f"alias {ALIAS!r}")
        if ipset_exists(IPSET):
            residue.append(f"ipset {IPSET!r}")
        if sg_exists(SG):
            residue.append(f"security group {SG!r}")
        if residue:
            print("  !!! MANUAL CLEANUP NEEDED on your PVE host:")
            for item in residue:
                print(f"      {item}")
            print(f"  pvesh delete /cluster/firewall/aliases/{ALIAS}")
            print(f"  pvesh delete /cluster/firewall/ipset/{IPSET} -force 1")
            print(f"  pvesh delete /cluster/firewall/groups/{SG}")
        else:
            print("  clean — no throwaway artifacts remain")

    v = server.audit_verify()
    print("\nledger verify:", {"ok": v.get("ok"), "entries": v.get("entries")})
    print("FIREWALL-OBJECTS-PLANE SMOKE COMPLETE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
