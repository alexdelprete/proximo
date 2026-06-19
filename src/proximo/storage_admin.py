"""Storage administration (storage.cfg CRUD) — cluster-scoped PVE storage *definitions*.

This module manages the PVE storage *definitions* (cluster storage.cfg) via the
/storage cluster API — distinct from the existing storage *content* module (storage.py),
which covers per-node content listing, download, and deletion.

Key structural notes:
- All endpoints are cluster-scoped (/storage, /storage/{storage}) — NOT /nodes/{node}/storage.
  The existing node_storage() in backends.py is a per-node status read; this module is
  the cluster-level definition CRUD.
- storage_create / storage_update / storage_delete are MUTATIONS — confirm-gated + audited
  at the server layer before these functions are called.
- plan_* functions are pure factories (no API call); they return a Plan with honest,
  pre-classified risk ratings.

Smoke-confirm notes throughout — none of these endpoints have been verified against a live
PVE instance. Verify endpoint shapes, response field names, and param semantics before
relying on them in production.
"""

from __future__ import annotations

from . import blast
from .backends import ProximoError
from .planning import RISK_HIGH, RISK_MEDIUM, Plan, _max_risk
from .storage import _check_storage  # reuse: same regex/rule, no duplication

# Smoke-confirm: _check_storage (from storage.py) uses ^[A-Za-z0-9._-]+\Z — permits dot-only
# names such as "." and ".." as valid storage IDs (pre-existing; not changed here).

# ---------------------------------------------------------------------------
# Local validators
# ---------------------------------------------------------------------------

# Curated set of PVE storage types as of PVE 8.x.
# Smoke-confirm: verify this list against the PVE API viewer for the target version.
# Additional types (e.g. glusterfs, zfs, drbd) may be accepted by PVE but are not
# listed here — operators hitting a rejection error should add the type to this set.
_VALID_STORAGE_TYPES = frozenset({
    "dir",
    "nfs",
    "cifs",
    "lvm",
    "lvmthin",
    "zfspool",
    "pbs",
    "cephfs",
    "rbd",
    "iscsi",
})


def _check_storage_type(storage_type: str) -> str:
    """Validate a PVE storage type against the curated allowed set.

    Smoke-confirm: the allowed set (_VALID_STORAGE_TYPES) is curated from PVE 8.x docs
    but may not be exhaustive. Verify against the live PVE API viewer for your version.
    """
    t = str(storage_type).strip()
    if t not in _VALID_STORAGE_TYPES:
        raise ProximoError(
            f"unsupported storage type: {storage_type!r} "
            f"(expected one of {sorted(_VALID_STORAGE_TYPES)})"
        )
    return t


# ---------------------------------------------------------------------------
# READ operations — no confirm, no plan; audited by the server layer
# ---------------------------------------------------------------------------

def storage_config_list(api) -> list:
    """List all storage definitions from the cluster storage.cfg.

    GET /storage
    Returns a list of storage definition dicts from PVE.

    This is a CLUSTER-SCOPED endpoint (no /nodes/{node} prefix) — it reads
    the shared storage.cfg, not a per-node status.

    Smoke-confirm: verify returned field names — expected dict keys include
    {storage, type, content, path, server, export, nodes, disable, shared, ...}
    but field names and presence vary by storage type and PVE version. Not all
    fields appear in every entry.
    """
    return api._get("/storage") or []


def storage_config_get(api, storage: str) -> dict:
    """Get a single storage definition from the cluster storage.cfg.

    GET /storage/{storage}
    Returns a dict of the storage definition from PVE.

    Smoke-confirm: verify returned field names for each storage type — keys vary
    by type (dir has 'path'; nfs has 'server'+'export'; pbs has 'server'+'datastore';
    etc.). Do not assume all fields are present.
    """
    _check_storage(storage)
    return api._get(f"/storage/{storage}") or {}


# ---------------------------------------------------------------------------
# MUTATION operations — each is confirm-gated + plan-first at the server layer
# ---------------------------------------------------------------------------

