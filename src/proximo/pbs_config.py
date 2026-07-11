"""Proximo PBS config + safety plane — datastore lifecycle, snapshot protection,
remote sync-source, and traffic-control.

Endpoints used by this module:

  Datastore lifecycle (/config/datastore):
    POST   /config/datastore             — create a datastore  (async worker → UPID)
    GET    /config/datastore/{name}      — read current config (CAPTURE)
    PUT    /config/datastore/{name}      — update datastore config
    DELETE /config/datastore/{name}      — detach or destroy   (async worker → UPID)

  Snapshot protection & notes (/admin/datastore/{store}/...):
    PUT    /admin/datastore/{store}/protected       — set/clear protected flag on a snapshot
    GET    /admin/datastore/{store}/notes           — read snapshot notes (CAPTURE)
    PUT    /admin/datastore/{store}/notes           — set snapshot notes
    PUT    /admin/datastore/{store}/change-owner    — reassign backup group owner

  Remote sync-source (/config/remote):
    POST   /config/remote                — create a remote (password secret)
    GET    /config/remote/{name}         — read current config WITHOUT password (CAPTURE)
    PUT    /config/remote/{name}         — update a remote
    DELETE /config/remote/{name}         — remove a remote + its credentials

  Traffic control (/config/traffic-control):
    GET    /config/traffic-control/{name} — detect create-vs-update (CAPTURE)
    POST   /config/traffic-control        — create a bandwidth-limit rule
    PUT    /config/traffic-control/{name} — update a bandwidth-limit rule
    DELETE /config/traffic-control/{name} — remove a bandwidth-limit rule

VERIFIED live (PBS 4.2, throwaway pbs-test datastore, 2026-06-26): datastore create (async worker
UPID → "submitted"), update, delete (real delete-datastore UPID); remote create/delete (auth-id is
the correct param; fingerprint must match PBS's SHA-256 regex; password redaction held — never in
the ledger); traffic-control create/delete (network accepts str or array; a GET on a NONEXISTENT
rule returns 400 not 404 — the upsert dispatch handles both). The destroy_data=True delete plan
(HIGH/irreversible) was verified on the PLAN path only — NEVER live-fired. Snapshot ops
(protected_set/notes_set/group_change_owner) remain Smoke-confirm — pbs-test had no backups to act
on. Remaining # Smoke-confirm: notes name the specific unverified field/param.

Security posture — secret handling:
  The remote 'password' field is a credential. It is UNCONDITIONALLY redacted:
  - Never appears in any plan factory (plan_remote_create / plan_remote_update have no
    'password' parameter).
  - Never appears in plan.change, plan.current, or any blast_radius string.
  - Never appears in the _audited() detail dict — only {"password": "[redacted]"} is logged.
  - The backend functions (remote_create / remote_update) receive the real password and
    pass it to the PBS API; the ledger never sees it.
  The TLS cert 'fingerprint' is PUBLIC data — it is NOT redacted and may appear in
  plans and the audit ledger for auditability.

EXCLUSION: PBS access management (acl / users / tokens) is deliberately NOT in this wave.
Access control is a distinct failure mode (access lockout rather than data destruction) and
belongs in its own focused PBS-access wave — mirroring how PVE access management lives in
dedicated access.py / access_users.py / access_governance.py modules.
"""

from __future__ import annotations

import httpx

from .backends import ProximoError
from .pbs import (
    PbsBackend,
    _check_backup_id,
    _check_backup_time,
    _check_backup_type,
    _check_namespace,
    _check_store,
)
from .planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM, Plan

# ---------------------------------------------------------------------------
# Validators (plane-specific)
# ---------------------------------------------------------------------------

def _check_datastore_path(path: str) -> str:
    """Validate a PBS datastore path — must be an absolute path, no traversal.

    Smoke-confirm: whether PBS accepts relative paths or only absolute.
    """
    s = str(path)
    if not s:
        raise ProximoError("datastore path must not be empty")
    if not s.startswith("/"):
        raise ProximoError(
            f"invalid datastore path: {path!r} (must be an absolute path starting with '/')"
        )
    for part in s.split("/"):
        if part == "..":
            raise ProximoError(
                f"invalid datastore path: {path!r} (path traversal '..' rejected)"
            )
    if any(c < " " or c == "\x7f" or ord(c) > 127 for c in s):
        raise ProximoError(
            f"invalid datastore path: {path!r} (control characters rejected)"
        )
    return s


# ---------------------------------------------------------------------------
# Secret redaction helper
# ---------------------------------------------------------------------------

def _remote_password_fingerprint() -> dict:
    """Unconditional redaction for PBS remote passwords — never store even a hash.

    Used by the server layer (never by plan factories — plan factories never receive the password).
    """
    return {"password": "[redacted]"}


def _strip_password(resp: object) -> object:
    """Defensively drop a 'password' key from a backend RESPONSE before it reaches the caller.

    PBS does not echo the credential back, but the _audited envelope returns the raw response as
    `result` — so if a PBS bug ever echoed it, this keeps it out of the client-visible return.
    """
    if isinstance(resp, dict):
        return {k: v for k, v in resp.items() if k != "password"}
    return resp


# ---------------------------------------------------------------------------
# Field-building helpers
# ---------------------------------------------------------------------------

def _datastore_schedule_fields(
    gc_schedule: str | None = None,
    prune_schedule: str | None = None,
    notification_mode: str | None = None,
    comment: str | None = None,
) -> dict:
    """Optional datastore config fields — shared by create/update backend calls and their plan-factory
    previews so the field list can't silently diverge.
    """
    fields: dict = {}
    if gc_schedule is not None:
        fields["gc-schedule"] = gc_schedule          # Smoke-confirm: hyphenated param name
    if prune_schedule is not None:
        fields["prune-schedule"] = prune_schedule    # Smoke-confirm
    if notification_mode is not None:
        fields["notification-mode"] = notification_mode  # Smoke-confirm
    if comment is not None:
        fields["comment"] = comment
    return fields


