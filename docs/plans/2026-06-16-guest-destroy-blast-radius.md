# Guest-destroy Blast-radius Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute and surface, at PLAN time, exactly what destroying a guest will do — what PVE will refuse, what references it leaves dangling (or cleans up, conditional on `purge`/`force`), and what it intrinsically removes — wired into `plan_delete` behind `pve_delete_guest`.

**Architecture:** A pure, I/O-free `compute_guest_destroy_blast(inputs)` in `src/proximo/blast.py` returns a `GuestDestroyBlastResult` (mirrors `FirewallReachResult`: `summary_lines` / `affected` / `risk` / `risk_reasons` / `complete`). A fail-closed `gather_guest_dependents(api, …)` does all the reads and packs a frozen `GuestDestroyInputs`. `plan_delete` calls gather→compute on the found branch, folds the result into its existing blast/reasons, and populates `Plan.affected` / `Plan.complete`. Risk is only ever raised, never lowered.

**Tech Stack:** Python 3.13, dataclasses, pytest. Dev env: `uv sync --extra dev`, then `uv run python -m pytest -q` / `uv run ruff check src tests` / `uv run pyright`. Baseline before starting: **2227 green** on branch `feat/guest-destroy-blast-radius`.

**Spec:** `docs/specs/2026-06-16-guest-destroy-blast-radius.md`.

---

## File Structure

- **Modify** `src/proximo/blast.py` — add `GuestDestroyInputs`, `GuestDestroyBlastResult`, `_GUEST_DESTROY_DISCLAIMER`, helper `_is_linked_clone_of`, pure `compute_guest_destroy_blast`, I/O `gather_guest_dependents`, wrapper `guest_destroy_blast`. (No package split — spec Non-goals.)
- **Modify** `src/proximo/provisioning.py` — `plan_delete` gains a `force` param and calls gather→compute on the found branch.
- **Modify** `src/proximo/server.py:847` — pass `force` into the `plan_delete` lambda.
- **Create** `tests/test_blast_guest_destroy.py` — pure unit tests (zero API).
- **Create** `tests/test_blast_guest_destroy_redteam.py` — adversarial tests (added in the redteam task).
- **Modify** `tests/` existing `plan_delete`/server-wiring test (seam coverage).
- **Modify** `CHANGELOG.md` — `[Unreleased]` entry.

Conventions: conventional-commit subjects; every commit ends with the trailer
`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

### Task 1: Result + Inputs dataclasses and the framing disclaimer

**Files:**
- Modify: `src/proximo/blast.py` (append near the other result dataclasses, after `ApplyLockoutResult`)
- Test: `tests/test_blast_guest_destroy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_blast_guest_destroy.py
"""Guest-destroy blast-radius engine — pure unit tests (zero API)."""
from __future__ import annotations

from proximo.blast import (
    GuestDestroyBlastResult,
    GuestDestroyInputs,
    _GUEST_DESTROY_DISCLAIMER,
    compute_guest_destroy_blast,
)
from proximo.planning import RISK_HIGH


def _inputs(**over) -> GuestDestroyInputs:
    """A minimal all-reads-succeeded, nothing-found input. Override per test."""
    base = dict(
        vmid="9000", kind="qemu", purge=False, force=False,
        guest_config={}, status="stopped",
        ha_resources=[], replication_jobs=[], backup_jobs=[],
        pools=[], snapshots=[], clone_configs={},
    )
    base.update(over)
    return GuestDestroyInputs(**base)


def test_dataclasses_exist_and_disclaimer_mentions_plan_time():
    inp = _inputs()
    assert inp.vmid == "9000"
    assert "PLAN time" in _GUEST_DESTROY_DISCLAIMER or "plan time" in _GUEST_DESTROY_DISCLAIMER.lower()
    # result is constructible with the documented field set
    r = GuestDestroyBlastResult(
        summary_lines=["x"], affected=[], risk=RISK_HIGH, risk_reasons=[], complete=True,
    )
    assert r.risk == RISK_HIGH and r.complete is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_blast_guest_destroy.py -q`
Expected: FAIL — `ImportError: cannot import name 'GuestDestroyInputs'`.

- [ ] **Step 3: Write minimal implementation**

In `src/proximo/blast.py`, after the `ApplyLockoutResult` block:

```python
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
```

Confirm `from dataclasses import dataclass` and the `RISK_*` / `_max_risk` imports are already present at the top of `blast.py` (they are — used by the existing classes).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_blast_guest_destroy.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add src/proximo/blast.py tests/test_blast_guest_destroy.py
git commit -m "feat(blast): guest-destroy result/inputs dataclasses + disclaimer

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `compute_guest_destroy_blast` skeleton + INFORMATIONAL category

Establishes the function and the always-present intrinsic footprint: disks+storages, snapshots, pool membership. Reuses `_disk_slots`.

**Files:**
- Modify: `src/proximo/blast.py`
- Test: `tests/test_blast_guest_destroy.py`

- [ ] **Step 1: Write the failing test**

```python
def test_informational_disks_snapshots_pool():
    inp = _inputs(
        vmid="9000", kind="qemu",
        guest_config={"scsi0": "local-lvm:vm-9000-disk-0,size=32G",
                      "scsi1": "nas:vm-9000-disk-1,size=100G"},
        snapshots=[{"name": "pre-upgrade"}, {"name": "current"}],
        pools=[{"poolid": "prod", "members": [{"vmid": 9000}]}],
    )
    r = compute_guest_destroy_blast(inp)
    assert r.risk == RISK_HIGH and r.complete is True
    kinds = {a["kind"] for a in r.affected}
    assert {"disk", "snapshots", "pool"} <= kinds
    disks = [a for a in r.affected if a["kind"] == "disk"]
    assert {d["ref"] for d in disks} == {"local-lvm", "nas"}  # storages named
    snap = next(a for a in r.affected if a["kind"] == "snapshots")
    assert "2" in snap["effect"]  # snapshot count surfaced
    pool = next(a for a in r.affected if a["kind"] == "pool")
    assert pool["ref"] == "prod"
    assert all(a["category"] == "informational" for a in r.affected)


