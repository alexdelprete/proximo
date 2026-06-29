"""Backup Schedules plane — PVE backup jobs, replication jobs, PBS scheduled jobs, realm sync.

Covers Plane B (PLAN + PROVE; no UNDO primitive — config is re-creatable after delete):
  - PVE cluster backup jobs     (/cluster/backup)
  - PVE replication jobs        (/cluster/replication)
  - PBS scheduled jobs          (/config/{type}  — type = sync|verify|prune)
  - PBS auth realm sync         (/access/domains/{realm}/sync)

VERIFIED live shapes: None — all endpoint shapes carry "Smoke-confirm:" comments.

Security posture:
  - All path components validated with \\Z-anchored regexes (trailing-newline bypass rejected).
  - PBS job type validated against a closed frozenset (no arbitrary string into URL path).
  - No snapshot primitive on this plane — plans declare re-creatable, NEVER imply undo.
  - RISK_LOW: schedule config only; existing backups/data are NOT touched by a delete.
"""

from __future__ import annotations

import re

from .backends import ProximoError
from .planning import RISK_LOW, RISK_MEDIUM, Plan

# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

# PVE backup job ID: path segment in /cluster/backup/{id}
# Smoke-confirm: exact accepted charset against a live PVE instance.
_JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")

# PVE replication job ID: typically "{vmid}/{slot}" (e.g. "101/0").
# Allow one slash to support the VMID/slot form; reject control chars + path traversal.
# Smoke-confirm: exact accepted form (digits only vs alpha allowed).
_REPLICATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_-]{0,63}\Z")

# PBS scheduled job types — documented PBS values; closed set (no arbitrary string into URL).
_VALID_PBS_JOB_TYPES = frozenset({"sync", "verify", "prune"})

# PBS scheduled job ID: path segment in /config/{type}/{id}
# Smoke-confirm: exact accepted charset against a live PBS instance.
_PBS_JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")

# PBS auth realm name: path segment in /access/domains/{realm}/sync
# Smoke-confirm: exact accepted charset against a live PBS instance.
_REALM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


def _check_job_id(job_id: str) -> str:
    # Do NOT strip — stripping defeats \\Z trailing-newline protection.
    s = str(job_id)
    if not _JOB_ID_RE.match(s):
        raise ProximoError(
            f"invalid PVE backup job ID: {job_id!r} "
            "(must start with alnum, then alnum/_/-, <=64 chars, no slash)"
        )
    return s


def _check_backup_selection(sel: dict) -> None:
    """Validate a vzdump backup-job guest-selection combination.

    PVE's selection modes are mutually exclusive — pass at most one of:
      * ``vmid``  — comma-separated guest IDs
      * ``all``   — back up every guest (bool)
      * ``pool``  — back up a resource pool
    ``exclude`` (comma-separated IDs) only filters the all-guests set, so it
    requires ``all``. PVE itself enforces that a job selects *something*; we do
    not pre-judge that here (avoids over-blocking a shape PVE may accept).
    """
    chosen = [name for name in ("vmid", "all", "pool") if sel.get(name)]
    if len(chosen) > 1:
        raise ProximoError(
            f"backup job selection is mutually exclusive: got {chosen}; "
            "pass at most one of vmid, all, pool"
        )
    if sel.get("exclude") and not sel.get("all"):
        raise ProximoError(
            "'exclude' only applies with all=True (it filters the all-guests set)"
        )


def _check_replication_id(rep_id: str) -> str:
    s = str(rep_id)
    if not _REPLICATION_ID_RE.match(s):
        raise ProximoError(
            f"invalid PVE replication job ID: {rep_id!r} "
            "(expected VMID/slot like '101/0'; no control chars)"
        )
    return s


def _check_pbs_job_type(job_type: str) -> str:
    if job_type not in _VALID_PBS_JOB_TYPES:
        raise ProximoError(
            f"invalid PBS job type: {job_type!r} "
            f"(expected one of {sorted(_VALID_PBS_JOB_TYPES)})"
        )
    return job_type


