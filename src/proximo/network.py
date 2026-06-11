"""Network & SDN pillar — bridge/bond/VLAN config + SDN zones/vnets listing and apply.

Every mutating function is PLAN-gated at the server layer (no plan, no mutation).
Plan functions are honest about risk: both network_apply and sdn_apply carry RISK_HIGH
because a mis-apply can lock out network access, requiring console/physical recovery.
iface_create/update write to the staged interfaces.new (not live), rated RISK_MEDIUM.

Endpoint-shape notes (flagged for live-smoke confirmation):
- network_apply: PUT /nodes/{node}/network — may return a UPID (async) or None (sync).
  Treat as raw; do not validate as UPID (mirrors backup_delete).
- sdn_apply: PUT /cluster/sdn — same uncertainty; return raw.
- Pending-diff representation: PVE may mark pending changes with per-iface "pending: 1"
  flags, a "changes" field, or a separate diff blob; exact shape uncertain until live smoke.
  Plan functions surface whatever the read returns rather than claiming a known shape.
- SDN apply may or may not require a non-empty body; implemented with empty {} (mirrors _post).
"""

from __future__ import annotations

import re

from .backends import ProximoError, _check_node
from .planning import RISK_HIGH, RISK_MEDIUM, Plan

# ---------------------------------------------------------------------------
# Validators (module-local)
# ---------------------------------------------------------------------------

# Interface name: letters, digits, underscore, hyphen, dot.
# No '/', '..', spaces, or control characters. Max 15 chars (Linux IFNAMSIZ-1).
# Uses \Z (not $) to block embedded newlines (redteam lesson from backends.py).
_IFACE_RE = re.compile(r"^[A-Za-z0-9._-]{1,15}\Z")

# Valid interface types understood by PVE (curated; PVE may accept more on a live system).
# Flagged as a shape risk: the exhaustive valid set is confirm-at-live-smoke.
_VALID_IFACE_TYPES = frozenset({
    "bridge", "bond", "eth", "alias", "vlan",
    "OVSBridge", "OVSBond", "OVSPort", "OVSIntPort",
})

# Allowed charset for network_list ?type= filter values.
# Broader than _VALID_IFACE_TYPES (PVE's GET filter accepts: any_bridge, any_local_bridge,
# any_uplink, … in addition to the create-type enum). A charset guard blocks injection
# without rejecting valid filter values that the create validator would wrongly reject.
# Shape risk: the exhaustive filter enum is PVE-version-dependent — confirm at live smoke.
_FILTER_TYPE_RE = re.compile(r"^[A-Za-z0-9_]+\Z")


def _check_iface(iface: str) -> str:
    """Validate a network interface name — URL-path-safe, no traversal, no shell-specials.

    Does NOT strip — stripping would hide trailing newlines from the ``\\Z`` guard.
    ``\\Z`` (not ``$``) blocks embedded newlines (same redteam lesson as backends.py _NODE_RE).
    """
    s = str(iface)
    if ".." in s:
        raise ProximoError(f"invalid interface name: {iface!r} (path traversal rejected)")
    if not _IFACE_RE.match(s):
        raise ProximoError(
            f"invalid interface name: {iface!r} "
            "(letters/digits/._- only, 1–15 chars, no '/', spaces, or control characters)"
        )
    return s


def _check_filter_type(iface_type: str) -> str:
    """Validate a network_list ?type= filter value (charset guard, not enum guard).

    PVE's GET filter accepts values broader than the create-type enum (e.g. any_bridge,
    any_local_bridge, any_uplink). We allow ``[A-Za-z0-9_]+`` — blocks query-string
    injection (spaces, ``&``, ``=``, ``#``, newlines) without rejecting valid filter values.

    Does NOT strip — ``\\Z`` blocks trailing newlines at the raw-string level.
    """
    t = str(iface_type)
    if not t:
        raise ProximoError("iface_type filter must not be empty")
    if not _FILTER_TYPE_RE.match(t):
        raise ProximoError(
            f"invalid iface_type filter: {iface_type!r} "
            "(letters/digits/underscores only; no spaces, &, =, or other specials)"
        )
    return t


def _check_iface_type(iface_type: str) -> str:
    """Validate interface type. Shape risk: the exhaustive enum is PVE-version-dependent."""
    t = str(iface_type)
    if not t:
        raise ProximoError("interface type must not be empty")
    if t not in _VALID_IFACE_TYPES:
        raise ProximoError(
            f"unknown interface type: {iface_type!r} "
            f"(known: {sorted(_VALID_IFACE_TYPES)}; PVE may accept additional types — "
            "confirm at live smoke if rejected)"
        )
    return t


