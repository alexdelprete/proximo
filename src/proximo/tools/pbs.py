"""PBS (Proxmox Backup Server) deep read/mutation tools plus the PBS config + safety plane (datastores,
namespaces, remotes, traffic control, prune/verify/GC).

Split out of proximo.server (2026-07-02) — see proximo/server.py's module
docstring for the funnel these wrappers depend on.
"""
from __future__ import annotations

import proximo.server as _proximo_server
from proximo.backup_schedules import pbs_scheduled_jobs_list
from proximo.pbs import (
    datastore_list as pbs_datastore_list_op,
)
from proximo.pbs import (
    datastore_status as pbs_datastore_status_op,
)
from proximo.pbs import (
    gc_start as pbs_gc_start_op,
)
from proximo.pbs import (
    gc_status as pbs_gc_status_op,
)
from proximo.pbs import (
    namespace_create as pbs_namespace_create_op,
)
from proximo.pbs import (
    namespace_delete as pbs_namespace_delete_op,
)
from proximo.pbs import (
    namespace_list as pbs_namespace_list_op,
)
from proximo.pbs import (
    plan_gc_start as pbs_plan_gc_start,
)
from proximo.pbs import (
    plan_namespace_create as pbs_plan_namespace_create,
)
from proximo.pbs import (
    plan_namespace_delete as pbs_plan_namespace_delete,
)
from proximo.pbs import (
    plan_prune as pbs_plan_prune,
)
from proximo.pbs import (
    plan_snapshot_delete as pbs_plan_snapshot_delete,
)
from proximo.pbs import (
    plan_verify_start as pbs_plan_verify_start,
)
from proximo.pbs import (
    prune as pbs_prune_op,
)
from proximo.pbs import (
    snapshot_delete as pbs_snapshot_delete_op,
)
from proximo.pbs import (
    snapshots_list as pbs_snapshots_list_op,
)
from proximo.pbs import (
    tasks_list as pbs_tasks_list_op,
)
from proximo.pbs import (
    verify_start as pbs_verify_start_op,
)
from proximo.pbs_config import (
    _remote_password_fingerprint,
)
from proximo.pbs_config import (
    datastore_create as pbs_cfg_datastore_create,
)
from proximo.pbs_config import (
    datastore_delete as pbs_cfg_datastore_delete,
)
from proximo.pbs_config import (
    datastore_get as pbs_cfg_datastore_get,
)
from proximo.pbs_config import (
    datastore_update as pbs_cfg_datastore_update,
)
from proximo.pbs_config import (
    group_change_owner as pbs_cfg_group_change_owner,
)
from proximo.pbs_config import (
    plan_datastore_create as pbs_plan_datastore_create,
)
from proximo.pbs_config import (
    plan_datastore_delete as pbs_plan_datastore_delete,
)
from proximo.pbs_config import (
    plan_datastore_update as pbs_plan_datastore_update,
)
from proximo.pbs_config import (
    plan_group_change_owner as pbs_plan_group_change_owner,
)
from proximo.pbs_config import (
    plan_remote_create as pbs_plan_remote_create,
)
from proximo.pbs_config import (
    plan_remote_delete as pbs_plan_remote_delete,
)
from proximo.pbs_config import (
    plan_remote_update as pbs_plan_remote_update,
)
from proximo.pbs_config import (
    plan_snapshot_notes_set as pbs_plan_snapshot_notes_set,
)
from proximo.pbs_config import (
    plan_snapshot_protected_set as pbs_plan_snapshot_protected_set,
)
from proximo.pbs_config import (
    plan_traffic_control_delete as pbs_plan_traffic_control_delete,
)
from proximo.pbs_config import (
    plan_traffic_control_upsert as pbs_plan_traffic_control_upsert,
)
from proximo.pbs_config import (
    remote_create as pbs_cfg_remote_create,
)
from proximo.pbs_config import (
    remote_delete as pbs_cfg_remote_delete,
)
from proximo.pbs_config import (
    remote_get as pbs_cfg_remote_get,
)
from proximo.pbs_config import (
    remote_update as pbs_cfg_remote_update,
)
from proximo.pbs_config import (
    remotes_list as pbs_cfg_remotes_list,
)
from proximo.pbs_config import (
    snapshot_notes_set as pbs_cfg_snapshot_notes_set,
)
from proximo.pbs_config import (
    snapshot_protected_set as pbs_cfg_snapshot_protected_set,
)
from proximo.pbs_config import (
    traffic_control_delete as pbs_cfg_traffic_control_delete,
)
from proximo.pbs_config import (
    traffic_control_upsert as pbs_cfg_traffic_control_upsert,
)
from proximo.pbs_config import (
    traffic_controls_list as pbs_cfg_traffic_controls_list,
)
from proximo.server import (
    _audited,
    _plan,
    tool,
)