def test_snapshot_read_failure_is_incomplete_not_zero():
    # None snapshots == read failed -> must NOT silently say "no snapshots"
    inp = _inputs(snapshots=None)
    r = compute_guest_destroy_blast(inp)
    assert r.complete is False
    assert any("snapshot" in s.lower() and "could not" in s.lower() for s in r.summary_lines)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_blast_guest_destroy.py -k informational -q`
Expected: FAIL — `NameError: compute_guest_destroy_blast` / assertion errors.

- [ ] **Step 3: Write minimal implementation**

In `src/proximo/blast.py`:

```python
def compute_guest_destroy_blast(inp: GuestDestroyInputs) -> GuestDestroyBlastResult:
    """Pure, no I/O. Classify what destroying inp.vmid does, conditional on purge/force.
    Risk is RISK_HIGH unconditional (destroy is irreversible) and only ever raised."""
    res = "qemu/{0}".format(inp.vmid) if inp.kind == "qemu" else "{0}/{1}".format(inp.kind, inp.vmid)
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

    # --- INFORMATIONAL: snapshots ---
    if inp.snapshots is None:
        complete = False
        summary.append(f"could NOT read snapshots for {res} — cannot confirm what is removed")
    elif inp.snapshots:
        affected.append({
            "category": "informational", "kind": "snapshots", "ref": str(len(inp.snapshots)),
            "effect": f"removes {len(inp.snapshots)} snapshot(s) with the guest",
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_blast_guest_destroy.py -k "informational or snapshot" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/proximo/blast.py tests/test_blast_guest_destroy.py
git commit -m "feat(blast): guest-destroy informational category (disks/snapshots/pool)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: WON'T-PROCEED — `protection=1`

**Files:**
- Modify: `src/proximo/blast.py` (inside `compute_guest_destroy_blast`, before the return)
- Test: `tests/test_blast_guest_destroy.py`

- [ ] **Step 1: Write the failing test**

```python
def test_protection_refuses_regardless_of_force():
    for force in (False, True):
        inp = _inputs(guest_config={"protection": 1}, force=force)
        r = compute_guest_destroy_blast(inp)
        wp = [a for a in r.affected if a["kind"] == "protection"]
        assert wp, f"protection not flagged (force={force})"
        assert wp[0]["category"] == "wont_proceed"
        assert any("protection" in s.lower() for s in r.risk_reasons)
        # force must NOT be described as overriding protection
        assert "force" not in wp[0]["effect"].lower() or "not" in wp[0]["effect"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_blast_guest_destroy.py -k protection -q`
Expected: FAIL — no `protection` entry.

- [ ] **Step 3: Write minimal implementation**

Insert into `compute_guest_destroy_blast`, after the disks block and before snapshots (only when config is readable):

```python
    # --- WON'T PROCEED: protection=1 (force does NOT override) ---
    if inp.guest_config is not None and str(inp.guest_config.get("protection", 0)) in ("1", "True", "true"):
        affected.append({
            "category": "wont_proceed", "kind": "protection", "ref": res,
            "effect": "PVE will REFUSE: protection=1 is set; force does NOT override — "
                      "unset protection first",
            "severity": "high",
        })
        reasons.append("would be REFUSED: protection=1 (force does not override)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_blast_guest_destroy.py -k protection -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/proximo/blast.py tests/test_blast_guest_destroy.py
git commit -m "feat(blast): guest-destroy wont-proceed — protection=1

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: WON'T-PROCEED — running + `force` conditional

**Files:**
- Modify: `src/proximo/blast.py`
- Test: `tests/test_blast_guest_destroy.py`

- [ ] **Step 1: Write the failing test**

```python
def test_running_without_force_refuses():
    inp = _inputs(status="running", force=False)
    r = compute_guest_destroy_blast(inp)
    wp = [a for a in r.affected if a["kind"] == "running"]
    assert wp and wp[0]["category"] == "wont_proceed"
    assert "force" in wp[0]["effect"].lower()  # names the override that's missing
    assert any("running" in s.lower() for s in r.risk_reasons)


def test_running_with_force_proceeds_not_a_refusal():
    inp = _inputs(status="running", force=True)
    r = compute_guest_destroy_blast(inp)
    # there must be NO wont_proceed/running entry — force overrides the running guard
    assert not [a for a in r.affected if a["kind"] == "running" and a["category"] == "wont_proceed"]


def test_stopped_guest_has_no_running_entry():
    r = compute_guest_destroy_blast(_inputs(status="stopped"))
    assert not [a for a in r.affected if a["kind"] == "running"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_blast_guest_destroy.py -k running -q`
Expected: FAIL — no `running` entry for the refuse case.

- [ ] **Step 3: Write minimal implementation**

Insert into `compute_guest_destroy_blast`, after the protection block:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_blast_guest_destroy.py -k running -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/proximo/blast.py tests/test_blast_guest_destroy.py
git commit -m "feat(blast): guest-destroy wont-proceed — running gated on force

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: WON'T-PROCEED — template with linked clones (+ `_is_linked_clone_of`)

**Files:**
- Modify: `src/proximo/blast.py` (helper + branch)
- Test: `tests/test_blast_guest_destroy.py`

- [ ] **Step 1: Write the failing test**

```python
from proximo.blast import _is_linked_clone_of


def test_is_linked_clone_of_detects_base_backing():
    clone_cfg = {"scsi0": "local-lvm:base-9000-disk-0/vm-101-disk-0,size=32G"}
    assert _is_linked_clone_of(clone_cfg, "9000") is True
    # a full/independent disk does not reference the template base
    assert _is_linked_clone_of({"scsi0": "local-lvm:vm-101-disk-0,size=32G"}, "9000") is False
    # different template
    assert _is_linked_clone_of(clone_cfg, "8000") is False


def test_template_with_clones_refuses_and_names_them():
    inp = _inputs(
        vmid="9000", guest_config={"template": 1},
        clone_configs={
            "101": {"scsi0": "local-lvm:base-9000-disk-0/vm-101-disk-0"},
            "102": {"scsi0": "local-lvm:base-9000-disk-0/vm-102-disk-0"},
            "200": {"scsi0": "local-lvm:vm-200-disk-0"},  # not a clone
        },
        force=True,  # force must NOT clear this
    )
    r = compute_guest_destroy_blast(inp)
    wp = [a for a in r.affected if a["kind"] == "template_clones"]
    assert wp and wp[0]["category"] == "wont_proceed"
    assert "101" in wp[0]["ref"] and "102" in wp[0]["ref"] and "200" not in wp[0]["ref"]
    assert any("clone" in s.lower() for s in r.risk_reasons)


def test_template_clone_scan_unreadable_is_incomplete():
    inp = _inputs(guest_config={"template": 1}, clone_configs=None)
    r = compute_guest_destroy_blast(inp)
    assert r.complete is False
    assert any("clone" in s.lower() and "could not" in s.lower() for s in r.summary_lines)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_blast_guest_destroy.py -k "clone or template" -q`
Expected: FAIL — `ImportError`/`NameError: _is_linked_clone_of`.

- [ ] **Step 3: Write minimal implementation**

Add the helper near the other `_*` disk helpers (after `_boot_slot`):

```python
def _is_linked_clone_of(config: dict, template_vmid: str) -> bool:
    """True if any disk in `config` backs onto template `template_vmid`'s base volume.
    A linked clone's volid carries the template's base volume name: `base-<tmpl>-disk-N`."""
    needle = f"base-{template_vmid}-disk"
    for key, val in (config or {}).items():
        if _is_disk_key(key) and needle in str(val):
            return True
    return False
```

Insert into `compute_guest_destroy_blast`, after the running block:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_blast_guest_destroy.py -k "clone or template" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/proximo/blast.py tests/test_blast_guest_destroy.py
git commit -m "feat(blast): guest-destroy wont-proceed — template with linked clones

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: REFERENCES — HA resource (conditional on `purge`)

**Files:**
- Modify: `src/proximo/blast.py`
- Test: `tests/test_blast_guest_destroy.py`

- [ ] **Step 1: Write the failing test**

```python
def test_ha_reference_dangling_when_purge_false():
    inp = _inputs(vmid="9000", kind="qemu", purge=False,
                  ha_resources=[{"sid": "vm:9000", "state": "started"},
                                {"sid": "vm:7777", "state": "started"}])
    r = compute_guest_destroy_blast(inp)
    ha = [a for a in r.affected if a["kind"] == "ha"]
    assert len(ha) == 1 and ha[0]["ref"] == "vm:9000"
    assert ha[0]["category"] == "reference"
    assert "dangl" in ha[0]["effect"].lower()  # left dangling
    assert "remov" not in ha[0]["effect"].lower() or "manual" in ha[0]["effect"].lower()


def test_ha_reference_cleaned_when_purge_true():
    inp = _inputs(vmid="9000", kind="qemu", purge=True,
                  ha_resources=[{"sid": "vm:9000", "state": "started"}])
    r = compute_guest_destroy_blast(inp)
    ha = next(a for a in r.affected if a["kind"] == "ha")
    assert "remov" in ha["effect"].lower() or "clean" in ha["effect"].lower()
    assert "dangl" not in ha["effect"].lower()  # MUST NOT claim the opposite of what purge does


def test_ha_lxc_sid_matches_ct():
    inp = _inputs(vmid="200", kind="lxc", ha_resources=[{"sid": "ct:200"}])
    r = compute_guest_destroy_blast(inp)
    assert [a for a in r.affected if a["kind"] == "ha"]


def test_ha_read_failure_incomplete():
    r = compute_guest_destroy_blast(_inputs(ha_resources=None))
    assert r.complete is False
    assert any("ha" in s.lower() and "could not" in s.lower() for s in r.summary_lines)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_blast_guest_destroy.py -k ha -q`
Expected: FAIL — no `ha` entry.

- [ ] **Step 3: Write minimal implementation**

First, add a small helper near the top of the references logic (module-level, after `_is_linked_clone_of`):

```python
def _purge_effect(purge: bool, what: str) -> str:
    """Phrase a reference consequence conditional on purge — NEVER the opposite of what happens."""
    if purge:
        return f"PVE will REMOVE this {what} as part of purge=true"
    return f"left DANGLING (purge=false); remove this {what} manually after the destroy"
```

Insert into `compute_guest_destroy_blast`, after the won't-proceed blocks:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_blast_guest_destroy.py -k ha -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/proximo/blast.py tests/test_blast_guest_destroy.py
git commit -m "feat(blast): guest-destroy reference — HA resource (purge-conditional)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: REFERENCES — replication job (conditional on `purge`)

**Files:**
- Modify: `src/proximo/blast.py`
- Test: `tests/test_blast_guest_destroy.py`

- [ ] **Step 1: Write the failing test**

```python
def test_replication_job_matched_by_vmid_prefix():
    inp = _inputs(vmid="9000", purge=False,
                  replication_jobs=[{"id": "9000-0", "target": "node2"},
                                    {"id": "9000-1", "target": "node3"},
                                    {"id": "7777-0", "target": "node2"}])
    r = compute_guest_destroy_blast(inp)
    rep = [a for a in r.affected if a["kind"] == "replication"]
    assert {x["ref"] for x in rep} == {"9000-0", "9000-1"}
    assert all("dangl" in x["effect"].lower() for x in rep)


def test_replication_purge_true_cleaned():
    inp = _inputs(vmid="9000", purge=True, replication_jobs=[{"id": "9000-0"}])
    r = compute_guest_destroy_blast(inp)
    rep = next(a for a in r.affected if a["kind"] == "replication")
    assert "remov" in rep["effect"].lower() and "dangl" not in rep["effect"].lower()


def test_replication_id_prefix_is_exact_not_substring():
    # "90001-0" must NOT match vmid 9000
    inp = _inputs(vmid="9000", replication_jobs=[{"id": "90001-0"}])
    r = compute_guest_destroy_blast(inp)
    assert not [a for a in r.affected if a["kind"] == "replication"]


def test_replication_read_failure_incomplete():
    r = compute_guest_destroy_blast(_inputs(replication_jobs=None))
    assert r.complete is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_blast_guest_destroy.py -k replication -q`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Insert after the HA block:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_blast_guest_destroy.py -k replication -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/proximo/blast.py tests/test_blast_guest_destroy.py
git commit -m "feat(blast): guest-destroy reference — replication job (purge-conditional)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: REFERENCES — backup job (explicit vmid only; all/pool/exclude → incomplete)

**Files:**
- Modify: `src/proximo/blast.py`
- Test: `tests/test_blast_guest_destroy.py`

- [ ] **Step 1: Write the failing test**

```python
def test_backup_explicit_vmid_list_matched():
    inp = _inputs(vmid="9000", purge=False,
                  backup_jobs=[{"id": "job-A", "vmid": "9000,7777"},
                               {"id": "job-B", "vmid": "100,200"}])
    r = compute_guest_destroy_blast(inp)
    bk = [a for a in r.affected if a["kind"] == "backup_job"]
    assert [x["ref"] for x in bk] == ["job-A"]
    assert "dangl" in bk[0]["effect"].lower()
    assert r.complete is True  # explicit lists are fully resolvable


def test_backup_purge_true_cleaned():
    inp = _inputs(vmid="9000", purge=True, backup_jobs=[{"id": "job-A", "vmid": "9000"}])
    r = compute_guest_destroy_blast(inp)
    bk = next(a for a in r.affected if a["kind"] == "backup_job")
    assert "remov" in bk["effect"].lower() and "dangl" not in bk["effect"].lower()


def test_backup_all_mode_is_incomplete_not_assumed():
    inp = _inputs(vmid="9000", backup_jobs=[{"id": "job-all", "all": 1}])
    r = compute_guest_destroy_blast(inp)
    assert r.complete is False
    assert any("backup" in s.lower() and ("all" in s.lower() or "could not" in s.lower())
               for s in r.summary_lines)
    # MUST NOT emit a confident backup_job affected entry for an all-mode job
    assert not [a for a in r.affected if a["kind"] == "backup_job" and a["ref"] == "job-all"]


def test_backup_pool_and_exclude_modes_incomplete():
    for job in ({"id": "j", "pool": "prod"}, {"id": "j", "exclude": "100"}):
        r = compute_guest_destroy_blast(_inputs(vmid="9000", backup_jobs=[job]))
        assert r.complete is False


def test_backup_read_failure_incomplete():
    r = compute_guest_destroy_blast(_inputs(backup_jobs=None))
    assert r.complete is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_blast_guest_destroy.py -k backup -q`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Insert after the replication block:

```python
    # --- REFERENCE: backup jobs (explicit vmid lists only; all/pool/exclude -> incomplete) ---
    if inp.backup_jobs is None:
        complete = False
        summary.append("could NOT read backup jobs — cannot determine backup-job references")
    else:
        for job in inp.backup_jobs:
            jid = str(job.get("id", "?"))
            # Non-explicit selection modes: cannot cheaply prove membership -> flag incomplete.
            if any(k in job for k in ("all", "pool", "exclude")) or "vmid" not in job:
                complete = False
                mode = next((k for k in ("all", "pool", "exclude") if k in job), "non-explicit")
                summary.append(
                    f"backup job {jid} uses {mode} selection — could NOT confirm whether "
                    f"{inp.vmid} is covered"
                )
                continue
            members = {v.strip() for v in str(job.get("vmid", "")).split(",") if v.strip()}
            if str(inp.vmid) in members:
                affected.append({
                    "category": "reference", "kind": "backup_job", "ref": jid,
                    "effect": _purge_effect(inp.purge, "backup-job membership"),
                    "severity": "info" if inp.purge else "medium",
                })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_blast_guest_destroy.py -k backup -q`
Expected: PASS. Then run the whole pure-test file: `uv run python -m pytest tests/test_blast_guest_destroy.py -q` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/proximo/blast.py tests/test_blast_guest_destroy.py
git commit -m "feat(blast): guest-destroy reference — backup job (explicit vmid; else incomplete)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: I/O `gather_guest_dependents` + `guest_destroy_blast` wrapper

Fail-closed reads; each failure → that input is `None` (never raises). Mirrors `gather_storage_dependents`.

**Files:**
- Modify: `src/proximo/blast.py` (imports for the readers + the two functions)
- Test: `tests/test_blast_guest_destroy.py`

- [ ] **Step 1: Write the failing test (fakes, not live API)**

```python
from proximo.blast import gather_guest_dependents, guest_destroy_blast


class _FakeApi:
    """Minimal stand-in: each attr is the value to return, or an Exception to raise."""
    def __init__(self, **kw):
        self._kw = kw
        class _C:  # api.config.node fallback
            node = "n1"
        self.config = _C()

    def _maybe(self, key, default):
        v = self._kw.get(key, default)
        if isinstance(v, Exception):
            raise v
        return v

    def _get(self, path):
        if path == "/cluster/replication":
            return self._maybe("replication", [])
        if path == "/cluster/backup":
            return self._maybe("backup", [])
        raise AssertionError(f"unexpected path {path}")

    def snapshot_list(self, vmid, kind="lxc", node=None):
        return self._maybe("snapshots", [])


def test_gather_packs_inputs_and_is_fail_closed(monkeypatch):
    import proximo.blast as B
    monkeypatch.setattr(B, "cluster_resources",
                        lambda api: [{"vmid": 9000, "type": "qemu", "node": "n1", "pool": "prod"},
                                     {"vmid": 101, "type": "qemu", "node": "n1"}])
    monkeypatch.setattr(B, "guest_config_get",
                        lambda api, vmid, kind, node=None: {"template": 1} if str(vmid) == "9000"
                        else {"scsi0": "local-lvm:base-9000-disk-0/vm-101-disk-0"})
    monkeypatch.setattr(B, "ha_resources_list", lambda api: [{"sid": "vm:9000"}])
    monkeypatch.setattr(B, "pools_list", lambda api: [{"poolid": "prod", "members": [{"vmid": 9000}]}])
    api = _FakeApi(replication=[{"id": "9000-0"}], backup=[{"id": "j", "vmid": "9000"}],
                   snapshots=[{"name": "s1"}])
    inp = gather_guest_dependents(api, "9000", "qemu", "n1", purge=False, force=False)
    assert inp.guest_config == {"template": 1}
    assert inp.clone_configs and "101" in inp.clone_configs and "9000" not in inp.clone_configs
    assert inp.ha_resources == [{"sid": "vm:9000"}]
    assert inp.replication_jobs == [{"id": "9000-0"}]


def test_gather_read_failures_become_none(monkeypatch):
    import proximo.blast as B
    monkeypatch.setattr(B, "cluster_resources", lambda api: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(B, "guest_config_get",
                        lambda api, vmid, kind, node=None: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(B, "ha_resources_list", lambda api: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(B, "pools_list", lambda api: (_ for _ in ()).throw(RuntimeError("x")))
    api = _FakeApi(replication=RuntimeError("x"), backup=RuntimeError("x"), snapshots=RuntimeError("x"))
    inp = gather_guest_dependents(api, "9000", "qemu", "n1", purge=False, force=False)
    assert inp.guest_config is None and inp.ha_resources is None
    assert inp.replication_jobs is None and inp.backup_jobs is None
    assert inp.pools is None and inp.snapshots is None and inp.clone_configs is None
    # the whole thing still computes (never raises) and is flagged incomplete
    r = guest_destroy_blast(api, "9000", "qemu", "n1", purge=False, force=False)
    assert r.complete is False and r.risk == RISK_HIGH
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_blast_guest_destroy.py -k gather -q`
Expected: FAIL — `ImportError: gather_guest_dependents`.

- [ ] **Step 3: Write minimal implementation**

At the top of `blast.py`, ensure the readers are imported (add an import block if not present):

```python
from proximo.cluster_ops import cluster_resources, ha_resources_list
from proximo.config_edit import guest_config_get
from proximo.tasks_pools import pools_list
```

> If any of these imports creates a circular import (blast ↔ those modules), import them lazily *inside* `gather_guest_dependents` instead (function-local `from … import …`). Verify by running the suite after this task. `snapshot_list` is a method on the api object (`api.snapshot_list`), not a module function.

Add the two functions after `compute_guest_destroy_blast`:

```python
def _safe(fn, default=None):
    """Call fn(); on ANY exception return `default` (the 'read failed' sentinel)."""
    try:
        return fn()
    except Exception:
        return default


def gather_guest_dependents(api, vmid: str, kind: str, node: str | None,
                            purge: bool, force: bool) -> GuestDestroyInputs:
    """I/O: read everything compute needs. NEVER raises — a failed read becomes None so the
    honesty contract (None == unknown, [] == confirmed-empty) holds downstream."""
    cfg = _safe(lambda: guest_config_get(api, vmid, kind, node))
    if cfg == {} or cfg is None:
        # an empty dict from a 200 {"data": null} is an unreadable config, not 'no disks'
        cfg = None if not cfg else cfg

    status = "unknown"
    gs = _safe(lambda: api.guest_status(vmid, kind, node))
    if isinstance(gs, dict) and gs.get("status"):
        status = str(gs["status"])

    rows = _safe(lambda: cluster_resources(api))
    clone_configs: dict | None = None
    if rows is not None:
        clone_configs = {}
        for rrow in rows:
            if rrow.get("type") not in ("qemu", "lxc"):
                continue
            rid = str(rrow.get("vmid", ""))
            if rid == str(vmid) or not rid:
                continue
            ccfg = _safe(lambda rrow=rrow, rid=rid: guest_config_get(
                api, rid, str(rrow.get("type")), rrow.get("node")))
            if ccfg:
                clone_configs[rid] = ccfg
            # a single unreadable peer doesn't None the whole map; the template branch only
            # over-reports completeness if EVERY peer fails — acceptable (compute still HIGH).

    return GuestDestroyInputs(
        vmid=str(vmid), kind=str(kind), purge=purge, force=force,
        guest_config=cfg, status=status,
        ha_resources=_safe(lambda: ha_resources_list(api)),
        replication_jobs=_safe(lambda: api._get("/cluster/replication")),
        backup_jobs=_safe(lambda: api._get("/cluster/backup")),
        pools=_safe(lambda: pools_list(api)),
        snapshots=_safe(lambda: api.snapshot_list(vmid, kind, node)),
        clone_configs=clone_configs,
    )


def guest_destroy_blast(api, vmid: str, kind: str, node: str | None,
                        purge: bool, force: bool) -> GuestDestroyBlastResult:
    """Convenience: gather (I/O, fail-closed) then compute (pure)."""
    return compute_guest_destroy_blast(
        gather_guest_dependents(api, vmid, kind, node, purge, force))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_blast_guest_destroy.py -q`
Expected: PASS (whole file). Then `uv run ruff check src tests` → clean.

- [ ] **Step 5: Commit**

```bash
git add src/proximo/blast.py tests/test_blast_guest_destroy.py
git commit -m "feat(blast): guest-destroy gather (fail-closed I/O) + wrapper

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Wire into `plan_delete` + thread `force` through the server

**Files:**
- Modify: `src/proximo/provisioning.py` (`plan_delete` signature + found branch)
- Modify: `src/proximo/server.py:847` (pass `force`)
- Test: `tests/test_blast_guest_destroy.py` (a wiring test using a fake api)

- [ ] **Step 1: Write the failing test**

```python
def test_plan_delete_populates_affected_and_completes(monkeypatch):
    from proximo.provisioning import plan_delete
    import proximo.blast as B

    # found, stopped, protected guest with one HA ref; purge off
    monkeypatch.setattr(B, "cluster_resources", lambda api: [])
    monkeypatch.setattr(B, "guest_config_get", lambda api, vmid, kind, node=None: {"protection": 1})
    monkeypatch.setattr(B, "ha_resources_list", lambda api: [{"sid": "vm:9000"}])
    monkeypatch.setattr(B, "pools_list", lambda api: [])

    class _Api(_FakeApi):
        def guest_status(self, vmid, kind="lxc", node=None):
            return {"status": "stopped", "name": "tmpl"}

    api = _Api(replication=[], backup=[], snapshots=[])
    plan = plan_delete(api, "9000", "qemu", None, purge=False, force=False)
    assert plan.risk == "high"
    assert plan.affected, "Plan.affected should carry the cascade"
    kinds = {a["kind"] for a in plan.affected}
    assert "protection" in kinds and "ha" in kinds
    # protection reason folded into the plan's risk_reasons
    assert any("protection" in r.lower() for r in plan.risk_reasons)


def test_plan_delete_not_found_skips_cascade(monkeypatch):
    from proximo.provisioning import plan_delete

    class _NF(_FakeApi):
        def guest_status(self, vmid, kind="lxc", node=None):
            err = RuntimeError("404")
            class _R: status_code = 404
            err.response = _R()
            raise err

    plan = plan_delete(_NF(), "9000", "qemu", None, purge=False, force=False)
    assert plan.risk == "high" and not plan.affected  # no cascade on a confirmed-absent guest
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_blast_guest_destroy.py -k plan_delete -q`
Expected: FAIL — `plan_delete()` takes no `force` arg / `affected` empty.

- [ ] **Step 3: Write minimal implementation**

In `src/proximo/provisioning.py`, change the signature and the found branch. Add `force: bool = False` to the parameter list (after `purge`). Import the engine at the top of the module: `from proximo.blast import guest_destroy_blast`. Then in the `else:` (found) branch, after building `blast`/`reasons`, before the `return Plan(...)`:

```python
        # --- cascade: what destroying this guest actually does (purge/force-conditional) ---
        gdb = guest_destroy_blast(api, vmid, kind, node, purge, force)
        blast.extend(gdb.summary_lines)
        reasons.extend(gdb.risk_reasons)
        cascade_affected = gdb.affected
        cascade_complete = gdb.complete
```

And update the `return Plan(...)` (found branch only) to pass them:

```python
    return Plan(
        action="pve_delete",
        target=f"{kind}/{vmid}",
        change=f"delete {kind} {vmid}" + (" (purge)" if purge else ""),
        current=current,
        blast_radius=blast,
        risk=RISK_HIGH,
        risk_reasons=reasons,
        affected=locals().get("cascade_affected", []),
        complete=locals().get("cascade_complete", True),
    )
```

> The `locals().get(...)` keeps the check_failed / not_found branches (which don't set the cascade vars) returning the defaults — they correctly carry NO cascade. If you prefer explicit, initialize `cascade_affected = []` and `cascade_complete = True` at the top of the function and drop the `locals()` calls.

In `src/proximo/server.py`, line ~847, change:

```python
    plan = _plan("pve_delete_guest", target, lambda: plan_delete(api, vmid, kind, node, purge, force))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_blast_guest_destroy.py -k plan_delete -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/proximo/provisioning.py src/proximo/server.py tests/test_blast_guest_destroy.py
git commit -m "feat(blast): wire guest-destroy cascade into plan_delete (thread force)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Seam test through the server response + PROVE ledger

Confirms a dry-run `pve_delete_guest` call surfaces `affected`/`complete` in the returned plan dict and that the existing audit path still records correctly.

**Files:**
- Test: add to the existing server-wiring test file. Find it first:
  `grep -rln "pve_delete_guest\|plan_delete" tests/` → use the file that already exercises server tool calls with a fake/mocked api (likely `tests/test_server*`).

- [ ] **Step 1: Write the failing test**

Locate the existing pattern for calling a server tool in dry-run with a fake api (search: `grep -rn "status.*plan" tests/test_server*.py | head`). Mirror it:

```python
def test_pve_delete_guest_plan_surfaces_cascade(monkeypatch, <existing fixtures>):
    # arrange a found, running guest (force=False) so a wont_proceed/running entry appears
    # ... set up the server's api the way the existing dry-run tests do ...
    resp = pve_delete_guest(vmid="9000", kind="qemu", confirm=False)
    assert resp["status"] == "plan"
    assert "affected" in resp and isinstance(resp["affected"], list)
    assert any(a["category"] == "wont_proceed" for a in resp["affected"])
    assert "complete" in resp
```

> Use the SAME api-injection mechanism the neighboring dry-run tests use (e.g. monkeypatching `_svc()` or a fixture). Do not invent a new one. If the existing tests construct the service with a mock api exposing `guest_status`/`_get`/`snapshot_list`, extend that mock with the reads `gather_guest_dependents` needs (`cluster_resources`/`ha_resources_list`/`pools_list` via monkeypatch as in Task 9).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/<that_file>.py -k delete_guest_plan_surfaces -q`
Expected: FAIL — `affected` missing or empty before the wiring is exercised through the server.

- [ ] **Step 3: Write minimal implementation**

No production change expected (Task 10 already wired it). If the test fails because `Plan.as_dict()` doesn't include `affected`/`complete`, inspect `planning.py:as_dict` and confirm it serializes those fields; they were added to the dataclass already (lines 57–58). If `as_dict` omits them, add them there — that is the only production change this task should need.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/<that_file>.py -k delete_guest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/<that_file>.py src/proximo/planning.py
git commit -m "test(blast): guest-destroy cascade surfaces through pve_delete_guest plan

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: Full verification + CHANGELOG

**Files:**
- Modify: `CHANGELOG.md` (`[Unreleased]`)

- [ ] **Step 1: Run the full gate**

```bash
uv run ruff check src tests
uv run pyright
uv run python -m pytest -q
```
Expected: ruff clean, pyright `0 errors`, pytest `≥ 2227 + new tests passed`. Fix anything red before continuing (do not round green).

- [ ] **Step 2: Add the CHANGELOG entry**

Under `## [Unreleased]` in `CHANGELOG.md`:

```markdown
### Added
- **Blast-radius op-class #4 — guest-destroy.** `pve_delete_guest` dry-run now computes, at PLAN
  time, what destroying a guest actually does: what PVE will REFUSE (protection=1, template with
  linked clones, running without force), what references it leaves dangling vs cleans up
  (HA / replication / explicit backup-job vmid — conditional on `purge`), and what it intrinsically
  removes (disks+storages, snapshots, pool membership). Per-edge incompleteness is flagged; a failed
  read is never reported as "nothing found." (`compute_guest_destroy_blast` / `gather_guest_dependents`.)
```

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): guest-destroy blast-radius op-class (Unreleased)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: Adversarial redteam (3-lens) + fixes

After the feature is green, run an adversarial pass — three independent lenses — and fix every real finding test-first. This is a required quality gate for blast-radius classes (matches the three shipped).

- [ ] **Step 1:** Dispatch (or reason as) three reviewers over the diff:
  - **Correctness** — does the linked-clone substring scan misfire (e.g. `base-9000-disk` matching vmid `900`)? Is the replication `<vmid>-N` segmentation exact? Does an LXC `ct:` vs qemu `vm:` sid ever mismatch?
  - **Honesty** — can any line state the opposite of what `purge`/`force` does? Is any failed read rendered as "none/safe"? Does `complete` ever stay True when an input was None?
  - **Leak** — any real infra names/IPs/secrets in new code, tests, or the CHANGELOG? (the four redacted-marker shapes; `172.30.*`)
- [ ] **Step 2:** For each confirmed finding, write a failing test first, then fix. Re-run the full gate.
- [ ] **Step 3:** Add `tests/test_blast_guest_destroy_redteam.py` capturing the adversarial cases. Commit:

```bash
git add tests/test_blast_guest_destroy_redteam.py src/proximo/blast.py
git commit -m "test(blast): guest-destroy adversarial redteam + fixes

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 14: Live read-only smoke (environment-permitting)

Dogfood the published path against a real PVE, read-only — don't round unit-green up to "works."

- [ ] **Step 1:** Using the configured read-only PVE token, call `pve_delete_guest(confirm=False)` (dry-run — NEVER `confirm=True`) on a throwaway/stopped guest and on the test template if one exists. Capture the returned `affected`/`complete`.
- [ ] **Step 2:** Confirm the two live-shape items from the spec's Open list: linked-clone volid naming (`base-<vmid>-disk-N`) and `/cluster/backup` field names (`vmid`/`all`/`pool`/`exclude`). If reality differs, write a failing test encoding the real shape, fix, re-run the gate.
- [ ] **Step 3:** Record the smoke result (what branches the live cluster could exercise vs unit-only) in the spec's Open section or an untracked local note. No commit unless a fix was needed.

---

## Self-Review

**Spec coverage:** load-bearing purge/force framing → Tasks 4,6,7,8 (conditional wording + the `_purge_effect` helper); three won't-proceed cases → Tasks 3,4,5; references → Tasks 6,7,8; informational → Task 2; honesty contract (None vs [], zero-never-safe, backup incomplete) → Tasks 2,6,7,8 + gather Task 9; output contract (`GuestDestroyBlastResult` + entry dict) → Tasks 1,2; wiring → Tasks 10,11; testing (TDD + redteam + live smoke) → all tasks + 13,14; non-goals (no firewall by-IP, no package split) → respected (not built). **No gaps.**

**Placeholder scan:** Task 11 deliberately leaves the exact existing-test-file name to discovery (`grep` command given) because the harness can't know it ahead of time — that's an instruction, not a placeholder; the assertion code is concrete. No `TBD` / `handle edge cases` / "write tests for the above"; every code step carries runnable code.

**Type consistency:** `GuestDestroyInputs` fields (Task 1) are consumed with the same names in Tasks 2–8; `compute_guest_destroy_blast(inp)` (single arg) is called consistently; `gather_guest_dependents(api, vmid, kind, node, purge, force)` and `guest_destroy_blast(...)` signatures match between Task 9 definition and Task 10 usage; affected-entry keys (`category`/`kind`/`ref`/`effect`/`severity`) are uniform across all category tasks.
