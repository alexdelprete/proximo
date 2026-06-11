#!/usr/bin/env python3
"""Proximo NETWORK/INFRA-PLANE mutation smoke.

Proves what Proximo's Tier-1 token can drive on a single Proxmox VE node:
  - FIREWALL rules: add -> list (by comment) -> update -> remove  [fw DISABLED = inert]
  - POOLS: create -> read-back -> delete                          [self-cleaning]
  - HA: PLAN dry-run only (no quorum needed; zero write)

Explicitly NOT exercised here (require cluster + 2nd node or carry real risk):
  - sdn_apply / network_apply / network_iface_*  (host net reload on production)
  - guest_migrate live (needs a 2nd node)
  - HA-enforce (needs quorum)
  - firewall_set_enabled (lockout risk on a production network)

Self-cleaning: a `finally` block removes any firewall rule bearing the throwaway
comment and any leftover throwaway pool, each gated on a 'did I create it' flag
with a LOUD manual-cleanup fallback. No guest is ever created.

Environment (set by the wrapper script; see netplane-smoke.sh and README.md):
  PROXIMO_API_BASE_URL  PROXIMO_NODE  PROXIMO_TOKEN_PATH  PROXIMO_VERIFY_TLS
  SMOKE_FW_COMMENT      SMOKE_POOL_ID
"""
from __future__ import annotations

import os

import proximo.server as server

# Read throwaway identifiers from env; defaults are safe, self-describing names.
FW_COMMENT: str = os.environ.get("SMOKE_FW_COMMENT", "proximo-smoke-fwtest")
FW_COMMENT_UPD: str = FW_COMMENT + "-upd"
POOL_ID: str = os.environ.get("SMOKE_POOL_ID", "proximo-smoke-throwaway-pool")


def hr(title: str) -> None:
    print(f"\n=== {title} ===")


def fw_find(comment: str) -> int | None:
    """Return the pos of the first firewall rule with the given comment, or None."""
    for i, rule in enumerate(server.pve_firewall_rules_list(scope="cluster")):
        if rule.get("comment") == comment:
            return rule.get("pos", i)
    return None


def pool_exists(poolid: str) -> bool:
    """Return True when the pool exists (fail-safe: True on read error)."""
    try:
        return any(p.get("poolid") == poolid for p in server.pve_pools_list())
    except Exception as e:  # noqa: BLE001 — a failed read must NOT be treated as "absent"
        print(f"  (pool-list read failed: {type(e).__name__}: {e})")
        return True  # fail-safe: assume it might exist so cleanup still attempts removal


def main() -> int:
    cfg, api, _, _ = server._svc()
    print(f"node={cfg.node}  url={cfg.api_base_url}")
    print(f"throwaway fw_comment={FW_COMMENT!r}  pool_id={POOL_ID!r}")

    pool_created = False
    try:
        # ---- FIREWALL CRUD (inert; firewall disabled throughout) ---------------------------
        hr("firewall rules — add / list-by-comment / update / remove (cluster; fw DISABLED)")
        a = server.pve_firewall_rule_add(
            action="ACCEPT", direction="in", scope="cluster",
            proto="tcp", dport="65000", comment=FW_COMMENT,
            enable=False, confirm=True,
        )
        print("  add:", a.get("status"))

        pos = fw_find(FW_COMMENT)
        print(f"  found at pos {pos}")
        if pos is not None:
            u = server.pve_firewall_rule_update(
                pos=pos, scope="cluster", comment=FW_COMMENT_UPD, confirm=True,
            )
            print("  update:", u.get("status"))
            pos2 = fw_find(FW_COMMENT_UPD)
            print(f"  re-found by updated comment at pos {pos2}")
            if pos2 is not None:
                rem = server.pve_firewall_rule_remove(pos=pos2, scope="cluster", confirm=True)
                gone = fw_find(FW_COMMENT_UPD) is None and fw_find(FW_COMMENT) is None
                print("  remove:", rem.get("status"), "| gone?", gone)

        # ---- POOL LIFECYCLE ----------------------------------------------------------------
        hr("pool lifecycle — create / read-back / delete")
        pc = server.pve_pool_create(poolid=POOL_ID, comment="proximo throwaway", confirm=True)
        pool_created = True
        print("  create:", pc.get("status"))

        pg = server.pve_pool_get(POOL_ID)
        # Show what live PVE returns so we learn the real contract (shape may vary by version)
        raw = pg.get("data") if isinstance(pg.get("data"), dict) else pg
        members = raw.get("members") if isinstance(raw, dict) else None
        print(
            f"  read-back OK: keys={sorted(pg.keys())}"
            f"  members={len(members) if members is not None else 'n/a'}"
        )

        pd = server.pve_pool_delete(poolid=POOL_ID, confirm=True)
        pgone = not pool_exists(POOL_ID)
        pool_created = not pgone
        print("  delete:", pd.get("status"), "| gone?", pgone)

        # ---- HA PLAN (dry-run only; standalone node, no quorum) ----------------------------
        hr("HA — PLAN dry-run only (no quorum; no write)")
        # Passing no `confirm=True` means the tool returns a PLAN, zero write.
        ha_plan = server.pve_ha_resource_add("9999", kind="qemu")
        print("  ha_resource_add PLAN:", {k: ha_plan.get(k) for k in ("status", "risk")})

    finally:
        hr("cleanup (guaranteed)")
        # Firewall cleanup
        for c in (FW_COMMENT_UPD, FW_COMMENT):
            p = fw_find(c)
            if p is not None:
                server.pve_firewall_rule_remove(pos=p, scope="cluster", confirm=True)
                print(f"  removed leftover firewall rule (comment={c!r}, pos={p})")
        # Pool cleanup
        if pool_created and pool_exists(POOL_ID):
            server.pve_pool_delete(poolid=POOL_ID, confirm=True)
            print(f"  removed leftover pool ({POOL_ID!r})")
        # Final residue check
        residue: list[str] = []
        if fw_find(FW_COMMENT) is not None or fw_find(FW_COMMENT_UPD) is not None:
            residue.append(f"firewall rule (comment {FW_COMMENT!r} or {FW_COMMENT_UPD!r})")
        if pool_exists(POOL_ID):
            residue.append(f"pool {POOL_ID!r}")
        if residue:
            print("  !!! MANUAL CLEANUP NEEDED on your PVE host:")
            for item in residue:
                print(f"      {item}")
            print("  pvesh get /cluster/firewall/rules   # find pos, then:")
            print("  pvesh delete /cluster/firewall/rules/<pos>")
            print(f"  pvesh delete /pools/{POOL_ID}")
        else:
            print("  clean — no throwaway artifacts remain")

    v = server.audit_verify()
    print("\nledger verify:", {"ok": v.get("ok"), "entries": v.get("entries")})
    print("NETWORK/INFRA-PLANE SMOKE COMPLETE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
