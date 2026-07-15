"""PBS disk administration — physical disk list/SMART/init/wipe + directory/zfs backend
creation (Wave 2d of the full-surface campaign, `.scratch/2026-07-15-full-surface-campaign.md`,
"2d — PBS disks").

Split out as its own module (not folded into `pbs_node.py`, which already carries dns/time/
network/certs/services/subscription/status/tasks/journal/syslog for Wave 2c) — disk admin is a
large, self-contained concern with its own validator/schema surface, mirroring how PVE keeps
`node_lifecycle.py` (disks + storage backends + node config + bulk power) as a module distinct
from `observability.py` (journal/syslog/tasks). `tools/pbs_disks.py` is the matching wrapper
module, same split as `pbs_node.py`/`tools/pbs_node.py`.

Schema truth: the LIVE api-viewer schema, https://pbs.proxmox.com/docs/api-viewer/apidoc.js,
pulled 2026-07-15 (full param detail, not just the path+verb table in
`.scratch/api-schemas-2026-07-15/methods-pbs.json`). The live PVE schema
(https://pve.proxmox.com/pve-docs/api-viewer/apidoc.js, pulled the same day) was ALSO fetched and
diffed against this module's endpoints — every "verified against the live PVE schema" claim below
was actually checked, not assumed. NONE of this module is live-verified against a running PBS
yet; every backend function is schema-derived only — "Smoke-confirm:" comments name the specific
unverified detail.

Endpoint table (all under /nodes/{node}/disks/..., node defaults to "localhost" — mirrors
pbs_node.py's own `node: str = "localhost"` convention, not PVE's `node or cfg.node`):

  GET    /list                       — disks_list             (read)
  GET    /smart                      — disk_smart              (read)
  PUT    /wipedisk                   — disk_wipe               (MUTATION, HIGH, no undo)
  POST   /initgpt                    — disk_initgpt            (MUTATION, HIGH)
  GET    /directory                  — disk_directory_list     (read)
  POST   /directory                  — disk_directory_create   (MUTATION, HIGH)
  DELETE /directory/{name}           — disk_directory_delete   (MUTATION, HIGH, SYNCHRONOUS)
  GET    /zfs                        — disk_zfs_list           (read)
  GET    /zfs/{name}                 — disk_zfs_get            (read)
  POST   /zfs                        — disk_zfs_create         (MUTATION, HIGH)

10 tools total (5 read, 5 mutation) — NOT the ~11 the campaign route's original guess named,
because two of the guessed backends don't exist on PBS (see gap #1 below) and one guessed
mutation (zfs delete) doesn't exist either (gap #2) while one un-guessed read (zfs/{name})
does exist and is built. "Build ONLY what the live schema exposes" — this is the exact set.

SCHEMA DIFFERENCES FROM PVE (confirmed against the live PVE schema too, not assumed — PVE's own
node_lifecycle.py disk endpoints were re-checked against https://pve.proxmox.com/pve-docs/
api-viewer/apidoc.js the same day this module was written):

  1. **Disk identifier format is BARE, not /dev/-prefixed.** PBS's own `disk`/`devices` patterns
     (verified on GET smart, PUT wipedisk, POST initgpt, POST directory, POST zfs) all match a
     bare `/sys/block/<name>` BASENAME — e.g. "sda", "nvme0n1" — with NO "/dev/" prefix anywhere
     in the pattern. PVE's equivalent `disk` pattern (verified: GET smart, PUT wipedisk, POST
     initgpt) is `^/dev/[a-zA-Z0-9/]+$` — the OPPOSITE convention, matching
     `backends._check_disk`'s own "/dev/..." requirement. A caller porting a PVE-style
     "/dev/sda" value into any tool in this module is rejected by Proximo's own validator here —
     matching what a real PBS server would also reject.
  2. **PBS has only TWO disk-backend types: directory and zfs.** The live schema has NO
     /nodes/{node}/disks/lvm* or /nodes/{node}/disks/lvmthin* path anywhere (confirmed: grepped
     the full flattened path list) — unlike PVE, which exposes all four (directory/lvm/lvmthin/
     zfs, each with GET+POST on the collection and DELETE on the named resource, confirmed
     against the live PVE schema). No pbs_node_disk_lvm_* or pbs_node_disk_lvmthin_* tools exist
     in this module because there is nothing on PBS's own API to call.
  3. **PBS's zfs backend has NO delete endpoint.** GET+POST /nodes/{node}/disks/zfs and GET
     /nodes/{node}/disks/zfs/{name} all exist, but there is no DELETE
     /nodes/{node}/disks/zfs/{name} anywhere in the live PBS schema — you can create a zpool via
     this API but cannot destroy it via this API. PVE, by contrast, DOES expose DELETE
     /nodes/{node}/disks/zfs/{name} (confirmed against the live PVE schema — same for its
     lvm/lvmthin/directory backends). No `disk_zfs_delete` / `pbs_node_disk_zfs_delete` exists
     here — there is nothing to build, not an oversight.
  4. **Directory-backend delete is SYNCHRONOUS on PBS, unlike PVE.** DELETE
     /nodes/{node}/disks/directory/{name}'s own `returns` schema is `{"type": "null"}`
     (confirmed) — unlike PVE's identically-shaped DELETE, whose `returns` schema is
     `{"type": "string"}` matching the UPID pattern (confirmed against the live PVE schema, and
     matching how node_lifecycle.py's own `plan_node_storage_backend_delete` already treats ALL
     four PVE backend deletes as async/"submitted"). This is the ONLY disk mutation in this
     module that is NOT async: `disk_directory_delete` returns None synchronously, and its
     wrapper records outcome="ok", not "submitted".
  5. **Directory-backend delete has NO cleanup option on PBS.** The live schema's DELETE
     /nodes/{node}/disks/directory/{name} parameters are `{name, node}` ONLY — no
     `cleanup-disks`/`cleanup-config` flags exist. PVE's equivalent DELETE exposes BOTH on every
     one of its four backends (confirmed against the live PVE schema — matching
     node_lifecycle.py's own `cleanup: bool` parameter on `pve_node_storage_backend_delete`).
     The underlying disk is NEVER wiped by PBS's directory-delete; only the systemd mount unit +
     datastore config mapping are removed. There is no PBS-side equivalent to expose.
  6. **PBS additionally exposes an individual zpool-status read PVE also has but Proximo never
     built.** GET /nodes/{node}/disks/zfs/{name} ("Get zpool status details") exists on BOTH
     planes at the identical path+verb (confirmed against the live PVE schema) — Proximo's own
     PVE `node_storage_backend_list` only ever covered the collection-level list, never the
     per-name detail read, so this is a gap in Proximo's OWN PVE coverage, not a PBS-only
     feature (same pattern already noted in pbs_node.py's docstring for subscription_check/
     delete). Built here as `disk_zfs_get` / `pbs_node_disk_zfs_get` since it is squarely in this
     wave's disk-admin scope; a future PVE-touch wave could add the PVE-side counterpart.
  7. **The disks/list filter param has a different name AND a different enum.** PBS's filter is
     `usage-type`, enum {unused, mounted, lvm, zfs, devicemapper, partitions, filesystem}. PVE's
     is `type`, enum {unused, journal_disks} (confirmed against the live PVE schema) — not just a
     rename, a materially different, narrower filter.
  8. **PBS's zfs raidlevel enum has no dRAID.** PBS: {single, mirror, raid10, raidz, raidz2,
     raidz3}. PVE additionally offers {draid, draid2, draid3} plus a separate `draid-config`
     parameter (confirmed against the live PVE schema) — dRAID is a PVE-only capability at this
     endpoint; not built here since PBS's own schema doesn't accept it.
  9. **wipedisk can target a partition on PBS; initgpt/smart/directory-create/zfs-create cannot.**
     PBS's own `disk` pattern on PUT /disks/wipedisk permits an OPTIONAL trailing partition
     suffix (`\\d*` for ATA/SCSI/virtio names, `(?:p\\d+)?` for nvme) — the other four endpoints'
     `disk`/`devices` patterns are whole-disk-only (no trailing digits accepted at all). Two
     separate validators enforce this distinction here (`_check_pbs_wholedisk` vs
     `_check_pbs_disk_or_partition`). PVE draws no such line: its wipedisk/initgpt/smart `disk`
     patterns are IDENTICAL to each other (`^/dev/[a-zA-Z0-9/]+$`, confirmed against the live PVE
     schema) — PVE's schema doesn't distinguish whole-disk from partition at all.

REGEX STRICTNESS NOTE (deliberate, not a bug here): PBS's own JSON-Schema `pattern` strings for
the whole-disk and disk-or-partition shapes are written as `/^A|B$/` — because `|` has the
lowest precedence in a regex, this literally parses as `(?:^A)|(?:B$)`, i.e. "starts with A" OR
"ends with B", NOT "the whole string is A or B" (the obviously-intended meaning; almost certainly
an upstream authoring slip, not a deliberate loosening). This module's validators enforce the
clearly-intended full-string match (`^(?:A|B)\\Z`, with `\\Z` per this codebase's established
trailing-newline-bypass discipline — see `backends._check_disk`'s own docstring) rather than
mirroring the upstream pattern's literal (and more permissive) behavior — the same defensive
posture `backends._check_disk` already takes with its own extra component-level traversal check
beyond what its source pattern alone would catch.

Security posture:
- All path components validated with \\Z-anchored regexes (trailing-newline bypass rejected),
  mirroring pbs_node.py's / pbs_access.py's shared discipline.
- disk/devices: charset+shape validated against PBS's own (corrected, see above) pattern; no
  "/dev/" prefix accepted (would silently 404/400 against a real PBS, and — more importantly —
  accepting it would mislead a caller who assumes PVE's /dev/ convention applies here too).
- datastore name (directory/zfs `name`): PBS's own `pattern` + `minLength`/`maxLength` (3-32)
  enforced together — the regex alone doesn't encode the length bounds.
- zpool name (`disk_zfs_get`'s path `name`): PBS documents a DIFFERENT, letter-start-only pattern
  for this one read endpoint (see gap-adjacent note in `_check_pbs_zpool_name`'s docstring) —
  validated separately, not reused from the datastore-name validator.
- Every mutation in this module is a disk-consuming, disk-formatting, or disk-wiping operation —
  ALL FIVE are rated RISK_HIGH, mirroring node_lifecycle.py's PVE disk-admin ratings exactly (no
  backend-dependent downgrade, matching `plan_node_storage_backend_create`/`_delete`'s own
  uniform-HIGH precedent). Plan factories are PURE (no API read) — mirrors node_lifecycle.py's
  disk plan factories, none of which do CAPTURE-or-declare either.
"""