# --- PBS (Proxmox Backup Server) deep (read) ---

@tool()
def pbs_datastores_list() -> list[dict]:
    """List all datastores on the PBS server (read). Needs PROXIMO_PBS_* config."""
    _, pbs = _proximo_server._pbs()
    return _audited("pbs_datastores_list", "pbs/datastores",
                    lambda: pbs_datastore_list_op(pbs))


@tool()
def pbs_datastore_status(store: str) -> dict:
    """Get usage statistics for a PBS datastore (read)."""
    _, pbs = _proximo_server._pbs()
    return _audited("pbs_datastore_status", f"pbs/{store}",
                    lambda: pbs_datastore_status_op(pbs, store))


@tool()
def pbs_gc_status(store: str) -> dict:
    """Get garbage-collection status for a PBS datastore (read)."""
    _, pbs = _proximo_server._pbs()
    return _audited("pbs_gc_status", f"pbs/{store}/gc", lambda: pbs_gc_status_op(pbs, store))


@tool()
def pbs_snapshots_list(store: str, ns: str | None = None, backup_type: str | None = None,
                       backup_id: str | None = None) -> list[dict]:
    """List backup snapshots in a PBS datastore, with optional filters (read)."""
    _, pbs = _proximo_server._pbs()
    return _audited("pbs_snapshots_list", f"pbs/{store}",
                    lambda: pbs_snapshots_list_op(pbs, store, ns, backup_type, backup_id))


@tool()
def pbs_namespaces_list(store: str, parent: str | None = None,
                        max_depth: int | None = None) -> list[dict]:
    """List namespaces within a PBS datastore (read)."""
    _, pbs = _proximo_server._pbs()
    return _audited("pbs_namespaces_list", f"pbs/{store}",
                    lambda: pbs_namespace_list_op(pbs, store, parent, max_depth))


@tool()
def pbs_remotes_list() -> list[dict]:
    """List all PBS remote sync-sources (read). Passwords are never returned by the PBS API.
    Needs PROXIMO_PBS_* config."""
    _, pbs = _proximo_server._pbs()
    return _audited("pbs_remotes_list", "pbs/config/remote",
                    lambda: pbs_cfg_remotes_list(pbs))


@tool()
def pbs_remote_get(name: str) -> dict:
    """Get the config of one PBS remote sync-source by name (read). No password returned.
    Needs PROXIMO_PBS_* config."""
    _, pbs = _proximo_server._pbs()
    return _audited("pbs_remote_get", f"pbs/config/remote/{name}",
                    lambda: pbs_cfg_remote_get(pbs, name))


@tool()
def pbs_traffic_controls_list() -> list[dict]:
    """List all PBS traffic-control bandwidth rules (read). Needs PROXIMO_PBS_* config."""
    _, pbs = _proximo_server._pbs()
    return _audited("pbs_traffic_controls_list", "pbs/config/traffic-control",
                    lambda: pbs_cfg_traffic_controls_list(pbs))


@tool()
def pbs_jobs_list(job_type: str) -> list[dict]:
    """List all PBS scheduled jobs of the given type (read). job_type = sync|verify|prune.
    Returns all jobs with their configs. Raises on invalid job_type. Needs PROXIMO_PBS_* config."""
    _, pbs = _proximo_server._pbs()
    return _audited("pbs_jobs_list", f"pbs/config/{job_type}",
                    lambda: pbs_scheduled_jobs_list(pbs, job_type))


@tool()
def pbs_tasks_list(node: str = "localhost", limit: int | None = None,
                   running: bool | None = None, errors: bool | None = None) -> list[dict]:
    """List PBS tasks on a node (read). Defaults to 'localhost' (standard single-node PBS name).
    Optionally filter: running=True for active tasks, errors=True for failed tasks.
    Needs PROXIMO_PBS_* config."""
    _, pbs = _proximo_server._pbs()
    return _audited("pbs_tasks_list", f"pbs/nodes/{node}/tasks",
                    lambda: pbs_tasks_list_op(pbs, node, limit, running, errors))


