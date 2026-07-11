"""Proximo node-lifecycle plane — physical disks, storage backends, host config (time/hosts/dns/cert),
and bulk guest power.

Endpoints (all under /nodes/{node}/...):

  Disks:
    GET    /disks/list                   — pve_node_disks_list         (read)
    GET    /disks/smart?disk=…           — pve_node_disk_smart         (read; GET only, NOT a self-test trigger)
    PUT    /disks/wipedisk               — pve_node_disk_wipe          (MUTATION, HIGH, no undo)
    POST   /disks/initgpt                — pve_node_disk_initgpt       (MUTATION, HIGH)
    GET    /disks/{backend}              — pve_node_storage_backend_list (read)
    POST   /disks/{backend}              — pve_node_storage_backend_create (MUTATION, HIGH)
    DELETE /disks/{backend}/{name}       — pve_node_storage_backend_delete (MUTATION, HIGH, no undo)

  Node config:
    GET    /time                         — pve_node_time_get            (read)
    PUT    /time                         — pve_node_time_set            (MUTATION, LOW, CAPTURE)
    GET    /hosts                        — pve_node_hosts_get           (read)
    POST   /hosts                        — pve_node_hosts_set           (MUTATION, MEDIUM, CAPTURE)
    PUT    /dns                          — pve_node_dns_set             (MUTATION, MEDIUM, CAPTURE)
    POST   /certificates/custom         — pve_node_cert_upload          (MUTATION, HIGH, no undo)
    DELETE /certificates/custom         — pve_node_cert_delete          (MUTATION, MEDIUM)

  Bulk power:
    POST   /startall                     — pve_node_startall            (MUTATION, MEDIUM)
    POST   /stopall                      — pve_node_stopall             (MUTATION, HIGH)
    POST   /migrateall                   — pve_node_migrateall          (MUTATION, HIGH)

VERIFIED live (PVE 9.2, reads only, 2026-06-25): disks_list, disk_smart (GET — the READ form, NOT a
self-test trigger), storage_backend_list (lvm → a VG TREE dict; lvmthin/zfs/directory → a list),
time_get ({localtime,time,timezone}), hosts_get ({data,digest}), dns. The MUTATIONS remain
Smoke-confirm — they were NEVER live-fired (disk wipe/initgpt, backend create/delete, cert upload/delete,
and node-wide bulk power are too destructive/fleet-impacting to smoke on the single prod node);
their plan path (read-only preview) is verified + redteamed.

EXCLUSION: POST /nodes/{node}/execute (host root shell) is deliberately excluded from this surface.
It is too dangerous for the default surface; a future PROXIMO_ENABLE_NODE_EXEC wave could add it
under a separate opt-in gate.

Security posture:
- All path components validated with \\Z-anchored regexes (trailing-newline bypass rejected).
- Backend ∈ closed {lvm, lvmthin, zfs, directory} (no arbitrary string into URL path).
- Disk path: /dev/… pattern; component-level check rejects ".." traversal.
- Storage name: alnum + underscore + hyphen, leading alnum.
- Cert private key: UNCONDITIONALLY redacted — never appears in plan, change, current, detail, or
  ledger, even with redact_ledger=False. _key_fingerprint() records {"key": "[redacted]"}.
  The cert body (certificates, public data) may appear in plans/logs.
- CAPTURE-or-declare: time/hosts/dns_set factories read current state before planning;
  on read failure → complete=False + note "could not capture current state — no guided revert".
"""

from __future__ import annotations

from typing import Any

from .backends import (
    ProximoError,
    _check_backend,
    _check_disk,
    _check_node,
    _check_storage_name,
    _check_timezone,
)
from .planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM, Plan


def _key_fingerprint() -> dict:
    """Unconditional redaction for TLS private keys — never store even a hash."""
    return {"key": "[redacted]"}


# ---------------------------------------------------------------------------
# Validators (plane-level wrappers around backend validators + per-backend param checks)
# ---------------------------------------------------------------------------