from __future__ import annotations

import re

from .backends import ProximoError
from .pbs import PbsBackend, _check_pbs_node
from .planning import RISK_HIGH, Plan

# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

# Whole-disk, bare /sys/block/<name> basename (source: 'disk' property pattern on GET smart, POST
# initgpt, POST directory, and each item of POST zfs's comma-separated 'devices' — all four share
# this identical pattern on the live PBS schema, 2026-07-15). Corrected to fully anchor both ends
# per this module's REGEX STRICTNESS NOTE above (PBS's own literal pattern only anchors one side
# per alternative branch).
_WHOLEDISK_RE = re.compile(r"^(?:(?:h|s|x?v)d[a-z]+|nvme\d+n\d+)\Z")

# Whole-disk OR one trailing partition, PUT wipedisk ONLY (source: 'disk' property pattern on PUT
# /disks/wipedisk, live PBS schema — the sole endpoint in this module whose disk pattern accepts a
# partition suffix). Same both-ends-anchored correction as _WHOLEDISK_RE.
_DISK_OR_PARTITION_RE = re.compile(r"^(?:(?:h|s|x?v)d[a-z]+\d*|nvme\d+n\d+(?:p\d+)?)\Z")

# Datastore name, POST directory/zfs 'name' + DELETE directory/{name} (source: 'name' property
# pattern, live PBS schema — minLength 3 / maxLength 32 enforced separately, the regex alone
# doesn't encode length).
_DATASTORE_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*\Z")

