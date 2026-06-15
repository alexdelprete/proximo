#!/usr/bin/env python3
"""Proximo SDN-PLANE mutation smoke (zone / vnet / subnet CRUD) — PENDING-ONLY.

Live-proves the SDN plane against a real Proxmox VE node by driving create -> read ->
update -> delete of a `simple` zone, a vnet in it, and a subnet in the vnet — all as
PENDING config changes. **pve_sdn_apply is NEVER called**, so there is no live-network
effect; this confirms the advisor's key property: pending SDN objects can be created and
deleted cleanly without forcing an apply against the production network.

Environment (set by the wrapper):
  PROXIMO_API_BASE_URL  PROXIMO_NODE  PROXIMO_TOKEN_PATH  PROXIMO_VERIFY_TLS
  SMOKE_SDN_ZONE (<=8 alnum, default psmkz1)  SMOKE_SDN_VNET (<=8, default psmkv1)
"""
from __future__ import annotations

import os

import proximo.server as server

ZONE: str = os.environ.get("SMOKE_SDN_ZONE", "psmkz1")
VNET: str = os.environ.get("SMOKE_SDN_VNET", "psmkv1")
CIDR: str = os.environ.get("SMOKE_SDN_CIDR", "10.99.99.0/24")


def hr(title: str) -> None:
    print(f"\n=== {title} ===")


def zone_exists(z: str) -> bool:
    try:
        return any(x.get("zone") == z for x in server.pve_sdn_zones_list())
    except Exception as e:  # noqa: BLE001
        print(f"  (zones read failed: {type(e).__name__}: {e})")
        return True


def vnet_exists(v: str) -> bool:
    try:
        return any(x.get("vnet") == v for x in server.pve_sdn_vnets_list())
    except Exception as e:  # noqa: BLE001
        print(f"  (vnets read failed: {type(e).__name__}: {e})")
        return True


def subnet_id(vnet: str, cidr: str):
    try:
        for s in server.pve_sdn_subnet_list(vnet):
            ident = s.get("subnet") or s.get("id") or ""
            if cidr in str(ident) or cidr == s.get("cidr") or cidr in str(s.get("network", "")):
                return ident
    except Exception as e:  # noqa: BLE001
        print(f"  (subnets read failed: {type(e).__name__}: {e})")
    return None


def main() -> int:
    cfg, _, _, _ = server._svc()
    print(f"node={cfg.node}  url={cfg.api_base_url}")
    print(f"throwaway: zone={ZONE!r}  vnet={VNET!r}  subnet={CIDR!r}  (PENDING ONLY — no apply)")

    zc = vc = False
    sid = None
    try:
        hr("zone — create (pending) / read / show pending state")
        server.pve_sdn_zone_create(ZONE, "simple", confirm=True)
        zc = True
        z = next((x for x in server.pve_sdn_zones_list() if x.get("zone") == ZONE), {})
        print(f"  zone created; present? {bool(z)}  state={z.get('state')}  pending={z.get('pending')}")

        hr("vnet — create (pending) / read")
        server.pve_sdn_vnet_create(VNET, ZONE, confirm=True)
        vc = True
        print(f"  vnet created; present? {vnet_exists(VNET)}")

        hr("subnet — create (pending) / read / update / id")
        server.pve_sdn_subnet_create(VNET, CIDR, confirm=True)
        subs = server.pve_sdn_subnet_list(VNET)
        print(f"  subnets now: {[s.get('subnet') or s.get('id') for s in subs]}")
        sid = subnet_id(VNET, CIDR)
        print(f"  resolved subnet id: {sid!r}")
        if sid:
            server.pve_sdn_subnet_update(VNET, sid, options={"gateway": "10.99.99.1"}, confirm=True)
            print("  subnet update (gateway): ok")

        hr("delete in reverse (pending): subnet -> vnet -> zone")
        if sid:
            server.pve_sdn_subnet_delete(VNET, sid, confirm=True)
            remaining = [s.get("subnet") or s.get("id") for s in server.pve_sdn_subnet_list(VNET)]
            print(f"  subnet deleted; remaining: {remaining}")
        server.pve_sdn_vnet_delete(VNET, confirm=True)
        vc = vnet_exists(VNET)
        print(f"  vnet deleted; gone? {not vc}")
        server.pve_sdn_zone_delete(ZONE, confirm=True)
        zc = zone_exists(ZONE)
        print(f"  zone deleted; gone? {not zc}")

    finally:
        hr("cleanup (guaranteed; reverse; NO apply)")
        sid2 = subnet_id(VNET, CIDR) if vnet_exists(VNET) else None
        if sid2:
            try:
                server.pve_sdn_subnet_delete(VNET, sid2, confirm=True)
                print(f"  removed leftover subnet {sid2}")
            except Exception as e:  # noqa: BLE001
                print(f"  !!! subnet cleanup failed: {e}")
        if vnet_exists(VNET):
            try:
                server.pve_sdn_vnet_delete(VNET, confirm=True)
                print(f"  removed leftover vnet {VNET}")
            except Exception as e:  # noqa: BLE001
                print(f"  !!! vnet cleanup failed: {e}")
        if zone_exists(ZONE):
            try:
                server.pve_sdn_zone_delete(ZONE, confirm=True)
                print(f"  removed leftover zone {ZONE}")
            except Exception as e:  # noqa: BLE001
                print(f"  !!! zone cleanup failed: {e}")
        residue = []
        if zone_exists(ZONE):
            residue.append(f"zone {ZONE}")
        if vnet_exists(VNET):
            residue.append(f"vnet {VNET}")
        print("  residue:", residue or "none — clean")
        print("  NOTE: pve_sdn_apply was NEVER called — all changes were pending-only.")

    v = server.audit_verify()
    print("\nledger verify:", {"ok": v.get("ok"), "entries": v.get("entries")})
    print("SDN-PLANE SMOKE COMPLETE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
