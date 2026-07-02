"""PVE guest lifecycle: node/guest status & power, snapshots/undo, in-container diagnostics (read), backup &
restore, provisioning, storage/ISO, guest config edit, disk ops, and cloud-init/template tools.

Split out of proximo.server (2026-07-02) — see proximo/server.py's module
docstring for the funnel these wrappers depend on.
"""
from __future__ import annotations

import proximo.server as _proximo_server
from proximo.backends import _check_vmid
from proximo.cloudinit import (
    capture_cloudinit_undo,
    cloudinit_get,
    cloudinit_set,
    plan_cloudinit_set,
    plan_template_convert,
    template_convert,
)
from proximo.config_edit import (
    guest_config_get,
    guest_config_revert,
    guest_config_set,
    plan_config_revert,
    plan_config_set,
)
from proximo.diagnose import (
    diagnose_container,
    diagnose_node,
)
from proximo.disk_ops import (
    disk_move,
    disk_resize,
    plan_disk_move,
    plan_disk_resize,
)
from proximo.doctor import doctor_check
from proximo.planning import (
    plan_power,
    plan_rollback,
    plan_snapshot_create,
    plan_snapshot_delete,
)
from proximo.provisioning import (
    clone_guest,
    create_container,
    create_vm,
    delete_guest,
    plan_clone,
    plan_create,
    plan_delete,
)
from proximo.server import (
    _audited,
    _blocked_allowlist,
    _exec_disabled,
    _plan,
    tool,
)
from proximo.storage import (
    content_delete,
    plan_content_delete,
    plan_storage_download,
    storage_content,
    storage_download_url,
    storage_status,
)

# --- Management (REST API, read) ---

@tool()
def pve_node_status(node: str | None = None) -> dict:
    """Health and resource status of a Proxmox node."""
    cfg, api, _, _ = _proximo_server._svc()
    return _audited("pve_node_status", node or cfg.node, lambda: api.node_status(node))


@tool()
def pve_list_guests(node: str | None = None) -> list[dict]:
    """List all VMs and LXC containers on a node, with state."""
    cfg, api, _, _ = _proximo_server._svc()
    return _audited("pve_list_guests", node or cfg.node, lambda: api.list_guests(node))


@tool()
def pve_guest_status(vmid: str, kind: str = "lxc", node: str | None = None) -> dict:
    """Status/config of one guest (kind = 'lxc' or 'qemu')."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_guest_status", f"{kind}/{vmid}", lambda: api.guest_status(vmid, kind, node))


# --- Management (REST API, MUTATION — confirm-gated) ---

@tool()
def pve_guest_power(
    vmid: str, action: str, kind: str = "lxc", node: str | None = None, confirm: bool = False
) -> dict:
    """MUTATION: start/stop/reboot/shutdown a guest.

    Dry-run by default: without confirm=True you get a PLAN — the exact change, the guest's live
    state, blast radius, and risk (with no-op detection) — recorded to the ledger. Re-call with
    confirm=True to execute. The plan is recorded on BOTH paths: even a one-shot confirm=True call
    records its plan before mutating — no plan, no mutation.
    """
    _, api, _, _ = _proximo_server._svc()
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

@tool()
def pve_snapshot_list(vmid: str, kind: str = "lxc", node: str | None = None) -> list[dict]:
    """List a guest's snapshots (read)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_snapshot_list", f"{kind}/{vmid}", lambda: api.snapshot_list(vmid, kind, node))


