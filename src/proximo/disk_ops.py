"""DISK OPERATIONS — resize and move guest disks.

Every mutating function returns a UPID (or None for synchronous responses).
Every plan function reads live state (one safe read where needed) to surface facts.

Hard rules mirrored from the codebase:
- Validators fire on every param before it enters a URL or request body.
- Plans are HONEST — HIGH is maintained on destructive paths; no false-safety claims.
- Disk resize is GROW-ONLY in the general case; shrink is blocked at the op AND plan layer.
- grow is NOT auto-undoable (you cannot shrink back) — disclosed honestly in every plan.
- Disk move is async (UPID) — outcome="submitted", never "ok".
- No self-gating: the server layer adds confirm-gating + audit; these functions are pure ops.

SHAPE-RISK DISCLOSURE (what only a live PVE call can confirm):
  - resize verb: Proxmox API docs say PUT /nodes/{n}/{kind}/{vmid}/resize; we call it via
    api._client.request("PUT", ...) because ApiBackend only exposes _get/_post/_delete.
    If PVE actually expects POST (some older builds), the verb will fail — confirm at live smoke.
  - QEMU move-disk endpoint: POST /nodes/{n}/qemu/{vmid}/move_disk, param "disk".
    LXC move-volume endpoint: POST /nodes/{n}/lxc/{vmid}/move_volume, param "volume".
    The divergence is an assumption from Proxmox API explorer notes; verify at live smoke.
  - move storage param name: assumed "storage" (target); confirm vs live API schema.
  - move delete param name: assumed "delete" (0/1); confirm vs live API schema.
  - resize size param name: assumed "size"; confirm vs live API schema.
  - config-key format for "current size" probe: assumed "size" key on the disk entry in
    /nodes/{n}/{kind}/{vmid}/config (e.g. "local-lvm:vm-100-disk-0,size=10G"); confirm format.
"""

from __future__ import annotations

import re

from .backends import ProximoError, _check_kind, _check_node, _check_vmid
from .planning import RISK_HIGH, RISK_MEDIUM, RISK_NONE, Plan, _max_risk

# ---------------------------------------------------------------------------
# Local validators
# ---------------------------------------------------------------------------

# Disk identifier: LXC uses rootfs, mp0..N, unused0..N; QEMU uses scsi0..N, virtio0..N,
# sata0..N, ide0..N, efidisk0, tpmstate0, unused0..N.
# Using \Z (not $) to reject trailing-newline bypass.
_DISK_RE = re.compile(
    r"^(?:rootfs|efidisk0|tpmstate0|(?:scsi|virtio|sata|ide|mp|unused)\d+)\Z"
)

# Size format: relative grow (+NUnit) or absolute (NUnit), Unit = K|M|G|T (case-insensitive).
# Plain integer bytes allowed for absolute size; no negative.
# Examples: "+10G", "50G", "1024M", "+512M".
_RELATIVE_SIZE_RE = re.compile(r"^\+\d+[KMGTkmgt]\Z")
_ABSOLUTE_SIZE_RE = re.compile(r"^\d+[KMGTkmgt]?\Z")

# Storage name: same character set as backup.py's _STORAGE_RE.
_STORAGE_RE = re.compile(r"^[A-Za-z0-9._-]+\Z")


def _check_disk(disk: str) -> str:
    """Validate a guest disk identifier (scsi0, virtio1, rootfs, mp2, …)."""
    s = str(disk).strip()
    if not _DISK_RE.match(s):
        raise ProximoError(
            f"invalid disk identifier: {disk!r} "
            "(expected rootfs | efidisk0 | tpmstate0 | scsiN | virtioN | sataN | ideN | mpN | unusedN)"
        )
    return s