# Zpool name, GET /disks/zfs/{name} ONLY (source: 'name' property pattern on that one endpoint,
# live PBS schema — letter-only start, no documented maxLength; genuinely a DIFFERENT pattern from
# the datastore-name one above, not a copy-paste — see module docstring gap notes).
_ZPOOL_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]+\Z")

_VALID_FILESYSTEMS = frozenset({"ext4", "xfs"})
_VALID_RAIDLEVELS = frozenset({"single", "mirror", "raid10", "raidz", "raidz2", "raidz3"})
# NOTE: PBS's own schema documents this enum in lowercase ("on"/"off") while its OWN 'default'
# field is displayed as "On" (capital O) — a schema-authoring quirk on PBS's side, not
# reconciled here. Validated against the declared enum exactly (lowercase); a caller who sends
# "On" is rejected, matching what the enum (not the mismatched default label) actually declares.
_VALID_COMPRESSION = frozenset({"gzip", "lz4", "lzjb", "zle", "zstd", "on", "off"})
_ASHIFT_MIN, _ASHIFT_MAX = 9, 16


def _check_pbs_wholedisk(disk: str) -> str:
    s = str(disk)
    if not _WHOLEDISK_RE.match(s):
        raise ProximoError(
            f"invalid PBS disk name: {disk!r} — expected a bare /sys/block/<name> basename "
            "(e.g. 'sda', 'nvme0n1'), no '/dev/' prefix and no partition suffix"
        )
    return s