@tool()
def pve_snapshot_create(vmid: str, snapname: str, kind: str = "lxc", node: str | None = None,
                        description: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create a snapshot (a restore point). Dry-run by default; confirm=True to execute.
    Async — returns the task UPID; poll pve_task_status. Needs snapshot-capable storage (ZFS/BTRFS/LVM-thin)."""
    _, api, _, _ = _proximo_server._svc()
    target = f"{kind}/{vmid}:{snapname}"
    plan = _plan("pve_snapshot_create", target, lambda: plan_snapshot_create(vmid, snapname, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_snapshot_create", target,
                    lambda: api.snapshot_create(vmid, snapname, kind, node, description),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@tool()
def pve_rollback(vmid: str, snapname: str, kind: str = "lxc", node: str | None = None,
                 confirm: bool = False) -> dict:
    """MUTATION (DESTRUCTIVE): roll a guest back to a snapshot — discards ALL changes since it.
    Dry-run by default (the PLAN spells out the blast radius); confirm=True to execute. Async -> UPID."""
    _, api, _, _ = _proximo_server._svc()
    target = f"{kind}/{vmid}:{snapname}"
    plan = _plan("pve_rollback", target, lambda: plan_rollback(api, vmid, snapname, kind, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_rollback", target,
                    lambda: api.snapshot_rollback(vmid, snapname, kind, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@tool()
def pve_snapshot_delete(vmid: str, snapname: str, kind: str = "lxc", node: str | None = None,
                        force: bool = False, confirm: bool = False) -> dict:
    """MUTATION: delete a snapshot (removes a restore point). Dry-run by default; confirm=True to execute.
    Async -> UPID."""
    _, api, _, _ = _proximo_server._svc()
    target = f"{kind}/{vmid}:{snapname}"
    plan = _plan("pve_snapshot_delete", target, lambda: plan_snapshot_delete(vmid, snapname, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_snapshot_delete", target,
                    lambda: api.snapshot_delete(vmid, snapname, kind, node, force),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@tool()
def pve_task_status(upid: str, node: str | None = None) -> dict:
    """Status of an async Proxmox task (running/stopped + exit status) — poll snapshot/rollback ops (read)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_task_status", upid, lambda: api.task_status(upid, node))


# --- In-container (read) ---

@tool()
def ct_logs(ctid: str, unit: str, lines: int = 50) -> dict:
    """Tail journalctl for a systemd unit inside a container (read-only)."""
    cfg, _, exec_, _ = _proximo_server._svc()
    detail = {"unit": unit, "lines": lines}
    if not cfg.enable_exec:
        return _exec_disabled("ct_logs", str(ctid), detail, mutation=False)
    ctid = _check_vmid(ctid)  # L07: validate CTID format at server layer before allowlist gate
    if not cfg.ct_permitted(ctid):
        return _blocked_allowlist("ct_logs", str(ctid), detail, mutation=False)

    def _do() -> dict:
        r = exec_.logs(ctid, unit, lines=lines)
        return {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr}

    return _audited("ct_logs", str(ctid), _do, detail=detail)


@tool()
def ct_diagnose(ctid: str, kind: str = "lxc", node: str | None = None) -> dict:
    """READ-ONLY: gather 'what's broken' evidence for a container — API status + a fixed read-only
    in-container battery (failed units, disk, recent errors, memory, listening ports) + advisory flags.

    No mutation, no confirm. The in-container probes need PROXIMO_ENABLE_EXEC and the CTID allowlist
    (same as ct_logs); with exec off it returns the API-only part and discloses the skipped probes."""
    cfg, api, exec_, _ = _proximo_server._svc()
    ctid = _check_vmid(ctid)  # L07: validate CTID at server layer before the allowlist gate / ledger target
    target = f"{kind}/{ctid}"
    if cfg.enable_exec and not cfg.ct_permitted(ctid):
        return _blocked_allowlist("ct_diagnose", str(ctid), mutation=False)
    use_exec = exec_ if cfg.enable_exec else None
    return _audited("ct_diagnose", target, lambda: diagnose_container(api, use_exec, ctid, kind, node))


@tool()
def pve_diagnose(node: str | None = None) -> dict:
    """READ-ONLY: gather node health evidence — status + storage usage + recent failed tasks + flags."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_diagnose", node or "node", lambda: diagnose_node(api, node))


@tool()
def pve_doctor() -> dict:
    """READ-ONLY preflight: check API connectivity + the calling token's effective permissions, and
    report what this token CAN and CANNOT do — with the privilege + role to grant for each gap. Run
    this FIRST after install to verify your config/token before wiring Proximo into an MCP client."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_doctor", "preflight", lambda: doctor_check(api), mutation=False)


# --- Provisioning (REST API, async). create/clone are additive; delete is DESTRUCTIVE. ---

@tool()
def pve_create_container(vmid: str, ostemplate: str, storage: str, node: str | None = None,
                         options: dict | None = None, confirm: bool = False) -> dict:
    """MUTATION: create a new LXC container. Dry-run by default; confirm=True. Async — returns a UPID.
    `options` carries extra create params (cores, memory, net0, rootfs, password, ...)."""
    _, api, _, _ = _proximo_server._svc()
    target = f"lxc/{vmid}"
    plan = _plan("pve_create_container", target,
                 lambda: plan_create(api, vmid, "lxc", node,
                                     {"ostemplate": ostemplate, "storage": storage, **(options or {})}))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited(
        "pve_create_container", target,
        lambda: create_container(api, vmid, ostemplate, storage, node, **(options or {})),
        mutation=True, outcome="submitted", detail={"confirmed": True})


@tool()
def pve_create_vm(vmid: str, node: str | None = None, options: dict | None = None,
                  confirm: bool = False) -> dict:
    """MUTATION: create a new QEMU VM. Dry-run by default; confirm=True. Async — returns a UPID.
    `options` carries create params (cores, memory, net0, scsi0, ostype, ...)."""
    _, api, _, _ = _proximo_server._svc()
    target = f"qemu/{vmid}"
    plan = _plan("pve_create_vm", target, lambda: plan_create(api, vmid, "qemu", node, options or {}))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_create_vm", target,
                    lambda: create_vm(api, vmid, node, **(options or {})),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@tool()
