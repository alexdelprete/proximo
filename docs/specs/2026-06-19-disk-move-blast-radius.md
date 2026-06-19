# Spec — disk-move blast-radius (+ coverage push)

## Context
Blast-radius coverage audit (2026-06-19) classified Proximo's 86 mutating tools: 11 COVERED,
~51 N/A (single-resource, no cross-resource graph), ~10–12 substantive GAPs. `pve_disk_move` is
the #1 gap — it currently reads only the *source* storage and rates risk solely on `delete_source`;
it computes **nothing** about the target. This spec closes it, and frames the broader push.

## The disk-move cross-resource graph
Moving disk D (provisioned size `SZ`) from its source onto **target storage T** can:
1. **Exhaust T's capacity** → every guest with a disk on T (the *co-tenants*) is at risk of
   allocation/write failure. ← the genuine cross-resource blast.
2. **Fail to fit** (SZ ≥ T's free space) → the move errors or fills T.
3. (validity, later cycle) target T may not support the guest's content type (`images` for qemu,
   `rootdir` for lxc), or may be node-restricted off the guest's node.

## `compute_disk_move_blast` — pure engine (blast.py)
Inputs (already-fetched, no I/O): `target_storage`, `disk_size_bytes` (provisioned, worst-case;
None=unknown), `target_avail`/`target_total` bytes (None=unreadable), `moved_resource` ("qemu/100",
excluded from co-tenants), cluster `guests`+`configs`, `complete`.

### Soundness invariant (load-bearing — no under-flag)
- **Fit check uses PROVISIONED size** (not thin/actual usage) = worst case. So "won't fit / fills T"
  can only OVER-flag (a thin disk that wouldn't really need full size), never under-flag. ✓
- **Co-tenants = every guest with a data disk on T** (reuse `_disk_slots`/`_storage_of_volid`),
  excluding the guest being moved. A config read failure → `complete=False` → forced HIGH. ✓
- **Capacity-unknown is never "safe":** if `disk_size_bytes` or `target_avail` is None, the engine
  cannot assess fit → forces `max_severity=high` + a loud "could not assess target capacity" line.

### Verdict ladder (engine ESCALATES risk, never lowers — base plan risk stays)
- capacity unknown (size or avail None) → **high**, loud line, no "safe" claim.
- `SZ ≥ avail` → **WON'T FIT / fills T** → **high**; name co-tenants (high).
- post-move free `(avail − SZ) < 10% of total` → **TIGHT** → **medium**; name co-tenants (medium).
- fits comfortably → **none**; informational line ("T has X free; disk Y; N co-tenants share T but
  ample headroom"). Co-tenants NOT flagged as affected — **cry-wolf control** (mirrors the
  storage-nodes "no guests stranded" path: state safety without scare lines).
- `complete=False` (guest enum incomplete) → loud `⚠ INCOMPLETE`, force high, append `unknown` sentinel.

`_DISK_MOVE_TIGHT_FRACTION = 0.10`.

### gather_disk_move_dependents(api, target_storage, vmid, disk, kind, node)
I/O, fail-closed (never raises): reads (a) the moved guest's config → provisioned size of `disk`;
(b) `storage_status(target_storage, node)` → avail/total; (c) cluster guests + configs (reuse
`gather_storage_dependents`). Any failed read → that input None / `complete=False`.

## Wiring — plan_disk_move (disk_ops.py)
Call `disk_move_blast(...)`, populate `Plan.affected` (co-tenant dicts) + `Plan.complete`, append
the engine `summary_lines` to `blast_radius`, and `_max_risk(base_risk, engine_severity)` so a
won't-fit/tight target escalates a retain-MEDIUM move. Keep the existing source/delete_source lines.

## Build discipline
TDD (failing test first) → 3-lens redteam (correctness / honesty: complete + never-safe / leak) →
full suite + ruff + pyright. Live read-only smoke on a real cluster where reachable.

## Coverage push order (ranks from the audit — do 1–9; thin platform-guarded ones are lower)
1. **disk_move** (this spec) · 2. firewall_set_enabled + firewall_options_set (cluster lockout) ·
3. guest_migrate (local-disk strand) · 4. network_iface_update/create (bridge/bond breaks guests) ·
5. pool_delete (zero reads today) · 6. group_delete (finish ACL enumeration) ·
7. role_update / realm_update (symmetric with their delete siblings) ·
8. backup_delete / pbs_namespace_delete / pbs_prune (last-copy / bulk-unnamed) ·
9. storage_content_delete (in-use disk-image scan). Thin tier (SDN/HA/ipset/sg/alias deletes,
   sdn_apply) lean on PVE referential-integrity refusal → lower priority, log if deferred.
