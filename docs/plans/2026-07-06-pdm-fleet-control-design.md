# PDM Fleet Control — Increment 1 (design + build plan)

> **Date:** 2026-07-06 · **Status:** approved (John, "do it right") · **Branch:** `feat/pdm-fleet-control`
> **Context:** the 2026-07-06 coverage audit found PDM is Proximo's thinnest surface — 22 tools,
> all read-only (6.7% of 327 addressable ops). No competitor exposes *any* PDM surface. A *governed*
> PDM write plane is uncontested ground. This increment turns PDM from a dashboard into a control point.

## Goal

Add the **guest-lifecycle mutation plane** to PDM, driven through PDM's own flat remote proxy, every
operation carrying the Proximo trust spine (PLAN dry-run · PROVE ledger · UNDO where a primitive exists),
fail-closed and dry-run-by-default — exactly like the PVE guest plane. Result: PDM 22 → ~34 tools,
read-only → governed fleet control. World-first: no other MCP server exposes governed PDM mutation.

## Scope (increment 1) — guest lifecycle only

Power · in-cluster migrate · cross-remote migrate · snapshot (create/delete/rollback), for both
qemu (VM) and lxc (CT). **~12 tools.**

### Verified PDM proxy paths (from the official schema, not guessed)

| Capability | qemu | lxc |
|---|---|---|
| Power | `POST …/qemu/{vmid}/{start,stop,shutdown,resume}` | `POST …/lxc/{vmid}/{start,stop,shutdown}` |
| Migrate (in-cluster) | `POST …/qemu/{vmid}/migrate` | `POST …/lxc/{vmid}/migrate` |
| Migrate (cross-remote) | `POST …/qemu/{vmid}/remote-migrate` | `POST …/lxc/{vmid}/remote-migrate` |
| Snapshot create | `POST …/qemu/{vmid}/snapshot` | `POST …/lxc/{vmid}/snapshot` |
| Snapshot delete | `DELETE …/qemu/{vmid}/snapshot/{snap}` | `DELETE …/lxc/{vmid}/snapshot/{snap}` |
| Snapshot rollback | `POST …/qemu/{vmid}/snapshot/{snap}/rollback` | `POST …/lxc/{vmid}/snapshot/{snap}/rollback` |

Prefix: `/pve/remotes/{remote}`. PDM exposes **no** reboot/suspend proxy for qemu beyond the above,
and **no** resume/suspend for lxc — so we expose exactly what exists, nothing invented.

### Tools (mirroring the existing `pdm_pve_qemu_*` / `pdm_pve_lxc_*` split)

`pdm_pve_qemu_power`, `pdm_pve_lxc_power` (one `action` param each) ·
`pdm_pve_qemu_migrate`, `pdm_pve_lxc_migrate` ·
`pdm_pve_qemu_remote_migrate`, `pdm_pve_lxc_remote_migrate` ·
`pdm_pve_qemu_snapshot_create/_delete/_rollback` + `pdm_pve_lxc_snapshot_create/_delete/_rollback`.

Shared backend logic (kind-parametrised), thin qemu/lxc wrappers — identical to how the read plane
is already built (`_guest_list`/`_guest_config`).

## Trust spine mapping (honest, per-op)

- **PLAN** — dedicated PDM plan builders read the guest's live state through the proxy
  (`GET …/{kind}/{vmid}/status`) and produce the standard Plan (target, current state, no-op detection,
  risk). Dry-run by default: no `confirm=True`, no mutation. Plan recorded on both paths.
- **PROVE** — the funnel's hash-chained ledger. Guest ops through PDM are **task-backed** (return a
  UPID) → `outcome="submitted"`, never `"ok"`: the ledger must not claim the guest stopped when only
  the task was accepted (same discipline as `pve_guest_power`).