def _check_pbs_job_id(job_id: str) -> str:
    s = str(job_id)
    if not _PBS_JOB_ID_RE.match(s):
        raise ProximoError(
            f"invalid PBS scheduled job ID: {job_id!r} "
            "(must start with alnum, then alnum/_/-, <=64 chars)"
        )
    return s


def _check_realm(realm: str) -> str:
    s = str(realm)
    if not _REALM_RE.match(s):
        raise ProximoError(
            f"invalid PBS realm name: {realm!r} "
            "(must start with alnum, then alnum/._/-, <=64 chars, no slash)"
        )
    return s


# ---------------------------------------------------------------------------
# PVE Backup Job operations
# ---------------------------------------------------------------------------

def backup_job_list(api) -> dict:
    """List PVE cluster backup jobs and guests not covered by any backup job.

    GET /cluster/backup                     -> list of backup job dicts
    GET /cluster/backup-info/not-backed-up  -> list of guest dicts with no coverage

    Smoke-confirm: exact response field names and shapes for both endpoints.
    """
    jobs = api._get("/cluster/backup") or []
    unprotected = api._get("/cluster/backup-info/not-backed-up") or []
    return {"jobs": jobs, "unprotected_guests": unprotected}


def backup_job_get(api, job_id: str) -> dict:
    """Get one PVE cluster backup job config.

    GET /cluster/backup/{id}
    Smoke-confirm: exact response shape (schedule, storage, vmid list, mode, etc.).
    """
    _check_job_id(job_id)
    return api._get(f"/cluster/backup/{job_id}") or {}


def backup_job_create(api, job_id: str, schedule: str, storage: str, **kw) -> None:
    """Create a PVE cluster backup job.

    POST /cluster/backup
    Body: {id, schedule, storage, ...optional (mode, compress, vmid, all, pool,
           exclude, enabled, comment, ...)}
    Guest selection (vmid | all | pool) is mutually exclusive; exclude requires all.
    Live-proven vs real PVE 2026-06-28: all/pool/exclude accepted; bad combos rejected pre-flight.
    MUTATION — confirm-gated + audited at the server layer.
    """
    _check_job_id(job_id)
    _check_backup_selection(kw)
    data = {"id": job_id, "schedule": schedule, "storage": storage, **kw}
    # MUTATION — confirm-gated + audited at the server layer.
    api._post("/cluster/backup", {k: v for k, v in data.items() if v is not None})


def backup_job_update(api, job_id: str, **kw) -> None:
    """Update a PVE cluster backup job.

    PUT /cluster/backup/{id}
    Body: {schedule?, storage?, vmid?, mode?, compress?, enabled?, comment?, ...}
    Smoke-confirm: exact accepted body fields.
    MUTATION — confirm-gated + audited at the server layer.
    """
    _check_job_id(job_id)
    # MUTATION — confirm-gated + audited at the server layer.
    api._put(f"/cluster/backup/{job_id}", {k: v for k, v in kw.items() if v is not None})


def backup_job_delete(api, job_id: str) -> None:
    """Delete a PVE cluster backup job. Existing backups are NOT deleted — schedule only.

    DELETE /cluster/backup/{id}
    Smoke-confirm: response shape (null or task ID).
    MUTATION — confirm-gated + audited at the server layer.
    """
    _check_job_id(job_id)
    # MUTATION — confirm-gated + audited at the server layer.
    api._delete(f"/cluster/backup/{job_id}")


# ---------------------------------------------------------------------------
# PVE Replication operations
# ---------------------------------------------------------------------------

def replication_get(api, rep_id: str) -> dict:
    """Get one PVE replication job config.

    GET /cluster/replication/{id}
    Smoke-confirm: exact response shape (target, schedule, rate, disable, comment, ...).
    """
    _check_replication_id(rep_id)
    return api._get(f"/cluster/replication/{rep_id}") or {}