# ---------------------------------------------------------------------------
# READ operations (audited, no confirm)
# ---------------------------------------------------------------------------

def network_list(api, node: str | None = None, iface_type: str | None = None) -> list[dict]:
    """List network interfaces on a node (bridges, bonds, VLANs, etc.).

    GET /nodes/{node}/network
    Optional: ?type=bridge|bond|vlan|eth|alias|…  (filters by interface type)

    Returns a list of interface dicts from PVE (iface, type, method, address, …).

    Shape risk: the exact fields returned per interface type are PVE-version-dependent;
    the 'type' filter enum is also version-dependent — confirm at live smoke.
    """
    _check_node(node)
    n = node or api.config.node
    path = f"/nodes/{n}/network"
    if iface_type is not None:
        iface_type = _check_filter_type(iface_type)
        path = f"{path}?type={iface_type}"
    return api._get(path) or []


def sdn_zones_list(api) -> list[dict]:
    """List SDN zones (cluster-scoped — no node param).

    GET /cluster/sdn/zones

    Returns a list of zone dicts (zone, type, state, pending, …).

    Shape risk: SDN may not be configured/enabled on the PVE cluster; the endpoint
    may return a 501 or empty list. The 'pending' and 'state' fields exist only if
    SDN is in use; confirm at live smoke.
    """
    return api._get("/cluster/sdn/zones") or []


def sdn_vnets_list(api) -> list[dict]:
    """List SDN virtual networks (cluster-scoped — no node param).

    GET /cluster/sdn/vnets

    Returns a list of vnet dicts (vnet, zone, tag, alias, …).

    Shape risk: requires SDN to be configured; endpoint and field names may vary by
    PVE version. Confirm at live smoke.
    """
    return api._get("/cluster/sdn/vnets") or []


# ---------------------------------------------------------------------------
# MUTATION operations — each validates params, no self-gating (server layer gates)
# ---------------------------------------------------------------------------

def network_iface_create(
    api,
    iface: str,
    iface_type: str,
    node: str | None = None,
    **opts,
) -> dict | None:
    """Create a new network interface configuration (written to interfaces.new — staged, not live).

    POST /nodes/{node}/network
    Body: {iface, type, …extra opts}

    Changes take effect only after network_apply. The create is reversible before apply
    by deleting the staged interface.

    Returns the PVE response (often None for synchronous confirms).

    Shape risk: POST body params beyond iface/type are PVE-interface-type-dependent
    (address, netmask, gateway, bridge_ports, slaves, vlan-raw-device, vlan-id, …).
    Extra opts are passed through; PVE validates them on its side.
    MUTATION — confirm-gated + audited at the server layer.
    """
    iface = _check_iface(iface)
    iface_type = _check_iface_type(iface_type)
    _check_node(node)
    if "type" in opts or "iface" in opts:
        raise ProximoError(
            "opts must not contain reserved keys 'type' or 'iface' — "
            "pass them as explicit positional/keyword arguments"
        )
    n = node or api.config.node
    data = {"iface": iface, "type": iface_type, **opts}
    return api._post(f"/nodes/{n}/network", data)


def network_iface_update(
    api,
    iface: str,
    node: str | None = None,
    **opts,
) -> dict | None:
    """Update an existing network interface configuration (staged, not live until apply).

    PUT /nodes/{node}/network/{iface}
    Body: {…opts}

    Changes take effect only after network_apply.

    Returns the PVE response (often None).

    Shape risk: same as iface_create — body params are type-dependent; PVE validates.
    MUTATION — confirm-gated + audited at the server layer.
    """
    iface = _check_iface(iface)
    _check_node(node)
    n = node or api.config.node
    return api._put(f"/nodes/{n}/network/{iface}", opts or {})


def network_apply(api, node: str | None = None) -> dict | None:
    """Apply pending network configuration changes (makes staged interfaces.new live).

    PUT /nodes/{node}/network
    Body: {} (no content needed — applies whatever is staged)

    *** CONNECTIVITY-LOCKOUT RISK ***
    Applying a misconfigured network interface can lose SSH/API connectivity to the node.
    Recovery requires console or physical access. RISK_HIGH; no automatic undo.

    Returns a UPID string (async task) or None (sync). Do NOT validate as UPID — return raw.

    Shape risk: whether apply is async (UPID) or sync (None), and whether it requires
    a non-empty body, must be confirmed at live smoke.
    MUTATION — confirm-gated + audited at the server layer.
    """
    _check_node(node)
    n = node or api.config.node
    return api._put(f"/nodes/{n}/network")