def _traffic_control_fields(
    rate_in: int | None = None,
    rate_out: int | None = None,
    network: str | None = None,
    burst_in: int | None = None,
    burst_out: int | None = None,
    timeframe: str | None = None,
    comment: str | None = None,
) -> dict:
    """Optional traffic-control rule fields — shared by traffic_control_upsert and
    plan_traffic_control_upsert so the field list can't silently diverge.
    """
    fields: dict = {}
    for py, api_k in [
        (rate_in, "rate-in"),       # Smoke-confirm: 'rate-in' param name
        (rate_out, "rate-out"),     # Smoke-confirm: 'rate-out' param name
        (network, "network"),
        (burst_in, "burst-in"),     # Smoke-confirm: 'burst-in' param name
        (burst_out, "burst-out"),   # Smoke-confirm: 'burst-out' param name
        (timeframe, "timeframe"),   # Smoke-confirm: 'timeframe' param name + accepted format
        (comment, "comment"),
    ]:
        if py is not None:
            fields[api_k] = py
    return fields


# ---------------------------------------------------------------------------
# Backend functions — raw PBS API calls
# ---------------------------------------------------------------------------

# ── Datastore lifecycle ──────────────────────────────────────────────────────

def datastore_get(api: PbsBackend, name: str) -> dict:
    """GET /config/datastore/{name} — read current datastore config.

    Smoke-confirm: response shape (expected {name, path, gc-schedule?, ...}).
    """
    name = _check_store(name)
    return api._get(f"/config/datastore/{name}") or {}


def datastore_create(
    api: PbsBackend,
    name: str,
    path: str,
    gc_schedule: str | None = None,
    prune_schedule: str | None = None,
    notification_mode: str | None = None,
    comment: str | None = None,
) -> object:
    """POST /config/datastore — create a new datastore.

    Returns a UPID (async worker task).
    Smoke-confirm: sync-vs-async (submitted is the safe default).
    Smoke-confirm: hyphenated param names (gc-schedule, prune-schedule, notification-mode).
    """
    name = _check_store(name)
    path = _check_datastore_path(path)
    data: dict = {
        "name": name,
        "path": path,
        **_datastore_schedule_fields(gc_schedule, prune_schedule, notification_mode, comment),
    }
    return api._post("/config/datastore", data)


def datastore_update(
    api: PbsBackend,
    name: str,
    gc_schedule: str | None = None,
    prune_schedule: str | None = None,
    notification_mode: str | None = None,
    comment: str | None = None,
) -> object:
    """PUT /config/datastore/{name} — update datastore config.

    Smoke-confirm: accepted body param names (hyphenated vs underscored).
    Smoke-confirm: whether a PUT with no fields succeeds or is rejected.
    """
    name = _check_store(name)
    data: dict = _datastore_schedule_fields(gc_schedule, prune_schedule, notification_mode, comment)
    return api._put(f"/config/datastore/{name}", data or None)


def datastore_delete(
    api: PbsBackend,
    name: str,
    destroy_data: bool = False,
    keep_job_configs: bool = False,
) -> object:
    """DELETE /config/datastore/{name} — detach or destroy a datastore.

    destroy_data=False: detaches the config; chunks remain on disk (re-addable).
    destroy_data=True:  PERMANENTLY DESTROYS all backup data in the datastore.

    Returns a UPID (async worker task).
    Smoke-confirm: destroy-data and keep-job-configs param names.
    Smoke-confirm: sync-vs-async (submitted is the safe default).
    """
    name = _check_store(name)
    params: dict = {}
    if destroy_data:
        params["destroy-data"] = 1        # Smoke-confirm: 'destroy-data' param name
    if keep_job_configs:
        params["keep-job-configs"] = 1    # Smoke-confirm: 'keep-job-configs' param name
    return api._delete(f"/config/datastore/{name}", params=params or None)


# ── Snapshot protection & notes ──────────────────────────────────────────────

def snapshot_protected_set(
    api: PbsBackend,
    store: str,
    backup_type: str,
    backup_id: str,
    backup_time: int,
    protected: bool,
    ns: str | None = None,
) -> object:
    """PUT /admin/datastore/{store}/protected — set or clear the protected flag on a snapshot.

    protected=True:  shields snapshot from pruning/GC.
    protected=False: SILENTLY re-enables pruning/GC — snapshot can now be auto-deleted.

    Smoke-confirm: exact endpoint path (may be /admin/datastore/{store}/snapshots with a
    different param structure on real PBS).
    Smoke-confirm: param names (backup-type, backup-id, backup-time, protected).
    """
    store = _check_store(store)
    backup_type = _check_backup_type(backup_type)   # type: ignore[assignment]
    backup_id = _check_backup_id(backup_id)         # type: ignore[assignment]
    backup_time = _check_backup_time(backup_time)
    ns = _check_namespace(ns)
    data: dict = {
        "backup-type": backup_type,    # Smoke-confirm: hyphenated
        "backup-id": backup_id,        # Smoke-confirm: hyphenated
        "backup-time": backup_time,    # Smoke-confirm: hyphenated
        "protected": protected,        # bool coerced by PbsBackend._form
    }
    if ns is not None:
        data["ns"] = ns
    # Smoke-confirm: exact path for setting protected flag
    return api._put(f"/admin/datastore/{store}/protected", data)