def replication_create(api, rep_id: str, rep_type: str, target: str, **kw) -> None:
    """Create a PVE replication job.

    POST /cluster/replication
    Body: {id, type, target, ...optional (schedule, rate, disable, comment)}
    'type' is typically 'local' (replicate to a node in the same PVE cluster).
    Smoke-confirm: exact accepted body fields and type values.
    MUTATION — confirm-gated + audited at the server layer.
    """
    _check_replication_id(rep_id)
    data = {"id": rep_id, "type": rep_type, "target": target, **kw}
    # MUTATION — confirm-gated + audited at the server layer.
    api._post("/cluster/replication", {k: v for k, v in data.items() if v is not None})


def replication_update(api, rep_id: str, **kw) -> None:
    """Update a PVE replication job.

    PUT /cluster/replication/{id}
    Body: {schedule?, rate?, disable?, comment?, ...}
    Smoke-confirm: exact accepted body fields.
    MUTATION — confirm-gated + audited at the server layer.
    """
    _check_replication_id(rep_id)
    # MUTATION — confirm-gated + audited at the server layer.
    api._put(f"/cluster/replication/{rep_id}", {k: v for k, v in kw.items() if v is not None})


def replication_delete(api, rep_id: str) -> None:
    """Delete a PVE replication job. Replication ceases; existing replicated data is NOT removed.

    DELETE /cluster/replication/{id}
    Smoke-confirm: response shape.
    MUTATION — confirm-gated + audited at the server layer.
    """
    _check_replication_id(rep_id)
    # MUTATION — confirm-gated + audited at the server layer.
    api._delete(f"/cluster/replication/{rep_id}")


# ---------------------------------------------------------------------------
# PBS Scheduled Job operations (PbsBackend)
# ---------------------------------------------------------------------------

def pbs_scheduled_job_get(pbs, job_type: str, job_id: str) -> dict:
    """Get one PBS scheduled job config.

    GET /config/{type}/{id}    (type = sync|verify|prune)
    Smoke-confirm: exact response shape and field names per job type.
    """
    job_type = _check_pbs_job_type(job_type)
    _check_pbs_job_id(job_id)
    return pbs._get(f"/config/{job_type}/{job_id}") or {}


def pbs_scheduled_jobs_list(pbs, job_type: str) -> list[dict]:
    """List all PBS scheduled jobs of the given type.

    GET /config/{type}   (type = sync|verify|prune)

    Returns a list of job config dicts; each has at minimum {id, store, schedule?, ...}.
    Smoke-confirm: exact response shape and field names per job type.
    """
    job_type = _check_pbs_job_type(job_type)
    return pbs._get(f"/config/{job_type}") or []


def pbs_scheduled_job_create(pbs, job_type: str, job_id: str, **kw) -> None:
    """Create a PBS scheduled job (sync/verify/prune).

    POST /config/{type}
    Body: {id, ...type-specific options (store, schedule, ns, keep-*, ...)}
    Smoke-confirm: exact accepted body fields per job type; id in body vs path segment.
    MUTATION — confirm-gated + audited at the server layer.
    """
    job_type = _check_pbs_job_type(job_type)
    _check_pbs_job_id(job_id)
    data = {"id": job_id, **kw}
    # MUTATION — confirm-gated + audited at the server layer.
    pbs._post(f"/config/{job_type}", {k: v for k, v in data.items() if v is not None})


def pbs_scheduled_job_update(pbs, job_type: str, job_id: str, **kw) -> None:
    """Update a PBS scheduled job.

    PUT /config/{type}/{id}
    Smoke-confirm: exact accepted body fields per job type.
    MUTATION — confirm-gated + audited at the server layer.
    """
    job_type = _check_pbs_job_type(job_type)
    _check_pbs_job_id(job_id)
    # MUTATION — confirm-gated + audited at the server layer.
    pbs._put(f"/config/{job_type}/{job_id}", {k: v for k, v in kw.items() if v is not None})