def _check_pbs_disk_or_partition(disk: str) -> str:
    s = str(disk)
    if not _DISK_OR_PARTITION_RE.match(s):
        raise ProximoError(
            f"invalid PBS disk/partition name: {disk!r} — expected a bare /sys/class/block/<name> "
            "basename, optionally with a partition suffix (e.g. 'sda', 'sda1', 'nvme0n1p1'), no "
            "'/dev/' prefix"
        )
    return s


def _check_pbs_datastore_name(name: str) -> str:
    s = str(name)
    if not (3 <= len(s) <= 32) or not _DATASTORE_NAME_RE.match(s):
        raise ProximoError(
            f"invalid PBS datastore name: {name!r} (must start with alnum/underscore, then "
            "alnum/./_/-, 3-32 chars)"
        )
    return s


def _check_pbs_zpool_name(name: str) -> str:
    s = str(name)
    if not _ZPOOL_NAME_RE.match(s):
        raise ProximoError(
            f"invalid ZFS pool name: {name!r} (must start with a letter, then alnum/./:/_/-, "
            ">=2 chars)"
        )
    return s


def _check_devices_csv(devices: str) -> str:
    """Validate a comma-separated device list (zfs create's 'devices' wire shape: a single string,
    not a JSON array — matches node_lifecycle.py's own PVE `devices: str` convention)."""
    s = str(devices)
    parts = s.split(",")
    if not parts or any(not p for p in parts):
        raise ProximoError(
            f"invalid devices list: {devices!r} — comma-separated, no empty segments"
        )
    for p in parts:
        _check_pbs_wholedisk(p)
    return s


def _check_filesystem(fs: str) -> str:
    s = str(fs)
    if s not in _VALID_FILESYSTEMS:
        raise ProximoError(f"invalid filesystem: {fs!r} (expected one of {sorted(_VALID_FILESYSTEMS)})")
    return s


def _check_raidlevel(raidlevel: str) -> str:
    s = str(raidlevel)
    if s not in _VALID_RAIDLEVELS:
        raise ProximoError(
            f"invalid ZFS raidlevel: {raidlevel!r} (expected one of {sorted(_VALID_RAIDLEVELS)}; "
            "note: dRAID is PVE-only, not accepted by PBS's own schema)"
        )
    return s


def _check_compression(compression: str) -> str:
    s = str(compression)
    if s not in _VALID_COMPRESSION:
        raise ProximoError(
            f"invalid ZFS compression: {compression!r} (expected one of {sorted(_VALID_COMPRESSION)})"
        )
    return s