def snapshot_notes_get(
    api: PbsBackend,
    store: str,
    backup_type: str,
    backup_id: str,
    backup_time: int,
    ns: str | None = None,
) -> str | None:
    """GET /admin/datastore/{store}/notes — read current snapshot notes (for CAPTURE).

    Smoke-confirm: exact endpoint, query param names (backup-type, backup-id, backup-time).
    Smoke-confirm: response shape (expected string or dict with 'notes' key).
    """
    store = _check_store(store)
    backup_type = _check_backup_type(backup_type)   # type: ignore[assignment]
    backup_id = _check_backup_id(backup_id)         # type: ignore[assignment]
    backup_time = _check_backup_time(backup_time)
    ns = _check_namespace(ns)
    params: dict = {
        "backup-type": backup_type,    # Smoke-confirm
        "backup-id": backup_id,        # Smoke-confirm
        "backup-time": backup_time,    # Smoke-confirm
    }
    if ns is not None:
        params["ns"] = ns
    return api._get(f"/admin/datastore/{store}/notes", params=params)


def snapshot_notes_set(
    api: PbsBackend,
    store: str,
    backup_type: str,
    backup_id: str,
    backup_time: int,
    notes: str,
    ns: str | None = None,
) -> object:
    """PUT /admin/datastore/{store}/notes — set annotation on a snapshot.

    Smoke-confirm: exact endpoint path and body param names.
    """
    store = _check_store(store)
    backup_type = _check_backup_type(backup_type)   # type: ignore[assignment]
    backup_id = _check_backup_id(backup_id)         # type: ignore[assignment]
    backup_time = _check_backup_time(backup_time)
    ns = _check_namespace(ns)
    data: dict = {
        "backup-type": backup_type,    # Smoke-confirm
        "backup-id": backup_id,        # Smoke-confirm
        "backup-time": backup_time,    # Smoke-confirm
        "notes": notes,
    }
    if ns is not None:
        data["ns"] = ns
    # Smoke-confirm: exact path for setting snapshot notes
    return api._put(f"/admin/datastore/{store}/notes", data)


def group_change_owner(
    api: PbsBackend,
    store: str,
    backup_type: str,
    backup_id: str,
    new_owner: str,
    ns: str | None = None,
) -> object:
    """POST /admin/datastore/{store}/change-owner — reassign the backup group owner.

    VERIFIED live (PBS 4.2, 2026-06-26): POST (not PUT) — PUT returns 404; POST returns 200.
    Param names confirmed live: backup-type, backup-id, new-owner.
    """
    store = _check_store(store)
    backup_type = _check_backup_type(backup_type)   # type: ignore[assignment]
    backup_id = _check_backup_id(backup_id)         # type: ignore[assignment]
    ns = _check_namespace(ns)
    data: dict = {
        "backup-type": backup_type,    # VERIFIED live
        "backup-id": backup_id,        # VERIFIED live
        "new-owner": new_owner,        # VERIFIED live
    }
    if ns is not None:
        data["ns"] = ns
    # VERIFIED live (PBS 4.2, 2026-06-26): POST (not PUT)
    return api._post(f"/admin/datastore/{store}/change-owner", data)


# ── Remote sync-source ───────────────────────────────────────────────────────

def remotes_list(api: PbsBackend) -> list[dict]:
    """GET /config/remote — list all PBS remote sync-sources (passwords never returned).

    PBS design: the GET list response never includes passwords.
    Strips 'password' defensively from each entry anyway.  Fail-closed: if the response is not
    the expected list shape, refuse to return it rather than risk handing back an un-redacted
    payload (a non-list shape previously bypassed redaction entirely).
    Smoke-confirm: response shape — expected list of remote config dicts.
    Smoke-confirm: that password is absent from the list response.
    """
    data = api._get("/config/remote") or []
    if not isinstance(data, list):
        raise ProximoError(
            f"unexpected /config/remote response shape: {type(data).__name__} "
            "(expected a list) — refusing to return a response that hasn't been verified "
            "password-free"
        )
    out: list[dict] = []
    for item in data:
        stripped = _strip_password(item)
        if not isinstance(stripped, dict):
            raise ProximoError(
                f"unexpected /config/remote entry shape: {type(item).__name__} "
                "(expected a dict) — refusing to return a response that hasn't been "
                "verified password-free"
            )
        out.append(stripped)
    return out


def traffic_controls_list(api: PbsBackend) -> list[dict]:
    """GET /config/traffic-control — list all PBS traffic-control bandwidth rules.

    Smoke-confirm: response shape — expected list of traffic-control rule dicts.
    """
    return api._get("/config/traffic-control") or []


def remote_get(api: PbsBackend, name: str) -> dict:
    """GET /config/remote/{name} — read current remote config (CAPTURE; no password returned).

    PBS design: the GET response never includes the password.  Strip defensively anyway.
    Smoke-confirm: response shape and that password is absent.
    """
    name = _check_store(name)   # remote names follow same charset rules as datastore names
    data = api._get(f"/config/remote/{name}") or {}
    # Strip defensively — PBS should not return the password, but never trust it blindly.
    return {k: v for k, v in data.items() if k != "password"}


def remote_create(
    api: PbsBackend,
    name: str,
    host: str,
    auth_id: str,
    password: str,                # secret — NEVER logged; only reaches the PBS API here
    fingerprint: str | None = None,
    port: int | None = None,
    comment: str | None = None,
) -> object:
    """POST /config/remote — create a PBS remote sync-source.

    PASSWORD HANDLING: password is a secret credential.  It is passed to the API here and
    nowhere else.  The plan factories (plan_remote_create / plan_remote_update) have NO
    password parameter — the server layer uses _remote_password_fingerprint() for redaction.

    Smoke-confirm: auth-id vs authid param name, port param name.
    """
    name = _check_store(name)   # Smoke-confirm: whether remote names have the same char rules
    data: dict = {
        "name": name,
        "host": host,
        "auth-id": auth_id,     # Smoke-confirm: 'auth-id' vs 'authid' vs 'userid'
        "password": password,   # passes to PBS; never echoed back
    }
    if fingerprint is not None:
        data["fingerprint"] = fingerprint
    if port is not None:
        data["port"] = port     # Smoke-confirm: 'port' param name + accepted type (int vs str)
    if comment is not None:
        data["comment"] = comment
    return _strip_password(api._post("/config/remote", data))