def pbs_scheduled_job_delete(pbs, job_type: str, job_id: str) -> None:
    """Delete a PBS scheduled job. Existing backups/synced data are NOT deleted.

    DELETE /config/{type}/{id}
    Smoke-confirm: response shape.
    MUTATION — confirm-gated + audited at the server layer.
    """
    job_type = _check_pbs_job_type(job_type)
    _check_pbs_job_id(job_id)
    # MUTATION — confirm-gated + audited at the server layer.
    pbs._delete(f"/config/{job_type}/{job_id}")


def pbs_scheduled_job_run(pbs, job_type: str, job_id: str) -> str:
    """Trigger a PBS scheduled job immediately. Returns a UPID (async task).

    POST /admin/{type}/{id}/run
    Smoke-confirm: exact path, whether body is required, and that response is a UPID string.
    MUTATION — confirm-gated + audited at the server layer.
    """
    job_type = _check_pbs_job_type(job_type)
    _check_pbs_job_id(job_id)
    # MUTATION — confirm-gated + audited at the server layer.
    return pbs._post(f"/admin/{job_type}/{job_id}/run") or ""


def pbs_realm_sync(pbs, realm: str, **kw) -> str:
    """Sync PBS auth realm (LDAP/AD) users. Returns a UPID (async task).

    POST /access/domains/{realm}/sync
    Body: {scope?, remove-vanished?, dry-run?}  (Smoke-confirm: exact field names and defaults)
    Smoke-confirm: exact path, body params, and UPID response shape.
    MUTATION — confirm-gated + audited at the server layer.
    """
    _check_realm(realm)
    data = {k: v for k, v in kw.items() if v is not None}
    # MUTATION — confirm-gated + audited at the server layer.
    return pbs._post(f"/access/domains/{realm}/sync", data) or ""


# ---------------------------------------------------------------------------
# Plan factories — PVE Backup Jobs
# ---------------------------------------------------------------------------

def plan_backup_job_create(job_id: str, schedule: str, storage: str, **kw) -> Plan:
    """Plan a PVE backup job creation (additive, LOW risk)."""
    _check_job_id(job_id)
    _check_backup_selection(kw)
    return Plan(
        action="pve_backup_job_create",
        target=f"cluster/backup/{job_id}",
        change=f"create PVE backup job {job_id!r}: schedule={schedule!r} storage={storage!r}",
        current={},
        blast_radius=["adds a new backup schedule (no existing data affected)"],
        risk=RISK_LOW,
        risk_reasons=["additive config — creates a new scheduled backup job"],
        note=(
            "No snapshot primitive on this plane. Deleting the job removes the schedule but "
            "does NOT delete existing backups. Re-create with pve_backup_job_create to restore."
        ),
    )


def plan_backup_job_update(api, job_id: str, **kw) -> Plan:
    """Plan a PVE backup job update. Reads current config for CAPTURE-or-declare honesty."""
    _check_job_id(job_id)
    current = backup_job_get(api, job_id)
    return Plan(
        action="pve_backup_job_update",
        target=f"cluster/backup/{job_id}",
        change=f"update PVE backup job {job_id!r}: {kw}",
        current=current,
        blast_radius=["modifies schedule/storage/filter for an existing backup job"],
        risk=RISK_LOW,
        risk_reasons=["config-only change — existing backups not affected"],
        note=(
            "No snapshot primitive on this plane. Current config captured above — "
            "re-apply it manually to revert."
        ),
    )


