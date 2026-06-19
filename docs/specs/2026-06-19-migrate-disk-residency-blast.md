# Spec — guest-migrate disk-residency blast (coverage op-class #8, rank 3)

## Context & honest framing
From the 2026-06-19 coverage audit (rank 3). `plan_migrate` reads only `guest_status` and warns
generically "requires shared storage"; it never reads the guest's disks to compute whether they can
actually move to the target node. Unlike the other blast classes, the harm here is primarily to the
GUEST being migrated (its disks strand / the migrate fails) — this is migration **feasibility**, closer
to pre-flight validation than cross-resource naming. Still a real, high-value gap: local-disk migrations
fail constantly in practice, and telling the operator up front is exactly the consequence-awareness goal.

## The graph
Migrating guest G to target node B: for each of G's data disks on storage S —
- S `shared=1` AND available on B (no `nodes` restriction, or B ∈ `nodes`) → clean migrate, NO copy.
- S `shared=0` (local-lvm/dir/zfs-local) → the disk is physically on the SOURCE node; migration must
  COPY it (needs `with-local-disks`); a plain migrate FAILS for local disks, and a LIVE (online qemu)
  migration is NOT possible with local disks.
- S `nodes`-restricted with B ∉ `nodes` → S is not available on B → migration cannot place the disk → FAILS.

## `compute_migrate_blast` — pure engine (blast.py)
Inputs (fetched): `target`, `disk_slots: {slot: storage}` (from `_disk_slots`), `storage_meta:
{storage: {"shared": bool, "nodes": set[str] | None}}` (a storage absent from the map → metadata
unreadable), `config_complete: bool` (guest config readable), `online: bool`, `kind: str`.

### Soundness invariant (no under-flag)
- Missing storage metadata → state "unknown" → flagged + `complete=False`, NEVER assumed migratable.
- `config_complete=False` → loud INCOMPLETE, forced HIGH, sentinel — disks can't be enumerated, never "safe".
- A disk is OK (not flagged) ONLY when its storage is provably shared AND available on the target. Anything
  else (local, unavailable, unknown) is flagged. Over-flag direction only.

### Verdict
- any flagged disk (unavailable / local / unknown) OR not config_complete → `max_severity="high"`
  (a forced/failed/copy migration). All disks shared+available → `max_severity="none"` (clean; the op's
  base downtime risk still stands — the engine only escalates).
- LIVE (online qemu) + a local disk → the "MEDIUM live migration" is actually impossible → escalation to
  HIGH is the key catch (a generic "requires shared storage" never said WHICH disk blocks it).

### gather_migrate_dependents(api, vmid, kind, node, target)
I/O, fail-closed: read guest config → `disk_slots` + `config_complete`; `storage_config_list` →
`storage_meta` ({shared bool, nodes set|None}); read failure → empty meta (→ all unknown) / config_complete False.

## Wiring — plan_migrate
Run the engine ONLY when the guest is confirmed to exist (status read succeeded, not 404 / not check_failed
— those paths already say "will FAIL / state unknown"). Append summary_lines to blast, set Plan.affected/
complete, escalate risk via `_max_risk`. Base risk (MEDIUM live-qemu / HIGH else) is never lowered.

## Build discipline
TDD (failing test first) → 2-lens redteam (soundness / under-flag + honesty / leak) → full suite +
ruff + pyright.

## Deferred (logged)
- Target-node CAPACITY / co-tenant pressure from copying a local disk to B (overlaps the disk-move engine;
  needs target-storage resolution, which `plan_migrate` does not expose) — out of v1.