def remote_update(
    api: PbsBackend,
    name: str,
    host: str | None = None,
    auth_id: str | None = None,
    password: str | None = None,   # secret — NEVER logged; only reaches PBS API here
    fingerprint: str | None = None,
    port: int | None = None,
    comment: str | None = None,
) -> object:
    """PUT /config/remote/{name} — update an existing PBS remote.

    PASSWORD HANDLING: if password is provided it is a secret; same policy as remote_create.
    Smoke-confirm: auth-id param name, whether partial PUT is accepted.
    """
    name = _check_store(name)
    data: dict = {}
    if host is not None:
        data["host"] = host
    if auth_id is not None:
        data["auth-id"] = auth_id   # Smoke-confirm
    if password is not None:
        data["password"] = password  # passes to PBS; never echoed back
    if fingerprint is not None:
        data["fingerprint"] = fingerprint
    if port is not None:
        data["port"] = port
    if comment is not None:
        data["comment"] = comment
    return _strip_password(api._put(f"/config/remote/{name}", data or None))


def remote_delete(api: PbsBackend, name: str) -> object:
    """DELETE /config/remote/{name} — remove a remote and its stored credentials.

    After deletion: any sync jobs referencing this remote break; re-add needs the password
    re-supplied.
    Smoke-confirm: response (expected null on success).
    """
    name = _check_store(name)
    return api._delete(f"/config/remote/{name}")


# ── Traffic control ──────────────────────────────────────────────────────────

def traffic_control_get(api: PbsBackend, name: str) -> dict | None:
    """GET /config/traffic-control/{name} — read a traffic-control rule (for CAPTURE/dispatch).

    Returns the rule dict if it exists, None-ish on 404.
    Smoke-confirm: endpoint path and response shape.
    """
    name = _check_store(name)
    return api._get(f"/config/traffic-control/{name}")


