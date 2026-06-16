"""Blast-radius engine — compute the SPECIFIC downstream impact of a dangerous op.

The pure reasoning (compute_storage_blast and its helpers) takes already-fetched cluster
state and returns named, classified consequences — no api, no I/O, fully unit-testable.
gather_storage_dependents does the safe reads and CATCHES per-guest failures (turning them
into complete=False, never raising) so the plan always builds with an honest INCOMPLETE marker.

Honesty contract (mirrors the access-plane plan_*_delete idiom):
- An incomplete enumeration is rendered LOUDLY and never read as "nothing affected = safe".
- The engine never lowers a plan's risk; on uncertainty it forces max_severity="high".
- "found zero affected" is not a safety signal — orphaned/unreferenced volumes are out of v1 scope.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field

from .cluster_ops import cluster_resources, ha_resources_list
from .config_edit import guest_config_get
from .planning import RISK_HIGH, RISK_MEDIUM, _max_risk
from .tasks_pools import pool_get, pools_list

# Config keys that hold a guest *data* volume. `netN` (NICs) and non-disk keys are excluded.
_DISK_KEY_RE = re.compile(r"^(?:rootfs|(?:efidisk|tpmstate|scsi|sata|ide|virtio|mp|unused)\d+)$")

# Boot-critical even when they are not the "boot disk": losing the UEFI variable store (efidisk0)
# or the TPM state (tpmstate0) prevents boot on UEFI / Secure-Boot / TPM-backed guests. Over-flag
# (treat their loss as won't-boot) rather than under-flag — these slots only exist when relevant.
_BOOT_CRITICAL = frozenset({"efidisk0", "tpmstate0"})


def _is_disk_key(key: str) -> bool:
    return bool(_DISK_KEY_RE.match(key))


def _storage_of_volid(volval: str) -> str | None:
    """Storage name from a disk config value, or None if it names no storage volume.

    A PVE disk value looks like '<storage>:<rest>,opt=val,...' e.g.
    'nas:101/vm-101-disk-0.qcow2,size=32G' or 'local-lvm:vm-101-disk-0,size=8G'.
    Returns the storage segment; None for 'none', raw paths ('/dev/...'), or anything
    without a 'storage:volume' shape.
    """
    head = volval.split(",", 1)[0].strip()
    if ":" not in head:
        return None
    storage, _, rest = head.partition(":")
    storage, rest = storage.strip(), rest.strip()
    if not storage or not rest or "/" in storage:
        return None  # '/' in the storage segment => an absolute path, not 'storage:vol'
    return storage


def _disk_slots(config: dict) -> dict[str, str]:
    """{slot: storage} for every DATA-disk slot in a guest config. cdrom media is excluded
    (removable media is not guest data; deleting its storage breaks a mount, not the guest)."""
    out: dict[str, str] = {}
    for key, val in config.items():
        if not isinstance(val, str) or not _is_disk_key(key):
            continue
        if "media=cdrom" in val:
            continue
        storage = _storage_of_volid(val)
        if storage is not None:
            out[key] = storage
    return out


def _boot_slot(config: dict, kind: str) -> str | None:
    """The slot holding the boot disk, or None if not determinable.
    LXC always boots from 'rootfs'. QEMU: prefer 'bootdisk', else first DISK in 'boot: order=...'.
    """
    if kind == "lxc":
        return "rootfs" if "rootfs" in config else None
    bootdisk = config.get("bootdisk")
    if isinstance(bootdisk, str) and bootdisk.strip():
        return bootdisk.strip()
    boot = config.get("boot")
    if isinstance(boot, str) and "order=" in boot:
        order = boot.split("order=", 1)[1]
        for tok in re.split(r"[;,]", order):
            tok = tok.strip()
            if _is_disk_key(tok):
                return tok
    return None


def _is_linked_clone_of(config: dict, template_vmid: str) -> bool:
    """True if any disk in `config` backs onto template `template_vmid`'s base volume.
    A linked clone's volid carries the template's base volume name: `base-<tmpl>-disk-N`."""
    needle = f"base-{template_vmid}-disk"
    for key, val in (config or {}).items():
        if _is_disk_key(key) and needle in str(val):
            return True
    return False


@dataclass
class BlastEntry:
    """One guest's loss if the target storage is removed/disabled."""

    resource: str          # "qemu/101" | "lxc/200"
    vmid: str
    name: str
    node: str
    via: list[str]         # data-disk slots on the target storage
    effect: str
    only_copy: bool        # every one of the guest's data disks is on the target storage
    running: bool
    severity: str          # "high" | "medium" | "unknown"

    def as_dict(self) -> dict:
        return {
            "resource": self.resource, "vmid": self.vmid, "name": self.name,
            "node": self.node, "via": self.via, "effect": self.effect,
            "only_copy": self.only_copy, "running": self.running, "severity": self.severity,
        }


def _classify_guest(storage: str, guest: dict, config: dict) -> BlastEntry | None:
    """Classify one guest's loss if `storage` is removed/disabled. None if it holds no data disk there."""
    slots = _disk_slots(config)                              # {slot: storage}
    on_s = sorted(slot for slot, st in slots.items() if st == storage)
    if not on_s:
        return None
    vmid = str(guest.get("vmid", ""))
    kind = guest.get("type", "qemu")                         # "qemu" | "lxc"
    node = str(guest.get("node", ""))
    name = str(guest.get("name", "") or "")
    running = guest.get("status") == "running"

    only_copy = len(on_s) == len(slots)                      # all data disks are on S
    boot = _boot_slot(config, kind)
    boot_on_s = boot is not None and slots.get(boot) == storage
    boot_critical_on_s = sorted(_BOOT_CRITICAL.intersection(on_s))
    wont_boot = only_copy or boot_on_s or bool(boot_critical_on_s)

    if only_copy:
        effect = f"will NOT boot — all data disks ({', '.join(on_s)}) are on this storage"
    elif boot_on_s:
        effect = f"will NOT boot — boot disk {boot} is on this storage"
    elif boot_critical_on_s:
        effect = (f"will NOT boot — loses UEFI/TPM state ({', '.join(boot_critical_on_s)}) on this "
                  "storage; UEFI / Secure-Boot / TPM-backed guests cannot boot without it")
    else:
        effect = f"degraded — loses disk(s) {', '.join(on_s)}; boot disk is elsewhere"
        if boot is None:
            effect += " (boot order not determinable — classified conservatively)"
    if running:
        effect += " — RUNNING: losing the disk live may crash or corrupt the guest"

    return BlastEntry(
        resource=f"{kind}/{vmid}", vmid=vmid, name=name, node=node, via=on_s,
        effect=effect, only_copy=only_copy, running=running,
        severity="high" if wont_boot else "medium",
    )