@tool()
def pbs_datastore_get(name: str) -> dict:
    """Get full config of one PBS datastore by name (read). Returns path, gc-schedule, etc.
    For runtime usage stats use pbs_datastore_status instead. Needs PROXIMO_PBS_* config."""
    _, pbs = _proximo_server._pbs()
    return _audited("pbs_datastore_get", f"pbs/config/datastore/{name}",
                    lambda: pbs_cfg_datastore_get(pbs, name))


# --- PBS deep (mutation) ---

@tool()
def pbs_gc_start(store: str, confirm: bool = False) -> dict:
    """MUTATION (HIGH): start garbage collection on a PBS datastore. Dry-run by default — GC
    permanently removes unreferenced chunks (no undo). confirm=True to execute. Async — UPID."""
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/{store}/gc"
    plan = _plan("pbs_gc_start", tgt, lambda: pbs_plan_gc_start(store))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_gc_start", tgt, lambda: pbs_gc_start_op(pbs, store),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@tool()
def pbs_verify_start(store: str, ns: str | None = None, backup_type: str | None = None,
                     backup_id: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: start an integrity verification run on a PBS datastore. Dry-run by default —
    non-destructive (read-only check) but heavy I/O. confirm=True to execute. Async — UPID."""
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/{store}/verify"
    plan = _plan("pbs_verify_start", tgt,
                 lambda: pbs_plan_verify_start(store, ns, backup_type, backup_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_verify_start", tgt,
                    lambda: pbs_verify_start_op(pbs, store, ns, backup_type, backup_id),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@tool()
def pbs_prune(store: str, keep_last: int | None = None, keep_daily: int | None = None,
              keep_weekly: int | None = None, keep_monthly: int | None = None,
              keep_yearly: int | None = None, ns: str | None = None,
              backup_type: str | None = None, backup_id: str | None = None,
              dry_run: bool = True, confirm: bool = False) -> dict:
    """MUTATION: prune backup snapshots per a retention policy. TWO safety gates: confirm
    (Proximo dry-run vs execute) AND dry_run (PBS-side preview). dry_run=True (default) only
    previews; dry_run=False DELETES recovery points (PLAN is HIGH, no undo). confirm=True to
    execute. Synchronous — returns prune decisions."""
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/{store}/prune"
    plan = _plan("pbs_prune", tgt,
                 lambda: pbs_plan_prune(store, keep_last, keep_daily, keep_weekly,
                                        keep_monthly, keep_yearly, ns, backup_type,
                                        backup_id, dry_run))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_prune", tgt,
                    lambda: pbs_prune_op(pbs, store, keep_last, keep_daily,
                                        keep_weekly, keep_monthly, keep_yearly,
                                        ns, backup_type, backup_id, dry_run),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "dry_run": dry_run})


@tool()
def pbs_snapshot_delete(store: str, backup_type: str, backup_id: str, backup_time: int,
                        ns: str | None = None, confirm: bool = False) -> dict:
    """MUTATION (HIGH): delete a specific backup snapshot (a recovery point) from a PBS
    datastore. Dry-run by default. Permanent — no undo. confirm=True to execute. Synchronous."""
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/{store}/{backup_type}/{backup_id}"
    plan = _plan("pbs_snapshot_delete", tgt,
                 lambda: pbs_plan_snapshot_delete(store, backup_type, backup_id, backup_time, ns))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_snapshot_delete", tgt,
                    lambda: pbs_snapshot_delete_op(pbs, store, backup_type, backup_id, backup_time, ns),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pbs_namespace_create(store: str, name: str, parent: str | None = None,
                         confirm: bool = False) -> dict:
    """MUTATION: create a namespace within a PBS datastore. Dry-run by default (additive, LOW).
    confirm=True to execute. Synchronous."""
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/{store}/namespace/{name}"
    plan = _plan("pbs_namespace_create", tgt,
                 lambda: pbs_plan_namespace_create(store, name, parent))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_namespace_create", tgt,
                    lambda: pbs_namespace_create_op(pbs, store, name, parent),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pbs_namespace_delete(store: str, ns: str, delete_groups: bool = False,
                         confirm: bool = False) -> dict:
    """MUTATION: delete a namespace from a PBS datastore. Dry-run by default — delete_groups=True
    is HIGH (it deletes all backup groups/snapshots inside the namespace, no undo). confirm=True
    to execute. Synchronous."""
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/{store}/namespace/{ns}"
    plan = _plan("pbs_namespace_delete", tgt,
                 lambda: pbs_plan_namespace_delete(store, ns, delete_groups))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_namespace_delete", tgt,
                    lambda: pbs_namespace_delete_op(pbs, store, ns, delete_groups),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- PBS config + safety plane (Wave 5) ---

@tool()
def pbs_datastore_create(
    name: str,
    path: str,
    gc_schedule: str | None = None,
    prune_schedule: str | None = None,
    notification_mode: str | None = None,
    comment: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): create a new PBS datastore at the given path.

    Dry-run by default — additive, but a misconfigured path can conflict with existing storage.
    PBS datastore creation is an async worker task (UPID) → outcome='submitted' (not 'ok').
    No rollback primitive. confirm=True to execute.

    POST /config/datastore
    Smoke-confirm: gc-schedule / prune-schedule / notification-mode param names; sync-vs-async.
    """
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/datastore/{name}"
    plan = _plan("pbs_datastore_create", tgt,
                 lambda: pbs_plan_datastore_create(
                     name, path, gc_schedule=gc_schedule,
                     prune_schedule=prune_schedule,
                     notification_mode=notification_mode, comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_datastore_create", tgt,
                    lambda: pbs_cfg_datastore_create(
                        pbs, name, path, gc_schedule=gc_schedule,
                        prune_schedule=prune_schedule,
                        notification_mode=notification_mode, comment=comment),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@tool()
def pbs_datastore_update(
    name: str,
    gc_schedule: str | None = None,
    prune_schedule: str | None = None,
    notification_mode: str | None = None,
    comment: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): update PBS datastore configuration. Dry-run by default.

    CAPTURE: reads current config before planning; on read failure the plan is marked incomplete.
    Changing gc-schedule / prune-schedule affects data retention cluster-wide.
    No rollback primitive — revert by re-applying the captured config. confirm=True to execute.

    PUT /config/datastore/{name}
    Smoke-confirm: accepted param names (hyphenated vs underscored).
    """
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/datastore/{name}"
    plan = _plan("pbs_datastore_update", tgt,
                 lambda: pbs_plan_datastore_update(
                     pbs, name, gc_schedule=gc_schedule,
                     prune_schedule=prune_schedule,
                     notification_mode=notification_mode, comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_datastore_update", tgt,
                    lambda: pbs_cfg_datastore_update(
                        pbs, name, gc_schedule=gc_schedule,
                        prune_schedule=prune_schedule,
                        notification_mode=notification_mode, comment=comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pbs_datastore_delete(
    name: str,
    destroy_data: bool = False,
    keep_job_configs: bool = False,
    confirm: bool = False,
) -> dict:
    """MUTATION: delete a PBS datastore. Dry-run by default. RISK IS CONDITIONAL:

    destroy_data=False (default) → MEDIUM: detaches the datastore config; backup CHUNKS
      REMAIN ON DISK and the datastore is re-addable to recover.
    destroy_data=True → HIGH, IRREVERSIBLE: PERMANENTLY DESTROYS ALL backup data in the
      named datastore — no recovery possible.

    PBS deletion is an async worker task (UPID) → outcome='submitted'. confirm=True to execute.

    DELETE /config/datastore/{name}
    Smoke-confirm: destroy-data / keep-job-configs param names; sync-vs-async.
    """
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/datastore/{name}"
    plan = _plan("pbs_datastore_delete", tgt,
                 lambda: pbs_plan_datastore_delete(
                     name, destroy_data=destroy_data, keep_job_configs=keep_job_configs))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_datastore_delete", tgt,
                    lambda: pbs_cfg_datastore_delete(
                        pbs, name, destroy_data=destroy_data,
                        keep_job_configs=keep_job_configs),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@tool()
def pbs_snapshot_protected_set(
    store: str,
    backup_type: str,
    backup_id: str,
    backup_time: int,
    protected: bool,
    ns: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: set or clear the protected flag on a PBS snapshot. RISK IS CONDITIONAL:

    protected=True  → LOW:  shields the snapshot from pruning and GC (protective).
    protected=False → HIGH: SILENTLY re-enables pruning/GC — this recovery point can now
      be auto-deleted by the next prune job or GC run. No undo once auto-deleted.

    No PBS snapshot primitive for rollback. Dry-run by default. confirm=True to execute.

    PUT /admin/datastore/{store}/protected
    Smoke-confirm: exact path + param names (backup-type, backup-id, backup-time, protected).
    """
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/{store}/{backup_type}/{backup_id}@{backup_time}/protected"
    plan = _plan("pbs_snapshot_protected_set", tgt,
                 lambda: pbs_plan_snapshot_protected_set(
                     store, backup_type, backup_id, backup_time, protected, ns))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_snapshot_protected_set", tgt,
                    lambda: pbs_cfg_snapshot_protected_set(
                        pbs, store, backup_type, backup_id, backup_time, protected, ns),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pbs_snapshot_notes_set(
    store: str,
    backup_type: str,
    backup_id: str,
    backup_time: int,
    notes: str,
    ns: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (LOW): annotate a PBS snapshot with notes. Dry-run by default.

    CAPTURE: reads current notes before planning; on failure the plan is marked incomplete.
    Does not affect backup data, retention, or protection.
    No PBS snapshot primitive — revert by re-applying the captured notes. confirm=True to execute.

    PUT /admin/datastore/{store}/notes
    Smoke-confirm: exact endpoint path + param names (backup-type, backup-id, backup-time).
    """
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/{store}/{backup_type}/{backup_id}@{backup_time}/notes"
    plan = _plan("pbs_snapshot_notes_set", tgt,
                 lambda: pbs_plan_snapshot_notes_set(
                     pbs, store, backup_type, backup_id, backup_time, notes, ns))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_snapshot_notes_set", tgt,
                    lambda: pbs_cfg_snapshot_notes_set(
                        pbs, store, backup_type, backup_id, backup_time, notes, ns),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pbs_group_change_owner(
    store: str,
    backup_type: str,
    backup_id: str,
    new_owner: str,
    ns: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): reassign the owner of a PBS backup group. Dry-run by default.

    The new owner controls deletion and prune of this backup group.
    The previous owner loses those permissions immediately.
    No PBS snapshot primitive — revert by re-assigning the owner back. confirm=True to execute.

    PUT /admin/datastore/{store}/change-owner
    Smoke-confirm: exact path + new-owner vs owner param name.
    """
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/{store}/{backup_type}/{backup_id}/owner"
    plan = _plan("pbs_group_change_owner", tgt,
                 lambda: pbs_plan_group_change_owner(
                     store, backup_type, backup_id, new_owner, ns))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_group_change_owner", tgt,
                    lambda: pbs_cfg_group_change_owner(
                        pbs, store, backup_type, backup_id, new_owner, ns),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pbs_remote_create(
    name: str,
    host: str,
    auth_id: str,
    password: str,
    fingerprint: str | None = None,
    port: int | None = None,
    comment: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): create a PBS remote sync-source. Dry-run by default.

    PRIVATE PASSWORD REDACTION: 'password' is a remote user credential. It is
    UNCONDITIONALLY redacted from the server-side plan, change, current state, detail,
    and audit ledger. Only {"password":"[redacted]"} is recorded on those surfaces.
    L02 NOTE: the MCP tool-call itself is a structured JSON object in which 'password' appears
    as a plain parameter — it is visible in the LLM's output token stream and in any MCP client
    log. This is an MCP-protocol property; server-side redaction protects the ledger only.
    The TLS cert 'fingerprint' is PUBLIC data — it is NOT redacted.

    No rollback primitive — revert by deleting the remote (pbs_remote_delete). confirm=True to execute.

    POST /config/remote
    Smoke-confirm: auth-id vs authid param name; port param name.
    """
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/remote/{name}"
    # UNCONDITIONAL: password never passes through the plan factory or into the ledger.
    pw_detail = _remote_password_fingerprint()
    plan = _plan("pbs_remote_create", tgt,
                 lambda: pbs_plan_remote_create(
                     name, host, auth_id, fingerprint=fingerprint,
                     port=port, comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict(), **pw_detail}
    return _audited("pbs_remote_create", tgt,
                    lambda: pbs_cfg_remote_create(
                        pbs, name, host, auth_id, password,
                        fingerprint=fingerprint, port=port, comment=comment),
                    mutation=True, outcome="ok",
                    detail={**pw_detail, "confirmed": True})


@tool()
def pbs_remote_update(
    name: str,
    host: str | None = None,
    auth_id: str | None = None,
    password: str | None = None,
    fingerprint: str | None = None,
    port: int | None = None,
    comment: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): update an existing PBS remote. Dry-run by default.

    CAPTURE: reads current (non-secret) config before planning; on failure plan is marked incomplete.
    PRIVATE PASSWORD REDACTION: if 'password' is provided it is UNCONDITIONALLY redacted from the
    server-side plan, change, current state, detail, and audit ledger.
    L02 NOTE: the MCP tool-call itself is a structured JSON object in which 'password' appears as
    a plain parameter — visible in the LLM's output token stream and any MCP client log.
    This is an MCP-protocol property; server-side redaction protects the ledger only.
    The TLS cert 'fingerprint' is PUBLIC and appears in plans/logs for audit.
    No rollback primitive — revert by re-applying captured config. confirm=True to execute.

    PUT /config/remote/{name}
    Smoke-confirm: auth-id param name; whether partial PUT is accepted.
    """
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/remote/{name}"
    # UNCONDITIONAL if password provided: never into plan factory or ledger.
    pw_detail = _remote_password_fingerprint() if password is not None else {}
    plan = _plan("pbs_remote_update", tgt,
                 lambda: pbs_plan_remote_update(
                     pbs, name, host=host, auth_id=auth_id,
                     fingerprint=fingerprint, port=port, comment=comment))
    if not confirm:
        resp = {"status": "plan", **plan.as_dict()}
        if pw_detail:
            resp.update(pw_detail)
        return resp
    return _audited("pbs_remote_update", tgt,
                    lambda: pbs_cfg_remote_update(
                        pbs, name, host=host, auth_id=auth_id,
                        password=password, fingerprint=fingerprint,
                        port=port, comment=comment),
                    mutation=True, outcome="ok",
                    detail={**pw_detail, "confirmed": True})


@tool()
def pbs_remote_delete(
    name: str,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): remove a PBS remote and its stored credentials. Dry-run by default.

    After deletion: any sync jobs referencing this remote break; re-add needs the password
    re-supplied. No rollback primitive — re-create with pbs_remote_create to recover.
    confirm=True to execute.

    DELETE /config/remote/{name}
    Smoke-confirm: response shape on success.
    """
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/remote/{name}"
    plan = _plan("pbs_remote_delete", tgt,
                 lambda: pbs_plan_remote_delete(name))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_remote_delete", tgt,
                    lambda: pbs_cfg_remote_delete(pbs, name),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pbs_traffic_control_upsert(
    name: str,
    rate_in: int | None = None,
    rate_out: int | None = None,
    network: str | None = None,
    burst_in: int | None = None,
    burst_out: int | None = None,
    timeframe: str | None = None,
    comment: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: create or update a PBS traffic-control (bandwidth-limit) rule. Dry-run by default.

    Detects create-vs-update by reading the existing rule config (CAPTURE on update path):
      create → LOW:    additive, no existing rule changed.
      update → MEDIUM: changing rate limits can throttle backups or saturate the network.

    A too-low rate-in or rate-out throttles PBS backups to a crawl.
    No rollback primitive. confirm=True to execute.

    POST (create) or PUT (update) /config/traffic-control[/{name}]
    Smoke-confirm: create-vs-update dispatch; rate-in/rate-out/burst-in/burst-out/timeframe param names.
    """
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/traffic-control/{name}"
    plan = _plan("pbs_traffic_control_upsert", tgt,
                 lambda: pbs_plan_traffic_control_upsert(
                     pbs, name, rate_in=rate_in, rate_out=rate_out, network=network,
                     burst_in=burst_in, burst_out=burst_out, timeframe=timeframe,
                     comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_traffic_control_upsert", tgt,
                    lambda: pbs_cfg_traffic_control_upsert(
                        pbs, name, rate_in=rate_in, rate_out=rate_out, network=network,
                        burst_in=burst_in, burst_out=burst_out, timeframe=timeframe,
                        comment=comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pbs_traffic_control_delete(
    name: str,
    confirm: bool = False,
) -> dict:
    """MUTATION (LOW): remove a PBS traffic-control (bandwidth-limit) rule. Dry-run by default.

    After deletion: backups run unthrottled on the matched network.
    Recoverable by re-creating the rule with pbs_traffic_control_upsert. confirm=True to execute.

    DELETE /config/traffic-control/{name}
    Smoke-confirm: response shape on success.
    """
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/traffic-control/{name}"
    plan = _plan("pbs_traffic_control_delete", tgt,
                 lambda: pbs_plan_traffic_control_delete(name))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_traffic_control_delete", tgt,
                    lambda: pbs_cfg_traffic_control_delete(pbs, name),
                    mutation=True, outcome="ok", detail={"confirmed": True})