def _check_backend_create_params(backend: str, devices: str | None, **kw: Any) -> None:
    """Per-backend required-param validation for storage_backend_create.

    zfs:        requires devices (disk list) + raidlevel (must be a non-empty string; bool/int rejected)
    lvm/lvmthin: requires devices (single disk); rejects any non-None raidlevel
    directory:  requires devices (disk path) + filesystem; rejects any non-None raidlevel
    """
    if backend == "zfs":
        if not devices:
            raise ProximoError("zfs backend requires 'devices' (disk list)")
        rl = kw.get("raidlevel")
        if not isinstance(rl, str) or not rl:
            raise ProximoError(
                "zfs backend requires 'raidlevel' as a non-empty string (e.g. raid1, raidz, single)"
            )
    elif backend in ("lvm", "lvmthin"):
        if not devices:
            raise ProximoError(f"{backend} backend requires 'devices' (disk path, e.g. /dev/sdb)")
        if kw.get("raidlevel") is not None:
            raise ProximoError(f"{backend} backend does not accept 'raidlevel'")
    elif backend == "directory":
        if not devices:
            raise ProximoError("directory backend requires 'devices' (disk path)")
        if not kw.get("filesystem"):
            raise ProximoError("directory backend requires 'filesystem' (e.g. ext4, xfs)")
        if kw.get("raidlevel") is not None:
            raise ProximoError("directory backend does not accept 'raidlevel'")


# ---------------------------------------------------------------------------
# Plan factories — Disks
# ---------------------------------------------------------------------------

def plan_node_disk_wipe(disk: str, node: str | None = None) -> Plan:
    """Plan for pve_node_disk_wipe — wipe all data and partition table on a disk.

    RISK_HIGH, no undo: this destroys all data on the named disk.
    """
    _check_disk(disk)
    _check_node(node)
    return Plan(
        action="pve_node_disk_wipe",
        target=f"node/{node or 'default'}/disks/{disk}",
        change=f"DESTROYS all data/partition table on {disk}; irreversible",
        current={},
        blast_radius=[
            f"disk {disk}: DESTROYS all data, partition table, and filesystems on this device"
        ],
        risk=RISK_HIGH,
        risk_reasons=[
            f"wipes the entire block device {disk} — all data, partitions, and filesystems are lost; "
            "no undo possible"
        ],
        note=(
            f"No undo: PUT /disks/wipedisk on {disk} is a destructive, irreversible operation. "
            "All data on the disk is permanently erased."
        ),
    )


def plan_node_disk_initgpt(disk: str, node: str | None = None) -> Plan:
    """Plan for pve_node_disk_initgpt — initialize a GPT partition table on a disk.

    RISK_HIGH: overwrites the existing partition table; irreversible.
    """
    _check_disk(disk)
    _check_node(node)
    return Plan(
        action="pve_node_disk_initgpt",
        target=f"node/{node or 'default'}/disks/{disk}",
        change=f"writes a new GPT partition table on {disk}; overwrites existing partition table",
        current={},
        blast_radius=[
            f"disk {disk}: overwrites the partition table — existing partitions and their data "
            "are rendered inaccessible"
        ],
        risk=RISK_HIGH,
        risk_reasons=[
            f"initializes a new GPT partition table on {disk}, destroying the existing one; "
            "irreversible — any data in overwritten partition table entries is lost"
        ],
        note=(
            f"No undo: POST /disks/initgpt on {disk} overwrites the partition table. "
            "Data on partitions may survive but existing layout is lost. Irreversible."
        ),
    )


def plan_node_storage_backend_create(
    backend: str,
    name: str,
    devices: str | None = None,
    node: str | None = None,
    **kw: Any,
) -> Plan:
    """Plan for pve_node_storage_backend_create — create a storage backend on the node.

    Per-backend required-param validation is enforced here.
    The named disk(s) are consumed by the new backend.
    """
    _check_backend(backend)
    _check_storage_name(name)
    _check_node(node)
    _check_backend_create_params(backend, devices, **kw)
    # Disclose the per-backend params actually being applied (e.g. zfs raidlevel, directory
    # filesystem) — these are materially consequential (redundancy/format) and must be visible
    # in the preview, not just validated silently. Mirrors hw_mappings.py's plan_mapping_pci_create.
    extra = {k: v for k, v in kw.items() if v is not None}
    return Plan(
        action="pve_node_storage_backend_create",
        target=f"node/{node or 'default'}/disks/{backend}/{name}",
        change=(
            f"create {backend} storage backend {name!r}"
            + (f" on device(s) {devices!r}" if devices else "")
            + (f" ({extra})" if extra else "")
        ),
        current={},
        blast_radius=[
            f"FORMATS disk(s) {devices!r} into the new {backend} backend {name!r} — any pre-existing "
            "data on those disks is destroyed immediately and irreversibly"
            + (f"; backend params: {extra}" if extra else "")
        ],
        risk=RISK_HIGH,
        risk_reasons=[
            f"creates a {backend} backend on {devices!r} — formatting is immediate and destroys any "
            "pre-existing data on the named disk(s); as irreversible as the delete"
        ],
        note=(
            f"No undo: creating the {backend} backend FORMATS the named disk(s) — pre-existing data is "
            f"lost. Deleting the backend (pve_node_storage_backend_delete) does NOT restore it."
            + (f" Backend params: {extra}." if extra else "")
        ),
    )


