"""PVE backup & restore plus scheduled planes: ad-hoc backup/restore, PVE backup jobs, replication jobs, and PBS
scheduled jobs / realm sync.

Split out of proximo.server (2026-07-02) — see proximo/server.py's module
docstring for the funnel these wrappers depend on.
"""
from __future__ import annotations

import proximo.server as _proximo_server
from proximo.backup import (
    backup_delete,
    backup_list,
    plan_backup,
    plan_backup_delete,
    plan_restore,
    restore_guest,
    vzdump_backup,
)
from proximo.backup_schedules import (
    backup_job_create,
    backup_job_delete,
    backup_job_list,
    backup_job_update,
    pbs_scheduled_job_create,
    pbs_scheduled_job_delete,
    pbs_scheduled_job_run,
    pbs_scheduled_job_update,
    plan_backup_job_create,
    plan_backup_job_delete,
    plan_backup_job_update,
    plan_pbs_job_create,
    plan_pbs_job_delete,
    plan_pbs_job_run,
    plan_pbs_job_update,
    plan_pbs_realm_sync,
    plan_replication_create,
    plan_replication_delete,
    plan_replication_update,
    replication_create,
    replication_delete,
    replication_update,
)
from proximo.backup_schedules import (
    pbs_realm_sync as pbs_realm_sync_op,
)
from proximo.server import (
    _audited,
    _plan,
    tool,
)

# --- Backup & restore (REST API, async -> UPID) ---

@tool()
def pve_backup(vmid: str, storage: str, mode: str = "snapshot", compress: str = "zstd",
               kind: str = "lxc", node: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: back up a guest with vzdump. Dry-run by default; confirm=True to execute.
    mode: snapshot (online, brief) | suspend | stop (HALTS the guest). Async — returns a task UPID."""
    _, api, _, _ = _proximo_server._svc()
    target = f"{kind}/{vmid}"
    plan = _plan("pve_backup", target, lambda: plan_backup(vmid, storage, mode, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_backup", target,
                    lambda: vzdump_backup(api, vmid, storage, mode, compress, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@tool()
def pve_backup_list(storage: str, node: str | None = None) -> list[dict]:
    """List backup archives in a storage (read). Ground truth for whether a backup exists —
    a backup missing from a pve_tasks_list slice (other node, or outside its limit window)
    still shows here."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_backup_list", storage, lambda: backup_list(api, storage, node))


@tool()
def pve_backup_delete(storage: str, volid: str, node: str | None = None,
                      confirm: bool = False) -> dict:
    """MUTATION: delete a backup archive (removes a recovery point). Dry-run by default; confirm=True.
    Async — may return a task UPID or null depending on storage."""
    _, api, _, _ = _proximo_server._svc()
    plan = _plan("pve_backup_delete", volid, lambda: plan_backup_delete(api, storage, volid))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_backup_delete", volid,
                    lambda: backup_delete(api, storage, volid, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@tool()
def pve_restore(vmid: str, archive: str, storage: str, kind: str = "lxc", node: str | None = None,
                force: bool = False, pool: str | None = None, confirm: bool = False) -> dict:
    """MUTATION (DESTRUCTIVE if it overwrites an existing guest): restore a guest from a backup
    archive. Dry-run by default — the PLAN states whether it CREATES or OVERWRITES. confirm=True to
    execute. Async — returns a task UPID. pool: place the restored guest in a resource pool."""
    _, api, _, _ = _proximo_server._svc()
    target = f"{kind}/{vmid}"
    plan = _plan("pve_restore", target, lambda: plan_restore(api, vmid, archive, kind, node, force))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_restore", target,
                    lambda: restore_guest(api, vmid, archive, storage, kind, node, force, pool),
                    mutation=True, outcome="submitted", detail={"confirmed": True, "force": force})


# --- Backup Schedules (Plane B) — PVE backup jobs, replication, PBS scheduled jobs ---