- **UNDO** —
  - *snapshot rollback* (destructive: discards current state) → **auto safety-snapshot before rollback**,
    proxied via `POST …/snapshot`, fail-closed (no snapshot, no rollback). This is the strong story
    and it is reachable through the proxy.
  - *power, migrate, remote-migrate* → state transitions with no snapshot-undo primitive; stated
    plainly (the inverse is another action, not an auto-rollback) — same honesty as the PVE power plane.
  - *snapshot delete* → not reversible (can't un-delete); no rollback, stated.
- **Security** — reuse the existing hardened validators (`_check_remote`, `_check_vmid`, `_check_node`,
  `_check_opt`), fail-closed TLS/fingerprint pinning, token-by-path-never-logged. New mutation params
  (target node, target remote, snapname) get their own validators.

## Out of scope (YAGNI — clean follow-ons, not this build)

Snapshot description edits (`PUT …/snapshot/{snap}/config`), task-cancel (`DELETE …/tasks/{upid}`),
node apt/update, guest-firewall `PUT`, and **PDM-native governance** (remote register/update/delete,
PDM ACL/user writes = the "govern the manager" plane) — that is increment 2 (option B).

## Architecture / new code

1. `src/proximo/pdm.py` — add mutation primitives (`_post`, `_put`, `_delete` + proxy variants
   `_pve_remote_post/_put/_delete`) and backend methods (guest_power, guest_migrate,
   guest_remote_migrate, snapshot_create/delete/rollback, guest_status-for-plan).
2. `src/proximo/planning.py` (or a `pdm` planning section) — PDM plan builders reading via the proxy;
   share Plan-shaping helpers with the PVE builders where clean.
3. New `src/proximo/tools/pdm_fleet.py` — the 12 confirm-gated tool wrappers (keeps `tools/pdm.py`
   read-only and focused; registered into server.py the same way as the other `tools/*.py`).
4. A PDM-flavoured auto-undo-before-rollback path (proxied snapshot_create + task wait).

## Tests (TDD — structural doubles, no live host)

Per tool: (a) dry-run returns a plan and issues **no** POST; (b) `confirm=True` issues exactly the
verified `(method, path)` with the right body; (c) ledger records `outcome="submitted"`;
(d) rollback takes the safety snapshot first and fail-closes if it can't; (e) validators reject
traversal/control-chars/bad vmid. Update `tests/test_tool_count.py` `EXPECTED_TOOL_COUNT` (352 →
~364) and add the new tools to `tests/test_taint_classification_complete.py`. Full suite must stay
green + ruff clean.

## Live-prove — DONE 2026-07-06 ✅

Operator-armed, against a real PDM 1.1.4 + the nested PVE 9.2 cluster (`pve-test1/2/3`) with a
throwaway qemu guest (31410) on shared NFS: `scripts/live-smoke/pdm-fleet-smoke.py` proved
power stop/start → snapshot create → rollback (auto safety-snapshot taken first) → snapshot delete →
**online migrate pve-test1→pve-test2 and back**, with the 92-entry PROVE hash-chain verified
(48 planned + 38 submitted + 4 undo_point). The run surfaced and fixed three real bugs (remote-qualified
UPID parsing, JSON-boolean serialization, surfacing the safety-snapshot name) — see CHANGELOG.

`remote-migrate` (cross-remote) is still NOT live-proven — it needs a second registered remote with
compatible storage; its path/body are schema-verified but its docstring stays honest until that smoke fires.

## Build order (TDD)

1. Backend mutation primitives + one method (power) — RED→GREEN.
2. Remaining backend methods (migrate, remote-migrate, snapshot ×3, status-read).
3. PDM plan builders.
4. Power tools (qemu+lxc) wired through `_plan`/`_audited`.
5. Snapshot tools + auto-undo-before-rollback.
6. Migrate + remote-migrate tools.
7. Count + taint-classification tests; docstrings; CHANGELOG `[Unreleased]`; ruff; full suite.

## Honesty caveats

PDM is alpha (API evolving — re-pull the denominator on future audits). This increment is
"code reaches the verified URL + unit-proven," not "live-tested," until the `!` smoke fires.
`remote-migrate` is the newest/riskiest PVE feature and the last to prove.

**Create/provision on a remote is NOT in scope — because it is not proxiable.** PDM exposes no
collection-level create (`POST …/qemu` / `…/lxc`) and no clone on the remote proxy — verified against
the schema. This matches a live user report + open Proxmox bugzilla feature request (KarelBP,
Proxmox forum, Apr–Jun 2026: "create a VM/CT on a remote node through PDM"). The demand is real and
public; the endpoint does not exist yet. We expose exactly what PDM proxies (lifecycle on existing
guests) and add create-on-remote only when Proxmox ships the proxy for it. Inventing it is the exact
oversell the thesis refuses.