def traffic_control_upsert(
    api: PbsBackend,
    name: str,
    rate_in: int | None = None,
    rate_out: int | None = None,
    network: str | None = None,
    burst_in: int | None = None,
    burst_out: int | None = None,
    timeframe: str | None = None,
    comment: str | None = None,
) -> object:
    """Create (POST) or update (PUT) a traffic-control rule — dispatch by reading existence first.

    Dispatch logic:
      - GET /config/traffic-control/{name}: if rule exists → PUT (update).
      - 404 (doesn't exist) → POST (create) with name in body.
      - Other GET error → raise (don't silently proceed with wrong verb).

    Smoke-confirm: /config/traffic-control endpoint, create-vs-update dispatch behavior,
    rate-in/rate-out/burst-in/burst-out/timeframe param names, whether 'name' is in POST body.
    """
    name = _check_store(name)
    data: dict = _traffic_control_fields(
        rate_in, rate_out, network, burst_in, burst_out, timeframe, comment
    )

    # Dispatch: detect create-vs-update.
    # VERIFIED live (PBS 4.2): a GET on a NONEXISTENT traffic-control rule returns 400, not 404 —
    # so both 400 and 404 mean "doesn't exist → create". Any OTHER exception (including a bare
    # AttributeError from a malformed response) is inconclusive and must abort rather than
    # silently assume absence — dispatching a CREATE against a rule that might already exist
    # would be exactly the false-safety this project forbids (see plan_restore in backup.py).
    try:
        existing = api._get(f"/config/traffic-control/{name}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (400, 404):
            existing = None
        else:
            raise

    if existing:
        # Rule exists → update
        return api._put(f"/config/traffic-control/{name}", data or None)
    else:
        # Rule doesn't exist → create
        data["name"] = name   # Smoke-confirm: whether name is in POST body for traffic-control
        return api._post("/config/traffic-control", data)


def traffic_control_delete(api: PbsBackend, name: str) -> object:
    """DELETE /config/traffic-control/{name} — remove a bandwidth-limit rule.

    After deletion: backups run unthrottled on the affected network.
    Smoke-confirm: response (expected null on success).
    """
    name = _check_store(name)
    return api._delete(f"/config/traffic-control/{name}")


# ---------------------------------------------------------------------------
# PLAN factories — PURE (or PURE-ish for CAPTURE-or-declare)
# ---------------------------------------------------------------------------

# ── Datastore lifecycle ──────────────────────────────────────────────────────

def plan_datastore_create(
    name: str,
    path: str,
    gc_schedule: str | None = None,
    prune_schedule: str | None = None,
    notification_mode: str | None = None,
    comment: str | None = None,
) -> Plan:
    """Preview creating a PBS datastore.  PURE — no API call.

    RISK_MEDIUM: additive, but a misconfigured path may claim or conflict with existing data.
    PBS datastore creation is an async worker task → outcome="submitted" (not "ok").
    No rollback primitive: declare irreversible.
    Smoke-confirm: sync-vs-async behavior of POST /config/datastore.
    """
    name = _check_store(name)
    path = _check_datastore_path(path)
    config_parts: dict = {
        "path": path,
        **_datastore_schedule_fields(gc_schedule, prune_schedule, notification_mode, comment),
    }
    return Plan(
        action="pbs_datastore_create",
        target=f"config/datastore/{name}",
        change=f"create PBS datastore '{name}' at {path!r}: {config_parts}",
        current={},
        blast_radius=[
            f"creates new datastore '{name}' at {path!r} (additive)",
            "a misconfigured path can claim storage that belongs to another datastore or "
            "conflict with a mounted filesystem",
            "no PBS snapshot primitive — no automatic rollback; to undo, delete the datastore "
            "(pbs_datastore_delete with destroy_data=True is irreversible)",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "additive but persistent config change; a bad path silently wastes or conflicts with disk",
            "undoing creation requires deletion — which can be HIGH risk (destroy_data=True)",
        ],
        note=(
            "PBS datastore creation is an async worker task (UPID) — outcome is 'submitted', not 'ok'. "
            "Smoke-confirm: sync-vs-async behavior of POST /config/datastore."
        ),
    )


def plan_datastore_update(
    api: PbsBackend,
    name: str,
    gc_schedule: str | None = None,
    prune_schedule: str | None = None,
    notification_mode: str | None = None,
    comment: str | None = None,
) -> Plan:
    """Preview updating a PBS datastore config.  CAPTURE-or-declare.

    CAPTURE: reads GET /config/datastore/{name} → plan.current; on failure → complete=False.
    RISK_MEDIUM: changing gc-schedule, prune-schedule, or notification-mode affects retention
    and backup behavior cluster-wide.
    No rollback primitive: declare irreversible; revert by re-applying the captured config.
    Smoke-confirm: GET /config/datastore/{name} response shape.
    """
    name = _check_store(name)
    current: dict = {}
    complete = True
    note_capture = ""
    try:
        data = api._get(f"/config/datastore/{name}") or {}
        # Strip any unexpected secret fields defensively (datastores don't have secrets, but be safe).
        current = {k: v for k, v in data.items() if k != "password"}
    except Exception:
        complete = False
        note_capture = " Could not capture current datastore config — no guided revert available."

    changes: dict = _datastore_schedule_fields(gc_schedule, prune_schedule, notification_mode, comment)

    return Plan(
        action="pbs_datastore_update",
        target=f"config/datastore/{name}",
        change=f"update PBS datastore '{name}' config: {changes}",
        current=current,
        blast_radius=[
            f"PBS datastore '{name}' configuration",
            "changing gc-schedule or prune-schedule affects data retention — backups outside the "
            "new schedule may be pruned or GC'd sooner than expected",
            "notification-mode changes affect alerting (missed alerts on backup failures)",
            "no PBS snapshot primitive — revert by re-applying the captured config with "
            "pbs_datastore_update",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "changing gc-schedule / prune-schedule can accelerate data deletion by retention jobs",
            "synchronous config edit but retention-impacting",
        ],
        complete=complete,
        note=(
            "Revert by re-applying the captured config with pbs_datastore_update. "
            "Smoke-confirm: GET /config/datastore/{name} response field names."
            + note_capture
        ),
    )


def plan_datastore_delete(
    name: str,
    destroy_data: bool = False,
    keep_job_configs: bool = False,
) -> Plan:
    """Preview deleting a PBS datastore.  PURE — no API call.

    RISK IS CONDITIONAL ON destroy_data:
      destroy_data=False → RISK_MEDIUM: detaches the datastore config; the backup CHUNKS
        REMAIN ON DISK and the datastore is re-addable to recover.
      destroy_data=True  → RISK_HIGH:  PERMANENTLY DESTROYS ALL backup data in the
        datastore '{name}' — no recovery possible.

    PBS datastore deletion is an async worker task → outcome="submitted".
    No rollback primitive — declare irreversible.
    Smoke-confirm: sync-vs-async behavior + destroy-data / keep-job-configs param names.
    """
    name = _check_store(name)
    if destroy_data:
        return Plan(
            action="pbs_datastore_delete",
            target=f"config/datastore/{name}",
            change=(
                f"DELETE datastore '{name}' WITH destroy_data=True — "
                "PERMANENTLY DESTROYS ALL backup data in this datastore"
            ),
            current={},
            blast_radius=[
                f"datastore '{name}': ALL backups permanently destroyed — no recovery",
                "destroy_data=True deletes the datastore config AND all backup data on disk",
                "this operation is IRREVERSIBLE — there is no undo",
                "sync jobs and backup jobs referencing this datastore break immediately",
            ],
            risk=RISK_HIGH,
            risk_reasons=[
                f"destroy_data=True: ALL backups in datastore '{name}' are permanently destroyed",
                "irreversible — no recovery possible once the worker task completes",
            ],
            note=(
                "No undo: destroy_data=True permanently deletes all backup data in this datastore. "
                "PBS worker task (UPID) — outcome is 'submitted'. "
                "Smoke-confirm: destroy-data param name + sync-vs-async behavior."
            ),
        )
    else:
        return Plan(
            action="pbs_datastore_delete",
            target=f"config/datastore/{name}",
            change=(
                f"detach datastore '{name}' config (destroy_data=False — "
                "backup data REMAINS ON DISK, datastore is re-addable)"
            ),
            current={},
            blast_radius=[
                f"removes the datastore config for '{name}'",
                "backup data REMAINS ON DISK — re-add the datastore to recover access",
                "sync jobs and backup jobs referencing this datastore break until re-added",
            ],
            risk=RISK_MEDIUM,
            risk_reasons=[
                "removes the PBS config entry — backups referencing this store break immediately",
                "data remains on disk and is recoverable by re-adding the datastore "
                "(contrast destroy_data=True which is RISK_HIGH and permanent)",
            ],
            note=(
                "Data is NOT deleted when destroy_data=False — the datastore can be re-added "
                "to restore access. PBS worker task (UPID) — outcome is 'submitted'. "
                "Smoke-confirm: destroy-data / keep-job-configs param names."
            ),
        )


# ── Snapshot protection & notes ──────────────────────────────────────────────

def plan_snapshot_protected_set(
    store: str,
    backup_type: str,
    backup_id: str,
    backup_time: int,
    protected: bool,
    ns: str | None = None,
) -> Plan:
    """Preview setting or clearing the protected flag on a snapshot.  PURE — no API call.

    RISK IS CONDITIONAL ON protected — polarity is the OPPOSITE of the flag:
      protected=False → RISK_HIGH: SILENTLY re-enables pruning/GC of this snapshot.
        This snapshot can now be auto-deleted by a prune job or GC run.
        Blast: "removes prune/GC protection — this recovery point can now be auto-deleted."
      protected=True  → RISK_LOW: shields the snapshot from pruning and GC.
        Protective — adds a safety shield.

    No PBS snapshot primitive — re-apply to revert; never implies a rollback.
    Smoke-confirm: exact PUT path + param names for the protected flag.
    """
    store = _check_store(store)
    backup_type = _check_backup_type(backup_type)  # type: ignore[assignment]
    backup_id = _check_backup_id(backup_id)        # type: ignore[assignment]
    backup_time = _check_backup_time(backup_time)
    ns = _check_namespace(ns)

    ns_note = f" in namespace '{ns}'" if ns else ""
    snapshot_desc = (
        f"{backup_type}/{backup_id}@{backup_time}{ns_note} in datastore '{store}'"
    )

    if not protected:
        return Plan(
            action="pbs_snapshot_protected_set",
            target=f"pbs/{store}/{backup_type}/{backup_id}@{backup_time}/protected",
            change=f"CLEAR protection on {snapshot_desc} (protected=False)",
            current={},
            blast_radius=[
                f"removes prune/GC protection from {snapshot_desc}",
                "this recovery point can now be auto-deleted by a prune job or GC run",
                "a scheduled prune or GC may immediately delete this snapshot if it falls "
                "outside the configured retention policy",
            ],
            risk=RISK_HIGH,
            risk_reasons=[
                "protected=False SILENTLY re-enables pruning/GC of this snapshot",
                "the snapshot can now be auto-deleted — potentially immediately if a prune/GC "
                "job runs before you review",
                "no undo once the snapshot is auto-deleted",
            ],
            note=(
                "Clearing protection makes a snapshot eligible for automatic deletion. "
                "Review the retention policy and ensure this recovery point is not needed "
                "before clearing its protection. "
                "Revert by re-setting protected=True with pbs_snapshot_protected_set. "
                "Smoke-confirm: PUT path and param names for the protected flag."
            ),
        )
    else:
        return Plan(
            action="pbs_snapshot_protected_set",
            target=f"pbs/{store}/{backup_type}/{backup_id}@{backup_time}/protected",
            change=f"SET protection on {snapshot_desc} (protected=True)",
            current={},
            blast_radius=[
                f"shields {snapshot_desc} from pruning and GC",
                "the snapshot is protected from automatic deletion — it will not be removed "
                "by prune jobs or GC regardless of the retention policy",
            ],
            risk=RISK_LOW,
            risk_reasons=[
                "protected=True shields the snapshot from pruning/GC — a protective, additive op",
                "does not delete or modify any backup data",
            ],
            note=(
                "Protection can be cleared later with protected=False (that is RISK_HIGH). "
                "Smoke-confirm: PUT path and param names for the protected flag."
            ),
        )


def plan_snapshot_notes_set(
    api: PbsBackend,
    store: str,
    backup_type: str,
    backup_id: str,
    backup_time: int,
    notes: str,
    ns: str | None = None,
) -> Plan:
    """Preview setting a note/annotation on a snapshot.  CAPTURE-or-declare.

    CAPTURE: reads GET /admin/datastore/{store}/notes → plan.current; on failure → complete=False.
    RISK_LOW: annotation only — does not affect backup data, retention, or protection.
    Smoke-confirm: GET notes endpoint path + param names (backup-type, backup-id, backup-time).
    """
    store = _check_store(store)
    backup_type = _check_backup_type(backup_type)  # type: ignore[assignment]
    backup_id = _check_backup_id(backup_id)        # type: ignore[assignment]
    backup_time = _check_backup_time(backup_time)
    ns = _check_namespace(ns)

    current: dict = {}
    complete = True
    note_capture = ""
    try:
        current_notes = snapshot_notes_get(api, store, backup_type, backup_id, backup_time, ns)
        if current_notes is not None:
            current = {"notes": current_notes}
    except Exception:
        complete = False
        note_capture = " Could not capture current notes — no guided revert available."

    ns_note = f" in namespace '{ns}'" if ns else ""
    snapshot_desc = f"{backup_type}/{backup_id}@{backup_time}{ns_note} in datastore '{store}'"

    return Plan(
        action="pbs_snapshot_notes_set",
        target=f"pbs/{store}/{backup_type}/{backup_id}@{backup_time}/notes",
        change=f"set notes on {snapshot_desc}",
        current=current,
        blast_radius=[
            f"annotation on {snapshot_desc} — does not affect backup data or retention",
        ],
        risk=RISK_LOW,
        risk_reasons=["annotation only — no backup data, retention, or protection is changed"],
        complete=complete,
        note=(
            "Revert by re-applying the captured notes with pbs_snapshot_notes_set. "
            "Smoke-confirm: GET /admin/datastore/{store}/notes endpoint and param names."
            + note_capture
        ),
    )


def plan_group_change_owner(
    store: str,
    backup_type: str,
    backup_id: str,
    new_owner: str,
    ns: str | None = None,
) -> Plan:
    """Preview changing the owner of a PBS backup group.  PURE — no API call.

    RISK_MEDIUM: the new owner controls who can prune/delete this backup group.
    Declaring: "the new owner controls deletion/prune of this group."
    No PBS snapshot primitive — no automatic rollback; revert by re-assigning the owner.
    Smoke-confirm: PUT /admin/datastore/{store}/change-owner path + new-owner param name.
    """
    store = _check_store(store)
    backup_type = _check_backup_type(backup_type)  # type: ignore[assignment]
    backup_id = _check_backup_id(backup_id)        # type: ignore[assignment]
    ns = _check_namespace(ns)

    ns_note = f" in namespace '{ns}'" if ns else ""
    group_desc = f"{backup_type}/{backup_id}{ns_note} in datastore '{store}'"

    return Plan(
        action="pbs_group_change_owner",
        target=f"pbs/{store}/{backup_type}/{backup_id}/owner",
        change=f"change owner of backup group {group_desc} → '{new_owner}'",
        current={},
        blast_radius=[
            f"backup group {group_desc}: ownership reassigned to '{new_owner}'",
            f"the new owner '{new_owner}' now controls deletion and prune of this group",
            "the previous owner loses those permissions immediately",
            "no PBS snapshot primitive — revert by re-assigning the owner back",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            f"reassigns ownership: '{new_owner}' gains prune/delete authority over the group",
            "access control change — immediately effective; no undo without a second change",
        ],
        note=(
            "Revert by re-assigning the owner back with pbs_group_change_owner. "
            "Smoke-confirm: PUT /admin/datastore/{store}/change-owner path and 'new-owner' "
            "param name vs 'owner'."
        ),
    )


# ── Remote sync-source ───────────────────────────────────────────────────────

def plan_remote_create(
    name: str,
    host: str,
    auth_id: str,
    fingerprint: str | None = None,
    port: int | None = None,
    comment: str | None = None,
) -> Plan:
    """Preview creating a PBS remote.  PURE — no API call.

    PASSWORD NEVER ENTERS THIS FUNCTION.  The server layer handles password redaction
    via _remote_password_fingerprint() before calling this factory.

    RISK_MEDIUM: creates a persistent credential-bearing remote entry.
    The cert fingerprint is PUBLIC and may appear in plans/logs.
    No rollback primitive — revert by deleting the remote (pbs_remote_delete).
    Smoke-confirm: POST /config/remote param names (auth-id vs authid, port).
    """
    name = _check_store(name)   # Smoke-confirm: charset rules for remote names
    config_parts: dict = {"host": host, "auth-id": auth_id}
    if fingerprint is not None:
        config_parts["fingerprint"] = fingerprint  # PUBLIC — may appear in plan
    if port is not None:
        config_parts["port"] = port
    if comment is not None:
        config_parts["comment"] = comment
    return Plan(
        action="pbs_remote_create",
        target=f"config/remote/{name}",
        change=f"create PBS remote '{name}': {config_parts}",
        current={},
        blast_radius=[
            f"creates remote '{name}' pointing to host '{host}' — credential entry stored in PBS",
            "a sync job using this remote can pull data from the remote PBS instance",
            "misconfigured host/auth-id can silently fail sync jobs",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "creates a credential-bearing remote entry — persists until explicitly deleted",
            "grants PBS the ability to connect to the specified host with the given credentials",
        ],
        note=(
            "Remote password is UNCONDITIONALLY redacted — only {\"password\":\"[redacted]\"} "
            "appears in plans and the audit ledger. The cert fingerprint is PUBLIC and is NOT "
            "redacted. "
            "Revert by deleting the remote with pbs_remote_delete. "
            "Smoke-confirm: POST /config/remote param names (auth-id vs authid, port)."
        ),
    )


def plan_remote_update(
    api: PbsBackend,
    name: str,
    host: str | None = None,
    auth_id: str | None = None,
    fingerprint: str | None = None,
    port: int | None = None,
    comment: str | None = None,
) -> Plan:
    """Preview updating a PBS remote.  CAPTURE-or-declare.

    PASSWORD NEVER ENTERS THIS FUNCTION.  Password handling is in the server layer.

    CAPTURE: reads GET /config/remote/{name} → plan.current (PBS omits the password;
    we strip defensively). On read failure → complete=False + honest note.
    RISK_MEDIUM: updating credentials or host can break sync jobs.
    The cert fingerprint is PUBLIC and may appear in plans/logs.
    Smoke-confirm: PUT /config/remote/{name} param names.
    """
    name = _check_store(name)
    current: dict = {}
    complete = True
    note_capture = ""
    try:
        # remote_get already strips 'password' defensively
        current = remote_get(api, name)
    except Exception:
        complete = False
        note_capture = " Could not capture current remote config — no guided revert available."

    changes: dict = {}
    if host is not None:
        changes["host"] = host
    if auth_id is not None:
        changes["auth-id"] = auth_id
    if fingerprint is not None:
        changes["fingerprint"] = fingerprint   # PUBLIC — may appear in plan
    if port is not None:
        changes["port"] = port
    if comment is not None:
        changes["comment"] = comment
    # NOTE: 'password' is intentionally absent here — it is never a plan-factory parameter.

    return Plan(
        action="pbs_remote_update",
        target=f"config/remote/{name}",
        change=f"update PBS remote '{name}': {changes}",
        current=current,
        blast_radius=[
            f"PBS remote '{name}': credential/host config changed",
            "any sync jobs using this remote will use the updated config immediately",
            "a wrong host or auth-id breaks all sync jobs referencing this remote",
            "no PBS snapshot primitive — revert by re-applying the captured config",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "updating remote credentials or host breaks sync jobs if misconfigured",
            "takes effect immediately — no staged rollout",
        ],
        complete=complete,
        note=(
            "Remote password is UNCONDITIONALLY redacted if provided — only "
            "{\"password\":\"[redacted]\"} appears in plans and the audit ledger. "
            "The cert fingerprint is PUBLIC and is NOT redacted. "
            "Revert by re-applying the captured config with pbs_remote_update. "
            "Smoke-confirm: GET /config/remote/{name} response shape (password absent)."
            + note_capture
        ),
    )


def plan_remote_delete(name: str) -> Plan:
    """Preview deleting a PBS remote.  PURE — no API call.

    RISK_MEDIUM: removes the remote entry and its stored credentials.
    After deletion: re-add requires the password re-supplied; sync jobs break immediately.
    No rollback primitive — re-create with pbs_remote_create to recover.
    Smoke-confirm: DELETE /config/remote/{name} response shape.
    """
    name = _check_store(name)
    return Plan(
        action="pbs_remote_delete",
        target=f"config/remote/{name}",
        change=f"delete PBS remote '{name}' and its stored credentials",
        current={},
        blast_radius=[
            f"removes remote '{name}' and its stored credentials from PBS",
            "any sync jobs referencing this remote break immediately",
            "re-adding the remote requires the password to be re-supplied",
            "the credential entry is deleted from PBS — it cannot be retrieved",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            f"removes the credential-bearing remote entry '{name}' — sync jobs break immediately",
            "recoverable only by re-creating with pbs_remote_create (password must be re-supplied)",
        ],
        note=(
            "Revert by re-creating the remote with pbs_remote_create. "
            "Smoke-confirm: DELETE /config/remote/{name} response shape."
        ),
    )


# ── Traffic control ──────────────────────────────────────────────────────────

def plan_traffic_control_upsert(
    api: PbsBackend,
    name: str,
    rate_in: int | None = None,
    rate_out: int | None = None,
    network: str | None = None,
    burst_in: int | None = None,
    burst_out: int | None = None,
    timeframe: str | None = None,
    comment: str | None = None,
) -> Plan:
    """Preview creating or updating a PBS traffic-control rule.  CAPTURE-or-declare.

    Detects create-vs-update by reading GET /config/traffic-control/{name}:
      - Rule exists  → update path (MEDIUM: changing rate limits can throttle/unthrottle backups).
      - 404 / absent → create path (LOW: additive only).
      - Other error  → create path assumed; complete=False + note.

    A too-low rate-in or rate-out throttles backups to a crawl — note it in the blast radius.
    No rollback primitive: revert by re-applying captured config or by deleting the rule.
    Smoke-confirm: /config/traffic-control endpoint, create-vs-update dispatch,
    rate-in / rate-out / burst-in / burst-out / timeframe param names.
    """
    name = _check_store(name)
    current: dict = {}
    complete = True
    is_update = False
    note_capture = ""

    try:
        data = api._get(f"/config/traffic-control/{name}")
        if data:
            is_update = True
            current = dict(data)
    except httpx.HTTPStatusError as e:
        # VERIFIED live (PBS 4.2): a nonexistent rule GET returns 400 (not 404) — both are the
        # normal "doesn't exist yet → create" case, NOT an uncertain state.
        if e.response.status_code in (400, 404):
            is_update = False   # Normal: rule doesn't exist yet → create path
        else:
            is_update = False
            complete = False
            note_capture = (
                f" Could not verify traffic-control rule existence "
                f"(HTTP {e.response.status_code}) — assuming create. Verify manually."
            )
    except Exception:
        # Other errors (including mock backends that raise generically)
        is_update = False
        complete = False
        note_capture = (
            " Could not read traffic-control rule config — assuming create path. "
            "No guided revert available."
        )

    changes: dict = _traffic_control_fields(
        rate_in, rate_out, network, burst_in, burst_out, timeframe, comment
    )

    throttle_note = ""
    if rate_in is not None or rate_out is not None:
        throttle_note = (
            " Note: a too-low rate throttles backups to a crawl "
            "(Smoke-confirm: rate units — bytes/s, KB/s, or MB/s)."
        )

    if is_update:
        return Plan(
            action="pbs_traffic_control_upsert",
            target=f"config/traffic-control/{name}",
            change=f"update traffic-control rule '{name}': {changes}",
            current=current,
            blast_radius=[
                f"PBS traffic-control rule '{name}': bandwidth limits changed",
                "affects backup and restore throughput on the matched network",
                "a too-low rate throttles backups to a crawl; a too-high rate (or removal of "
                "limit) can saturate the network",
                "no PBS snapshot primitive — revert by re-applying the captured config with "
                "pbs_traffic_control_upsert",
            ],
            risk=RISK_MEDIUM,
            risk_reasons=[
                f"modifies bandwidth throttling for rule '{name}' — incorrect limits can "
                "throttle backups or saturate the network",
            ],
            complete=complete,
            note=(
                "Revert by re-applying the captured config with pbs_traffic_control_upsert. "
                "Smoke-confirm: create-vs-update dispatch + rate-in/burst-in/timeframe param names."
                + throttle_note + note_capture
            ),
        )
    else:
        return Plan(
            action="pbs_traffic_control_upsert",
            target=f"config/traffic-control/{name}",
            change=f"create traffic-control rule '{name}': {changes}",
            current=current,
            blast_radius=[
                f"creates new bandwidth-throttling rule '{name}' (additive — no existing rule changed)",
                "a too-low rate-in/rate-out will throttle PBS backups to a crawl",
                "no effect on other traffic-control rules",
            ],
            risk=RISK_LOW,
            risk_reasons=[
                "additive — creates a new traffic-control rule; no existing config is modified",
            ],
            complete=complete,
            note=(
                "Revert by deleting the rule with pbs_traffic_control_delete. "
                "Smoke-confirm: create-vs-update dispatch + rate-in/burst-in/timeframe param names."
                + throttle_note + note_capture
            ),
        )


def plan_traffic_control_delete(name: str) -> Plan:
    """Preview deleting a PBS traffic-control rule.  PURE — no API call.

    RISK_MEDIUM: removes a bandwidth limit — backups run unthrottled on the affected network
    after deletion (network saturation is possible).
    No rollback primitive: re-create with pbs_traffic_control_upsert to restore limits.
    Smoke-confirm: DELETE /config/traffic-control/{name} endpoint + response shape.
    """
    name = _check_store(name)
    return Plan(
        action="pbs_traffic_control_delete",
        target=f"config/traffic-control/{name}",
        change=f"delete traffic-control rule '{name}' — backups run unthrottled afterward",
        current={},
        blast_radius=[
            f"removes bandwidth-throttling rule '{name}'",
            "backups and restores on the matched network run unthrottled after deletion",
            "re-create with pbs_traffic_control_upsert to restore limits",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "removes a bandwidth limit — backups run unthrottled; network saturation is possible "
            "if the underlying network is shared",
            "recoverable by re-creating the rule",
        ],
        note=(
            "Revert by re-creating the rule with pbs_traffic_control_upsert. "
            "Smoke-confirm: DELETE /config/traffic-control/{name} endpoint."
        ),
    )
