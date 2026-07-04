"""PVE network & SDN: interfaces/bridges, SDN zones/vnets/subnets, and apply tools.

Split out of proximo.server (2026-07-02) — see proximo/server.py's module
docstring for the funnel these wrappers depend on.
"""
from __future__ import annotations

import proximo.server as _proximo_server
from proximo.network import (
    network_apply,
    network_iface_create,
    network_iface_update,
    network_list,
    plan_iface_create,
    plan_iface_update,
    plan_network_apply,
    plan_sdn_apply,
    plan_sdn_subnet_create,
    plan_sdn_subnet_delete,
    plan_sdn_subnet_update,
    plan_sdn_vnet_create,
    plan_sdn_vnet_delete,
    plan_sdn_vnet_update,
    plan_sdn_zone_create,
    plan_sdn_zone_delete,
    plan_sdn_zone_update,
    sdn_apply,
    sdn_subnet_create,
    sdn_subnet_delete,
    sdn_subnet_list,
    sdn_subnet_update,
    sdn_vnet_create,
    sdn_vnet_delete,
    sdn_vnet_update,
    sdn_vnets_list,
    sdn_zone_create,
    sdn_zone_delete,
    sdn_zone_update,
    sdn_zones_list,
)
from proximo.server import (
    _audited,
    _plan,
    tool,
)

# --- Network & SDN (REST API, read) ---

@tool()
def pve_network_list(node: str | None = None, iface_type: str | None = None) -> list[dict]:
    """List network interfaces on a node (bridges, bonds, VLANs, etc.) (read)."""
    cfg, api, _, _ = _proximo_server._svc()
    tgt = f"nodes/{node or cfg.node}/network"
    return _audited("pve_network_list", tgt, lambda: network_list(api, node, iface_type))


@tool()
def pve_sdn_zones_list() -> list[dict]:
    """List SDN zones (cluster-scoped) (read)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_sdn_zones_list", "cluster/sdn/zones", lambda: sdn_zones_list(api))


@tool()
def pve_sdn_vnets_list() -> list[dict]:
    """List SDN virtual networks (cluster-scoped) (read)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_sdn_vnets_list", "cluster/sdn/vnets", lambda: sdn_vnets_list(api))


# --- Network & SDN (REST API, MUTATION — confirm-gated) ---