def _check_size(size: str) -> str:
    """Validate a resize size string.

    Accepts: '+NUnit' (relative grow) or 'NUnit' / 'N' (absolute).
    Rejects: negative, zero (no-op), empty.
    Returns the size string as-is (PVE validates the rest).
    """
    s = str(size).strip()
    if not s:
        raise ProximoError("size must not be empty")
    if _RELATIVE_SIZE_RE.match(s) or _ABSOLUTE_SIZE_RE.match(s):
        return s
    raise ProximoError(
        f"invalid size: {size!r} "
        "(expected '+NUnit' for relative grow, or 'NUnit' for absolute, e.g. '+10G', '50G')"
    )


def _check_storage(storage: str) -> str:
    """Non-empty + character-set check; PVE validates existence on its side."""
    s = str(storage).strip()
    if not s or not _STORAGE_RE.match(s):
        raise ProximoError(
            f"invalid storage name: {storage!r} (letters/digits/. _/- only, must not be empty)"
        )
    return s


def _is_relative_grow(size: str) -> bool:
    """True iff size is an unambiguous relative grow (leading '+')."""
    return size.strip().startswith("+")


# ---------------------------------------------------------------------------
# Current disk size probe (for absolute-size shrink detection)
# ---------------------------------------------------------------------------

def _read_disk_size(
    api, node: str, kind: str, vmid: str, disk: str
) -> tuple[str | None, str | None]:
    """Read the current disk's size from the guest config (one safe read).

    Returns (size_str, error_type_name). error_type_name is the raising exception's class
    name when the config GET itself raised, and None in every other case (non-dict cfg,
    disk key missing, no 'size=' token, or a size was found successfully).

    Shared by _probe_disk_size (which only needs the size) and plan_disk_resize (which
    also needs to distinguish a genuine read failure from a readable-but-absent size, to
    disclose the difference honestly in the plan).

    SHAPE-RISK: PVE config returns disk entries as 'storage:volid,size=NUnit,...'. We extract
    the 'size=' component. The exact key format must be confirmed at live smoke.
    """
    try:
        cfg = api._get(f"/nodes/{node}/{kind}/{vmid}/config")
        if not isinstance(cfg, dict):
            return None, None
        disk_entry = cfg.get(disk)
        if not isinstance(disk_entry, str):
            return None, None
        # Parse comma-separated key=value options; size= is one of them.
        for part in disk_entry.split(","):
            part = part.strip()
            if part.startswith("size="):
                return part[5:], None
        return None, None
    except Exception as e:
        return None, type(e).__name__


def _probe_disk_size(api, node: str, kind: str, vmid: str, disk: str) -> str | None:
    """Try to read the current disk's size from the guest config.

    Returns the size string (e.g. '10G') on success, None on any failure.
    """
    return _read_disk_size(api, node, kind, vmid, disk)[0]


def _parse_size_bytes(s: str) -> int | None:
    """Parse a size string like '10G', '512M', '100' into bytes.

    Returns None if unparseable OR non-positive. Fail-closed by design: a wrong-small or
    negative int slipping through to a capacity/shrink comparison would UNDER-flag, so anything
    that isn't a clean positive size is reported as unknown (the caller forces caution on None).
    """
    if not s:
        return None
    s = s.strip()
    if not s:                                    # whitespace-only — guard before s[-1]
        return None
    multipliers = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
    upper = s[-1].upper()
    try:
        val = int(s[:-1]) * multipliers[upper] if upper in multipliers else int(s)
    except ValueError:
        return None
    return val if val > 0 else None              # 0 / negative → unknown, never a wrong small int


# ---------------------------------------------------------------------------
# Mutation operations — validate params, build exact PVE URLs, return UPID
# ---------------------------------------------------------------------------