def plan_node_storage_backend_delete(
    backend: str,
    name: str,
    node: str | None = None,
    cleanup: bool = False,
) -> Plan:
    """Plan for pve_node_storage_backend_delete — delete a storage backend.

    RISK_HIGH, no undo: backend-specific blast wording names the target.

    cleanup=True sends cleanup-disks=1 to PVE — an ADDITIONAL destructive action that wipes
    the underlying disk(s), not just removing the config mapping. Disclosed explicitly below
    since it contradicts the directory backend's default "data may persist" wording.
    """
    _check_backend(backend)
    _check_storage_name(name)
    _check_node(node)
    if backend == "zfs":
        blast_detail = f"destroys the zpool {name!r} and ALL data on it; irreversible"
        risk_reason = (
            f"zfs: destroys zpool {name!r} and ALL data stored on it — no recovery possible; "
            "irreversible"
        )
    elif backend in ("lvm", "lvmthin"):
        blast_detail = (
            f"removes the VG {name!r} — any storage built on it breaks; irreversible"
        )
        risk_reason = (
            f"{backend}: removes volume group {name!r} — any LVs (VMs, containers) built on it "
            "become inaccessible; irreversible"
        )
    else:  # directory
        blast_detail = (
            f"removes the directory mapping {name!r}; data on the underlying disk may persist "
            "but the storage backend is destroyed"
        )
        risk_reason = (
            f"directory: removes the directory mapping {name!r} — Proxmox will no longer manage "
            "this storage path; data on the underlying disk may persist but is unmanaged"
        )
    if cleanup:
        blast_detail += " (cleanup=True: the underlying disk(s) are ALSO wiped)"
        risk_reason += "; cleanup=True additionally wipes the underlying disk(s)"
    return Plan(
        action="pve_node_storage_backend_delete",
        target=f"node/{node or 'default'}/disks/{backend}/{name}",
        change=f"delete {backend} backend {name!r}: {blast_detail}",
        current={},
        blast_radius=[
            f"{backend} backend {name!r}: {blast_detail}"
        ],
        risk=RISK_HIGH,
        risk_reasons=[risk_reason],
        note=(
            f"No undo: DELETE /disks/{backend}/{name!r} is irreversible. "
            "Ensure any VMs/containers using this storage are migrated or deleted first."
        ),
    )


# ---------------------------------------------------------------------------
# Plan factories — Node config (CAPTURE-or-declare)
# ---------------------------------------------------------------------------

def plan_node_time_set(api: Any, timezone: str, node: str | None = None) -> Plan:
    """Plan for pve_node_time_set — set the node timezone.

    CAPTURE-or-declare: reads current timezone via GET /time; on failure → complete=False.
    """
    _check_timezone(timezone)
    _check_node(node)
    n = node or api.config.node
    current: dict = {}
    complete = True
    note_capture = ""
    try:
        result = api.node_time_get(node)
        current = {"timezone": result.get("timezone", "unknown")}
    except Exception:
        complete = False
        note_capture = " Could not capture current timezone — no guided revert available."
    return Plan(
        action="pve_node_time_set",
        target=f"node/{n}/time",
        change=f"set node timezone to {timezone!r}",
        current=current,
        blast_radius=[f"node/{n} timezone configuration"],
        risk=RISK_LOW,
        risk_reasons=["timezone change takes effect immediately on the node"],
        complete=complete,
        note=(
            "Revert by re-applying the captured timezone with pve_node_time_set."
            + note_capture        ),
    )


