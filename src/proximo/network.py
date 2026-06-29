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

import ipaddress
import re
from urllib.parse import urlsplit

from . import blast as blast_engine
from .backends import ProximoError, _check_node
from .planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM, Plan


def _mgmt_host_from_api(api) -> str | None:
    """Best-effort: the host Proximo talks to, parsed from cfg.api_base_url (config, not a network
    read). Often a HOSTNAME (won't match an iface address) — the lockout naming is best-effort and
    HIGH stands regardless. Returns None if no base URL / unparseable (caller keeps HIGH)."""
    base = getattr(getattr(api, "config", None), "api_base_url", None)
    if not base:
        return None
    try:
        host = urlsplit(base).hostname
    except ValueError:
        return None
    return host or None

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
    # Reject dot-segments: '.' normalizes PUT /network/. onto PUT /network (the config-APPLY
    # endpoint) and '..' onto the node — wrong-target ops the plan would mislabel. VLANs (eth0.100)
    # contain a single dot but are never a lone '.'/'..', so they stay valid.
    if s == "." or ".." in s:
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


def _current_iface_type(api, iface: str, node: str | None = None) -> str | None:
    """Return an interface's current PVE type (a read), or None if the iface is absent."""
    for entry in network_list(api, node) or []:
        if entry.get("iface") == iface:
            return entry.get("type")
    return None


