# Spec: Native async-task wait (`pve_task_wait`)

- **Date:** 2026-06-19
- **Status:** Implemented (TDD).
- **Surface:** MCP tool + `tasks_pools.py` helper.

## Why (and why NOT MCP Tasks)

Proxmox long-running ops — `pve_guest_migrate`, `pve_backup`, `pve_restore`, `pve_clone`,
`pve_rollback`, snapshot create/delete, guest create — are **async**: they return a task **UPID**
and the caller polls `pve_task_status` until it finishes. Today a client (or an AI) must hand-roll a
poll loop. The ergonomic gap: *"start the backup and tell me when it's done."*

We do **not** adopt the MCP Tasks protocol feature for this: **SEP-1686 (Tasks) was removed from the
MCP specification**; the `mcp` SDK's task API is `experimental`, `@deprecated`, and slated for removal
in mcp 2.0 ("expected to return as a separate MCP extension"). Building on it would be building on a
feature already being torn out. Instead we polish Proximo's **native** UPID model — which works on
every MCP client today — and stay ready to graft the Tasks extension if/when it actually ships.

## What gets built

`pve_task_wait(upid, node=None, timeout=120, interval=2)` — a **read-only** tool that blocks until a
task reaches a terminal state or the timeout elapses, returning a structured result:

```
{ "upid": ..., "finished": bool, "succeeded": bool, "status": "stopped"|"running"|...,
  "exitstatus": "OK"|<err>|None, "timed_out": bool, "polls": int }
```

- `finished` = reached terminal (PVE `status == "stopped"`) within the timeout.
- `succeeded` = `finished AND exitstatus == "OK"` (fail-closed: a stopped task with no/!=OK
  exitstatus is **not** success — mirrors the internal `_wait_task` contract).
- **Never raises on task outcome** — a failed or timed-out task is a *result*, not an exception (a
  tool returns structured data). A genuine API error still propagates (as for every other tool).
- The full log stays in the existing `pve_task_log` tool. We deliberately don't bundle a "tail" here:
  PVE's log endpoint (as wrapped) doesn't return the line total, so a true tail can't be produced
  without mislabeling a head — and `exitstatus` already carries the outcome/error summary.

The proven poll logic already exists internally as `_wait_task` (server.py, used by the auto-undo
path); that one **raises** by design (fail-closed for UNDO). This adds a public, *structured-result*
sibling, `wait_for_task`, in `tasks_pools.py` — pure, with injectable `sleep`/`monotonic` for
deterministic tests. `_wait_task` is left untouched (it is load-bearing and currently untested;
DRY-merging it is a separate, safety-netted change).

## Design decisions

- **Read-only.** Polling observes; no mutation, no confirm gate. Audited as a read.
- **Bounds clamped.** `timeout` → [1, 600]s, `interval` → [1, 60]s (no unbounded blocking).
- **Injectable timing.** `wait_for_task` takes `sleep`/`monotonic` callables (default `time.*`) so
  tests are deterministic and never actually sleep.
- **Additive only.** No change to existing async tools' return shapes (a consistent task-handle shape
  across all of them is a possible *future* increment, not this one).

## Non-goals

- Not the MCP Tasks protocol (removed — see Why).
- Not auto-waiting inside the submit tools (they still return a UPID; waiting is an explicit,
  opt-in second call — keeps submit fast and non-blocking).
- Not added to the A2A curated skill slice in this cycle (separate decision).

## Test plan (TDD)

1. `wait_for_task`: terminal-OK after N polls → `finished/succeeded`, correct `polls`, slept N-1×.
2. Non-OK exit → `finished=True, succeeded=False`, exitstatus preserved.
3. Always-running + clock past deadline → `timed_out=True, finished=False`.
4. Immediate terminal → `polls==1`, never sleeps.
5. `pve_task_wait` tool: returns the structured handle (with `upid`), surfaces task failure, audited
   as a read. (Tool tests use an immediate-terminal status so they never actually sleep.)