@dataclass
class BlastResult:
    affected: list[BlastEntry]
    summary_lines: list[str]
    complete: bool
    max_severity: str          # "high" | "medium" | "none" — drives risk escalation, never lowers

    def affected_dicts(self) -> list[dict]:
        return [e.as_dict() for e in self.affected]


def compute_storage_blast(storage: str, guests: list[dict], configs: dict,
                          complete: bool) -> BlastResult:
    """PURE. Given enumerated guests + their configs (vmid -> config dict, or None if the read
    failed), compute which guests lose volumes on `storage`. `complete=False` (partial enumeration)
    renders a loud INCOMPLETE marker, forces max_severity='high', and appends an 'unknown' sentinel."""
    affected: list[BlastEntry] = []
    for guest in guests:
        config = configs.get(str(guest.get("vmid", "")))
        if not isinstance(config, dict):
            continue                                        # unread guest — reflected via `complete`
        entry = _classify_guest(storage, guest, config)
        if entry is not None:
            affected.append(entry)
    affected.sort(key=lambda e: (0 if e.severity == "high" else 1, e.vmid))

    total = len(guests)
    failed = sum(1 for g in guests if not isinstance(configs.get(str(g.get("vmid", ""))), dict))
    lines: list[str] = []
    if not complete:
        miss = str(failed) if failed else "some"
        lines.append(
            f"⚠ INCOMPLETE: could not enumerate {miss} of {total} guests cluster-wide — "
            "do NOT treat this list as exhaustive; absence of a guest here is not proof it is safe"
        )
    if affected:
        lines.append(f"ENUMERATED {len(affected)} guest(s) with data volumes on '{storage}':")
        for e in affected:
            label = e.resource + (f" ({e.name})" if e.name else "")
            lines.append(f"  {label} on {e.node}: {e.effect}")
    elif complete:
        lines.append(
            f"no guest config references storage '{storage}' — NOTE: orphaned/unreferenced "
            "volumes are not enumerated in v1; absence here is not proof the storage is unused"
        )

    if not complete:
        max_severity = "high"                               # uncertainty is HIGH, never lowered
    elif any(e.severity == "high" for e in affected):
        max_severity = "high"
    elif affected:
        max_severity = "medium"
    else:
        max_severity = "none"

    if not complete:
        affected = affected + [BlastEntry(
            resource="?", vmid="", name="", node="", via=[],
            effect="enumeration incomplete — one or more guests could not be read",
            only_copy=False, running=False, severity="unknown",
        )]
    return BlastResult(affected=affected, summary_lines=lines, complete=complete,
                       max_severity=max_severity)


def gather_storage_dependents(api, storage: str) -> tuple[list[dict], dict, bool]:
    """I/O: enumerate ALL guests cluster-wide + read each config. Returns (guests, configs, complete).
    A total cluster_resources failure -> ([], {}, False); a per-guest config failure ->
    configs[vmid]=None + complete=False. NEVER raises — the plan must always build.

    `storage` is unused here (enumeration is storage-agnostic; the filter happens in
    compute_storage_blast) but kept for a symmetric, future-proof signature.
    """
    try:
        rows = cluster_resources(api) or []
    except Exception:
        return [], {}, False
    guests = [r for r in rows if r.get("type") in ("qemu", "lxc")]
    configs: dict = {}
    complete = True
    for g in guests:
        vmid = str(g.get("vmid", ""))
        try:
            cfg = guest_config_get(api, vmid, str(g.get("type")), g.get("node"))
        except Exception:
            configs[vmid] = None
            complete = False
            continue
        # An enumerated guest with an empty/null config means we could NOT see its disks
        # (e.g. HTTP 200 with {"data": null}); a real guest config is never empty. Treat it as a
        # FAILED read (partial enumeration) — never as "no disks → not affected = safe".
        if not cfg:
            configs[vmid] = None
            complete = False
        else:
            configs[vmid] = cfg
    return guests, configs, complete


def storage_blast(api, storage: str) -> BlastResult:
    """Convenience: gather live cluster state then compute the pure blast result."""
    guests, configs, complete = gather_storage_dependents(api, storage)
    return compute_storage_blast(storage, guests, configs, complete)


# ===========================================================================
# Access / ACL class — shadow/widen reasoning for an ACL grant/revoke.
# ===========================================================================

@dataclass
class AclBlastResult:
    summary_lines: list[str]
    risk: str
    risk_reasons: list[str]
    current: dict
    affected: list[dict] = field(default_factory=list)
    complete: bool = True


