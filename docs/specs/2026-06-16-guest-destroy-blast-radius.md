# Spec — Blast-radius engine (guest-destroy class)

> Created 2026-06-16. Status: **pre-implementation, awaiting maintainer review.**
> Branch: `feat/guest-destroy-blast-radius`. Author: brainstormed with the maintainer (advisor-reviewed).
> Prior op-classes (shipped to `main`, v0.3.0): storage/disk (`docs/specs/2026-06-15-blast-radius-engine.md`),
> access/ACL (`docs/specs/2026-06-15-acl-blast-radius.md`), firewall/network
> (`docs/specs/2026-06-15-firewall-network-blast-radius.md`).

## Motivation

The fourth blast-radius op-class, and the one aimed at the platform's single most destructive button:
**permanently destroying a guest.** The headline: *"destroying ct/200 will refuse — it has protection
set"* and *"destroying vm/9000 orphans 1 HA resource and 1 replication job (purge is off, so they will
be left dangling)."*

`plan_delete` (in `provisioning.py`, wired to `pve_delete_guest`) today is honest but **shallow**: it
reads `guest_status`, names the guest (`name`, `status`), and returns `RISK_HIGH` unconditionally with
a not-found / could-not-verify ladder. It does **not** enumerate the cascade — what *else* in the
cluster references this guest, what PVE will refuse, or how the `purge`/`force` flags change the
outcome. That cascade is the unbuilt, differentiated capability (competitors are resource-blind).

## The load-bearing framing — OUTCOME IS CONDITIONAL ON `purge` AND `force` (advisor-caught)

The other three classes describe what depends on a *resource*. This class describes **what destroying
a *guest* actually does** — and that is **not** a property of the guest alone. It is conditional on two
arguments the caller already passes to `pve_delete_guest` / `plan_delete`:

- **`purge`** (PVE: *"also removes the guest from backup jobs, HA, and replication config"*). This
  **inverts** the reference category:
  - `purge=False` (default) → those references are **left dangling** → "clean up manually" warning.
  - `purge=True` → PVE **actively removes** them → the honest phrasing is "will be cleaned up", **not**
    "will be orphaned."
- **`force`** (PVE: *"attempt deletion even if the guest is running"*). It overrides the **running**
  guard **only** — it does **not** override `protection=1` or template-with-linked-clones.

**Hard framing constraint:** a PLAN/honesty tool MUST NEVER assert the opposite of what will happen.
Every reference-category line and `affected` entry MUST be phrased conditionally on the *actual
argument values for this call*. With `purge=True`, the engine MUST NOT say "orphaned"; with
`force=True`, it MUST NOT say "PVE will refuse because the guest is running." This is the same family
of correction as storage's "cluster-wide or you undercount" and firewall's "per-rule reach, not
cluster exposure." It is a framing constraint on the wording, carried by passing `purge`/`force` into
the pure compute function — not a scope decision.

## v1 scope

The pure engine `compute_guest_destroy_blast(...)` wired into `plan_delete`, preserving the existing
existence / not-found / check-failed ladder. `RISK_HIGH` stays unconditional (destruction is
irreversible regardless of what the cascade finds; the cascade only **enriches** the affected set and
adds risk reasons — it never lowers risk). Three outcome categories:

### 1. WON'T PROCEED — PVE will refuse (the flagship value)

`force` does **not** override the first two; it overrides only the third.

- **Template with linked clones.** If the target guest is a template (`template: 1` in its config),
  scan every other guest config cluster-wide for a disk volume whose name backs onto this template
  (`base-<vmid>-disk-N` / `vm-<clone>-disk-N` chained to `base-<vmid>`). Any match → PVE refuses the
  destroy (and a forced raw removal would corrupt those clones). Name the dependent clones.
- **`protection=1`.** A one-field read in the config we already fetch. PVE refuses to destroy a
  protected guest; `force` does **not** bypass it (the operator must unset `protection` first).
- **Running + `force=False`.** From `guest_status.status == "running"`. PVE refuses to destroy a
  running guest without `force`. **Conditional:** with `force=True` this flips to "will proceed
  (force overrides the running guard)" — it is NOT a won't-proceed entry in that case.

### 2. REFERENCES — conditional on `purge`

For each reference found, the entry states the *consequence under the call's actual `purge` value*:

- **HA resource** — `/cluster/ha/resources` entry whose `sid` is `vm:<vmid>` or `ct:<vmid>`.
- **Replication job** — `/cluster/replication` job whose `id` is `<vmid>-N`.
- **Backup-job membership** — `/cluster/backup` jobs. Resolve per selection mode: `all=1` (covered
  unless in the exclude list); `pool=X` (covered iff target is a member of that pool AND not excluded
  — incomplete only if pool data was unreadable); explicit `vmid` list (direct membership). Only a
  truly unrecognizable selection (e.g. `all=0` with no pool and no vmid) stays `complete=False`. This
  refinement was driven by the live dogfood: the most common real-cluster config (`all=1, exclude=…`)
  was previously flagged incomplete on every destroy plan. *(v1 flagged all three non-explicit modes
  incomplete; tightened after live smoke 2026-06-16.)*

`purge=False` → effect = "left dangling (PVE will not clean this up); remove manually." `purge=True` →
effect = "PVE will remove this reference as part of the purge."

### 3. INFORMATIONAL — intrinsic to the destroy

Expected consequences, not warnings; named so the operator sees the full footprint:

- **Disks freed** + their storages, from the guest's own config disk slots.
- **Snapshots removed** — count from `snapshot_list` (destroyed with the guest).
- **Pool membership** — the pool the guest belongs to (from the `cluster_resources` row); destroying
  removes it from that pool.

## Honesty contract (established pattern)

- Any unreadable edge → a loud `⚠ INCOMPLETE` first summary line, `complete=False` on the result, and
  the specific edge named. Risk is **never** lowered on incompleteness.
- **Zero-found is never read as safe.** "No HA resources reference this guest" is only stated when the
  HA read *succeeded*; a failed read says "could not determine HA references," not "none."
- The guest's own config returning empty/null (HTTP 200 `{"data": null}`) = a **failed** read of that
  guest's disks/flags → `complete=False`, never "no disks → nothing lost."
- Backup-job coverage is resolved per mode: `all=1` (covered unless excluded), `pool=X` (covered iff
  in that pool — incomplete only if pool data unreadable), explicit `vmid` list (direct). Only a
  truly unrecognizable selection → `complete=False` with a named explanation. The common real-cluster
  `all=1, exclude=…` config is now resolved rather than flagged incomplete.
- The pure compute function NEVER does I/O and NEVER raises; the I/O `gather_guest_dependents` catches
  per-edge failures, returns partial data + a per-edge completeness map, and NEVER raises (the plan
  must always build).

## Output contract

Mirrors `FirewallReachResult` (most recent class):

```python
@dataclass(frozen=True)
class GuestDestroyBlastResult:
    summary_lines: list[str]      # human-readable, each conditional on purge/force
    affected: list[dict]          # structured; see entry shape below
    risk: str                     # always RISK_HIGH for destroy; only ever raised
    risk_reasons: list[str]       # e.g. "would be REFUSED: protection=1"
    complete: bool = True
```

Each `affected` entry is a dict:

```python
{
  "category": "wont_proceed" | "reference" | "informational",
  "kind": "template_clones" | "protection" | "running" | "ha" | "replication"
          | "backup_job" | "disk" | "snapshots" | "pool",
  "ref": "<sid / job-id / volid / poolid / clone vmid>",   # the referencing thing
  "effect": "<consequence phrased for THIS call's purge/force>",
  "severity": "high" | "info" | "unknown",
}
```

`plan_delete` copies `affected` → `Plan.affected`, ANDs `complete` → `Plan.complete`, and folds
`summary_lines` / `risk_reasons` into the existing plan blast strings. A standing framing disclaimer
string (analogous to `_REACH_DISCLAIMER`) is carried on every result, stating that the cascade is
computed at PLAN time against the cluster as currently read and that effects are shown for the
`purge`/`force` values of this specific call.

## Files

- `src/proximo/blast.py` — add `GuestDestroyBlastResult`, the disclaimer constant, pure
  `compute_guest_destroy_blast(vmid, kind, purge, force, guest_config, status, ha_resources,
  replication_jobs, backup_jobs, pools, snapshots, clone_configs)`, and I/O
  `gather_guest_dependents(api, vmid, kind, node)` + a thin `guest_destroy_blast(api, ...)` wrapper.
  (No package split — see Non-goals.)
- `src/proximo/provisioning.py` — `plan_delete` calls the gather+compute, populates `Plan.affected` /
  `Plan.complete`, keeps the existence/not-found/check-failed ladder.