def pve_clone(vmid: str, newid: str, kind: str = "lxc", node: str | None = None,
              name: str | None = None, full: bool = False, pool: str | None = None,
              storage: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: clone a guest to a new id. Dry-run by default; confirm=True. Async — returns a UPID.
    pool: place the new guest in a resource pool (needed when the token is pool-scoped).
    storage: target storage for the full clone's disks (full=True only) — keeps a clone off the
    source storage; refused for a linked clone (PVE only honors it on a full clone)."""
    _, api, _, _ = _proximo_server._svc()
    target = f"{kind}/{vmid}->{newid}"
    plan = _plan("pve_clone", target,
                 lambda: plan_clone(api, vmid, newid, kind, node, storage, full, name, pool))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_clone", target,
                    lambda: clone_guest(api, vmid, newid, kind, node, name, full, pool, storage),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@tool()
def pve_delete_guest(vmid: str, kind: str = "lxc", node: str | None = None, purge: bool = False,
                     force: bool = False, confirm: bool = False) -> dict:
    """MUTATION (DESTRUCTIVE, IRREVERSIBLE): permanently destroy a guest and its disks. Dry-run by
    default — the PLAN names exactly what will be destroyed. confirm=True to execute. Async — UPID."""
    _, api, _, _ = _proximo_server._svc()
    target = f"{kind}/{vmid}"
    plan = _plan("pve_delete_guest", target, lambda: plan_delete(api, vmid, kind, node, purge, force))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_delete_guest", target,
                    lambda: delete_guest(api, vmid, kind, node, purge, force),
                    mutation=True, outcome="submitted", detail={"confirmed": True, "purge": purge})


# --- Storage / ISO / templates (REST API) ---

@tool()
def pve_storage_content(storage: str, node: str | None = None,
                        content: str | None = None) -> list[dict]:
    """List a storage's content, optionally filtered (content = iso | vztmpl | backup) (read)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_storage_content", storage,
                    lambda: storage_content(api, storage, node, content))


@tool()
def pve_storage_status(storage: str, node: str | None = None) -> dict:
    """Status of a storage — total/used/avail/enabled (read)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_storage_status", storage, lambda: storage_status(api, storage, node))


@tool()
def pve_storage_download(storage: str, content: str, url: str, filename: str,
                         node: str | None = None, checksum: str | None = None,
                         checksum_algorithm: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: download an ISO (content=iso) or CT template (content=vztmpl) from a URL into a
    storage. Dry-run by default; confirm=True. Async — returns a UPID."""
    _, api, _, _ = _proximo_server._svc()
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