def plan_backup_job_delete(api, job_id: str) -> Plan:
    """Plan a PVE backup job deletion. Reads current config for CAPTURE-or-declare honesty."""
    _check_job_id(job_id)
    current = backup_job_get(api, job_id)
    return Plan(
        action="pve_backup_job_delete",
        target=f"cluster/backup/{job_id}",
        change=f"delete PVE backup job {job_id!r}",
        current=current,
        blast_radius=["removes the backup schedule; existing backups are NOT deleted"],
        risk=RISK_LOW,
        risk_reasons=["config-only change — deletes schedule, not existing backups"],
        note=(
            "No UNDO primitive on this plane. Current config captured above — "
            "re-create with pve_backup_job_create to restore the schedule."
        ),
    )


# ---------------------------------------------------------------------------
# Plan factories — PVE Replication
# ---------------------------------------------------------------------------

def plan_replication_create(rep_id: str, rep_type: str, target: str, **kw) -> Plan:
    """Plan a PVE replication job creation (additive, LOW risk)."""
    _check_replication_id(rep_id)
    return Plan(
        action="pve_replication_create",
        target=f"cluster/replication/{rep_id}",
        change=f"create PVE replication job {rep_id!r}: type={rep_type!r} target={target!r}",
        current={},
        blast_radius=["adds a new replication schedule (no existing data affected)"],
        risk=RISK_LOW,
        risk_reasons=["additive config — creates a new replication job"],
        note=(
            "No snapshot primitive on this plane. Deleting the job stops replication but "
            "does NOT remove existing replicated data on the target. "
            "Re-create with pve_replication_create to restore."
        ),
    )


def plan_replication_update(api, rep_id: str, **kw) -> Plan:
    """Plan a PVE replication job update. Reads current config for honesty."""
    _check_replication_id(rep_id)
    current = replication_get(api, rep_id)
    return Plan(
        action="pve_replication_update",
        target=f"cluster/replication/{rep_id}",
        change=f"update PVE replication job {rep_id!r}: {kw}",
        current=current,
        blast_radius=["modifies schedule/rate/target for an existing replication job"],
        risk=RISK_LOW,
        risk_reasons=["config-only change — in-flight replication not immediately disrupted"],
        note=(
            "No snapshot primitive on this plane. Current config captured above — "
            "re-apply it manually to revert."
        ),
    )


def plan_replication_delete(api, rep_id: str) -> Plan:
    """Plan a PVE replication job deletion. Reads current config for honesty."""
    _check_replication_id(rep_id)
    current = replication_get(api, rep_id)
    return Plan(
        action="pve_replication_delete",
        target=f"cluster/replication/{rep_id}",
        change=f"delete PVE replication job {rep_id!r}",
        current=current,
        blast_radius=[
            "removes the replication schedule; replication ceases after current cycle",
            "existing replicated data on the target is NOT automatically removed",
        ],
        risk=RISK_LOW,
        risk_reasons=["config-only change — stops future replication, no data loss"],
        note=(
            "No UNDO primitive on this plane. Current config captured above — "
            "re-create with pve_replication_create to restore."
        ),
    )


# ---------------------------------------------------------------------------
# Plan factories — PBS Scheduled Jobs
# ---------------------------------------------------------------------------

def plan_pbs_job_create(job_type: str, job_id: str, **kw) -> Plan:
    """Plan a PBS scheduled job creation (additive, LOW risk)."""
    job_type = _check_pbs_job_type(job_type)
    _check_pbs_job_id(job_id)
    return Plan(
        action="pbs_job_create",
        target=f"pbs/config/{job_type}/{job_id}",
        change=f"create PBS {job_type} job {job_id!r}: {kw}",
        current={},
        blast_radius=[f"adds a new PBS {job_type} scheduled job (no existing data affected)"],
        risk=RISK_LOW,
        risk_reasons=["additive config — creates a new PBS scheduled job"],
        note=(
            "No snapshot primitive on this plane. Deleting the job removes the schedule but "
            "does NOT delete existing backup data. Re-create with pbs_job_create to restore."
        ),
    )


