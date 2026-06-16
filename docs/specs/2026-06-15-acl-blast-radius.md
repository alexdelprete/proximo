# Spec — Blast-radius engine (access/ACL class)

> Created 2026-06-15. Status: **pre-implementation, awaiting maintainer review.**
> Branch: `feat/acl-blast-radius`. Author: brainstormed with the maintainer.
> Prior op-class: `docs/specs/2026-06-15-blast-radius-engine.md` (storage/disk — shipped to `main`).

## Motivation

The blast-radius thesis — *name the specific downstream impact of a dangerous op, in-band* — landed
its first op-class (storage/disk) and the moat sharpened. The ROADMAP (§H) names the access plane as
the flagship example: *"an access tool that PLANs an ACL change — showing what it shadows, what it
widens, who it affects."*

Unlike storage, this is **surgical, not greenfield.** `plan_acl_modify(api, …)` is already a mature
blast-radius computation: it reads the current ACL, computes **SHADOW** (inherited roles lost when a
specific-path entry replaces an ancestor's *propagated* grant — the notorious PVE gotcha), **WIDEN**
(roles restored on revoke), fails closed on read error (`RISK_HIGH`, "absence of a warning is not a
safety signal"), and escalates on Administrator / root paths. The killer feature is largely built.

It stops in two specific places, which this op-class closes:
1. **All analysis lives in `blast_radius` strings** — it does not populate the structured
   `affected: list[dict]` field the storage class established.
2. **The group blind spot is acknowledged but not resolved.** The current scan matches `ugid ==
   target` only, so it misses the rights the target inherits *via their own group memberships* — it
   emits *"UNCERTAINTY: group-type ACL entries exist … analysis may be INCOMPLETE for group
   members"* but never resolves it.

## The per-principal correction (the load-bearing honesty constraint)

`acl_modify`'s `kind` is **`user` or `token` only — never a group** (access.py:258-259, 382-383). PVE
computes a principal's effective rights as *(their direct ACLs) ∪ (ACLs of groups they belong to) ∪
(propagated ancestor ACLs)*. Modifying `bob@pam`'s entry touches **only the "bob's direct" term** —
`alice@pam`'s rights are computed without ever referencing bob's entry.

Therefore *"this revoke also removes access for alice (via group ops)"* is **factually false** and must
never be emitted. "Resolve the group blind spot" decomposes into two distinct things — the spec keeps
them rigorously separate:

- **#1 (rigorous — the real gap): complete the TARGET's own shadow/widen.** Fold the target's
  group-inherited grants into `inherited_roles`. The principals NAMED here are *the groups the target
  inherits through* ("also shadows PVEVMAdmin inherited via group 'ops' at /"), not other members.
  Only **gains/loses** verbs, only ever about the target.
- **#2 (valid, but CONTEXT — never gains/loses): who-else-can-reach.** List the members of group-type
  ACL entries at/above the path, labeled strictly **"also has access here — UNCHANGED by this
  change."** Useful blast context; the verb is always *unchanged*.

## Goal

Bring `pve_acl_modify`'s preview to the established blast-radius contract: extract the shadow/widen
reasoning into a **pure `compute_acl_blast(...)`** in `blast.py`, populate the structured
`affected: list[dict]`, **complete** the target's shadow via group-membership resolution (#1), and add
**who-else-can-reach** context (#2) — all under the per-principal honesty constraint above and the
existing fail-closed discipline. Computed blast-radius continues to flow into the PROVE ledger.

## v1 scope

- **In:** `pve_acl_modify` only (grant + revoke; `kind=user` and `kind=token`).
- **Out (already have their own affected-set plans):** `plan_user_delete`, `plan_group_delete`,
  `plan_role_*`, `plan_realm_*`, `plan_token_*`. Not retrofitted here.
- **Out (deferred):** resource enumeration (naming which cluster resources a path covers — a different
  dimension); firewall/network exposure (the next op-class).

## Architecture — extract pure engine + I/O in the plan factory (mirrors storage)

```
access.py  plan_acl_modify(api, ...)            blast.py
──────────────────────────────────              ────────
1. gather (each read fail-closed):              compute_acl_blast(
     acl = access_acl_list(api)                   path, roles, target, kind, delete,
     #1 target_groups = user_get(target).groups   acl_entries,           # current ACL
        (kind=user, or token owner if privsep=0)   target_groups,         # list | None (unread/N/A)
     #2 group_members = {g: group_get(g).members  group_members,         # {group: [members]} | partial
         for g in group_entries_at_or_above(path)} token_privsep,         # True|False|None (token only)
     token_privsep = <read for kind=token>      ) -> AclBlastResult
2. result = compute_acl_blast(...)  # PURE         .affected: list[dict]
3. return Plan(blast_radius=result.lines,          .summary_lines: list[str]
        affected=result.affected,                  .risk / .risk_reasons   (escalate, never lower)
        risk=result.risk, ...)                     .complete: bool         (group dims resolved?)
```

- **`compute_acl_blast` is pure** — it receives already-fetched ACL entries + resolved group data and
  returns the structured result. Fully unit-testable with fabricated ACL lists. It subsumes the
  existing inline shadow/widen logic (behavior preserved) and adds #1 fold-in + #2 context + structured
  `affected`.
- **`plan_acl_modify` does the I/O** and is the only place that touches `api` — gathering acl_list,
  the target's groups (#1), and group members (#2), then delegating. This matches the existing
  `plan_acl_modify(api, …)` / `plan_group_delete(api, …)` house idiom.

## Reads + fail-closed honesty

Each read is independently fail-closed; a failure degrades **toward caution**, never toward a clean
"no impact":

- **acl_list fails** → existing behavior unchanged: `RISK_HIGH`, "cannot determine shadow/widen;
  absence of a warning is not a safety signal."
- **#1 `user_get(target)` fails** (or the per-group ancestor scan can't complete) → the target's
  shadow analysis is marked **incomplete**: keep the *"shadow/widen may be incomplete for group-
  inherited grants"* caveat, do **not** claim completeness, keep risk at its escalated floor. The
  caveat is dropped **only** when group resolution succeeds.
- **#2 `group_get(group)` fails** for an in-scope group → emit *"could not enumerate members of group
  'ops' — who-else-can-reach is incomplete"* (never a silent empty list). Does not lower risk.
- **privsep token:** for `kind=token`, read the token's privsep via `access_tokens_list(owner)`. A
  privsep=0 token **IS** the owner, so fold in the owner's **groups AND the owner's own DIRECT
  propagated grants** (`extra_inherited`) — a redteam pass caught that folding only the owner's
  *groups* silently missed a shadow when the owner held a direct user grant at an ancestor (the
  cardinal under-flag). For **privsep=1**, fold nothing (the token has only its own ACLs) and stay
  honest (the caveat fires when group entries are in scope). If privsep is unreadable → default to
  privsep=1 (no fold), do not claim "complete."

The engine **never lowers** the risk the existing logic assigns; it may only raise (consistent with the
storage class and the module's creed).

## Output contract — structured `affected` + preserved strings

`Plan.affected` (the additive field shipped with the storage class) is populated; the existing
`blast_radius` strings and risk escalations are **preserved** (the engine output augments, never
replaces). `affected` entry shape — principal-centric, honest verb:

```python
{
  "principal": "bob@pam",            # the target, a group the target inherits through, or a who-else member
  "kind": "user" | "token" | "group" | "group-member",
  "via": "direct"                    # the target's own direct entry at path
        | "inherited:/ (group ops)"  # #1: target inherits via a group at an ancestor path
        | "group ops",               # #2: a member reachable via this group at/above path
  "change": "loses" | "gains"        # ONLY for the target (the only principal whose access changes)
          | "unchanged",             # ONLY for #2 who-else context — NEVER gains/loses
  "roles": ["PVEVMAdmin"],
  "at": "/vms/100",
  "severity": "high" | "medium" | "unknown",
}
```

`Plan.as_dict()` already serializes `affected`; `_record_plan` already writes it to the ledger (both
shipped with the storage class — no change needed). `pve_acl_modify` is **not** in the A2A slice
(EXCLUDED-class governance op; MCP-only), so `affected` surfaces via the MCP response + the PROVE
ledger, not A2A — same honest scope as storage.

## Files

- **Edit:** `src/proximo/blast.py` — add `compute_acl_blast(...)` (PURE) + dedicated `AclBlastEntry`
  /`AclBlastResult` (the ACL `affected` shape — principal/kind/via/change/roles — differs from storage's
  resource/via/effect/only_copy, so it is its own type, not a reuse) + the shadow/widen reasoning (moved
  from access.py) + #1 group fold-in + #2 who-else assembly. No new `api` import needed (pure).
- **Edit:** `src/proximo/access.py` — `plan_acl_modify` gathers the reads (acl_list, `user_get`,
  `group_get`, token privsep), calls `blast.compute_acl_blast`, builds the `Plan` (blast_radius +
  affected + risk). Reads `user_get`/`group_get` imported from `access_users`.
- **New:** `tests/test_blast_acl.py` — pure-engine unit tests.
- **Edit:** `tests/test_access.py` (or wherever `plan_acl_modify` is tested) — update the existing
  shadow/widen assertions for the refactor (behavior preserved) + assert structured `affected`.
- **New:** `scripts/live-smoke/acl-blast-smoke.py` — read-only (PLAN-only) ACL blast check.

> Watch for an import cycle: `blast.py` would import `user_get`/`group_get`? No — those reads stay in
> `plan_acl_modify` (access.py); the pure engine receives already-fetched data. `access.py` imports
> `blast` (it already imports `planning`). `blast` imports `cluster_ops`/`config_edit` (storage class)
> — neither imports `access`. No cycle. (Confirm with the suite run.)

## Testing (TDD throughout)

Pure-engine unit tests (`compute_acl_blast`, zero API):
- **preserved:** grant that shadows an inherited role → SHADOW warning + `RISK_HIGH`; revoke that
  restores an inherited role → WIDEN warning + `RISK_HIGH`; Administrator/root escalation; additive
  grant (no shadow) → MEDIUM.
- **#1 group fold-in:** target inherits `PVEVMAdmin` via group `ops` at `/`; a new direct entry at
  `/vms/100` shadows it → SHADOW now names the group-inherited role; caveat dropped (resolution
  succeeded); `affected` carries the target's `loses` entry with `via: inherited:/ (group ops)`.
- **#1 incomplete:** `target_groups=None` (user_get failed) → caveat RETAINED, not "complete",
  risk unchanged.
- **#2 who-else:** group `ops` has a grant at `/vms` with members `[bob, alice]`; editing `/vms/100`
  → `affected` carries bob/alice as `kind: group-member, change: unchanged, via: group ops`; strings
  say "UNCHANGED"; no gains/loses verb on them.
- **#2 incomplete:** `group_members` missing a group (group_get failed) → "could not enumerate members
  of 'ops'" line; never a silent empty list.
- **privsep token:** `kind=token`, privsep=1 → no fold-in + caveat stays; privsep=0 → owner groups
  AND owner direct propagated grants folded (shadow names them); privsep unread → default privsep=1,
  not "complete".
- **`complete` boolean propagates to the `Plan`** (added to `Plan` + `as_dict` + the PROVE ledger
  detail) so the incompleteness signal is machine-checkable, not only a `blast_radius` string — a
  downstream gate can refuse to auto-confirm when `complete=False`. (Both ACL and storage classes.)

I/O / seam tests (fake api, mirrors `test_blast_seam.py` / `test_server_round3_wiring`):
- `pve_acl_modify` dry-run with a group-inheriting target → `resp["affected"]` names the target's
  loss + who-else members; ledger `planned` entry carries `affected`.
- a `user_get`/`group_get` raise → plan still returns, caveat present, risk not lowered.

Full suite stays green (currently 2156); ruff + `pyright` (src-scoped) clean. Independent 3-lens
adversarial redteam before "done" (correctness/under-flag · honesty/false-gains-loses · leak), then a
read-only live ACL-blast smoke on x3650.

## Non-goals / explicitly deferred

- Resource enumeration (which resources a path covers) — different dimension, later.
- Retrofitting the other access plans (user/group/role/realm/token) to the structured `affected` field.
- firewall/network exposure blast-radius — the next op-class.
- Any change to `acl_modify` (the mutation) — this is PLAN-only enrichment.

## Open / smoke-confirm

- Confirm PVE returns group membership at `GET /access/users/{userid}` as `.groups` (list) and group
  members at `GET /access/groups/{groupid}` as `.members` (list) on the target version (the existing
  `plan_user_delete`/`plan_group_delete` rely on these; reuse, don't re-verify blindly).
- Confirm the token privsep flag is readable via `GET /access/users/{owner}/token` (`access_tokens_list`)
  per-token; confirm its key name (`privsep`, 1/0).
- Confirm PVE's exact precedence when a user has BOTH a direct entry at a path AND a group-inherited
  grant at an ancestor — the spec assumes the most-specific-path direct entry shadows ancestor
  propagation (incl. group-propagated); verify at live smoke and keep the conservative disclosure where
  precedence is uncertain.
