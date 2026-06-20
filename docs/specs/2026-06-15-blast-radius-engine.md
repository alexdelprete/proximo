# Spec — Blast-radius engine (v1: storage/disk class)

> Created 2026-06-15. Status: **pre-implementation, awaiting maintainer review.**
> Branch: `feat/blast-radius-engine`. Author: brainstormed with the maintainer.

## Motivation

The `Plan` dataclass carries a `blast_radius: list[str]` field, but for the dangerous
governance ops it holds only **generic, hand-written warnings** — e.g. `plan_storage_delete`
says *"any guest disk living ONLY on this storage becomes inaccessible."* True, but it
**cannot name the actual affected guests** because the `plan_*` factories are pure and never
read the cluster. That generic sentence is exactly what any competitor can hardcode.

Proximo's stated moat (POSITIONING / LANDSCAPE) is *"beat them on PLAN / UNDO / **blast-radius**
— the un-boltable parts."* Generic MCP gateways and policy layers are **resource-blind**: they
cannot say *"deleting storage `nas` orphans VM 101's rootfs and CT 200's rootfs"* because they
do not model the cluster. Blast-radius is the one differentiator that is **named as the moat and
still hollow in the code.** This spec makes it real for the first op-class.

## Goal

A general, pure **blast-radius engine** (`src/proximo/blast.py`) that, given already-fetched
cluster state, computes the **specific** downstream impact of a dangerous op — naming affected
resources, the relationship (which disk/slot), and the effect (won't boot vs degraded) — and
surfaces it both as human-readable `blast_radius` strings **and** a machine-structured
`affected: list[dict]` field. The engine is wired into the existing PLAN seam so the computed
blast-radius flows into the tamper-evident ledger (PROVE) for free.

v1 lights up the **storage/disk class** as the engine-proving vertical slice. Other op-classes
(access/ACL, firewall/network) follow the **same seam** in later rounds.

## v1 scope — the shared storage-side primitive

"Storage/disk class" is really three different dependency graphs. v1 ships the **one primitive
shared by two ops**, and explicitly defers the other two graphs:

| Op | Reuses primitive? | v1 |
|---|---|---|
| `pve_storage_delete` | "which guests hold volumes on storage S" | ✅ in |
| `pve_storage_update` (disable) | **identical** set — guests with volumes on S lose access | ✅ in |
| `pve_storage_update` (nodes-restrict) | same primitive **+ a node-set-diff filter** | ⛔ deferred (immediate fast-follow) |
| `guest-destroy` (`pve_delete_guest`) | **reverse** graph (HA resources, replication/backup jobs depend on the guest) | ⛔ deferred |
| `disk-move` / `content-delete` | different graph (single-volume, not storage-wide) | ⛔ deferred |

The shared primitive: **given a target storage S, enumerate every guest cluster-wide, read each
guest's config, parse its disk volids, and classify each guest's loss.** `storage_delete` and
`storage_update(disable=True)` consume this primitive over the **exact same affected set** (every
guest with a volume on S); only their framing ("definition removed cluster-wide" vs "storage
disabled — guests lose access") differs. The nodes-restrict variant adds one filter (only guests
on a now-excluded node are cut off) and is the immediate fast-follow, kept out of v1 so the shared
primitive stays identical across both v1 ops.

## Architecture — pure engine + thin enrichment seam (Approach A)

**This mirrors the established house idiom.** `plan_group_delete(api, groupid)` / `plan_user_delete`
already *"do safe reads to compute the affected set"* at plan time, with `"RISK_HIGH maintained:
uncertainty is not a safety signal"` written into the code. So a plan that reads the cluster to name
what it affects is the **house standard**, not a new pattern. We follow it: `plan_storage_delete` /
`plan_storage_update` take `api` (like `plan_group_delete`, `plan_power`) and delegate the pure graph
reasoning to `blast.py`.

```
storage_admin.py                         blast.py
────────────────                         ────────
plan_storage_delete(api, S):             gather_storage_dependents(api, S) -> (guests, configs, complete)
  result = blast.storage_blast(api, S)     # I/O: cluster_resources() + guest_config_get() per guest;
  return Plan(                             # catches per-guest read failure -> complete=False (never raises)
    blast_radius = result.summary_lines  compute_storage_blast(S, guests, configs, complete) -> BlastResult
                   + GENERIC_FLOOR,         # PURE — no api. The differentiated, unit-testable IP.
    affected     = [e.as_dict() ...],      .affected: list[BlastEntry]
    risk         = RISK_HIGH (floor),      .summary_lines: list[str]   (INCOMPLETE marker first if !complete)
    ...)                                    .complete: bool
                                           .max_severity: "high"|"medium"|"none"  (drives risk escalation)
plan_storage_update(api, S, ..., disable):
  if disable is True:  enrich as above; risk = _max_risk(MEDIUM, HIGH-if-max_severity-high)
  else:                unchanged generic plan (no guest-disk blast)
```

- **`blast.py` splits pure reasoning from I/O.** `compute_storage_blast(...)` is **pure** (no `api`)
  and **fully unit-testable** with fabricated configs — the valuable, differentiated IP.
  `gather_storage_dependents(api, S)` does the safe reads and **catches per-guest failures** (turning
  them into `complete=False`, never raising), so the plan always builds.
- **The `plan_*` functions keep their generic strings as a fallback floor** — the engine output is
  *prepended* (so the INCOMPLETE marker and the named guests lead), never replacing the generic
  warnings.
- **The ledger weld is free**: `_plan` → `_record_plan` already serializes the whole plan; the
  computed blast-radius lands in PROVE automatically, and the new `affected` field is added with one
  line in `_record_plan`'s `detail`.

### Enumeration MUST be cluster-wide

Storage definitions are **cluster-scoped** — a guest on *any* node can hold a disk on storage S.
Enumerating per-node (`list_guests(node)`) would **undercount**, presenting a *falsely small*
blast-radius — strictly worse than none, because "only 1 guest affected" reads as "probably fine."

v1 enumerates via a single **`cluster_resources(api)`** (no `type=` filter — avoids the ambiguity of
whether `type=vm` includes LXC), then keeps rows where `row["type"] in {"qemu", "lxc"}`. Each row
carries `{vmid, node, type, status, name}` for **all** guests cluster-wide. Each guest's config is
then read via **`guest_config_get(api, vmid, kind, node)`** with `kind = row["type"]`.
Forward-from-configs is the robust primitive: it gives disk-slot granularity (needed for won't-boot
vs degraded) and generalizes to the deferred `guest-destroy` graph.

> Read cost: 2 + N reads (N = guest count). These are safe GETs and PLAN is a deliberate,
> low-frequency operation, so this is acceptable for v1. A future optimization may use
> `storage_content(S, node)` to prefilter candidate vmids; **not** in v1 (correctness-first).

## The honesty contract (the crux)

This is where the thesis lives or dies. The engine must never let a failed/partial read read as
"nothing affected = safe."

1. **Fail-closed on incomplete enumeration.** If `cluster_resources` fails, or any guest's
   `guest_config_get` raises (node down, transient error) **or returns an empty/null config**
   (HTTP 200 `{"data": null}` — a real guest config is never empty, so we cannot see its disks),
   the result is marked **`complete=False`** and the **first** `blast_radius` line is a loud,
   uppercase `"⚠ INCOMPLETE: could not enumerate N of M guests — do NOT treat this list as
   exhaustive"`. The `affected` list still carries every guest successfully classified, plus a
   sentinel entry `{"resource": "?", "effect": "enumeration incomplete", "severity": "unknown"}`.
   Never a silent short list; never an empty list rendered as safe. *(Redteam-hardened 2026-06-15:
   the empty-config soft-failure path was the one way a guest could silently drop with
   `complete=True`.)*

2. **The engine never lowers risk.** `plan_storage_delete` is hardcoded `RISK_HIGH`; enrichment
   keeps it HIGH. `plan_storage_update` is `RISK_MEDIUM`; enrichment **may RAISE it to HIGH** (via
   `_max_risk`) when it finds a **running** guest whose **only copy** of a disk is on S — but never
   lowers it. Finding zero affected guests is **not** a safety signal (planning.py's own creed).

3. **Total-death vs degraded, per guest.** Each affected guest is classified:
   - **won't boot** (`severity: high`): its boot disk is on S — `rootfs` for an LXC; for a VM, the
     disk named by the `boot`/`bootdisk` config line, or (fallback) when *all* of the guest's disks
     are on S.
   - **degraded** (`severity: medium`): a non-boot disk (data disk, `mpN`, `unusedN`) is on S but
     the boot disk lives elsewhere.
   - **running** guests carry an extra effect note: *"RUNNING — losing the disk live may crash or
     corrupt the guest"* (state comes free from `cluster_resources`).

4. **Honest VM boot-disk detection.** VM boot-disk identification uses the `boot`/`bootdisk` config
   line when present. When the boot disk is **indeterminate** (no `bootdisk`, no `boot: order=` with
   a disk token — e.g. legacy `boot: c`/`cdn`, or a net-boot `order=net0`) **and** the guest loses a
   disk on S that is neither its only copy nor a boot-critical slot, the engine **over-flags**: it
   reports `severity: high` with *"may NOT boot — the boot disk could not be determined and may be
   among them"* — because one of the lost disks may itself be the boot disk. It does **not** claim
   *"boot disk is elsewhere"* (a reassurance it cannot back up). The legacy-`boot: c` and disk-bearing
   net-boot cases are deliberately over-flagged here; tightening `_boot_slot` to parse them is a future
   precision enhancement, not a safety gap. (Over-flag, never under-flag — risk is never lowered on
   uncertainty.)

## Output contract — structured `affected` + human strings (maintainer's choice)

Additive, non-breaking → stays a semver **minor**.

```python
@dataclass
class Plan:
    ...
    blast_radius: list[str]
    affected: list[dict] = field(default_factory=list)   # NEW — additive
```

`affected` entry shape (a `BlastEntry` dataclass in `blast.py`, serialized to dict):

```python
{
  "resource": "qemu/101",          # kind/vmid
  "vmid": "101",
  "name": "web-01",                # from cluster_resources; "" if absent
  "node": "pve1",
  "via": ["scsi0", "unused0"],     # disk slots whose volid names storage S
  "effect": "will not boot (boot disk on this storage)",
  "only_copy": true,               # guest has NO disk outside S
  "running": true,
  "severity": "high",              # high | medium | unknown
}
```

`Plan.as_dict()` gains `"affected": self.affected`; `_record_plan` adds `"affected"` to its
ledger `detail`. **The v1 storage mutation ops are MCP-only — `pve_storage_delete` /
`pve_storage_update` are NOT in the curated A2A slice** (`SKILLS` in `a2a/skills.py`; the
dangerous/irreversible plane deliberately stays off A2A). So in v1 `affected` is surfaced via the
**MCP tool response** and the **PROVE ledger**, not A2A. Because the serialization rides on
`as_dict()`, if a blast-enriched op is ever added to the A2A slice, `affected` flows through
unchanged — to be verified at that point. (The MCP seam test asserts `resp["affected"]`, proving
`as_dict()` carries the field.)

## Files

- **New:** `src/proximo/blast.py` — `compute_storage_blast(...)` (PURE), `gather_storage_dependents(api, S)`
  (I/O, failure-catching), `storage_blast(api, S)` (= gather→compute), `BlastEntry`, `BlastResult`,
  volid parsing (`_storage_of_volid`, `_disk_slots`, `_boot_slot`), classification (`_classify_guest`).
- **Edit:** `src/proximo/planning.py` — add `affected: list[dict] = field(default_factory=list)` to
  `Plan` (import `field`); add `"affected": self.affected` to `as_dict`.
- **Edit:** `src/proximo/storage_admin.py` — `plan_storage_delete(api, storage)` and
  `plan_storage_update(api, storage, ...)` take `api`, call `blast.storage_blast`, prepend
  `summary_lines`, set `affected`, maintain the `RISK_HIGH` floor (delete) / `_max_risk`-escalate
  (update-disable). Keep the existing generic strings as the floor.
- **Edit:** `src/proximo/server.py` — pass `api` into the two build lambdas
  (`plan_storage_delete(api, storage)`, `plan_storage_update(api, storage, ...)`); add `"affected"`
  to `_record_plan`'s ledger `detail`.
- **New:** `tests/test_blast.py` — pure-engine unit tests.
- **Edit:** `tests/test_storage_admin.py` (or new `tests/test_blast_seam.py`) — server-seam tests
  with a fake api: happy path + partial-failure fail-closed + risk-raise on disable.
- **Edit:** `scripts/live-smoke/` — add a **read-only** blast-radius check (PLAN only, never
  confirm) so the engine is exercised against the real node.

## Testing (TDD throughout)

Pure-engine unit tests (fabricated configs, zero API):
- only-copy VM (all disks on S) → `won't boot`, `only_copy=true`, `severity=high`
- degraded VM (rootfs elsewhere, data disk on S) → `degraded`, `only_copy=false`, `medium`
- LXC `rootfs` on S → won't boot; LXC `mp0` on S, rootfs elsewhere → degraded
- guest with no volume on S → not in `affected`
- malformed / storage-less volid → skipped safely, never crashes
- `unusedN` disk on S → included (its data is on S), classified degraded
- VM with explicit `boot`/`bootdisk` → boot disk respected; without → conservative fallback
- multiple guests across multiple nodes → all enumerated, sorted deterministically

Server-seam tests (fake api):
- happy path: engine result merged into `blast_radius` + `affected`; ledger detail carries both
- **fail-closed:** a guest config read raises → plan still returns, `complete=False`, INCOMPLETE
  line present, sentinel in `affected`, **risk unchanged (still HIGH)**
- `storage_update(disable=True)` with a running only-copy guest → risk **raised** MEDIUM→HIGH
- serialization: the MCP tool response carries `affected` (`resp["affected"]`), proving `as_dict()`
  exposes the field (storage mutation ops are MCP-only, not in the A2A slice — see Output contract)

Full suite stays green (currently 2126); ruff + `pyright` (src-scoped) clean. Independent
adversarial redteam pass before "done" (correctness · honesty/under-flag · leak).

## Non-goals / explicitly deferred

- `storage_update` **nodes-restrict** blast-radius (node-set-diff refinement — immediate fast-follow,
  same primitive + a node filter; out of v1 only to keep the shared primitive identical).
- `guest-destroy` and `disk-move/content-delete` blast-radius (different graphs — next rounds).
- access/ACL and firewall/network blast-radius (later op-classes, same seam).
- Orphaned-volume enumeration via `storage_content` (volumes on S not referenced by any guest).
- Live-firing a real storage *delete* (RED, destructive) — v1 proves the engine via **PLAN/read
  only** on the real node; the destructive op is never executed by Proximo for this test.

## Open / smoke-confirm

- Confirm `cluster_resources` returns `name` + `status` for both `vm` and `lxc` types (it should;
  verify field presence live before relying on `name`).
- Confirm the VM `boot` line format on the target PVE version (`order=scsi0;net0` style) for the
  boot-disk parser; the conservative fallback covers the unparseable case regardless.
- Confirm `unusedN` and `efidisk0`/`tpmstate0` slot names appear with normal `storage:...` volids
  (they do on PVE 8/9; the parser treats any `<storage>:` volid uniformly). **Redteam-hardened
  2026-06-15:** `efidisk0`/`tpmstate0` are treated as **boot-critical** — if one is the only slot
  lost to the storage, the guest is classified *won't-boot* (UEFI / Secure-Boot / TPM-backed guests
  cannot boot without it), not merely *degraded*. Over-flag, never under-flag.