def disk_resize(
    api,
    vmid: str,
    disk: str,
    size: str,
    kind: str = "lxc",
    node: str | None = None,
) -> str:
    """Grow a guest disk.

    PUT /nodes/{node}/{kind}/{vmid}/resize  →  UPID or empty string (sync)

    CRITICAL SAFETY: Proxmox disk resize is GROW-ONLY in the general case; shrink is
    unsupported / destructive. This function BLOCKS any size that is provably a shrink
    (relative negative values, or absolute value < current size from the live config read).
    Ambiguous cases (absolute size where current size is unknown) are surfaced as an
    error rather than silently passed through — do NOT let an unverified absolute reach PVE.

    SHAPE-RISK: resize uses PUT (not POST); we call api._client.request("PUT", ...) because
    ApiBackend has no _put method. If PVE expects POST on this endpoint, update the verb here.
    Confirm at live smoke.
    """
    vmid = _check_vmid(vmid)
    disk = _check_disk(disk)
    size = _check_size(size)
    kind = _check_kind(kind)
    _check_node(node)
    n = node or api.config.node

    # Block provable shrinks at the op layer — mirror the plan-layer check with a hard stop.
    if _is_relative_grow(size):
        # '+NUnit' is unambiguous grow — allowed.
        pass
    else:
        # Absolute size: read current disk size from config to detect shrink.
        # If the read fails, we REFUSE rather than silently pass through —
        # a claimed grow on an unverifiable size would be a false-safety claim.
        current_str = _probe_disk_size(api, n, kind, vmid, disk)
        if current_str is None:
            raise ProximoError(
                f"cannot verify whether size {size!r} is a grow or a shrink for {kind}/{vmid} "
                f"disk {disk!r} — use a relative '+NUnit' form (e.g. '+10G') to be unambiguous, "
                "or ensure the guest config is readable before retrying an absolute resize."
            )
        current_bytes = _parse_size_bytes(current_str)
        new_bytes = _parse_size_bytes(size)
        if current_bytes is None or new_bytes is None:
            # FAIL-CLOSED: the current or requested size could not be parsed to bytes, so we
            # cannot PROVE this is a grow — an unverified absolute size may be a destructive
            # shrink. Refuse rather than pass it through (the docstring's promise, enforced).
            raise ProximoError(
                f"cannot verify grow vs shrink for {kind}/{vmid} disk {disk!r}: unparseable size "
                f"(current={current_str!r}, requested={size!r}) — use a relative '+NUnit' form "
                "(e.g. '+10G') to grow unambiguously."
            )
        if new_bytes <= current_bytes:
            raise ProximoError(
                f"BLOCKED: size {size!r} ({new_bytes} bytes) is not larger than the current "
                f"disk size {current_str!r} ({current_bytes} bytes) — Proxmox disk resize is "
                "GROW-ONLY; shrink or no-op is unsupported and would corrupt the filesystem. "
                "Use a relative '+NUnit' form (e.g. '+10G') to grow safely."
            )

    data = {"disk": disk, "size": size}
    # MUTATION — confirm-gated + audited at the server layer.
    # SHAPE-RISK: PUT verb assumption; ApiBackend has no _put so we call the underlying client.
    r = api._client.request("PUT", f"/nodes/{n}/{kind}/{vmid}/resize",
                            headers=api._auth_header(), data=data)
    r.raise_for_status()
    return r.json().get("data") or ""


