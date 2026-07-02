"""Node-lifecycle plane: disks, storage backends, node config (time/hosts/dns/certs), and bulk power
(startall/stopall/migrateall).

Split out of proximo.server (2026-07-02) — see proximo/server.py's module
docstring for the funnel these wrappers depend on.
"""
from __future__ import annotations

from typing import Any

import proximo.server as _proximo_server
from proximo.node_lifecycle import (
    _key_fingerprint,
    plan_node_cert_delete,
    plan_node_cert_upload,
    plan_node_disk_initgpt,
    plan_node_disk_wipe,
    plan_node_dns_set,
    plan_node_hosts_set,
    plan_node_migrateall,
    plan_node_startall,
    plan_node_stopall,
    plan_node_storage_backend_create,
    plan_node_storage_backend_delete,
    plan_node_time_set,
)
from proximo.server import (
    _audited,
    _plan,
    tool,
)

# --- node-lifecycle plane (Wave 4) ---

# --- Disks (reads) ---

@tool()
def pve_node_disks_list(node: str | None = None) -> list:
    """List physical disks on a PVE node (read).

    GET /nodes/{node}/disks/list — physical disk inventory and health info.
    Smoke-confirm: response shape not live-verified.
    """
    cfg, api, _, _ = _proximo_server._svc()
    return _audited("pve_node_disks_list", node or cfg.node,
                    lambda: api.node_disks_list(node))


@tool()
def pve_node_disk_smart(disk: str, node: str | None = None) -> dict:
    """Get SMART health data for a disk on a PVE node (read).

    GET /nodes/{node}/disks/smart?disk=… — SMART attributes and health status.
    Smoke-confirm: GET (read) only — this tool does NOT trigger a self-test.
    """
    cfg, api, _, _ = _proximo_server._svc()
    return _audited("pve_node_disk_smart", f"{node or cfg.node}:{disk}",
                    lambda: api.node_disk_smart(disk, node))


# --- Disks (mutations) ---