def compute_acl_blast(
    path: str,
    roles: str,
    target: str,
    kind: str,
    delete: bool,
    acl_entries: list[dict] | None,   # None => the ACL read FAILED (fail-closed branch)
    acl_error: str | None = None,
    target_groups: list[str] | None = None,   # the target's own group memberships; None => unresolved
    group_members: dict[str, list | None] | None = None,   # #2 in-scope group -> members (None=read failed)
    extra_inherited: dict[str, str] | None = None,   # privsep=0 token: owner's direct grants, role->via label
) -> AclBlastResult:
    """PURE shadow/widen analysis for an ACL grant/revoke. No API.

    `acl_entries` is the already-fetched current ACL; None means the read FAILED → a RISK_HIGH
    disclosure ("absence of a warning is not a safety signal"), never a clean "safe".

    THE PROXMOX GOTCHA: a specific-path ACL entry REPLACES (shadows) an ancestor's propagated
    grant rather than unioning with it. So granting at a deeper path can NARROW access (shadow),
    and revoking a specific entry can WIDEN it (the shadowed inherited grant returns.)
    """
    new_roles = {r.strip() for r in roles.split(",")}

    # Fail-closed keys on the DATA: acl_entries is None means the read failed, regardless of whether
    # a label was passed. Synthesize a generic message if acl_error is absent — never fall through
    # to a clean "additive / safe" plan on a failed read.
    check_error = (acl_error or "ACL read failed (no detail)") if acl_entries is None else None
    entries = acl_entries or []

    current_direct_entries: list[dict] = []
    inherited_entries: list[dict] = []
    if check_error is None:
        for entry in entries:
            ugid = entry.get("ugid", "")
            entry_path = entry.get("path", "")
            entry_propagate = entry.get("propagate", True)
            if ugid != target:
                continue
            if entry_path == path:
                current_direct_entries.append(entry)
            elif path.startswith(entry_path.rstrip("/") + "/") and entry_propagate:
                inherited_entries.append(entry)

    inherited_roles: set[str] = {e.get("roleid", "") for e in inherited_entries}

    # #1: fold in roles the TARGET inherits via THEIR OWN group memberships (ancestor, propagated).
    # target_groups None => resolution unavailable (user_get failed / privsep token) -> stay incomplete.
    group_inherited: dict[str, str] = {}   # roleid -> the group it came from (for naming)
    groups_resolved = target_groups is not None
    if check_error is None and groups_resolved:
        gset = set(target_groups or [])
        for entry in entries:
            if entry.get("type") != "group" or entry.get("ugid", "") not in gset:
                continue
            ep = entry.get("path", "")
            if path.startswith(ep.rstrip("/") + "/") and entry.get("propagate", True):
                group_inherited[entry.get("roleid", "")] = entry.get("ugid", "")
        inherited_roles |= set(group_inherited)

    # privsep=0 token: the token IS the owner — also fold the owner's DIRECT propagated grants
    # (resolved by the caller from the ACL list) so they are shadowed too. role -> via label.
    if check_error is None and extra_inherited:
        group_inherited.update(extra_inherited)
        inherited_roles |= set(extra_inherited)

    current_direct_roles: set[str] = {e.get("roleid", "") for e in current_direct_entries}
    has_direct = bool(current_direct_entries)
    effective_before: set[str] = current_direct_roles if has_direct else inherited_roles
    if not delete:
        effective_after = new_roles
    else:
        remaining_direct = current_direct_roles - new_roles
        effective_after = remaining_direct if remaining_direct else inherited_roles
    shadowed_inherited = inherited_roles - new_roles if not has_direct and not delete else set()
    widened = effective_after - effective_before

    blast: list[str] = []
    reasons: list[str] = []
    risk = RISK_MEDIUM
    complete = True

    if check_error is not None:
        blast.append(
            f"could NOT read current ACL ({check_error}) — cannot determine what privileges "
            "would be shadowed or widened; absence of a shadow/widen warning is NOT a safety signal"
        )
        reasons.append(
            "ACL read failed — shadow/widen analysis unavailable; absence of a warning is not a safety signal"
        )
        risk = RISK_HIGH
        complete = False
    else:
        group_entries_present = any(
            e.get("type") == "group" and (
                e.get("path") == path or path.startswith(e.get("path", "").rstrip("/") + "/")
            )
            for e in entries
        )
        if group_entries_present and not groups_resolved:
            complete = False
            blast.append(
                "UNCERTAINTY: group-type ACL entries exist at or above this path and group "
                "membership could not be resolved — shadow/widen analysis may be INCOMPLETE for "
                "users who are group members"
            )
            reasons.append(
                "group-based ACL grants exist and were not resolved; "
                "shadow analysis may miss group-inherited privileges"
            )
        if not delete:
            if shadowed_inherited:
                sr = ", ".join(sorted(shadowed_inherited))
                blast.append(
                    f"SHADOW WARNING: granting {roles!r} at {path!r} will REPLACE {target!r}'s "
                    f"INHERITED grants — the following inherited roles will NO LONGER apply at "
                    f"{path!r}: {sr}. (The specific-path entry takes precedence over ancestor "
                    "propagated grants.)"
                )
                reasons.append(
                    "granting a specific-path ACL replaces ancestor inherited (propagated) grants — "
                    f"inherited roles {{{sr}}} are shadowed (lost) at {path!r}"
                )
                risk = RISK_HIGH
            if widened:
                wr = ", ".join(sorted(widened))
                blast.append(f"NEW privileges at {path!r}: {target!r} gains {wr}")
                reasons.append(f"target gains new roles: {wr}")
            if not shadowed_inherited and not widened:
                blast.append(
                    f"grants {roles!r} to {target!r} at {path!r} — "
                    "no inherited grants detected to shadow; no new privileges detected"
                )
                reasons.append("no inherited grants to shadow; grant is additive at this path")
        else:
            if widened:
                wr = ", ".join(sorted(widened))
                blast.append(
                    f"WIDEN WARNING: revoking the specific entry at {path!r} for {target!r} "
                    f"RESTORES inherited grants — {target!r} will gain back: {wr}"
                )
                reasons.append(
                    "revoking a specific-path ACL restores inherited grants — "
                    f"the following roles become effective again at {path!r}: {wr}"
                )
                risk = RISK_HIGH
            if not widened:
                blast.append(
                    f"revokes {roles!r} from {target!r} at {path!r} — no inherited grants detected "
                    "that would widen access after revoke"
                )
                reasons.append("no inherited grants detected; revoke is straightforward")

    if "Administrator" in new_roles:
        blast.append("Administrator role grants ALL Proxmox privileges — this is the widest possible role")
        reasons.append("Administrator = super-role with full cluster privileges")
        risk = RISK_HIGH
    if path in ("/", "/storage"):
        blast.append(f"ACL at {path!r} affects ALL resources at that scope on the cluster")
        reasons.append(f"path {path!r} is a high-blast scope (root or storage-wide)")
        risk = RISK_HIGH

    if not current_direct_entries:
        current: dict = {}
    else:
        first = current_direct_entries[0]
        current = {k: first[k] for k in ("path", "roleid", "ugid", "propagate") if k in first}

    affected: list[dict] = []
    sev = "high" if risk == RISK_HIGH else "medium"
    if check_error is None:
        if shadowed_inherited:
            for role in sorted(shadowed_inherited):
                grp = group_inherited.get(role)
                via = f"inherited via group {grp}" if grp else "inherited (shadowed by the new direct entry)"
                affected.append({
                    "principal": target, "kind": kind, "via": via,
                    "change": "loses", "roles": [role], "at": path, "severity": "high",
                })
        if widened:
            affected.append({
                "principal": target, "kind": kind, "via": "direct",
                "change": "gains", "roles": sorted(widened), "at": path, "severity": sev,
            })

    # #2: who-ELSE can reach this path (members of group-type ACL entries at/above). CONTEXT only —
    # their access is UNCHANGED by editing the target's entry (per-principal model). NEVER gains/loses.
    if check_error is None and group_members:
        named: list[str] = []
        for grp, members in group_members.items():
            if members is None:
                complete = False
                blast.append(
                    f"could not enumerate members of group {grp!r} — "
                    "who-else-can-reach is INCOMPLETE (not a safety signal)"
                )
                continue
            for m in members:
                affected.append({
                    "principal": m, "kind": "group-member", "via": f"group {grp}",
                    "change": "unchanged", "roles": [], "at": path, "severity": "medium",
                })
                named.append(m)
        if named:
            blast.append(
                f"also has access at this path — UNCHANGED by this change: {', '.join(named)} "
                "(via group membership; their access is computed independently of the target's entry)"
            )

    return AclBlastResult(summary_lines=blast, risk=risk, risk_reasons=reasons,
                          current=current, affected=affected, complete=complete)


