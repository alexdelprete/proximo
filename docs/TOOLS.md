# Proximo — tool reference

The complete external interface of Proximo **v0.20.0**: every MCP tool it exposes, with its inputs. This file is generated from the live server's `tools/list` output (via `lhm.plugin.json`) by [`scripts/gen_tools_doc.py`](../scripts/gen_tools_doc.py) — do not hand-edit.

**Interface conventions.** Proximo speaks the [Model Context Protocol](https://modelcontextprotocol.io); each tool is also self-describing at runtime over the standard `tools/list` method. **Inputs** are the typed parameters listed per tool below. **Output** is a structured JSON result: read tools return the requested data; every mutating tool first returns a **PLAN** preview (the action and its blast radius) rather than acting, and each call is recorded in the tamper-evident audit ledger. Which tools are registered depends on `PROXIMO_SURFACES` and whether the opt-in exec/agent edges are enabled; this reference lists the **full** catalog.

**365 tools** across 7 surfaces.

## Contents

- [Proxmox VE — in-guest agent (opt-in)](#proxmox-ve--in-guest-agent-opt-in) — 6
- [Proxmox VE (PVE)](#proxmox-ve-pve) — 184
- [Proxmox Backup Server (PBS)](#proxmox-backup-server-pbs) — 33
- [Proxmox Mail Gateway (PMG)](#proxmox-mail-gateway-pmg) — 103
- [Proxmox Datacenter Manager (PDM)](#proxmox-datacenter-manager-pdm) — 34
- [Container exec (opt-in)](#container-exec-opt-in) — 4
- [Core / trust spine](#core--trust-spine) — 1

## Proxmox VE — in-guest agent (opt-in)

#### `pve_agent_exec`

MUTATION: run a command inside a guest via the qemu-agent (async, polls for result).

Dry-run by default: without confirm=True you get a PLAN recorded to the ledger.
Re-call with confirm=True to execute.

Requires PROXIMO_ENABLE_AGENT=1 and the VMID in PROXIMO_AGENT_ALLOWLIST.
The command runs INSIDE the guest OS — no undo primitive on this plane.

Returns status="ok" only when the agent reports the process exited.
Returns status="running" with pid when the poll deadline is reached before exit.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `command` | array<string> | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `timeout` | integer | no | (default: `30`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_agent_file_read`

READ-ONLY: read a file from inside the guest via the qemu-agent.

Requires PROXIMO_ENABLE_AGENT=1 and the VMID in PROXIMO_AGENT_ALLOWLIST.
No confirm needed — read-only.  File path must be absolute.

Ledger records only the file path (never the content); the returned dict carries content.
Smoke-confirm: PVE file-read response shape is unverified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `file` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_agent_file_write`

MUTATION: write a file inside the guest via the qemu-agent.

Dry-run by default: without confirm=True you get a PLAN recorded to the ledger.
Re-call with confirm=True to execute.

Requires PROXIMO_ENABLE_AGENT=1 and the VMID in PROXIMO_AGENT_ALLOWLIST.
File path must be absolute.  Content is UNCONDITIONALLY redacted from the ledger.
No undo primitive on this plane.
Smoke-confirm: PVE file-write endpoint and content encoding are unverified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `file` | string | yes |  |
| `content` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_agent_fs`

MUTATION: fsfreeze-freeze, fsfreeze-thaw, or fstrim inside the guest via the qemu-agent.

Dry-run by default: without confirm=True you get a PLAN recorded to the ledger.
Re-call with confirm=True to execute.

Requires PROXIMO_ENABLE_AGENT=1 and the VMID in PROXIMO_AGENT_ALLOWLIST.
command: fsfreeze-freeze | fsfreeze-thaw | fstrim
No undo primitive on this plane; always pair freeze with thaw.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `command` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_agent_info`

READ-ONLY: query the qemu-agent on a guest (ping, osinfo, hostname, users, exec-status, …).

Requires PROXIMO_ENABLE_AGENT=1 and the VMID in PROXIMO_AGENT_ALLOWLIST.
No confirm needed — read-only.

command: one of ping, info, get-fsinfo, get-host-name, get-osinfo, get-time,
         get-timezone, get-users, get-vcpus, network-get-interfaces,
         get-memory-blocks, fsfreeze-status, exec-status.
pid: required when command='exec-status' (the pid returned by pve_agent_exec).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `command` | string | no | (default: `"info"`) |
| `pid` | integer (nullable) | no | (default: `null`) |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_agent_set_password`

MUTATION: set a guest OS user's password via the qemu-agent.

Dry-run by default: without confirm=True you get a PLAN recorded to the ledger.
Re-call with confirm=True to execute.

Requires PROXIMO_ENABLE_AGENT=1 and the VMID in PROXIMO_AGENT_ALLOWLIST.
Password is UNCONDITIONALLY redacted from the ledger (fingerprint only — "[redacted]").
No undo primitive on this plane.
Smoke-confirm: PVE set-user-password endpoint and body fields are unverified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `username` | string | yes |  |
| `password` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

## Proxmox VE (PVE)

#### `pve_acl_list`

List all ACL entries on the Proxmox cluster (read-only). Returns each entry's path (resource
scope), roleid (privilege set), principal (user/group/token), type, and propagate flag. Use
pve_acl_modify to grant/revoke; use pve_overbroad_grants to flag Administrator or root-path
grants.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acl_modify`

MUTATION: grant or revoke an ACL entry (PUT /access/acl).

Dry-run by default — the PLAN surfaces the critical Proxmox gotcha: a specific-path ACL
REPLACES inherited grants (SHADOW) and revoking can RESTORE them (WIDEN). Re-call with
confirm=True to execute. Synchronous.

kind='user' (default), 'group', or 'token'. delete=False = grant; delete=True = revoke.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `path` | string | yes |  |
| `roles` | string | yes |  |
| `target` | string | yes |  |
| `kind` | string | no | (default: `"user"`) |
| `propagate` | boolean | no | (default: `true`) |
| `delete` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acl_prune`

MUTATION: prune (remove/narrow) an over-broad ACL grant flagged by pve_overbroad_grants.

Dry-run by default — the PLAN names every principal losing/gaining what, and flags
shadow/widen gotchas. Re-call with confirm=True to execute (revoke, then optional
narrower re-grant). Synchronous. roleid = the over-broad role to remove (from detection).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `path` | string | yes |  |
| `target` | string | yes |  |
| `kind` | string | no | (default: `"user"`) |
| `roleid` | string | no | (default: `""`) |
| `narrow_role` | string (nullable) | no | (default: `null`) |
| `narrow_path` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acme_account_create`

MUTATION: register a new ACME account with the CA. Dry-run by default.
confirm=True to execute. Smoke-confirm: POST body shape (name in body) against a live PVE instance.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `contact` | string | yes |  |
| `tos_url` | string (nullable) | no | (default: `null`) |
| `directory` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acme_account_delete`

MUTATION: IRREVERSIBLE — deactivate and delete an ACME account from the CA. Dry-run by default.
confirm=True to execute. HIGH risk: TLS lockout at cert expiry if this is the only account.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acme_account_update`

MUTATION: update ACME account contact info. Dry-run by default.
confirm=True to execute. LOW risk — metadata update only, no cert impact.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `contact` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acme_cert_order`

MUTATION: order a NEW ACME TLS certificate for the node's configured ACME domains. Dry-run
by default. Async — returns a task UPID (poll pve_task_status/pve_task_wait).

MEDIUM (lower than pve_node_cert_upload's HIGH): the cert is CA-validated and installed ONLY on
a successful challenge — a failed challenge leaves the existing cert untouched, so it cannot
lock you out. On success PVE reloads pveproxy. force=overwrite an existing custom cert.
Revert to self-signed with pve_node_cert_delete. confirm=True to execute.
Smoke-confirm: POST shape + async UPID against a live PVE instance.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `force` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acme_cert_renew`

MUTATION: renew the node's existing ACME TLS certificate. Dry-run by default. Async — returns
a UPID. MEDIUM: CA-validated, installed only on success (a failure can't lock you out); reloads
pveproxy on success. force=renew even if more than 30 days to expiry. confirm=True to execute.
Smoke-confirm: PUT shape + async UPID against a live PVE instance.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `force` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acme_cert_revoke`

MUTATION: IRREVERSIBLE — revoke the node's ACME TLS certificate at the CA. Dry-run by default.
Async — returns a UPID. HIGH: a revoked cert cannot be un-revoked; only a NEW pve_acme_cert_order
restores trust. To fall back to PVE's self-signed cert WITHOUT revoking at the CA, use
pve_node_cert_delete instead. confirm=True to execute. Smoke-confirm: DELETE shape against a live
PVE instance.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acme_plugin_create`

MUTATION: create an ACME DNS challenge plugin. Dry-run by default.
confirm=True to execute. dns_api = DNS provider name (e.g. 'cf', 'route53').
Smoke-confirm: POST body shape (id in body) against a live PVE instance.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `plugin_id` | string | yes |  |
| `plugin_type` | string | yes |  |
| `dns_api` | string (nullable) | no | (default: `null`) |
| `data` | string (nullable) | no | (default: `null`) |
| `disable` | boolean (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acme_plugin_delete`

MUTATION: delete an ACME DNS challenge plugin. Dry-run by default.
confirm=True to execute. HIGH risk: cert auto-renewal breaks — TLS lockout at cert expiry.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `plugin_id` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acme_plugin_update`

MUTATION: update an ACME DNS challenge plugin. Dry-run by default.
confirm=True to execute. MEDIUM risk — invalid credentials break renewal at next attempt.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `plugin_id` | string | yes |  |
| `dns_api` | string (nullable) | no | (default: `null`) |
| `data` | string (nullable) | no | (default: `null`) |
| `disable` | boolean (nullable) | no | (default: `null`) |
| `digest` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_backup`

MUTATION: back up a guest with vzdump. Dry-run by default; confirm=True to execute.
mode: snapshot (online, brief) | suspend | stop (HALTS the guest). Async — returns a task UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `storage` | string | yes |  |
| `mode` | string | no | (default: `"snapshot"`) |
| `compress` | string | no | (default: `"zstd"`) |
| `kind` | string | no | (default: `"lxc"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_backup_delete`

MUTATION: delete a backup archive (removes a recovery point). Dry-run by default; confirm=True.
Async — may return a task UPID or null depending on storage.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes |  |
| `volid` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_backup_freshness`

Backup-freshness fence (read): walks ACTUAL backup archives per guest and compares their
age against what enabled backup jobs promise. A job or task reporting OK is never treated as
evidence a backup exists — only an archive on storage counts. Verdicts per guest:
fresh | stale | never | uncovered | unknown; an unreadable storage yields unknown +
complete=false, never a clean bill. max_age_hours overrides the schedule-derived expectation;
grace_hours pads each job's parsed cadence.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `max_age_hours` | number (nullable) | no | (default: `null`) |
| `grace_hours` | number | no | (default: `6.0`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_backup_job_create`

MUTATION: create a PVE cluster backup job. Dry-run by default — shows the plan.
confirm=True to execute. Config-only; existing backups are NOT affected.
Guest selection is mutually exclusive — pass at most one of: vmid (CSV of guest IDs),
all_guests=True (every guest), or pool (a resource pool); PVE requires a selection.
exclude (CSV) filters all_guests.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `job_id` | string | yes |  |
| `schedule` | string | yes |  |
| `storage` | string | yes |  |
| `mode` | string (nullable) | no | (default: `null`) |
| `compress` | string (nullable) | no | (default: `null`) |
| `vmid` | string (nullable) | no | (default: `null`) |
| `all_guests` | boolean (nullable) | no | (default: `null`) |
| `pool` | string (nullable) | no | (default: `null`) |
| `exclude` | string (nullable) | no | (default: `null`) |
| `enabled` | boolean (nullable) | no | (default: `null`) |
| `comment` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_backup_job_delete`

MUTATION: delete a PVE cluster backup job. Dry-run by default — captures current config.
confirm=True to execute. Schedule removed; existing backups are NOT deleted.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `job_id` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_backup_job_list`

List all PVE cluster backup jobs and guests not covered by any job (read).
Returns {jobs: [...], unprotected_guests: [...]}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_backup_job_update`

MUTATION: update a PVE cluster backup job. Dry-run by default — captures current config.
confirm=True to execute. Config-only; no impact on existing backups.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `job_id` | string | yes |  |
| `schedule` | string (nullable) | no | (default: `null`) |
| `storage` | string (nullable) | no | (default: `null`) |
| `mode` | string (nullable) | no | (default: `null`) |
| `compress` | string (nullable) | no | (default: `null`) |
| `vmid` | string (nullable) | no | (default: `null`) |
| `enabled` | boolean (nullable) | no | (default: `null`) |
| `comment` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_backup_list`

List backup archives in a storage (read). Ground truth for whether a backup exists —
a backup missing from a pve_tasks_list slice (other node, or outside its limit window)
still shows here.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_clone`

MUTATION: clone a guest to a new id. Dry-run by default; confirm=True. Async — returns a UPID.
pool: place the new guest in a resource pool (needed when the token is pool-scoped).
storage: target storage for the full clone's disks (full=True only) — keeps a clone off the
source storage; refused for a linked clone (PVE only honors it on a full clone).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `newid` | string | yes |  |
| `kind` | string | no | (default: `"lxc"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `name` | string (nullable) | no | (default: `null`) |
| `full` | boolean | no | (default: `false`) |
| `pool` | string (nullable) | no | (default: `null`) |
| `storage` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_cloudinit_get`

Read a QEMU guest's cloud-init configuration (read-only). Returns cloud-init fields
(ciuser, sshkeys, ipconfigN, cipassword placeholder) with secret fields masked for safety.
Use pve_cloudinit_set to mutate it; the set operation auto-captures an undo record for
rollback.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `kind` | string | no | (default: `"qemu"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_cloudinit_set`

MUTATION: set cloud-init fields (ciuser/sshkeys/ipconfigN/...) on a QEMU guest. Dry-run by
default — the PLAN shows the diff with secrets masked; confirm=True to execute. Synchronous.
Secret fields (cipassword) are never echoed to results or the ledger.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `changes` | object | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `kind` | string | no | (default: `"qemu"`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_cluster_resources`

List all resources across the cluster (VMs, nodes, storage, SDN).
resource_type: optional filter — 'vm', 'storage', 'node', or 'sdn' (read).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `resource_type` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_cluster_status`

Retrieve the cluster's overall status: nodes, quorum state, and the corosync
config version (read-only). Returns a list of status dicts with node names, types, online
status, and quorum info. Use pve_cluster_resources to list all resources across the cluster.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_create_container`

MUTATION: create a new LXC container. Dry-run by default; confirm=True. Async — returns a UPID.
`options` carries extra create params (cores, memory, net0, rootfs, password, ...).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `ostemplate` | string | yes |  |
| `storage` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `options` | object (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_create_vm`

MUTATION: create a new QEMU VM. Dry-run by default; confirm=True. Async — returns a UPID.
`options` carries create params (cores, memory, net0, scsi0, ostype, ...).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `options` | object (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_delete_guest`

MUTATION (DESTRUCTIVE, IRREVERSIBLE): permanently destroy a guest and its disks. Dry-run by
default — the PLAN names exactly what will be destroyed. confirm=True to execute. Async — UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `kind` | string | no | (default: `"lxc"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `purge` | boolean | no | (default: `false`) |
| `force` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_diagnose`

READ-ONLY: gather node health evidence — status + storage usage + recent failed tasks + flags.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_disk_move`

MUTATION: move a guest disk to another storage. Dry-run by default — the PLAN shows
source->target and whether the source copy is deleted (delete_source=True is HIGH). confirm=True
to execute. Async — returns a task UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `disk` | string | yes |  |
| `target_storage` | string | yes |  |
| `kind` | string | no | (default: `"lxc"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `delete_source` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_disk_resize`

MUTATION: grow a guest disk (e.g. size='+10G'). GROW ONLY — a shrink is refused (destructive).
Dry-run by default; confirm=True to execute. Async — returns a task UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `disk` | string | yes |  |
| `size` | string | yes |  |
| `kind` | string | no | (default: `"lxc"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_doctor`

READ-ONLY preflight: check API connectivity + the calling token's effective permissions, and
report what this token CAN and CANNOT do — with the privilege + role to grant for each gap. Run
this FIRST after install to verify your config/token before wiring Proximo into an MCP client.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_alias_create`

MUTATION: create a firewall alias (named CIDR). Dry-run by default — the PLAN shows the
name, CIDR, and scope. Re-call with confirm=True to execute. Passive until a rule references it.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `cidr` | string | yes |  |
| `scope` | string | no | (default: `"cluster"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `vmid` | string (nullable) | no | (default: `null`) |
| `kind` | string (nullable) | no | (default: `null`) |
| `comment` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_alias_delete`

MUTATION: delete a firewall alias. Dry-run by default — the PLAN shows the current alias.
PVE refuses while any rule still references the alias. No UNDO: re-create to revert.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `scope` | string | no | (default: `"cluster"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `vmid` | string (nullable) | no | (default: `null`) |
| `kind` | string (nullable) | no | (default: `null`) |
| `digest` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_alias_list`

List firewall aliases (named CIDRs) for the given scope (read). Scope = cluster
or guest only — the PVE API has no node-scope aliases (node firewall = options/rules/log).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `scope` | string | no | (default: `"cluster"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `vmid` | string (nullable) | no | (default: `null`) |
| `kind` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_alias_update`

MUTATION: update a firewall alias. Dry-run by default — the PLAN shows the current alias and
the fields being changed. Changing the CIDR silently alters every referencing rule's match set.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `scope` | string | no | (default: `"cluster"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `vmid` | string (nullable) | no | (default: `null`) |
| `kind` | string (nullable) | no | (default: `null`) |
| `cidr` | string (nullable) | no | (default: `null`) |
| `comment` | string (nullable) | no | (default: `null`) |
| `rename` | string (nullable) | no | (default: `null`) |
| `digest` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_ipset_create`

MUTATION: create an empty IP set. Dry-run by default — the PLAN shows the name and scope.
Passive until a rule references it as '+name' and entries are added.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `scope` | string | no | (default: `"cluster"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `vmid` | string (nullable) | no | (default: `null`) |
| `kind` | string (nullable) | no | (default: `null`) |
| `comment` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_ipset_delete`

MUTATION: delete an IP set. Dry-run by default — the PLAN shows member count and the
force semantics. force=True WIPES all members; PVE refuses while a rule references the set.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `scope` | string | no | (default: `"cluster"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `vmid` | string (nullable) | no | (default: `null`) |
| `kind` | string (nullable) | no | (default: `null`) |
| `force` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_ipset_entry_add`

MUTATION: add an IP/Network entry to an IP set. Dry-run by default — the PLAN shows the
entry and warns it changes every referencing rule's match set. nomatch=True = exclusion.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `cidr` | string | yes |  |
| `scope` | string | no | (default: `"cluster"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `vmid` | string (nullable) | no | (default: `null`) |
| `kind` | string (nullable) | no | (default: `null`) |
| `comment` | string (nullable) | no | (default: `null`) |
| `nomatch` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_ipset_entry_remove`

MUTATION: remove an IP/Network entry from an IP set. Dry-run by default — the PLAN shows the
entry and warns it changes every referencing rule's match set (may open or close access).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `cidr` | string | yes |  |
| `scope` | string | no | (default: `"cluster"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `vmid` | string (nullable) | no | (default: `null`) |
| `kind` | string (nullable) | no | (default: `null`) |
| `digest` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_options_get`

Get firewall options (enable flag, policy, log rate, …) for the given scope (read).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `scope` | string | no | (default: `"cluster"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `vmid` | string (nullable) | no | (default: `null`) |
| `kind` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_options_set`

MUTATION: set firewall options for a scope (policy_in/out, log levels, ebtables, log_ratelimit,
...). `options` is a key->value bag; `delete` unsets keys. Dry-run by default — the PLAN shows the
current values and flags lockout risk. RISK_HIGH when enabling the firewall or changing a policy.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `scope` | string | no | (default: `"cluster"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `vmid` | string (nullable) | no | (default: `null`) |
| `kind` | string (nullable) | no | (default: `null`) |
| `options` | object (nullable) | no | (default: `null`) |
| `delete` | array<string> (nullable) | no | (default: `null`) |
| `digest` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_rule_add`

MUTATION: add a new firewall rule. Dry-run by default — the PLAN shows scope, direction,
action, and key address/port fields. Re-call with confirm=True to execute. Synchronous.

WARNING: a misplaced DROP/REJECT can cause a connectivity lockout.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `action` | string | yes |  |
| `direction` | string | no | (default: `"in"`) |
| `scope` | string | no | (default: `"cluster"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `vmid` | string (nullable) | no | (default: `null`) |
| `kind` | string (nullable) | no | (default: `null`) |
| `source` | string (nullable) | no | (default: `null`) |
| `dest` | string (nullable) | no | (default: `null`) |
| `proto` | string (nullable) | no | (default: `null`) |
| `dport` | string (nullable) | no | (default: `null`) |
| `sport` | string (nullable) | no | (default: `null`) |
| `comment` | string (nullable) | no | (default: `null`) |
| `enable` | boolean | no | (default: `true`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_rule_remove`

MUTATION: delete a firewall rule by position. Dry-run by default — the PLAN shows the rule
at that position AND the optimistic-lock digest. Positions SHIFT after inserts/deletes — pass the
digest from the plan back as `digest=` on confirm so PVE rejects the delete if the rule list moved
since the preview (otherwise a concurrent insert can shift positions and remove the wrong rule).
Synchronous.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `pos` | integer | yes |  |
| `scope` | string | no | (default: `"cluster"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `vmid` | string (nullable) | no | (default: `null`) |
| `kind` | string (nullable) | no | (default: `null`) |
| `digest` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_rule_update`

MUTATION: update an existing firewall rule at position `pos`. Dry-run by default — the PLAN
shows the rule's current state, the fields being changed, AND the optimistic-lock digest. Pass the
digest from the plan back as `digest=` on confirm so PVE rejects the update if the rule list moved
since the preview (positions shift and the wrong rule can be updated otherwise). Synchronous.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `pos` | integer | yes |  |
| `scope` | string | no | (default: `"cluster"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `vmid` | string (nullable) | no | (default: `null`) |
| `kind` | string (nullable) | no | (default: `null`) |
| `action` | string (nullable) | no | (default: `null`) |
| `direction` | string (nullable) | no | (default: `null`) |
| `source` | string (nullable) | no | (default: `null`) |
| `dest` | string (nullable) | no | (default: `null`) |
| `proto` | string (nullable) | no | (default: `null`) |
| `dport` | string (nullable) | no | (default: `null`) |
| `sport` | string (nullable) | no | (default: `null`) |
| `comment` | string (nullable) | no | (default: `null`) |
| `enable` | boolean (nullable) | no | (default: `null`) |
| `digest` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_rules_list`

List firewall rules for the given scope (cluster, node, or guest) (read-only).

Returns the active rules at that scope level, including action, direction, protocol,
and address/port fields. Use pve_firewall_options_get to read firewall settings
(enable flag, policy, log rate).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `scope` | string | no | (default: `"cluster"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `vmid` | string (nullable) | no | (default: `null`) |
| `kind` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_security_group_create`

MUTATION: create an empty cluster security group. Dry-run by default — the PLAN shows the
name. Passive until rules are added and a rule references it (type=group).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `group` | string | yes |  |
| `comment` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_security_group_delete`

MUTATION: delete a cluster security group. Dry-run by default — the PLAN shows how many rules
the group holds. PVE refuses while the group is non-empty or still referenced by a rule.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `group` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_set_enabled`

MUTATION (HIGH RISK): toggle the firewall on or off for the given scope. Dry-run by default.
RISK_HIGH both directions: enabling may instantly lock you out (default-DROP, no ACCEPT for 22/8006);
disabling strips all protection. Cluster scope = master kill-switch. Synchronous.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `enabled` | boolean | yes |  |
| `scope` | string | no | (default: `"cluster"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `vmid` | string (nullable) | no | (default: `null`) |
| `kind` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_group_create`

MUTATION: create an (empty) group. Dry-run by default (additive, LOW risk).
Returns the plan preview; confirm=True to execute. The group is inert until users are
added or an ACL entry grants it privileges.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `groupid` | string | yes |  |
| `comment` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_group_delete`

MUTATION (HIGH): delete a group. Dry-run by default — the PLAN reads members and warns ACLs
granted to/on the group are orphaned. confirm=True.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `groupid` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_group_get`

Get a group's full config (read-only). Returns groupid, comment, and member list (users in
the group). Use pve_group_create/update/delete to manage the group; use pve_acl_list to see
ACL entries referencing this group.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `groupid` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_group_update`

MUTATION: update a group's comment. Dry-run by default (additive, LOW risk).
Returns the plan preview; confirm=True to execute. Does not modify group membership.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `groupid` | string | yes |  |
| `comment` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_groups_list`

List all Proxmox groups (read-only). Returns each group's id, comment, and member count.
Use pve_group_get for full member list; use pve_group_create/update/delete to manage groups.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_guest_config_get`

Read a guest's current configuration (kind='lxc' or 'qemu') (read-only). Returns the
complete config dict with cores, memory, network, disks, metadata, and all settings. Use
pve_guest_config_set to mutate; capture the returned dict to enable rollback via
pve_guest_config_revert.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `kind` | string | no | (default: `"lxc"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_guest_config_revert`

MUTATION (UNDO): re-apply a previously captured guest config (the prior_config returned by
pve_guest_config_set). Dry-run by default; confirm=True to execute. Synchronous.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `prior_config` | object | yes |  |
| `kind` | string | no | (default: `"lxc"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_guest_config_set`

MUTATION: edit a guest's config (cores/memory/net/onboot/...). Dry-run by default — the PLAN
shows the exact per-key diff; confirm=True to execute. Captures the prior config first so the
change is revertible via pve_guest_config_revert. Synchronous.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `changes` | object | yes |  |
| `kind` | string | no | (default: `"lxc"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_guest_migrate`

MUTATION: migrate a guest to a different node. Dry-run by default — the PLAN shows the
guest's live state, the source→target, and the honest blast radius (LXC 'online' is
stop→move→start, NOT zero-downtime; QEMU live migration requires shared storage).
confirm=True to execute. Async — returns a task UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `target` | string | yes |  |
| `kind` | string | no | (default: `"lxc"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `online` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_guest_power`

MUTATION: start/stop/reboot/shutdown a guest.

Dry-run by default: without confirm=True you get a PLAN — the exact change, the guest's live
state, blast radius, and risk (with no-op detection) — recorded to the ledger. Re-call with
confirm=True to execute. The plan is recorded on BOTH paths: even a one-shot confirm=True call
records its plan before mutating — no plan, no mutation.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `action` | string | yes |  |
| `kind` | string | no | (default: `"lxc"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_guest_status`

Read the operational status and current configuration of a single guest (kind='lxc' or
'qemu') (read-only). Returns the guest's runtime state and resource utilization
(CPU/memory/disk/network/uptime) — operational metrics, not its stored configuration.
Use pve_guest_config_get for the full configuration.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `kind` | string | no | (default: `"lxc"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_ha_groups_list`

List all HA resource groups (read). PVE-8 only — PVE 9 migrated groups to rules
(use pve_ha_rules_list); on PVE 9 this raises a clear error pointing there.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_ha_resource_add`

MUTATION: add a guest to HA management. Dry-run by default — the PLAN shows the SID,
group, initial state, and blast radius (state='stopped' is HIGH: CRM will stop the guest).
confirm=True to execute. Synchronous (pmxcfs config write; CRM enforces state asynchronously).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `kind` | string | no | (default: `"lxc"`) |
| `group` | string (nullable) | no | (default: `null`) |
| `state` | string (nullable) | no | (default: `null`) |
| `max_restart` | integer (nullable) | no | (default: `null`) |
| `max_relocate` | integer (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_ha_resource_remove`

MUTATION: remove a guest from HA management. Dry-run by default — the PLAN shows the SID
and that this loses automated failover protection (guest itself is NOT stopped).
confirm=True to execute. Synchronous (pmxcfs config write).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `kind` | string | no | (default: `"lxc"`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_ha_resources_list`

List all guests managed by HA (High Availability) with their current HA settings
(read-only). Returns a list of HA resource dicts with SID, type, state, group, and restart
settings. Use pve_ha_groups_list or pve_ha_rules_list to view HA placement rules, not for
resource enumeration.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_ha_rule_create`

MUTATION: create an HA rule (the PVE 9 replacement for HA groups). Dry-run by default — the
PLAN shows the rule type, resources, and placement effect. `rule_type` is 'node-affinity'
(needs `nodes`; optional `strict`) or 'resource-affinity' (needs `affinity` positive|negative).
confirm=True to execute. Synchronous (pmxcfs config write). RISK_MEDIUM — constrains CRM placement.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `rule` | string | yes |  |
| `rule_type` | string | yes |  |
| `resources` | string | yes |  |
| `comment` | string (nullable) | no | (default: `null`) |
| `disable` | boolean | no | (default: `false`) |
| `nodes` | string (nullable) | no | (default: `null`) |
| `strict` | boolean | no | (default: `false`) |
| `affinity` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_ha_rule_delete`

MUTATION: delete an HA rule. Dry-run by default — the PLAN shows the current rule and that
its resources lose this placement constraint (CRM may migrate them). confirm=True to execute.
Synchronous. RISK_MEDIUM.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `rule` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_ha_rule_update`

MUTATION: update an HA rule. Dry-run by default — the PLAN shows the current rule and the
fields being changed. `delete` unsets keys. confirm=True to execute. Synchronous.
RISK_MEDIUM — may trigger CRM migration of affected resources.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `rule` | string | yes |  |
| `comment` | string (nullable) | no | (default: `null`) |
| `disable` | boolean (nullable) | no | (default: `null`) |
| `resources` | string (nullable) | no | (default: `null`) |
| `rule_type` | string (nullable) | no | (default: `null`) |
| `nodes` | string (nullable) | no | (default: `null`) |
| `strict` | boolean (nullable) | no | (default: `null`) |
| `affinity` | string (nullable) | no | (default: `null`) |
| `delete` | array<string> (nullable) | no | (default: `null`) |
| `digest` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_ha_rules_list`

List HA rules (read) — the PVE 9 replacement for HA groups.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_hardware_list`

List physical PCI or USB devices on a PVE node (read).
hw_type: 'pci' (default) or 'usb'.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | yes |  |
| `hw_type` | string | no | (default: `"pci"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_ipset_list`

List IP sets for the given scope (read). Scope = cluster or guest only —
the PVE API has no node-scope ipsets (node firewall = options/rules/log).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `scope` | string | no | (default: `"cluster"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `vmid` | string (nullable) | no | (default: `null`) |
| `kind` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_list_guests`

List all VMs and LXC containers on a node with their current state (read-only). Returns
a list of guest objects, each with VMID, name, type (lxc or qemu), and status. Works across
both kinds in a single call.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_mapping_pci_create`

MUTATION: create a PCI cluster passthrough mapping. Dry-run by default.
confirm=True to execute. Smoke-confirm: POST body shape (id in body) against a live PVE instance.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `mapping_id` | string | yes |  |
| `description` | string (nullable) | no | (default: `null`) |
| `map` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_mapping_pci_delete`

MUTATION: delete a PCI cluster mapping. Dry-run by default.
confirm=True to execute. VMs referencing this mapping lose the device path.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `mapping_id` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_mapping_pci_list`

List all PCI device mappings at cluster scope (read-only). Returns a list of
dicts defining passthrough mappings for PCI devices assignable to VMs/LXCs,
each with mapping ID, device list, and description.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_mapping_pci_update`

MUTATION: update a PCI cluster mapping. Dry-run by default.
confirm=True to execute. Reads current config for plan honesty.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `mapping_id` | string | yes |  |
| `description` | string (nullable) | no | (default: `null`) |
| `map` | string (nullable) | no | (default: `null`) |
| `digest` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_mapping_usb_create`

MUTATION: create a USB cluster passthrough mapping. Dry-run by default.
confirm=True to execute. Smoke-confirm: POST body shape (id in body) against a live PVE instance.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `mapping_id` | string | yes |  |
| `description` | string (nullable) | no | (default: `null`) |
| `map` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_mapping_usb_delete`

MUTATION: delete a USB cluster mapping. Dry-run by default.
confirm=True to execute. VMs referencing this mapping lose the USB device path.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `mapping_id` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_mapping_usb_list`

List all USB device mappings at cluster scope (read-only). Returns a list of
dicts defining passthrough mappings for USB devices assignable to VMs/LXCs,
each with mapping ID, device list, and description.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_mapping_usb_update`

MUTATION: update a USB cluster mapping. Dry-run by default.
confirm=True to execute. Reads current config for plan honesty.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `mapping_id` | string | yes |  |
| `description` | string (nullable) | no | (default: `null`) |
| `map` | string (nullable) | no | (default: `null`) |
| `digest` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_metrics_server_delete`

MUTATION: delete a PVE metrics server definition. Dry-run by default.
confirm=True to execute. Metrics forwarding to this server ceases; no data loss.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `metrics_id` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_metrics_server_list`

List all PVE metrics server definitions (read-only). Returns a list of dicts
for each configured metrics forwarding target (InfluxDB, Graphite, etc.), with
id, type, server address, and port.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_metrics_server_set`

MUTATION: create-or-update a PVE metrics server definition. Dry-run by default.
confirm=True to execute. Config-only; metrics forwarding adjusts to new settings.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `metrics_id` | string | yes |  |
| `metrics_type` | string (nullable) | no | (default: `null`) |
| `server` | string (nullable) | no | (default: `null`) |
| `port` | integer (nullable) | no | (default: `null`) |
| `disable` | boolean (nullable) | no | (default: `null`) |
| `comment` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_network_apply`

MUTATION (HIGH RISK): apply staged network config changes to the live network stack.
Dry-run by default — the PLAN surfaces pending interfaces. confirm=True to execute.
A misconfigured interface can lose SSH/API access; recovery requires console/physical access.
May return a UPID (async) or None (sync) — outcome='submitted' in either case.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_network_iface_create`

MUTATION: create a new network interface config (staged — not live until pve_network_apply).
Dry-run by default; confirm=True to execute. Synchronous.
`options` carries type-dependent fields (address, netmask, gateway, bridge_ports, …).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `iface` | string | yes |  |
| `iface_type` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `options` | object (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_network_iface_update`

MUTATION: update an existing network interface config (staged — not live until pve_network_apply).
Dry-run by default; confirm=True to execute. Synchronous.
`options` carries fields to update (address, netmask, bridge_ports, …).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `iface` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `options` | object (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_network_list`

List network interfaces on a node (read-only). Returns iface name, type
(bridge/bond/vlan/eth/alias), method, and address. Filter by type with iface_type.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `iface_type` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_acme_domains_set`

MUTATION: set a node's ACME account + domains (PUT /nodes/{node}/config). Dry-run by default.

The "what to issue" half of an ACME cert: pair with pve_acme_account_create +
pve_acme_plugin_create, then issue with pve_acme_cert_order. plugin=<id> uses a DNS-01
challenge (written as acmedomain0..N=domain=...,plugin=...); omit plugin for standalone
http-01 (domains ride in acme=...,domains=...). REPLACE semantics: stale acmedomainN entries
are removed, not merged. MEDIUM — config only, no cert is issued by this step. confirm=True
to execute. Smoke-confirm: node-config body shape against a live PVE instance.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `account` | string | yes |  |
| `domains` | array<string> | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `plugin` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_cert_delete`

MUTATION: delete the custom TLS certificate from a PVE node.

RISK_MEDIUM: PVE reverts to its self-signed certificate (recoverable by re-uploading).
restart=True reloads pveproxy after deletion. confirm=True to execute.

DELETE /nodes/{node}/certificates/custom
Smoke-confirm: endpoint and params shape not live-verified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `restart` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_cert_upload`

MUTATION: upload a custom TLS certificate to a PVE node.

RISK_HIGH, NO UNDO. A malformed cert/key can lock you out of the PVE web UI and API.
restart=True reloads pveproxy after upload (brief service interruption).

PRIVATE KEY REDACTION: the 'key' param is a TLS private key (secret). It is
UNCONDITIONALLY redacted — it NEVER appears in the plan, change, current state,
detail, or ledger (regardless of redact_ledger setting). Only {"key": "[redacted]"}
is recorded. The cert body (certificates) is public and may appear in plans/logs.

Revert: re-upload a correct cert, or use pve_node_cert_delete to revert to self-signed.
confirm=True to execute.

POST /nodes/{node}/certificates/custom
Smoke-confirm: endpoint and body shape not live-verified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `certificates` | string | yes |  |
| `key` | string (nullable) | no | (default: `null`) |
| `node` | string (nullable) | no | (default: `null`) |
| `force` | boolean | no | (default: `false`) |
| `restart` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_certificates`

List TLS certificates configured on a Proxmox node (read-only). Returns a
list of certificate dicts with filename, subject, issuer, validity dates
(notbefore/notafter), SANs, and fingerprint.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_disk_initgpt`

MUTATION: initialize a GPT partition table on a node disk.

RISK_HIGH: overwrites the existing partition table on the named disk; irreversible.
confirm=True to execute.

POST /nodes/{node}/disks/initgpt
Smoke-confirm: endpoint and body shape not live-verified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `disk` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_disk_smart`

Get SMART health data for a disk on a PVE node (read).

GET /nodes/{node}/disks/smart?disk=… — SMART attributes and health status.
Smoke-confirm: GET (read) only — this tool does NOT trigger a self-test.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `disk` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_disk_wipe`

MUTATION: wipe ALL data and the partition table on a node disk.

RISK_HIGH, NO UNDO: DESTROYS all data, partitions, and filesystems on the named disk.
This is irreversible — all data is permanently erased. confirm=True to execute.

PUT /nodes/{node}/disks/wipedisk
Smoke-confirm: endpoint and body shape not live-verified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `disk` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_disks_list`

List physical disks on a PVE node (read).

GET /nodes/{node}/disks/list — physical disk inventory and health info.
Smoke-confirm: response shape not live-verified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_dns`

Read a Proxmox node's DNS configuration (read-only). Returns a dict with
search domain and configured nameservers (dns1/dns2/dns3). Use pve_node_dns_set
to change it.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_dns_set`

MUTATION: update DNS resolver configuration on a PVE node.

RISK_MEDIUM (a wrong resolver config breaks name resolution cluster-wide — same failure
mode as node hosts_set). CAPTURE: reads current DNS config before planning (reuse
pve_node_dns read); if unreadable → complete=False. confirm=True to execute.

PUT /nodes/{node}/dns
Smoke-confirm: endpoint and body shape not live-verified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `search` | string (nullable) | no | (default: `null`) |
| `dns1` | string (nullable) | no | (default: `null`) |
| `dns2` | string (nullable) | no | (default: `null`) |
| `dns3` | string (nullable) | no | (default: `null`) |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_hosts_get`

Get the /etc/hosts content of a PVE node (read).

GET /nodes/{node}/hosts — returns {data, digest}.
Smoke-confirm: response shape not live-verified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_hosts_set`

MUTATION: replace the /etc/hosts file on a PVE node.

RISK_MEDIUM. CAPTURE: reads current /etc/hosts before planning (revert by re-applying captured
content); if unreadable → complete=False. A bad /etc/hosts can break name resolution.
confirm=True to execute.

POST /nodes/{node}/hosts
Smoke-confirm: endpoint and body shape not live-verified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `data` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `digest` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_journal`

Fetch journal entries from a PVE node (read; returns log-line strings). lastentries capped at 5000.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `lastentries` | integer | no | (default: `100`) |
| `since` | string (nullable) | no | (default: `null`) |
| `until` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_migrateall`

MUTATION: migrate all (or filtered) guests from a node to a target node.

RISK_HIGH, NOT auto-reversible: reversal requires a second pve_node_migrateall back,
which may not restore the original state. target = destination node name (required).
confirm=True to execute.

POST /nodes/{node}/migrateall
Smoke-confirm: endpoint and body shape not live-verified. May return task UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `target` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `vms` | string (nullable) | no | (default: `null`) |
| `maxworkers` | integer (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_rrddata`

Fetch RRD (round-robin database) time-series telemetry for a PVE node
(read-only). Returns a list of data-point dicts with timestamps and metrics
(cpu, memory, disk, network) over the specified timeframe, optionally
aggregated by consolidation function (AVERAGE or MAX).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `timeframe` | string | no | (default: `"hour"`) |
| `cf` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_service_control`

MUTATION: start/stop/restart/reload a service on a PVE node. Dry-run by default — the
PLAN flags lockout-class services (sshd/pveproxy/pvedaemon/pve-cluster/corosync/networking/
...) as HIGH because stop/restart can sever the management plane or break quorum. There is
NO auto-undo for a service control. confirm=True to execute. Async — returns a task UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `service` | string | yes |  |
| `action` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_service_status`

Get the current state of a single service on a PVE node (read).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `service` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_services_list`

List all services on a PVE node (read-only). Returns a list of service dicts
with name, state (running/dead/inactive), and description for each service.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_startall`

MUTATION: start all (or filtered) guests on a PVE node.

RISK_MEDIUM. Reversible — the inverse of pve_node_stopall. vms = optional CSV of VMIDs
to filter the scope. confirm=True to execute.

POST /nodes/{node}/startall
Smoke-confirm: endpoint and vms param format not live-verified. May return task UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `vms` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_status`

Read Proxmox node health and resource status (read-only). Returns node metrics including
total capacity, current usage, CPU, memory, disk state, and operational status. See pve_diagnose
for detailed per-node diagnostics including failed tasks.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_stopall`

MUTATION: stop ALL (or filtered) running guests on a PVE node.

RISK_HIGH — fleet-wide service outage unless vms filters the scope.
Reversible via pve_node_startall, but guests must be restarted inside. confirm=True to execute.

POST /nodes/{node}/stopall
Smoke-confirm: endpoint and vms param format not live-verified. May return task UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `vms` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_storage_backend_create`

MUTATION: create a storage backend on the node (lvm/lvmthin/zfs/directory).

Per-backend required params:
  zfs:       devices (comma-sep disk list) + raidlevel
  lvm/lvmthin: devices (single disk)
  directory: devices (disk path) + filesystem (e.g. ext4)

The named disk(s) are consumed by the new backend. confirm=True to execute.

POST /nodes/{node}/disks/{backend}
Smoke-confirm: endpoint and body shape not live-verified. May return a task UPID (async).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `backend` | string | yes |  |
| `name` | string | yes |  |
| `devices` | string (nullable) | no | (default: `null`) |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |
| `kw` | any | yes |  |

#### `pve_node_storage_backend_delete`

MUTATION: destroy a storage backend on the node.

RISK_HIGH, NO UNDO — backend-specific blast:
  zfs:        destroys the zpool and ALL data on it
  lvm/lvmthin: removes the VG — any storage built on it breaks
  directory:  removes the directory mapping (data on disk may persist)

confirm=True to execute.

DELETE /nodes/{node}/disks/{backend}/{name}
Smoke-confirm: endpoint and params shape not live-verified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `backend` | string | yes |  |
| `name` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `cleanup` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_storage_backend_list`

List storage backends of a type on a PVE node (read).

backend ∈ {lvm, lvmthin, zfs, directory}.
GET /nodes/{node}/disks/{backend}
Smoke-confirm: response shape not live-verified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `backend` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_subscription`

Read a Proxmox node's subscription status (read-only). Returns a dict with
status, product name, check time, next due date, and subscription level.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_syslog`

Fetch syslog entries from a PVE node (read). limit capped at 5000.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `limit` | integer | no | (default: `100`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_time_get`

Get the current time and timezone of a PVE node (read).

GET /nodes/{node}/time — returns {localtime, time, timezone}.
Smoke-confirm: response shape not live-verified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_time_set`

MUTATION: set the timezone on a PVE node.

RISK_LOW. CAPTURE: reads the current timezone before planning; if unreadable → complete=False.
Revert by re-applying the captured timezone. confirm=True to execute.

PUT /nodes/{node}/time
Smoke-confirm: endpoint and body shape not live-verified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `timezone` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_notification_endpoint_create`

MUTATION: create a PVE notification endpoint. ep_type = gotify|smtp|sendmail|webhook.
Dry-run by default. confirm=True to execute. `options` carries the endpoint-specific config
(sendmail: {"mailto-user":"root@pam"}; gotify: {"server":..,"token":..}; webhook: {"url":..}).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ep_type` | string | yes |  |
| `name` | string | yes |  |
| `comment` | string (nullable) | no | (default: `null`) |
| `options` | object (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_notification_endpoint_delete`

MUTATION: delete a PVE notification endpoint. ep_type = gotify|smtp|sendmail|webhook.
Dry-run by default — captures current config. confirm=True to execute.
WARN: matchers referencing this endpoint will silently fail until it is restored.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ep_type` | string | yes |  |
| `name` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_notification_endpoint_list`

List all PVE notification endpoints (read-only). Returns a list of dicts for
each configured delivery channel (gotify, SMTP, sendmail, webhook), containing
type, name, and endpoint-specific configuration.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_notification_endpoint_update`

MUTATION: update a PVE notification endpoint. ep_type = gotify|smtp|sendmail|webhook.
Dry-run by default — captures current config. confirm=True to execute. `options` carries the
endpoint-specific fields to change (same shape as create).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ep_type` | string | yes |  |
| `name` | string | yes |  |
| `comment` | string (nullable) | no | (default: `null`) |
| `options` | object (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_notification_matcher_delete`

MUTATION: delete a PVE notification matcher. Dry-run by default.
confirm=True to execute. WARN: alerts matching this filter go un-routed after deletion.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_notification_matcher_set`

MUTATION: create-or-update a PVE notification matcher (alert routing rule).
Dry-run by default. confirm=True to execute.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `comment` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_notification_test`

MUTATION: send a test notification to a PVE notification target. Dry-run by default.
confirm=True to execute. SENDS A REAL NOTIFICATION — recipients will receive it.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_overbroad_grants`

Surface over-broad ACL grants (Administrator role or root '/' path) as a diagnostic (read).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_pool_create`

MUTATION: create an (empty) resource pool. Dry-run by default (PLAN = additive, LOW).
confirm=True to execute. Synchronous.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `poolid` | string | yes |  |
| `comment` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_pool_delete`

MUTATION: delete a resource pool. Dry-run by default — the PLAN warns ACLs on /pool/{poolid}
are orphaned and the pool must be empty first (members are NOT deleted). confirm=True to
execute. Synchronous.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `poolid` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_pool_get`

Retrieve a single resource pool's configuration and complete member list by pool ID
(read-only). Returns the pool's config including all VMs and storage resources assigned.
Use pve_pools_list to enumerate all pools.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `poolid` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_pool_update`

MUTATION: add (delete=False) or remove (delete=True) pool members. Dry-run by default —
the PLAN notes membership re-scopes ACL coverage. confirm=True to execute. Synchronous.
delete=True with no vms/storage is refused (ambiguous).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `poolid` | string | yes |  |
| `vms` | string (nullable) | no | (default: `null`) |
| `storage` | string (nullable) | no | (default: `null`) |
| `delete` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_pools_list`

List all resource pools defined cluster-wide (read-only). Returns a list of pool dicts
with pool IDs and optional comments. Use pve_pool_get to fetch a pool's detailed
configuration and complete member list.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_realm_create`

MUTATION: create an auth realm. Dry-run by default; confirm=True to execute.
`options` carries the type-specific fields PVE requires (ldap: server1/base_dn/user_attr;
ad: domain/server1; openid: issuer-url/client-id) — passed verbatim; PVE validates them.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes |  |
| `realm_type` | string | yes |  |
| `comment` | string (nullable) | no | (default: `null`) |
| `options` | object (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_realm_delete`

MUTATION (HIGH, lockout-class): delete an auth realm. Dry-run by default — the PLAN reads
users to count who can no longer log in, and refuses built-in pam/pve. confirm=True.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_realm_get`

Get a realm's full config (read-only). Returns realm type, comment, TFA requirement, and
type-specific settings (server/base_dn for ldap; domain/server1 for ad; issuer-url/client-id
for openid). Use pve_realm_create/update/delete to manage realms.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_realm_update`

MUTATION: update a realm. Dry-run by default — built-in pam/pve realms are flagged HIGH
(changing them risks breaking logins). confirm=True. `options` carries type-specific fields
(server1/base_dn/etc.) passed verbatim; PVE validates them.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes |  |
| `comment` | string (nullable) | no | (default: `null`) |
| `options` | object (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_realms_list`

List authentication realms/domains configured in Proxmox (read-only). Returns each realm's
type (pam/pve/ldap/ad/openid), comment, TFA setting, and default flag. Use pve_realm_get for
type-specific config; use pve_realm_create/update/delete to manage realms.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_replication_create`

MUTATION: create a PVE replication job. Dry-run by default.
rep_type is typically 'local'. confirm=True to execute.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `rep_id` | string | yes |  |
| `rep_type` | string | yes |  |
| `target` | string | yes |  |
| `schedule` | string (nullable) | no | (default: `null`) |
| `rate` | number (nullable) | no | (default: `null`) |
| `disable` | boolean (nullable) | no | (default: `null`) |
| `comment` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_replication_delete`

MUTATION: delete a PVE replication job. Dry-run by default — captures current config.
confirm=True to execute. Replication ceases; existing replicated data is NOT removed.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `rep_id` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_replication_update`

MUTATION: update a PVE replication job. Dry-run by default — captures current config.
confirm=True to execute. Config-only; in-flight replication is not immediately disrupted.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `rep_id` | string | yes |  |
| `schedule` | string (nullable) | no | (default: `null`) |
| `rate` | number (nullable) | no | (default: `null`) |
| `disable` | boolean (nullable) | no | (default: `null`) |
| `comment` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_restore`

MUTATION (DESTRUCTIVE if it overwrites an existing guest): restore a guest from a backup
archive. Dry-run by default — the PLAN states whether it CREATES or OVERWRITES. confirm=True to
execute. Async — returns a task UPID. pool: place the restored guest in a resource pool.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `archive` | string | yes |  |
| `storage` | string | yes |  |
| `kind` | string | no | (default: `"lxc"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `force` | boolean | no | (default: `false`) |
| `pool` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_role_create`

MUTATION: create a custom role with an optional privilege set. Dry-run by default (MEDIUM
risk — inert until an ACL entry references it). Returns the plan preview; confirm=True to
execute. privs format: comma-separated privilege names (e.g. 'VM.PowerMgmt,VM.Config.Disk').

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `roleid` | string | yes |  |
| `privs` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_role_delete`

MUTATION (HIGH): delete a role. Dry-run by default — the PLAN reads ACLs to count grants
that will break, and refuses built-in roles. confirm=True.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `roleid` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_role_update`

MUTATION: change a role's privileges. Dry-run by default — built-in roles (Administrator,
PVEAdmin, …) are flagged HIGH (changing them re-scopes every ACL using them). confirm=True.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `roleid` | string | yes |  |
| `privs` | string (nullable) | no | (default: `null`) |
| `append` | boolean (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_roles_list`

List all Proxmox roles and their privileges (read-only). Returns each role's id, privilege
set, and whether it is built-in. Use pve_role_create/update/delete to modify roles; use
pve_acl_list to see which principals hold which roles at which paths.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_rollback`

MUTATION (DESTRUCTIVE): roll a guest back to a snapshot — discards ALL changes since it.
Dry-run by default (the PLAN spells out the blast radius); confirm=True to execute. Async -> UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `snapname` | string | yes |  |
| `kind` | string | no | (default: `"lxc"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_apply`

MUTATION (HIGH RISK): apply pending SDN config changes (cluster-scoped).
Dry-run by default — the PLAN surfaces pending zones/vnets. confirm=True to execute.
A misconfigured SDN can disrupt virtual networking for ALL guests cluster-wide.
May return a UPID (async) or None (sync) — outcome='submitted' in either case.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_subnet_create`

MUTATION: create an SDN subnet (PENDING). `subnet` is a CIDR (e.g. 10.0.0.0/24); `options`
carries gateway/snat/dhcp params. Dry-run by default. RISK_LOW (staging; inert until apply).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vnet` | string | yes |  |
| `subnet` | string | yes |  |
| `options` | object (nullable) | no | (default: `null`) |
| `lock_token` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_subnet_delete`

MUTATION: delete an SDN subnet (PENDING). `subnet` is the id from pve_sdn_subnet_list.
Dry-run by default. RISK_MEDIUM (staging a removal an apply would enact).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vnet` | string | yes |  |
| `subnet` | string | yes |  |
| `lock_token` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_subnet_list`

List subnets in a vnet (read-only). Returns subnet CIDR, gateway, dhcp,
snat, and dns settings. Use pve_sdn_subnet_create to add and pve_sdn_apply to
commit.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vnet` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_subnet_update`

MUTATION: update an SDN subnet (PENDING). `subnet` is the id from pve_sdn_subnet_list.
Dry-run by default. RISK_LOW (staging).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vnet` | string | yes |  |
| `subnet` | string | yes |  |
| `options` | object (nullable) | no | (default: `null`) |
| `delete` | array<string> (nullable) | no | (default: `null`) |
| `digest` | string (nullable) | no | (default: `null`) |
| `lock_token` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_vnet_create`

MUTATION: create an SDN vnet in a zone (PENDING). `options` carries tag/alias/vlanaware/etc.
Dry-run by default. RISK_LOW (staging; inert until pve_sdn_apply).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vnet` | string | yes |  |
| `zone` | string | yes |  |
| `options` | object (nullable) | no | (default: `null`) |
| `lock_token` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_vnet_delete`

MUTATION: delete an SDN vnet (PENDING). Dry-run by default — the PLAN shows the current vnet.
PVE refuses if a subnet still references it. RISK_MEDIUM.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vnet` | string | yes |  |
| `lock_token` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_vnet_update`

MUTATION: update an SDN vnet (PENDING — inert until pve_sdn_apply).
Options sets fields (tag/alias/vlanaware/etc), delete removes keys. Dry-run
by default. RISK_LOW (staging, no live network effect).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vnet` | string | yes |  |
| `options` | object (nullable) | no | (default: `null`) |
| `delete` | array<string> (nullable) | no | (default: `null`) |
| `digest` | string (nullable) | no | (default: `null`) |
| `lock_token` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_vnets_list`

List SDN vnets in the cluster (read-only). Returns vnet name, zone, tag,
alias, and vlanaware state. Use pve_sdn_vnet_create to add and pve_sdn_apply
to commit.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_zone_create`

MUTATION: create an SDN zone (PENDING — inert until pve_sdn_apply, NOT applied here).
`zone_type` is simple/vlan/qinq/vxlan/evpn/faucet; `options` carries type-specific params.
Dry-run by default. RISK_LOW (staging, no live network effect).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `zone` | string | yes |  |
| `zone_type` | string | yes |  |
| `options` | object (nullable) | no | (default: `null`) |
| `lock_token` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_zone_delete`

MUTATION: delete an SDN zone (PENDING). Dry-run by default — the PLAN shows the current zone.
PVE refuses if a vnet still references it. RISK_MEDIUM (staging a removal an apply would enact).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `zone` | string | yes |  |
| `lock_token` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_zone_update`

MUTATION: update an SDN zone (PENDING). `options` sets fields; `delete` unsets keys.
Dry-run by default. RISK_LOW (staging; inert until pve_sdn_apply).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `zone` | string | yes |  |
| `options` | object (nullable) | no | (default: `null`) |
| `delete` | array<string> (nullable) | no | (default: `null`) |
| `digest` | string (nullable) | no | (default: `null`) |
| `lock_token` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_zones_list`

List SDN zones in the cluster (read-only). Returns zone id, type
(simple/vlan/qinq/vxlan/evpn/faucet), and state. Use pve_sdn_zone_create to add and
pve_sdn_apply to commit.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_security_groups_list`

List the cluster's firewall security groups (read-only).

Returns each group's name, comment, and digest. A security group is a reusable
named rule set you attach to a VM/node firewall; use pve_firewall_rules_list to read
a specific scope's active rules.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_snapshot_create`

MUTATION: create a snapshot (a restore point). Dry-run by default; confirm=True to execute.
Async — returns the task UPID; poll pve_task_status. Needs snapshot-capable storage (ZFS/BTRFS/LVM-thin).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `snapname` | string | yes |  |
| `kind` | string | no | (default: `"lxc"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `description` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_snapshot_delete`

MUTATION: delete a snapshot (removes a restore point). Dry-run by default; confirm=True to execute.
Async -> UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `snapname` | string | yes |  |
| `kind` | string | no | (default: `"lxc"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `force` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_snapshot_list`

List a guest's snapshots (read-only). Returns each snapshot's name, description, parent,
and creation time, plus the synthetic 'current' node showing live state. Works for both VMs
and containers (kind='qemu' or 'lxc'). Use pve_snapshot_create / pve_rollback to act on them.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `kind` | string | no | (default: `"lxc"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_storage_config_get`

Retrieve a single storage definition from storage.cfg by storage ID (read-only).
Returns the storage's complete configuration including type, paths, servers, and access
settings. Use pve_storage_config_list to enumerate all storages.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_storage_config_list`

List all storage definitions from storage.cfg cluster-wide (read-only). Returns a list
of storage dicts with IDs, types, paths, and server addresses. Use
pve_storage_config_get to fetch a single storage's complete configuration.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_storage_content`

List a storage's content, optionally filtered (content = iso | vztmpl | backup) (read).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `content` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_storage_content_delete`

MUTATION: delete a content volume (ISO / template / backup) from storage. Dry-run by default
(HIGH risk for a backup volume); confirm=True. Async — UPID or null.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes |  |
| `volid` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_storage_create`

MUTATION: define a new storage (storage.cfg). Dry-run by default. confirm=True to execute.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes |  |
| `storage_type` | string | yes |  |
| `content` | string (nullable) | no | (default: `null`) |
| `path` | string (nullable) | no | (default: `null`) |
| `server` | string (nullable) | no | (default: `null`) |
| `export` | string (nullable) | no | (default: `null`) |
| `nodes` | string (nullable) | no | (default: `null`) |
| `disable` | boolean | no | (default: `false`) |
| `shared` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_storage_delete`

MUTATION (HIGH): remove a storage definition cluster-wide. Dry-run by default — the PLAN
warns guest disks/backups living only there become inaccessible (data not erased). confirm=True.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_storage_download`

MUTATION: download an ISO (content=iso) or CT template (content=vztmpl) from a URL into a
storage. Dry-run by default; confirm=True. Async — returns a UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes |  |
| `content` | string | yes |  |
| `url` | string | yes |  |
| `filename` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `checksum` | string (nullable) | no | (default: `null`) |
| `checksum_algorithm` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_storage_status`

Read a storage backend's capacity and state (read-only). Returns total size, used space,
available free space, and enabled status. Use pve_storage_content to list ISOs, templates,
and backups stored on it.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_storage_update`

MUTATION: update a storage definition. Dry-run by default (disable=True warns guests lose
disk access). confirm=True to execute.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes |  |
| `content` | string (nullable) | no | (default: `null`) |
| `nodes` | string (nullable) | no | (default: `null`) |
| `disable` | boolean (nullable) | no | (default: `null`) |
| `shared` | boolean (nullable) | no | (default: `null`) |
| `delete` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_task_log`

Retrieve a task's log output by UPID (read-only). Returns the task's log lines with
line numbers, paginated via start/limit. Use pve_task_wait for completion polling, or
pve_tasks_list to find a UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `upid` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `start` | integer | no | (default: `0`) |
| `limit` | integer | no | (default: `50`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_task_status`

Status of an async Proxmox task (running/stopped + exit status) — poll snapshot/rollback ops (read).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `upid` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_task_stop`

MUTATION (HIGH): stop (cancel) a running task. Dry-run by default — the PLAN warns that
stopping a backup/restore/migration/clone mid-flight can leave the target inconsistent, with
NO undo. confirm=True to execute. Synchronous cancellation signal (returns null).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `upid` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_task_wait`

Block until an async Proxmox task reaches a terminal state — or the timeout — then report the
outcome (read). The ergonomic complement to the submit-an-async-op tools (migrate / backup /
restore / clone / rollback / snapshot + guest create) that return a UPID: wait for completion
without hand-rolling a pve_task_status poll loop.

Returns {upid, finished, succeeded, status, exitstatus, timed_out, polls}. `succeeded` is
fail-closed (finished AND exitstatus == "OK"); a failed or timed-out task is reported, not raised.
timeout is clamped 1..600s, interval 1..60s. Use pve_task_log for the full log.

(Proximo's native UPID model — NOT the MCP Tasks protocol, which was removed from the spec.)

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `upid` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `timeout` | integer | no | (default: `120`) |
| `interval` | integer | no | (default: `2`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_tasks_list`

List recent tasks on a node (read). limit 1-1000 (clamped).

Caveat: this is a windowed, per-node slice — node defaults to the configured node, and
only the `limit` most-recent tasks return. A task on another node or outside the window
is absent without being dead. Never conclude a backup failed from absence here — verify
against pve_backup_list or pbs_snapshots_list.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `limit` | integer | no | (default: `50`) |
| `errors` | boolean | no | (default: `false`) |
| `vmid` | string (nullable) | no | (default: `null`) |
| `typefilter` | string (nullable) | no | (default: `null`) |
| `statusfilter` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_template_convert`

MUTATION (IRREVERSIBLE): convert a guest into a template — effectively one-way. Dry-run by
default (the PLAN flags it HIGH/irreversible); confirm=True to execute.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `kind` | string | no | (default: `"qemu"`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_tfa_delete`

MUTATION (HIGH RISK): delete a user's TFA factor. Dry-run by default — the PLAN shows how many
factors remain and warns this WEAKENS the account (and can lock the user out if it's the last
factor on a TFA-required realm). `password` (if PVE requires it) is passed through but never
logged. confirm=True to execute.

NOTE (live-verified PVE 9.1.7): PVE requires a ticket-based login session — NOT an API token —
to mutate TFA, returning `403 ... need proper ticket` under token auth. Proximo is token-authed,
so this delete will 403 on PVE; the read tools (pve_tfa_get/pve_tfa_list) work normally.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes |  |
| `tfa_id` | string | yes |  |
| `password` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_tfa_get`

Read a user's TFA entries (read-only). Returns list of entries if tfa_id is omitted; a
single entry dict if tfa_id is specified. Each entry includes factor type, id, and metadata.
Use pve_tfa_delete (confirm=True) to remove a factor (RISK_HIGH — can lock the user out).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes |  |
| `tfa_id` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_tfa_list`

List all per-user TFA (two-factor) entries across the cluster (read-only). Returns each
entry's userid, factor type (totp/webauthn/yubico/recovery), factor id, and metadata. Use pve_tfa_get
for one user's entries; use pve_tfa_delete (confirm=True) to remove a factor (RISK_HIGH).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_token_create`

MUTATION: create an API token for a user.

Dry-run by default — the PLAN shows risk (privsep=False is HIGH: token inherits ALL owner perms).
confirm=True to execute. The token secret (value) is returned ONCE to the caller and is NEVER
written to the audit ledger. Synchronous.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes |  |
| `tokenid` | string | yes |  |
| `privsep` | boolean | no | (default: `true`) |
| `comment` | string (nullable) | no | (default: `null`) |
| `expire` | integer (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_token_revoke`

MUTATION (IRREVERSIBLE): permanently revoke an API token.

Dry-run by default — the PLAN flags HIGH: revocation is permanent, the secret is gone forever.
confirm=True to execute. Synchronous.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes |  |
| `tokenid` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_tokens_list`

List API tokens for a specific user (read-only). Returns each token's id, comment, expiry,
and privsep (privilege separation) flag — NOT the secret (shown only at creation). userid
format: 'user@realm'. Use pve_token_create/revoke to manage tokens.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_user_create`

MUTATION: create a user. Dry-run by default (note: password is set separately — the user
cannot log in until then). confirm=True to execute.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes |  |
| `comment` | string (nullable) | no | (default: `null`) |
| `email` | string (nullable) | no | (default: `null`) |
| `enable` | boolean (nullable) | no | (default: `null`) |
| `expire` | integer (nullable) | no | (default: `null`) |
| `groups` | string (nullable) | no | (default: `null`) |
| `firstname` | string (nullable) | no | (default: `null`) |
| `lastname` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_user_delete`

MUTATION (HIGH): delete a user. Dry-run by default — the PLAN reads the user's ACLs/tokens
to show what access vanishes (permanent, no undo; admin = lockout risk). confirm=True.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_user_get`

Get a user's full config (read-only). Returns userid, enabled flag, expiry, email, comment,
group membership, API tokens, and firstname/lastname. Use pve_user_create/update/delete to
modify the user; use pve_acl_list to see their effective permissions.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_user_update`

MUTATION: update a user (enable=False stops login; group changes re-scope access).
Dry-run by default. confirm=True to execute.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes |  |
| `comment` | string (nullable) | no | (default: `null`) |
| `email` | string (nullable) | no | (default: `null`) |
| `enable` | boolean (nullable) | no | (default: `null`) |
| `expire` | integer (nullable) | no | (default: `null`) |
| `groups` | string (nullable) | no | (default: `null`) |
| `firstname` | string (nullable) | no | (default: `null`) |
| `lastname` | string (nullable) | no | (default: `null`) |
| `append` | boolean (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_users_list`

List all Proxmox users across every realm (read-only). Returns each user's id (user@realm),
enabled flag, expiry, group membership, email, and comment. Use pve_user_get for one user's
full config, tokens, and effective ACL.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

## Proxmox Backup Server (PBS)

#### `pbs_datastore_create`

MUTATION (MEDIUM): create a new PBS datastore at the given path.

Dry-run by default — additive, but a misconfigured path can conflict with existing storage.
PBS datastore creation is an async worker task (UPID) → outcome='submitted' (not 'ok').
No rollback primitive. confirm=True to execute.

POST /config/datastore
Smoke-confirm: gc-schedule / prune-schedule / notification-mode param names; sync-vs-async.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `path` | string | yes |  |
| `gc_schedule` | string (nullable) | no | (default: `null`) |
| `prune_schedule` | string (nullable) | no | (default: `null`) |
| `notification_mode` | string (nullable) | no | (default: `null`) |
| `comment` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_datastore_delete`

MUTATION: delete a PBS datastore. Dry-run by default. RISK IS CONDITIONAL:

destroy_data=False (default) → MEDIUM: detaches the datastore config; backup CHUNKS
  REMAIN ON DISK and the datastore is re-addable to recover.
destroy_data=True → HIGH, IRREVERSIBLE: PERMANENTLY DESTROYS ALL backup data in the
  named datastore — no recovery possible.

PBS deletion is an async worker task (UPID) → outcome='submitted'. confirm=True to execute.

DELETE /config/datastore/{name}
Smoke-confirm: destroy-data / keep-job-configs param names; sync-vs-async.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `destroy_data` | boolean | no | (default: `false`) |
| `keep_job_configs` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_datastore_get`

Get full config of one PBS datastore by name (read). Returns path, gc-schedule, etc.
For runtime usage stats use pbs_datastore_status instead. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_datastore_status`

Get runtime usage statistics for one PBS datastore (read-only). Returns total
capacity, used bytes, and available bytes. Use pbs_datastores_list to enumerate
datastores (with backend type) or pbs_gc_status for garbage-collection state.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_datastore_update`

MUTATION (MEDIUM): update PBS datastore configuration. Dry-run by default.

CAPTURE: reads current config before planning; on read failure the plan is marked incomplete.
Changing gc-schedule / prune-schedule affects data retention cluster-wide.
No rollback primitive — revert by re-applying the captured config. confirm=True to execute.

PUT /config/datastore/{name}
Smoke-confirm: accepted param names (hyphenated vs underscored).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `gc_schedule` | string (nullable) | no | (default: `null`) |
| `prune_schedule` | string (nullable) | no | (default: `null`) |
| `notification_mode` | string (nullable) | no | (default: `null`) |
| `comment` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_datastores_list`

List all PBS datastores (read-only). Returns datastore objects with store name,
backend type, and mount status. Use pbs_datastore_status for runtime usage statistics
or pbs_datastore_get for full configuration. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_gc_start`

MUTATION (HIGH): start garbage collection on a PBS datastore. Dry-run by default — GC
permanently removes unreferenced chunks (no undo). confirm=True to execute. Async — UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_gc_status`

Get garbage-collection status for one PBS datastore (read-only). Returns GC
schedule, current state, disk/index statistics, and pending/removed chunk counts.
Use pbs_gc_start to execute garbage collection or pbs_datastore_status for capacity.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_group_change_owner`

MUTATION (MEDIUM): reassign the owner of a PBS backup group. Dry-run by default.

The new owner controls deletion and prune of this backup group.
The previous owner loses those permissions immediately.
No PBS snapshot primitive — revert by re-assigning the owner back. confirm=True to execute.

PUT /admin/datastore/{store}/change-owner
Smoke-confirm: exact path + new-owner vs owner param name.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes |  |
| `backup_type` | string | yes |  |
| `backup_id` | string | yes |  |
| `new_owner` | string | yes |  |
| `ns` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_job_create`

MUTATION: create a PBS scheduled job. job_type = sync|verify|prune. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PBS_* config. Config-only; no existing data affected.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `job_type` | string | yes |  |
| `job_id` | string | yes |  |
| `store` | string (nullable) | no | (default: `null`) |
| `schedule` | string (nullable) | no | (default: `null`) |
| `ns` | string (nullable) | no | (default: `null`) |
| `comment` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_job_delete`

MUTATION: delete a PBS scheduled job. job_type = sync|verify|prune. Dry-run by default —
captures current config. confirm=True to execute. Schedule removed; backup data NOT deleted.
Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `job_type` | string | yes |  |
| `job_id` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_job_run`

MUTATION: trigger a PBS scheduled job immediately. job_type = sync|verify|prune.
Dry-run by default. confirm=True to execute. Async — returns UPID.
Needs PROXIMO_PBS_* config. Prune runs may delete snapshots per the retention policy.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `job_type` | string | yes |  |
| `job_id` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_job_update`

MUTATION: update a PBS scheduled job. job_type = sync|verify|prune. Dry-run by default —
captures current config. confirm=True to execute. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `job_type` | string | yes |  |
| `job_id` | string | yes |  |
| `schedule` | string (nullable) | no | (default: `null`) |
| `ns` | string (nullable) | no | (default: `null`) |
| `comment` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_jobs_list`

List all PBS scheduled jobs of the given type (read). job_type = sync|verify|prune.
Returns all jobs with their configs. Raises on invalid job_type. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `job_type` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_namespace_create`

MUTATION: create a namespace within a PBS datastore. Dry-run by default (additive, LOW).
confirm=True to execute. Synchronous.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes |  |
| `name` | string | yes |  |
| `parent` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_namespace_delete`

MUTATION: delete a namespace from a PBS datastore. Dry-run by default — delete_groups=True
is HIGH (it deletes all backup groups/snapshots inside the namespace, no undo). confirm=True
to execute. Synchronous.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes |  |
| `ns` | string | yes |  |
| `delete_groups` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_namespaces_list`

List namespaces within a PBS datastore with optional hierarchical filtering (read-only).
Returns each namespace's hierarchical path (the `ns` field); optionally filter by
parent namespace or limit recursion depth. Use pbs_namespace_create to add namespaces.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes |  |
| `parent` | string (nullable) | no | (default: `null`) |
| `max_depth` | integer (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_prune`

MUTATION: prune backup snapshots per a retention policy. TWO safety gates: confirm
(Proximo dry-run vs execute) AND dry_run (PBS-side preview). dry_run=True (default) only
previews; dry_run=False DELETES recovery points (PLAN is HIGH, no undo). confirm=True to
execute. Synchronous — returns prune decisions.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes |  |
| `keep_last` | integer (nullable) | no | (default: `null`) |
| `keep_daily` | integer (nullable) | no | (default: `null`) |
| `keep_weekly` | integer (nullable) | no | (default: `null`) |
| `keep_monthly` | integer (nullable) | no | (default: `null`) |
| `keep_yearly` | integer (nullable) | no | (default: `null`) |
| `ns` | string (nullable) | no | (default: `null`) |
| `backup_type` | string (nullable) | no | (default: `null`) |
| `backup_id` | string (nullable) | no | (default: `null`) |
| `dry_run` | boolean | no | (default: `true`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_realm_sync`

MUTATION: sync PBS auth realm (LDAP/AD) users. Dry-run by default.
confirm=True to execute. Async — returns UPID. Needs PROXIMO_PBS_* config.
remove_vanished=True also removes PBS users no longer in the directory.
(2026-07-10 audit: the old 'scope' param was dropped — PBS /sync has no such field.)

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes |  |
| `remove_vanished` | boolean (nullable) | no | (default: `null`) |
| `dry_run` | boolean (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_remote_create`

MUTATION (MEDIUM): create a PBS remote sync-source. Dry-run by default.

PRIVATE PASSWORD REDACTION: 'password' is a remote user credential. It is
UNCONDITIONALLY redacted from the server-side plan, change, current state, detail,
and audit ledger. Only {"password":"[redacted]"} is recorded on those surfaces.
L02 NOTE: the MCP tool-call itself is a structured JSON object in which 'password' appears
as a plain parameter — it is visible in the LLM's output token stream and in any MCP client
log. This is an MCP-protocol property; server-side redaction protects the ledger only.
The TLS cert 'fingerprint' is PUBLIC data — it is NOT redacted.

No rollback primitive — revert by deleting the remote (pbs_remote_delete). confirm=True to execute.

POST /config/remote
Smoke-confirm: auth-id vs authid param name; port param name.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `host` | string | yes |  |
| `auth_id` | string | yes |  |
| `password` | string | yes |  |
| `fingerprint` | string (nullable) | no | (default: `null`) |
| `port` | integer (nullable) | no | (default: `null`) |
| `comment` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_remote_delete`

MUTATION (MEDIUM): remove a PBS remote and its stored credentials. Dry-run by default.

After deletion: any sync jobs referencing this remote break; re-add needs the password
re-supplied. No rollback primitive — re-create with pbs_remote_create to recover.
confirm=True to execute.

DELETE /config/remote/{name}
Smoke-confirm: response shape on success.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_remote_get`

Get the config of one PBS remote sync-source by name (read). No password returned.
Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_remote_update`

MUTATION (MEDIUM): update an existing PBS remote. Dry-run by default.

CAPTURE: reads current (non-secret) config before planning; on failure plan is marked incomplete.
PRIVATE PASSWORD REDACTION: if 'password' is provided it is UNCONDITIONALLY redacted from the
server-side plan, change, current state, detail, and audit ledger.
L02 NOTE: the MCP tool-call itself is a structured JSON object in which 'password' appears as
a plain parameter — visible in the LLM's output token stream and any MCP client log.
This is an MCP-protocol property; server-side redaction protects the ledger only.
The TLS cert 'fingerprint' is PUBLIC and appears in plans/logs for audit.
No rollback primitive — revert by re-applying captured config. confirm=True to execute.

PUT /config/remote/{name}
Smoke-confirm: auth-id param name; whether partial PUT is accepted.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `host` | string (nullable) | no | (default: `null`) |
| `auth_id` | string (nullable) | no | (default: `null`) |
| `password` | string (nullable) | no | (default: `null`) |
| `fingerprint` | string (nullable) | no | (default: `null`) |
| `port` | integer (nullable) | no | (default: `null`) |
| `comment` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_remotes_list`

List all PBS remote sync-sources (read). Passwords are never returned by the PBS API.
Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_snapshot_delete`

MUTATION (HIGH): delete a specific backup snapshot (a recovery point) from a PBS
datastore. Dry-run by default. Permanent — no undo. confirm=True to execute. Synchronous.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes |  |
| `backup_type` | string | yes |  |
| `backup_id` | string | yes |  |
| `backup_time` | integer | yes |  |
| `ns` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_snapshot_notes_set`

MUTATION (LOW): annotate a PBS snapshot with notes. Dry-run by default.

CAPTURE: reads current notes before planning; on failure the plan is marked incomplete.
Does not affect backup data, retention, or protection.
No PBS snapshot primitive — revert by re-applying the captured notes. confirm=True to execute.

PUT /admin/datastore/{store}/notes
Smoke-confirm: exact endpoint path + param names (backup-type, backup-id, backup-time).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes |  |
| `backup_type` | string | yes |  |
| `backup_id` | string | yes |  |
| `backup_time` | integer | yes |  |
| `notes` | string | yes |  |
| `ns` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_snapshot_protected_set`

MUTATION: set or clear the protected flag on a PBS snapshot. RISK IS CONDITIONAL:

protected=True  → LOW:  shields the snapshot from pruning and GC (protective).
protected=False → HIGH: SILENTLY re-enables pruning/GC — this recovery point can now
  be auto-deleted by the next prune job or GC run. No undo once auto-deleted.

No PBS snapshot primitive for rollback. Dry-run by default. confirm=True to execute.

PUT /admin/datastore/{store}/protected
Smoke-confirm: exact path + param names (backup-type, backup-id, backup-time, protected).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes |  |
| `backup_type` | string | yes |  |
| `backup_id` | string | yes |  |
| `backup_time` | integer | yes |  |
| `protected` | boolean | yes |  |
| `ns` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_snapshots_list`

List backup snapshots in a PBS datastore with optional filters (read-only). Returns
snapshot metadata including backup type, ID, timestamp, size, owner, and protection
status; filter by namespace, backup_type (vm/ct/host), or backup_id.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes |  |
| `ns` | string (nullable) | no | (default: `null`) |
| `backup_type` | string (nullable) | no | (default: `null`) |
| `backup_id` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_tasks_list`

List PBS tasks on a node (read). Defaults to 'localhost' (standard single-node PBS name).
Optionally filter: running=True for active tasks, errors=True for failed tasks.
Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | (default: `"localhost"`) |
| `limit` | integer (nullable) | no | (default: `null`) |
| `running` | boolean (nullable) | no | (default: `null`) |
| `errors` | boolean (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_traffic_control_delete`

MUTATION (LOW): remove a PBS traffic-control (bandwidth-limit) rule. Dry-run by default.

After deletion: backups run unthrottled on the matched network.
Recoverable by re-creating the rule with pbs_traffic_control_upsert. confirm=True to execute.

DELETE /config/traffic-control/{name}
Smoke-confirm: response shape on success.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_traffic_control_upsert`

MUTATION: create or update a PBS traffic-control (bandwidth-limit) rule. Dry-run by default.

Detects create-vs-update by reading the existing rule config (CAPTURE on update path):
  create → LOW:    additive, no existing rule changed.
  update → MEDIUM: changing rate limits can throttle backups or saturate the network.

A too-low rate-in or rate-out throttles PBS backups to a crawl.
No rollback primitive. confirm=True to execute.

POST (create) or PUT (update) /config/traffic-control[/{name}]
Smoke-confirm: create-vs-update dispatch; rate-in/rate-out/burst-in/burst-out/timeframe param names.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `rate_in` | integer (nullable) | no | (default: `null`) |
| `rate_out` | integer (nullable) | no | (default: `null`) |
| `network` | string (nullable) | no | (default: `null`) |
| `burst_in` | integer (nullable) | no | (default: `null`) |
| `burst_out` | integer (nullable) | no | (default: `null`) |
| `timeframe` | string (nullable) | no | (default: `null`) |
| `comment` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_traffic_controls_list`

List all PBS traffic-control bandwidth-limit rules (read-only). Returns active rules
with their rate-in/rate-out limits, network targets, and comment. Use
pbs_traffic_control_upsert to create or modify rules. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_verify_start`

MUTATION: start an integrity verification run on a PBS datastore. Dry-run by default —
non-destructive (read-only check) but heavy I/O. confirm=True to execute. Async — UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes |  |
| `ns` | string (nullable) | no | (default: `null`) |
| `backup_type` | string (nullable) | no | (default: `null`) |
| `backup_id` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

## Proxmox Mail Gateway (PMG)

#### `pmg_action_bcc_create`

MUTATION (LOW): create a BCC action object in the PMG RuleDB. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/action/bcc.
name: action object name. target: BCC recipient email address.
info: optional description. original: if True, send the ORIGINAL unmodified mail to the BCC
target (PMG's "send original mail" flag), not the processed copy — controls which version is sent.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `target` | string | yes |  |
| `info` | string (nullable) | no | (default: `null`) |
| `original` | boolean (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_action_bcc_update`

MUTATION (MEDIUM): update a BCC action object in the PMG RuleDB. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: PUT /config/ruledb/action/bcc/{id}.
id_: compound action object ID (e.g. '13_26') from pmg_action_objects_list.
Only non-None fields are sent; omitted fields keep current values.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `name` | string (nullable) | no | (default: `null`) |
| `target` | string (nullable) | no | (default: `null`) |
| `info` | string (nullable) | no | (default: `null`) |
| `original` | boolean (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_action_delete`

MUTATION (MEDIUM): delete an action object from the PMG RuleDB. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/action/objects/{id}.
id_: compound action object ID (e.g. '13_26') from pmg_action_objects_list.
NOTE: PMG rejects deletion of non-editable (built-in) system action objects.
Check 'editable' flag in pmg_action_objects_list before confirming.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_action_disclaimer_create`

MUTATION (LOW): create a disclaimer action object in the PMG RuleDB. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/action/disclaimer.
name: action name. disclaimer: disclaimer text. position: start|end.
add_separator: maps to API param 'add-separator' (bool).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `disclaimer` | string | yes |  |
| `info` | string (nullable) | no | (default: `null`) |
| `position` | string (nullable) | no | (default: `null`) |
| `add_separator` | boolean (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_action_disclaimer_update`

MUTATION (MEDIUM): update a disclaimer action object in the PMG RuleDB. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: PUT /config/ruledb/action/disclaimer/{id}.
id_: compound action object ID (e.g. '13_26') from pmg_action_objects_list.
position: start|end (validated). add_separator → 'add-separator'. Only non-None fields sent.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `name` | string (nullable) | no | (default: `null`) |
| `disclaimer` | string (nullable) | no | (default: `null`) |
| `info` | string (nullable) | no | (default: `null`) |
| `position` | string (nullable) | no | (default: `null`) |
| `add_separator` | boolean (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_action_field_create`

MUTATION (LOW): create a field-modification action object in the PMG RuleDB. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/action/field.
name: action object name. field: mail header field to set. value: value to assign.
info: optional description.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `field` | string | yes |  |
| `value` | string | yes |  |
| `info` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_action_field_update`

MUTATION (MEDIUM): update a field-modification action object in the PMG RuleDB. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: PUT /config/ruledb/action/field/{id}.
id_: compound action object ID (e.g. '13_26') from pmg_action_objects_list.
name, field, value all required — PMG 9.1 field action PUT rejects partial updates (400).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `name` | string | yes |  |
| `field` | string | yes |  |
| `value` | string | yes |  |
| `info` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_action_notification_create`

MUTATION (LOW): create a notification action object in the PMG RuleDB. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/action/notification.
name: action name. to: notification recipient. subject: notification subject.
body_text: notification body (maps to API param 'body'). attach: attach original message.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `to` | string | yes |  |
| `subject` | string | yes |  |
| `body_text` | string | yes |  |
| `info` | string (nullable) | no | (default: `null`) |
| `attach` | boolean (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_action_notification_update`

MUTATION (MEDIUM): update a notification action object in the PMG RuleDB. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: PUT /config/ruledb/action/notification/{id}.
id_: compound action object ID (e.g. '13_26') from pmg_action_objects_list.
name, to, subject, body_text all required — PMG 9.1 notification PUT rejects partial updates (400).
body_text maps to API param 'body'.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `name` | string | yes |  |
| `to` | string | yes |  |
| `subject` | string | yes |  |
| `body_text` | string | yes |  |
| `info` | string (nullable) | no | (default: `null`) |
| `attach` | boolean (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_action_objects_list`

List all PMG RuleDB action objects including non-editable (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/action/objects.
Returns all action objects; each entry carries an 'editable' flag.
Non-editable action objects are built-in and cannot be modified via the API.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_action_removeattachments_create`

MUTATION (LOW): create a remove-attachments action object in the PMG RuleDB. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/action/removeattachments.
name: action name. text: replacement text for removed attachments.
all_: maps to API param 'all' (bool; remove all attachments).
quarantine: if True, quarantine removed attachments.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `text` | string | yes |  |
| `info` | string (nullable) | no | (default: `null`) |
| `all_` | boolean (nullable) | no | (default: `null`) |
| `quarantine` | boolean (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_action_removeattachments_update`

MUTATION (MEDIUM): update a remove-attachments action object in the PMG RuleDB. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: PUT /config/ruledb/action/removeattachments/{id}.
id_: compound action object ID (e.g. '13_26') from pmg_action_objects_list.
all_: maps to API param 'all' (bool). Only non-None fields are sent.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `name` | string (nullable) | no | (default: `null`) |
| `text` | string (nullable) | no | (default: `null`) |
| `info` | string (nullable) | no | (default: `null`) |
| `all_` | boolean (nullable) | no | (default: `null`) |
| `quarantine` | boolean (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_backup_create`

MUTATION (LOW): create a PMG configuration backup. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: POST /nodes/{node}/backup.
notify: always|error|never (default never).
statistic: include mail statistics in backup (default True).
Backup is written to /var/lib/pmg/backup/ on the target node.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `notify` | string | no | (default: `"never"`) |
| `statistic` | boolean | no | (default: `true`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_doctor`

PMG connectivity + credential/permission preflight (read). Checks /nodes/{node}/version
and /access/users. A successful /version call means ticket login also succeeded —
connectivity and credentials are proven together. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified: PMG has no /access/permissions endpoint (that is PVE-only);
/access/users is the closest equivalent and returns the same user/role information.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_domain_create`

MUTATION (LOW): create a managed mail domain. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: POST /config/domains.
domain: domain name to add (e.g. 'example.com').

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `domain` | string | yes |  |
| `comment` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_domain_delete`

MUTATION (MEDIUM): delete a managed mail domain. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: DELETE /config/domains/{domain}.
Mail routing rules referencing this domain may break — review before confirming.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `domain` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_domains_list`

List PMG managed mail domains (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified: /config/domains path and response shape confirmed via
pmg-smoke.py W1 round-trip and W3 full domain create/list/delete cycle.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_mynetworks_add`

MUTATION (LOW): add a CIDR to the PMG mynetworks trusted relay list. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: POST /config/mynetworks.
cidr: network in CIDR notation (e.g. '10.0.0.0/8'). Only add CIDRs you control.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `cidr` | string | yes |  |
| `comment` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_mynetworks_remove`

MUTATION (MEDIUM): remove a CIDR from the PMG mynetworks trusted relay list. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: DELETE /config/mynetworks/{cidr} (CIDR URL-encoded).
Internal senders in the range will be subject to spam filtering after removal.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `cidr` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_node_rrddata`

Get PMG node RRD performance data (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /nodes/{node}/rrddata.
timeframe: REQUIRED — hour|day|week|month|year.
cf: consolidation function AVERAGE|MAX (optional).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `timeframe` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `cf` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_node_status`

Get PMG node cpu/mem/disk/uptime status (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified: /nodes/{node}/status path and response shape confirmed via
pmg-smoke.py W1 round-trip (node_status PASS).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_node_syslog`

Get PMG node syslog entries (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /nodes/{node}/syslog.
limit: max entries; service: filter by service name.
since/until: time range; start: pagination offset.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `limit` | integer (nullable) | no | (default: `null`) |
| `service` | string (nullable) | no | (default: `null`) |
| `since` | string (nullable) | no | (default: `null`) |
| `until` | string (nullable) | no | (default: `null`) |
| `start` | integer (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_postfix_flush`

MUTATION (LOW): flush all Postfix queues (immediate re-delivery attempt). Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: POST /nodes/{node}/postfix/flush_queues.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_postfix_qshape`

Get PMG Postfix queue shape (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified: /nodes/{node}/postfix/qshape returns a list of
dicts (one row per domain + a TOTAL row with queue-age bucket counts).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_action`

MUTATION (MEDIUM; HIGH for action='delete' — permanent, irreversible). Apply an action to
quarantined message(s). Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

action: one of deliver|delete|mark-seen|mark-unseen|blocklist|welcomelist.
mail_ids: single mail ID or comma-separated list.
PMG 9.1 live-proven 2026-06-26: POST /quarantine/content — delete and deliver
both confirmed against real quarantined GTUBE messages.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `action` | string | yes |  |
| `mail_ids` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_attachment`

List attachment quarantine entries (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /quarantine/attachment.
pmail: per-user scope — defaults to authenticated user (api.config.username).
Maps start/end Unix epoch → starttime/endtime query params.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `pmail` | string (nullable) | no | (default: `null`) |
| `start` | integer (nullable) | no | (default: `null`) |
| `end` | integer (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_blocklist_add`

MUTATION (LOW): add an address to the quarantine blocklist. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: POST /quarantine/blocklist.
pmail: scope to a per-user blocklist (optional).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `address` | string | yes |  |
| `pmail` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_blocklist_list`

List PMG quarantine blocklist entries (read). Optional pmail to scope to one user.
Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: /quarantine/blocklist.
pmail: scopes the read to one user's blocklist; ALWAYS sent, defaulting to the authenticated
PMG user when omitted — so an empty result means "none for that user", not "none globally".

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `pmail` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_blocklist_remove`

MUTATION (LOW): remove an address from the quarantine blocklist. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: DELETE /quarantine/blocklist.
pmail: optional per-user scope (defaults to authenticated user).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `address` | string | yes |  |
| `pmail` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_spam`

List PMG quarantined spam messages (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified: endpoint is /quarantine/spam (not /quarantine/mails).
For virus quarantine use pmg_quarantine_virus; for attachment use pmg_quarantine_attachment.
To act on quarantined messages (deliver/delete/mark-seen/blocklist/welcomelist) use
pmg_quarantine_action.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_spamstatus`

Get spam quarantine status summary (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /quarantine/spamstatus.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_spamusers`

List users with quarantined mail entries (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /quarantine/spamusers.
quarantine_type: spam|virus|attachment (default spam) — sent to API as 'quarantine-type'.
Maps start/end Unix epoch → starttime/endtime query params.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | integer (nullable) | no | (default: `null`) |
| `end` | integer (nullable) | no | (default: `null`) |
| `quarantine_type` | string | no | (default: `"spam"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_virus`

List virus quarantine entries (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /quarantine/virus.
pmail: per-user scope — defaults to authenticated user (api.config.username).
Maps start/end Unix epoch → starttime/endtime query params.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `pmail` | string (nullable) | no | (default: `null`) |
| `start` | integer (nullable) | no | (default: `null`) |
| `end` | integer (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_virusstatus`

Get virus quarantine status summary (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /quarantine/virusstatus.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_welcomelist_add`

MUTATION (LOW): add an address to the quarantine welcomelist. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: POST /quarantine/welcomelist.
pmail: optional per-user scope (defaults to authenticated user).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `address` | string | yes |  |
| `pmail` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_welcomelist_list`

List PMG quarantine welcomelist entries (read). Optional pmail to scope to one user.
Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /quarantine/welcomelist.
pmail defaults to the authenticated user when not provided.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `pmail` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_welcomelist_remove`

MUTATION (LOW): remove an address from the quarantine welcomelist. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: DELETE /quarantine/welcomelist.
pmail: optional per-user scope (defaults to authenticated user).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `address` | string | yes |  |
| `pmail` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_relay_config`

Get PMG SMTP relay/smarthost configuration (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified: relay/smarthost settings live at /config/mail (not /config/relay).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_digest`

Get the PMG RuleDB digest (change-detection hash) (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/digest.
The digest changes whenever any ruledb configuration is modified.
Use to detect configuration drift without fetching the full rule list.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_action_attach`

MUTATION (MEDIUM): attach an action group to a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 live-verified path: POST /config/ruledb/rules/{id}/action (singular; /actions returns 501).
id_: rule ID. ogroup: numeric action group ID from pmg_action_objects_list.
Only affects mail flow if the rule is active.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `ogroup` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_action_detach`

MUTATION (MEDIUM): detach an action group from a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 live-verified path: DELETE /config/ruledb/rules/{id}/action/{ogroup} (singular; /actions returns 501).
id_: rule ID. ogroup: numeric action group ID to detach.
Only affects mail flow if the rule is active.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `ogroup` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_actions_list`

List the 'actions' objects attached to a PMG RuleDB rule (read). Needs PROXIMO_PMG_* config.

PMG 9.1: reads GET /config/ruledb/rules/{id}/config and extracts the embedded 'action' list —
the dedicated .../actions path returns HTTP 501 (not implemented), so it is NOT used.
id_: rule ID (positive integer string, e.g. '100').

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_create`

MUTATION (MEDIUM): create a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/rules.
name: rule name. priority: 0-100 (lower = higher priority).
active: DEFAULTS TO FALSE — rules control live mail processing; only activate
when the rule configuration and group attachments have been verified.
direction: 0=inbound, 1=outbound, 2=both.
from_and/from_invert/to_and/to_invert/what_and/what_invert/when_and/when_invert:
    optional bool flags for AND/invert logic (map to hyphen-param API names).
Returns the numeric rule ID assigned by PMG on confirm.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `priority` | integer | yes |  |
| `active` | boolean | no | (default: `false`) |
| `direction` | integer (nullable) | no | (default: `null`) |
| `from_and` | boolean (nullable) | no | (default: `null`) |
| `from_invert` | boolean (nullable) | no | (default: `null`) |
| `to_and` | boolean (nullable) | no | (default: `null`) |
| `to_invert` | boolean (nullable) | no | (default: `null`) |
| `what_and` | boolean (nullable) | no | (default: `null`) |
| `what_invert` | boolean (nullable) | no | (default: `null`) |
| `when_and` | boolean (nullable) | no | (default: `null`) |
| `when_invert` | boolean (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_delete`

MUTATION (MEDIUM): delete a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/rules/{id}.
id_: rule ID (positive integer string, e.g. '100').
WARNING: permanently removes the rule and all its group bindings.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_from_attach`

MUTATION (MEDIUM): attach a 'from' (sender/who) group to a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/rules/{id}/from.
id_: rule ID. ogroup: numeric who-group ID from pmg_who_groups_list.
Only affects mail flow if the rule is active.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `ogroup` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_from_detach`

MUTATION (MEDIUM): detach a 'from' (sender/who) group from a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/rules/{id}/from/{ogroup}.
id_: rule ID. ogroup: numeric who-group ID to detach.
Only affects mail flow if the rule is active.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `ogroup` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_from_list`

List the 'from' objects attached to a PMG RuleDB rule (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules/{id}/from.
id_: rule ID (positive integer string, e.g. '100').

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_get`

Get a PMG RuleDB rule's configuration (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules/{id}/config.
id_: rule ID (positive integer string, e.g. '100').

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_to_attach`

MUTATION (MEDIUM): attach a 'to' (recipient/who) group to a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/rules/{id}/to.
id_: rule ID. ogroup: numeric who-group ID from pmg_who_groups_list.
Only affects mail flow if the rule is active.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `ogroup` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_to_detach`

MUTATION (MEDIUM): detach a 'to' (recipient/who) group from a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/rules/{id}/to/{ogroup}.
id_: rule ID. ogroup: numeric who-group ID to detach.
Only affects mail flow if the rule is active.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `ogroup` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_to_list`

List the 'to' objects attached to a PMG RuleDB rule (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules/{id}/to.
id_: rule ID (positive integer string, e.g. '100').

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_update`

MUTATION (MEDIUM): update a PMG RuleDB rule configuration. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: PUT /config/ruledb/rules/{id}/config.
id_: rule ID (positive integer string, e.g. '100').
All other fields are optional; only non-None values are sent.
WARNING: setting active=True activates the rule and begins live mail processing.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `name` | string (nullable) | no | (default: `null`) |
| `priority` | integer (nullable) | no | (default: `null`) |
| `active` | boolean (nullable) | no | (default: `null`) |
| `direction` | integer (nullable) | no | (default: `null`) |
| `from_and` | boolean (nullable) | no | (default: `null`) |
| `from_invert` | boolean (nullable) | no | (default: `null`) |
| `to_and` | boolean (nullable) | no | (default: `null`) |
| `to_invert` | boolean (nullable) | no | (default: `null`) |
| `what_and` | boolean (nullable) | no | (default: `null`) |
| `what_invert` | boolean (nullable) | no | (default: `null`) |
| `when_and` | boolean (nullable) | no | (default: `null`) |
| `when_invert` | boolean (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_what_attach`

MUTATION (MEDIUM): attach a 'what' (content) group to a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/rules/{id}/what.
id_: rule ID. ogroup: numeric what-group ID from pmg_what_groups_list.
Only affects mail flow if the rule is active.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `ogroup` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_what_detach`

MUTATION (MEDIUM): detach a 'what' (content) group from a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/rules/{id}/what/{ogroup}.
id_: rule ID. ogroup: numeric what-group ID to detach.
Only affects mail flow if the rule is active.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `ogroup` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_what_list`

List the 'what' objects attached to a PMG RuleDB rule (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules/{id}/what.
id_: rule ID (positive integer string, e.g. '100').

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_when_attach`

MUTATION (MEDIUM): attach a 'when' (timeframe) group to a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/rules/{id}/when.
id_: rule ID. ogroup: numeric when-group ID from pmg_when_groups_list.
Only affects mail flow if the rule is active.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `ogroup` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_when_detach`

MUTATION (MEDIUM): detach a 'when' (timeframe) group from a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/rules/{id}/when/{ogroup}.
id_: rule ID. ogroup: numeric when-group ID to detach.
Only affects mail flow if the rule is active.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `ogroup` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_when_list`

List the 'when' objects attached to a PMG RuleDB rule (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules/{id}/when.
id_: rule ID (positive integer string, e.g. '100').

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rules_list`

List all PMG RuleDB rules (hydrated rule list) (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules.
Returns the full hydrated rule list including from/to/what/when/actions for each rule.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_service_control`

MUTATION (MEDIUM): start, stop, restart, or reload a PMG service. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: POST /nodes/{node}/services/{service}/{action}.
service: e.g. 'postfix', 'pmgproxy', 'pmgdaemon', 'clamav', 'spamassassin'.
action: start|stop|restart|reload.

WARNING: stop on postfix/pmgproxy/pmgdaemon interrupts mail delivery until manually restarted.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `service` | string | yes |  |
| `action` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_service_status`

Get the status of a PMG system service (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: /nodes/{node}/services/{service}/state.
service: e.g. 'postfix', 'pmgproxy', 'pmgdaemon', 'pmgmirror', 'pmgtunnel',
         'pmg-smtp-filter', 'clamav', 'spamassassin'. No hardcoded enum —
         pass any valid service name; unknown names return a PMG 404.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `service` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_spam_config`

Get PMG spam filter configuration (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: /config/spam.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_spam_config_update`

MUTATION (MEDIUM): update PMG spam filter configuration. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: PUT /config/spam.
Only non-None fields are sent — omitted fields keep their current PMG values.
delete: comma-separated list of field names to reset to defaults.
Changes take effect immediately on new inbound mail.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `bounce_score` | integer (nullable) | no | (default: `null`) |
| `clamav_heuristic_score` | integer (nullable) | no | (default: `null`) |
| `extract_text` | boolean (nullable) | no | (default: `null`) |
| `languages` | string (nullable) | no | (default: `null`) |
| `maxspamsize` | integer (nullable) | no | (default: `null`) |
| `rbl_checks` | boolean (nullable) | no | (default: `null`) |
| `use_awl` | boolean (nullable) | no | (default: `null`) |
| `use_bayes` | boolean (nullable) | no | (default: `null`) |
| `use_razor` | boolean (nullable) | no | (default: `null`) |
| `wl_bounce_relays` | string (nullable) | no | (default: `null`) |
| `delete` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_statistics_domains`

Get PMG per-domain mail statistics (read). Optional Unix epoch start/end timespan.
Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: /statistics/domains.
Maps start/end params → starttime/endtime query params.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | integer (nullable) | no | (default: `null`) |
| `end` | integer (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_statistics_mail`

Get PMG mail delivery statistics (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified: /statistics/mail returns today's aggregate counters
(count_in, count_out, spam, virus, bytes, …). Always returns today's totals;
for time-ranged data use pmg_statistics_mailcount instead.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_statistics_mailcount`

Get per-bucket mail count statistics (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /statistics/mailcount.
timespan: histogram bucket size in seconds, 3600–31622400 (default 3600 = 1 hour).
Maps start/end Unix epoch → starttime/endtime query params.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | integer (nullable) | no | (default: `null`) |
| `end` | integer (nullable) | no | (default: `null`) |
| `timespan` | integer | no | (default: `3600`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_statistics_receiver`

Get per-recipient mail statistics (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /statistics/receiver.
filter_: optional search string; orderby: raw sort spec passthrough.
Maps start/end Unix epoch → starttime/endtime query params.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | integer (nullable) | no | (default: `null`) |
| `end` | integer (nullable) | no | (default: `null`) |
| `filter_` | string (nullable) | no | (default: `null`) |
| `orderby` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_statistics_recent`

Get PMG recent mail statistics (read). hours: 1-24 window. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: /statistics/recent.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `hours` | integer | no | (default: `1`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_statistics_sender`

Get per-sender mail statistics (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /statistics/sender.
filter_: optional search string. orderby: accepted for compatibility but IGNORED —
PMG 9.1 rejects orderby on /statistics/sender (HTTP 400), so rows come back in PMG's
default order (unlike pmg_statistics_receiver, which does pass orderby through).
Maps start/end Unix epoch → starttime/endtime query params.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | integer (nullable) | no | (default: `null`) |
| `end` | integer (nullable) | no | (default: `null`) |
| `filter_` | string (nullable) | no | (default: `null`) |
| `orderby` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_statistics_spamscores`

Get PMG spam score distribution statistics (read). Optional Unix epoch start/end timespan.
Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: /statistics/spamscores.
Maps start/end params → starttime/endtime query params.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | integer (nullable) | no | (default: `null`) |
| `end` | integer (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_statistics_virus`

Get PMG virus statistics (read). Optional Unix epoch start/end timespan.
Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: /statistics/virus.
Maps start/end params → starttime/endtime query params.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | integer (nullable) | no | (default: `null`) |
| `end` | integer (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_tasks_list`

List PMG tasks on a node (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /nodes/{node}/tasks.
start: pagination offset; limit: max entries.
errors: True = only failed tasks; userfilter/typefilter/statusfilter: text filters.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `start` | integer (nullable) | no | (default: `null`) |
| `limit` | integer (nullable) | no | (default: `null`) |
| `userfilter` | string (nullable) | no | (default: `null`) |
| `errors` | boolean (nullable) | no | (default: `null`) |
| `typefilter` | string (nullable) | no | (default: `null`) |
| `since` | integer (nullable) | no | (default: `null`) |
| `until` | integer (nullable) | no | (default: `null`) |
| `statusfilter` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_tracker_detail`

Get tracking detail for a specific mail ID (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /nodes/{node}/tracker/{id}.
id_: mail/queue tracker ID, validated path-segment-safe (rejects '..', '/',
control/whitespace chars) before use — see _check_tracker_id.
Maps start/end Unix epoch → starttime/endtime query params.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `start` | integer (nullable) | no | (default: `null`) |
| `end` | integer (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_tracker_list`

List mail tracking entries (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /nodes/{node}/tracker.
Maps start/end Unix epoch → starttime/endtime query params.
from_: filter by envelope sender; target: filter by recipient.
ndr: NDR filter; greylist: greylisting filter.
limit: max results 0–100000 (default 2000).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | (default: `null`) |
| `start` | integer (nullable) | no | (default: `null`) |
| `end` | integer (nullable) | no | (default: `null`) |
| `from_` | string (nullable) | no | (default: `null`) |
| `target` | string (nullable) | no | (default: `null`) |
| `xfilter` | string (nullable) | no | (default: `null`) |
| `ndr` | boolean (nullable) | no | (default: `null`) |
| `greylist` | boolean (nullable) | no | (default: `null`) |
| `limit` | integer | no | (default: `2000`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_transport_create`

MUTATION (LOW): create a mail transport rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: POST /config/transport.
domain: destination domain. host: next-hop relay host.
port: TCP port 1-65535 (default 25). protocol: smtp|lmtp (default smtp).
use_mx: use MX lookup for the host (default True).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `domain` | string | yes |  |
| `host` | string | yes |  |
| `comment` | string (nullable) | no | (default: `null`) |
| `port` | integer | no | (default: `25`) |
| `protocol` | string | no | (default: `"smtp"`) |
| `use_mx` | boolean | no | (default: `true`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_transport_delete`

MUTATION (MEDIUM): delete a mail transport rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: DELETE /config/transport/{domain}.
Mail for the domain will fall back to default PMG routing (MX lookup).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `domain` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_what_group_create`

MUTATION (LOW): create a PMG RuleDB 'what' object group. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/what.
name: group name.
info: optional description.
and_: maps to API param 'and' (bool; AND vs OR logic for group members).
invert: if True, the group match is inverted.
Returns the numeric ogroup ID assigned by PMG on confirm.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `info` | string (nullable) | no | (default: `null`) |
| `and_` | boolean (nullable) | no | (default: `null`) |
| `invert` | boolean (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_what_group_delete`

MUTATION (MEDIUM): delete a PMG RuleDB 'what' object group. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/what/{ogroup}.
ogroup: numeric ID string (e.g. '8') from pmg_what_groups_list.
WARNING: also removes all objects within the group.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_what_group_get`

Get a PMG RuleDB 'what' object group's configuration (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/what/{ogroup}/config.
ogroup: numeric ID string (e.g. '2') from the matching pmg_*_groups_list — NOT the group name.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_what_group_objects`

List the objects in a PMG RuleDB 'what' object group (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/what/{ogroup}/objects.
ogroup: numeric ID string (e.g. '2') from the matching pmg_*_groups_list — NOT the group name.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_what_group_update`

MUTATION (MEDIUM): update a PMG RuleDB 'what' object group config. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: PUT /config/ruledb/what/{ogroup}/config.
ogroup: numeric ID string (e.g. '8') from pmg_what_groups_list.
Only non-None fields are sent to PMG; omitted fields keep current values.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes |  |
| `name` | string (nullable) | no | (default: `null`) |
| `info` | string (nullable) | no | (default: `null`) |
| `and_` | boolean (nullable) | no | (default: `null`) |
| `invert` | boolean (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_what_groups_list`

List all PMG RuleDB 'what' object groups (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/what.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_what_object_add`

MUTATION (LOW): add an object to a PMG RuleDB 'what' object group. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/what/{ogroup}/{type}.
ogroup: numeric ID string (e.g. '8') from pmg_what_groups_list.
type_: contenttype|matchfield|spamfilter|virusfilter|filenamefilter|archivefilter|archivefilenamefilter.
Type-specific fields: contenttype+only_content (contenttype/archivefilter),
field+value+top_part_only (matchfield), spamlevel (spamfilter), filename (filenamefilter/archivefilenamefilter).
only_content maps to API param 'only-content'; top_part_only → 'top-part-only'.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes |  |
| `type_` | string | yes |  |
| `contenttype` | string (nullable) | no | (default: `null`) |
| `only_content` | boolean (nullable) | no | (default: `null`) |
| `field` | string (nullable) | no | (default: `null`) |
| `value` | string (nullable) | no | (default: `null`) |
| `top_part_only` | boolean (nullable) | no | (default: `null`) |
| `spamlevel` | integer (nullable) | no | (default: `null`) |
| `filename` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_what_object_delete`

MUTATION (MEDIUM): delete an object from a PMG RuleDB 'what' object group. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/what/{ogroup}/objects/{id}.
ogroup: numeric ID string (e.g. '8') from pmg_what_groups_list.
id_: object ID (numeric string) from pmg_what_group_objects.
Object DELETE always goes through /objects/{id} regardless of type.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes |  |
| `id_` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_what_object_update`

MUTATION (MEDIUM): update an object in a PMG RuleDB 'what' object group. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: PUT /config/ruledb/what/{ogroup}/{type}/{id}.
ogroup: numeric ID string (e.g. '8') from pmg_what_groups_list.
type_: contenttype|matchfield|spamfilter|virusfilter|filenamefilter|archivefilter|archivefilenamefilter.
id_: object ID (numeric string) from pmg_what_group_objects.
All type-specific fields optional; only non-None fields are sent.
only_content → 'only-content'; top_part_only → 'top-part-only'.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes |  |
| `type_` | string | yes |  |
| `id_` | string | yes |  |
| `contenttype` | string (nullable) | no | (default: `null`) |
| `only_content` | boolean (nullable) | no | (default: `null`) |
| `field` | string (nullable) | no | (default: `null`) |
| `value` | string (nullable) | no | (default: `null`) |
| `top_part_only` | boolean (nullable) | no | (default: `null`) |
| `spamlevel` | integer (nullable) | no | (default: `null`) |
| `filename` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_when_group_create`

MUTATION (LOW): create a PMG RuleDB 'when' object group. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/when.
name: group name.
info: optional description.
and_: maps to API param 'and' (bool; AND vs OR logic for group members).
invert: if True, the group match is inverted.
Returns the numeric ogroup ID assigned by PMG on confirm.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `info` | string (nullable) | no | (default: `null`) |
| `and_` | boolean (nullable) | no | (default: `null`) |
| `invert` | boolean (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_when_group_delete`

MUTATION (MEDIUM): delete a PMG RuleDB 'when' object group. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/when/{ogroup}.
ogroup: numeric ID string (e.g. '4') from pmg_when_groups_list.
WARNING: also removes all objects within the group.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_when_group_get`

Get a PMG RuleDB 'when' object group's configuration (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/when/{ogroup}/config.
ogroup: numeric ID string (e.g. '2') from the matching pmg_*_groups_list — NOT the group name.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_when_group_objects`

List the objects in a PMG RuleDB 'when' object group (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/when/{ogroup}/objects.
ogroup: numeric ID string (e.g. '2') from the matching pmg_*_groups_list — NOT the group name.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_when_group_update`

MUTATION (MEDIUM): update a PMG RuleDB 'when' object group config. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: PUT /config/ruledb/when/{ogroup}/config.
ogroup: numeric ID string (e.g. '4') from pmg_when_groups_list.
Only non-None fields are sent to PMG; omitted fields keep current values.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes |  |
| `name` | string (nullable) | no | (default: `null`) |
| `info` | string (nullable) | no | (default: `null`) |
| `and_` | boolean (nullable) | no | (default: `null`) |
| `invert` | boolean (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_when_groups_list`

List all PMG RuleDB 'when' object groups (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/when.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_when_object_add`

MUTATION (LOW): add a timeframe object to a PMG RuleDB 'when' object group. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/when/{ogroup}/timeframe.
ogroup: numeric ID string (e.g. '4') from pmg_when_groups_list.
start: time in H:i format (e.g. '08:00').
end: time in H:i format (e.g. '17:00').

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes |  |
| `start` | string | yes |  |
| `end` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_when_object_delete`

MUTATION (MEDIUM): delete a timeframe object from a PMG RuleDB 'when' object group. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/when/{ogroup}/objects/{id}.
ogroup: numeric ID string (e.g. '4') from pmg_when_groups_list.
id_: object ID (numeric string) from pmg_when_group_objects.
Object DELETE always goes through /objects/{id} regardless of type.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes |  |
| `id_` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_when_object_update`

MUTATION (MEDIUM): update a timeframe object in a PMG RuleDB 'when' object group. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: PUT /config/ruledb/when/{ogroup}/timeframe/{id}.
ogroup: numeric ID string (e.g. '4') from pmg_when_groups_list.
id_: object ID (numeric string) from pmg_when_group_objects.
Both start and end are required — PMG 9.1 timeframe PUT rejects partial updates (400).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes |  |
| `id_` | string | yes |  |
| `start` | string | yes |  |
| `end` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_who_group_create`

MUTATION (LOW): create a PMG RuleDB 'who' object group. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/who.
name: group name.
info: optional description.
and_: maps to API param 'and' (bool; AND vs OR logic for group members).
invert: if True, the group match is inverted.
Returns the numeric ogroup ID assigned by PMG on confirm.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `info` | string (nullable) | no | (default: `null`) |
| `and_` | boolean (nullable) | no | (default: `null`) |
| `invert` | boolean (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_who_group_delete`

MUTATION (MEDIUM): delete a PMG RuleDB 'who' object group. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/who/{ogroup}.
ogroup: numeric ID string (e.g. '2') from pmg_who_groups_list.
WARNING: also removes all objects within the group.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_who_group_get`

Get a PMG RuleDB 'who' object group's configuration (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/who/{ogroup}/config.
ogroup: numeric ID string (e.g. '2') from the matching pmg_*_groups_list — NOT the group name.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_who_group_objects`

List the objects in a PMG RuleDB 'who' object group (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/who/{ogroup}/objects.
ogroup: numeric ID string (e.g. '2') from the matching pmg_*_groups_list — NOT the group name.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_who_group_update`

MUTATION (MEDIUM): update a PMG RuleDB 'who' object group config. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: PUT /config/ruledb/who/{ogroup}/config.
ogroup: numeric ID string (e.g. '2') from pmg_who_groups_list.
Only non-None fields are sent to PMG; omitted fields keep current values.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes |  |
| `name` | string (nullable) | no | (default: `null`) |
| `info` | string (nullable) | no | (default: `null`) |
| `and_` | boolean (nullable) | no | (default: `null`) |
| `invert` | boolean (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_who_groups_list`

List all PMG RuleDB 'who' object groups (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/who.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_who_object_add`

MUTATION (LOW): add an object to a PMG RuleDB 'who' object group. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/who/{ogroup}/{type}.
ogroup: numeric ID string (e.g. '2') from pmg_who_groups_list.
type_: email|domain|regex|ip|network|ldap — controls the sub-path.
Type-specific fields: email(email), domain(domain), regex(regex), ip(ip),
network(cidr), ldap(mode, profile, group).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes |  |
| `type_` | string | yes |  |
| `email` | string (nullable) | no | (default: `null`) |
| `domain` | string (nullable) | no | (default: `null`) |
| `regex` | string (nullable) | no | (default: `null`) |
| `ip` | string (nullable) | no | (default: `null`) |
| `cidr` | string (nullable) | no | (default: `null`) |
| `mode` | string (nullable) | no | (default: `null`) |
| `profile` | string (nullable) | no | (default: `null`) |
| `group` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_who_object_delete`

MUTATION (MEDIUM): delete an object from a PMG RuleDB 'who' object group. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/who/{ogroup}/objects/{id}.
ogroup: numeric ID string (e.g. '2') from pmg_who_groups_list.
id_: object ID (numeric string) from pmg_who_group_objects.
Object DELETE always goes through /objects/{id} regardless of type.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes |  |
| `id_` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_who_object_update`

MUTATION (MEDIUM): update an object in a PMG RuleDB 'who' object group. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: PUT /config/ruledb/who/{ogroup}/{type}/{id}.
ogroup: numeric ID string (e.g. '2') from pmg_who_groups_list.
type_: email|domain|regex|ip|network|ldap — controls the sub-path.
id_: object ID (numeric string) from pmg_who_group_objects.
All type-specific fields optional; only non-None fields are sent.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes |  |
| `type_` | string | yes |  |
| `id_` | string | yes |  |
| `email` | string (nullable) | no | (default: `null`) |
| `domain` | string (nullable) | no | (default: `null`) |
| `regex` | string (nullable) | no | (default: `null`) |
| `ip` | string (nullable) | no | (default: `null`) |
| `cidr` | string (nullable) | no | (default: `null`) |
| `mode` | string (nullable) | no | (default: `null`) |
| `profile` | string (nullable) | no | (default: `null`) |
| `group` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

## Proxmox Datacenter Manager (PDM)

#### `pdm_acl_list`

DIAGNOSE (LOW): list PDM access control entries.
path: optional ACL path filter (e.g. '/'). exact: if True, exact path only.
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `path` | string (nullable) | no | (default: `null`) |
| `exact` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_node_status`

DIAGNOSE (LOW): get resource stats for a PDM node. Defaults to 'localhost'
(PDM is a single-node appliance). Shape equals PVE node status;
live-prove-pending. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | (default: `"localhost"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pbs_datastores_list`

DIAGNOSE (LOW): list datastores on a PDM-registered PBS remote.
remote: remote name from pdm_remotes_list.
Live-verified shape: [{"name","path"}, ...] (PDM 1.1 -> PBS 4.2).
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pbs_remote_status`

DIAGNOSE (LOW): get node status for a PDM-registered PBS remote.
remote: remote name from pdm_remotes_list.
Live-verified (PDM 1.1 -> PBS 4.2).
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pbs_snapshots_list`

DIAGNOSE (LOW): list backup snapshots in a datastore on a PDM-registered PBS remote.
remote: remote name. datastore: PBS datastore name. ns: optional namespace filter.
Live-verified path (PDM 1.1 -> PBS 4.2); empty datastore returns [].
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `datastore` | string | yes |  |
| `ns` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_ping`

DIAGNOSE (LOW): health check the PDM appliance. Returns 'pong' on success.
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_cluster_status`

DIAGNOSE (LOW): get cluster status for a PDM-registered PVE remote.
remote: remote name from pdm_remotes_list.
Shape equals PVE cluster/status; live-proven 2026-06-27 against a registered PVE remote.
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_config`

DIAGNOSE (LOW): get LXC config from a PDM-registered PVE remote.
remote: remote name. vmid: numeric CT ID.
node, snapshot: optional query params (node is NOT required).
state: REQUIRED by PDM ("active" = current config) — defaults to "active"; PDM 400s if omitted.
Live-proven 2026-06-27 against a registered PVE remote. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `vmid` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `snapshot` | string (nullable) | no | (default: `null`) |
| `state` | string | no | (default: `"active"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_list`

DIAGNOSE (LOW): list LXC containers across a PDM-registered PVE remote (cluster-wide).
remote: remote name. node: OPTIONAL filter to one PVE node.
Shape equals PVE lxc list; live-proven 2026-06-27 against a registered PVE remote.
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_migrate`

MUTATION: migrate a container to another node within the remote's cluster (through PDM).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `vmid` | string | yes |  |
| `target` | string | yes |  |
| `online` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_power`

MUTATION: start/stop/shutdown a container on a PDM-registered remote (through PDM).

Dry-run by default (PLAN); confirm=True to submit. Task-backed → 'submitted'.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `vmid` | string | yes |  |
| `action` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_remote_migrate`

MUTATION: migrate a container to a DIFFERENT PDM-registered remote
(datacenter-to-datacenter).

target_bridge and target_storage mappings are required (e.g. 'vmbr0:vmbr0',
'local-lvm:local-lvm'). delete=True removes the source after a successful move
(destructive). Dry-run by default (PLAN); confirm=True to submit.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `vmid` | string | yes |  |
| `target_remote` | string | yes |  |
| `target_bridge` | string | yes |  |
| `target_storage` | string | yes |  |
| `target_vmid` | string (nullable) | no | (default: `null`) |
| `online` | boolean | no | (default: `false`) |
| `delete` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_snapshot_create`

MUTATION: snapshot a container on a PDM-registered remote (through PDM).

Containers have no RAM state, so there is no vmstate option. Dry-run by default.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `vmid` | string | yes |  |
| `snapname` | string | yes |  |
| `description` | string (nullable) | no | (default: `null`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_snapshot_delete`

MUTATION: delete a container snapshot on a PDM-registered remote. Irreversible; no UNDO.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `vmid` | string | yes |  |
| `snapname` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_snapshot_rollback`

MUTATION: roll a container back to a snapshot on a PDM-registered remote (through PDM).

DESTRUCTIVE. Takes an auto safety-snapshot first (fail-closed). Dry-run by default.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `vmid` | string | yes |  |
| `snapname` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_node_list`

DIAGNOSE (LOW): list nodes in a PDM-registered PVE remote.
remote: remote name from pdm_remotes_list.
Shape equals PVE /nodes; live-proven 2026-06-27 against a registered PVE remote.
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_qemu_config`

DIAGNOSE (LOW): get VM config from a PDM-registered PVE remote.
remote: remote name. vmid: numeric VM ID.
node, snapshot: optional query params (node is NOT required).
state: REQUIRED by PDM ("active" = current config) — defaults to "active"; PDM 400s if omitted.
Live-proven 2026-06-27 against a registered PVE remote. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `vmid` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `snapshot` | string (nullable) | no | (default: `null`) |
| `state` | string | no | (default: `"active"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_qemu_list`

DIAGNOSE (LOW): list VMs across a PDM-registered PVE remote (cluster-wide).
remote: remote name. node: OPTIONAL filter to one PVE node.
Shape equals PVE qemu list; live-proven 2026-06-27 against a registered PVE remote.
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_qemu_migrate`

MUTATION: migrate a VM to another node within the remote's cluster (through PDM).

online=True migrates a running VM. Dry-run by default (PLAN); confirm=True to submit.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `vmid` | string | yes |  |
| `target` | string | yes |  |
| `online` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_qemu_power`

MUTATION: start/stop/shutdown/resume a VM on a PDM-registered remote (through PDM).

Dry-run by default: returns a PLAN (live state, blast radius, risk) recorded to the
ledger. Re-call with confirm=True to submit. Task-backed → status='submitted'.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `vmid` | string | yes |  |
| `action` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_qemu_remote_migrate`

MUTATION: migrate a VM to a DIFFERENT PDM-registered remote (datacenter-to-datacenter).

target_bridge and target_storage mappings are required (e.g. 'vmbr0:vmbr0',
'local-lvm:local-lvm'). delete=True removes the source after a successful move (destructive).
Dry-run by default (PLAN); confirm=True to submit.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `vmid` | string | yes |  |
| `target_remote` | string | yes |  |
| `target_bridge` | string | yes |  |
| `target_storage` | string | yes |  |
| `target_vmid` | string (nullable) | no | (default: `null`) |
| `online` | boolean | no | (default: `false`) |
| `delete` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_qemu_snapshot_create`

MUTATION: snapshot a VM on a PDM-registered remote (through PDM).

vmstate=True includes the VM's RAM state. Additive (LOW risk). Dry-run by default.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `vmid` | string | yes |  |
| `snapname` | string | yes |  |
| `description` | string (nullable) | no | (default: `null`) |
| `vmstate` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_qemu_snapshot_delete`

MUTATION: delete a VM snapshot on a PDM-registered remote. Irreversible; no UNDO. Dry-run by default.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `vmid` | string | yes |  |
| `snapname` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_qemu_snapshot_rollback`

MUTATION: roll a VM back to a snapshot on a PDM-registered remote (through PDM).

DESTRUCTIVE (discards current state). Takes an auto safety-snapshot first (fail-closed:
no snapshot, no rollback). Dry-run by default (PLAN); confirm=True to submit.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `vmid` | string | yes |  |
| `snapname` | string | yes |  |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_resources`

DIAGNOSE (LOW): list resources on a PDM-registered PVE remote.
remote: remote name from pdm_remotes_list.
kind: optional filter (vm, storage, node, sdn, ...).
Shape equals PVE cluster/resources; live-proven 2026-06-27 against a registered PVE remote.
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes |  |
| `kind` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_remote_config_get`

DIAGNOSE (LOW): get configuration for one PDM-registered remote (no secrets returned).
remote_id: the remote name as shown in pdm_remotes_list.
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote_id` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_remote_version`

DIAGNOSE (LOW): get version info for one PDM-registered remote.
remote_id: the remote name as shown in pdm_remotes_list.
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote_id` | string | yes |  |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_remotes_list`

DIAGNOSE (LOW): list all PVE/PBS remotes registered in PDM.
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_resources_list`

DIAGNOSE (LOW): list all fleet resources (VMs, LXCs, storage, etc.) across all remotes.
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_resources_status`

DIAGNOSE (LOW): aggregated fleet status counters (running VMs, LXCs, failed remotes, etc.).
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_roles_list`

DIAGNOSE (LOW): list all roles and their privileges defined in PDM.
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_tasks_list`

DIAGNOSE (LOW): list recent PDM tasks across all remotes.
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_users_list`

DIAGNOSE (LOW): list all PDM users.
include_tokens: if True, include API token entries.
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `include_tokens` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_version`

DIAGNOSE (LOW): get PDM appliance version (release, repoid, version).
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

## Container exec (opt-in)

#### `ct_diagnose`

READ-ONLY: gather 'what's broken' evidence for a container — API status + a fixed read-only
in-container battery (failed units, disk, recent errors, memory, listening ports) + advisory flags.

No mutation, no confirm. The in-container probes need PROXIMO_ENABLE_EXEC and the CTID allowlist
(same as ct_logs); with exec off it returns the API-only part and discloses the skipped probes.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ctid` | string | yes |  |
| `kind` | string | no | (default: `"lxc"`) |
| `node` | string (nullable) | no | (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `ct_exec`

Run a command inside an LXC (ssh -> pct exec). MUTATION-CAPABLE.

Dry-run by default: without confirm=True you get a PLAN — the command plus a heuristic
read-vs-write / destructive-pattern classification (advisory only) — recorded to the ledger.
Re-call with confirm=True to execute. Disabled unless PROXIMO_ENABLE_EXEC is set (safe default
is API-only). Allowlist-scoped (fail-closed) and audited.

snapshot=True (UNDO): take an auto-undo snapshot first and WAIT for it; if it can't be made
(e.g. storage doesn't support snapshots) the command is NOT run (fail-closed). On success the
result carries an `undo_point` you can revert with pve_rollback.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ctid` | string | yes |  |
| `command` | array<string> | yes |  |
| `snapshot` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `ct_logs`

Tail journalctl for a systemd unit inside a container (read-only). Returns the command's
returncode, stdout, and stderr. Container-specific diagnostic; gated by the CTID allowlist
when PROXIMO_ENABLE_EXEC is set. Fails closed if exec is disabled.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ctid` | string | yes |  |
| `unit` | string | yes |  |
| `lines` | integer | no | (default: `50`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `ct_psql`

Run SQL via psql inside a container (as the db OS user). MUTATION-CAPABLE.

Dry-run by default: without confirm=True you get a PLAN — the SQL plus a heuristic
read/DML/DDL classification (advisory only) — recorded to the ledger. Re-call with
confirm=True to execute.

snapshot=True (UNDO): take an auto-undo snapshot first and WAIT for it; if it can't be made the
SQL is NOT run (fail-closed). On success the result carries an `undo_point` (revert via pve_rollback).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ctid` | string | yes |  |
| `sql` | string | yes |  |
| `db` | string | no | (default: `"postgres"`) |
| `snapshot` | boolean | no | (default: `false`) |
| `confirm` | boolean | no | (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

## Core / trust spine

#### `audit_verify`

Verify the tamper-evident audit ledger's hash chain — PROVE the log is intact.

Pass `expected_head` (the head() value you pinned off-box) to also catch tail
truncation, a forged tail-append, or a full file replacement — a forward walk
alone can't see those. Falls back to PROXIMO_AUDIT_EXPECTED_HEAD when omitted.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `expected_head` | string (nullable) | no | (default: `null`) |