def network_iface_update(
    api,
    iface: str,
    node: str | None = None,
    **opts,
) -> dict | None:
    """Update an existing network interface configuration (staged, not live until apply).

    PUT /nodes/{node}/network/{iface}
    Body: {…opts, type}  — `type` is injected from the iface's current config (see below).

    Changes take effect only after network_apply.

    Returns the PVE response (often None).

    PVE's update endpoint requires `type` even for an address-only change. We read the
    interface's CURRENT type and inject it, so plain field updates (address, netmask,
    bridge_ports, …) go through while a type *change* stays impossible by construction — a
    caller-supplied `type` is still rejected. Adds one read (network_list) before the PUT.
    (PVE schema confirms `type` is the SOLE required update param — `pvesh usage`, 2026-06-28 —
    so injecting it is sufficient; all other fields are optional.)

    Shape risk: body params beyond type are PVE-interface-type-dependent; PVE validates.
    MUTATION — confirm-gated + audited at the server layer.
    """
    iface = _check_iface(iface)
    _check_node(node)
    if "type" in opts:
        raise ProximoError(
            "opts must not contain the reserved key 'type' — an interface's type is preserved "
            "automatically from its current config; changing the type is a structural change "
            "(recreate the interface instead)"
        )
    n = node or api.config.node
    current_type = _current_iface_type(api, iface, node)
    if current_type is None:
        raise ProximoError(
            f"cannot update interface {iface!r} on {n}: not found "
            "(no current type to preserve — create it first)"
        )
    return api._put(f"/nodes/{n}/network/{iface}", {**opts, "type": current_type})


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
    opts: dict | None = None,
) -> Plan:
    """Preview updating a network interface.

    Reads the current interface config (a safe read) to show what is being changed, and discloses
    the STAGED fields (*opts*) so the confirmed plan describes the actual mutation, not just "(staged)".
    Staged change — not live until network_apply. RISK_MEDIUM.
    """
    iface = _check_iface(iface)
    _check_node(node)
    opts = opts or {}

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
    affected: list[dict] = []
    complete = True

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
        # Attachment blast: name the guests with a NIC on this bridge — they are disrupted when the
        # staged change is applied. Risk stays MEDIUM (staged/reversible); the apply step carries HIGH.
        att = blast_engine.iface_attachment_blast(api, iface)
        blast.extend(att.summary_lines)
        affected = att.affected
        complete = att.complete

    if opts:
        blast.append("staged fields: " + ", ".join(f"{k}={opts[k]}" for k in sorted(opts)))

    return Plan(
        action="pve_network_iface_update",
        target=f"nodes/{n}/network/{iface}",
        change=f"update interface '{iface}' on {n} (staged)",
        current=current,
        blast_radius=blast,
        risk=RISK_MEDIUM,
        risk_reasons=reasons,
        affected=affected,
        complete=complete,
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
    mgmt_host = _mgmt_host_from_api(api)

    ifaces: list[dict] = []
    pending_info: list[str] = []
    pending_names: list[str] = []
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
                pending_names.append(name)
    except Exception:
        read_failed = True

    # Best-effort mgmt-interface naming on top of the UNCONDITIONAL HIGH. compute_apply_lockout
    # NEVER lowers risk and NEVER says "no lockout" — non-identification => HIGH stands. On a read
    # failure we have no ifaces to match, so it correctly reports "could not identify" + complete=False.
    lockout = blast_engine.compute_apply_lockout(pending_names, mgmt_host, ifaces)
    affected = lockout.affected
    complete = not read_failed

    if read_failed:
        pending_summary = (
            "could NOT read pending network state — applying UNKNOWN changes; "
            "review manually before confirming"
        )
        blast = [
            *lockout.summary_lines,
            f"APPLIES all pending network changes on {n} to live network stack",
            pending_summary,
            "CONNECTIVITY-LOCKOUT RISK: a misconfigured interface can lose SSH/API access — "
            "console or physical access required to recover",
        ]
        reasons = [
            *lockout.risk_reasons,
            "network apply is irreversible in the connectivity sense — no automatic rollback",
            "pending-state read failed; applying unknown changes; RISK_HIGH maintained",
            "connectivity lockout requires console/physical access to recover",
        ]
    elif pending_info:
        blast = [
            *lockout.summary_lines,
            f"APPLIES all pending network changes on {n} to live network stack",
            f"Detected {len(pending_info)} pending interface(s):",
            *pending_info,
            "CONNECTIVITY-LOCKOUT RISK: a misconfigured interface can lose SSH/API access — "
            "console or physical access required to recover",
        ]
        reasons = [
            *lockout.risk_reasons,
            "network apply makes staged config live — if an interface is misconfigured, "
            "SSH/API connectivity is lost immediately",
            "no automatic undo: recovery requires console or physical access",
        ]
    else:
        blast = [
            *lockout.summary_lines,
            f"APPLIES pending network configuration on {n} (no pending changes detected, "
            "but apply proceeds regardless)",
            "CONNECTIVITY-LOCKOUT RISK: applies staged config; if misconfigured, SSH/API "
            "access may be lost — console or physical access required to recover",
        ]
        reasons = [
            *lockout.risk_reasons,
            "network apply makes staged config live — even 'no changes detected' does not "
            "guarantee safety (read may have missed pending entries)",
            "RISK_HIGH maintained: absent confirmation of no-op, apply always carries lockout risk",
            "no automatic undo: recovery requires console or physical access",
        ]

    return Plan(
        action="pve_network_apply",
        target=f"nodes/{n}/network",
        change=f"apply pending network configuration on {n}",
        current={"pending_ifaces": pending_info, "read_failed": read_failed,
                 "mgmt_host": mgmt_host},
        blast_radius=blast,
        affected=affected,
        risk=RISK_HIGH,
        risk_reasons=reasons,
        complete=complete,
        note=(
            "RISK_HIGH is unconditional for network apply — connectivity lockout has no "
            "automatic recovery path. Mgmt-interface naming is best-effort (the mgmt host may be a "
            "hostname or live on a bond/VLAN under the bridge); non-identification => HIGH stands, "
            "never 'no lockout'. Shape risk: how PVE marks pending changes is uncertain until live "
            "smoke (fields checked: 'pending', 'changes')."
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

    # Light touch (mgmt-lockout class): the management path is almost always on a plain bridge
    # (vmbr*) — NOT an SDN vnet — so SDN apply rarely cuts the admin's own access. Stated, not
    # deep-modeled; if your mgmt IP DOES live on an SDN vnet, this apply could lock you out.
    blast.append(
        "note: the management host is normally on a plain bridge (vmbr*), not an SDN vnet, so this "
        "apply rarely cuts your own SSH/API access — verify if your management IP is on an SDN vnet"
    )

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


# ===========================================================================
# SDN — zone / vnet / subnet CRUD (cluster-scoped)
# ---------------------------------------------------------------------------
# Grounded against live PVE 9.1.7 schema (2026-06-14):
#   POST   /cluster/sdn/zones                       {type, zone, ...type-conditional}
#   PUT    /cluster/sdn/zones/{zone}                 {<opts>, delete?:csv, digest?}
#   DELETE /cluster/sdn/zones/{zone}
#   POST   /cluster/sdn/vnets                        {type:vnet, vnet, zone, tag?, ...}
#   PUT/DELETE /cluster/sdn/vnets/{vnet}
#   GET/POST   /cluster/sdn/vnets/{vnet}/subnets     {type:subnet, subnet(=CIDR), gateway?, ...}
#   PUT/DELETE /cluster/sdn/vnets/{vnet}/subnets/{subnet}
#
# SDN objects are STAGED (pending) — they have NO live network effect until pve_sdn_apply
# (PUT /cluster/sdn), which is a SEPARATE, RISK_HIGH tool NOT re-added here. So zone/vnet/subnet
# create/update/delete is reversible config staging: RISK_LOW for create/update, RISK_MEDIUM for
# delete (staging a removal that an apply would enact on possibly-live networking). No config UNDO
# — revert by deleting the pending object (before apply). `lock-token` is the optional PVE-9
# global-SDN-lock param (only needed when the SDN config is locked).
#
# Zone create has a large, type-conditional param set; vnet/subnet likewise. Rather than enumerate
# every per-type field, these tools take a generic `options` dict (PVE validates per type) plus the
# structural params (type/zone/vnet/subnet) as explicit args. Reserved structural keys are rejected
# from `options` so they can't be smuggled.
# ===========================================================================

_VALID_ZONE_TYPES = frozenset({"evpn", "faucet", "qinq", "simple", "vlan", "vxlan"})
# Path-safe id (PVE additionally enforces its own length/charset, e.g. 8-char zones); we only
# guarantee no path-traversal / injection here and surface PVE's stricter error otherwise.
_SDN_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\Z")
_SUBNET_PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,63}\Z")
_SDN_RESERVED = frozenset({"type", "zone", "vnet", "subnet", "delete", "digest",
                           "lock-token", "lock_token"})


def _check_sdn_id(value: str, label: str) -> str:
    v = str(value).strip()
    if not _SDN_ID_RE.match(v):
        raise ProximoError(
            f"invalid SDN {label} id: {value!r} (alphanumeric/_/-, start with alnum; "
            "PVE enforces additional length/charset limits)"
        )
    return v


def _check_zone_type(zone_type: str) -> str:
    t = str(zone_type).strip()
    if t not in _VALID_ZONE_TYPES:
        raise ProximoError(
            f"invalid SDN zone type: {zone_type!r} (expected one of {sorted(_VALID_ZONE_TYPES)})"
        )
    return t


def _check_sdn_options(options: dict | None) -> None:
    """Reject structural/reserved keys inside the generic options bag (they have dedicated args)."""
    bad = _SDN_RESERVED & set(options or {})
    if bad:
        raise ProximoError(
            f"reserved key(s) {sorted(bad)} cannot be passed inside options — use the dedicated "
            "type/zone/vnet/subnet/delete/digest/lock_token parameters instead"
        )


def _check_subnet_cidr(cidr: str) -> str:
    """The subnet CREATE identifier is a CIDR (e.g. 10.0.0.0/24). Validate with ipaddress."""
    v = str(cidr).strip()
    try:
        ipaddress.ip_network(v, strict=False)
    except ValueError as exc:
        raise ProximoError(f"invalid subnet cidr: {cidr!r} (expected a CIDR network)") from exc
    return v


def _check_subnet_path_id(value: str) -> str:
    """The subnet identifier for update/delete flows into a URL path (it may be a CIDR or the
    PVE-derived 'zone-cidr' id). Allow CIDR/id chars but reject path-traversal."""
    v = str(value).strip()
    if ".." in v or not _SUBNET_PATH_RE.match(v):
        raise ProximoError(
            f"invalid subnet id: {value!r} (expected a CIDR or PVE subnet id; no path traversal)"
        )
    return v


def _sdn_csv(delete) -> str:
    return ",".join(delete) if isinstance(delete, list) else str(delete)


def _sdn_pending_blast(lead: str) -> list[str]:
    return [
        lead,
        "INERT until pve_sdn_apply (a separate RISK_HIGH step) — no live network effect yet",
        "no UNDO at config level: revert by deleting the pending object before apply",
    ]


# --- zones ------------------------------------------------------------------

def sdn_zone_create(api, zone: str, zone_type: str, options: dict | None = None,
                    lock_token: str | None = None) -> object:
    """Create an SDN zone (PENDING). MUTATION — confirm-gated + audited at the server layer.
    POST /cluster/sdn/zones {type, zone, ...}. Inert until pve_sdn_apply. No config UNDO."""
    zone = _check_sdn_id(zone, "zone")
    zone_type = _check_zone_type(zone_type)
    _check_sdn_options(options)
    data: dict = {"type": zone_type, "zone": zone, **(options or {})}
    if lock_token is not None:
        data["lock-token"] = lock_token
    return api._post("/cluster/sdn/zones", data)


def sdn_zone_update(api, zone: str, options: dict | None = None, delete: list | str | None = None,
                    digest: str | None = None, lock_token: str | None = None) -> object:
    """Update an SDN zone (PENDING). PUT /cluster/sdn/zones/{zone}. Requires >=1 set/unset."""
    zone = _check_sdn_id(zone, "zone")
    _check_sdn_options(options)
    if not options and not delete:
        raise ProximoError("sdn_zone_update requires at least one option to set or delete")
    data: dict = dict(options or {})
    if delete:
        data["delete"] = _sdn_csv(delete)
    if digest is not None:
        data["digest"] = digest
    if lock_token is not None:
        data["lock-token"] = lock_token
    return api._put(f"/cluster/sdn/zones/{zone}", data)


def sdn_zone_delete(api, zone: str, lock_token: str | None = None) -> object:
    """Delete an SDN zone (PENDING). DELETE /cluster/sdn/zones/{zone}. PVE refuses if a vnet
    still references the zone. Inert until pve_sdn_apply."""
    zone = _check_sdn_id(zone, "zone")
    params: dict = {}
    if lock_token is not None:
        params["lock-token"] = lock_token
    return api._delete(f"/cluster/sdn/zones/{zone}", params)


# --- vnets ------------------------------------------------------------------

def sdn_vnet_create(api, vnet: str, zone: str, options: dict | None = None,
                    lock_token: str | None = None) -> object:
    """Create an SDN vnet in a zone (PENDING). POST /cluster/sdn/vnets {type:vnet, vnet, zone, ...}."""
    vnet = _check_sdn_id(vnet, "vnet")
    zone = _check_sdn_id(zone, "zone")
    _check_sdn_options(options)
    data: dict = {"type": "vnet", "vnet": vnet, "zone": zone, **(options or {})}
    if lock_token is not None:
        data["lock-token"] = lock_token
    return api._post("/cluster/sdn/vnets", data)


def sdn_vnet_update(api, vnet: str, options: dict | None = None, delete: list | str | None = None,
                    digest: str | None = None, lock_token: str | None = None) -> object:
    """Update an SDN vnet (PENDING). PUT /cluster/sdn/vnets/{vnet}. Requires >=1 set/unset."""
    vnet = _check_sdn_id(vnet, "vnet")
    _check_sdn_options(options)
    if not options and not delete:
        raise ProximoError("sdn_vnet_update requires at least one option to set or delete")
    data: dict = dict(options or {})
    if delete:
        data["delete"] = _sdn_csv(delete)
    if digest is not None:
        data["digest"] = digest
    if lock_token is not None:
        data["lock-token"] = lock_token
    return api._put(f"/cluster/sdn/vnets/{vnet}", data)


def sdn_vnet_delete(api, vnet: str, lock_token: str | None = None) -> object:
    """Delete an SDN vnet (PENDING). DELETE /cluster/sdn/vnets/{vnet}. PVE refuses if a subnet
    still references the vnet. Inert until pve_sdn_apply."""
    vnet = _check_sdn_id(vnet, "vnet")
    params: dict = {}
    if lock_token is not None:
        params["lock-token"] = lock_token
    return api._delete(f"/cluster/sdn/vnets/{vnet}", params)


# --- subnets ----------------------------------------------------------------

def sdn_subnet_list(api, vnet: str) -> list[dict]:
    """List subnets in a vnet (read). GET /cluster/sdn/vnets/{vnet}/subnets."""
    vnet = _check_sdn_id(vnet, "vnet")
    return api._get(f"/cluster/sdn/vnets/{vnet}/subnets") or []


def sdn_subnet_create(api, vnet: str, subnet: str, options: dict | None = None,
                      lock_token: str | None = None) -> object:
    """Create an SDN subnet (PENDING). POST /cluster/sdn/vnets/{vnet}/subnets {type:subnet, subnet=CIDR, ...}.
    `subnet` is the CIDR (e.g. 10.0.0.0/24). Inert until pve_sdn_apply."""
    vnet = _check_sdn_id(vnet, "vnet")
    subnet = _check_subnet_cidr(subnet)
    _check_sdn_options(options)
    data: dict = {"type": "subnet", "subnet": subnet, **(options or {})}
    if lock_token is not None:
        data["lock-token"] = lock_token
    return api._post(f"/cluster/sdn/vnets/{vnet}/subnets", data)


def sdn_subnet_update(api, vnet: str, subnet: str, options: dict | None = None,
                      delete: list | str | None = None, digest: str | None = None,
                      lock_token: str | None = None) -> object:
    """Update an SDN subnet (PENDING). PUT /cluster/sdn/vnets/{vnet}/subnets/{subnet}.
    `subnet` is the identifier from sdn_subnet_list. Requires >=1 set/unset."""
    vnet = _check_sdn_id(vnet, "vnet")
    subnet = _check_subnet_path_id(subnet)
    _check_sdn_options(options)
    if not options and not delete:
        raise ProximoError("sdn_subnet_update requires at least one option to set or delete")
    data: dict = dict(options or {})
    if delete:
        data["delete"] = _sdn_csv(delete)
    if digest is not None:
        data["digest"] = digest
    if lock_token is not None:
        data["lock-token"] = lock_token
    return api._put(f"/cluster/sdn/vnets/{vnet}/subnets/{subnet}", data)


def sdn_subnet_delete(api, vnet: str, subnet: str, lock_token: str | None = None) -> object:
    """Delete an SDN subnet (PENDING). DELETE /cluster/sdn/vnets/{vnet}/subnets/{subnet}.
    `subnet` is the identifier from sdn_subnet_list. Inert until pve_sdn_apply."""
    vnet = _check_sdn_id(vnet, "vnet")
    subnet = _check_subnet_path_id(subnet)
    params: dict = {}
    if lock_token is not None:
        params["lock-token"] = lock_token
    return api._delete(f"/cluster/sdn/vnets/{vnet}/subnets/{subnet}", params)


# --- SDN plan factories -----------------------------------------------------

def plan_sdn_zone_create(zone: str, zone_type: str, options: dict | None = None) -> Plan:
    """Preview creating an SDN zone. PURE. RISK_LOW — pending, inert until apply."""
    zone = _check_sdn_id(zone, "zone")
    zone_type = _check_zone_type(zone_type)
    _check_sdn_options(options)
    return Plan(
        action="pve_sdn_zone_create", target=f"sdn/zones/{zone}",
        change=f"create SDN {zone_type} zone '{zone}' (pending)", current={},
        blast_radius=_sdn_pending_blast(f"stages a PENDING SDN zone '{zone}' (type={zone_type})"),
        risk=RISK_LOW, risk_reasons=["SDN object create is a pending config change — inert until apply"],
    )


def plan_sdn_zone_update(zone: str, options: dict | None = None, delete: list | str | None = None) -> Plan:
    """Preview updating an SDN zone. PURE. RISK_LOW — pending, inert until apply."""
    zone = _check_sdn_id(zone, "zone")
    _check_sdn_options(options)
    if not options and not delete:
        raise ProximoError("sdn_zone_update requires at least one option to set or delete")
    keys = sorted(set(options or {})) + ([f"-{k}" for k in (delete if isinstance(delete, list) else
                  ([delete] if delete else []))])
    return Plan(
        action="pve_sdn_zone_update", target=f"sdn/zones/{zone}",
        change=f"update SDN zone '{zone}' (pending): {', '.join(keys) or '(none)'}", current={},
        blast_radius=_sdn_pending_blast(f"stages a PENDING update to SDN zone '{zone}'"),
        risk=RISK_LOW, risk_reasons=["SDN object update is a pending config change — inert until apply"],
    )


def plan_sdn_zone_delete(api, zone: str) -> Plan:
    """Preview deleting an SDN zone. Reads current zones (one safe read). RISK_MEDIUM — staging a
    removal that an apply would enact; PVE refuses if a vnet still references the zone."""
    zone = _check_sdn_id(zone, "zone")
    current: dict = {}
    try:
        current = next((z for z in (sdn_zones_list(api) or []) if z.get("zone") == zone), {})
    except Exception:
        current = {}
    return Plan(
        action="pve_sdn_zone_delete", target=f"sdn/zones/{zone}",
        change=f"delete SDN zone '{zone}' (pending)", current=current,
        blast_radius=[
            f"stages REMOVAL of SDN zone '{zone}' (pending)",
            "takes effect on pve_sdn_apply; if the zone is live-applied, applying removes its networking",
            "PVE refuses to delete a zone still referenced by a vnet",
            "no UNDO at config level: re-create the zone to revert",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=["staging removal of an SDN zone — an apply would disrupt its networking"],
    )


def plan_sdn_vnet_create(vnet: str, zone: str, options: dict | None = None) -> Plan:
    """Preview creating an SDN vnet. PURE. RISK_LOW — pending, inert until apply."""
    vnet = _check_sdn_id(vnet, "vnet")
    zone = _check_sdn_id(zone, "zone")
    _check_sdn_options(options)
    return Plan(
        action="pve_sdn_vnet_create", target=f"sdn/vnets/{vnet}",
        change=f"create SDN vnet '{vnet}' in zone '{zone}' (pending)", current={},
        blast_radius=_sdn_pending_blast(f"stages a PENDING SDN vnet '{vnet}' in zone '{zone}'"),
        risk=RISK_LOW, risk_reasons=["SDN object create is a pending config change — inert until apply"],
    )


def plan_sdn_vnet_update(vnet: str, options: dict | None = None, delete: list | str | None = None) -> Plan:
    """Preview updating an SDN vnet. PURE. RISK_LOW — pending, inert until apply."""
    vnet = _check_sdn_id(vnet, "vnet")
    _check_sdn_options(options)
    if not options and not delete:
        raise ProximoError("sdn_vnet_update requires at least one option to set or delete")
    return Plan(
        action="pve_sdn_vnet_update", target=f"sdn/vnets/{vnet}",
        change=f"update SDN vnet '{vnet}' (pending)", current={},
        blast_radius=_sdn_pending_blast(f"stages a PENDING update to SDN vnet '{vnet}'"),
        risk=RISK_LOW, risk_reasons=["SDN object update is a pending config change — inert until apply"],
    )


def plan_sdn_vnet_delete(api, vnet: str) -> Plan:
    """Preview deleting an SDN vnet. Reads current vnets (one safe read). RISK_MEDIUM."""
    vnet = _check_sdn_id(vnet, "vnet")
    current: dict = {}
    try:
        current = next((v for v in (sdn_vnets_list(api) or []) if v.get("vnet") == vnet), {})
    except Exception:
        current = {}
    return Plan(
        action="pve_sdn_vnet_delete", target=f"sdn/vnets/{vnet}",
        change=f"delete SDN vnet '{vnet}' (pending)", current=current,
        blast_radius=[
            f"stages REMOVAL of SDN vnet '{vnet}' (pending)",
            "takes effect on pve_sdn_apply; if applied, removes the vnet's virtual network",
            "PVE refuses to delete a vnet still referenced by a subnet",
            "no UNDO at config level: re-create the vnet to revert",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=["staging removal of an SDN vnet — an apply would disrupt its networking"],
    )


def plan_sdn_subnet_create(vnet: str, subnet: str, options: dict | None = None) -> Plan:
    """Preview creating an SDN subnet. PURE. RISK_LOW — pending, inert until apply."""
    vnet = _check_sdn_id(vnet, "vnet")
    subnet = _check_subnet_cidr(subnet)
    _check_sdn_options(options)
    return Plan(
        action="pve_sdn_subnet_create", target=f"sdn/vnets/{vnet}/subnets/{subnet}",
        change=f"create SDN subnet {subnet} in vnet '{vnet}' (pending)", current={},
        blast_radius=_sdn_pending_blast(f"stages a PENDING SDN subnet {subnet} in vnet '{vnet}'"),
        risk=RISK_LOW, risk_reasons=["SDN object create is a pending config change — inert until apply"],
    )


def plan_sdn_subnet_update(vnet: str, subnet: str, options: dict | None = None,
                           delete: list | str | None = None) -> Plan:
    """Preview updating an SDN subnet. PURE. RISK_LOW — pending, inert until apply."""
    vnet = _check_sdn_id(vnet, "vnet")
    subnet = _check_subnet_path_id(subnet)
    _check_sdn_options(options)
    if not options and not delete:
        raise ProximoError("sdn_subnet_update requires at least one option to set or delete")
    return Plan(
        action="pve_sdn_subnet_update", target=f"sdn/vnets/{vnet}/subnets/{subnet}",
        change=f"update SDN subnet {subnet} in vnet '{vnet}' (pending)", current={},
        blast_radius=_sdn_pending_blast(f"stages a PENDING update to SDN subnet {subnet}"),
        risk=RISK_LOW, risk_reasons=["SDN object update is a pending config change — inert until apply"],
    )


def plan_sdn_subnet_delete(vnet: str, subnet: str) -> Plan:
    """Preview deleting an SDN subnet. PURE. RISK_MEDIUM — staging a removal."""
    vnet = _check_sdn_id(vnet, "vnet")
    subnet = _check_subnet_path_id(subnet)
    return Plan(
        action="pve_sdn_subnet_delete", target=f"sdn/vnets/{vnet}/subnets/{subnet}",
        change=f"delete SDN subnet {subnet} from vnet '{vnet}' (pending)", current={},
        blast_radius=[
            f"stages REMOVAL of SDN subnet {subnet} from vnet '{vnet}' (pending)",
            "takes effect on pve_sdn_apply; if applied, removes the subnet's addressing/gateway",
            "no UNDO at config level: re-create the subnet to revert",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=["staging removal of an SDN subnet — an apply would disrupt its addressing"],
    )