# ===========================================================================
# Firewall / network reach class.
#
# PER-RULE REACH, never "the cluster is exposed" as fact. A firewall rule's true
# effect depends on the whole ordered ruleset + default policy + enabled state; a
# single-rule classifier computes only what THIS rule permits/blocks IF it is the
# deciding match in an enforced, default-DROP firewall. Every line is phrased as a
# property of the RULE. Missing field => MAXIMAL, never benign (empty dport => ALL
# ports; empty source => anywhere; ipset/alias => unknown-conservative). enable=0 =>
# "staged, not active". Risk is only ever raised, never lowered.
# ===========================================================================

# Well-known admin/management ports -> service label. Used for sensitivity, NOT to
# narrow reach — an unrecognized port form is never downgraded to benign.
_SENSITIVE_PORTS: dict[int, str] = {
    22: "SSH", 8006: "PVE API", 3389: "RDP", 23: "telnet", 3306: "MySQL",
    5432: "Postgres", 6379: "Redis", 27017: "MongoDB", 9200: "Elasticsearch",
    2375: "Docker API", 2376: "Docker API (TLS)", 111: "rpcbind", 445: "SMB",
    135: "MSRPC", 139: "NetBIOS", 5985: "WinRM", 5986: "WinRM (TLS)",
}

# VNC display ports (5900-5999) are a remote-desktop admin surface — sensitive as a RANGE, not
# enumerable into the dict. Service NAMES PVE may carry as a dport (e.g. "ssh", "vnc") map to the
# same sensitivity; an UNRECOGNIZED name is NEVER downgraded to benign (spec honesty contract).
_VNC_LO, _VNC_HI = 5900, 5999
_SENSITIVE_SERVICE_NAMES: frozenset[str] = frozenset({
    "ssh", "vnc", "rdp", "ms-wbt-server", "telnet", "mysql", "postgres", "postgresql", "redis",
    "mongodb", "docker", "winrm", "smb", "microsoft-ds", "netbios-ssn", "rpcbind", "ldap", "ldaps",
    "elasticsearch",
})


def _is_vnc(port: int) -> bool:
    return _VNC_LO <= port <= _VNC_HI


# "Internal/private" by the SPEC's explicit RFC1918 / loopback / link-local list — NOT Python's
# broader ip.is_private (which also flags documentation/benchmark/reserved ranges like 203.0.113/24
# and 198.18/15). Classifying those as "internal" would UNDER-state the reach of a documentation /
# reserved source; treating a non-RFC1918 address as a concrete host/range is the conservative call.
_INTERNAL_NETS = [
    ipaddress.ip_network(c) for c in (
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
        "127.0.0.0/8", "169.254.0.0/16",
        "fc00::/7", "fe80::/10", "::1/128",
    )
]


def _is_internal_net(net: ipaddress.IPv4Network | ipaddress.IPv6Network) -> bool:
    """True if `net` is wholly contained in an RFC1918 / loopback / link-local range."""
    return any(
        net.version == base.version and net.subnet_of(base)  # type: ignore[arg-type]
        for base in _INTERNAL_NETS
    )


def _source_breadth(source: str | None) -> tuple[str, str]:
    """(kind, human) for a rule source. kind in {anywhere, internal, host, range, named}.

    None/empty/0.0.0.0/0/::/0 => anywhere (widest). RFC1918/loopback/link-local =>
    internal. A concrete public host => host; a public CIDR => range. A non-IP token
    (ipset '+name' / alias 'dc/name' / bare alias) => named (unknown breadth — NEVER
    treated as narrow; the membership is not resolved in v1).
    """
    s = (source or "").strip()
    if s == "":
        # No source given => widest, family-agnostic. Lead with 0.0.0.0/0 but name ::/0 too so an
        # IPv6 reader is not misled into thinking only IPv4 is covered.
        return "anywhere", "0.0.0.0/0 + ::/0 (the entire internet/WAN — no source restriction)"
    if s in ("0.0.0.0/0", "::/0"):
        # Honest per-TOKEN label: never claim 0.0.0.0/0 when the source was ::/0, or vice versa.
        return "anywhere", f"{s} (the entire internet/WAN)"
    try:
        net = ipaddress.ip_network(s, strict=False)
    except ValueError:
        return "named", f"{s} (named set/alias — membership not resolved)"
    if _is_internal_net(net):
        return "internal", f"{s} (internal/private)"
    if net.num_addresses == 1:
        return "host", f"{s} (a single host)"
    return "range", f"{s} (a public range)"


def _proto_suffix(proto: str | None) -> str:
    """The '/proto' suffix for a port label. tcp / unspecified => '/tcp' (the conventional default
    PVE rules carry); a named proto (udp, icmp, …) is reflected honestly so a udp rule is NOT
    narrated as '/tcp'. An 'any'/'all' proto drops the suffix (the port spans all protocols)."""
    p = (proto or "").strip().lower()
    if p in ("", "tcp"):
        return "/tcp"
    if p in ("any", "all"):
        return ""
    return f"/{p}"