def storage_create(
    api,
    storage: str,
    storage_type: str,
    content: str | None = None,
    path: str | None = None,
    server: str | None = None,
    export: str | None = None,
    nodes: str | None = None,
    disable: bool = False,
    shared: bool = False,
) -> object:
    """Create a new storage definition in the cluster storage.cfg.

    POST /storage
    Body: {storage, type, [content, path, server, export, nodes, disable, shared]}

    storage: the storage ID (name used across the cluster).
    storage_type: the PVE storage driver type (e.g. 'dir', 'nfs', 'pbs').
    content: comma-separated list of content types to allow (e.g. 'iso,backup,images').
    path: filesystem path (required for type=dir; Smoke-confirm per-type required fields).
    server: remote host (required for nfs/cifs/pbs; Smoke-confirm per-type required fields).
    export: NFS export path (required for nfs; Smoke-confirm per-type required fields).
    nodes: comma-separated list of nodes this storage is available on (omit = all nodes).
    disable: if True, storage is created in disabled state (PVE sends '1'/'0').
    shared: if True, marks storage as shared across all nodes.

    Returns the PVE API response (typically None or a dict on success).

    MUTATION — confirm-gated + audited at the server layer before this is called.

    Smoke-confirm:
    - Verify the POST /storage body key is 'type' (NOT 'storage_type').
    - Verify required fields per storage type — e.g. 'path' for dir, 'server'+'export'
      for nfs, 'server'+'datastore' for pbs — do NOT claim this list is exhaustive.
    - Verify bool fields are sent as integer 1/0 (PVE API style).
    - Verify the full accepted storage type set against the live PVE API viewer.
    """
    _check_storage(storage)
    storage_type = _check_storage_type(storage_type)

    data: dict = {"storage": storage, "type": storage_type}
    if content is not None:
        data["content"] = content
    if path is not None:
        data["path"] = path
    if server is not None:
        data["server"] = server
    if export is not None:
        data["export"] = export
    if nodes is not None:
        data["nodes"] = nodes
    # Only include disable/shared when True — omitting them leaves PVE to use its own defaults.
    # Smoke-confirm: verify PVE uses 1/0 (not true/false) for these boolean fields.
    if disable:
        data["disable"] = 1
    if shared:
        data["shared"] = 1

    # MUTATION — confirm-gated + audited at the server layer.
    return api._post("/storage", data)


def storage_update(
    api,
    storage: str,
    content: str | None = None,
    nodes: str | None = None,
    disable: bool | None = None,
    shared: bool | None = None,
    delete: str | None = None,
) -> object:
    """Update an existing storage definition in the cluster storage.cfg.

    PUT /storage/{storage}
    Body: {content?, nodes?, disable?, shared?, delete?}

    The storage type CANNOT be changed via this endpoint — use delete + create.
    Only fields explicitly passed (not None) are included in the PUT body.

    storage: the storage ID to update.
    content: new comma-separated content type list.
    nodes: new comma-separated node restriction list.
    disable: True=disable (send 1), False=enable (send 0), None=leave unchanged.
    shared: True=shared (send 1), False=unshared (send 0), None=leave unchanged.
    delete: comma-separated list of config fields to UNSET on the storage definition.
            Smoke-confirm: verify the 'delete' param name and comma-sep semantics against
            a live PVE — this is the standard PVE 'delete' field that unsets named
            config keys, but confirm the exact list of unsetable fields and whether
            some fields are required and cannot be unset.

    Returns the PVE API response.

    MUTATION — confirm-gated + audited at the server layer before this is called.

    Smoke-confirm:
    - Verify PUT /storage/{storage} body field names.
    - Verify 'delete' semantics (comma-sep field names to unset; unconfirmed which fields
      can be unset vs required).
    - Verify bool fields are 1/0 integers (not true/false strings).
    """
    _check_storage(storage)

    data: dict = {}
    if content is not None:
        data["content"] = content
    if nodes is not None:
        data["nodes"] = nodes
    # disable/shared: None=omit, True=1, False=0 — distinguishable from "not provided"
    # Smoke-confirm: verify PVE uses 1/0 for bool fields on PUT.
    if disable is not None:
        data["disable"] = 1 if disable else 0
    if shared is not None:
        data["shared"] = 1 if shared else 0
    if delete is not None:
        data["delete"] = delete

    # MUTATION — confirm-gated + audited at the server layer.
    return api._put(f"/storage/{storage}", data)


def storage_delete(api, storage: str) -> object:
    """Remove a storage *definition* from the cluster storage.cfg.

    DELETE /storage/{storage}

    WARNING: This removes the storage DEFINITION cluster-wide. It does NOT erase any
    data on disk, but PVE loses the handle to that storage — any guest disk or backup
    living ONLY on this storage becomes inaccessible to PVE after this call. Backups
    stored there are no longer listable or restorable through PVE.

    To recover access: re-add the storage definition with the same configuration.

    Returns the PVE API response (typically None).

    MUTATION — confirm-gated + audited at the server layer before this is called.

    Smoke-confirm: verify DELETE /storage/{storage} returns null on success (not a UPID
    — storage config writes are synchronous pmxcfs operations, not async tasks).
    """
    _check_storage(storage)
    # MUTATION — confirm-gated + audited at the server layer.
    return api._delete(f"/storage/{storage}")


# ---------------------------------------------------------------------------
# PLAN functions — pure factories (no API call); the PLAN pillar
# ---------------------------------------------------------------------------