def _check_ashift(ashift: int) -> int:
    try:
        n = int(ashift)
    except (TypeError, ValueError) as exc:
        raise ProximoError(f"invalid ashift: {ashift!r} (must be an integer)") from exc
    if not (_ASHIFT_MIN <= n <= _ASHIFT_MAX):
        raise ProximoError(f"invalid ashift: {ashift!r} (must be {_ASHIFT_MIN}-{_ASHIFT_MAX})")
    return n


# ---------------------------------------------------------------------------
# Backend functions — reads
# ---------------------------------------------------------------------------

def disks_list(
    api: PbsBackend,
    node: str = "localhost",
    include_partitions: bool | None = None,
    skipsmart: bool | None = None,
    usage_type: str | None = None,
) -> list[dict]:
    """GET /nodes/{node}/disks/list — physical disk inventory. Returns a list of dicts (name/
    devpath/disk-type/size/status/used/model/serial/wwn/wearout/rpm/gpt/partitions...)."""
    node = _check_pbs_node(node)
    params: dict = {}
    if include_partitions is not None:
        params["include-partitions"] = include_partitions
    if skipsmart is not None:
        params["skipsmart"] = skipsmart
    if usage_type is not None:
        params["usage-type"] = str(usage_type)
    return api._get(f"/nodes/{node}/disks/list", params=params or None) or []


def disk_smart(
    api: PbsBackend,
    disk: str,
    node: str = "localhost",
    healthonly: bool | None = None,
) -> dict:
    """GET /nodes/{node}/disks/smart?disk=... — SMART attributes + health for one disk. Returns
    {status, attributes, wearout}."""
    disk = _check_pbs_wholedisk(disk)
    node = _check_pbs_node(node)
    params: dict = {"disk": disk}
    if healthonly is not None:
        params["healthonly"] = healthonly
    return api._get(f"/nodes/{node}/disks/smart", params=params) or {}


def disk_directory_list(api: PbsBackend, node: str = "localhost") -> list[dict]:
    """GET /nodes/{node}/disks/directory — list systemd datastore mount units. Returns a list of
    {device, name, path, removable, unitfile, filesystem?, options?} dicts."""
    node = _check_pbs_node(node)
    return api._get(f"/nodes/{node}/disks/directory") or []


def disk_zfs_list(api: PbsBackend, node: str = "localhost") -> list[dict]:
    """GET /nodes/{node}/disks/zfs — list zpools. Returns a list of {name, health, size, alloc,
    free, frag, dedup} dicts (summary only — for one pool's full vdev tree use disk_zfs_get)."""
    node = _check_pbs_node(node)
    return api._get(f"/nodes/{node}/disks/zfs") or []


def disk_zfs_get(api: PbsBackend, name: str, node: str = "localhost") -> dict:
    """GET /nodes/{node}/disks/zfs/{name} — one zpool's status/vdev tree. Also on PVE at the
    identical path+verb, but never built there (see module docstring gap #6)."""
    name = _check_pbs_zpool_name(name)
    node = _check_pbs_node(node)
    return api._get(f"/nodes/{node}/disks/zfs/{name}") or {}


# ---------------------------------------------------------------------------
# Backend functions — mutations
# ---------------------------------------------------------------------------

def disk_wipe(api: PbsBackend, disk: str, node: str = "localhost") -> object:
    """PUT /nodes/{node}/disks/wipedisk — wipe a disk OR partition. Returns the worker UPID
    (async — Smoke-confirm: shape not live-verified). IRREVERSIBLE, destroys all data."""
    disk = _check_pbs_disk_or_partition(disk)
    node = _check_pbs_node(node)
    return api._put(f"/nodes/{node}/disks/wipedisk", {"disk": disk})  # Smoke-confirm: PUT, async UPID