def _port_label(dport: str | None, proto: str | None = None) -> str:
    """Human label for a dport. Empty => 'ALL ports' (maximal — NEVER benign). Recognizes a single
    well-known port; passes ranges/lists/service-names through verbatim (not downgraded). The
    protocol is reflected honestly (a udp rule is not narrated as '/tcp')."""
    d = (dport or "").strip()
    if not d:
        return "ALL ports"
    suffix = _proto_suffix(proto)
    if d.isdigit():
        n = int(d)
        svc = _SENSITIVE_PORTS.get(n) or ("VNC" if _is_vnc(n) else None)
        return f"{svc} ({d}{suffix})" if svc else f"port {d}{suffix}"
    return f"port(s) {d}" + (f" ({proto})" if suffix and proto and proto.strip().lower() != "tcp" else "")


def _port_is_sensitive(dport: str | None) -> bool:
    """True if the dport reaches a known mgmt/admin service — OVER-flag, never under-flag. Empty =>
    ALL ports => True. A single well-known port or a VNC display (5900-5999) => True. A range or
    comma-list => scan each member (a mgmt port hidden in '80,22' / '20:30' / a VNC range still
    trips). A service NAME maps via _SENSITIVE_SERVICE_NAMES; an UNRECOGNIZED non-numeric token is
    treated conservatively (True) — the spec forbids downgrading an unrecognized form to benign."""
    d = (dport or "").strip()
    if not d:
        return True   # ALL ports includes the sensitive ones
    if d.isdigit():
        n = int(d)
        return n in _SENSITIVE_PORTS or _is_vnc(n)
    unrecognized = False
    for member in d.split(","):
        member = member.strip()
        if not member:
            continue
        if member.isdigit():
            n = int(member)
            if n in _SENSITIVE_PORTS or _is_vnc(n):
                return True
            continue
        if ":" in member:
            # a range 'a:b' — flag if any sensitive port (or the VNC band) falls inside [a, b]
            lo, _, hi = member.partition(":")
            lo, hi = lo.strip(), hi.strip()
            if lo.isdigit() and hi.isdigit():
                a, b = int(lo), int(hi)
                if a <= b and (any(a <= p <= b for p in _SENSITIVE_PORTS) or (a <= _VNC_HI and b >= _VNC_LO)):
                    return True
            else:
                unrecognized = True  # malformed range — don't downgrade to benign
            continue
        # a service NAME token: known-sensitive => True; unknown => conservative (never benign)
        if member.lower() in _SENSITIVE_SERVICE_NAMES:
            return True
        unrecognized = True
    return unrecognized


@dataclass
class FirewallReachResult:
    """Per-rule reach classification. summary_lines are rule-scoped; affected is a list of dicts
    (effect/service/from/direction/scope/severity); risk is only ever raised, never lowered."""

    summary_lines: list[str]
    affected: list[dict]
    risk: str
    risk_reasons: list[str]
    complete: bool = True


# The standing framing disclaimer carried on every reach result. It is intentionally NOT a
# "this rule …" sentence; the per-rule-reach framing test treats it (any line containing
# "per-rule") as the one exception to the "every line starts with 'this rule'" rule.
_REACH_DISCLAIMER = (
    "PER-RULE REACH: this describes what THIS rule permits/blocks if it is the deciding match in "
    "an enforced, default-DROP firewall — NOT whether the cluster is actually exposed (that "
    "depends on the full ordered ruleset, the default policy, and whether the firewall is enabled "
    "for this scope)."
)


def compute_firewall_reach(
    action: str,
    direction: str,
    source: str | None,
    dport: str | None,
    proto: str | None,
    scope_label: str,
    enable: bool = True,
    mgmt_host: str | None = None,
) -> FirewallReachResult:
    """PURE per-rule reach classification. No API. See _REACH_DISCLAIMER for the framing contract.

    `proto`/`mgmt_host` are accepted for signature symmetry; an empty proto does NOT narrow reach
    (all protocols), and the mgmt_host self-lockout hint is a v1 nicety (may be None).
    """
    action = (action or "").upper()
    direction = (direction or "").lower()
    breadth, from_label = _source_breadth(source)
    service = _port_label(dport, proto)
    sensitive = _port_is_sensitive(dport)
    lines: list[str] = [_REACH_DISCLAIMER]
    reasons: list[str] = ["per-rule reach is heuristic; absence of HIGH is not a safety signal"]
    affected: list[dict] = []
    risk = RISK_MEDIUM

    # enable=0 — STAGED, not active. Never "permits"/"blocks"; risk floor only.
    if not enable:
        lines.append(
            f"this rule is DISABLED (enable=0) — STAGED, not active: it would "
            f"{action.lower() or 'apply'} {service} from {from_label} ({direction}) only once enabled"
        )
        affected.append({"effect": "staged", "service": service, "from": from_label,
                         "direction": direction, "scope": scope_label, "severity": "low"})
        return FirewallReachResult(summary_lines=lines, affected=affected, risk=risk,
                                   risk_reasons=reasons + ["rule is staged (enable=0)"])

    # Outbound — egress note, materially lower exposure than an inbound open. The engine only holds
    # `source`; an egress rule's DESTINATION is the rule's `dest` (not passed in v1), so do NOT
    # narrate the source as the destination — state the egress effect without a (false) target.
    if direction == "out":
        is_accept = action == "ACCEPT"
        verb = "PERMITS" if is_accept else "BLOCKS"
        lines.append(
            f"this rule {verb} OUTBOUND {service} (egress — lower exposure; the destination is the "
            "rule's dest, not classified in v1)"
        )
        affected.append({"effect": "permits" if is_accept else "blocks", "service": service,
                         "from": "(egress — dest not classified in v1)", "direction": "out",
                         "scope": scope_label, "severity": "low"})
        return FirewallReachResult(summary_lines=lines, affected=affected, risk=risk,
                                   risk_reasons=reasons)

    # Inbound.
    if action == "ACCEPT":
        if breadth == "anywhere":
            sev = "high"
        elif breadth in ("range", "named"):
            # public range or unresolved named set/alias — never "low"; HIGH if it reaches mgmt.
            sev = "high" if sensitive else "medium"
        elif breadth == "internal":
            sev = "medium"
        else:  # host
            sev = "medium" if sensitive else "low"
        lines.append(f"this rule PERMITS inbound {service} from {from_label} on {scope_label}")
        if sev == "high":
            lines.append(
                f"  -> reachable from {from_label}"
                + (" on a management/admin service" if sensitive else "")
            )
        affected.append({"effect": "permits", "service": service, "from": from_label,
                         "direction": "in", "scope": scope_label, "severity": sev})
        if sev == "high":
            risk = _max_risk(risk, RISK_HIGH)
    else:  # DROP / REJECT, inbound
        lockout = sensitive and breadth in ("anywhere", "range", "named", "internal")
        lines.append(f"this rule BLOCKS inbound {service} from {from_label} on {scope_label}")
        sev = "medium"
        if lockout:
            sev = "high"
            lines.append(
                "  -> LOCKOUT RISK: this rule blocks a management/admin port from a broad source; "
                "if it covers your access path you lose SSH/API (console to recover)"
            )
            risk = _max_risk(risk, RISK_HIGH)
        affected.append({"effect": "blocks", "service": service, "from": from_label,
                         "direction": "in", "scope": scope_label, "severity": sev})

    return FirewallReachResult(summary_lines=lines, affected=affected, risk=risk,
                               risk_reasons=reasons)