def plan_node_hosts_set(
    api: Any,
    data: str,
    node: str | None = None,
    digest: str | None = None,
) -> Plan:
    """Plan for pve_node_hosts_set — replace the node's /etc/hosts.

    CAPTURE-or-declare: reads current /etc/hosts via GET /hosts; on failure → complete=False.
    MEDIUM risk: a bad /etc/hosts can break name resolution on the node.
    """
    _check_node(node)
    n = node or api.config.node
    current: dict = {}
    complete = True
    note_capture = ""
    try:
        result = api.node_hosts_get(node)
        current = {"data": result.get("data", ""), "digest": result.get("digest", "")}
    except Exception:
        complete = False
        note_capture = " Could not capture current /etc/hosts — no guided revert available."
    return Plan(
        action="pve_node_hosts_set",
        target=f"node/{n}/hosts",
        change="replaces the entire /etc/hosts; revert by re-applying the captured content",
        current=current,
        blast_radius=[
            f"node/{n} /etc/hosts — a bad entry can break name resolution, affecting "
            "Proxmox cluster communication and VM/container connectivity"
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "replaces the entire /etc/hosts file — a malformed entry can break name resolution "
            "on the node, potentially disrupting cluster communication"
        ],
        complete=complete,
        note=(
            "Revert by re-applying the captured data with pve_node_hosts_set."
            + note_capture        ),
    )


def plan_node_dns_set(
    api: Any,
    search: str | None = None,
    dns1: str | None = None,
    dns2: str | None = None,
    dns3: str | None = None,
    node: str | None = None,
) -> Plan:
    """Plan for pve_node_dns_set — update the node's DNS resolver configuration.

    CAPTURE-or-declare: reads current DNS via GET /dns (reuses node_dns_get path);
    on failure → complete=False.
    """
    _check_node(node)
    n = node or api.config.node
    current: dict = {}
    complete = True
    note_capture = ""
    try:
        result = api._get(f"/nodes/{n}/dns") or {}
        current = {k: result[k] for k in ("search", "dns1", "dns2", "dns3") if k in result}
    except Exception:
        complete = False
        note_capture = " Could not capture current DNS config — no guided revert available."
    changes = {k: v for k, v in {
        "search": search, "dns1": dns1, "dns2": dns2, "dns3": dns3
    }.items() if v is not None}
    return Plan(
        action="pve_node_dns_set",
        target=f"node/{n}/dns",
        change=f"update DNS resolver config: {changes}",
        current=current,
        blast_radius=[f"node/{n} DNS resolver config — affects name resolution for all guests and PVE services"],
        risk=RISK_MEDIUM,
        risk_reasons=["DNS config change takes effect immediately; incorrect config can break name "
                      "resolution cluster-wide (same failure mode as node hosts_set, which is also MEDIUM)"],
        complete=complete,
        note=(
            "Revert by re-applying the captured DNS settings with pve_node_dns_set."
            + note_capture        ),
    )


def plan_node_cert_upload(
    certificates: str,
    node: str | None = None,
    force: bool = False,
    restart: bool = False,
) -> Plan:
    """Plan for pve_node_cert_upload — upload a custom TLS certificate to the node.

    RISK_HIGH, no undo. Key NEVER appears in this function — unconditional redaction.
    The cert body (certificates) is public and may appear in the plan.
    """
    _check_node(node)
    # UNCONDITIONAL: key never passed to or from this function.
    # The server tool holds the key; only {"key": "[redacted]"} reaches the ledger.
    # The cert body (certificates) is PUBLIC and appears in the plan change for auditability.
    cert_preview = certificates[:64] + ("…" if len(certificates) > 64 else "")
    return Plan(
        action="pve_node_cert_upload",
        target=f"node/{node or 'default'}/certificates/custom",
        change=(
            f"upload custom TLS certificate to the node (cert body: {cert_preview!r})"
            + (" (force=True: overwrite existing)" if force else "")
            + (" (restart=True: reloads pveproxy)" if restart else "")
        ),
        current={},
        blast_radius=[
            "node TLS certificate: a malformed cert/key pair can lock you out of the PVE web "
            "UI and API; restart=True also reloads pveproxy (brief service interruption)"
        ],
        risk=RISK_HIGH,
        risk_reasons=[
            "a malformed cert/key can lock you out of the PVE web UI + API; "
            "no undo — re-upload a working cert or use pve_node_cert_delete to revert to self-signed"
        ],
        note=(
            "No undo: once uploaded, revert by re-uploading a good cert or by deleting the custom "
            "cert (pve_node_cert_delete) to fall back to PVE's self-signed certificate. "
            "Private key is unconditionally redacted from the ledger."
        ),
    )