def disk_initgpt(api: PbsBackend, disk: str, node: str = "localhost", uuid: str | None = None) -> object:
    """POST /nodes/{node}/disks/initgpt — write a new GPT partition table (whole disk only, no
    partition suffix accepted — unlike disk_wipe). Returns the worker UPID (async — Smoke-confirm:
    shape not live-verified). IRREVERSIBLE, overwrites the existing partition table."""
    disk = _check_pbs_wholedisk(disk)
    node = _check_pbs_node(node)
    data: dict = {"disk": disk}
    if uuid is not None:
        data["uuid"] = str(uuid)
    return api._post(f"/nodes/{node}/disks/initgpt", data)  # Smoke-confirm: POST, async UPID


def disk_directory_create(
    api: PbsBackend,
    disk: str,
    name: str,
    node: str = "localhost",
    filesystem: str | None = None,
    add_datastore: bool | None = None,
    removable_datastore: bool | None = None,
) -> object:
    """POST /nodes/{node}/disks/directory — format 'disk' with a filesystem and mount it under
    /mnt/datastore/<name>. Returns the worker UPID (async — Smoke-confirm: shape not
    live-verified). IRREVERSIBLE, FORMATS the named disk."""
    disk = _check_pbs_wholedisk(disk)
    name = _check_pbs_datastore_name(name)
    node = _check_pbs_node(node)
    data: dict = {"disk": disk, "name": name}
    if filesystem is not None:
        data["filesystem"] = _check_filesystem(filesystem)
    if add_datastore:
        data["add-datastore"] = True
    if removable_datastore:
        data["removable-datastore"] = True
    return api._post(f"/nodes/{node}/disks/directory", data)  # Smoke-confirm: POST, async UPID


def disk_directory_delete(api: PbsBackend, name: str, node: str = "localhost") -> object:
    """DELETE /nodes/{node}/disks/directory/{name} — remove the mount unit + datastore config
    mapping for 'name'. Returns None SYNCHRONOUSLY (PBS's own schema: returns.type == "null" —
    unlike PVE's identically-shaped delete, which is async/UPID; see module docstring gap #4).
    NO cleanup-disks option exists on PBS (gap #5) — the underlying disk data is never wiped by
    this call."""
    name = _check_pbs_datastore_name(name)
    node = _check_pbs_node(node)
    return api._delete(f"/nodes/{node}/disks/directory/{name}")


def disk_zfs_create(
    api: PbsBackend,
    devices: str,
    name: str,
    raidlevel: str,
    node: str = "localhost",
    ashift: int | None = None,
    compression: str | None = None,
    add_datastore: bool | None = None,
) -> object:
    """POST /nodes/{node}/disks/zfs — create a zpool from 'devices' and mount it under
    /mnt/datastore/<name>. Returns the worker UPID (async — Smoke-confirm: shape not
    live-verified). IRREVERSIBLE, FORMATS the named disk(s) — and there is NO delete endpoint for
    the result (module docstring gap #3): once created, this zpool cannot be destroyed through
    this API."""
    devices = _check_devices_csv(devices)
    name = _check_pbs_datastore_name(name)
    raidlevel = _check_raidlevel(raidlevel)
    node = _check_pbs_node(node)
    data: dict = {"devices": devices, "name": name, "raidlevel": raidlevel}
    if ashift is not None:
        data["ashift"] = _check_ashift(ashift)
    if compression is not None:
        data["compression"] = _check_compression(compression)
    if add_datastore:
        data["add-datastore"] = True
    return api._post(f"/nodes/{node}/disks/zfs", data)  # Smoke-confirm: POST, async UPID


# ---------------------------------------------------------------------------
# Plan factories — all PURE (no API read), all RISK_HIGH (mirrors node_lifecycle.py's PVE
# disk-admin ratings exactly — see module docstring's Security posture note).
# ---------------------------------------------------------------------------