def plan_pbs_job_update(pbs, job_type: str, job_id: str, **kw) -> Plan:
    """Plan a PBS scheduled job update. Reads current config for honesty."""
    job_type = _check_pbs_job_type(job_type)
    _check_pbs_job_id(job_id)
    current = pbs_scheduled_job_get(pbs, job_type, job_id)
    return Plan(
        action="pbs_job_update",
        target=f"pbs/config/{job_type}/{job_id}",
        change=f"update PBS {job_type} job {job_id!r}: {kw}",
        current=current,
        blast_radius=[f"modifies schedule/options for PBS {job_type} job {job_id!r}"],
        risk=RISK_LOW,
        risk_reasons=["config-only change — existing backup data not affected"],
        note=(
            "No snapshot primitive on this plane. Current config captured above — "
            "re-apply it manually to revert."
        ),
    )


def plan_pbs_job_delete(pbs, job_type: str, job_id: str) -> Plan:
    """Plan a PBS scheduled job deletion. Reads current config for honesty."""
    job_type = _check_pbs_job_type(job_type)
    _check_pbs_job_id(job_id)
    current = pbs_scheduled_job_get(pbs, job_type, job_id)
    return Plan(
        action="pbs_job_delete",
        target=f"pbs/config/{job_type}/{job_id}",
        change=f"delete PBS {job_type} job {job_id!r}",
        current=current,
        blast_radius=[
            "removes the PBS scheduled job; scheduled runs cease",
            "existing backups, snapshots, or synced data are NOT deleted",
        ],
        risk=RISK_LOW,
        risk_reasons=["config-only change — deletes schedule, not backup data"],
        note=(
            "No UNDO primitive on this plane. Current config captured above — "
            "re-create with pbs_job_create to restore the schedule."
        ),
    )


def plan_pbs_job_run(job_type: str, job_id: str) -> Plan:
    """Plan triggering a PBS scheduled job immediately (async, UPID)."""
    job_type = _check_pbs_job_type(job_type)
    _check_pbs_job_id(job_id)
    return Plan(
        action="pbs_job_run",
        target=f"pbs/admin/{job_type}/{job_id}",
        change=f"trigger PBS {job_type} job {job_id!r} immediately",
        current={},
        blast_radius=[
            f"starts a {job_type} run immediately (async task) — may consume I/O and CPU",
            "for prune jobs: may delete backup snapshots per the job's retention policy",
        ],
        risk=RISK_LOW,
        risk_reasons=["triggers the configured job now; prune may remove old snapshots per policy"],
        note=(
            "Async — returns a UPID. Use pve_task_wait to poll completion. "
            "Prune runs delete snapshots per the configured retention policy — not undoable."
        ),
    )


def plan_pbs_realm_sync(realm: str, **kw) -> Plan:
    """Plan syncing a PBS auth realm (LDAP/AD). Async, UPID."""
    _check_realm(realm)
    remove_vanished = bool(kw.get("remove_vanished") or kw.get("remove-vanished"))
    return Plan(
        action="pbs_realm_sync",
        target=f"pbs/access/domains/{realm}",
        change=(
            f"sync PBS auth realm {realm!r} from LDAP/AD"
            + (" (remove-vanished=true: DELETES users absent from the directory)"
               if remove_vanished else "")
        ),
        current={},
        blast_radius=[
            "adds/updates PBS users from the LDAP/AD directory",
            ("remove-vanished=true: ALSO removes PBS users not present in the directory"
             if remove_vanished else "remove-vanished not set: no user deletions"),
        ],
        risk=RISK_MEDIUM if remove_vanished else RISK_LOW,
        risk_reasons=(
            ["remove-vanished=true: deletes directory-absent PBS users (recoverable only by re-sync)"]
            if remove_vanished else ["user sync without remove-vanished — additive, no deletions"]
        ),
        note=(
            "Smoke-confirm: exact body params (remove-vanished, dry-run, scope) against a live PBS. "
            "Async — returns a UPID. Use pve_task_wait to poll completion."
        ),
    )