def sdn_apply(api) -> dict | None:
    """Apply pending SDN configuration changes (cluster-scoped — no node param).

    PUT /cluster/sdn
    Body: {} (no content — applies staged SDN config)

    *** CONNECTIVITY-LOCKOUT RISK ***
    Applying a misconfigured SDN can disrupt virtual networking for guests across the cluster.
    RISK_HIGH; no automatic undo.

    Returns a UPID string or None. Return raw — do not validate as UPID.

    Shape risk: whether body is required, the return type (UPID vs None vs empty object),
    and whether this is async or sync must be confirmed at live smoke.
    MUTATION — confirm-gated + audited at the server layer.
    """
    return api._put("/cluster/sdn")


# ---------------------------------------------------------------------------
# PLAN functions — each returns a Plan for inspection (PLAN pillar)
# ---------------------------------------------------------------------------

def plan_network_list(node: str | None = None) -> Plan:
    """Preview a network_list read (pure — no API call).

    Reads are audited but never confirm-gated. This plan is informational.
    """
    _check_node(node)
    target = f"nodes/{node or 'default'}/network"
    return Plan(
        action="pve_network_list",
        target=target,
        change=f"list network interfaces on {node or 'default node'}",
        current={},
        blast_radius=["read-only: lists current network interface configuration"],
        risk="low",
        risk_reasons=["read-only listing — no state change"],
    )


def plan_iface_create(
    api,
    iface: str,
    iface_type: str,
    node: str | None = None,
) -> Plan:
    """Preview creating a network interface.

    Reads the current network list (a safe read) to detect iface collision.
    Changes are staged (interfaces.new) — not live until network_apply.
    RISK_MEDIUM: staged change, reversible before apply.

    If the collision check fails, that uncertainty is disclosed — absence of a HIGH
    flag is not a safety signal.
    """
    iface = _check_iface(iface)
    iface_type = _check_iface_type(iface_type)
    _check_node(node)

    taken = False
    check_error: str | None = None
    try:
        ifaces = network_list(api, node) or []
        taken = any(i.get("iface") == iface for i in ifaces)
    except Exception as e:
        check_error = type(e).__name__

    n = node or api.config.node

    if check_error is not None:
        blast = [
            f"collision check failed ({check_error}) — could not confirm '{iface}' is free; "
            "create may fail if it already exists"
        ]
        reasons = [
            f"staged create of {iface_type} '{iface}' on {n}",
            "collision check unavailable — absence of HIGH flag is not a safety signal",
        ]
    elif taken:
        blast = [f"create will FAIL — interface '{iface}' already exists on {n}"]
        reasons = [f"'{iface}' is already configured on {n}; create will be rejected by PVE"]
    else:
        blast = [
            f"stages new {iface_type} interface '{iface}' on {n} (written to interfaces.new)",
            "change is NOT live until network_apply is run",
        ]
        reasons = [
            f"staged configuration change: creates {iface_type} '{iface}' on {n}",
            "reversible before apply: delete the staged iface before applying to undo",
        ]

    return Plan(
        action="pve_network_iface_create",
        target=f"nodes/{n}/network/{iface}",
        change=f"create {iface_type} interface '{iface}' on {n} (staged)",
        current={},
        blast_radius=blast,
        risk=RISK_MEDIUM,
        risk_reasons=reasons,
        note=(
            "Change is staged (interfaces.new) — it does NOT affect live connectivity until "
            "network_apply is called. Apply carries RISK_HIGH (connectivity-lockout). "
            "Review carefully before applying."
        ),
    )