@tool()
def pve_storage_content_delete(storage: str, volid: str, node: str | None = None,
                               confirm: bool = False) -> dict:
    """MUTATION: delete a content volume (ISO / template / backup) from storage. Dry-run by default
    (HIGH risk for a backup volume); confirm=True. Async — UPID or null."""
    _, api, _, _ = _proximo_server._svc()
    plan = _plan("pve_storage_content_delete", volid, lambda: plan_content_delete(api, storage, volid))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_storage_content_delete", volid,
                    lambda: content_delete(api, storage, volid, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


# --- Guest config edit (REST API). Config PUT is SYNCHRONOUS -> outcome="ok". ---

@tool()
def pve_guest_config_get(vmid: str, kind: str = "lxc", node: str | None = None) -> dict:
    """Read a guest's current config (kind = 'lxc' or 'qemu') (read)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_guest_config_get", f"{kind}/{vmid}",
                    lambda: guest_config_get(api, vmid, kind, node))


@tool()
def pve_guest_config_set(vmid: str, changes: dict, kind: str = "lxc", node: str | None = None,
                         confirm: bool = False) -> dict:
    """MUTATION: edit a guest's config (cores/memory/net/onboot/...). Dry-run by default — the PLAN
    shows the exact per-key diff; confirm=True to execute. Captures the prior config first so the
    change is revertible via pve_guest_config_revert. Synchronous."""
    _, api, _, _ = _proximo_server._svc()
    target = f"{kind}/{vmid}"
    plan = _plan("pve_guest_config_set", target,
                 lambda: plan_config_set(api, vmid, changes, kind, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_guest_config_set", target,
                    lambda: guest_config_set(api, vmid, changes, kind, node),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_guest_config_revert(vmid: str, prior_config: dict, kind: str = "lxc",
                            node: str | None = None, confirm: bool = False) -> dict:
    """MUTATION (UNDO): re-apply a previously captured guest config (the prior_config returned by
    pve_guest_config_set). Dry-run by default; confirm=True to execute. Synchronous."""
    _, api, _, _ = _proximo_server._svc()
    target = f"{kind}/{vmid}"
    plan = _plan("pve_guest_config_revert", target,
                 lambda: plan_config_revert(api, vmid, prior_config, kind, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_guest_config_revert", target,
                    lambda: guest_config_revert(api, vmid, prior_config, kind, node),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- Disk ops (REST API). Resize/move are async -> task UPID -> outcome="submitted". ---

@tool()
def pve_disk_resize(vmid: str, disk: str, size: str, kind: str = "lxc", node: str | None = None,
                    confirm: bool = False) -> dict:
    """MUTATION: grow a guest disk (e.g. size='+10G'). GROW ONLY — a shrink is refused (destructive).
    Dry-run by default; confirm=True to execute. Async — returns a task UPID."""
    _, api, _, _ = _proximo_server._svc()
    target = f"{kind}/{vmid}:{disk}"
    plan = _plan("pve_disk_resize", target,
                 lambda: plan_disk_resize(api, vmid, disk, size, kind, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_disk_resize", target,
                    lambda: disk_resize(api, vmid, disk, size, kind, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@tool()
def pve_disk_move(vmid: str, disk: str, target_storage: str, kind: str = "lxc",
                  node: str | None = None, delete_source: bool = False,
                  confirm: bool = False) -> dict:
    """MUTATION: move a guest disk to another storage. Dry-run by default — the PLAN shows
    source->target and whether the source copy is deleted (delete_source=True is HIGH). confirm=True
    to execute. Async — returns a task UPID."""
    _, api, _, _ = _proximo_server._svc()
    target = f"{kind}/{vmid}:{disk}"
    plan = _plan("pve_disk_move", target,
                 lambda: plan_disk_move(api, vmid, disk, target_storage, kind, node, delete_source))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_disk_move", target,
                    lambda: disk_move(api, vmid, disk, target_storage, kind, node, delete_source),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


# --- Cloud-init + template (REST API, QEMU). Config POST is synchronous -> outcome="ok". ---

@tool()
def pve_cloudinit_get(vmid: str, node: str | None = None, kind: str = "qemu") -> dict:
    """Read a QEMU guest's cloud-init config (secret fields are masked) (read)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_cloudinit_get", f"{kind}/{vmid}",
                    lambda: cloudinit_get(api, vmid, node, kind))


@tool()
def pve_cloudinit_set(vmid: str, changes: dict, node: str | None = None, kind: str = "qemu",
                      confirm: bool = False) -> dict:
    """MUTATION: set cloud-init fields (ciuser/sshkeys/ipconfigN/...) on a QEMU guest. Dry-run by
    default — the PLAN shows the diff with secrets masked; confirm=True to execute. Synchronous.
    Secret fields (cipassword) are never echoed to results or the ledger."""
    _, api, _, _ = _proximo_server._svc()
    target = f"{kind}/{vmid}"
    plan = _plan("pve_cloudinit_set", target,
                 lambda: plan_cloudinit_set(api, vmid, changes, node, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    # Capture the prior cloud-init config (secret-stripped) BEFORE the set, so the result carries
    # a real undo_record. A config edit is not blocked on undo-capture failure (unlike exec) — but
    # the degraded UNDO must NOT be silent: surface it in the status AND the PROVE ledger (M-1).
    try:
        undo = capture_cloudinit_undo(api, vmid, node, kind)
        outcome = "ok"
    except Exception as e:
        undo = {"prior_ci_config": None,
                "secret_undo_caveat": f"undo capture failed: {type(e).__name__}"}
        outcome = "ok:undo_unavailable"  # mutation ran, but no rollback was captured — recorded, not silent
    envelope = _audited("pve_cloudinit_set", target,
                        lambda: cloudinit_set(api, vmid, changes, node, kind),
                        mutation=True, outcome=outcome, detail={"confirmed": True})
    envelope["undo_record"] = undo
    return envelope


@tool()
def pve_template_convert(vmid: str, node: str | None = None, kind: str = "qemu",
                         confirm: bool = False) -> dict:
    """MUTATION (IRREVERSIBLE): convert a guest into a template — effectively one-way. Dry-run by
    default (the PLAN flags it HIGH/irreversible); confirm=True to execute."""
    _, api, _, _ = _proximo_server._svc()
    target = f"{kind}/{vmid}"
    plan = _plan("pve_template_convert", target,
                 lambda: plan_template_convert(api, vmid, node, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_template_convert", target,
                    lambda: template_convert(api, vmid, node, kind),
                    mutation=True, outcome="submitted", detail={"confirmed": True})