def plan_storage_create(
    storage: str,
    storage_type: str,
    content: str | None = None,
    path: str | None = None,
    server: str | None = None,
    export: str | None = None,
    nodes: str | None = None,
    disable: bool = False,
    shared: bool = False,
) -> Plan:
    """Preview creating a new storage definition.  PURE — no API call.

    RISK_MEDIUM: additive config change — storage.cfg gains a new entry.
    No data is destroyed; however, a misconfigured storage definition (wrong path,
    unreachable server, bad export) will fail to mount and PVE may log errors.
    Guests cannot use the storage until it is reachable; a bad mount can slow down
    PVE storage enumeration across the cluster.

    UNDO: delete the storage definition via storage_delete (noted in blast).
    """
    _check_storage(storage)
    storage_type = _check_storage_type(storage_type)  # strip + validate; use stripped form throughout

    scope_note = f"on nodes [{nodes}]" if nodes else "on all cluster nodes"
    state_note = " (created DISABLED)" if disable else ""
    shared_note = " (shared)" if shared else ""
    details = [f"type={storage_type}"]
    if content:
        details.append(f"content={content}")
    if path:
        details.append(f"path={path}")
    if server:
        details.append(f"server={server}")
    if export:
        details.append(f"export={export}")

    return Plan(
        action="pve_storage_create",
        target=f"storage/{storage}",
        change=f"create storage definition '{storage}' ({storage_type}) {scope_note}{state_note}{shared_note}",
        current={},
        blast_radius=[
            f"adds storage definition '{storage}' to storage.cfg cluster-wide{state_note}",
            f"type={storage_type}{shared_note}; {', '.join(details)}; {scope_note}",
            "misconfigured storage (unreachable path/server) will fail to mount; "
            "PVE may log errors and storage enumeration may be slower",
            "to undo: remove the definition via storage_delete",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "additive config change — no existing data is touched",
            "a misconfigured definition can fail to mount and slow cluster storage enumeration",
        ],
        note=(
            "Smoke-confirm: verify required fields per storage type "
            "(e.g. path for dir; server+export for nfs; server+datastore for pbs). "
            "This plan does not validate per-type required fields — PVE will reject "
            "the create if required fields for the type are missing. "
            "path, server, export, content, and nodes are operator-trusted strings — "
            "Proximo does not deep-validate them; PVE validates server-side."
        ),
    )