def plan_disk_wipe(disk: str, node: str = "localhost") -> Plan:
    """Plan for pbs_node_disk_wipe — wipe a disk or partition. RISK_HIGH, no undo. Mirrors
    node_lifecycle.py's plan_node_disk_wipe, adapted for PBS's bare disk-name convention and its
    optional partition-targeting (see module docstring gap #9)."""
    disk = _check_pbs_disk_or_partition(disk)
    node = _check_pbs_node(node)
    return Plan(
        action="pbs_node_disk_wipe",
        target=f"pbs/node/{node}/disks/{disk}",
        change=f"DESTROYS all data/partition table on {disk!r} (PBS node {node!r}); irreversible",
        current={},
        blast_radius=[
            f"disk/partition {disk!r} on PBS node {node!r}: DESTROYS all data, partition table, "
            "and filesystems on this device",
        ],
        risk=RISK_HIGH,
        risk_reasons=[
            f"wipes the entire block device or partition {disk!r} — all data, partitions, and "
            "filesystems are lost; no undo possible",
        ],
        note=(
            f"No undo: PUT /disks/wipedisk on {disk!r} is a destructive, irreversible operation. "
            "All data on the device is permanently erased. Note: unlike initgpt, wipedisk may "
            "target a PARTITION as well as a whole disk."
        ),
    )


def plan_disk_initgpt(disk: str, node: str = "localhost", uuid: str | None = None) -> Plan:
    """Plan for pbs_node_disk_initgpt — initialize a GPT partition table on a whole disk.
    RISK_HIGH. Mirrors node_lifecycle.py's plan_node_disk_initgpt."""
    disk = _check_pbs_wholedisk(disk)
    node = _check_pbs_node(node)
    uuid_note = f" (uuid={uuid!r})" if uuid else ""
    return Plan(
        action="pbs_node_disk_initgpt",
        target=f"pbs/node/{node}/disks/{disk}",
        change=(
            f"writes a new GPT partition table on {disk!r} (PBS node {node!r}); overwrites "
            f"existing partition table{uuid_note}"
        ),
        current={},
        blast_radius=[
            f"disk {disk!r} on PBS node {node!r}: overwrites the partition table — existing "
            "partitions and their data are rendered inaccessible",
        ],
        risk=RISK_HIGH,
        risk_reasons=[
            f"initializes a new GPT partition table on {disk!r}, destroying the existing one; "
            "irreversible",
        ],
        note=(
            f"No undo: POST /disks/initgpt on {disk!r} overwrites the partition table. Whole-disk "
            "only (unlike wipedisk, this does not accept a partition suffix). Irreversible."
        ),
    )


def plan_disk_directory_create(
    disk: str,
    name: str,
    node: str = "localhost",
    filesystem: str | None = None,
    add_datastore: bool | None = None,
    removable_datastore: bool | None = None,
) -> Plan:
    """Plan for pbs_node_disk_directory_create — format 'disk' and mount it as a directory
    datastore. RISK_HIGH (mirrors node_lifecycle.py's plan_node_storage_backend_create, which
    rates ALL backends HIGH uniformly, not backend-dependent)."""
    disk = _check_pbs_wholedisk(disk)
    name = _check_pbs_datastore_name(name)
    node = _check_pbs_node(node)
    extra = []
    if filesystem is not None:
        filesystem = _check_filesystem(filesystem)
        extra.append(f"filesystem={filesystem!r}")
    if add_datastore:
        extra.append("add-datastore=True")
    if removable_datastore:
        extra.append("removable-datastore=True")
    extra_note = f" ({', '.join(extra)})" if extra else ""
    return Plan(
        action="pbs_node_disk_directory_create",
        target=f"pbs/node/{node}/disks/directory/{name}",
        change=f"create directory datastore {name!r} on disk {disk!r} (PBS node {node!r}){extra_note}",
        current={},
        blast_radius=[
            f"FORMATS disk {disk!r} into the new directory datastore {name!r} on PBS node "
            f"{node!r} — any pre-existing data on that disk is destroyed immediately and "
            f"irreversibly{extra_note}",
        ],
        risk=RISK_HIGH,
        risk_reasons=[
            f"formats disk {disk!r} — immediate and destroys any pre-existing data on the disk; "
            "as irreversible as the delete",
        ],
        note=(
            f"No undo: creating the directory datastore FORMATS disk {disk!r} — pre-existing data "
            "is lost. Deleting the datastore (pbs_node_disk_directory_delete) does NOT restore it "
            "and does NOT wipe the disk either (PBS's directory-delete has no cleanup option)."
        ),
    )