@tool()
def pve_backup_job_list() -> dict:
    """List all PVE cluster backup jobs and guests not covered by any job (read).
    Returns {jobs: [...], unprotected_guests: [...]}."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_backup_job_list", "cluster/backup",
                    lambda: backup_job_list(api))


@tool()
def pve_backup_job_create(job_id: str, schedule: str, storage: str,
                          mode: str | None = None, compress: str | None = None,
                          vmid: str | None = None, all_guests: bool | None = None,
                          pool: str | None = None, exclude: str | None = None,
                          enabled: bool | None = None,
                          comment: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create a PVE cluster backup job. Dry-run by default — shows the plan.
    confirm=True to execute. Config-only; existing backups are NOT affected.
    Guest selection is mutually exclusive — pass at most one of: vmid (CSV of guest IDs),
    all_guests=True (every guest), or pool (a resource pool); PVE requires a selection.
    exclude (CSV) filters all_guests."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/backup/{job_id}"
    # all_guests -> PVE's `all` wire field (the tool name avoids shadowing the builtin).
    # Falsy all_guests collapses to None so it behaves exactly like omitting it (no all=0 leak).
    sel = {"vmid": vmid, "all": all_guests or None, "pool": pool, "exclude": exclude}
    plan = _plan("pve_backup_job_create", tgt,
                 lambda: plan_backup_job_create(job_id, schedule, storage,
                                                mode=mode, compress=compress,
                                                enabled=enabled, comment=comment, **sel))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_backup_job_create", tgt,
                    lambda: backup_job_create(api, job_id, schedule, storage,
                                             mode=mode, compress=compress,
                                             enabled=enabled, comment=comment, **sel),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_backup_job_update(job_id: str, schedule: str | None = None,
                          storage: str | None = None, mode: str | None = None,
                          compress: str | None = None, vmid: str | None = None,
                          enabled: bool | None = None, comment: str | None = None,
                          confirm: bool = False) -> dict:
    """MUTATION: update a PVE cluster backup job. Dry-run by default — captures current config.
    confirm=True to execute. Config-only; no impact on existing backups."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/backup/{job_id}"
    plan = _plan("pve_backup_job_update", tgt,
                 lambda: plan_backup_job_update(api, job_id, schedule=schedule,
                                                storage=storage, mode=mode,
                                                compress=compress, vmid=vmid,
                                                enabled=enabled, comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_backup_job_update", tgt,
                    lambda: backup_job_update(api, job_id, schedule=schedule,
                                             storage=storage, mode=mode, compress=compress,
                                             vmid=vmid, enabled=enabled, comment=comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_backup_job_delete(job_id: str, confirm: bool = False) -> dict:
    """MUTATION: delete a PVE cluster backup job. Dry-run by default — captures current config.
    confirm=True to execute. Schedule removed; existing backups are NOT deleted."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/backup/{job_id}"
    plan = _plan("pve_backup_job_delete", tgt,
                 lambda: plan_backup_job_delete(api, job_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_backup_job_delete", tgt,
                    lambda: backup_job_delete(api, job_id),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_replication_create(rep_id: str, rep_type: str, target: str,
                           schedule: str | None = None, rate: float | None = None,
                           disable: bool | None = None, comment: str | None = None,
                           confirm: bool = False) -> dict:
    """MUTATION: create a PVE replication job. Dry-run by default.
    rep_type is typically 'local'. confirm=True to execute."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/replication/{rep_id}"
    plan = _plan("pve_replication_create", tgt,
                 lambda: plan_replication_create(rep_id, rep_type, target,
                                                 schedule=schedule, rate=rate,
                                                 disable=disable, comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_replication_create", tgt,
                    lambda: replication_create(api, rep_id, rep_type, target,
                                              schedule=schedule, rate=rate,
                                              disable=disable, comment=comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_replication_update(rep_id: str, schedule: str | None = None,
                           rate: float | None = None, disable: bool | None = None,
                           comment: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: update a PVE replication job. Dry-run by default — captures current config.
    confirm=True to execute. Config-only; in-flight replication is not immediately disrupted."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/replication/{rep_id}"
    plan = _plan("pve_replication_update", tgt,
                 lambda: plan_replication_update(api, rep_id, schedule=schedule,
                                                 rate=rate, disable=disable,
                                                 comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_replication_update", tgt,
                    lambda: replication_update(api, rep_id, schedule=schedule,
                                              rate=rate, disable=disable, comment=comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_replication_delete(rep_id: str, confirm: bool = False) -> dict:
    """MUTATION: delete a PVE replication job. Dry-run by default — captures current config.
    confirm=True to execute. Replication ceases; existing replicated data is NOT removed."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/replication/{rep_id}"
    plan = _plan("pve_replication_delete", tgt,
                 lambda: plan_replication_delete(api, rep_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_replication_delete", tgt,
                    lambda: replication_delete(api, rep_id),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pbs_job_create(job_type: str, job_id: str, store: str | None = None,
                   schedule: str | None = None, ns: str | None = None,
                   comment: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create a PBS scheduled job. job_type = sync|verify|prune. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PBS_* config. Config-only; no existing data affected."""
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/config/{job_type}/{job_id}"
    plan = _plan("pbs_job_create", tgt,
                 lambda: plan_pbs_job_create(job_type, job_id, store=store,
                                             schedule=schedule, ns=ns, comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_job_create", tgt,
                    lambda: pbs_scheduled_job_create(pbs, job_type, job_id, store=store,
                                                     schedule=schedule, ns=ns,
                                                     comment=comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pbs_job_update(job_type: str, job_id: str, schedule: str | None = None,
                   ns: str | None = None, comment: str | None = None,
                   confirm: bool = False) -> dict:
    """MUTATION: update a PBS scheduled job. job_type = sync|verify|prune. Dry-run by default —
    captures current config. confirm=True to execute. Needs PROXIMO_PBS_* config."""
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/config/{job_type}/{job_id}"
    plan = _plan("pbs_job_update", tgt,
                 lambda: plan_pbs_job_update(pbs, job_type, job_id, schedule=schedule,
                                             ns=ns, comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_job_update", tgt,
                    lambda: pbs_scheduled_job_update(pbs, job_type, job_id,
                                                     schedule=schedule, ns=ns,
                                                     comment=comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pbs_job_delete(job_type: str, job_id: str, confirm: bool = False) -> dict:
    """MUTATION: delete a PBS scheduled job. job_type = sync|verify|prune. Dry-run by default —
    captures current config. confirm=True to execute. Schedule removed; backup data NOT deleted.
    Needs PROXIMO_PBS_* config."""
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/config/{job_type}/{job_id}"
    plan = _plan("pbs_job_delete", tgt,
                 lambda: plan_pbs_job_delete(pbs, job_type, job_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_job_delete", tgt,
                    lambda: pbs_scheduled_job_delete(pbs, job_type, job_id),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pbs_job_run(job_type: str, job_id: str, confirm: bool = False) -> dict:
    """MUTATION: trigger a PBS scheduled job immediately. job_type = sync|verify|prune.
    Dry-run by default. confirm=True to execute. Async — returns UPID.
    Needs PROXIMO_PBS_* config. Prune runs may delete snapshots per the retention policy."""
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/admin/{job_type}/{job_id}"
    plan = _plan("pbs_job_run", tgt,
                 lambda: plan_pbs_job_run(job_type, job_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_job_run", tgt,
                    lambda: pbs_scheduled_job_run(pbs, job_type, job_id),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@tool()
def pbs_realm_sync(realm: str, remove_vanished: bool | None = None,
                   dry_run: bool | None = None, scope: str | None = None,
                   confirm: bool = False) -> dict:
    """MUTATION: sync PBS auth realm (LDAP/AD) users. Dry-run by default.
    confirm=True to execute. Async — returns UPID. Needs PROXIMO_PBS_* config.
    remove_vanished=True also removes PBS users no longer in the directory."""
    _, pbs = _proximo_server._pbs()
    tgt = f"pbs/access/domains/{realm}"
    plan = _plan("pbs_realm_sync", tgt,
                 lambda: plan_pbs_realm_sync(realm,
                                             remove_vanished=remove_vanished,
                                             dry_run=dry_run, scope=scope))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_realm_sync", tgt,
                    lambda: pbs_realm_sync_op(pbs, realm,
                                              remove_vanished=remove_vanished,
                                              dry_run=dry_run, scope=scope),
                    mutation=True, outcome="submitted", detail={"confirmed": True})