@tool()
def pve_sdn_subnet_list(vnet: str) -> list[dict]:
    """List subnets in an SDN vnet (read)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_sdn_subnet_list", f"sdn/vnets/{vnet}/subnets",
                    lambda: sdn_subnet_list(api, vnet))


@tool()
def pve_sdn_zone_create(
    zone: str, zone_type: str, options: dict | None = None,
    lock_token: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: create an SDN zone (PENDING — inert until pve_sdn_apply, NOT applied here).
    `zone_type` is simple/vlan/qinq/vxlan/evpn/faucet; `options` carries type-specific params.
    Dry-run by default. RISK_LOW (staging, no live network effect).
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"sdn/zones/{zone}"
    plan = _plan("pve_sdn_zone_create", tgt, lambda: plan_sdn_zone_create(zone, zone_type, options))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_zone_create", tgt,
                    lambda: sdn_zone_create(api, zone, zone_type, options, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_sdn_zone_update(
    zone: str, options: dict | None = None, delete: list[str] | None = None,
    digest: str | None = None, lock_token: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: update an SDN zone (PENDING). `options` sets fields; `delete` unsets keys.
    Dry-run by default. RISK_LOW (staging; inert until pve_sdn_apply).
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"sdn/zones/{zone}"
    plan = _plan("pve_sdn_zone_update", tgt, lambda: plan_sdn_zone_update(zone, options, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_zone_update", tgt,
                    lambda: sdn_zone_update(api, zone, options, delete, digest, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_sdn_zone_delete(zone: str, lock_token: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: delete an SDN zone (PENDING). Dry-run by default — the PLAN shows the current zone.
    PVE refuses if a vnet still references it. RISK_MEDIUM (staging a removal an apply would enact).
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"sdn/zones/{zone}"
    plan = _plan("pve_sdn_zone_delete", tgt, lambda: plan_sdn_zone_delete(api, zone))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_zone_delete", tgt,
                    lambda: sdn_zone_delete(api, zone, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_sdn_vnet_create(
    vnet: str, zone: str, options: dict | None = None,
    lock_token: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: create an SDN vnet in a zone (PENDING). `options` carries tag/alias/vlanaware/etc.
    Dry-run by default. RISK_LOW (staging; inert until pve_sdn_apply).
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"sdn/vnets/{vnet}"
    plan = _plan("pve_sdn_vnet_create", tgt, lambda: plan_sdn_vnet_create(vnet, zone, options))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_vnet_create", tgt,
                    lambda: sdn_vnet_create(api, vnet, zone, options, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_sdn_vnet_update(
    vnet: str, options: dict | None = None, delete: list[str] | None = None,
    digest: str | None = None, lock_token: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: update an SDN vnet (PENDING). Dry-run by default. RISK_LOW (staging)."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"sdn/vnets/{vnet}"
    plan = _plan("pve_sdn_vnet_update", tgt, lambda: plan_sdn_vnet_update(vnet, options, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_vnet_update", tgt,
                    lambda: sdn_vnet_update(api, vnet, options, delete, digest, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_sdn_vnet_delete(vnet: str, lock_token: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: delete an SDN vnet (PENDING). Dry-run by default — the PLAN shows the current vnet.
    PVE refuses if a subnet still references it. RISK_MEDIUM.
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"sdn/vnets/{vnet}"
    plan = _plan("pve_sdn_vnet_delete", tgt, lambda: plan_sdn_vnet_delete(api, vnet))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_vnet_delete", tgt,
                    lambda: sdn_vnet_delete(api, vnet, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_sdn_subnet_create(
    vnet: str, subnet: str, options: dict | None = None,
    lock_token: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: create an SDN subnet (PENDING). `subnet` is a CIDR (e.g. 10.0.0.0/24); `options`
    carries gateway/snat/dhcp params. Dry-run by default. RISK_LOW (staging; inert until apply).
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"sdn/vnets/{vnet}/subnets/{subnet}"
    plan = _plan("pve_sdn_subnet_create", tgt, lambda: plan_sdn_subnet_create(vnet, subnet, options))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_subnet_create", tgt,
                    lambda: sdn_subnet_create(api, vnet, subnet, options, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_sdn_subnet_update(
    vnet: str, subnet: str, options: dict | None = None, delete: list[str] | None = None,
    digest: str | None = None, lock_token: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: update an SDN subnet (PENDING). `subnet` is the id from pve_sdn_subnet_list.
    Dry-run by default. RISK_LOW (staging).
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"sdn/vnets/{vnet}/subnets/{subnet}"
    plan = _plan("pve_sdn_subnet_update", tgt, lambda: plan_sdn_subnet_update(vnet, subnet, options, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_subnet_update", tgt,
                    lambda: sdn_subnet_update(api, vnet, subnet, options, delete, digest, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_sdn_subnet_delete(
    vnet: str, subnet: str, lock_token: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: delete an SDN subnet (PENDING). `subnet` is the id from pve_sdn_subnet_list.
    Dry-run by default. RISK_MEDIUM (staging a removal an apply would enact).
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"sdn/vnets/{vnet}/subnets/{subnet}"
    plan = _plan("pve_sdn_subnet_delete", tgt, lambda: plan_sdn_subnet_delete(vnet, subnet))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_subnet_delete", tgt,
                    lambda: sdn_subnet_delete(api, vnet, subnet, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_network_iface_create(
    iface: str, iface_type: str, node: str | None = None,
    options: dict | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: create a new network interface config (staged — not live until pve_network_apply).
    Dry-run by default; confirm=True to execute. Synchronous.
    `options` carries type-dependent fields (address, netmask, gateway, bridge_ports, …).
    """
    cfg, api, _, _ = _proximo_server._svc()
    tgt = f"nodes/{node or cfg.node}/network/{iface}"
    plan = _plan("pve_network_iface_create", tgt,
                 lambda: plan_iface_create(api, iface, iface_type, node, options or {}))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_network_iface_create", tgt,
                    lambda: network_iface_create(api, iface, iface_type, node, **(options or {})),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_network_iface_update(
    iface: str, node: str | None = None,
    options: dict | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: update an existing network interface config (staged — not live until pve_network_apply).
    Dry-run by default; confirm=True to execute. Synchronous.
    `options` carries fields to update (address, netmask, bridge_ports, …).
    """
    cfg, api, _, _ = _proximo_server._svc()
    tgt = f"nodes/{node or cfg.node}/network/{iface}"
    plan = _plan("pve_network_iface_update", tgt,
                 lambda: plan_iface_update(api, iface, node, options or {}))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_network_iface_update", tgt,
                    lambda: network_iface_update(api, iface, node, **(options or {})),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_network_apply(node: str | None = None, confirm: bool = False) -> dict:
    """MUTATION (HIGH RISK): apply staged network config changes to the live network stack.
    Dry-run by default — the PLAN surfaces pending interfaces. confirm=True to execute.
    A misconfigured interface can lose SSH/API access; recovery requires console/physical access.
    May return a UPID (async) or None (sync) — outcome='submitted' in either case.
    """
    cfg, api, _, _ = _proximo_server._svc()
    tgt = f"nodes/{node or cfg.node}/network"
    plan = _plan("pve_network_apply", tgt, lambda: plan_network_apply(api, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_network_apply", tgt,
                    lambda: network_apply(api, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@tool()
def pve_sdn_apply(confirm: bool = False) -> dict:
    """MUTATION (HIGH RISK): apply pending SDN config changes (cluster-scoped).
    Dry-run by default — the PLAN surfaces pending zones/vnets. confirm=True to execute.
    A misconfigured SDN can disrupt virtual networking for ALL guests cluster-wide.
    May return a UPID (async) or None (sync) — outcome='submitted' in either case.
    """
    _, api, _, _ = _proximo_server._svc()
    plan = _plan("pve_sdn_apply", "cluster/sdn", lambda: plan_sdn_apply(api))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_apply", "cluster/sdn",
                    lambda: sdn_apply(api),
                    mutation=True, outcome="submitted", detail={"confirmed": True})