# ===========================================================================
# Network-apply lockout class — best-effort mgmt-interface naming on an UNCONDITIONAL HIGH.
#
# plan_network_apply is already RISK_HIGH unconditional, so naming the interface CANNOT under-flag;
# it only adds specificity. Non-identification (hostname mgmt_host, addressless ifaces, no match)
# => HIGH STANDS, never "no lockout". Risk is never lowered.
# ===========================================================================

@dataclass
class ApplyLockoutResult:
    summary_lines: list[str]
    affected: list[dict]
    risk: str
    risk_reasons: list[str]
    complete: bool = True


def _iface_holding_host(host: str | None, ifaces: list[dict]) -> str | None:
    """Best-effort: the iface whose address/cidr equals the mgmt host IP. None if host is not an IP,
    no iface matches, or addresses are absent (best-effort — caller keeps HIGH regardless)."""
    h = (host or "").strip()
    try:
        target = ipaddress.ip_address(h)
    except ValueError:
        return None
    for i in ifaces:
        for key in ("address", "cidr", "address6", "cidr6"):
            raw = i.get(key)
            if not raw:
                continue
            val = str(raw).split("/")[0].strip()
            if not val:
                continue
            try:
                if ipaddress.ip_address(val) == target:
                    return i.get("iface")
            except ValueError:
                continue
    return None


def compute_apply_lockout(pending_ifaces: list[str], mgmt_host: str | None,
                          ifaces: list[dict]) -> ApplyLockoutResult:
    """PURE. Best-effort naming on top of an UNCONDITIONAL HIGH (network apply is always RISK_HIGH).
    Names the pending iface that carries the mgmt host; non-identification => HIGH STANDS, never 'safe'.
    """
    mgmt_iface = _iface_holding_host(mgmt_host, ifaces)
    lines: list[str] = []
    affected: list[dict] = []
    reasons = ["network apply can lose connectivity; no automatic rollback (console to recover)"]
    if mgmt_iface and mgmt_iface in pending_ifaces:
        lines.append(
            f"LOCKOUT: this apply changes {mgmt_iface!r}, which holds the management host "
            f"{mgmt_host} — you will lose SSH/API access; recovery needs console/physical access"
        )
        affected.append({"iface": mgmt_iface, "effect": "management interface changing",
                         "holds": mgmt_host, "severity": "high"})
        reasons.append(f"pending change to {mgmt_iface} (management interface) — lockout")
    elif mgmt_iface:
        lines.append(
            f"management host {mgmt_host} is on {mgmt_iface!r}, which is NOT in the pending set — "
            "but apply is still RISK_HIGH (a dependent bond/VLAN under it may be affected, and the "
            "pending-change read may be incomplete)"
        )
        reasons.append(
            f"management host is on {mgmt_iface} (not pending) — HIGH stands; dependent layers may "
            "still be affected"
        )
    else:
        lines.append(
            f"could not identify the management interface (mgmt host {mgmt_host!r} is a hostname, is "
            "addressless on the read, or did not match any iface address) — RISK_HIGH STANDS; assume "
            "lockout risk"
        )
        reasons.append(
            "management interface not identified — RISK_HIGH stands; absence of a named lockout is "
            "NOT a safety signal"
        )
    return ApplyLockoutResult(summary_lines=lines, affected=affected, risk=RISK_HIGH,
                              risk_reasons=reasons)


# ===========================================================================
# Guest-destroy class — cascade what destroying a VM/CT actually does.
#
# Three outcome categories: WON'T PROCEED (PVE will refuse — protection=1,
# template-with-clones, running+force=False), REFERENCES (HA / replication /
# backup — each conditional on `purge`), INFORMATIONAL (disks, snapshots, pool).
# Risk is RISK_HIGH unconditional; only ever raised, never lowered.
# ===========================================================================

_GUEST_DESTROY_DISCLAIMER = (
    "GUEST-DESTROY CASCADE: computed at PLAN time against the cluster as currently read. "
    "Consequences are shown for THIS call's purge/force values — a different purge/force would "
    "change them. RISK is always HIGH for a destroy and is only ever raised, never lowered."
)


@dataclass(frozen=True)
class GuestDestroyInputs:
    """Everything compute_guest_destroy_blast needs — assembled by gather_guest_dependents.
    A None on any cluster-wide read means that read FAILED (not 'empty'); an empty list means
    the read succeeded and found nothing. guest_config None means the target's own config was
    unreadable."""
    vmid: str
    kind: str
    purge: bool
    force: bool
    guest_config: dict | None
    status: str
    ha_resources: list[dict] | None
    replication_jobs: list[dict] | None
    backup_jobs: list[dict] | None
    pools: list[dict] | None
    snapshots: list[dict] | None
    clone_configs: dict | None  # {vmid: config} of OTHER guests, for the template-clone scan


@dataclass(frozen=True)
class GuestDestroyBlastResult:
    summary_lines: list[str]
    affected: list[dict]
    risk: str
    risk_reasons: list[str]
    complete: bool = True


def _purge_effect(purge: bool, what: str) -> str:
    """Phrase a reference consequence conditional on purge — NEVER the opposite of what happens."""
    if purge:
        return f"PVE will REMOVE this {what} as part of purge=true"
    return f"left DANGLING (purge=false); remove this {what} manually after the destroy"


