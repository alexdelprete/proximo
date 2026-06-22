# Spec — Complete the half-built planes → total coverage

> Created 2026-06-14. Status: **approved, pre-implementation.**
> Branch: `extend/half-built-planes`. Author: brainstormed with the maintainer.

## Motivation

Proximo shipped 0.1.2 (PyPI + GitHub + GHCR) with **117 MCP tools**. The `ROADMAP.md`
(dated 2026-06-08/10) lists a "remaining ☐ coverage" set that is now **substantially stale** —
group/role/realm/user CRUD, ACL + token mutate, and storage create/delete/update all shipped
since it was written. Reconciling the *actual* 117-tool surface against Proxmox VE's full API
surface leaves four planes that are **half-built: read/list present, mutation CRUD missing.**

The project thesis is total coverage — *every operation Proxmox VE can perform, each mutating one
PLANNED, and PROVED.* Completing these four planes moves the half-built groups to ✅ and closes the
largest remaining structural gaps that are mechanically well-understood (vs. Ceph / APT / DR, which
are whole new planes deferred to later rounds).

## Goal

Bring the four half-built planes to **total CRUD coverage**, each new tool wearing the existing
trust substrate (PLAN + PROVE) by construction, built **test-first** and **adversarially redteamed**,
and — per the honesty correction below — **live-proven on the real node** where the operation is a
reversible config-object edit.

## Honesty correction: most of this round is live-provable, not mock-only

Initial framing assumed SDN/HA/firewall could only be mock-proven (no SDN/HA/cluster running on the
single pve-node). That is **too pessimistic**. SDN objects, firewall aliases/IP-sets/security-groups,
and HA groups are **config objects** (`/etc/pve/sdn/*`, `cluster.fw`, `/etc/pve/ha/groups.cfg`) — not
operations that require a running SDN controller, HA stack, or multi-node cluster. Their
create→read→delete is **additive and reversible with no connectivity effect** — the *same shape* as
the governance plane (ACL/role/user) the roadmap records as live-proven against the real PVE 9.2 API.

So this round can be **live-proven on the real node**. The single connectivity-touching operation,
`sdn_apply`, already exists and is **not** re-added here. Creating an SDN object leaves it *pending*
until apply; deleting the pending object reverts cleanly without ever touching the production network.

## Scope — ~26 new tools across four independent planes

Endpoint paths below are the **build-time grounding targets**, not assumptions to encode blindly.
Every path + param set is verified against the live API schema (`pvesh usage <path> --verbose` /
apidoc) **before** the tool is written. Nested sub-resources (IP-set CIDR entries, SDN subnets) are
container+children, not flat CRUD — highest mock-drift risk, grounded first.

### Firewall (~11) — `firewall.py`, scope-aware via `_fw_base` (cluster/node/guest)
- **Aliases:** `alias_list` (GET `…/firewall/aliases`), `alias_create` (POST), `alias_update`
  (PUT `…/aliases/{name}` — supports rename), `alias_delete` (DELETE `…/aliases/{name}`)
- **IP-sets:** `ipset_create` (POST `…/firewall/ipset` `{name, comment}`), `ipset_delete`
  (DELETE `…/ipset/{name}` `{force}`), `ipset_entry_add` (POST `…/ipset/{name}` `{cidr, nomatch, comment}`),
  `ipset_entry_remove` (DELETE `…/ipset/{name}/{cidr}`)
- **Security groups (cluster-only):** `security_group_create` (POST `/cluster/firewall/groups`),
  `security_group_delete` (DELETE `/cluster/firewall/groups/{group}`)
- **Options:** `firewall_options_set` (PUT `…/firewall/options`)

### SDN (~10) — `network.py`
- **Zones:** `sdn_zone_create` (POST `/cluster/sdn/zones`), `sdn_zone_update`
  (PUT `/cluster/sdn/zones/{zone}`), `sdn_zone_delete` (DELETE)
- **VNets:** `sdn_vnet_create` (POST `/cluster/sdn/vnets`), `sdn_vnet_update`
  (PUT `/cluster/sdn/vnets/{vnet}`), `sdn_vnet_delete` (DELETE)
- **Subnets:** `sdn_subnet_list` (GET `/cluster/sdn/vnets/{vnet}/subnets`), `sdn_subnet_create`
  (POST), `sdn_subnet_update` (PUT `…/subnets/{subnet}`), `sdn_subnet_delete` (DELETE)

