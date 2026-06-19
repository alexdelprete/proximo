# Spec: storage_update(nodes-restrict) blast-radius

- **Date:** 2026-06-19
- **Status:** SPEC (build pending).
- **Surface:** `blast.py` engine + `plan_storage_update` (storage_admin.py).

## Why

Restricting a storage definition's `nodes` list (the set of nodes the storage is available on)
**strands every guest on an excluded node from its disk(s) on that storage** — a won't-boot for
boot-disk/only-copy guests, degraded otherwise, and a live crash risk if running. Today
`plan_storage_update`'s `nodes` branch only emits a *generic string* ("guests on excluded nodes lose
access") — it does **not name the guests**. The `disable` branch already computes the cluster-wide
named impact; `nodes` is the last string-only storage footgun. This is the surgical sibling of the
shipped storage-*delete* class (`compute_storage_blast`), filtered by node.

## The graph (load-bearing)

A guest is **stranded** by restricting storage `S` to `new_nodes` iff it **has a disk on `S`** AND its
**current node ∉ `new_nodes`**.

- **No current-`nodes` read required.** A guest sitting on node X *with a disk config on S* proves S is
  currently available on X (PVE can't place a disk on a storage not available on the node). So "node ∉
  new_nodes" is sufficient to conclude stranding — we don't read the storage's existing `nodes`.
- **Over-flag is the safe direction.** If a guest were *already* stranded before the update (a
  pre-existing misconfig), we'd flag it as "loses access" when it already had none — harmless, and
  still true post-update. Consistent with "absence of HIGH is not a safety signal."
- Reuse `_classify_guest` verbatim (won't-boot / degraded / running classification + per-guest `node`).
  The only addition over `compute_storage_blast` is the `node ∉ new_nodes` filter and the framing.

### Edges

- **`nodes=""` (empty/omitted)** = PVE CLEARS the restriction → available on ALL nodes → a WIDENING
  that strands nobody. The *pure engine* still treats a literal empty node-set as "available nowhere →
  strand all" (correct math); the *wiring* (`plan_storage_update`) maps the PVE string `""` to its real
  "clear → widen" meaning and emits the widening line, NOT maximal stranding. (Smoke-confirm `nodes=''`
  clears vs empties on your PVE version.) — *corrected after redteam; the original spec had this edge
  backwards.*
- **Widening / no-op** (`new_nodes` ⊇ the guests' nodes): no guest's node is excluded → nobody
  stranded. The plan must then say "strands no guests on the new node set" and must NOT fall through
  to a generic "guests on excluded nodes lose access" line (the storage analog of "never state
  exposure as fact"). The change is still surfaced — it's connectivity config — just without a
  stranding claim.

### Soundness invariant + risk floor

- **No under-flag path.** `node ∈ new_nodes ⟹ storage stays available there ⟹ guest keeps access`.
  The only error direction is over-flag (safe). Test #2 (guest on an included node → NOT stranded) is
  the soundness gate, not just one case among seven.
- **`new_nodes` parsing is string-only** (split/strip the user value) — it never reads guest data, so
  no path can spuriously add a guest's node to `new_nodes` (the only way to flip to under-flag). A
  case/whitespace mismatch fails membership → over-flag (safe).
- **Risk floor = MEDIUM** even when nobody is stranded (a `nodes` restriction is connectivity-affecting
  config); escalate to HIGH on any stranded won't-boot entry or incomplete enumeration, never lower.
- **Incomplete enumeration** (cluster read or a guest config read failed): reuse the storage-blast
  honesty contract — loud `⚠ INCOMPLETE`, `max_severity='high'`, `complete=False`, never "safe."

## What gets built

- **NEW** `blast.compute_storage_nodes_blast(storage, new_nodes: set[str], guests, configs, complete)
  -> BlastResult` — pure; mirrors `compute_storage_blast` with the node filter + stranding framing.
- **Wire** `plan_storage_update`: when `nodes` is set (and `disable` is not True — disable dominates,
  it's cluster-wide), parse `new_nodes`, `gather_storage_dependents`, compute, populate `affected`,
  escalate risk (HIGH on stranded/incomplete, never lower), set `complete`. Keep the generic floor
  lines; PREPEND the computed named set (mirrors the delete/disable pattern).
- **Fix** the stale `plan_storage_update` docstring ("PURE — no API call" is false; it reads the
  cluster for disable, and now for nodes).

## Framing (never overclaim)

Per-guest, never "the storage is broken." E.g.:
`restricting storage 'S' to nodes [pve2] strands 3 guest(s) on excluded nodes: lxc/104 (web) on pve1:
will NOT boot — boot disk rootfs is on this storage …`. The `disable`-vs-`nodes` distinction stays
honest: nodes-restrict strands only the excluded-node guests; disable cuts everyone.

## Test plan (TDD)

1. Guest on an excluded node with a boot disk on S → stranded, severity high (won't boot).
2. Guest on an *included* node (∈ new_nodes) with a disk on S → NOT stranded (keeps access).
3. Empty `new_nodes` → all disk-on-S guests stranded.
4. Widening (all guest nodes ∈ new_nodes) → none stranded, max_severity none.
5. Incomplete enumeration → `complete=False`, `max_severity='high'`, loud INCOMPLETE, sentinel entry.
6. Running guest on excluded node → "RUNNING: losing the disk live may crash" surfaced.
7. `plan_storage_update(nodes=...)` wiring: names the stranded guests, escalates risk, sets affected;
   `disable=True` still dominates (cluster-wide).

## Build discipline

spec → TDD (failing test first) → 3-lens redteam (correctness: node-filter / over-under-flag; honesty:
complete + never-safe; leak) → full suite + ruff + pyright.