def plan_storage_update(
    api,
    storage: str,
    content: str | None = None,
    nodes: str | None = None,
    disable: bool | None = None,
    shared: bool | None = None,
    delete: str | None = None,
) -> Plan:
    """Preview updating an existing storage definition.

    Reads the cluster to NAME affected guests: `disable=True` cuts EVERY guest with a volume on this
    storage (cluster-wide); restricting `nodes` strands only the guests on the EXCLUDED nodes.
    RISK_MEDIUM floor: changing nodes/disable can cut guests off from their disks.

    Specifically: if disable=True is set, guests currently using volumes on this storage
    WILL LOSE ACCESS to their disks immediately — this includes running VMs and containers
    whose root filesystems or data volumes are on this storage. Be forceful about this.

    UNDO: the inverse update (re-enable, restore nodes list) can recover access; however,
    if a running guest's disk became inaccessible, the guest may have already crashed or
    corrupted its state.
    """
    _check_storage(storage)

    changes: list[str] = []
    if content is not None:
        changes.append(f"content -> {content!r}")
    if nodes is not None:
        changes.append(f"nodes -> {nodes!r}")
    if disable is True:
        changes.append("disable -> True (STORAGE DISABLED)")
    elif disable is False:
        changes.append("disable -> False (re-enabling)")
    if shared is not None:
        changes.append(f"shared -> {shared}")
    if delete is not None:
        changes.append(f"delete fields: {delete!r}")

    change_summary = "; ".join(changes) if changes else "no fields provided"

    base_blast = [
        f"updates storage definition '{storage}' in storage.cfg cluster-wide",
        f"changes: {change_summary}",
    ]

    if disable is True:
        base_blast.append(
            "WARNING: disable=True — ALL guests with volumes on this storage WILL LOSE ACCESS "
            "to their disks; running VMs/containers may crash or corrupt state; "
            "re-enabling restores access to the storage, but guests that lost their disk "
            "may have crashed and need a restart — config reversal does not equal guest recovery"
        )

    base_blast.append(
        "to undo: apply the inverse update (restore previous content/nodes/disable/shared values)"
    )

    # NAME the affected guests, ESCALATE risk on uncertainty/only-copy (never lower it):
    #   disable=True -> cluster-wide (every guest with a volume on this storage), same as delete.
    #   nodes=...     -> only guests on the EXCLUDED nodes (those whose node leaves the allowed set).
    # disable dominates when both are set (it cuts everyone regardless of nodes).
    summary_lines: list[str] = []
    affected: list[dict] = []
    risk = RISK_MEDIUM
    complete = True
    if disable is True:
        result = blast.storage_blast(api, storage)
        summary_lines = result.summary_lines
        affected = result.affected_dicts()
        complete = result.complete
        if result.max_severity == "high":
            risk = _max_risk(RISK_MEDIUM, RISK_HIGH)
    elif nodes is not None:
        # new_nodes parse is string-only — it never reads guest data, so it cannot under-flag.
        new_nodes = {n.strip() for n in str(nodes).split(",") if n.strip()}
        if not new_nodes:
            # PVE: an empty/omitted `nodes` value CLEARS the restriction → available on ALL nodes.
            # That is a WIDENING (strands nobody) — do NOT read empty as "available nowhere" and cry
            # wolf with maximal stranding. (Smoke-confirm nodes='' clears vs empties on your PVE.)
            summary_lines = [
                f"clears the node restriction on '{storage}' — PVE treats an empty/omitted 'nodes' "
                "value as available on ALL nodes; this WIDENS availability and strands no guests"
            ]
        else:
            guests, configs, gathered = blast.gather_storage_dependents(api, storage)
            result = blast.compute_storage_nodes_blast(storage, new_nodes, guests, configs, gathered)
            summary_lines = result.summary_lines
            affected = result.affected_dicts()
            complete = result.complete
            if result.max_severity == "high":
                risk = _max_risk(RISK_MEDIUM, RISK_HIGH)

    return Plan(
        action="pve_storage_update",
        target=f"storage/{storage}",
        change=f"update storage '{storage}': {change_summary}",
        current={},
        blast_radius=summary_lines + base_blast,
        affected=affected,
        risk=risk,
        complete=complete,
        risk_reasons=[
            "changing nodes or disabling storage can cut running guests off from their disks",
            "disabling storage / changing nodes can cut running guests off from their disks "
            "(see blast radius); not automatically reversible",
        ],
        note=(
            "Smoke-confirm: verify 'delete' param semantics (comma-sep field names to unset); "
            "verify which fields can be unset vs. which are required and cannot be deleted; "
            "verify bool fields are sent as 1/0 integers. "
            "content, nodes, and delete are operator-trusted strings — "
            "Proximo does not deep-validate them; PVE validates server-side."
        ),
    )


def plan_storage_delete(api, storage: str) -> Plan:
    """Preview deleting a storage definition.  Reads the cluster to NAME affected guests.

    RISK_HIGH (floor, never lowered): removes the storage DEFINITION cluster-wide. Any guest
    disk or backup living ONLY on this storage becomes inaccessible to PVE. Backups stored
    there are no longer listable or restorable through PVE.

    IMPORTANT: this does NOT erase on-disk data, but PVE loses the handle to the storage.
    To recover access, re-add the definition with the same configuration.

    There is no automatic undo. Re-adding the definition is the recovery path.

    The blast engine PREPENDS the computed, cluster-wide affected set (which guests lose which
    disks) ahead of the generic floor below; the floor is never replaced.
    """
    _check_storage(storage)
    result = blast.storage_blast(api, storage)

    return Plan(
        action="pve_storage_delete",
        target=f"storage/{storage}",
        change=f"remove storage definition '{storage}' from storage.cfg cluster-wide",
        current={},
        blast_radius=result.summary_lines + [
            f"removes storage definition '{storage}' from storage.cfg cluster-wide — "
            "PVE immediately loses the handle to this storage on ALL nodes",
            "any guest disk (VM image, container rootfs) living ONLY on this storage "
            "becomes inaccessible to PVE — the guest will fail to start or may crash if running",
            "backups stored on this storage are no longer listable or restorable through PVE",
            "does NOT erase on-disk data — the data remains on the underlying disk/share/pool, "
            "but PVE has no handle to reach it",
            "NO automatic undo — to recover access, re-add the storage definition "
            "with the same type and configuration",
        ],
        affected=result.affected_dicts(),
        complete=result.complete,
        risk=RISK_HIGH,
        risk_reasons=[
            "removes the storage definition cluster-wide — all nodes lose access simultaneously",
            "guest disks and backups living only on this storage become inaccessible to PVE",
            "backups are no longer listable or restorable through PVE once the definition is gone",
            "no automatic undo: re-adding the definition manually is the only recovery path",
        ],
        note=(
            "Smoke-confirm: verify DELETE /storage/{storage} is synchronous (returns null, "
            "not a UPID). Verify the cluster-wide propagation timing (pmxcfs should replicate "
            "the removal to all nodes, but confirm the replication is immediate vs. eventual)."
        ),
    )
