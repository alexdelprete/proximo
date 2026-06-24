"""Proximo MCP server.

Exposes Proxmox management (REST API) and in-container exec (ssh+pct) as MCP tools.

Verified 2026-06-07 against the official `mcp` Python SDK (FastMCP): import path,
`@mcp.tool()` decorator, type-hinted params, and dict returns are current (v1.x).

Ethical spine:
- In-container exec (ct_*) is OFF by default — API-only is the safe default; enable with PROXIMO_ENABLE_EXEC.
- Every tool call is audited *with its real outcome* (errors recorded, not assumed "ok").
- Every mutating tool (pve_guest_power, ct_exec, ct_psql) is confirm-gated.
- The CTID allowlist is enforced fail-closed in the exec backend.
- Secrets are never read or logged here.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import __version__
from .access import (
    access_acl_list,
    access_overbroad_grants,
    access_roles_list,
    access_tokens_list,
    access_users_list,
    acl_modify,
    plan_acl_modify,
    plan_token_create,
    plan_token_revoke,
    token_create,
    token_revoke,
)
from .access_governance import (
    plan_realm_create,
    plan_realm_delete,
    plan_realm_update,
    plan_role_create,
    plan_role_delete,
    plan_role_update,
    plan_tfa_delete,
    realm_create,
    realm_delete,
    realm_get,
    realm_update,
    realms_list,
    role_create,
    role_delete,
    role_update,
    tfa_delete,
    tfa_get,
    tfa_list,
)
from .access_users import (
    group_create,
    group_delete,
    group_get,
    group_update,
    groups_list,
    plan_group_create,
    plan_group_delete,
    plan_group_update,
    plan_user_create,
    plan_user_delete,
    plan_user_update,
    user_create,
    user_delete,
    user_get,
    user_update,
)
from .audit import AuditLedger, find_rotation_archive, looks_like_head, open_ledger
from .backends import ApiBackend, ExecBackend, ProximoError
from .backup import (
    backup_delete,
    backup_list,
    plan_backup,
    plan_backup_delete,
    plan_restore,
    restore_guest,
    vzdump_backup,
)
from .cloudinit import (
    capture_cloudinit_undo,
    cloudinit_get,
    cloudinit_set,
    plan_cloudinit_set,
    plan_template_convert,
    template_convert,
)
from .cluster_ops import (
    cluster_resources,
    cluster_status,
    guest_migrate,
    ha_groups_list,
    ha_resource_add,
    ha_resource_remove,
    ha_resources_list,
    ha_rule_create,
    ha_rule_delete,
    ha_rule_update,
    ha_rules_list,
    plan_ha_resource_add,
    plan_ha_resource_remove,
    plan_ha_rule_create,
    plan_ha_rule_delete,
    plan_ha_rule_update,
    plan_migrate,
)
from .config import ProximoConfig
from .config_edit import (
    guest_config_get,
    guest_config_revert,
    guest_config_set,
    plan_config_revert,
    plan_config_set,
)
from .diagnose import diagnose_container, diagnose_node
from .disk_ops import (
    disk_move,
    disk_resize,
    plan_disk_move,
    plan_disk_resize,
)
from .doctor import doctor_check
from .firewall import (
    alias_create,
    alias_delete,
    alias_list,
    alias_update,
    firewall_options_get,
    firewall_options_set,
    firewall_rule_add,
    firewall_rule_remove,
    firewall_rule_update,
    firewall_rules_list,
    firewall_set_enabled,
    ipset_create,
    ipset_delete,
    ipset_entry_add,
    ipset_entry_remove,
    ipset_list,
    plan_alias_create,
    plan_alias_delete,
    plan_alias_update,
    plan_firewall_options_set,
    plan_firewall_rule_add,
    plan_firewall_rule_remove,
    plan_firewall_rule_update,
    plan_firewall_set_enabled,
    plan_ipset_create,
    plan_ipset_delete,
    plan_ipset_entry_add,
    plan_ipset_entry_remove,
    plan_security_group_create,
    plan_security_group_delete,
    security_group_create,
    security_group_delete,
    security_groups_list,
)
from .network import (
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
from .observability import (
    node_certificates_info,
    node_dns_get,
    node_journal,
    node_rrddata,
    node_service_control,
    node_service_status,
    node_services_list,
    node_subscription,
    node_syslog,
    plan_node_service_control,
)
from .pbs import (
    PbsBackend,
    PbsConfig,
)
from .pbs import (
    datastore_list as pbs_datastore_list_op,
)
from .pbs import (
    datastore_status as pbs_datastore_status_op,
)
from .pbs import (
    gc_start as pbs_gc_start_op,
)
from .pbs import (
    gc_status as pbs_gc_status_op,
)
from .pbs import (
    namespace_create as pbs_namespace_create_op,
)
from .pbs import (
    namespace_delete as pbs_namespace_delete_op,
)
from .pbs import (
    namespace_list as pbs_namespace_list_op,
)
from .pbs import (
    plan_gc_start as pbs_plan_gc_start,
)
from .pbs import (
    plan_namespace_create as pbs_plan_namespace_create,
)
from .pbs import (
    plan_namespace_delete as pbs_plan_namespace_delete,
)
from .pbs import (
    plan_prune as pbs_plan_prune,
)
from .pbs import (
    plan_snapshot_delete as pbs_plan_snapshot_delete,
)
from .pbs import (
    plan_verify_start as pbs_plan_verify_start,
)
from .pbs import (
    prune as pbs_prune_op,
)
from .pbs import (
    snapshot_delete as pbs_snapshot_delete_op,
)
from .pbs import (
    snapshots_list as pbs_snapshots_list_op,
)
from .pbs import (
    verify_start as pbs_verify_start_op,
)
from .planning import (
    Plan,
    command_fingerprint,
    plan_exec,
    plan_power,
    plan_psql,
    plan_rollback,
    plan_snapshot_create,
    plan_snapshot_delete,
    sql_fingerprint,
    undo_snapname,
)
from .provisioning import (
    clone_guest,
    create_container,
    create_vm,
    delete_guest,
    plan_clone,
    plan_create,
    plan_delete,
)
from .storage import (
    content_delete,
    plan_content_delete,
    plan_storage_download,
    storage_content,
    storage_download_url,
    storage_status,
)
from .storage_admin import (
    plan_storage_create,
    plan_storage_delete,
    plan_storage_update,
    storage_config_get,
    storage_config_list,
    storage_create,
    storage_delete,
    storage_update,
)
from .tasks_pools import (
    plan_pool_create,
    plan_pool_delete,
    plan_pool_update,
    plan_task_stop,
    pool_create,
    pool_delete,
    pool_get,
    pool_update,
    pools_list,
    task_log,
    task_stop,
    tasks_list,
    wait_for_task,
)

BANNER = (
    "Proximo — the ethical Proxmox MCP\n"
    '  "Win the crowd and you will win your freedom."  ·  Strength and honor.\n'
)

mcp = FastMCP("proximo")
# FastMCP leaves the low-level Server.version=None, so the `initialize` handshake would advertise the
# MCP SDK's version. Set Proximo's own version instead, so clients see the real server version.
mcp._mcp_server.version = __version__


@lru_cache(maxsize=1)
def _svc() -> tuple[ProximoConfig, ApiBackend, ExecBackend, AuditLedger]:
    """Lazily build config + backends (no import-time env dependency; testable)."""
    cfg = ProximoConfig.from_env()
    return cfg, ApiBackend(cfg), ExecBackend(cfg), open_ledger(cfg)


@lru_cache(maxsize=1)
def _pbs() -> tuple[PbsConfig, PbsBackend]:
    """Lazily build the PBS backend — only when a pbs_* tool is called.

    Separate service from the PVE host: needs PROXIMO_PBS_* env (fails loud if unset).
    PBS ops still record to the SAME tamper-evident ledger via _audited/_plan (_svc's
    AuditLedger) so PROVE remains one coherent chain across PVE and PBS actions.
    """
    cfg = PbsConfig.from_env()
    return cfg, PbsBackend(cfg)


def _audited(action: str, target: str, fn: Callable[[], Any], *,
             mutation: bool = False, outcome: str = "ok", detail: dict | None = None) -> Any:
    """Run fn, then audit the REAL outcome. On exception, record the error and re-raise.

    `outcome` defaults to "ok" (synchronous completion). Async ops that only *start* a task pass
    outcome="submitted" so the ledger never claims an in-flight task is done.

    For mutation calls (mutation=True) the return is a SYMMETRIC envelope:
        {"status": <outcome>, "result": <raw fn() return>}
    where ``status`` equals the ``outcome`` recorded to the ledger — so a caller can uniformly
    read ``resp["status"]`` and it is always honest (never "ok" for an async/submitted op).

    Read calls (mutation=False) pass the raw fn() return through unchanged — no envelope.
    """
    _, _, _, audit = _svc()
    try:
        result = fn()
    except Exception as e:
        audit.record(action, target=target, mutation=mutation, outcome="error",
                     detail={**(detail or {}), "error": type(e).__name__})
        raise
    audit.record(action, target=target, mutation=mutation, outcome=outcome, detail=detail)
    if mutation:
        return {"status": outcome, "result": result}
    return result


def _record_plan(plan: Plan) -> None:
    """Write the previewed plan (incl. the live state it was based on) to the tamper-evident ledger,
    with outcome="planned". This is the PLAN->PROVE weld: a verified chain shows the exact preview."""
    _, _, _, audit = _svc()
    audit.record(
        plan.action, target=plan.target, mutation=True, outcome="planned",
        detail={"change": plan.change, "risk": plan.risk, "risk_reasons": plan.risk_reasons,
                "blast_radius": plan.blast_radius, "current": plan.current,
                "affected": plan.affected, "complete": plan.complete},
    )


def _plan(action: str, target: str, build: Callable[[], Plan]) -> Plan:
    """Build a plan and record it — MANDATORY before any mutation (no plan, no mutation).

    Called on BOTH paths: the dry-run (confirm=False) returns it; the execute path (confirm=True)
    runs it first so every mutation is preceded by a recorded "planned" entry — a one-shot confirm
    cannot bypass the preview. If building the plan fails (e.g. plan_power's live read raises),
    audit the failed probe and re-raise; never mutate without a recorded plan.
    """
    _, _, _, audit = _svc()
    try:
        plan = build()
    except Exception as e:
        audit.record(action, target=target, mutation=True, outcome="error",
                     detail={"error": type(e).__name__, "phase": "planning"})
        raise
    # The server tool name is AUTHORITATIVE for the ledger: stamp it onto the plan so the "planned"
    # entry pairs with the later "submitted"/"ok" entry under ONE action (PROVE coherence) — a plan_*
    # helper's internal label can never drift the audit trail (and shared helpers like plan_create,
    # used by both pve_create_container and pve_create_vm, record under the right tool each time).
    plan.action = action
    _record_plan(plan)
    return plan


def _wait_task(api: ApiBackend, upid: str, node: str | None = None,
               timeout: int = 120, interval: int = 2) -> dict:
    """Poll a Proxmox task to completion. Snapshot ops are async; the auto-undo path must wait for
    the snapshot to actually finish before mutating. Raises if the task fails or times out."""
    deadline = time.monotonic() + timeout
    while True:
        st = api.task_status(upid, node)
        if st.get("status") == "stopped":
            # Strict: only an explicit "OK" passes. A stopped task that reports no exitstatus is
            # treated as failure (fail-closed), not silently assumed successful.
            exit_ = st.get("exitstatus")
            if exit_ != "OK":
                raise ProximoError(f"task {upid} did not finish OK: {exit_!r}")
            return st
        if time.monotonic() >= deadline:
            raise ProximoError(f"task {upid} timed out after {timeout}s")
        time.sleep(interval)


def _auto_undo(action: str, target: str, api: ApiBackend, vmid: str,
               detail: dict, kind: str = "lxc", node: str | None = None) -> dict:
    """Take a labeled undo snapshot and WAIT for it. On success returns the undo-point dict; on
    failure returns an {"status": "blocked:undo_unavailable"} dict (and audits it) — the caller MUST NOT
    mutate when unavailable (fail-closed: no net, no risky act)."""
    _, _, _, audit = _svc()
    snapname = undo_snapname()
    try:
        upid = api.snapshot_create(vmid, snapname, kind=kind, node=node,
                                   description="proximo auto-undo before mutation")
        _wait_task(api, upid, node=node)
    except Exception as e:
        audit.record(action, target=target, mutation=True, outcome="blocked:undo_unavailable",
                     detail={**detail, "error": type(e).__name__})
        return {
            "status": "blocked:undo_unavailable",
            "message": ("Requested an undo snapshot but it could not be created/completed (the "
                        "container's storage may not support snapshots). Command NOT run "
                        "(fail-closed). Re-run without snapshot=True to proceed unprotected."),
            "error": type(e).__name__,
        }
    audit.record(action, target=target, mutation=True, outcome="undo_point",
                 detail={"snapshot": snapname, "task": upid})
    return {"snapshot": snapname, "task": upid,
            "revert": f"pve_rollback vmid={vmid} snapname={snapname}",
            "note": ("undo points are NOT auto-pruned — they accumulate and consume storage; "
                     "delete with pve_snapshot_delete when no longer needed.")}


def _blocked_allowlist(action: str, target: str, detail: dict | None = None,
                       *, mutation: bool = True) -> dict:
    """Refuse + audit a container op whose CTID isn't on the allowlist (fail-closed), as a clean dict
    — checked at the server layer BEFORE any snapshot/exec, so a forbidden CTID never gets touched.
    `mutation` must reflect the GATED tool's true class so blocked reads don't ledger as mutations."""
    _, _, _, audit = _svc()
    audit.record(action, target=target, mutation=mutation, outcome="blocked:allowlist", detail=detail)
    return {"status": "blocked:allowlist",
            "message": f"CTID {target} is not permitted by the allowlist (fail-closed)."}


def _exec_disabled(action: str, target: str, detail: dict | None = None,
                   *, mutation: bool = True) -> dict:
    """In-container exec is off by default (safe). Refuse + audit; explain how to opt in.
    `mutation` must reflect the GATED tool's true class so blocked reads don't ledger as mutations."""
    _, _, _, audit = _svc()
    audit.record(action, target=target, mutation=mutation, outcome="blocked:exec_disabled", detail=detail)
    return {
        "status": "blocked:exec_disabled",
        "message": ("In-container exec is disabled (safe default: API-only). It grants near-root on the "
                    "PVE host; enable deliberately with PROXIMO_ENABLE_EXEC=1."),
    }


# --- Management (REST API, read) ---

@mcp.tool()
def pve_node_status(node: str | None = None) -> dict:
    """Health and resource status of a Proxmox node."""
    cfg, api, _, _ = _svc()
    return _audited("pve_node_status", node or cfg.node, lambda: api.node_status(node))


@mcp.tool()
def pve_list_guests(node: str | None = None) -> list[dict]:
    """List all VMs and LXC containers on a node, with state."""
    cfg, api, _, _ = _svc()
    return _audited("pve_list_guests", node or cfg.node, lambda: api.list_guests(node))


@mcp.tool()
def pve_guest_status(vmid: str, kind: str = "lxc", node: str | None = None) -> dict:
    """Status/config of one guest (kind = 'lxc' or 'qemu')."""
    _, api, _, _ = _svc()
    return _audited("pve_guest_status", f"{kind}/{vmid}", lambda: api.guest_status(vmid, kind, node))


# --- Management (REST API, MUTATION — confirm-gated) ---

@mcp.tool()
def pve_guest_power(
    vmid: str, action: str, kind: str = "lxc", node: str | None = None, confirm: bool = False
) -> dict:
    """MUTATION: start/stop/reboot/shutdown a guest.

    Dry-run by default: without confirm=True you get a PLAN — the exact change, the guest's live
    state, blast radius, and risk (with no-op detection) — recorded to the ledger. Re-call with
    confirm=True to execute. The plan is recorded on BOTH paths: even a one-shot confirm=True call
    records its plan before mutating — no plan, no mutation.
    """
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}:{action}"
    plan = _plan("pve_guest_power", target, lambda: plan_power(api, vmid, action, kind, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    # PVE guest power is task-backed (POST .../status/{action} returns a UPID) — async, like the
    # identical-shape node_service_control. Record "submitted", never "ok": the ledger must not claim
    # the guest stopped/started when only the task was accepted.
    return _audited("pve_guest_power", target, lambda: api.guest_power(vmid, action, kind, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


# --- Snapshots / UNDO (REST API). Create/rollback/delete are ASYNC -> return a task UPID. ---

@mcp.tool()
def pve_snapshot_list(vmid: str, kind: str = "lxc", node: str | None = None) -> list[dict]:
    """List a guest's snapshots (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_snapshot_list", f"{kind}/{vmid}", lambda: api.snapshot_list(vmid, kind, node))


@mcp.tool()
def pve_snapshot_create(vmid: str, snapname: str, kind: str = "lxc", node: str | None = None,
                        description: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create a snapshot (a restore point). Dry-run by default; confirm=True to execute.
    Async — returns the task UPID; poll pve_task_status. Needs snapshot-capable storage (ZFS/BTRFS/LVM-thin)."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}:{snapname}"
    plan = _plan("pve_snapshot_create", target, lambda: plan_snapshot_create(vmid, snapname, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_snapshot_create", target,
                    lambda: api.snapshot_create(vmid, snapname, kind, node, description),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_rollback(vmid: str, snapname: str, kind: str = "lxc", node: str | None = None,
                 confirm: bool = False) -> dict:
    """MUTATION (DESTRUCTIVE): roll a guest back to a snapshot — discards ALL changes since it.
    Dry-run by default (the PLAN spells out the blast radius); confirm=True to execute. Async -> UPID."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}:{snapname}"
    plan = _plan("pve_rollback", target, lambda: plan_rollback(api, vmid, snapname, kind, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_rollback", target,
                    lambda: api.snapshot_rollback(vmid, snapname, kind, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_snapshot_delete(vmid: str, snapname: str, kind: str = "lxc", node: str | None = None,
                        force: bool = False, confirm: bool = False) -> dict:
    """MUTATION: delete a snapshot (removes a restore point). Dry-run by default; confirm=True to execute.
    Async -> UPID."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}:{snapname}"
    plan = _plan("pve_snapshot_delete", target, lambda: plan_snapshot_delete(vmid, snapname, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_snapshot_delete", target,
                    lambda: api.snapshot_delete(vmid, snapname, kind, node, force),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_task_status(upid: str, node: str | None = None) -> dict:
    """Status of an async Proxmox task (running/stopped + exit status) — poll snapshot/rollback ops (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_task_status", upid, lambda: api.task_status(upid, node))


# --- In-container exec (ssh -> pct) — MUTATION-CAPABLE, confirm-gated ---

@mcp.tool()
def ct_exec(ctid: str, command: list[str], snapshot: bool = False, confirm: bool = False) -> dict:
    """Run a command inside an LXC (ssh -> pct exec). MUTATION-CAPABLE.

    Dry-run by default: without confirm=True you get a PLAN — the command plus a heuristic
    read-vs-write / destructive-pattern classification (advisory only) — recorded to the ledger.
    Re-call with confirm=True to execute. Disabled unless PROXIMO_ENABLE_EXEC is set (safe default
    is API-only). Allowlist-scoped (fail-closed) and audited.

    snapshot=True (UNDO): take an auto-undo snapshot first and WAIT for it; if it can't be made
    (e.g. storage doesn't support snapshots) the command is NOT run (fail-closed). On success the
    result carries an `undo_point` you can revert with pve_rollback.
    """
    cfg, api, exec_, _ = _svc()
    # Audit completeness is the default; PROXIMO_LEDGER_REDACT records a command fingerprint instead
    # of the argv (which can carry secrets, e.g. `--password ...`) — see audit.py + README.
    detail = command_fingerprint(command) if cfg.redact_ledger else {"command": command}
    if not cfg.enable_exec:
        return _exec_disabled("ct_exec", str(ctid), detail)
    if not cfg.ct_permitted(ctid):
        return _blocked_allowlist("ct_exec", str(ctid), detail)
    plan = _plan("ct_exec", str(ctid), lambda: plan_exec(ctid, command, redact=cfg.redact_ledger))
    if not confirm:
        return {"status": "plan", "auto_snapshot": snapshot, **plan.as_dict()}

    undo_point = None
    if snapshot:
        undo = _auto_undo("ct_exec", str(ctid), api, ctid, detail)
        if undo.get("status") == "blocked:undo_unavailable":
            return undo  # fail-closed: command NOT run
        undo_point = undo

    def _do() -> dict:
        r = exec_.run(ctid, command)
        out = {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr}
        if undo_point:
            out["undo_point"] = undo_point
        return out

    return _audited("ct_exec", str(ctid), _do, mutation=True,
                    detail={**detail, "confirmed": True, "undo": bool(undo_point)})


@mcp.tool()
def ct_psql(ctid: str, sql: str, db: str = "postgres", snapshot: bool = False,
            confirm: bool = False) -> dict:
    """Run SQL via psql inside a container (as the db OS user). MUTATION-CAPABLE.

    Dry-run by default: without confirm=True you get a PLAN — the SQL plus a heuristic
    read/DML/DDL classification (advisory only) — recorded to the ledger. Re-call with
    confirm=True to execute.

    snapshot=True (UNDO): take an auto-undo snapshot first and WAIT for it; if it can't be made the
    SQL is NOT run (fail-closed). On success the result carries an `undo_point` (revert via pve_rollback).
    """
    cfg, api, exec_, _ = _svc()
    # Audit completeness is the default; PROXIMO_LEDGER_REDACT records a fingerprint instead of
    # the body (which can carry secrets/PII) — see audit.py + README.
    detail = {"db": db, **(sql_fingerprint(sql) if cfg.redact_ledger else {"sql": sql})}
    if not cfg.enable_exec:
        return _exec_disabled("ct_psql", str(ctid), detail)
    if not cfg.ct_permitted(ctid):
        return _blocked_allowlist("ct_psql", str(ctid), detail)
    plan = _plan("ct_psql", str(ctid), lambda: plan_psql(ctid, sql, db=db, redact=cfg.redact_ledger))
    if not confirm:
        return {"status": "plan", "auto_snapshot": snapshot, **plan.as_dict()}

    undo_point = None
    if snapshot:
        undo = _auto_undo("ct_psql", str(ctid), api, ctid, detail)
        if undo.get("status") == "blocked:undo_unavailable":
            return undo  # fail-closed: SQL NOT run
        undo_point = undo

    def _do() -> dict:
        r = exec_.psql(ctid, sql, db=db)
        out = {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr}
        if undo_point:
            out["undo_point"] = undo_point
        return out

    return _audited("ct_psql", str(ctid), _do, mutation=True,
                    detail={**detail, "confirmed": True, "undo": bool(undo_point)})


# --- In-container (read) ---

@mcp.tool()
def ct_logs(ctid: str, unit: str, lines: int = 50) -> dict:
    """Tail journalctl for a systemd unit inside a container (read-only)."""
    cfg, _, exec_, _ = _svc()
    detail = {"unit": unit, "lines": lines}
    if not cfg.enable_exec:
        return _exec_disabled("ct_logs", str(ctid), detail, mutation=False)
    if not cfg.ct_permitted(ctid):
        return _blocked_allowlist("ct_logs", str(ctid), detail, mutation=False)

    def _do() -> dict:
        r = exec_.logs(ctid, unit, lines=lines)
        return {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr}

    return _audited("ct_logs", str(ctid), _do, detail=detail)


@mcp.tool()
def ct_diagnose(ctid: str, kind: str = "lxc", node: str | None = None) -> dict:
    """READ-ONLY: gather 'what's broken' evidence for a container — API status + a fixed read-only
    in-container battery (failed units, disk, recent errors, memory, listening ports) + advisory flags.

    No mutation, no confirm. The in-container probes need PROXIMO_ENABLE_EXEC and the CTID allowlist
    (same as ct_logs); with exec off it returns the API-only part and discloses the skipped probes."""
    cfg, api, exec_, _ = _svc()
    target = f"{kind}/{ctid}"
    if cfg.enable_exec and not cfg.ct_permitted(ctid):
        return _blocked_allowlist("ct_diagnose", str(ctid), mutation=False)
    use_exec = exec_ if cfg.enable_exec else None
    return _audited("ct_diagnose", target, lambda: diagnose_container(api, use_exec, ctid, kind, node))


@mcp.tool()
def pve_diagnose(node: str | None = None) -> dict:
    """READ-ONLY: gather node health evidence — status + storage usage + recent failed tasks + flags."""
    _, api, _, _ = _svc()
    return _audited("pve_diagnose", node or "node", lambda: diagnose_node(api, node))


@mcp.tool()
def pve_doctor() -> dict:
    """READ-ONLY preflight: check API connectivity + the calling token's effective permissions, and
    report what this token CAN and CANNOT do — with the privilege + role to grant for each gap. Run
    this FIRST after install to verify your config/token before wiring Proximo into an MCP client."""
    _, api, _, _ = _svc()
    return _audited("pve_doctor", "preflight", lambda: doctor_check(api), mutation=False)


@mcp.tool()
def audit_verify(expected_head: str | None = None) -> dict:
    """Verify the tamper-evident audit ledger's hash chain — PROVE the log is intact.

    Pass `expected_head` (the head() value you pinned off-box) to also catch tail
    truncation, a forged tail-append, or a full file replacement — a forward walk
    alone can't see those. Falls back to PROXIMO_AUDIT_EXPECTED_HEAD when omitted.
    """
    cfg, _, _, audit = _svc()
    pin = expected_head if expected_head is not None else cfg.expected_head
    if pin is not None:
        # Normalize a copy-pasted head (case-insensitive hexdigest; strip stray spaces/newline) the
        # same way config does — a blank/whitespace value becomes "unpinned", not a caller error.
        pin = pin.strip().lower() or None
    if pin is not None and not looks_like_head(pin):
        # A genuinely malformed pin is a CALLER error, not tamper — raise clearly instead of
        # letting it fall through to a "head mismatch" that cries wolf.
        raise ProximoError(
            f"invalid expected_head: {pin!r} (must be a 64-char hex head() value)"
        )
    v = audit.verify(expected_head=pin)
    # When nothing is pinned, the forward walk can't see tail truncation / forged append / wipe —
    # nudge the operator to anchor the head off-box (the strong guarantee), so the feature isn't
    # silently unused. No nudge once a pin is in effect.
    hint = None if pin is not None else (
        "not pinned against tail attacks: set PROXIMO_AUDIT_EXPECTED_HEAD (or pass expected_head=) "
        "to the current 'head' value, stored off-box, to detect tail truncation / forged append / "
        "full wipe — the off-box anchor is the strong guarantee."
    )
    # A pinned "head mismatch" with the chain otherwise intact is byte-identical whether it's a tail
    # attack or a keyed-default upgrade that rotated the head. If a rotation archive sits beside the
    # ledger, say so — the stderr migration warning is often swallowed by MCP stdio clients.
    rotation_hint = None
    if not v.ok and v.broken_at is None and pin is not None:
        archive = find_rotation_archive(audit.path)
        if archive:
            rotation_hint = (
                "a keyed-default migration archive sits beside this ledger "
                f"({os.path.basename(archive)!r}). If you upgraded Proximo since you pinned, this "
                "'head mismatch' is the expected migration head-rotation — re-pin "
                "PROXIMO_AUDIT_EXPECTED_HEAD to the 'head' value above. If you did NOT just upgrade, "
                "treat this as a genuine tail-attack signal and investigate."
            )
    return {
        "ok": v.ok,
        "entries": v.entries,
        "broken_at_line": v.broken_at,
        "reason": v.reason,
        "head": audit.head(),
        "expected_head": pin,
        "keyed": audit.keyed,
        "hint": hint,
        "rotation_hint": rotation_hint,
    }


# --- Backup & restore (REST API, async -> UPID) ---

@mcp.tool()
def pve_backup(vmid: str, storage: str, mode: str = "snapshot", compress: str = "zstd",
               kind: str = "lxc", node: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: back up a guest with vzdump. Dry-run by default; confirm=True to execute.
    mode: snapshot (online, brief) | suspend | stop (HALTS the guest). Async — returns a task UPID."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}"
    plan = _plan("pve_backup", target, lambda: plan_backup(vmid, storage, mode, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_backup", target,
                    lambda: vzdump_backup(api, vmid, storage, mode, compress, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_backup_list(storage: str, node: str | None = None) -> list[dict]:
    """List backup archives in a storage (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_backup_list", storage, lambda: backup_list(api, storage, node))


@mcp.tool()
def pve_backup_delete(storage: str, volid: str, node: str | None = None,
                      confirm: bool = False) -> dict:
    """MUTATION: delete a backup archive (removes a recovery point). Dry-run by default; confirm=True.
    Async — may return a task UPID or null depending on storage."""
    _, api, _, _ = _svc()
    plan = _plan("pve_backup_delete", volid, lambda: plan_backup_delete(api, storage, volid))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_backup_delete", volid,
                    lambda: backup_delete(api, storage, volid, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_restore(vmid: str, archive: str, storage: str, kind: str = "lxc", node: str | None = None,
                force: bool = False, pool: str | None = None, confirm: bool = False) -> dict:
    """MUTATION (DESTRUCTIVE if it overwrites an existing guest): restore a guest from a backup
    archive. Dry-run by default — the PLAN states whether it CREATES or OVERWRITES. confirm=True to
    execute. Async — returns a task UPID. pool: place the restored guest in a resource pool."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}"
    plan = _plan("pve_restore", target, lambda: plan_restore(api, vmid, archive, kind, node, force))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_restore", target,
                    lambda: restore_guest(api, vmid, archive, storage, kind, node, force, pool),
                    mutation=True, outcome="submitted", detail={"confirmed": True, "force": force})


# --- Provisioning (REST API, async). create/clone are additive; delete is DESTRUCTIVE. ---

@mcp.tool()
def pve_create_container(vmid: str, ostemplate: str, storage: str, node: str | None = None,
                         options: dict | None = None, confirm: bool = False) -> dict:
    """MUTATION: create a new LXC container. Dry-run by default; confirm=True. Async — returns a UPID.
    `options` carries extra create params (cores, memory, net0, rootfs, password, ...)."""
    _, api, _, _ = _svc()
    target = f"lxc/{vmid}"
    plan = _plan("pve_create_container", target, lambda: plan_create(api, vmid, "lxc", node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited(
        "pve_create_container", target,
        lambda: create_container(api, vmid, ostemplate, storage, node, **(options or {})),
        mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_create_vm(vmid: str, node: str | None = None, options: dict | None = None,
                  confirm: bool = False) -> dict:
    """MUTATION: create a new QEMU VM. Dry-run by default; confirm=True. Async — returns a UPID.
    `options` carries create params (cores, memory, net0, scsi0, ostype, ...)."""
    _, api, _, _ = _svc()
    target = f"qemu/{vmid}"
    plan = _plan("pve_create_vm", target, lambda: plan_create(api, vmid, "qemu", node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_create_vm", target,
                    lambda: create_vm(api, vmid, node, **(options or {})),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_clone(vmid: str, newid: str, kind: str = "lxc", node: str | None = None,
              name: str | None = None, full: bool = False, pool: str | None = None,
              storage: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: clone a guest to a new id. Dry-run by default; confirm=True. Async — returns a UPID.
    pool: place the new guest in a resource pool (needed when the token is pool-scoped).
    storage: target storage for the full clone's disks (full=True only) — keeps a clone off the
    source storage; refused for a linked clone (PVE only honors it on a full clone)."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}->{newid}"
    plan = _plan("pve_clone", target, lambda: plan_clone(api, vmid, newid, kind, node, storage, full))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_clone", target,
                    lambda: clone_guest(api, vmid, newid, kind, node, name, full, pool, storage),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_delete_guest(vmid: str, kind: str = "lxc", node: str | None = None, purge: bool = False,
                     force: bool = False, confirm: bool = False) -> dict:
    """MUTATION (DESTRUCTIVE, IRREVERSIBLE): permanently destroy a guest and its disks. Dry-run by
    default — the PLAN names exactly what will be destroyed. confirm=True to execute. Async — UPID."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}"
    plan = _plan("pve_delete_guest", target, lambda: plan_delete(api, vmid, kind, node, purge, force))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_delete_guest", target,
                    lambda: delete_guest(api, vmid, kind, node, purge, force),
                    mutation=True, outcome="submitted", detail={"confirmed": True, "purge": purge})


# --- Storage / ISO / templates (REST API) ---

@mcp.tool()
def pve_storage_content(storage: str, node: str | None = None,
                        content: str | None = None) -> list[dict]:
    """List a storage's content, optionally filtered (content = iso | vztmpl | backup) (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_storage_content", storage,
                    lambda: storage_content(api, storage, node, content))


@mcp.tool()
def pve_storage_status(storage: str, node: str | None = None) -> dict:
    """Status of a storage — total/used/avail/enabled (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_storage_status", storage, lambda: storage_status(api, storage, node))


@mcp.tool()
def pve_storage_download(storage: str, content: str, url: str, filename: str,
                         node: str | None = None, checksum: str | None = None,
                         checksum_algorithm: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: download an ISO (content=iso) or CT template (content=vztmpl) from a URL into a
    storage. Dry-run by default; confirm=True. Async — returns a UPID."""
    _, api, _, _ = _svc()
    target = f"{storage}:{filename}"
    plan = _plan("pve_storage_download", target,
                 lambda: plan_storage_download(storage, content, url, filename))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited(
        "pve_storage_download", target,
        lambda: storage_download_url(api, storage, content, url, filename, node,
                                     checksum, checksum_algorithm),
        mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_storage_content_delete(storage: str, volid: str, node: str | None = None,
                               confirm: bool = False) -> dict:
    """MUTATION: delete a content volume (ISO / template / backup) from storage. Dry-run by default
    (HIGH risk for a backup volume); confirm=True. Async — UPID or null."""
    _, api, _, _ = _svc()
    plan = _plan("pve_storage_content_delete", volid, lambda: plan_content_delete(api, storage, volid))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_storage_content_delete", volid,
                    lambda: content_delete(api, storage, volid, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


# --- Guest config edit (REST API). Config PUT is SYNCHRONOUS -> outcome="ok". ---

@mcp.tool()
def pve_guest_config_get(vmid: str, kind: str = "lxc", node: str | None = None) -> dict:
    """Read a guest's current config (kind = 'lxc' or 'qemu') (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_guest_config_get", f"{kind}/{vmid}",
                    lambda: guest_config_get(api, vmid, kind, node))


@mcp.tool()
def pve_guest_config_set(vmid: str, changes: dict, kind: str = "lxc", node: str | None = None,
                         confirm: bool = False) -> dict:
    """MUTATION: edit a guest's config (cores/memory/net/onboot/...). Dry-run by default — the PLAN
    shows the exact per-key diff; confirm=True to execute. Captures the prior config first so the
    change is revertible via pve_guest_config_revert. Synchronous."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}"
    plan = _plan("pve_guest_config_set", target,
                 lambda: plan_config_set(api, vmid, changes, kind, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_guest_config_set", target,
                    lambda: guest_config_set(api, vmid, changes, kind, node),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_guest_config_revert(vmid: str, prior_config: dict, kind: str = "lxc",
                            node: str | None = None, confirm: bool = False) -> dict:
    """MUTATION (UNDO): re-apply a previously captured guest config (the prior_config returned by
    pve_guest_config_set). Dry-run by default; confirm=True to execute. Synchronous."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}"
    plan = _plan("pve_guest_config_revert", target,
                 lambda: plan_config_revert(api, vmid, prior_config, kind, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_guest_config_revert", target,
                    lambda: guest_config_revert(api, vmid, prior_config, kind, node),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- Disk ops (REST API). Resize/move are async -> task UPID -> outcome="submitted". ---

@mcp.tool()
def pve_disk_resize(vmid: str, disk: str, size: str, kind: str = "lxc", node: str | None = None,
                    confirm: bool = False) -> dict:
    """MUTATION: grow a guest disk (e.g. size='+10G'). GROW ONLY — a shrink is refused (destructive).
    Dry-run by default; confirm=True to execute. Async — returns a task UPID."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}:{disk}"
    plan = _plan("pve_disk_resize", target,
                 lambda: plan_disk_resize(api, vmid, disk, size, kind, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_disk_resize", target,
                    lambda: disk_resize(api, vmid, disk, size, kind, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_disk_move(vmid: str, disk: str, target_storage: str, kind: str = "lxc",
                  node: str | None = None, delete_source: bool = False,
                  confirm: bool = False) -> dict:
    """MUTATION: move a guest disk to another storage. Dry-run by default — the PLAN shows
    source->target and whether the source copy is deleted (delete_source=True is HIGH). confirm=True
    to execute. Async — returns a task UPID."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}:{disk}"
    plan = _plan("pve_disk_move", target,
                 lambda: plan_disk_move(api, vmid, disk, target_storage, kind, node, delete_source))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_disk_move", target,
                    lambda: disk_move(api, vmid, disk, target_storage, kind, node, delete_source),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


# --- Cloud-init + template (REST API, QEMU). Config POST is synchronous -> outcome="ok". ---

@mcp.tool()
def pve_cloudinit_get(vmid: str, node: str | None = None, kind: str = "qemu") -> dict:
    """Read a QEMU guest's cloud-init config (secret fields are masked) (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_cloudinit_get", f"{kind}/{vmid}",
                    lambda: cloudinit_get(api, vmid, node, kind))


@mcp.tool()
def pve_cloudinit_set(vmid: str, changes: dict, node: str | None = None, kind: str = "qemu",
                      confirm: bool = False) -> dict:
    """MUTATION: set cloud-init fields (ciuser/sshkeys/ipconfigN/...) on a QEMU guest. Dry-run by
    default — the PLAN shows the diff with secrets masked; confirm=True to execute. Synchronous.
    Secret fields (cipassword) are never echoed to results or the ledger."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}"
    plan = _plan("pve_cloudinit_set", target,
                 lambda: plan_cloudinit_set(api, vmid, changes, node, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    # Capture the prior cloud-init config (secret-stripped) BEFORE the set, so the result carries
    # a real undo_record — best-effort: a failed capture must never block the mutation.
    try:
        undo = capture_cloudinit_undo(api, vmid, node, kind)
    except Exception as e:
        undo = {"prior_ci_config": None,
                "secret_undo_caveat": f"undo capture failed: {type(e).__name__}"}
    envelope = _audited("pve_cloudinit_set", target,
                        lambda: cloudinit_set(api, vmid, changes, node, kind),
                        mutation=True, outcome="ok", detail={"confirmed": True})
    envelope["undo_record"] = undo
    return envelope


@mcp.tool()
def pve_template_convert(vmid: str, node: str | None = None, kind: str = "qemu",
                         confirm: bool = False) -> dict:
    """MUTATION (IRREVERSIBLE): convert a guest into a template — effectively one-way. Dry-run by
    default (the PLAN flags it HIGH/irreversible); confirm=True to execute."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}"
    plan = _plan("pve_template_convert", target,
                 lambda: plan_template_convert(api, vmid, node, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_template_convert", target,
                    lambda: template_convert(api, vmid, node, kind),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


# --- Access governance (REST API, read) ---

@mcp.tool()
def pve_users_list() -> list[dict]:
    """List all Proxmox users (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_users_list", "access/users", lambda: access_users_list(api))


@mcp.tool()
def pve_roles_list() -> list[dict]:
    """List all Proxmox roles and their privileges (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_roles_list", "access/roles", lambda: access_roles_list(api))


@mcp.tool()
def pve_acl_list() -> list[dict]:
    """List all ACL entries on the Proxmox cluster (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_acl_list", "access/acl", lambda: access_acl_list(api))


@mcp.tool()
def pve_tokens_list(userid: str) -> list[dict]:
    """List API tokens for a specific user (read). userid: 'user@realm'."""
    _, api, _, _ = _svc()
    return _audited("pve_tokens_list", f"access/users/{userid}/token",
                    lambda: access_tokens_list(api, userid))


@mcp.tool()
def pve_overbroad_grants() -> list[dict]:
    """Surface over-broad ACL grants (Administrator role or root '/' path) as a diagnostic (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_overbroad_grants", "access/acl",
                    lambda: access_overbroad_grants(api))


# --- Access governance (REST API, MUTATION — confirm-gated) ---

@mcp.tool()
def pve_acl_modify(
    path: str, roles: str, target: str, kind: str = "user",
    propagate: bool = True, delete: bool = False, confirm: bool = False,
) -> dict:
    """MUTATION: grant or revoke an ACL entry (PUT /access/acl).

    Dry-run by default — the PLAN surfaces the critical Proxmox gotcha: a specific-path ACL
    REPLACES inherited grants (SHADOW) and revoking can RESTORE them (WIDEN). Re-call with
    confirm=True to execute. Synchronous.

    kind='user' (default) or 'token'. delete=False = grant; delete=True = revoke.
    """
    _, api, _, _ = _svc()
    tgt = f"acl:{path}:{target}"
    plan = _plan("pve_acl_modify", tgt,
                 lambda: plan_acl_modify(api, path, roles, target, kind, propagate, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_acl_modify", tgt,
                    lambda: acl_modify(api, path, roles, target, kind, propagate, delete),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_token_create(
    userid: str, tokenid: str, privsep: bool = True,
    comment: str | None = None, expire: int | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: create an API token for a user.

    Dry-run by default — the PLAN shows risk (privsep=False is HIGH: token inherits ALL owner perms).
    confirm=True to execute. The token secret (value) is returned ONCE to the caller and is NEVER
    written to the audit ledger. Synchronous.
    """
    _, api, _, _ = _svc()
    tgt = f"token:{userid}!{tokenid}"
    plan = _plan("pve_token_create", tgt,
                 lambda: plan_token_create(userid, tokenid, privsep))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    # SECRET HANDLING: return op result directly (carries the token value to caller);
    # detail dict must NEVER contain the secret — only {"confirmed": True}.
    return _audited("pve_token_create", tgt,
                    lambda: token_create(api, userid, tokenid, privsep, comment, expire),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_token_revoke(userid: str, tokenid: str, confirm: bool = False) -> dict:
    """MUTATION (IRREVERSIBLE): permanently revoke an API token.

    Dry-run by default — the PLAN flags HIGH: revocation is permanent, the secret is gone forever.
    confirm=True to execute. Synchronous.
    """
    _, api, _, _ = _svc()
    tgt = f"token:{userid}!{tokenid}"
    plan = _plan("pve_token_revoke", tgt, lambda: plan_token_revoke(userid, tokenid))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_token_revoke", tgt,
                    lambda: token_revoke(api, userid, tokenid),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- Firewall (REST API, read) ---

@mcp.tool()
def pve_firewall_rules_list(
    scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
) -> list[dict]:
    """List all firewall rules for the given scope (cluster/node/guest) (read)."""
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}"
    return _audited("pve_firewall_rules_list", tgt,
                    lambda: firewall_rules_list(api, scope, node, vmid, kind))


@mcp.tool()
def pve_firewall_options_get(
    scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
) -> dict:
    """Get firewall options (enable flag, policy, log rate, …) for the given scope (read)."""
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/options"
    return _audited("pve_firewall_options_get", tgt,
                    lambda: firewall_options_get(api, scope, node, vmid, kind))


@mcp.tool()
def pve_security_groups_list() -> list[dict]:
    """List cluster-wide firewall security groups (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_security_groups_list", "firewall/cluster/groups",
                    lambda: security_groups_list(api))


@mcp.tool()
def pve_ipset_list(
    scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
) -> list[dict]:
    """List IP sets for the given scope (read)."""
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/ipset"
    return _audited("pve_ipset_list", tgt,
                    lambda: ipset_list(api, scope, node, vmid, kind))


# --- Firewall (REST API, MUTATION — confirm-gated) ---

@mcp.tool()
def pve_firewall_rule_add(
    action: str, direction: str = "in", scope: str = "cluster",
    node: str | None = None, vmid: str | None = None, kind: str | None = None,
    source: str | None = None, dest: str | None = None, proto: str | None = None,
    dport: str | None = None, sport: str | None = None, comment: str | None = None,
    enable: bool = True, confirm: bool = False,
) -> dict:
    """MUTATION: add a new firewall rule. Dry-run by default — the PLAN shows scope, direction,
    action, and key address/port fields. Re-call with confirm=True to execute. Synchronous.

    WARNING: a misplaced DROP/REJECT can cause a connectivity lockout.
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/rules"
    plan = _plan("pve_firewall_rule_add", tgt,
                 lambda: plan_firewall_rule_add(action, direction, scope, node, vmid, kind,
                                                source, dest, dport, proto))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_rule_add", tgt,
                    lambda: firewall_rule_add(api, action, direction, scope, node,
                                             vmid, kind, source, dest, proto, dport,
                                             sport, comment, enable),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_rule_remove(
    pos: int, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: delete a firewall rule by position. Dry-run by default — the PLAN shows the rule
    at that position. Positions SHIFT after inserts/deletes — verify before confirming. Synchronous.
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/rules/{pos}"
    plan = _plan("pve_firewall_rule_remove", tgt,
                 lambda: plan_firewall_rule_remove(api, pos, scope, node, vmid, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_rule_remove", tgt,
                    lambda: firewall_rule_remove(api, pos, scope, node, vmid, kind),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_rule_update(
    pos: int, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
    action: str | None = None, direction: str | None = None,
    source: str | None = None, dest: str | None = None, proto: str | None = None,
    dport: str | None = None, sport: str | None = None, comment: str | None = None,
    enable: bool | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: update an existing firewall rule at position `pos`. Dry-run by default — the PLAN
    shows the rule's current state and the fields being changed. Synchronous.
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/rules/{pos}"
    # Build a dict of only the non-None update fields (matches plan_firewall_rule_update **new_fields).
    changes: dict = {}
    if action is not None:
        changes["action"] = action
    if direction is not None:
        changes["direction"] = direction
    if source is not None:
        changes["source"] = source
    if dest is not None:
        changes["dest"] = dest
    if proto is not None:
        changes["proto"] = proto
    if dport is not None:
        changes["dport"] = dport
    if sport is not None:
        changes["sport"] = sport
    if comment is not None:
        changes["comment"] = comment
    if enable is not None:
        changes["enable"] = enable
    plan = _plan("pve_firewall_rule_update", tgt,
                 lambda: plan_firewall_rule_update(api, pos, scope, node, vmid, kind, **changes))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_rule_update", tgt,
                    lambda: firewall_rule_update(api, pos, scope, node, vmid, kind, **changes),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_set_enabled(
    enabled: bool, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION (HIGH RISK): toggle the firewall on or off for the given scope. Dry-run by default.
    RISK_HIGH both directions: enabling may instantly lock you out (default-DROP, no ACCEPT for 22/8006);
    disabling strips all protection. Cluster scope = master kill-switch. Synchronous.
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/options"
    plan = _plan("pve_firewall_set_enabled", tgt,
                 lambda: plan_firewall_set_enabled(api, enabled, scope, node, vmid, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_set_enabled", tgt,
                    lambda: firewall_set_enabled(api, enabled, scope, node, vmid, kind),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_alias_list(
    scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
) -> list[dict]:
    """List firewall aliases (named CIDRs) for the given scope (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_firewall_alias_list", f"firewall/{scope}/aliases",
                    lambda: alias_list(api, scope, node, vmid, kind))


@mcp.tool()
def pve_firewall_alias_create(
    name: str, cidr: str, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None, comment: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: create a firewall alias (named CIDR). Dry-run by default — the PLAN shows the
    name, CIDR, and scope. Re-call with confirm=True to execute. Passive until a rule references it.
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/aliases/{name}"
    plan = _plan("pve_firewall_alias_create", tgt,
                 lambda: plan_alias_create(name, cidr, scope, node, vmid, kind, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_alias_create", tgt,
                    lambda: alias_create(api, name, cidr, scope, node, vmid, kind, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_alias_update(
    name: str, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
    cidr: str | None = None, comment: str | None = None,
    rename: str | None = None, digest: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: update a firewall alias. Dry-run by default — the PLAN shows the current alias and
    the fields being changed. Changing the CIDR silently alters every referencing rule's match set.
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/aliases/{name}"
    plan = _plan("pve_firewall_alias_update", tgt,
                 lambda: plan_alias_update(api, name, scope, node, vmid, kind, cidr, comment, rename))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_alias_update", tgt,
                    lambda: alias_update(api, name, scope, node, vmid, kind, cidr, comment, rename, digest),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_alias_delete(
    name: str, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
    digest: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: delete a firewall alias. Dry-run by default — the PLAN shows the current alias.
    PVE refuses while any rule still references the alias. No UNDO: re-create to revert.
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/aliases/{name}"
    plan = _plan("pve_firewall_alias_delete", tgt,
                 lambda: plan_alias_delete(api, name, scope, node, vmid, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_alias_delete", tgt,
                    lambda: alias_delete(api, name, scope, node, vmid, kind, digest),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_ipset_create(
    name: str, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None, comment: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: create an empty IP set. Dry-run by default — the PLAN shows the name and scope.
    Passive until a rule references it as '+name' and entries are added.
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/ipset/{name}"
    plan = _plan("pve_firewall_ipset_create", tgt,
                 lambda: plan_ipset_create(name, scope, node, vmid, kind, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_ipset_create", tgt,
                    lambda: ipset_create(api, name, scope, node, vmid, kind, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_ipset_delete(
    name: str, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
    force: bool = False, confirm: bool = False,
) -> dict:
    """MUTATION: delete an IP set. Dry-run by default — the PLAN shows member count and the
    force semantics. force=True WIPES all members; PVE refuses while a rule references the set.
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/ipset/{name}"
    plan = _plan("pve_firewall_ipset_delete", tgt,
                 lambda: plan_ipset_delete(api, name, scope, node, vmid, kind, force))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_ipset_delete", tgt,
                    lambda: ipset_delete(api, name, scope, node, vmid, kind, force),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_ipset_entry_add(
    name: str, cidr: str, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
    comment: str | None = None, nomatch: bool = False, confirm: bool = False,
) -> dict:
    """MUTATION: add an IP/Network entry to an IP set. Dry-run by default — the PLAN shows the
    entry and warns it changes every referencing rule's match set. nomatch=True = exclusion.
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/ipset/{name}"
    plan = _plan("pve_firewall_ipset_entry_add", tgt,
                 lambda: plan_ipset_entry_add(name, cidr, scope, node, vmid, kind, comment, nomatch))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_ipset_entry_add", tgt,
                    lambda: ipset_entry_add(api, name, cidr, scope, node, vmid, kind, comment, nomatch),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_ipset_entry_remove(
    name: str, cidr: str, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
    digest: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: remove an IP/Network entry from an IP set. Dry-run by default — the PLAN shows the
    entry and warns it changes every referencing rule's match set (may open or close access).
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/ipset/{name}"
    plan = _plan("pve_firewall_ipset_entry_remove", tgt,
                 lambda: plan_ipset_entry_remove(name, cidr, scope, node, vmid, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_ipset_entry_remove", tgt,
                    lambda: ipset_entry_remove(api, name, cidr, scope, node, vmid, kind, digest),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_security_group_create(
    group: str, comment: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: create an empty cluster security group. Dry-run by default — the PLAN shows the
    name. Passive until rules are added and a rule references it (type=group).
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/cluster/groups/{group}"
    plan = _plan("pve_firewall_security_group_create", tgt,
                 lambda: plan_security_group_create(group, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_security_group_create", tgt,
                    lambda: security_group_create(api, group, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_security_group_delete(group: str, confirm: bool = False) -> dict:
    """MUTATION: delete a cluster security group. Dry-run by default — the PLAN shows how many rules
    the group holds. PVE refuses while the group is non-empty or still referenced by a rule.
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/cluster/groups/{group}"
    plan = _plan("pve_firewall_security_group_delete", tgt,
                 lambda: plan_security_group_delete(api, group))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_security_group_delete", tgt,
                    lambda: security_group_delete(api, group),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_options_set(
    scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
    options: dict | None = None, delete: list[str] | None = None,
    digest: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: set firewall options for a scope (policy_in/out, log levels, ebtables, log_ratelimit,
    ...). `options` is a key->value bag; `delete` unsets keys. Dry-run by default — the PLAN shows the
    current values and flags lockout risk. RISK_HIGH when enabling the firewall or changing a policy.
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/options"
    plan = _plan("pve_firewall_options_set", tgt,
                 lambda: plan_firewall_options_set(api, scope, node, vmid, kind, options, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_options_set", tgt,
                    lambda: firewall_options_set(api, scope, node, vmid, kind, options, delete, digest),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- Network & SDN (REST API, read) ---

@mcp.tool()
def pve_network_list(node: str | None = None, iface_type: str | None = None) -> list[dict]:
    """List network interfaces on a node (bridges, bonds, VLANs, etc.) (read)."""
    cfg, api, _, _ = _svc()
    tgt = f"nodes/{node or cfg.node}/network"
    return _audited("pve_network_list", tgt, lambda: network_list(api, node, iface_type))


@mcp.tool()
def pve_sdn_zones_list() -> list[dict]:
    """List SDN zones (cluster-scoped) (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_sdn_zones_list", "cluster/sdn/zones", lambda: sdn_zones_list(api))


@mcp.tool()
def pve_sdn_vnets_list() -> list[dict]:
    """List SDN virtual networks (cluster-scoped) (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_sdn_vnets_list", "cluster/sdn/vnets", lambda: sdn_vnets_list(api))


# --- Network & SDN (REST API, MUTATION — confirm-gated) ---

@mcp.tool()
def pve_sdn_subnet_list(vnet: str) -> list[dict]:
    """List subnets in an SDN vnet (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_sdn_subnet_list", f"sdn/vnets/{vnet}/subnets",
                    lambda: sdn_subnet_list(api, vnet))


@mcp.tool()
def pve_sdn_zone_create(
    zone: str, zone_type: str, options: dict | None = None,
    lock_token: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: create an SDN zone (PENDING — inert until pve_sdn_apply, NOT applied here).
    `zone_type` is simple/vlan/qinq/vxlan/evpn/faucet; `options` carries type-specific params.
    Dry-run by default. RISK_LOW (staging, no live network effect).
    """
    _, api, _, _ = _svc()
    tgt = f"sdn/zones/{zone}"
    plan = _plan("pve_sdn_zone_create", tgt, lambda: plan_sdn_zone_create(zone, zone_type, options))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_zone_create", tgt,
                    lambda: sdn_zone_create(api, zone, zone_type, options, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_sdn_zone_update(
    zone: str, options: dict | None = None, delete: list[str] | None = None,
    digest: str | None = None, lock_token: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: update an SDN zone (PENDING). `options` sets fields; `delete` unsets keys.
    Dry-run by default. RISK_LOW (staging; inert until pve_sdn_apply).
    """
    _, api, _, _ = _svc()
    tgt = f"sdn/zones/{zone}"
    plan = _plan("pve_sdn_zone_update", tgt, lambda: plan_sdn_zone_update(zone, options, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_zone_update", tgt,
                    lambda: sdn_zone_update(api, zone, options, delete, digest, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_sdn_zone_delete(zone: str, lock_token: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: delete an SDN zone (PENDING). Dry-run by default — the PLAN shows the current zone.
    PVE refuses if a vnet still references it. RISK_MEDIUM (staging a removal an apply would enact).
    """
    _, api, _, _ = _svc()
    tgt = f"sdn/zones/{zone}"
    plan = _plan("pve_sdn_zone_delete", tgt, lambda: plan_sdn_zone_delete(api, zone))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_zone_delete", tgt,
                    lambda: sdn_zone_delete(api, zone, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_sdn_vnet_create(
    vnet: str, zone: str, options: dict | None = None,
    lock_token: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: create an SDN vnet in a zone (PENDING). `options` carries tag/alias/vlanaware/etc.
    Dry-run by default. RISK_LOW (staging; inert until pve_sdn_apply).
    """
    _, api, _, _ = _svc()
    tgt = f"sdn/vnets/{vnet}"
    plan = _plan("pve_sdn_vnet_create", tgt, lambda: plan_sdn_vnet_create(vnet, zone, options))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_vnet_create", tgt,
                    lambda: sdn_vnet_create(api, vnet, zone, options, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_sdn_vnet_update(
    vnet: str, options: dict | None = None, delete: list[str] | None = None,
    digest: str | None = None, lock_token: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: update an SDN vnet (PENDING). Dry-run by default. RISK_LOW (staging)."""
    _, api, _, _ = _svc()
    tgt = f"sdn/vnets/{vnet}"
    plan = _plan("pve_sdn_vnet_update", tgt, lambda: plan_sdn_vnet_update(vnet, options, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_vnet_update", tgt,
                    lambda: sdn_vnet_update(api, vnet, options, delete, digest, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_sdn_vnet_delete(vnet: str, lock_token: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: delete an SDN vnet (PENDING). Dry-run by default — the PLAN shows the current vnet.
    PVE refuses if a subnet still references it. RISK_MEDIUM.
    """
    _, api, _, _ = _svc()
    tgt = f"sdn/vnets/{vnet}"
    plan = _plan("pve_sdn_vnet_delete", tgt, lambda: plan_sdn_vnet_delete(api, vnet))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_vnet_delete", tgt,
                    lambda: sdn_vnet_delete(api, vnet, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_sdn_subnet_create(
    vnet: str, subnet: str, options: dict | None = None,
    lock_token: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: create an SDN subnet (PENDING). `subnet` is a CIDR (e.g. 10.0.0.0/24); `options`
    carries gateway/snat/dhcp params. Dry-run by default. RISK_LOW (staging; inert until apply).
    """
    _, api, _, _ = _svc()
    tgt = f"sdn/vnets/{vnet}/subnets/{subnet}"
    plan = _plan("pve_sdn_subnet_create", tgt, lambda: plan_sdn_subnet_create(vnet, subnet, options))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_subnet_create", tgt,
                    lambda: sdn_subnet_create(api, vnet, subnet, options, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_sdn_subnet_update(
    vnet: str, subnet: str, options: dict | None = None, delete: list[str] | None = None,
    digest: str | None = None, lock_token: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: update an SDN subnet (PENDING). `subnet` is the id from pve_sdn_subnet_list.
    Dry-run by default. RISK_LOW (staging).
    """
    _, api, _, _ = _svc()
    tgt = f"sdn/vnets/{vnet}/subnets/{subnet}"
    plan = _plan("pve_sdn_subnet_update", tgt, lambda: plan_sdn_subnet_update(vnet, subnet, options, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_subnet_update", tgt,
                    lambda: sdn_subnet_update(api, vnet, subnet, options, delete, digest, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_sdn_subnet_delete(
    vnet: str, subnet: str, lock_token: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: delete an SDN subnet (PENDING). `subnet` is the id from pve_sdn_subnet_list.
    Dry-run by default. RISK_MEDIUM (staging a removal an apply would enact).
    """
    _, api, _, _ = _svc()
    tgt = f"sdn/vnets/{vnet}/subnets/{subnet}"
    plan = _plan("pve_sdn_subnet_delete", tgt, lambda: plan_sdn_subnet_delete(vnet, subnet))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_subnet_delete", tgt,
                    lambda: sdn_subnet_delete(api, vnet, subnet, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_network_iface_create(
    iface: str, iface_type: str, node: str | None = None,
    options: dict | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: create a new network interface config (staged — not live until pve_network_apply).
    Dry-run by default; confirm=True to execute. Synchronous.
    `options` carries type-dependent fields (address, netmask, gateway, bridge_ports, …).
    """
    cfg, api, _, _ = _svc()
    tgt = f"nodes/{node or cfg.node}/network/{iface}"
    plan = _plan("pve_network_iface_create", tgt,
                 lambda: plan_iface_create(api, iface, iface_type, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_network_iface_create", tgt,
                    lambda: network_iface_create(api, iface, iface_type, node, **(options or {})),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_network_iface_update(
    iface: str, node: str | None = None,
    options: dict | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: update an existing network interface config (staged — not live until pve_network_apply).
    Dry-run by default; confirm=True to execute. Synchronous.
    `options` carries fields to update (address, netmask, bridge_ports, …).
    """
    cfg, api, _, _ = _svc()
    tgt = f"nodes/{node or cfg.node}/network/{iface}"
    plan = _plan("pve_network_iface_update", tgt,
                 lambda: plan_iface_update(api, iface, node, options or {}))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_network_iface_update", tgt,
                    lambda: network_iface_update(api, iface, node, **(options or {})),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_network_apply(node: str | None = None, confirm: bool = False) -> dict:
    """MUTATION (HIGH RISK): apply staged network config changes to the live network stack.
    Dry-run by default — the PLAN surfaces pending interfaces. confirm=True to execute.
    A misconfigured interface can lose SSH/API access; recovery requires console/physical access.
    May return a UPID (async) or None (sync) — outcome='submitted' in either case.
    """
    cfg, api, _, _ = _svc()
    tgt = f"nodes/{node or cfg.node}/network"
    plan = _plan("pve_network_apply", tgt, lambda: plan_network_apply(api, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_network_apply", tgt,
                    lambda: network_apply(api, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_sdn_apply(confirm: bool = False) -> dict:
    """MUTATION (HIGH RISK): apply pending SDN config changes (cluster-scoped).
    Dry-run by default — the PLAN surfaces pending zones/vnets. confirm=True to execute.
    A misconfigured SDN can disrupt virtual networking for ALL guests cluster-wide.
    May return a UPID (async) or None (sync) — outcome='submitted' in either case.
    """
    _, api, _, _ = _svc()
    plan = _plan("pve_sdn_apply", "cluster/sdn", lambda: plan_sdn_apply(api))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_apply", "cluster/sdn",
                    lambda: sdn_apply(api),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


# --- Cluster & HA (REST API, read) ---

@mcp.tool()
def pve_cluster_status() -> list[dict]:
    """Overall cluster status — nodes, quorum, version (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_cluster_status", "cluster/status", lambda: cluster_status(api))


@mcp.tool()
def pve_cluster_resources(resource_type: str | None = None) -> list[dict]:
    """List all resources across the cluster (VMs, nodes, storage, SDN).
    resource_type: optional filter — 'vm', 'storage', 'node', or 'sdn' (read)."""
    _, api, _, _ = _svc()
    tgt = f"cluster/resources/{resource_type or 'all'}"
    return _audited("pve_cluster_resources", tgt,
                    lambda: cluster_resources(api, resource_type))


@mcp.tool()
def pve_ha_groups_list() -> list[dict]:
    """List all HA resource groups (read). PVE-8 only — PVE 9 migrated groups to rules
    (use pve_ha_rules_list); on PVE 9 this raises a clear error pointing there."""
    _, api, _, _ = _svc()
    return _audited("pve_ha_groups_list", "cluster/ha/groups", lambda: ha_groups_list(api))


@mcp.tool()
def pve_ha_rules_list() -> list[dict]:
    """List HA rules (read) — the PVE 9 replacement for HA groups."""
    _, api, _, _ = _svc()
    return _audited("pve_ha_rules_list", "cluster/ha/rules", lambda: ha_rules_list(api))


@mcp.tool()
def pve_ha_resources_list() -> list[dict]:
    """List all HA resources (managed guests) (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_ha_resources_list", "cluster/ha/resources",
                    lambda: ha_resources_list(api))


# --- Cluster & HA (REST API, MUTATION — confirm-gated) ---

@mcp.tool()
def pve_guest_migrate(
    vmid: str, target: str, kind: str = "lxc", node: str | None = None,
    online: bool = False, confirm: bool = False,
) -> dict:
    """MUTATION: migrate a guest to a different node. Dry-run by default — the PLAN shows the
    guest's live state, the source→target, and the honest blast radius (LXC 'online' is
    stop→move→start, NOT zero-downtime; QEMU live migration requires shared storage).
    confirm=True to execute. Async — returns a task UPID.
    """
    _, api, _, _ = _svc()
    tgt = f"{kind}/{vmid}->{target}"
    plan = _plan("pve_guest_migrate", tgt,
                 lambda: plan_migrate(api, vmid, target, kind, node, online))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_guest_migrate", tgt,
                    lambda: guest_migrate(api, vmid, target, kind, node, online),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_ha_resource_add(
    vmid: str, kind: str = "lxc", group: str | None = None,
    state: str | None = None, max_restart: int | None = None,
    max_relocate: int | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: add a guest to HA management. Dry-run by default — the PLAN shows the SID,
    group, initial state, and blast radius (state='stopped' is HIGH: CRM will stop the guest).
    confirm=True to execute. Synchronous (pmxcfs config write; CRM enforces state asynchronously).
    """
    _, api, _, _ = _svc()
    tgt = f"ha:{kind}/{vmid}"
    plan = _plan("pve_ha_resource_add", tgt,
                 lambda: plan_ha_resource_add(vmid, kind, group, state))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_ha_resource_add", tgt,
                    lambda: ha_resource_add(api, vmid, kind, group, state, max_restart, max_relocate),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_ha_resource_remove(vmid: str, kind: str = "lxc", confirm: bool = False) -> dict:
    """MUTATION: remove a guest from HA management. Dry-run by default — the PLAN shows the SID
    and that this loses automated failover protection (guest itself is NOT stopped).
    confirm=True to execute. Synchronous (pmxcfs config write).
    """
    _, api, _, _ = _svc()
    tgt = f"ha:{kind}/{vmid}"
    plan = _plan("pve_ha_resource_remove", tgt,
                 lambda: plan_ha_resource_remove(vmid, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_ha_resource_remove", tgt,
                    lambda: ha_resource_remove(api, vmid, kind),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_ha_rule_create(
    rule: str, rule_type: str, resources: str, comment: str | None = None,
    disable: bool = False, nodes: str | None = None, strict: bool = False,
    affinity: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: create an HA rule (the PVE 9 replacement for HA groups). Dry-run by default — the
    PLAN shows the rule type, resources, and placement effect. `rule_type` is 'node-affinity'
    (needs `nodes`; optional `strict`) or 'resource-affinity' (needs `affinity` positive|negative).
    confirm=True to execute. Synchronous (pmxcfs config write). RISK_MEDIUM — constrains CRM placement.
    """
    _, api, _, _ = _svc()
    tgt = f"ha/rules/{rule}"
    plan = _plan("pve_ha_rule_create", tgt,
                 lambda: plan_ha_rule_create(rule, rule_type, resources, nodes, strict, affinity, disable))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_ha_rule_create", tgt,
                    lambda: ha_rule_create(api, rule, rule_type, resources, comment, disable,
                                           nodes, strict, affinity),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_ha_rule_update(
    rule: str, comment: str | None = None, disable: bool | None = None,
    resources: str | None = None, rule_type: str | None = None, nodes: str | None = None,
    strict: bool | None = None, affinity: str | None = None,
    delete: list[str] | None = None, digest: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: update an HA rule. Dry-run by default — the PLAN shows the current rule and the
    fields being changed. `delete` unsets keys. confirm=True to execute. Synchronous.
    RISK_MEDIUM — may trigger CRM migration of affected resources.
    """
    _, api, _, _ = _svc()
    tgt = f"ha/rules/{rule}"
    plan = _plan("pve_ha_rule_update", tgt,
                 lambda: plan_ha_rule_update(api, rule, comment, disable, resources, rule_type,
                                             nodes, strict, affinity, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_ha_rule_update", tgt,
                    lambda: ha_rule_update(api, rule, comment, disable, resources, rule_type,
                                           nodes, strict, affinity, delete, digest),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_ha_rule_delete(rule: str, confirm: bool = False) -> dict:
    """MUTATION: delete an HA rule. Dry-run by default — the PLAN shows the current rule and that
    its resources lose this placement constraint (CRM may migrate them). confirm=True to execute.
    Synchronous. RISK_MEDIUM.
    """
    _, api, _, _ = _svc()
    tgt = f"ha/rules/{rule}"
    plan = _plan("pve_ha_rule_delete", tgt, lambda: plan_ha_rule_delete(api, rule))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_ha_rule_delete", tgt,
                    lambda: ha_rule_delete(api, rule),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- Observability (REST API, read) ---

@mcp.tool()
def pve_node_services_list(node: str | None = None) -> list[dict]:
    """List all services on a PVE node, with state (read)."""
    cfg, api, _, _ = _svc()
    return _audited("pve_node_services_list", node or cfg.node,
                    lambda: node_services_list(api, node))


@mcp.tool()
def pve_node_service_status(service: str, node: str | None = None) -> dict:
    """Get the current state of a single service on a PVE node (read)."""
    cfg, api, _, _ = _svc()
    return _audited("pve_node_service_status", f"{node or cfg.node}/services/{service}",
                    lambda: node_service_status(api, service, node))


@mcp.tool()
def pve_node_rrddata(node: str | None = None, timeframe: str = "hour",
                     cf: str | None = None) -> list[dict]:
    """Get RRD telemetry (time-series) for a PVE node (read). timeframe: hour/day/week/month/year."""
    cfg, api, _, _ = _svc()
    return _audited("pve_node_rrddata", node or cfg.node,
                    lambda: node_rrddata(api, node, timeframe, cf))


@mcp.tool()
def pve_node_journal(node: str | None = None, lastentries: int = 100,
                     since: str | None = None, until: str | None = None) -> list[str]:
    """Fetch journal entries from a PVE node (read; returns log-line strings). lastentries capped at 5000."""
    cfg, api, _, _ = _svc()
    return _audited("pve_node_journal", node or cfg.node,
                    lambda: node_journal(api, node, lastentries, since, until))


@mcp.tool()
def pve_node_syslog(node: str | None = None, limit: int = 100) -> list[dict]:
    """Fetch syslog entries from a PVE node (read). limit capped at 5000."""
    cfg, api, _, _ = _svc()
    return _audited("pve_node_syslog", node or cfg.node,
                    lambda: node_syslog(api, node, limit))


@mcp.tool()
def pve_node_dns(node: str | None = None) -> dict:
    """Get the DNS configuration of a PVE node (read)."""
    cfg, api, _, _ = _svc()
    return _audited("pve_node_dns", node or cfg.node, lambda: node_dns_get(api, node))


@mcp.tool()
def pve_node_subscription(node: str | None = None) -> dict:
    """Get the subscription status of a PVE node (read)."""
    cfg, api, _, _ = _svc()
    return _audited("pve_node_subscription", node or cfg.node,
                    lambda: node_subscription(api, node))


@mcp.tool()
def pve_node_certificates(node: str | None = None) -> list[dict]:
    """List TLS certificates configured on a PVE node (read)."""
    cfg, api, _, _ = _svc()
    return _audited("pve_node_certificates", node or cfg.node,
                    lambda: node_certificates_info(api, node))


# --- Observability (mutation) ---

@mcp.tool()
def pve_node_service_control(service: str, action: str, node: str | None = None,
                             confirm: bool = False) -> dict:
    """MUTATION: start/stop/restart/reload a service on a PVE node. Dry-run by default — the
    PLAN flags lockout-class services (sshd/pveproxy/pvedaemon/pve-cluster/corosync/networking/
    ...) as HIGH because stop/restart can sever the management plane or break quorum. There is
    NO auto-undo for a service control. confirm=True to execute. Async — returns a task UPID.
    """
    cfg, api, _, _ = _svc()
    tgt = f"{node or cfg.node}/services/{service}:{action}"
    plan = _plan("pve_node_service_control", tgt,
                 lambda: plan_node_service_control(service, action, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_service_control", tgt,
                    lambda: node_service_control(api, service, action, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


# --- Task control + resource pools (read) ---

@mcp.tool()
def pve_tasks_list(node: str | None = None, limit: int = 50, errors: bool = False,
                   vmid: str | None = None, typefilter: str | None = None,
                   statusfilter: str | None = None) -> list[dict]:
    """List recent tasks on a node (read). limit 1-1000 (clamped)."""
    cfg, api, _, _ = _svc()
    return _audited("pve_tasks_list", node or cfg.node,
                    lambda: tasks_list(api, node, limit, errors, vmid, typefilter, statusfilter))


@mcp.tool()
def pve_task_log(upid: str, node: str | None = None, start: int = 0,
                 limit: int = 50) -> list[dict]:
    """Retrieve the log lines for a task (read)."""
    cfg, api, _, _ = _svc()
    return _audited("pve_task_log", upid, lambda: task_log(api, upid, node, start, limit))


@mcp.tool()
def pve_task_wait(upid: str, node: str | None = None, timeout: int = 120,
                  interval: int = 2) -> dict:
    """Block until an async Proxmox task reaches a terminal state — or the timeout — then report the
    outcome (read). The ergonomic complement to the submit-an-async-op tools (migrate / backup /
    restore / clone / rollback / snapshot + guest create) that return a UPID: wait for completion
    without hand-rolling a pve_task_status poll loop.

    Returns {upid, finished, succeeded, status, exitstatus, timed_out, polls}. `succeeded` is
    fail-closed (finished AND exitstatus == "OK"); a failed or timed-out task is reported, not raised.
    timeout is clamped 1..600s, interval 1..60s. Use pve_task_log for the full log.

    (Proximo's native UPID model — NOT the MCP Tasks protocol, which was removed from the spec.)"""
    _, api, _, _ = _svc()
    t = max(1, min(int(timeout), 600))
    iv = max(1, min(int(interval), 60))

    def _do() -> dict:
        r = wait_for_task(lambda: api.task_status(upid, node), timeout=t, interval=iv)
        r["upid"] = upid
        return r

    return _audited("pve_task_wait", upid, _do)


@mcp.tool()
def pve_pools_list() -> list[dict]:
    """List all resource pools (cluster-scoped) (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_pools_list", "cluster/pools", lambda: pools_list(api))


@mcp.tool()
def pve_pool_get(poolid: str) -> dict:
    """Get a resource pool's config and member list (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_pool_get", f"pool/{poolid}", lambda: pool_get(api, poolid))


# --- Task control + resource pools (mutation) ---

@mcp.tool()
def pve_task_stop(upid: str, node: str | None = None, confirm: bool = False) -> dict:
    """MUTATION (HIGH): stop (cancel) a running task. Dry-run by default — the PLAN warns that
    stopping a backup/restore/migration/clone mid-flight can leave the target inconsistent, with
    NO undo. confirm=True to execute. Synchronous cancellation signal (returns null)."""
    _, api, _, _ = _svc()
    plan = _plan("pve_task_stop", upid, lambda: plan_task_stop(upid, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_task_stop", upid,
                    lambda: task_stop(api, upid, node),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_pool_create(poolid: str, comment: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create an (empty) resource pool. Dry-run by default (PLAN = additive, LOW).
    confirm=True to execute. Synchronous."""
    _, api, _, _ = _svc()
    tgt = f"pool/{poolid}"
    plan = _plan("pve_pool_create", tgt, lambda: plan_pool_create(poolid, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_pool_create", tgt,
                    lambda: pool_create(api, poolid, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_pool_update(poolid: str, vms: str | None = None, storage: str | None = None,
                    delete: bool = False, confirm: bool = False) -> dict:
    """MUTATION: add (delete=False) or remove (delete=True) pool members. Dry-run by default —
    the PLAN notes membership re-scopes ACL coverage. confirm=True to execute. Synchronous.
    delete=True with no vms/storage is refused (ambiguous)."""
    _, api, _, _ = _svc()
    tgt = f"pool/{poolid}"
    plan = _plan("pve_pool_update", tgt,
                 lambda: plan_pool_update(poolid, vms, storage, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_pool_update", tgt,
                    lambda: pool_update(api, poolid, vms, storage, delete),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_pool_delete(poolid: str, confirm: bool = False) -> dict:
    """MUTATION: delete a resource pool. Dry-run by default — the PLAN warns ACLs on /pool/{poolid}
    are orphaned and the pool must be empty first (members are NOT deleted). confirm=True to
    execute. Synchronous."""
    _, api, _, _ = _svc()
    tgt = f"pool/{poolid}"
    plan = _plan("pve_pool_delete", tgt, lambda: plan_pool_delete(api, poolid))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_pool_delete", tgt,
                    lambda: pool_delete(api, poolid),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- PBS (Proxmox Backup Server) deep (read) ---

@mcp.tool()
def pbs_datastores_list() -> list[dict]:
    """List all datastores on the PBS server (read). Needs PROXIMO_PBS_* config."""
    _, pbs = _pbs()
    return _audited("pbs_datastores_list", "pbs/datastores",
                    lambda: pbs_datastore_list_op(pbs))


@mcp.tool()
def pbs_datastore_status(store: str) -> dict:
    """Get usage statistics for a PBS datastore (read)."""
    _, pbs = _pbs()
    return _audited("pbs_datastore_status", f"pbs/{store}",
                    lambda: pbs_datastore_status_op(pbs, store))


@mcp.tool()
def pbs_gc_status(store: str) -> dict:
    """Get garbage-collection status for a PBS datastore (read)."""
    _, pbs = _pbs()
    return _audited("pbs_gc_status", f"pbs/{store}/gc", lambda: pbs_gc_status_op(pbs, store))


@mcp.tool()
def pbs_snapshots_list(store: str, ns: str | None = None, backup_type: str | None = None,
                       backup_id: str | None = None) -> list[dict]:
    """List backup snapshots in a PBS datastore, with optional filters (read)."""
    _, pbs = _pbs()
    return _audited("pbs_snapshots_list", f"pbs/{store}",
                    lambda: pbs_snapshots_list_op(pbs, store, ns, backup_type, backup_id))


@mcp.tool()
def pbs_namespaces_list(store: str, parent: str | None = None,
                        max_depth: int | None = None) -> list[dict]:
    """List namespaces within a PBS datastore (read)."""
    _, pbs = _pbs()
    return _audited("pbs_namespaces_list", f"pbs/{store}",
                    lambda: pbs_namespace_list_op(pbs, store, parent, max_depth))


# --- PBS deep (mutation) ---

@mcp.tool()
def pbs_gc_start(store: str, confirm: bool = False) -> dict:
    """MUTATION (HIGH): start garbage collection on a PBS datastore. Dry-run by default — GC
    permanently removes unreferenced chunks (no undo). confirm=True to execute. Async — UPID."""
    _, pbs = _pbs()
    tgt = f"pbs/{store}/gc"
    plan = _plan("pbs_gc_start", tgt, lambda: pbs_plan_gc_start(store))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_gc_start", tgt, lambda: pbs_gc_start_op(pbs, store),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pbs_verify_start(store: str, ns: str | None = None, backup_type: str | None = None,
                     backup_id: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: start an integrity verification run on a PBS datastore. Dry-run by default —
    non-destructive (read-only check) but heavy I/O. confirm=True to execute. Async — UPID."""
    _, pbs = _pbs()
    tgt = f"pbs/{store}/verify"
    plan = _plan("pbs_verify_start", tgt,
                 lambda: pbs_plan_verify_start(store, ns, backup_type, backup_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_verify_start", tgt,
                    lambda: pbs_verify_start_op(pbs, store, ns, backup_type, backup_id),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pbs_prune(store: str, keep_last: int | None = None, keep_daily: int | None = None,
              keep_weekly: int | None = None, keep_monthly: int | None = None,
              keep_yearly: int | None = None, ns: str | None = None,
              backup_type: str | None = None, backup_id: str | None = None,
              dry_run: bool = True, confirm: bool = False) -> dict:
    """MUTATION: prune backup snapshots per a retention policy. TWO safety gates: confirm
    (Proximo dry-run vs execute) AND dry_run (PBS-side preview). dry_run=True (default) only
    previews; dry_run=False DELETES recovery points (PLAN is HIGH, no undo). confirm=True to
    execute. Synchronous — returns prune decisions."""
    _, pbs = _pbs()
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


@mcp.tool()
def pbs_snapshot_delete(store: str, backup_type: str, backup_id: str, backup_time: int,
                        ns: str | None = None, confirm: bool = False) -> dict:
    """MUTATION (HIGH): delete a specific backup snapshot (a recovery point) from a PBS
    datastore. Dry-run by default. Permanent — no undo. confirm=True to execute. Synchronous."""
    _, pbs = _pbs()
    tgt = f"pbs/{store}/{backup_type}/{backup_id}"
    plan = _plan("pbs_snapshot_delete", tgt,
                 lambda: pbs_plan_snapshot_delete(store, backup_type, backup_id, backup_time, ns))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_snapshot_delete", tgt,
                    lambda: pbs_snapshot_delete_op(pbs, store, backup_type, backup_id, backup_time, ns),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pbs_namespace_create(store: str, name: str, parent: str | None = None,
                         confirm: bool = False) -> dict:
    """MUTATION: create a namespace within a PBS datastore. Dry-run by default (additive, LOW).
    confirm=True to execute. Synchronous."""
    _, pbs = _pbs()
    tgt = f"pbs/{store}/namespace/{name}"
    plan = _plan("pbs_namespace_create", tgt,
                 lambda: pbs_plan_namespace_create(store, name, parent))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_namespace_create", tgt,
                    lambda: pbs_namespace_create_op(pbs, store, name, parent),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pbs_namespace_delete(store: str, ns: str, delete_groups: bool = False,
                         confirm: bool = False) -> dict:
    """MUTATION: delete a namespace from a PBS datastore. Dry-run by default — delete_groups=True
    is HIGH (it deletes all backup groups/snapshots inside the namespace, no undo). confirm=True
    to execute. Synchronous."""
    _, pbs = _pbs()
    tgt = f"pbs/{store}/namespace/{ns}"
    plan = _plan("pbs_namespace_delete", tgt,
                 lambda: pbs_plan_namespace_delete(store, ns, delete_groups))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_namespace_delete", tgt,
                    lambda: pbs_namespace_delete_op(pbs, store, ns, delete_groups),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- Storage administration (storage.cfg CRUD) ---

@mcp.tool()
def pve_storage_config_list() -> list[dict]:
    """List the cluster storage definitions (storage.cfg) (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_storage_config_list", "cluster/storage",
                    lambda: storage_config_list(api))


@mcp.tool()
def pve_storage_config_get(storage: str) -> dict:
    """Get one storage definition (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_storage_config_get", f"storage/{storage}",
                    lambda: storage_config_get(api, storage))


@mcp.tool()
def pve_storage_create(storage: str, storage_type: str, content: str | None = None,
                       path: str | None = None, server: str | None = None,
                       export: str | None = None, nodes: str | None = None,
                       disable: bool = False, shared: bool = False,
                       confirm: bool = False) -> dict:
    """MUTATION: define a new storage (storage.cfg). Dry-run by default. confirm=True to execute."""
    _, api, _, _ = _svc()
    tgt = f"storage/{storage}"
    plan = _plan("pve_storage_create", tgt,
                 lambda: plan_storage_create(storage, storage_type, content, path, server,
                                             export, nodes, disable, shared))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_storage_create", tgt,
                    lambda: storage_create(api, storage, storage_type, content, path,
                                          server, export, nodes, disable, shared),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_storage_update(storage: str, content: str | None = None, nodes: str | None = None,
                       disable: bool | None = None, shared: bool | None = None,
                       delete: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: update a storage definition. Dry-run by default (disable=True warns guests lose
    disk access). confirm=True to execute."""
    _, api, _, _ = _svc()
    tgt = f"storage/{storage}"
    plan = _plan("pve_storage_update", tgt,
                 lambda: plan_storage_update(api, storage, content, nodes, disable, shared, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_storage_update", tgt,
                    lambda: storage_update(api, storage, content, nodes, disable, shared, delete),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_storage_delete(storage: str, confirm: bool = False) -> dict:
    """MUTATION (HIGH): remove a storage definition cluster-wide. Dry-run by default — the PLAN
    warns guest disks/backups living only there become inaccessible (data not erased). confirm=True."""
    _, api, _, _ = _svc()
    tgt = f"storage/{storage}"
    plan = _plan("pve_storage_delete", tgt, lambda: plan_storage_delete(api, storage))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_storage_delete", tgt,
                    lambda: storage_delete(api, storage),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- Access governance: users & groups ---

@mcp.tool()
def pve_user_get(userid: str) -> dict:
    """Get a user's config, groups, and tokens (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_user_get", f"user/{userid}", lambda: user_get(api, userid))


@mcp.tool()
def pve_groups_list() -> list[dict]:
    """List all groups (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_groups_list", "access/groups", lambda: groups_list(api))


@mcp.tool()
def pve_group_get(groupid: str) -> dict:
    """Get a group's config and members (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_group_get", f"group/{groupid}", lambda: group_get(api, groupid))


@mcp.tool()
def pve_user_create(userid: str, comment: str | None = None, email: str | None = None,
                    enable: bool | None = None, expire: int | None = None,
                    groups: str | None = None, firstname: str | None = None,
                    lastname: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create a user. Dry-run by default (note: password is set separately — the user
    cannot log in until then). confirm=True to execute."""
    _, api, _, _ = _svc()
    tgt = f"user/{userid}"
    plan = _plan("pve_user_create", tgt,
                 lambda: plan_user_create(userid, comment, email, enable, expire, groups,
                                          firstname, lastname))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_user_create", tgt,
                    lambda: user_create(api, userid, comment, email, enable, expire,
                                       groups, firstname, lastname),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_user_update(userid: str, comment: str | None = None, email: str | None = None,
                    enable: bool | None = None, expire: int | None = None,
                    groups: str | None = None, firstname: str | None = None,
                    lastname: str | None = None, append: bool | None = None,
                    confirm: bool = False) -> dict:
    """MUTATION: update a user (enable=False stops login; group changes re-scope access).
    Dry-run by default. confirm=True to execute."""
    _, api, _, _ = _svc()
    tgt = f"user/{userid}"
    plan = _plan("pve_user_update", tgt,
                 lambda: plan_user_update(userid, comment, email, enable, expire, groups,
                                          firstname, lastname, append))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_user_update", tgt,
                    lambda: user_update(api, userid, comment, email, enable, expire,
                                       groups, firstname, lastname, append),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_user_delete(userid: str, confirm: bool = False) -> dict:
    """MUTATION (HIGH): delete a user. Dry-run by default — the PLAN reads the user's ACLs/tokens
    to show what access vanishes (permanent, no undo; admin = lockout risk). confirm=True."""
    _, api, _, _ = _svc()
    tgt = f"user/{userid}"
    plan = _plan("pve_user_delete", tgt, lambda: plan_user_delete(api, userid))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_user_delete", tgt,
                    lambda: user_delete(api, userid),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_group_create(groupid: str, comment: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create an (empty) group. Dry-run by default (additive, LOW). confirm=True."""
    _, api, _, _ = _svc()
    tgt = f"group/{groupid}"
    plan = _plan("pve_group_create", tgt, lambda: plan_group_create(groupid, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_group_create", tgt,
                    lambda: group_create(api, groupid, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_group_update(groupid: str, comment: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: update a group's comment. Dry-run by default. confirm=True."""
    _, api, _, _ = _svc()
    tgt = f"group/{groupid}"
    plan = _plan("pve_group_update", tgt, lambda: plan_group_update(groupid, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_group_update", tgt,
                    lambda: group_update(api, groupid, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_group_delete(groupid: str, confirm: bool = False) -> dict:
    """MUTATION (HIGH): delete a group. Dry-run by default — the PLAN reads members and warns ACLs
    granted to/on the group are orphaned. confirm=True."""
    _, api, _, _ = _svc()
    tgt = f"group/{groupid}"
    plan = _plan("pve_group_delete", tgt, lambda: plan_group_delete(api, groupid))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_group_delete", tgt,
                    lambda: group_delete(api, groupid),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- Access governance: roles, realms, TFA ---

@mcp.tool()
def pve_realms_list() -> list[dict]:
    """List authentication realms/domains (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_realms_list", "access/domains", lambda: realms_list(api))


@mcp.tool()
def pve_realm_get(realm: str) -> dict:
    """Get a realm's config (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_realm_get", f"realm/{realm}", lambda: realm_get(api, realm))


@mcp.tool()
def pve_tfa_list() -> list[dict]:
    """List per-user TFA (two-factor) entries across the cluster (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_tfa_list", "access/tfa", lambda: tfa_list(api))


@mcp.tool()
def pve_tfa_get(userid: str, tfa_id: str | None = None) -> object:
    """Read a user's TFA entries, or one entry (read). GET /access/tfa/{userid}[/{tfa_id}]."""
    _, api, _, _ = _svc()
    return _audited("pve_tfa_get", f"access/tfa/{userid}", lambda: tfa_get(api, userid, tfa_id))


@mcp.tool()
def pve_tfa_delete(
    userid: str, tfa_id: str, password: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION (HIGH RISK): delete a user's TFA factor. Dry-run by default — the PLAN shows how many
    factors remain and warns this WEAKENS the account (and can lock the user out if it's the last
    factor on a TFA-required realm). `password` (if PVE requires it) is passed through but never
    logged. confirm=True to execute.

    NOTE (live-verified PVE 9.1.7): PVE requires a ticket-based login session — NOT an API token —
    to mutate TFA, returning `403 ... need proper ticket` under token auth. Proximo is token-authed,
    so this delete will 403 on PVE; the read tools (pve_tfa_get/pve_tfa_list) work normally.
    """
    _, api, _, _ = _svc()
    tgt = f"access/tfa/{userid}/{tfa_id}"
    plan = _plan("pve_tfa_delete", tgt, lambda: plan_tfa_delete(api, userid, tfa_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_tfa_delete", tgt,
                    lambda: tfa_delete(api, userid, tfa_id, password),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_role_create(roleid: str, privs: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create a custom role. Dry-run by default. confirm=True to execute."""
    _, api, _, _ = _svc()
    tgt = f"role/{roleid}"
    plan = _plan("pve_role_create", tgt, lambda: plan_role_create(roleid, privs))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_role_create", tgt,
                    lambda: role_create(api, roleid, privs),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_role_update(roleid: str, privs: str | None = None, append: bool | None = None,
                    confirm: bool = False) -> dict:
    """MUTATION: change a role's privileges. Dry-run by default — built-in roles (Administrator,
    PVEAdmin, …) are flagged HIGH (changing them re-scopes every ACL using them). confirm=True."""
    _, api, _, _ = _svc()
    tgt = f"role/{roleid}"
    plan = _plan("pve_role_update", tgt, lambda: plan_role_update(api, roleid, privs, append))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_role_update", tgt,
                    lambda: role_update(api, roleid, privs, append),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_role_delete(roleid: str, confirm: bool = False) -> dict:
    """MUTATION (HIGH): delete a role. Dry-run by default — the PLAN reads ACLs to count grants
    that will break, and refuses built-in roles. confirm=True."""
    _, api, _, _ = _svc()
    tgt = f"role/{roleid}"
    plan = _plan("pve_role_delete", tgt, lambda: plan_role_delete(api, roleid))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_role_delete", tgt,
                    lambda: role_delete(api, roleid),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_realm_create(realm: str, realm_type: str, comment: str | None = None,
                     options: dict | None = None, confirm: bool = False) -> dict:
    """MUTATION: create an auth realm. Dry-run by default; confirm=True to execute.
    `options` carries the type-specific fields PVE requires (ldap: server1/base_dn/user_attr;
    ad: domain/server1; openid: issuer-url/client-id) — passed verbatim; PVE validates them."""
    _, api, _, _ = _svc()
    tgt = f"realm/{realm}"
    plan = _plan("pve_realm_create", tgt,
                 lambda: plan_realm_create(realm, realm_type, comment, options))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_realm_create", tgt,
                    lambda: realm_create(api, realm, realm_type, comment, options),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_realm_update(realm: str, comment: str | None = None,
                     options: dict | None = None, confirm: bool = False) -> dict:
    """MUTATION: update a realm. Dry-run by default — built-in pam/pve realms are flagged HIGH
    (changing them risks breaking logins). confirm=True. `options` carries type-specific fields
    (server1/base_dn/etc.) passed verbatim; PVE validates them."""
    _, api, _, _ = _svc()
    tgt = f"realm/{realm}"
    plan = _plan("pve_realm_update", tgt, lambda: plan_realm_update(api, realm, comment, options))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_realm_update", tgt,
                    lambda: realm_update(api, realm, comment, options),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_realm_delete(realm: str, confirm: bool = False) -> dict:
    """MUTATION (HIGH, lockout-class): delete an auth realm. Dry-run by default — the PLAN reads
    users to count who can no longer log in, and refuses built-in pam/pve. confirm=True."""
    _, api, _, _ = _svc()
    tgt = f"realm/{realm}"
    plan = _plan("pve_realm_delete", tgt, lambda: plan_realm_delete(api, realm))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_realm_delete", tgt,
                    lambda: realm_delete(api, realm),
                    mutation=True, outcome="ok", detail={"confirmed": True})


def main() -> None:
    # `proximo doctor` — verify your token/config (read-only preflight) BEFORE wiring Proximo into
    # an AI client. Prints what THIS token can and cannot do; never starts the server.
    if len(sys.argv) > 1 and sys.argv[1] == "doctor":
        import json
        try:
            result = pve_doctor()
        except Exception as e:  # config/token/connectivity problem — give a plain message, not a trace
            print(f"proximo doctor: {e}", file=sys.stderr)
            raise SystemExit(1) from None
        print(json.dumps(result, indent=2))
        return
    print(BANNER, file=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    main()