def plan_node_cert_delete(
    node: str | None = None,
    restart: bool = False,
) -> Plan:
    """Plan for pve_node_cert_delete — delete the custom TLS certificate on the node.

    RISK_MEDIUM: recoverable — PVE reverts to its self-signed cert.
    """
    _check_node(node)
    return Plan(
        action="pve_node_cert_delete",
        target=f"node/{node or 'default'}/certificates/custom",
        change=(
            "remove the custom TLS certificate; PVE reverts to its self-signed cert"
            + (" (restart=True: reloads pveproxy)" if restart else "")
        ),
        current={},
        blast_radius=[
            "node TLS certificate: removes the custom cert — PVE reverts to self-signed; "
            "clients will see a TLS warning until a new cert is uploaded"
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "removes the custom TLS certificate — PVE reverts to its self-signed cert; "
            "recoverable by re-uploading a certificate"
        ],
        note=(
            "Recoverable: PVE reverts to its self-signed certificate. "
            "Re-upload a certificate with pve_node_cert_upload to restore custom TLS."
        ),
    )


# ---------------------------------------------------------------------------
# Plan factories — Bulk power
# ---------------------------------------------------------------------------

def plan_node_startall(
    node: str | None = None,
    vms: str | None = None,
) -> Plan:
    """Plan for pve_node_startall — start all (or filtered) guests on the node.

    RISK_MEDIUM: reversible — the inverse of pve_node_stopall.
    """
    _check_node(node)
    scope = f" (filtered: {vms!r})" if vms else " (all guests)"
    return Plan(
        action="pve_node_startall",
        target=f"node/{node or 'default'}/startall",
        change=f"start all guests on node{scope}",
        current={},
        blast_radius=[f"all stopped guests on node/{node or 'default'}{scope}"],
        risk=RISK_MEDIUM,
        risk_reasons=["starts all stopped guests — resource contention if many start simultaneously"],
        note=(
            "Reversible via pve_node_stopall. "
            "Smoke-confirm: verify the 'vms' param name/format against a live PVE instance."
        ),
    )


def plan_node_stopall(
    node: str | None = None,
    vms: str | None = None,
) -> Plan:
    """Plan for pve_node_stopall — stop all (or filtered) guests on the node.

    RISK_HIGH: halts EVERY running guest on the node — a node-wide service outage.
    Reversible via pve_node_startall (but guests must be restarted manually).
    """
    _check_node(node)
    scope = f" (filtered: {vms!r})" if vms else " (ALL guests)"
    return Plan(
        action="pve_node_stopall",
        target=f"node/{node or 'default'}/stopall",
        change=f"halts all running guests on {node or 'this node'}{scope} — a node-wide service outage",
        current={},
        blast_radius=[
            f"ALL running guests on node/{node or 'default'}: "
            f"halts all running guests on {node or 'the node'}{scope} — a node-wide service outage"
        ],
        risk=RISK_HIGH,
        risk_reasons=[
            "stops ALL running guests on the node — a fleet-wide service outage; "
            "reversible only via pve_node_startall (manual restart required)"
        ],
        note=(
            "Fleet-wide blast: this halts every running guest on the node unless 'vms' filters the scope. "
            "Reversible via pve_node_startall, but services must be manually restarted inside guests."
        ),
    )


def plan_node_migrateall(
    target: str,
    node: str | None = None,
    vms: str | None = None,
    maxworkers: int | None = None,
) -> Plan:
    """Plan for pve_node_migrateall — migrate all (or filtered) guests to another node.

    RISK_HIGH, NOT auto-reversible: moving all guests back requires a second migrate-all.
    """
    _check_node(node)
    _check_node(target)
    scope = f" (filtered: {vms!r})" if vms else " (ALL guests)"
    workers_note = f" maxworkers={maxworkers}" if maxworkers is not None else ""
    return Plan(
        action="pve_node_migrateall",
        target=f"node/{node or 'default'}/migrateall->{target}",
        change=(
            f"migrate all guests from {node or 'this node'} to {target!r}{scope}{workers_note}; "
            "reversal = a second migrate-all back, not guaranteed identical"
        ),
        current={},
        blast_radius=[
            f"ALL guests on node/{node or 'default'}{scope}: moved to {target!r}; "
            "reversal requires a second pve_node_migrateall back — not automatic"
        ],
        risk=RISK_HIGH,
        risk_reasons=[
            f"migrates all guests to {target!r} — fleet-wide move; "
            "not auto-reversible: a second migrate-all back is required and may not be identical "
            "(HA, local resources, storage differences)"
        ],
        note=(
            f"Not auto-reversible: moving guests back to {node or 'this node'} requires a separate "
            f"pve_node_migrateall from {target!r} back, which may not restore the original state "
            "(HA rules, local storage, and resource pinning may differ)."
        ),
    )