def disk_move(
    api,
    vmid: str,
    disk: str,
    target_storage: str,
    kind: str = "lxc",
    node: str | None = None,
    delete_source: bool = False,
) -> str:
    """Move a guest disk to another storage pool.  Returns a UPID.

    QEMU: POST /nodes/{node}/qemu/{vmid}/move_disk    body: {disk, storage, delete}
    LXC:  POST /nodes/{node}/lxc/{vmid}/move_volume   body: {volume, storage, delete}

    UNDO posture:
    - delete_source=False (default): the source copy is retained; the natural undo is that the
      source disk still exists and the move can be reversed manually.
    - delete_source=True: the source is deleted after the move; no easy undo — rated HIGH.

    Outcome = "submitted" (the task is async — the disk move runs in the background).
    SHAPE-RISK: endpoint names, param names (disk vs volume, storage, delete), and async
    behavior (always UPID) are assumptions from Proxmox API explorer notes. Confirm at live smoke.
    """
    vmid = _check_vmid(vmid)
    disk = _check_disk(disk)
    target_storage = _check_storage(target_storage)
    kind = _check_kind(kind)
    _check_node(node)
    n = node or api.config.node

    # MUTATION — confirm-gated + audited at the server layer.
    if kind == "qemu":
        # SHAPE-RISK: 'disk' param name for QEMU; endpoint 'move_disk'
        data: dict = {"disk": disk, "storage": target_storage}
        if delete_source:
            data["delete"] = 1
        return api._post(f"/nodes/{n}/qemu/{vmid}/move_disk", data)
    else:
        # kind == "lxc"
        # SHAPE-RISK: 'volume' param name for LXC; endpoint 'move_volume'
        data = {"volume": disk, "storage": target_storage}
        if delete_source:
            data["delete"] = 1
        return api._post(f"/nodes/{n}/lxc/{vmid}/move_volume", data)


# ---------------------------------------------------------------------------
# Plan functions — each returns a Plan for caller inspection (PLAN pillar)
# ---------------------------------------------------------------------------