def plan_disk_directory_delete(name: str, node: str = "localhost") -> Plan:
    """Plan for pbs_node_disk_directory_delete — remove a directory datastore's mount unit +
    config mapping. RISK_HIGH (mirrors node_lifecycle.py's plan_node_storage_backend_delete's
    directory-backend rating). Honestly discloses PBS's lack of a cleanup option (gap #5) — the
    underlying disk data persists, unmanaged, after this call."""
    name = _check_pbs_datastore_name(name)
    node = _check_pbs_node(node)
    return Plan(
        action="pbs_node_disk_directory_delete",
        target=f"pbs/node/{node}/disks/directory/{name}",
        change=f"remove directory datastore {name!r} on PBS node {node!r}; synchronous (no task)",
        current={},
        blast_radius=[
            f"directory datastore {name!r} on PBS node {node!r}: removes the mount unit and "
            "datastore config mapping — data on the underlying disk may persist but is unmanaged; "
            "PBS's own API exposes NO cleanup-disks option here (unlike PVE), so the disk is never "
            "wiped by this call",
        ],
        risk=RISK_HIGH,
        risk_reasons=[
            f"destroys the datastore mapping {name!r} irreversibly — any backups referencing this "
            "datastore lose their management path; the removal itself executes synchronously "
            "(DELETE returns null, not a task UPID, per PBS's own schema)",
        ],
        note=(
            f"No undo for the config mapping: DELETE /disks/directory/{name!r} is irreversible. "
            "Data on the underlying disk is NOT wiped (PBS provides no cleanup-disks flag on this "
            "endpoint) — it persists but unmanaged until reused."
        ),
    )


def plan_disk_zfs_create(
    devices: str,
    name: str,
    raidlevel: str,
    node: str = "localhost",
    ashift: int | None = None,
    compression: str | None = None,
    add_datastore: bool | None = None,
) -> Plan:
    """Plan for pbs_node_disk_zfs_create — create a zpool from 'devices' and mount it as a zfs
    datastore. RISK_HIGH (mirrors node_lifecycle.py's plan_node_storage_backend_create's uniform
    HIGH rating). Additionally discloses that PBS's own API has NO delete for the result (gap #3)
    — this creation has no in-API undo at all, not even a destructive one."""
    devices = _check_devices_csv(devices)
    name = _check_pbs_datastore_name(name)
    raidlevel = _check_raidlevel(raidlevel)
    node = _check_pbs_node(node)
    extra = [f"raidlevel={raidlevel!r}"]
    if ashift is not None:
        ashift = _check_ashift(ashift)
        extra.append(f"ashift={ashift}")
    if compression is not None:
        compression = _check_compression(compression)
        extra.append(f"compression={compression!r}")
    if add_datastore:
        extra.append("add-datastore=True")
    extra_note = f" ({', '.join(extra)})"
    return Plan(
        action="pbs_node_disk_zfs_create",
        target=f"pbs/node/{node}/disks/zfs/{name}",
        change=(
            f"create zfs datastore {name!r} on device(s) {devices!r} (PBS node {node!r})"
            f"{extra_note}"
        ),
        current={},
        blast_radius=[
            f"FORMATS device(s) {devices!r} into the new zpool/datastore {name!r} on PBS node "
            f"{node!r} — any pre-existing data on those disks is destroyed immediately and "
            f"irreversibly{extra_note}",
            "NO undo path exists in PBS's own API: there is no delete endpoint for a zpool "
            "created this way (module docstring gap #3) — recovery requires manual host-level "
            "intervention (zpool destroy outside this API)",
        ],
        risk=RISK_HIGH,
        risk_reasons=[
            f"formats device(s) {devices!r} into a zpool — immediate, destroys any pre-existing "
            "data, and PBS's API provides no way to destroy the resulting zpool afterward",
        ],
        note=(
            f"No undo: creating the zfs datastore FORMATS {devices!r}. Unlike the directory "
            "backend, PBS's API has NO delete for a zfs backend at all — plan carefully before "
            "confirming."
        ),
    )