### HA (~3) — `cluster_ops.py`
- **Groups:** `ha_group_create` (POST `/cluster/ha/groups`), `ha_group_update`
  (PUT `/cluster/ha/groups/{group}`), `ha_group_delete` (DELETE)
- Must handle the PVE 9 "HA groups migrated → HA rules" case the module already detects
  (`_is_ha_groups_migrated`): if groups are deprecated on the target, surface that honestly
  rather than 500-ing.

### TFA (~2) — `access_*`
- `tfa_get` (GET `/access/tfa/{userid}` or `…/{id}`), `tfa_delete` (DELETE `/access/tfa/{userid}/{id}`)
- **Out of scope (explicit):** TFA *enrollment* (TOTP/WebAuthn challenge→confirm dance) — interactive,
  not a clean admin one-shot.

### Out of scope this round
- TFA enrollment (above). `sdn_apply` re-add (already exists). New planes: Ceph, APT/updates,
  backup-schedules/replication, notifications — separate future rounds.
- Security-group *rule* management within a group (the group container CRUD is in scope; per-group
  rule CRUD reuses the scoped `firewall_rule_*` pattern and is a candidate follow-on, not this round).

## The pattern every tool wears (identical to existing modules)

Each mutation is a **pair**:
1. `do_x(api, …)` — input validation via existing `_check_*` helpers → single backend call → return
   dict/object. Pure op, no self-gating.
2. `plan_x(…) -> Plan` — the PLAN pillar: an honest dry-run preview surfacing scope + the exact change
   + risk level, *before* any mutation.

`server.py` wires each as an `@mcp.tool` with **confirm-gate + audit ledger** (the PROVE pillar) and
the "no plan → no mutation" rule.

**UNDO is honestly absent** for all four planes — their state lives in cluster config files, not guest
disk snapshots, so `_auto_undo`/snapshot rollback does **not** revert them. Tools never claim UNDO; the
documented revert is the **inverse op** (delete the alias, remove the entry, etc.). This mirrors the
existing firewall module's stated contract.

**Risk posture:** firewall/SDN/HA edits carry connectivity/lockout potential → RISK_MEDIUM floor with a
prominent note; `firewall_options_set` is RISK_HIGH when it changes the enable flag or default policy
(same reasoning as `firewall_set_enabled`). Optimistic-locking via the PVE `digest` is used on
update/delete where the endpoint surfaces one.

## Proving strategy

1. **Unit + redteam (every tool):** test-first against grounded mock responses; adversarial review pass
   (same discipline as planes 4–6). Lint clean (ruff).
2. **Live create→read→delete on the real node** for the config-object ops (firewall/HA-group/SDN-object).
   Uses **throwaway-named** objects (e.g. `proximo-smoke-*`). This touches **shared cluster config** →
   **YELLOW**: announced to the maintainer before running, not done silently.
3. **SDN pending-state check:** verify a *pending* SDN object can be created and deleted **without**
   forcing an apply against the production network (no `sdn_apply` in the smoke path).
4. Open question carried to live-smoke: does the nested test cluster from the governance-plane proving
   still exist? If yes, it's the cleanest live-prove target for everything; if not, throwaway objects on
   the real node cover firewall/HA/SDN-object CRUD safely.

## Execution shape

One spec → **four per-plane phases**, with a **checkpoint after each plane** (tests green + redteam +
live-prove or explicit defer). Recommended order by value + confidence:

1. **Firewall** — most universal, fully config-object live-provable, module gotchas already documented.
2. **HA groups** — tiny (3 tools), config-object live-provable.
3. **SDN** — biggest (10 tools); carries the pending/apply clean-state check.
4. **TFA** — tiny (2 tools); touches real user auth, done last and carefully.

## Success criteria

- All ~26 tools implemented, each with a `plan_*` pair, wired + confirm-gated + audited in `server.py`.
- Full test suite green (current 1960+), ruff clean.
- Adversarial redteam pass per plane.
- Config-object CRUD live-proven on the real node (or explicitly deferred with reason if the node is
  unavailable).
- `ROADMAP.md` / `LANDSCAPE.md` reconciled: the four planes flip half-built → ✅, and the stale
  "remaining ☐" claims are corrected.