def plan_disk_resize(
    api,
    vmid: str,
    disk: str,
    size: str,
    kind: str = "lxc",
    node: str | None = None,
) -> Plan:
    """Preview a disk resize.

    Reads the guest config (a safe read) to find the current disk size for shrink detection
    and to surface current size in the plan. If the read fails, uncertainty is disclosed —
    the absence of a HIGH flag is not a safety signal.

    CRITICAL SAFETY:
    - Shrink (new <= current) → RISK_HIGH, plan documents the block and explains why.
    - Ambiguous absolute without readable config → RISK_HIGH, plan documents the uncertainty.
    - Relative grow ('+NUnit') → RISK_MEDIUM; discloses grow is NOT auto-undoable.
    - grow is NOT auto-undoable (cannot shrink back after a grow) — always disclosed.
    """
    vmid = _check_vmid(vmid)
    disk = _check_disk(disk)
    size = _check_size(size)
    kind = _check_kind(kind)
    _check_node(node)
    n = node or api.config.node

    current: dict = {}
    current_str, read_error = _read_disk_size(api, n, kind, vmid, disk)
    config_read_failed = read_error is not None
    if read_error is not None:
        current["config_read_error"] = read_error
    elif current_str is not None:
        current["disk"] = disk
        current["current_size"] = current_str

    # Determine risk and blast based on size direction.
    if _is_relative_grow(size):
        # Unambiguous grow — RISK_MEDIUM with honest undo disclosure.
        risk = RISK_MEDIUM
        size_info = f"grow {disk} by {size}"
        blast = [
            f"grows disk {disk!r} on {kind}/{vmid} by {size}",
            "IMPORTANT: disk grow is NOT auto-undoable — Proxmox cannot shrink a disk back; "
            "you cannot reverse this by resizing down. Consider a snapshot before proceeding.",
        ]
        if current_str:
            blast.append(f"current size: {current_str} → new size: current + {size[1:]}")
        reasons = [
            "disk grow is irreversible (Proxmox GROW-ONLY; no shrink path after commit)",
            "filesystem inside the guest must be expanded separately after the resize",
        ]
    else:
        # Absolute size — need to compare against current.
        current_bytes = _parse_size_bytes(current_str) if current_str else None
        new_bytes = _parse_size_bytes(size)

        if config_read_failed:
            # Cannot verify grow vs shrink — rate HIGH (false safety would be a violation).
            risk = RISK_HIGH
            size_info = f"resize {disk} to {size} (absolute — grow vs shrink UNKNOWN)"
            blast = [
                f"could NOT verify current size of disk {disk!r} on {kind}/{vmid} — "
                f"cannot confirm whether size {size!r} is a grow or a shrink",
                "with an absolute size and no config read, this operation MAY be a "
                "destructive shrink — RISK_HIGH maintained (uncertainty is not a safety signal)",
                "IMPORTANT: disk grow is NOT auto-undoable even if this is a grow",
            ]
            reasons = [
                f"config read failed — cannot verify grow vs shrink for absolute size {size!r}",
                "absence of a HIGH flag is not a safety signal; confirm current size before proceeding",
            ]
        elif current_bytes is not None and new_bytes is not None and new_bytes <= current_bytes:
            # Provable shrink or no-op — RISK_HIGH, will be blocked at op layer.
            risk = RISK_HIGH
            size_info = f"BLOCKED resize {disk} to {size} (shrink/no-op detected)"
            blast = [
                f"BLOCKED: size {size!r} ({new_bytes} bytes) is NOT larger than the current "
                f"size {current_str!r} ({current_bytes} bytes)",
                "Proxmox disk resize is GROW-ONLY; shrink is unsupported and would corrupt "
                "the filesystem — this operation will be refused by the op layer",
            ]
            reasons = [
                f"size {size!r} implies shrink or no-op (new <= current) — BLOCKED",
                "Proxmox has no supported shrink path; shrinking corrupts filesystem data",
            ]
        elif current_str is None:
            # Disk not found in config (not same as read failure) — uncertain.
            risk = RISK_HIGH
            size_info = f"resize {disk} to {size} (disk not found in config — grow vs shrink unknown)"
            blast = [
                f"disk {disk!r} not found in {kind}/{vmid} config — cannot verify grow vs shrink",
                f"absolute size {size!r} may be a shrink if the disk exists under a different key",
                "IMPORTANT: disk grow is NOT auto-undoable even if this is a grow",
            ]
            reasons = [
                f"disk {disk!r} not present in config — absolute size ambiguous; use '+NUnit' form",
                "uncertainty is not a safety signal",
            ]
        elif current_bytes is None or new_bytes is None:
            # Current size present but UNPARSEABLE (or requested size unparseable) — we cannot
            # prove grow vs shrink, so this is NOT a "provable grow". Rate HIGH; the op layer
            # will fail-closed. Absence of a HIGH flag must never be read as a safety signal.
            risk = RISK_HIGH
            size_info = (f"resize {disk} to {size} "
                         f"(current size {current_str!r} unparseable — grow vs shrink UNKNOWN)")
            blast = [
                f"current size {current_str!r} of disk {disk!r} on {kind}/{vmid} could not be "
                f"parsed to bytes — cannot confirm whether {size!r} is a grow or a shrink",
                "an absolute resize on an unverifiable current size MAY be a destructive shrink — "
                "RISK_HIGH maintained (uncertainty is not a safety signal); the op layer refuses it",
            ]
            reasons = [
                f"current size {current_str!r} unparseable — cannot verify grow vs shrink",
                "absence of a HIGH flag is not a safety signal; use a relative '+NUnit' form",
            ]
        else:
            # Provable grow — RISK_MEDIUM with undo disclosure.
            risk = RISK_MEDIUM
            size_info = f"grow {disk} from {current_str} to {size}"
            blast = [
                f"grows disk {disk!r} on {kind}/{vmid} from {current_str} to {size}",
                "IMPORTANT: disk grow is NOT auto-undoable — cannot shrink back after this commit",
            ]
            reasons = [
                "disk grow is irreversible (Proxmox GROW-ONLY; no shrink path after commit)",
                "filesystem inside the guest must be expanded separately after the resize",
            ]

    return Plan(
        action="pve_disk_resize",
        target=f"{kind}/{vmid}:{disk}",
        change=size_info,
        current=current,
        blast_radius=blast,
        risk=risk,
        risk_reasons=reasons,
    )


