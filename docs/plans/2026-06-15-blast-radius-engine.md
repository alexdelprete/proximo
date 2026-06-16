# Blast-radius Engine Implementation Plan (v1: storage/disk class)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `Plan.blast_radius` *computed* for the storage/disk dangerous ops — naming the actual cluster-wide guests that lose disks if a storage is removed or disabled — surfaced as human strings plus a structured `affected: list[dict]`, flowing into the PROVE ledger.

**Architecture:** A pure `blast.py` engine (`compute_storage_blast` + helpers — no `api`, unit-testable) does the graph reasoning; `gather_storage_dependents(api, S)` does the safe reads and catches per-guest failures (→ `complete=False`, never raises). The existing `plan_storage_delete`/`plan_storage_update` factories take `api` (mirroring the house `plan_group_delete(api, …)` idiom), call `blast.storage_blast`, prepend the engine's lines, set `affected`, and maintain the `RISK_HIGH` floor / escalate on uncertainty.

**Tech Stack:** Python 3.12+, dataclasses, stdlib `re`. Proxmox reads via existing `cluster_resources` (`cluster_ops.py`) + `guest_config_get` (`config_edit.py`). Tests: pytest (run via `uv run python -m pytest`).

**Spec:** `docs/specs/2026-06-15-blast-radius-engine.md`. **Branch:** `feat/blast-radius-engine`.