def compute_guest_destroy_blast(inp: GuestDestroyInputs) -> GuestDestroyBlastResult:
    """Pure, no I/O. Classify what destroying inp.vmid does, conditional on purge/force.
    Risk is RISK_HIGH unconditional (destroy is irreversible) and only ever raised."""
    res = f"{inp.kind}/{inp.vmid}"
    affected: list[dict] = []
    summary: list[str] = [_GUEST_DESTROY_DISCLAIMER]
    reasons: list[str] = []
    risk = RISK_HIGH
    complete = True

    # --- INFORMATIONAL: disks + storages (from the target's own config) ---
    if inp.guest_config is None:
        complete = False
        summary.append(f"could NOT read {res} config — cannot enumerate its disks")
    else:
        slots = _disk_slots(inp.guest_config)
        storages = sorted(set(slots.values()))
        for st in storages:
            via = sorted(s for s, sto in slots.items() if sto == st)
            affected.append({
                "category": "informational", "kind": "disk", "ref": st,
                "effect": f"frees disk(s) {', '.join(via)} on storage {st}",
                "severity": "info",
            })

    # --- WON'T PROCEED: protection=1 (force does NOT override) ---
    if inp.guest_config is not None and str(inp.guest_config.get("protection", 0)) in ("1", "True", "true"):
        affected.append({
            "category": "wont_proceed", "kind": "protection", "ref": res,
            "effect": "PVE will REFUSE: protection=1 is set; force does NOT override — "
                      "unset protection first",
            "severity": "high",
        })
        reasons.append("would be REFUSED: protection=1 (force does not override)")

    # --- WON'T PROCEED: running + force=False (force=True overrides this guard ONLY) ---
    if inp.status == "running" and not inp.force:
        affected.append({
            "category": "wont_proceed", "kind": "running", "ref": res,
            "effect": "PVE will REFUSE: the guest is running; re-call with force=true to "
                      "override the running guard (force does NOT override protection or "
                      "template-with-clones)",
            "severity": "high",
        })
        reasons.append("would be REFUSED: guest is running and force=false")
    elif inp.status not in ("running", "stopped") and not inp.force:
        # status="unknown" is the ONE input where unknown silently reads as safe — the running
        # guard above never fires, so a clean complete=True "go" would be a FALSE pass on a guest
        # that may actually be running. With force=True the running guard is overridden anyway, so
        # an unknown run-state is irrelevant — only flag when force=False.
        complete = False
        summary.append(
            f"could NOT confirm run-state of {res} (got {inp.status!r}); if it is running and "
            "force=false, PVE will REFUSE the destroy."
        )

    # --- WON'T PROCEED: template with linked clones (force does NOT override) ---
    if inp.guest_config is not None and str(inp.guest_config.get("template", 0)) in ("1", "True", "true"):
        if inp.clone_configs is None:
            complete = False
            summary.append(
                f"{res} is a TEMPLATE but could NOT scan for linked clones — if any exist, "
                "the destroy will be REFUSED"
            )
        else:
            clones = sorted(
                v for v, cfg in inp.clone_configs.items() if _is_linked_clone_of(cfg, str(inp.vmid))
            )
            if clones:
                affected.append({
                    "category": "wont_proceed", "kind": "template_clones",
                    "ref": ", ".join(clones),
                    "effect": f"PVE will REFUSE: this template has {len(clones)} linked clone(s) "
                              f"({', '.join(clones)}); destroying it would corrupt them; force does "
                              "NOT override",
                    "severity": "high",
                })
                reasons.append(f"would be REFUSED: template has linked clone(s) {', '.join(clones)}")
            # Even on a clean scan, name the blind spot: linked clones on directory/qcow2 storage
            # record their backing chain in the qcow2 file, NOT the PVE config, so they are invisible
            # to a config scan. Documented limitation (not a failed read) — caveat, never incomplete.
            summary.append(
                f"{res} is a TEMPLATE — linked-clone detection is config-based (covers "
                "LVM-thin/ZFS/RBD backing); directory/qcow2 backing chains are not visible in "
                "config and are NOT detected."
            )

    sid = f"{'vm' if inp.kind == 'qemu' else 'ct'}:{inp.vmid}"

    # --- REFERENCE: HA resource (conditional on purge) ---
    if inp.ha_resources is None:
        complete = False
        summary.append("could NOT read HA resources — cannot determine HA references")
    else:
        for hr in inp.ha_resources:
            if str(hr.get("sid")) == sid:
                affected.append({
                    "category": "reference", "kind": "ha", "ref": sid,
                    "effect": _purge_effect(inp.purge, "HA resource"),
                    "severity": "info" if inp.purge else "medium",
                })

    # --- REFERENCE: replication jobs (id == "<vmid>-N", exact vmid segment) ---
    if inp.replication_jobs is None:
        complete = False
        summary.append("could NOT read replication jobs — cannot determine replication references")
    else:
        for job in inp.replication_jobs:
            jid = str(job.get("id", ""))
            head, _, tail = jid.partition("-")
            if head == str(inp.vmid) and tail.isdigit():
                affected.append({
                    "category": "reference", "kind": "replication", "ref": jid,
                    "effect": _purge_effect(inp.purge, "replication job"),
                    "severity": "info" if inp.purge else "medium",
                })

    # --- REFERENCE: backup jobs (resolve per selection mode; only unrecognizable stays incomplete) ---
    if inp.backup_jobs is None:
        complete = False
        summary.append("could NOT read backup jobs — cannot determine backup-job references")
    else:
        for job in inp.backup_jobs:
            jid = str(job.get("id", "?"))
            # PVE may serialize all=0/pool=""/exclude="" on explicit-vmid jobs; value-coercion
            # (not key presence) is required to distinguish an active mode from a falsy default.
            all_mode = str(job.get("all", 0)) in ("1", "True", "true")
            pool_val = str(job.get("pool", "")).strip()
            pool_mode = bool(pool_val)
            exclude_set = {v.strip() for v in str(job.get("exclude", "")).split(",") if v.strip()}
            vmid_set = {v.strip() for v in str(job.get("vmid", "")).split(",") if v.strip()}

            # Tri-state coverage: True=covered, False=not covered, None=unresolvable.
            if all_mode:
                # all=1: every guest is covered UNLESS in the exclude list.
                covered: bool | None = str(inp.vmid) not in exclude_set
            elif pool_mode:
                # pool=X: covered iff target is a member of that pool AND not excluded.
                if inp.pools is None:
                    covered = None  # pool data unreadable — cannot resolve
                else:
                    target_pools = {
                        str(p.get("poolid", ""))
                        for p in inp.pools
                        if any(str(m.get("vmid")) == str(inp.vmid) for m in (p.get("members") or []))
                    }
                    covered = (pool_val in target_pools) and (str(inp.vmid) not in exclude_set)
            elif vmid_set:
                # Explicit vmid list (all=0/falsy, no pool): direct membership check.
                covered = str(inp.vmid) in vmid_set
            else:
                # Unrecognizable selection (e.g. all=0, no pool, no vmid).
                covered = None

            if covered is None:
                complete = False
                summary.append(
                    f"backup job {jid} uses an unresolvable selection — could NOT confirm whether "
                    f"{inp.vmid} is covered"
                )
            elif covered:
                affected.append({
                    "category": "reference", "kind": "backup_job", "ref": jid,
                    "effect": _purge_effect(inp.purge, "backup-job membership"),
                    "severity": "info" if inp.purge else "medium",
                })
            # covered is False → resolved, not covered → no entry, no incomplete flag

    # --- INFORMATIONAL: snapshots ---
    if inp.snapshots is None:
        complete = False
        summary.append(f"could NOT read snapshots for {res} — cannot confirm what is removed")
    else:
        # PVE's snapshot endpoint always includes a synthetic {"name": "current"} entry (the live
        # state, a reserved name) — it is NOT a real snapshot. Exclude it from the count/emit.
        real = [s for s in inp.snapshots if s.get("name") != "current"]
        if real:
            affected.append({
                "category": "informational", "kind": "snapshots", "ref": str(len(real)),
                "effect": f"removes {len(real)} snapshot(s) with the guest",
                "severity": "info",
            })

    # --- INFORMATIONAL: pool membership ---
    if inp.pools is None:
        complete = False
        summary.append(f"could NOT read pools — cannot confirm {res} pool membership")
    else:
        for p in inp.pools:
            members = p.get("members") or []
            if any(str(m.get("vmid")) == str(inp.vmid) for m in members):
                affected.append({
                    "category": "informational", "kind": "pool", "ref": str(p.get("poolid", "")),
                    "effect": f"removes {res} from pool {p.get('poolid')}",
                    "severity": "info",
                })

    return GuestDestroyBlastResult(
        summary_lines=summary, affected=affected, risk=risk,
        risk_reasons=reasons, complete=complete,
    )