def plan_disk_move(
    api,
    vmid: str,
    disk: str,
    target_storage: str,
    kind: str = "lxc",
    node: str | None = None,
    delete_source: bool = False,
) -> Plan:
    """Preview a disk move.

    Tries to read the guest config (a safe read) to surface the source storage in the plan.
    If the read fails, source storage is disclosed as unknown — never silently assumed safe.

    UNDO posture:
    - delete_source=False → RISK_MEDIUM; source copy retained — that IS the undo path.
    - delete_source=True  → RISK_HIGH; source deleted after move — no easy undo.
    """
    vmid = _check_vmid(vmid)
    disk = _check_disk(disk)
    target_storage = _check_storage(target_storage)
    kind = _check_kind(kind)
    _check_node(node)
    n = node or api.config.node

    current: dict = {}
    source_storage: str | None = None
    config_read_failed = False

    try:
        cfg = api._get(f"/nodes/{n}/{kind}/{vmid}/config")
        if isinstance(cfg, dict):
            disk_entry = cfg.get(disk)
            if isinstance(disk_entry, str):
                # First token before ':' is typically the storage name (e.g. "local-lvm:vm-100-disk-0").
                source_storage = disk_entry.split(":")[0] if ":" in disk_entry else None
                current["disk"] = disk
                if source_storage:
                    current["source_storage"] = source_storage
                current["disk_config"] = disk_entry
    except Exception as e:
        config_read_failed = True
        current["config_read_error"] = type(e).__name__

    source_label = source_storage or ("unknown (config read failed)" if config_read_failed else "unknown")

    if delete_source:
        # Destructive path — source copy deleted after move; no easy undo.
        risk = RISK_HIGH
        blast = [
            f"moves disk {disk!r} on {kind}/{vmid} from {source_label!r} → {target_storage!r}",
            f"DELETES the source copy in {source_label!r} after the move — source is gone; "
            "no easy undo once the task completes",
        ]
        reasons = [
            "delete_source=True: the source disk copy is removed after move — irreversible",
            "to preserve an undo path, re-run with delete_source=False (source retained)",
        ]
    else:
        # Source retained — the natural undo exists.
        risk = RISK_MEDIUM
        blast = [
            f"moves disk {disk!r} on {kind}/{vmid} from {source_label!r} → {target_storage!r}",
            f"source copy in {source_label!r} is RETAINED (delete_source=False) — "
            "natural undo: the source disk still exists if the move needs to be reversed",
        ]
        reasons = [
            "disk move without source deletion — source copy survives as a natural undo",
            "disk move is async (UPID); poll pve_task_status to confirm completion",
        ]

    if config_read_failed:
        blast.append(
            "NOTE: config read failed — source storage is unknown; the move proceeds but "
            "the plan cannot confirm what is being migrated away from"
        )
        reasons.append("config read failed — source storage unknown (uncertainty is not a safety signal)")

    # TARGET-side blast radius: moving onto the target storage consumes its capacity, putting every
    # co-tenant (a guest with a disk on the target) at risk if it fills or the move won't fit. The
    # engine ESCALATES risk (never lowers it) and populates the structured affected/complete signals.
    from .blast import disk_move_blast
    engine = disk_move_blast(api, vmid, disk, target_storage, kind, node)
    engine_risk = (RISK_HIGH if engine.max_severity == "high"
                   else RISK_MEDIUM if engine.max_severity == "medium" else RISK_NONE)
    risk = _max_risk(risk, engine_risk)
    blast.extend(engine.summary_lines)
    if engine_risk == RISK_HIGH:
        reasons.append(f"target '{target_storage}' capacity/fit check escalated risk to HIGH "
                       "(won't-fit, capacity-unknown, or incomplete enumeration)")

    return Plan(
        action="pve_disk_move",
        target=f"{kind}/{vmid}:{disk}",
        change=f"move {kind}/{vmid} disk {disk!r} → storage {target_storage!r}"
               + (" (delete source)" if delete_source else ""),
        current=current,
        blast_radius=blast,
        risk=risk,
        risk_reasons=reasons,
        affected=engine.affected_dicts(),
        complete=engine.complete,
    )