def plan_iface_update(
    api,
    iface: str,
    node: str | None = None,
) -> Plan:
    """Preview updating a network interface.

    Reads the current interface config (a safe read) to show what is being changed.
    Staged change — not live until network_apply. RISK_MEDIUM.
    """
    iface = _check_iface(iface)
    _check_node(node)

    current: dict = {}
    found = True
    check_failed = False
    try:
        ifaces = network_list(api, node) or []
        match = next((i for i in ifaces if i.get("iface") == iface), None)
        if match is None:
            found = False
        else:
            current = {k: match[k] for k in ("iface", "type", "method", "address", "active") if k in match}
    except Exception as e:
        check_failed = True
        _ = e  # acknowledged

    n = node or api.config.node

    if check_failed:
        blast = [
            f"could NOT read current config for '{iface}' on {n}; update may fail if it does not exist"
        ]
        reasons = [
            f"staged update of '{iface}' on {n}",
            "current state check failed — cannot show what would change",
        ]
    elif not found:
        blast = [f"update will FAIL — interface '{iface}' not found on {n}; nothing would change"]
        reasons = [f"'{iface}' is not configured on {n}; update will be rejected by PVE"]
    else:
        blast = [
            f"updates interface '{iface}' on {n} (staged — written to interfaces.new)",
            "change is NOT live until network_apply is run",
        ]
        reasons = [
            f"staged modification of existing {iface} interface on {n}",
            "reversible before apply: revert the staged iface before applying",
        ]

    return Plan(
        action="pve_network_iface_update",
        target=f"nodes/{n}/network/{iface}",
        change=f"update interface '{iface}' on {n} (staged)",
        current=current,
        blast_radius=blast,
        risk=RISK_MEDIUM,
        risk_reasons=reasons,
        note=(
            "Staged change (interfaces.new) — does NOT affect live connectivity until "
            "network_apply is called. Apply carries RISK_HIGH (connectivity-lockout)."
        ),
    )


def plan_network_apply(api, node: str | None = None) -> Plan:
    """Preview applying pending network configuration changes.

    *** TWO-STEP APPLY: this plan reads the current staged/pending state first and
    surfaces it in the blast_radius so the operator sees exactly what would go live.
    RISK_HIGH is mandatory and unconditional — network apply can lose connectivity. ***

    Reads the network interface list (a safe read) to surface any pending/staged changes
    in the blast radius. If the read fails, HIGH is maintained — uncertainty is not a
    safety signal (mirrors plan_delete logic).

    Shape risk: how PVE marks 'pending' changes in the network list (per-iface 'pending'
    flag, 'changes' field, or separate blob) is uncertain until live smoke. This plan
    surfaces whatever markers the read returns.
    """
    _check_node(node)
    n = node or api.config.node

    pending_info: list[str] = []
    read_failed = False
    try:
        ifaces = network_list(api, node) or []
        # Surface any ifaces with a 'pending' marker. Shape risk: the exact key/value
        # PVE uses to flag pending changes is uncertain — 'pending', 'changes', or a
        # boolean field. We check both 'pending' (truthy) and 'changes' (non-empty).
        for i in ifaces:
            name = i.get("iface", "?")
            if i.get("pending") or i.get("changes"):
                pending_info.append(
                    f"  {name}: pending={i.get('pending')!r} changes={i.get('changes')!r}"
                )
    except Exception:
        read_failed = True

    if read_failed:
        pending_summary = (
            "could NOT read pending network state — applying UNKNOWN changes; "
            "review manually before confirming"
        )
        blast = [
            f"APPLIES all pending network changes on {n} to live network stack",
            pending_summary,
            "CONNECTIVITY-LOCKOUT RISK: a misconfigured interface can lose SSH/API access — "
            "console or physical access required to recover",
        ]
        reasons = [
            "network apply is irreversible in the connectivity sense — no automatic rollback",
            "pending-state read failed; applying unknown changes; RISK_HIGH maintained",
            "connectivity lockout requires console/physical access to recover",
        ]
    elif pending_info:
        blast = [
            f"APPLIES all pending network changes on {n} to live network stack",
            f"Detected {len(pending_info)} pending interface(s):",
            *pending_info,
            "CONNECTIVITY-LOCKOUT RISK: a misconfigured interface can lose SSH/API access — "
            "console or physical access required to recover",
        ]
        reasons = [
            "network apply makes staged config live — if an interface is misconfigured, "
            "SSH/API connectivity is lost immediately",
            "no automatic undo: recovery requires console or physical access",
        ]
    else:
        blast = [
            f"APPLIES pending network configuration on {n} (no pending changes detected, "
            "but apply proceeds regardless)",
            "CONNECTIVITY-LOCKOUT RISK: applies staged config; if misconfigured, SSH/API "
            "access may be lost — console or physical access required to recover",
        ]
        reasons = [
            "network apply makes staged config live — even 'no changes detected' does not "
            "guarantee safety (read may have missed pending entries)",
            "RISK_HIGH maintained: absent confirmation of no-op, apply always carries lockout risk",
            "no automatic undo: recovery requires console or physical access",
        ]

    return Plan(
        action="pve_network_apply",
        target=f"nodes/{n}/network",
        change=f"apply pending network configuration on {n}",
        current={"pending_ifaces": pending_info, "read_failed": read_failed},
        blast_radius=blast,
        risk=RISK_HIGH,
        risk_reasons=reasons,
        note=(
            "RISK_HIGH is unconditional for network apply — connectivity lockout has no "
            "automatic recovery path. Shape risk: how PVE marks pending changes is "
            "uncertain until live smoke (fields checked: 'pending', 'changes')."
        ),
    )