**Commands (Proximo's own venv):**
- Tests: `uv run python -m pytest <path> -q`
- Lint: `uv run ruff check src tests`
- Types: `uv run pyright`

---

### Task 1: Add the `affected` field to `Plan`

**Files:**
- Modify: `src/proximo/planning.py:21` (import) and the `Plan` dataclass (`:44-69`)
- Test: `tests/test_planning.py` (append; create if absent)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_planning.py` (create the file with the import header if it does not exist):

```python
from proximo.planning import Plan


def test_plan_affected_defaults_empty_and_serializes():
    p = Plan(action="x", target="t", change="c", current={}, blast_radius=[],
             risk="high", risk_reasons=[])
    assert p.affected == []
    assert p.as_dict()["affected"] == []


def test_plan_affected_roundtrips_in_as_dict():
    entry = {"resource": "qemu/101", "severity": "high"}
    p = Plan(action="x", target="t", change="c", current={}, blast_radius=[],
             risk="high", risk_reasons=[], affected=[entry])
    assert p.as_dict()["affected"] == [entry]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_planning.py -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'affected'` (and/or KeyError on `"affected"`).

- [ ] **Step 3: Implement the field**

In `src/proximo/planning.py`, change the dataclass import (line 21):

```python
from dataclasses import dataclass, field
```

Add the field to `Plan` (after `note: str = ""`):

```python
    note: str = ""            # honesty disclaimer for heuristic classifications
    affected: list[dict] = field(default_factory=list)  # computed downstream impact (blast engine)
```

Add to `as_dict`'s returned dict (after the `"note"` entry):

```python
            "note": self.note,
            "affected": self.affected,
```

- [ ] **Step 4: Run test to verify it passes (and nothing else broke)**

Run: `uv run python -m pytest tests/test_planning.py -q && uv run python -m pytest -q`
Expected: PASS; full suite still **2126 passed** (adding a defaulted trailing field + key is non-breaking — no test asserts exact `as_dict()` equality).

- [ ] **Step 5: Commit**

```bash
git add src/proximo/planning.py tests/test_planning.py
git commit -m "feat(plan): add computed-impact 'affected' field to Plan (additive)"
```

---

### Task 2: `blast.py` — volid + disk-slot parsing (pure)

**Files:**
- Create: `src/proximo/blast.py`
- Test: `tests/test_blast.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_blast.py`:

```python
from proximo.blast import _disk_slots, _is_disk_key, _storage_of_volid


def test_storage_of_volid_extracts_storage():
    assert _storage_of_volid("nas:101/vm-101-disk-0.qcow2,size=32G") == "nas"
    assert _storage_of_volid("local-lvm:vm-101-disk-0,size=8G") == "local-lvm"


def test_storage_of_volid_none_for_non_volumes():
    assert _storage_of_volid("none") is None          # cdrom-empty / no media
    assert _storage_of_volid("/dev/disk/by-id/x") is None  # raw passthrough path
    assert _storage_of_volid("") is None


def test_is_disk_key():
    for k in ("rootfs", "scsi0", "virtio15", "sata1", "ide2", "mp0", "unused3",
              "efidisk0", "tpmstate0"):
        assert _is_disk_key(k), k
    for k in ("net0", "name", "boot", "memory", "cores", "scsihw", "ostype"):
        assert not _is_disk_key(k), k


def test_disk_slots_maps_data_disks_to_storage():
    cfg = {"scsi0": "local-lvm:vm-1-disk-0,size=8G",
           "scsi1": "nas:1/vm-1-disk-1.qcow2,size=50G",
           "net0": "virtio=AA:BB,bridge=vmbr0",
           "cores": "2"}
    assert _disk_slots(cfg) == {"scsi0": "local-lvm", "scsi1": "nas"}


def test_disk_slots_excludes_cdrom_media():
    cfg = {"ide2": "nas:iso/debian.iso,media=cdrom",
           "scsi0": "nas:1/vm-1-disk-0.qcow2,size=8G"}
    assert _disk_slots(cfg) == {"scsi0": "nas"}        # cdrom mount is not guest data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_blast.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'proximo.blast'`.

- [ ] **Step 3: Create `src/proximo/blast.py` with the parsing layer**

```python
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

import re
from dataclasses import dataclass

from .cluster_ops import cluster_resources
from .config_edit import guest_config_get

# Config keys that hold a guest *data* volume. `netN` (NICs) and non-disk keys are excluded.
_DISK_KEY_RE = re.compile(r"^(?:rootfs|(?:efidisk|tpmstate|scsi|sata|ide|virtio|mp|unused)\d+)$")


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_blast.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/proximo/blast.py tests/test_blast.py
git commit -m "feat(blast): volid + data-disk-slot parsing (pure)"
```

---

### Task 3: `blast.py` — boot-slot detection + per-guest classification

**Files:**
- Modify: `src/proximo/blast.py`
- Test: `tests/test_blast.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_blast.py`:

```python
from proximo.blast import BlastEntry, _boot_slot, _classify_guest


def test_boot_slot_lxc_is_rootfs():
    assert _boot_slot({"rootfs": "nas:subvol-1-disk-0,size=8G"}, "lxc") == "rootfs"
    assert _boot_slot({}, "lxc") is None


def test_boot_slot_qemu_prefers_bootdisk_then_order():
    assert _boot_slot({"bootdisk": "scsi0", "boot": "order=ide2;scsi0"}, "qemu") == "scsi0"
    assert _boot_slot({"boot": "order=scsi0;net0"}, "qemu") == "scsi0"
    assert _boot_slot({"boot": "order=net0;ide2"}, "qemu") == "ide2"  # first DISK in order
    assert _boot_slot({"cores": "2"}, "qemu") is None                 # not determinable


def _guest(vmid="101", kind="qemu", node="pve1", name="web", status="running"):
    return {"vmid": vmid, "type": kind, "node": node, "name": name, "status": status}


def test_classify_only_copy_wont_boot_high():
    cfg = {"scsi0": "nas:101/vm-101-disk-0.qcow2,size=32G", "bootdisk": "scsi0"}
    e = _classify_guest("nas", _guest(), cfg)
    assert e.severity == "high" and e.only_copy is True and e.via == ["scsi0"]
    assert "will NOT boot" in e.effect and "RUNNING" in e.effect


def test_classify_degraded_when_boot_disk_elsewhere_medium():
    cfg = {"scsi0": "local-lvm:vm-101-disk-0,size=8G",   # boot disk, NOT on nas
           "scsi1": "nas:101/vm-101-disk-1.qcow2,size=50G",  # data disk on nas
           "bootdisk": "scsi0"}
    e = _classify_guest("nas", _guest(status="stopped"), cfg)
    assert e.severity == "medium" and e.only_copy is False and e.via == ["scsi1"]
    assert "degraded" in e.effect and "RUNNING" not in e.effect


def test_classify_not_affected_returns_none():
    cfg = {"scsi0": "local-lvm:vm-101-disk-0,size=8G", "bootdisk": "scsi0"}
    assert _classify_guest("nas", _guest(), cfg) is None


def test_classify_lxc_rootfs_on_target_wont_boot():
    cfg = {"rootfs": "nas:subvol-200-disk-0,size=8G"}
    e = _classify_guest("nas", _guest(vmid="200", kind="lxc"), cfg)
    assert e.severity == "high" and e.resource == "lxc/200"


def test_classify_unknown_boot_not_only_copy_is_degraded_with_note():
    cfg = {"scsi0": "local-lvm:vm-1-disk-0,size=8G",     # some disk elsewhere
           "scsi1": "nas:1/vm-1-disk-1.qcow2,size=9G"}   # data on nas; NO bootdisk/boot line
    e = _classify_guest("nas", _guest(status="stopped"), cfg)
    assert e.severity == "medium"
    assert "boot order not determinable" in e.effect
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_blast.py -q`
Expected: FAIL — `ImportError: cannot import name 'BlastEntry'` / `_boot_slot` / `_classify_guest`.

- [ ] **Step 3: Add the dataclass, boot detection, and classifier to `src/proximo/blast.py`**

Insert after `_disk_slots`:

```python
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
    wont_boot = only_copy or boot_on_s

    if only_copy:
        effect = f"will NOT boot — all data disks ({', '.join(on_s)}) are on this storage"
    elif boot_on_s:
        effect = f"will NOT boot — boot disk {boot} is on this storage"
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_blast.py -q`
Expected: PASS (all Task 2 + Task 3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/proximo/blast.py tests/test_blast.py
git commit -m "feat(blast): boot-slot detection + per-guest loss classification (pure)"
```

---

### Task 4: `blast.py` — `compute_storage_blast` aggregator + INCOMPLETE contract

**Files:**
- Modify: `src/proximo/blast.py`
- Test: `tests/test_blast.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_blast.py`:

```python
from proximo.blast import BlastResult, compute_storage_blast


def _cfg_on(storage, slot="scsi0", bootdisk="scsi0"):
    return {slot: f"{storage}:1/vm-1-disk-0.qcow2,size=8G", "bootdisk": bootdisk}


def test_compute_sorts_high_before_medium_then_vmid():
    guests = [_guest(vmid="105"), _guest(vmid="102"), _guest(vmid="200", kind="lxc")]
    configs = {
        "105": {"scsi0": "local-lvm:vm-105-disk-0,size=8G",          # boot elsewhere
                "scsi1": "nas:105/vm-105-disk-1.qcow2,size=9G", "bootdisk": "scsi0"},  # medium
        "102": _cfg_on("nas"),                                        # high (only copy)
        "200": {"rootfs": "nas:subvol-200-disk-0,size=8G"},           # high (lxc rootfs)
    }
    r = compute_storage_blast("nas", guests, configs, complete=True)
    assert [e.resource for e in r.affected] == ["lxc/200", "qemu/102", "qemu/105"]
    assert r.max_severity == "high" and r.complete is True
    assert any("ENUMERATED 3 guest" in line for line in r.summary_lines)


def test_compute_empty_complete_says_none_found_but_not_safe():
    guests = [_guest(vmid="102")]
    configs = {"102": {"scsi0": "local-lvm:vm-102-disk-0,size=8G", "bootdisk": "scsi0"}}
    r = compute_storage_blast("nas", guests, configs, complete=True)
    assert r.affected == [] and r.max_severity == "none"
    assert any("no guest config references storage 'nas'" in line for line in r.summary_lines)
    assert any("not proof" in line for line in r.summary_lines)


def test_compute_incomplete_is_loud_forces_high_and_adds_sentinel():
    guests = [_guest(vmid="102"), _guest(vmid="103")]
    configs = {"102": _cfg_on("nas"), "103": None}      # 103 config read failed
    r = compute_storage_blast("nas", guests, configs, complete=False)
    assert r.complete is False and r.max_severity == "high"
    assert r.summary_lines[0].startswith("⚠ INCOMPLETE")
    assert "1 of 2" in r.summary_lines[0]
    assert any(e.severity == "unknown" for e in r.affected)   # sentinel present
    assert r.affected_dicts()[-1]["severity"] == "unknown"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_blast.py -q`
Expected: FAIL — `ImportError: cannot import name 'compute_storage_blast'` / `BlastResult`.

- [ ] **Step 3: Add the aggregator to `src/proximo/blast.py`**

Insert after `_classify_guest`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_blast.py -q`
Expected: PASS (all blast unit tests).

- [ ] **Step 5: Commit**

```bash
git add src/proximo/blast.py tests/test_blast.py
git commit -m "feat(blast): compute_storage_blast aggregator + fail-closed INCOMPLETE contract"
```

---

### Task 5: `blast.py` — `gather_storage_dependents` + `storage_blast` (I/O, failure-catching)

**Files:**
- Modify: `src/proximo/blast.py`
- Test: `tests/test_blast.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_blast.py`:

```python
from types import SimpleNamespace

from proximo.blast import gather_storage_dependents, storage_blast


def _fake_api(rows, configs, *, fail_resources=False, fail_config_for=()):
    cfg = SimpleNamespace(node="pve1")

    def _get(path):
        if path == "/cluster/resources":
            if fail_resources:
                raise RuntimeError("cluster unreachable")
            return rows
        if path.endswith("/config"):
            vmid = path.strip("/").split("/")[3]   # /nodes/<node>/<kind>/<vmid>/config
            if vmid in fail_config_for:
                raise RuntimeError("node down")
            return configs[vmid]
        raise AssertionError(f"unexpected GET {path}")

    return SimpleNamespace(_get=_get, config=cfg)


def test_gather_filters_to_guests_and_reads_each_config():
    rows = [{"vmid": "101", "type": "qemu", "node": "pve1", "name": "a", "status": "running"},
            {"vmid": "200", "type": "lxc", "node": "pve2", "name": "b", "status": "stopped"},
            {"type": "storage", "node": "pve1"},          # filtered out
            {"type": "node", "node": "pve1"}]             # filtered out
    configs = {"101": {"scsi0": "nas:101/d.qcow2,size=8G"},
               "200": {"rootfs": "local-lvm:subvol-200,size=8G"}}
    api = _fake_api(rows, configs)
    guests, got, complete = gather_storage_dependents(api, "nas")
    assert complete is True
    assert {g["vmid"] for g in guests} == {"101", "200"}
    assert got["101"]["scsi0"].startswith("nas:")


def test_gather_total_failure_is_incomplete_not_raise():
    api = _fake_api([], {}, fail_resources=True)
    guests, got, complete = gather_storage_dependents(api, "nas")
    assert guests == [] and got == {} and complete is False


def test_gather_per_guest_config_failure_marks_incomplete():
    rows = [{"vmid": "101", "type": "qemu", "node": "pve1", "name": "a", "status": "running"}]
    api = _fake_api(rows, {}, fail_config_for=("101",))
    guests, got, complete = gather_storage_dependents(api, "nas")
    assert complete is False and got["101"] is None and len(guests) == 1


def test_storage_blast_end_to_end_pure_plus_io():
    rows = [{"vmid": "101", "type": "qemu", "node": "pve1", "name": "web", "status": "running"}]
    configs = {"101": {"scsi0": "nas:101/d.qcow2,size=8G", "bootdisk": "scsi0"}}
    r = storage_blast(_fake_api(rows, configs), "nas")
    assert r.complete is True and r.max_severity == "high"
    assert r.affected[0].resource == "qemu/101"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_blast.py -q`
Expected: FAIL — `ImportError: cannot import name 'gather_storage_dependents'` / `storage_blast`.

- [ ] **Step 3: Add the I/O layer to `src/proximo/blast.py`**

Append at the end of the module:

```python
def gather_storage_dependents(api, storage: str) -> tuple[list[dict], dict, bool]:
    """I/O: enumerate ALL guests cluster-wide + read each config. Returns (guests, configs, complete).
    A total cluster_resources failure -> ([], {}, False); a per-guest config failure ->
    configs[vmid]=None + complete=False. NEVER raises — the plan must always build."""
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
            configs[vmid] = guest_config_get(api, vmid, g.get("type"), g.get("node"))
        except Exception:
            configs[vmid] = None
            complete = False
    return guests, configs, complete


def storage_blast(api, storage: str) -> BlastResult:
    """Convenience: gather live cluster state then compute the pure blast result."""
    guests, configs, complete = gather_storage_dependents(api, storage)
    return compute_storage_blast(storage, guests, configs, complete)
```

> Note: `storage` is unused inside `gather_storage_dependents` (it enumerates all guests; the
> filtering-by-storage happens in `compute_storage_blast`). Keep the param for a symmetric,
> future-proof signature — silence ruff with the leading-underscore convention ONLY if ruff flags
> it; `gather_storage_dependents` does not currently trip `F841`/`ARG` under the project's selected
> rules (`E,F,I,UP,B,S`), so leave the name as-is for readability. Verify in Step 4's ruff run.

- [ ] **Step 4: Run tests + lint to verify**

Run: `uv run python -m pytest tests/test_blast.py -q && uv run ruff check src/proximo/blast.py`
Expected: tests PASS; ruff clean. (If ruff flags `storage` as unused — it should not under the
selected rule set — rename to `_storage` in the signature.)

- [ ] **Step 5: Commit**

```bash
git add src/proximo/blast.py tests/test_blast.py
git commit -m "feat(blast): live enumeration (gather_storage_dependents) + storage_blast convenience"
```

---

### Task 6: Enrich `plan_storage_delete(api, storage)`

**Files:**
- Modify: `src/proximo/storage_admin.py` (import block `:24`; `plan_storage_delete` `:403-445`)
- Test: `tests/test_storage_admin.py`

- [ ] **Step 1: Update the existing pure-signature tests to the new `api`-taking signature, and add an enrichment test**

In `tests/test_storage_admin.py`, find every call to `plan_storage_delete(<storage>)` and change it to
`plan_storage_delete(_blast_api([]), <storage>)` (an api whose cluster has no guests — keeps the
existing generic-floor assertions valid). Add this helper near the top fake section and a new test:

```python
def _blast_api(rows, configs=None):
    """Path-aware fake for blast enumeration: /cluster/resources -> rows; /config -> configs[vmid]."""
    from types import SimpleNamespace
    configs = configs or {}

    def _get(path):
        if path == "/cluster/resources":
            return rows
        if path.endswith("/config"):
            return configs[path.strip("/").split("/")[3]]
        return None

    return SimpleNamespace(_get=_get, config=SimpleNamespace(node="pve"))


def test_plan_storage_delete_names_affected_guests_and_keeps_high():
    rows = [{"vmid": "101", "type": "qemu", "node": "pve1", "name": "web", "status": "running"}]
    configs = {"101": {"scsi0": "nas:101/d.qcow2,size=8G", "bootdisk": "scsi0"}}
    plan = plan_storage_delete(_blast_api(rows, configs), "nas")
    assert plan.risk == RISK_HIGH                          # floor maintained
    assert any("qemu/101" in line for line in plan.blast_radius)
    assert plan.affected and plan.affected[0]["resource"] == "qemu/101"
    # generic floor still present (engine PREPENDS, never replaces)
    assert any("does NOT erase on-disk data" in line for line in plan.blast_radius)
```

- [ ] **Step 2: Run to verify the new test fails (and old ones error on arity)**

Run: `uv run python -m pytest tests/test_storage_admin.py -q`
Expected: FAIL — `plan_storage_delete()` arity error on the updated calls / new test fails.

- [ ] **Step 3: Update `plan_storage_delete` in `src/proximo/storage_admin.py`**

Change the import line (`:24`) to add the blast module and `_max_risk` is not needed here:

```python
from . import blast
from .backends import ProximoError
from .planning import RISK_HIGH, RISK_MEDIUM, Plan
from .storage import _check_storage  # reuse: same regex/rule, no duplication
```

Replace the `plan_storage_delete` function body (keep its docstring) so it takes `api`, calls the
engine, and PREPENDS the engine lines to the existing generic floor:

```python
def plan_storage_delete(api, storage: str) -> Plan:
    """Preview deleting a storage definition.  Reads the cluster to NAME affected guests.

    RISK_HIGH (floor, never lowered): removes the storage DEFINITION cluster-wide. Any guest disk
    or backup living ONLY on this storage becomes inaccessible to PVE. No automatic undo.
    """
    _check_storage(storage)
    result = blast.storage_blast(api, storage)
    generic_floor = [
        f"removes storage definition '{storage}' from storage.cfg cluster-wide — "
        "PVE immediately loses the handle to this storage on ALL nodes",
        "any guest disk (VM image, container rootfs) living ONLY on this storage "
        "becomes inaccessible to PVE — the guest will fail to start or may crash if running",
        "backups stored on this storage are no longer listable or restorable through PVE",
        "does NOT erase on-disk data — the data remains on the underlying disk/share/pool, "
        "but PVE has no handle to reach it",
        "NO automatic undo — to recover access, re-add the storage definition "
        "with the same type and configuration",
    ]
    return Plan(
        action="pve_storage_delete",
        target=f"storage/{storage}",
        change=f"remove storage definition '{storage}' from storage.cfg cluster-wide",
        current={},
        blast_radius=result.summary_lines + generic_floor,
        affected=result.affected_dicts(),
        risk=RISK_HIGH,
        risk_reasons=[
            "removes the storage definition cluster-wide — all nodes lose access simultaneously",
            "guest disks and backups living only on this storage become inaccessible to PVE",
            "backups are no longer listable or restorable through PVE once the definition is gone",
            "no automatic undo: re-adding the definition manually is the only recovery path",
        ],
        note=(
            "Smoke-confirm: verify DELETE /storage/{storage} is synchronous (returns null, "
            "not a UPID). Verify the cluster-wide propagation timing (pmxcfs should replicate "
            "the removal to all nodes, but confirm the replication is immediate vs. eventual)."
        ),
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run python -m pytest tests/test_storage_admin.py -q`
Expected: PASS. (If the server lambda is now mis-arity'd, that's fixed in Task 8 — run only this file here.)

- [ ] **Step 5: Commit**

```bash
git add src/proximo/storage_admin.py tests/test_storage_admin.py
git commit -m "feat(storage): plan_storage_delete names affected guests via blast engine"
```

---

### Task 7: Enrich `plan_storage_update(api, storage, …)` (disable case) + risk escalation

**Files:**
- Modify: `src/proximo/storage_admin.py` (import block; `plan_storage_update` `:320-400`)
- Test: `tests/test_storage_admin.py`

- [ ] **Step 1: Update existing calls + add escalation tests**

In `tests/test_storage_admin.py`, change every `plan_storage_update(<storage>, ...)` call to
`plan_storage_update(_blast_api([]), <storage>, ...)`. Add:

```python
def test_plan_storage_update_disable_escalates_to_high_when_only_copy_running():
    rows = [{"vmid": "101", "type": "qemu", "node": "pve1", "name": "db", "status": "running"}]
    configs = {"101": {"scsi0": "nas:101/d.qcow2,size=8G", "bootdisk": "scsi0"}}
    plan = plan_storage_update(_blast_api(rows, configs), "nas", disable=True)
    assert plan.risk == RISK_HIGH                          # escalated from MEDIUM
    assert plan.affected and plan.affected[0]["resource"] == "qemu/101"


def test_plan_storage_update_non_disable_does_not_enumerate():
    plan = plan_storage_update(_blast_api([]), "nas", content="images,iso")
    assert plan.risk == RISK_MEDIUM and plan.affected == []
    assert any("update storage definition 'nas'" in line for line in plan.blast_radius)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/test_storage_admin.py -q`
Expected: FAIL — arity error on updated calls / new tests fail.

- [ ] **Step 3: Update imports + `plan_storage_update` in `src/proximo/storage_admin.py`**

Add `_max_risk` to the planning import:

```python
from .planning import RISK_HIGH, RISK_MEDIUM, Plan, _max_risk
```

Replace the tail of `plan_storage_update` (from `blast = [...]` construction through the `return Plan(...)`)
so it enriches only when `disable is True`. Keep the existing `changes`/`change_summary` building and
the existing conditional warning strings; rename the local `blast` list to `base_blast` to avoid
shadowing the imported `blast` module:

```python
    base_blast = [
        f"updates storage definition '{storage}' in storage.cfg cluster-wide",
        f"changes: {change_summary}",
    ]

    if disable is True:
        base_blast.append(
            "WARNING: disable=True — ALL guests with volumes on this storage WILL LOSE ACCESS "
            "to their disks; running VMs/containers may crash or corrupt state; "
            "re-enabling restores access to the storage, but guests that lost their disk "
            "may have crashed and need a restart — config reversal does not equal guest recovery"
        )

    if nodes is not None:
        base_blast.append(
            f"changing 'nodes' to [{nodes}] — guests on excluded nodes lose access to "
            "their disks on this storage"
        )

    base_blast.append(
        "to undo: apply the inverse update (restore previous content/nodes/disable/shared values)"
    )

    # Enrich the DISABLE case with the cluster-wide affected set (same primitive as delete).
    # disable cuts EVERY guest with a volume on S off from its disk -> compute + escalate.
    summary_lines: list[str] = []
    affected: list[dict] = []
    risk = RISK_MEDIUM
    if disable is True:
        result = blast.storage_blast(api, storage)
        summary_lines = result.summary_lines
        affected = result.affected_dicts()
        if result.max_severity == "high":
            risk = _max_risk(RISK_MEDIUM, RISK_HIGH)        # raise on uncertainty/only-copy; never lower

    return Plan(
        action="pve_storage_update",
        target=f"storage/{storage}",
        change=f"update storage '{storage}': {change_summary}",
        current={},
        blast_radius=summary_lines + base_blast,
        affected=affected,
        risk=risk,
        risk_reasons=[
            "changing nodes or disabling storage can cut running guests off from their disks",
            "disabling storage / changing nodes can cut running guests off from their disks "
            "(see blast radius); not automatically reversible",
        ],
        note=(
            "Smoke-confirm: verify 'delete' param semantics (comma-sep field names to unset); "
            "verify which fields can be unset vs. which are required and cannot be deleted; "
            "verify bool fields are sent as 1/0 integers. "
            "content, nodes, and delete are operator-trusted strings — "
            "Proximo does not deep-validate them; PVE validates server-side."
        ),
    )
```

Also update the `plan_storage_update` signature line to take `api` first:

```python
def plan_storage_update(
    api,
    storage: str,
    content: str | None = None,
    nodes: str | None = None,
    disable: bool | None = None,
    shared: bool | None = None,
    delete: str | None = None,
) -> Plan:
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run python -m pytest tests/test_storage_admin.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/proximo/storage_admin.py tests/test_storage_admin.py
git commit -m "feat(storage): plan_storage_update(disable) enriches + escalates risk via blast engine"
```

---

### Task 8: Wire `api` into the server build lambdas + record `affected` in the ledger

**Files:**
- Modify: `src/proximo/server.py` (`_record_plan` `:374-382`; `pve_storage_update` `:2304-2305`; `pve_storage_delete` `:2319`)

- [ ] **Step 1: Write the failing test (server seam, mirrors test_server_round3_wiring)**

Create `tests/test_blast_seam.py`:

```python
"""Server-seam integration for the blast engine — storage_delete/update PLAN through the real
tool path. Backends faked (path-aware), ledger real (tmp_path). Mirrors test_server_round3_wiring."""

from __future__ import annotations

import json
from types import SimpleNamespace

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig


class _FakeApi:
    def __init__(self, rows, configs, fail_config_for=()):
        self.config = SimpleNamespace(node="pve1")
        self._rows = rows
        self._configs = configs
        self._fail = set(fail_config_for)

    def _get(self, path):
        if path == "/cluster/resources":
            return self._rows
        if path.endswith("/config"):
            vmid = path.strip("/").split("/")[3]
            if vmid in self._fail:
                raise RuntimeError("node down")
            return self._configs[vmid]
        return []

    def _delete(self, path, params=None):
        return None

    def _put(self, path, data=None):
        return None


def _wire(tmp_path, monkeypatch, api):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(api_base_url="https://x:8006/api2/json", node="pve1",
                        token_path="/run/x", audit_log_path=log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, SimpleNamespace(), AuditLedger(log)))
    return log


def _entries(log):
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


_ROWS = [{"vmid": "101", "type": "qemu", "node": "pve1", "name": "web", "status": "running"}]
_CONFIGS = {"101": {"scsi0": "nas:101/d.qcow2,size=8G", "bootdisk": "scsi0"}}


def test_delete_plan_names_affected_and_ledger_records_it(tmp_path, monkeypatch):
    log = _wire(tmp_path, monkeypatch, _FakeApi(_ROWS, _CONFIGS))
    resp = server.pve_storage_delete("nas")               # dry-run (confirm defaults False)
    assert resp["status"] == "plan" and resp["risk"] == "high"
    assert resp["affected"][0]["resource"] == "qemu/101"  # as_dict carries affected (A2A path too)
    assert any("qemu/101" in line for line in resp["blast_radius"])
    planned = [e for e in _entries(log) if e.get("outcome") == "planned"]
    assert planned and planned[-1]["detail"]["affected"][0]["resource"] == "qemu/101"


def test_delete_plan_fail_closed_on_unreadable_guest(tmp_path, monkeypatch):
    log = _wire(tmp_path, monkeypatch, _FakeApi(_ROWS, _CONFIGS, fail_config_for=("101",)))
    resp = server.pve_storage_delete("nas")
    assert resp["risk"] == "high"                         # never lowered
    assert resp["blast_radius"][0].startswith("⚠ INCOMPLETE")
    assert any(a["severity"] == "unknown" for a in resp["affected"])


def test_update_disable_plan_escalates_to_high(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch, _FakeApi(_ROWS, _CONFIGS))
    resp = server.pve_storage_update("nas", disable=True)
    assert resp["status"] == "plan" and resp["risk"] == "high"
    assert resp["affected"][0]["resource"] == "qemu/101"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m pytest tests/test_blast_seam.py -q`
Expected: FAIL — `pve_storage_delete` still calls `plan_storage_delete(storage)` (arity error: missing `api`).

- [ ] **Step 3: Update `src/proximo/server.py`**

In `_record_plan` (around `:380-381`), add `affected` to the ledger detail:

```python
        detail={"change": plan.change, "risk": plan.risk, "risk_reasons": plan.risk_reasons,
                "blast_radius": plan.blast_radius, "current": plan.current,
                "affected": plan.affected},
```

In `pve_storage_update` (`:2304-2305`), pass `api`:

```python
    plan = _plan("pve_storage_update", tgt,
                 lambda: plan_storage_update(api, storage, content, nodes, disable, shared, delete))
```

In `pve_storage_delete` (`:2319`), pass `api`:

```python
    plan = _plan("pve_storage_delete", tgt, lambda: plan_storage_delete(api, storage))
```

- [ ] **Step 4: Run to verify it passes + full suite green**

Run: `uv run python -m pytest tests/test_blast_seam.py -q && uv run python -m pytest -q`
Expected: seam tests PASS; full suite green (2126 baseline + new blast/seam/planning tests, ~2150+). No import cycle (blast ← cluster_ops/config_edit; neither imports blast/storage_admin).

- [ ] **Step 5: Commit**

```bash
git add src/proximo/server.py tests/test_blast_seam.py
git commit -m "feat(server): wire api into storage plan lambdas; record affected-set in PROVE ledger"
```

---

### Task 9: Lint, types, and full-suite gate

**Files:** none (verification task)

- [ ] **Step 1: Ruff**

Run: `uv run ruff check src tests`
Expected: clean. Fix any findings (likely import-order `I` or unused — none expected). If `gather_storage_dependents`'s `storage` param trips a rule, rename to `_storage` and re-run.

- [ ] **Step 2: Pyright (src-scoped)**

Run: `uv run pyright`
Expected: 0 errors (config scopes to `src/`). If `_max_risk` import triggers a private-use note, it's an internal sibling import — acceptable (same pattern as planning's own use); ensure no real type errors.

- [ ] **Step 3: Full suite**

Run: `uv run python -m pytest -q`
Expected: all green, 0 unexpected skips.

- [ ] **Step 4: Commit (only if fixes were needed)**

```bash
git add -A
git commit -m "chore(blast): ruff + pyright clean"
```

---

### Task 10: CHANGELOG + read-only live-smoke + adversarial redteam

**Files:**
- Modify: `CHANGELOG.md`
- Create: `scripts/live-smoke/blast-smoke.py`

- [ ] **Step 1: CHANGELOG entry (do NOT bump the version — release is the maintainer's intentional call)**

Add under a new `## [Unreleased]` section at the top of `CHANGELOG.md`:

```markdown
## [Unreleased]
### Added
- **Computed blast-radius (storage/disk class).** `pve_storage_delete` and `pve_storage_update`
  (disable) now read the cluster at PLAN time and NAME the actual guests that lose disks —
  cluster-wide, distinguishing "will not boot" (boot disk / only copy on the storage) from
  "degraded". Surfaced as `blast_radius` strings and a new structured `affected: list[dict]`
  field (additive, non-breaking), recorded to the PROVE ledger. Fail-closed: incomplete
  enumeration renders a loud INCOMPLETE marker and never lowers risk. New pure engine
  `proximo.blast`. (Spec: `docs/specs/2026-06-15-blast-radius-engine.md`.)
```

- [ ] **Step 2: Read-only live-smoke script**

Create `scripts/live-smoke/blast-smoke.py` (PLAN-only — NEVER calls confirm=True; safe on a real node):

```python
#!/usr/bin/env python3
"""Read-only blast-radius smoke: PLAN a storage delete against a live PVE and print the computed
affected set. NEVER mutates (no confirm). Env: PROXIMO_* (see scripts/live-smoke/README).
Usage: PROXIMO_STORAGE=local-lvm uv run python scripts/live-smoke/blast-smoke.py"""
import json
import os
import sys

from proximo.blast import storage_blast
from proximo.server import _svc


def main() -> int:
    storage = os.environ.get("PROXIMO_STORAGE")
    if not storage:
        print("set PROXIMO_STORAGE=<existing storage id> (read-only; no mutation)", file=sys.stderr)
        return 2
    _, api, _, _ = _svc()
    result = storage_blast(api, storage)
    print(f"storage={storage} complete={result.complete} max_severity={result.max_severity}")
    for line in result.summary_lines:
        print(line)
    print(json.dumps(result.affected_dicts(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md scripts/live-smoke/blast-smoke.py
git commit -m "docs+smoke(blast): CHANGELOG [Unreleased] + read-only live-smoke for blast-radius"
```

- [ ] **Step 4: Adversarial redteam (independent pass before "done")**

Dispatch an independent review (Sonnet, 3 lenses) over the `feat/blast-radius-engine` diff:
- **correctness/under-flag:** can the engine EVER report a *falsely small* or empty blast-radius for a guest that truly loses a disk? (volid forms, multi-disk, snapshots/linked-clones, `unusedN`, exotic storage types, `type=vm` vs the no-filter enumeration). Under-flagging is the cardinal sin.
- **honesty/fail-closed:** does any read path swallow an error into a silent "complete"? Is `max_severity` ever lowered? Does INCOMPLETE always surface first?
- **leak:** no real infra names / IPs / secrets in new files (fixtures use `nas`/`pve1`/`local-lvm` generics).

Apply confirmed findings test-first; re-run Task 9's gate. Record the verdict in the PR/handoff.

---

## Self-Review (run after writing — checklist, not a subagent)

**Spec coverage:**
- Pure engine `blast.py` → Tasks 2–5 ✅
- `affected` structured field + strings → Task 1 (field) + Tasks 6–8 (populated) ✅
- Cluster-wide enumeration (no undercount) → Task 5 (`cluster_resources` no-filter → qemu/lxc) ✅
- Fail-closed INCOMPLETE / never-lower-risk / forces-high → Task 4 + seam test Task 8 ✅
- Total-death vs degraded, running note → Task 3 ✅
- Honest VM boot detection + conservative fallback → Task 3 ✅
- `plan_*(api)` house idiom (delete + update-disable) → Tasks 6–7 ✅
- Ledger weld carries `affected` → Task 8 ✅
- A2A `as_dict` carries `affected` → Task 8 seam test (`resp["affected"]` via same as_dict) ✅
- nodes-restrict / guest-destroy / disk-move deferred → not in any task (correct) ✅
- Lint/types/suite gate → Task 9 ✅; redteam → Task 10 ✅

**Placeholder scan:** No TBD/TODO; every code step has complete code. ✅

**Type consistency:** `BlastEntry`/`BlastResult` fields, `compute_storage_blast(storage, guests, configs, complete)`, `gather_storage_dependents(api, storage) -> (guests, configs, complete)`, `storage_blast(api, storage)`, `result.summary_lines`/`affected_dicts()`/`max_severity`/`complete`, `Plan.affected` — all names consistent across Tasks 1–10 and match the spec. ✅