- Reuse existing readers: `cluster_resources`, `guest_config_get`, `ha_resources_list`,
  `pools_list`, `snapshot_list`, and `api._get` for `/cluster/replication` + `/cluster/backup`.
- `tests/test_blast_guest_destroy.py` (pure unit + adversarial/redteam cases folded in) + seam
  coverage in the existing `plan_delete` (`tests/test_provisioning.py`) / server-wiring
  (`tests/test_server_plan.py`) tests.

## Testing (TDD)

Write the failing test first for each branch, then the implementation:

- **Won't-proceed × force:** template-with-clones (force irrelevant); `protection=1` (force
  irrelevant); running + `force=False` (refuse) vs running + `force=True` (proceeds, NOT a refusal).
- **References × purge:** HA / replication / backup-explicit-vmid each under `purge=False` (dangling)
  and `purge=True` (cleaned up) — assert the effect wording flips and never states the opposite.
- **Informational:** disks + storages named; snapshot count; pool membership.
- **Incompleteness:** each reader failing in isolation → `complete=False` + that edge named, risk not
  lowered; empty guest config → failed-read path; backup unrecognizable selection → edge incomplete.
- **Pure-function guarantees:** `compute_*` does no I/O and raises on no input; `gather_*` never raises
  even when every reader throws.
- Then a **3-lens adversarial redteam** (correctness / honesty / leak), fixes test-first.
- Then a **live read-only smoke** on a throwaway guest where the environment allows (assert the
  function-level branches that the live cluster can actually exercise; unit-cover the rest) — dogfood
  the published path, don't round "unit-green" up to "works."

## Sequencing

1. Result dataclass + disclaimer + pure `compute_guest_destroy_blast` (won't-proceed branches first,
   then references, then informational) — all unit-tested.
2. I/O `gather_guest_dependents` + wrapper (fail-closed, per-edge completeness).
3. Wire into `plan_delete`; seam test through the server response + PROVE ledger.
4. Redteam → fixes. 5. Live read-only smoke. 6. CHANGELOG `[Unreleased]`; merge to `main`.

## Non-goals / deferred

- **Firewall cross-references by IP.** Rules reference IPs / aliases / ipsets, not vmids; attributing
  them to a guest needs IP resolution (DHCP, multi-NIC) + a full ordered-ruleset scan — low confidence,
  high cost. Deferred with a noted limitation. The guest's **own** firewall config is destroyed with
  it (informational, not separately enumerated in v1).
- **Backup `all`/`pool`/`exclude` membership resolution.** ~~Flagged incomplete in v1~~ — resolved
  after live dogfood (2026-06-16): `all` and `pool` modes are now computed (pool uses the same
  `inp.pools` data already gathered for the informational path; incomplete only when that read
  failed). Only truly unrecognizable selection stays incomplete.
- **Splitting `blast.py` into a package.** Adding this class pushes it to ~975 lines, but the classes
  are independent functions; a package split touches imports cluster-wide and is a separate change.
- **Services the guest provides** (it hosts a DB others depend on, holds a service IP) — not
  API-discoverable; out of scope.

## Smoke results (read-only, live cluster, 2026-06-16)

Ran the branch engine read-only against the real cluster (dry-run; no mutation). Confirmed:

- **`/cluster/backup` field names** — live job carries `{id, type, storage, schedule, enabled, all,
  exclude, ...}`. The engine reads `all` / `pool` / `exclude` / `vmid` correctly. This smoke is what
  surfaced the `all=1, exclude=…` resolution gap (now fixed — see §2 References).
- **`/cluster/replication`** returns `[]` on this cluster → the `or []` normalization holds (no
  false-incomplete).
- **Pool membership** fires end-to-end (`pool_get` resolves members; the summary `/pools` carries
  none — confirming the earlier dead-`members` finding was real).
- **Run-state gating** verified live: a running guest with `force=false` → `wont_proceed/running`;
  with `force=true` → no refusal.
- **Backup coverage** verified live: an excluded guest → resolved *not covered* (no false-incomplete);
  a covered guest → a real purge-conditional `backup_job` reference.

Not exercisable on this cluster (unit-tested only, honestly noted): HA resources (`/cluster/ha/resources`
is empty), replication references (no jobs), and the template-with-linked-clones branch (no template in
the fleet). The linked-clone backing-volume naming (`base-<vmid>-disk-N`) remains validated by unit tests
against documented PVE naming; a future cluster with a template + clones should re-confirm it live.