def plan_sdn_apply(api) -> Plan:
    """Preview applying pending SDN configuration changes (cluster-scoped).

    *** TWO-STEP APPLY: reads SDN zones/vnets to surface pending state before apply.
    RISK_HIGH is mandatory and unconditional — SDN apply can disrupt guest networking
    cluster-wide. No automatic undo. ***

    Shape risk: SDN pending state representation (state/pending fields in zones/vnets)
    is uncertain until live smoke. This plan surfaces whatever markers the reads return.
    """
    pending_zones: list[str] = []
    pending_vnets: list[str] = []
    read_failed = False
    try:
        zones = sdn_zones_list(api) or []
        for z in zones:
            name = z.get("zone", "?")
            if z.get("pending") or z.get("state") == "pending":
                pending_zones.append(f"  zone {name}: state={z.get('state')!r} pending={z.get('pending')!r}")
        vnets = sdn_vnets_list(api) or []
        for v in vnets:
            name = v.get("vnet", "?")
            if v.get("pending") or v.get("state") == "pending":
                pending_vnets.append(f"  vnet {name}: state={v.get('state')!r} pending={v.get('pending')!r}")
    except Exception:
        read_failed = True

    all_pending = pending_zones + pending_vnets

    if read_failed:
        blast = [
            "APPLIES all pending SDN configuration changes cluster-wide",
            "could NOT read pending SDN state — applying UNKNOWN changes; "
            "review manually before confirming",
            "CONNECTIVITY-LOCKOUT RISK: a misconfigured SDN can disrupt virtual networking "
            "for ALL guests on the cluster",
        ]
        reasons = [
            "SDN apply is cluster-scoped — affects all guest virtual networking",
            "pending-state read failed; applying unknown SDN changes; RISK_HIGH maintained",
            "no automatic undo: SDN config rollback requires manual revert and re-apply",
        ]
    elif all_pending:
        blast = [
            "APPLIES all pending SDN configuration changes cluster-wide",
            f"Detected {len(all_pending)} pending SDN entry/entries:",
            *all_pending,
            "CONNECTIVITY-LOCKOUT RISK: a misconfigured SDN can disrupt virtual networking "
            "for ALL guests on the cluster",
        ]
        reasons = [
            "SDN apply is cluster-scoped; misconfiguration can disrupt guest virtual networking",
            "no automatic undo: recovery requires manual SDN revert + re-apply",
        ]
    else:
        blast = [
            "APPLIES pending SDN configuration cluster-wide (no pending changes detected, "
            "but apply proceeds regardless)",
            "CONNECTIVITY-LOCKOUT RISK: SDN apply can disrupt virtual networking for all guests; "
            "even 'no changes detected' does not guarantee a no-op",
        ]
        reasons = [
            "SDN apply is cluster-scoped — affects all guest virtual networking",
            "RISK_HIGH maintained: absence of detected pending entries is not a safety signal "
            "(shape of pending state is uncertain until live smoke)",
            "no automatic undo: recovery requires manual SDN revert + re-apply",
        ]

    return Plan(
        action="pve_sdn_apply",
        target="cluster/sdn",
        change="apply pending SDN configuration (cluster-wide)",
        current={"pending_zones": pending_zones, "pending_vnets": pending_vnets, "read_failed": read_failed},
        blast_radius=blast,
        risk=RISK_HIGH,
        risk_reasons=reasons,
        note=(
            "RISK_HIGH is unconditional for SDN apply — cluster-wide virtual networking disruption "
            "has no automatic recovery path. Shape risk: SDN pending/state field names are "
            "uncertain until live smoke (fields checked: 'pending', 'state')."
        ),
    )