@tool()
def pve_node_disk_wipe(disk: str, node: str | None = None,
                       confirm: bool = False) -> dict:
    """MUTATION: wipe ALL data and the partition table on a node disk.

    RISK_HIGH, NO UNDO: DESTROYS all data, partitions, and filesystems on the named disk.
    This is irreversible — all data is permanently erased. confirm=True to execute.

    PUT /nodes/{node}/disks/wipedisk
    Smoke-confirm: endpoint and body shape not live-verified.
    """
    cfg, api, _, _ = _proximo_server._svc()
    tgt = f"{node or cfg.node}/disks/{disk}"
    plan = _plan("pve_node_disk_wipe", tgt,
                 lambda: plan_node_disk_wipe(disk, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    # Async (worker UPID) like the sibling disk/storage ops — record "submitted", not "ok": the
    # ledger must not claim the wipe finished when only the task was accepted.
    return _audited("pve_node_disk_wipe", tgt,
                    lambda: api.node_disk_wipe(disk, node),
                    mutation=True, outcome="submitted",
                    detail={"disk": disk, "confirmed": True})


@tool()
def pve_node_disk_initgpt(disk: str, node: str | None = None,
                          confirm: bool = False) -> dict:
    """MUTATION: initialize a GPT partition table on a node disk.

    RISK_HIGH: overwrites the existing partition table on the named disk; irreversible.
    confirm=True to execute.

    POST /nodes/{node}/disks/initgpt
    Smoke-confirm: endpoint and body shape not live-verified.
    """
    cfg, api, _, _ = _proximo_server._svc()
    tgt = f"{node or cfg.node}/disks/{disk}"
    plan = _plan("pve_node_disk_initgpt", tgt,
                 lambda: plan_node_disk_initgpt(disk, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_disk_initgpt", tgt,
                    lambda: api.node_disk_initgpt(disk, node),
                    mutation=True, outcome="submitted",
                    detail={"disk": disk, "confirmed": True})


# --- Storage backends (reads + mutations) ---

@tool()
def pve_node_storage_backend_list(backend: str, node: str | None = None) -> list:
    """List storage backends of a type on a PVE node (read).

    backend ∈ {lvm, lvmthin, zfs, directory}.
    GET /nodes/{node}/disks/{backend}
    Smoke-confirm: response shape not live-verified.
    """
    cfg, api, _, _ = _proximo_server._svc()
    return _audited("pve_node_storage_backend_list", f"{node or cfg.node}/disks/{backend}",
                    lambda: api.node_storage_backend_list(backend, node))


@tool()
def pve_node_storage_backend_create(
    backend: str,
    name: str,
    devices: str | None = None,
    node: str | None = None,
    confirm: bool = False,
    **kw: Any,
) -> dict:
    """MUTATION: create a storage backend on the node (lvm/lvmthin/zfs/directory).

    Per-backend required params:
      zfs:       devices (comma-sep disk list) + raidlevel
      lvm/lvmthin: devices (single disk)
      directory: devices (disk path) + filesystem (e.g. ext4)

    The named disk(s) are consumed by the new backend. confirm=True to execute.

    POST /nodes/{node}/disks/{backend}
    Smoke-confirm: endpoint and body shape not live-verified. May return a task UPID (async).
    """
    cfg, api, _, _ = _proximo_server._svc()
    tgt = f"{node or cfg.node}/disks/{backend}/{name}"
    plan = _plan("pve_node_storage_backend_create", tgt,
                 lambda: plan_node_storage_backend_create(backend, name, devices, node, **kw))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_storage_backend_create", tgt,
                    lambda: api.node_storage_backend_create(backend, name, node,
                                                            **({"devices": devices} if devices else {}),
                                                            **kw),
                    mutation=True, outcome="submitted",
                    detail={"backend": backend, "name": name, "confirmed": True})


@tool()
def pve_node_storage_backend_delete(
    backend: str,
    name: str,
    node: str | None = None,
    cleanup: bool = False,
    confirm: bool = False,
) -> dict:
    """MUTATION: destroy a storage backend on the node.

    RISK_HIGH, NO UNDO — backend-specific blast:
      zfs:        destroys the zpool and ALL data on it
      lvm/lvmthin: removes the VG — any storage built on it breaks
      directory:  removes the directory mapping (data on disk may persist)

    confirm=True to execute.

    DELETE /nodes/{node}/disks/{backend}/{name}
    Smoke-confirm: endpoint and params shape not live-verified.
    """
    cfg, api, _, _ = _proximo_server._svc()
    tgt = f"{node or cfg.node}/disks/{backend}/{name}"
    plan = _plan("pve_node_storage_backend_delete", tgt,
                 lambda: plan_node_storage_backend_delete(backend, name, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    # Async (worker UPID) like backend_create — record "submitted", not "ok".
    return _audited("pve_node_storage_backend_delete", tgt,
                    lambda: api.node_storage_backend_delete(backend, name, node, cleanup),
                    mutation=True, outcome="submitted",
                    detail={"backend": backend, "name": name, "confirmed": True})


# --- Node config (reads) ---

@tool()
def pve_node_time_get(node: str | None = None) -> dict:
    """Get the current time and timezone of a PVE node (read).

    GET /nodes/{node}/time — returns {localtime, time, timezone}.
    Smoke-confirm: response shape not live-verified.
    """
    cfg, api, _, _ = _proximo_server._svc()
    return _audited("pve_node_time_get", node or cfg.node,
                    lambda: api.node_time_get(node))


@tool()
def pve_node_hosts_get(node: str | None = None) -> dict:
    """Get the /etc/hosts content of a PVE node (read).

    GET /nodes/{node}/hosts — returns {data, digest}.
    Smoke-confirm: response shape not live-verified.
    """
    cfg, api, _, _ = _proximo_server._svc()
    return _audited("pve_node_hosts_get", node or cfg.node,
                    lambda: api.node_hosts_get(node))


# --- Node config (mutations) ---

@tool()
def pve_node_time_set(timezone: str, node: str | None = None,
                      confirm: bool = False) -> dict:
    """MUTATION: set the timezone on a PVE node.

    RISK_LOW. CAPTURE: reads the current timezone before planning; if unreadable → complete=False.
    Revert by re-applying the captured timezone. confirm=True to execute.

    PUT /nodes/{node}/time
    Smoke-confirm: endpoint and body shape not live-verified.
    """
    cfg, api, _, _ = _proximo_server._svc()
    tgt = f"{node or cfg.node}/time"
    plan = _plan("pve_node_time_set", tgt,
                 lambda: plan_node_time_set(api, timezone, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_time_set", tgt,
                    lambda: api.node_time_set(timezone, node),
                    mutation=True, outcome="ok",
                    detail={"timezone": timezone, "confirmed": True})


@tool()
def pve_node_hosts_set(
    data: str,
    node: str | None = None,
    digest: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: replace the /etc/hosts file on a PVE node.

    RISK_MEDIUM. CAPTURE: reads current /etc/hosts before planning (revert by re-applying captured
    content); if unreadable → complete=False. A bad /etc/hosts can break name resolution.
    confirm=True to execute.

    POST /nodes/{node}/hosts
    Smoke-confirm: endpoint and body shape not live-verified.
    """
    cfg, api, _, _ = _proximo_server._svc()
    tgt = f"{node or cfg.node}/hosts"
    plan = _plan("pve_node_hosts_set", tgt,
                 lambda: plan_node_hosts_set(api, data, node, digest))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_hosts_set", tgt,
                    lambda: api.node_hosts_set(data, node, digest),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True})


@tool()
def pve_node_dns_set(
    search: str | None = None,
    dns1: str | None = None,
    dns2: str | None = None,
    dns3: str | None = None,
    node: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: update DNS resolver configuration on a PVE node.

    RISK_MEDIUM (a wrong resolver config breaks name resolution cluster-wide — same failure
    mode as node hosts_set). CAPTURE: reads current DNS config before planning (reuse
    pve_node_dns read); if unreadable → complete=False. confirm=True to execute.

    PUT /nodes/{node}/dns
    Smoke-confirm: endpoint and body shape not live-verified.
    """
    cfg, api, _, _ = _proximo_server._svc()
    tgt = f"{node or cfg.node}/dns"
    plan = _plan("pve_node_dns_set", tgt,
                 lambda: plan_node_dns_set(api, search, dns1, dns2, dns3, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_dns_set", tgt,
                    lambda: api.node_dns_set(node, search, dns1, dns2, dns3),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True})


@tool()
def pve_node_cert_upload(
    certificates: str,
    key: str | None = None,
    node: str | None = None,
    force: bool = False,
    restart: bool = False,
    confirm: bool = False,
) -> dict:
    """MUTATION: upload a custom TLS certificate to a PVE node.

    RISK_HIGH, NO UNDO. A malformed cert/key can lock you out of the PVE web UI and API.
    restart=True reloads pveproxy after upload (brief service interruption).

    PRIVATE KEY REDACTION: the 'key' param is a TLS private key (secret). It is
    UNCONDITIONALLY redacted — it NEVER appears in the plan, change, current state,
    detail, or ledger (regardless of redact_ledger setting). Only {"key": "[redacted]"}
    is recorded. The cert body (certificates) is public and may appear in plans/logs.

    Revert: re-upload a correct cert, or use pve_node_cert_delete to revert to self-signed.
    confirm=True to execute.

    POST /nodes/{node}/certificates/custom
    Smoke-confirm: endpoint and body shape not live-verified.
    """
    cfg, api, _, _ = _proximo_server._svc()
    tgt = f"{node or cfg.node}/certificates/custom"

    # UNCONDITIONAL: key redacted always; never passes through plan factory or ledger.
    key_detail = _key_fingerprint()

    plan = _plan("pve_node_cert_upload", tgt,
                 lambda: plan_node_cert_upload(certificates, node, force, restart))
    if not confirm:
        # key_detail injected into return (but not into the Plan itself — plan factory has no key).
        return {"status": "plan", **plan.as_dict(), **key_detail}
    return _audited("pve_node_cert_upload", tgt,
                    lambda: api.node_cert_upload(certificates, node, key, force, restart),
                    mutation=True, outcome="ok",
                    detail={**key_detail, "confirmed": True})


@tool()
def pve_node_cert_delete(
    node: str | None = None,
    restart: bool = False,
    confirm: bool = False,
) -> dict:
    """MUTATION: delete the custom TLS certificate from a PVE node.

    RISK_MEDIUM: PVE reverts to its self-signed certificate (recoverable by re-uploading).
    restart=True reloads pveproxy after deletion. confirm=True to execute.

    DELETE /nodes/{node}/certificates/custom
    Smoke-confirm: endpoint and params shape not live-verified.
    """
    cfg, api, _, _ = _proximo_server._svc()
    tgt = f"{node or cfg.node}/certificates/custom"
    plan = _plan("pve_node_cert_delete", tgt,
                 lambda: plan_node_cert_delete(node, restart))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_cert_delete", tgt,
                    lambda: api.node_cert_delete(node, restart),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True})


# --- Bulk power (mutations) ---

@tool()
def pve_node_startall(
    node: str | None = None,
    vms: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: start all (or filtered) guests on a PVE node.

    RISK_MEDIUM. Reversible — the inverse of pve_node_stopall. vms = optional CSV of VMIDs
    to filter the scope. confirm=True to execute.

    POST /nodes/{node}/startall
    Smoke-confirm: endpoint and vms param format not live-verified. May return task UPID.
    """
    cfg, api, _, _ = _proximo_server._svc()
    tgt = f"{node or cfg.node}/startall"
    plan = _plan("pve_node_startall", tgt,
                 lambda: plan_node_startall(node, vms))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_startall", tgt,
                    lambda: api.node_startall(node, vms),
                    mutation=True, outcome="submitted",
                    detail={"confirmed": True, **({"vms": vms} if vms else {})})


@tool()
def pve_node_stopall(
    node: str | None = None,
    vms: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: stop ALL (or filtered) running guests on a PVE node.

    RISK_HIGH — fleet-wide service outage unless vms filters the scope.
    Reversible via pve_node_startall, but guests must be restarted inside. confirm=True to execute.

    POST /nodes/{node}/stopall
    Smoke-confirm: endpoint and vms param format not live-verified. May return task UPID.
    """
    cfg, api, _, _ = _proximo_server._svc()
    tgt = f"{node or cfg.node}/stopall"
    plan = _plan("pve_node_stopall", tgt,
                 lambda: plan_node_stopall(node, vms))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_stopall", tgt,
                    lambda: api.node_stopall(node, vms),
                    mutation=True, outcome="submitted",
                    detail={"confirmed": True, **({"vms": vms} if vms else {})})


@tool()
def pve_node_migrateall(
    target: str,
    node: str | None = None,
    vms: str | None = None,
    maxworkers: int | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: migrate all (or filtered) guests from a node to a target node.

    RISK_HIGH, NOT auto-reversible: reversal requires a second pve_node_migrateall back,
    which may not restore the original state. target = destination node name (required).
    confirm=True to execute.

    POST /nodes/{node}/migrateall
    Smoke-confirm: endpoint and body shape not live-verified. May return task UPID.
    """
    cfg, api, _, _ = _proximo_server._svc()
    tgt = f"{node or cfg.node}/migrateall->{target}"
    plan = _plan("pve_node_migrateall", tgt,
                 lambda: plan_node_migrateall(target, node, vms, maxworkers))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_migrateall", tgt,
                    lambda: api.node_migrateall(target, node, vms, maxworkers),
                    mutation=True, outcome="submitted",
                    detail={"target": target, "confirmed": True})