def _safe(fn, default=None):
    """Call fn(); on ANY exception return `default` (the 'read failed' sentinel)."""
    try:
        return fn()
    except Exception:
        return default


def _resolve_pool_members(api) -> list[dict]:
    """Resolve each pool's MEMBER list. pools_list returns only summaries (no members); membership
    lives in pool_get(api, poolid). Raises on ANY failure (pools_list OR a single pool_get) so the
    caller's _safe turns it into None == 'membership unknown' (never under-report by dropping a pool).
    """
    out: list[dict] = []
    for summary in pools_list(api) or []:
        pid = str(summary.get("poolid", ""))
        if not pid:
            continue
        out.append({"poolid": pid, "members": pool_get(api, pid).get("members") or []})
    return out


def gather_guest_dependents(api, vmid: str, kind: str, node: str | None,
                            purge: bool, force: bool) -> GuestDestroyInputs:
    """I/O: read everything compute needs. NEVER raises — a failed read becomes None so the
    honesty contract (None == unknown, [] == confirmed-empty) holds downstream."""
    cfg = _safe(lambda: guest_config_get(api, vmid, kind, node))
    # an empty dict from a 200 {"data": null} is an unreadable config, not 'no disks'
    if not cfg:
        cfg = None

    status = "unknown"
    gs = _safe(lambda: api.guest_status(vmid, kind, node))
    if isinstance(gs, dict) and gs.get("status"):
        status = str(gs["status"])

    # The peer-config clone scan is only needed (and only correct) when the TARGET is a template.
    # Decision table for clone_configs (the sentinel compute reads as 'could not scan'):
    #   - target cfg unreadable (cfg is None)  -> None  (template-ness unknown; stay incomplete)
    #   - target readable, NOT a template      -> {}    (compute's template branch won't use it)
    #   - target readable AND a template:
    #       - cluster_resources read failed     -> None
    #       - ANY peer config read failed/empty -> None  (a dropped peer may be a hidden clone)
    #       - else                              -> {peer_vmid: cfg, ...}
    clone_configs: dict | None
    is_template = cfg is not None and str(cfg.get("template", 0)) in ("1", "True", "true")
    if cfg is None:
        clone_configs = None
    elif not is_template:
        clone_configs = {}
    else:
        rows = _safe(lambda: cluster_resources(api))
        if rows is None:
            clone_configs = None
        else:
            scanned: dict = {}
            any_peer_failed = False
            for rrow in rows:
                if rrow.get("type") not in ("qemu", "lxc"):
                    continue
                rid = str(rrow.get("vmid", ""))
                if rid == str(vmid) or not rid:
                    continue
                ccfg = _safe(lambda rrow=rrow, rid=rid: guest_config_get(
                    api, rid, str(rrow.get("type")), rrow.get("node")))
                if ccfg:
                    scanned[rid] = ccfg
                else:
                    # A peer we could NOT read may itself be a linked clone we now cannot see.
                    # Dropping it silently would let compute find no clones -> false complete=True.
                    any_peer_failed = True
            clone_configs = None if any_peer_failed else scanned

    return GuestDestroyInputs(
        vmid=str(vmid), kind=str(kind), purge=purge, force=force,
        guest_config=cfg, status=status,
        ha_resources=_safe(lambda: ha_resources_list(api)),
        replication_jobs=_safe(lambda: api._get("/cluster/replication") or []),
        backup_jobs=_safe(lambda: api._get("/cluster/backup") or []),
        pools=_safe(lambda: _resolve_pool_members(api)),
        snapshots=_safe(lambda: api.snapshot_list(vmid, kind, node)),
        clone_configs=clone_configs,
    )


def guest_destroy_blast(api, vmid: str, kind: str, node: str | None,
                        purge: bool, force: bool) -> GuestDestroyBlastResult:
    """Convenience: gather (I/O, fail-closed) then compute (pure)."""
    return compute_guest_destroy_blast(
        gather_guest_dependents(api, vmid, kind, node, purge, force))
