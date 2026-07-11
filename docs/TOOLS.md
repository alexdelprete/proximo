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
| `vmid` | string | yes | Numeric VMID of the target QEMU guest (allowlist-scoped). |
| `command` | array<string> | yes | Argv list to run in the guest via the qemu-agent. |
| `node` | string (nullable) | no | PVE node the guest runs on; omit to resolve automatically. (default: `null`) |
| `timeout` | integer | no | Seconds to poll for exit before returning status='running'. (default: `30`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; true executes. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_agent_file_read`

READ-ONLY: read a file from inside the guest via the qemu-agent.

Requires PROXIMO_ENABLE_AGENT=1 and the VMID in PROXIMO_AGENT_ALLOWLIST.
No confirm needed — read-only.  File path must be absolute.

Ledger records only the file path (never the content); the returned dict carries content.
Smoke-confirm: PVE file-read response shape is unverified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric VM ID of the guest to read from via the qemu-agent. |
| `file` | string | yes | Absolute path of the file to read inside the guest. |
| `node` | string (nullable) | no | Proxmox node name hosting the guest; auto-detected if omitted. (default: `null`) |
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
| `vmid` | string | yes | Numeric VM ID of the guest to write to via the qemu-agent. |
| `file` | string | yes | Absolute path of the file to write inside the guest. |
| `content` | string | yes | File content to write; unconditionally redacted from the ledger (fingerprint only). |
| `node` | string (nullable) | no | Proxmox node name hosting the guest; auto-detected if omitted. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the write. (default: `false`) |
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
| `vmid` | string | yes | Numeric VM ID of the guest to operate on via the qemu-agent. |
| `command` | string | yes | Filesystem operation: fsfreeze-freeze, fsfreeze-thaw, or fstrim. |
| `node` | string (nullable) | no | Proxmox node name hosting the guest; auto-detected if omitted. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the command. (default: `false`) |
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
| `vmid` | string | yes | Numeric VM ID of the guest to query via the qemu-agent. |
| `command` | string | no | qemu-agent query: ping, info, get-fsinfo, get-host-name, get-osinfo, get-time, get-timezone, get-users, get-vcpus, network-get-interfaces, get-memory-blocks, fsfreeze-status, or exec-status. (default: `"info"`) |
| `pid` | integer (nullable) | no | Process id returned by pve_agent_exec; required only when command='exec-status'. (default: `null`) |
| `node` | string (nullable) | no | Proxmox node name hosting the guest; auto-detected if omitted. (default: `null`) |
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
| `vmid` | string | yes | Numeric VM ID of the guest whose OS user password is being set. |
| `username` | string | yes | Guest OS username whose password will be changed. |
| `password` | string | yes | New password for the guest OS user; unconditionally redacted from the ledger. |
| `node` | string (nullable) | no | Proxmox node name hosting the guest; auto-detected if omitted. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the password change. (default: `false`) |
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
| `path` | string | yes | Resource path the ACL entry applies to, e.g. '/vms/100' or '/'. |
| `roles` | string | yes | Comma-separated role id(s) to grant or revoke, e.g. 'PVEVMAdmin'. |
| `target` | string | yes | Principal the ACL entry applies to: userid, groupid, or tokenid depending on kind. |
| `kind` | string | no | Principal type of target: 'user', 'group', or 'token'. (default: `"user"`) |
| `propagate` | boolean | no | Whether the grant propagates to child paths below `path`. (default: `true`) |
| `delete` | boolean | no | False to grant the roles, True to revoke them. (default: `false`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acl_prune`

MUTATION: prune (remove/narrow) an over-broad ACL grant flagged by pve_overbroad_grants.

Dry-run by default — the PLAN names every principal losing/gaining what, and flags
shadow/widen gotchas. Re-call with confirm=True to execute (revoke, then optional
narrower re-grant). Synchronous. roleid = the over-broad role to remove (from detection).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `path` | string | yes | Resource path of the over-broad ACL entry to prune, e.g. '/'. |
| `target` | string | yes | Principal the over-broad grant belongs to: userid, groupid, or tokenid depending on kind. |
| `kind` | string | no | Principal type of target: 'user', 'group', or 'token'. (default: `"user"`) |
| `roleid` | string | no | The over-broad role id to remove, as identified by pve_overbroad_grants. (default: `""`) |
| `narrow_role` | string (nullable) | no | Optional narrower role id to re-grant in place of the removed one. (default: `null`) |
| `narrow_path` | string (nullable) | no | Optional narrower path to scope the re-grant to, instead of the original path. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acme_account_create`

MUTATION: register a new ACME account with the CA. Dry-run by default.
confirm=True to execute. Smoke-confirm: POST body shape (name in body) against a live PVE instance.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name to register the new ACME account under (cluster/acme/account/{name}). |
| `contact` | string | yes | Contact email address for the ACME account (CA renewal/expiry notices). |
| `tos_url` | string (nullable) | no | URL of the CA's terms-of-service to accept; omit to accept the CA's default ToS. (default: `null`) |
| `directory` | string (nullable) | no | ACME directory URL of the CA to register with; omit to use PVE's default CA. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the account registration. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acme_account_delete`

MUTATION: IRREVERSIBLE — deactivate and delete an ACME account from the CA. Dry-run by default.
confirm=True to execute. HIGH risk: TLS lockout at cert expiry if this is the only account.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the ACME account to deactivate and delete from the CA. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the irreversible deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acme_account_update`

MUTATION: update ACME account contact info. Dry-run by default.
confirm=True to execute. LOW risk — metadata update only, no cert impact.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the existing ACME account to update. |
| `contact` | string (nullable) | no | New contact email address for the ACME account; omit to leave unchanged. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the update. (default: `false`) |
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
| `node` | string (nullable) | no | Target PVE node name; omit to use the configured default node. (default: `null`) |
| `force` | boolean | no | Overwrite an existing custom certificate on the node if one is already installed. (default: `false`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True submits the ACME order task. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acme_cert_renew`

MUTATION: renew the node's existing ACME TLS certificate. Dry-run by default. Async — returns
a UPID. MEDIUM: CA-validated, installed only on success (a failure can't lock you out); reloads
pveproxy on success. force=renew even if more than 30 days to expiry. confirm=True to execute.
Smoke-confirm: PUT shape + async UPID against a live PVE instance.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | Target PVE node name; omit to use the configured default node. (default: `null`) |
| `force` | boolean | no | Renew now even if the current certificate has more than 30 days left before expiry. (default: `false`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True submits the ACME renewal task. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acme_cert_revoke`

MUTATION: IRREVERSIBLE — revoke the node's ACME TLS certificate at the CA. Dry-run by default.
Async — returns a UPID. HIGH: a revoked cert cannot be un-revoked; only a NEW pve_acme_cert_order
restores trust. To fall back to PVE's self-signed cert WITHOUT revoking at the CA, use
pve_node_cert_delete instead. confirm=True to execute. Smoke-confirm: DELETE shape against a live
PVE instance.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | Target PVE node name; omit to use the configured default node. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True submits the irreversible revocation task. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acme_plugin_create`

MUTATION: create an ACME DNS challenge plugin. Dry-run by default.
confirm=True to execute. dns_api = DNS provider name (e.g. 'cf', 'route53').
Smoke-confirm: POST body shape (id in body) against a live PVE instance.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `plugin_id` | string | yes | Identifier for the new ACME DNS challenge plugin (cluster/acme/plugins/{plugin_id}). |
| `plugin_type` | string | yes | ACME challenge plugin type, e.g. 'dns' for a DNS-01 challenge plugin. |
| `dns_api` | string (nullable) | no | DNS provider API name for a DNS-01 challenge (e.g. 'cf', 'route53'); maps to PVE's 'api' field. (default: `null`) |
| `data` | string (nullable) | no | Plugin-specific credential/config data (e.g. API tokens) required by the DNS provider. (default: `null`) |
| `disable` | boolean (nullable) | no | Set to disable the plugin on creation; omit to leave it enabled. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the plugin creation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acme_plugin_delete`

MUTATION: delete an ACME DNS challenge plugin. Dry-run by default.
confirm=True to execute. HIGH risk: cert auto-renewal breaks — TLS lockout at cert expiry.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `plugin_id` | string | yes | Identifier of the ACME DNS challenge plugin to delete. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acme_plugin_update`

MUTATION: update an ACME DNS challenge plugin. Dry-run by default.
confirm=True to execute. MEDIUM risk — invalid credentials break renewal at next attempt.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `plugin_id` | string | yes | Identifier of the existing ACME DNS challenge plugin to update. |
| `dns_api` | string (nullable) | no | New DNS provider API name for a DNS-01 challenge; maps to PVE's 'api' field. Omit to leave unchanged. (default: `null`) |
| `data` | string (nullable) | no | New plugin-specific credential/config data; omit to leave unchanged. (default: `null`) |
| `disable` | boolean (nullable) | no | Set to enable/disable the plugin; omit to leave unchanged. (default: `null`) |
| `digest` | string (nullable) | no | Config digest for optimistic-locking the update against concurrent changes; omit to skip the check. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the update. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_backup`

MUTATION: back up a guest with vzdump. Dry-run by default; confirm=True to execute.
mode: snapshot (online, brief) | suspend | stop (HALTS the guest). Async — returns a task UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric ID of the guest (VM or CT) to back up. |
| `storage` | string | yes | Storage ID to write the backup archive to. |
| `mode` | string | no | Backup mode: snapshot (online, brief) \| suspend (RAM-quiesced pause) \| stop (HALTS the guest). (default: `"snapshot"`) |
| `compress` | string | no | Compression algorithm for the archive, e.g. zstd, gzip, lzo, or none. (default: `"zstd"`) |
| `kind` | string | no | Guest type: lxc or qemu. (default: `"lxc"`) |
| `node` | string (nullable) | no | Proxmox node hosting the guest; defaults to the configured node if omitted. (default: `null`) |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the backup. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_backup_delete`

MUTATION: delete a backup archive (removes a recovery point). Dry-run by default; confirm=True.
Async — may return a task UPID or null depending on storage.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes | Storage ID holding the backup archive. |
| `volid` | string | yes | Volume ID of the backup archive to delete (as returned by pve_backup_list). |
| `node` | string (nullable) | no | Proxmox node hosting the storage; defaults to the configured node if omitted. (default: `null`) |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the deletion. (default: `false`) |
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
| `max_age_hours` | number (nullable) | no | Override for max acceptable backup age in hours; if omitted, age expectation is derived from each guest's backup job schedule. (default: `null`) |
| `grace_hours` | number | no | Hours of slack padded onto each job's parsed cadence before a backup is flagged stale. (default: `6.0`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_backup_job_create`

MUTATION: create a PVE cluster backup job. Dry-run by default — shows the plan.
confirm=True to execute. Config-only; existing backups are NOT affected.
Guest selection is mutually exclusive — pass at most one of: vmid (CSV of guest IDs),
all_guests=True (every guest), or pool (a resource pool); PVE requires a selection.
exclude (CSV) filters all_guests.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `job_id` | string | yes | Unique ID for the new PVE backup job. |
| `schedule` | string | yes | Proxmox calendar-event schedule string, e.g. 'sat 02:00' or a systemd.time-style spec. |
| `storage` | string | yes | Storage ID the job writes backups to. |
| `mode` | string (nullable) | no | Backup mode: snapshot \| suspend \| stop; defaults to Proxmox's own default if omitted. (default: `null`) |
| `compress` | string (nullable) | no | Compression algorithm for archives, e.g. zstd, gzip, lzo, or none. (default: `null`) |
| `vmid` | string (nullable) | no | CSV of guest IDs to include; mutually exclusive with all_guests and pool. (default: `null`) |
| `all_guests` | boolean (nullable) | no | If true, back up every guest on the cluster; mutually exclusive with vmid and pool. (default: `null`) |
| `pool` | string (nullable) | no | Resource pool of guests to back up; mutually exclusive with vmid and all_guests. (default: `null`) |
| `exclude` | string (nullable) | no | CSV of guest IDs to exclude when all_guests=True. (default: `null`) |
| `enabled` | boolean (nullable) | no | Whether the job is active; defaults to enabled if omitted. (default: `null`) |
| `comment` | string (nullable) | no | Free-text note stored on the job. (default: `null`) |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the creation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_backup_job_delete`

MUTATION: delete a PVE cluster backup job. Dry-run by default — captures current config.
confirm=True to execute. Schedule removed; existing backups are NOT deleted.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `job_id` | string | yes | ID of the PVE backup job to delete. |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the deletion. (default: `false`) |
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
| `job_id` | string | yes | ID of the existing PVE backup job to update. |
| `schedule` | string (nullable) | no | New Proxmox calendar-event schedule string; omit to leave unchanged. (default: `null`) |
| `storage` | string (nullable) | no | New storage ID for the job's backups; omit to leave unchanged. (default: `null`) |
| `mode` | string (nullable) | no | New backup mode: snapshot \| suspend \| stop; omit to leave unchanged. (default: `null`) |
| `compress` | string (nullable) | no | New compression algorithm, e.g. zstd, gzip, lzo, or none; omit to leave unchanged. (default: `null`) |
| `vmid` | string (nullable) | no | New CSV of guest IDs the job covers; omit to leave unchanged. (default: `null`) |
| `enabled` | boolean (nullable) | no | Whether the job is active; omit to leave unchanged. (default: `null`) |
| `comment` | string (nullable) | no | New free-text note; omit to leave unchanged. (default: `null`) |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the update. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_backup_list`

List backup archives in a storage (read). Ground truth for whether a backup exists —
a backup missing from a pve_tasks_list slice (other node, or outside its limit window)
still shows here.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes | Storage ID to list backup archives from. |
| `node` | string (nullable) | no | Proxmox node hosting the storage; defaults to the configured node if omitted. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_clone`

MUTATION: clone a guest to a new id. Dry-run by default; confirm=True. Async — returns a UPID.
pool: place the new guest in a resource pool (needed when the token is pool-scoped).
storage: target storage for the full clone's disks (full=True only) — keeps a clone off the
source storage; refused for a linked clone (PVE only honors it on a full clone).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric ID of the source guest to clone — VMID for a QEMU VM or CTID for an LXC container. |
| `newid` | string | yes | Numeric ID to assign to the new cloned guest. |
| `kind` | string | no | Guest type: `lxc` for a container or `qemu` for a VM. (default: `"lxc"`) |
| `node` | string (nullable) | no | PVE node the source guest runs on. Omit to resolve it automatically from the cluster. (default: `null`) |
| `name` | string (nullable) | no | Name to give the new cloned guest. (default: `null`) |
| `full` | boolean | no | If true, make a full independent copy of the disks; if false (default), make a space-saving linked clone. (default: `false`) |
| `pool` | string (nullable) | no | Resource pool to place the new guest in — needed when the calling token is pool-scoped. (default: `null`) |
| `storage` | string (nullable) | no | Target storage for the full clone's disks (full=True only); keeps the clone off the source storage. Refused for a linked clone. (default: `null`) |
| `confirm` | boolean | no | Leave `false` (default) to get a dry-run PLAN; set `true` to execute the clone. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_cloudinit_get`

Read a QEMU guest's cloud-init configuration (read-only). Returns cloud-init fields
(ciuser, sshkeys, ipconfigN, cipassword placeholder) with secret fields masked for safety.
Use pve_cloudinit_set to mutate it; the set operation auto-captures an undo record for
rollback.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric VMID of the QEMU guest to read cloud-init config from. |
| `node` | string (nullable) | no | PVE node the guest runs on. Omit to resolve it automatically from the cluster. (default: `null`) |
| `kind` | string | no | Guest type; cloud-init applies to `qemu` guests. (default: `"qemu"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_cloudinit_set`

MUTATION: set cloud-init fields (ciuser/sshkeys/ipconfigN/...) on a QEMU guest. Dry-run by
default — the PLAN shows the diff with secrets masked; confirm=True to execute. Synchronous.
Secret fields (cipassword) are never echoed to results or the ledger.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric VMID of the QEMU guest to set cloud-init config on. |
| `changes` | object | yes | Cloud-init fields to change, e.g. {'ciuser': 'admin', 'sshkeys': '...', 'ipconfig0': 'ip=dhcp'}. |
| `node` | string (nullable) | no | PVE node the guest runs on. Omit to resolve it automatically from the cluster. (default: `null`) |
| `kind` | string | no | Guest type; cloud-init applies to `qemu` guests. (default: `"qemu"`) |
| `confirm` | boolean | no | Leave `false` (default) to get a dry-run PLAN with secrets masked; set `true` to execute. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_cluster_resources`

List all resources across the cluster (VMs, nodes, storage, SDN).
resource_type: optional filter — 'vm', 'storage', 'node', or 'sdn' (read).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `resource_type` | string (nullable) | no | Optional filter: 'vm', 'storage', 'node', or 'sdn'; omit to list all resource types. (default: `null`) |
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
| `vmid` | string | yes | Numeric CTID to assign to the new LXC container. |
| `ostemplate` | string | yes | Storage volume ID of the OS template to install, e.g. `local:vztmpl/debian-12-standard_12.2-1_amd64.tar.zst`. |
| `storage` | string | yes | Storage backend name to place the container's root filesystem on. |
| `node` | string (nullable) | no | PVE node to create the container on. Omit to use the configured default node. (default: `null`) |
| `options` | object (nullable) | no | Extra Proxmox create params (e.g. cores, memory, net0, rootfs, password) merged into the request. (default: `null`) |
| `confirm` | boolean | no | Leave `false` (default) to get a dry-run PLAN; set `true` to execute the creation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_create_vm`

MUTATION: create a new QEMU VM. Dry-run by default; confirm=True. Async — returns a UPID.
`options` carries create params (cores, memory, net0, scsi0, ostype, ...).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric VMID to assign to the new QEMU VM. |
| `node` | string (nullable) | no | PVE node to create the VM on. Omit to use the configured default node. (default: `null`) |
| `options` | object (nullable) | no | Extra Proxmox create params (e.g. cores, memory, net0, scsi0, ostype) merged into the request. (default: `null`) |
| `confirm` | boolean | no | Leave `false` (default) to get a dry-run PLAN; set `true` to execute the creation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_delete_guest`

MUTATION (DESTRUCTIVE, IRREVERSIBLE): permanently destroy a guest and its disks. Dry-run by
default — the PLAN names exactly what will be destroyed. confirm=True to execute. Async — UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric ID of the guest to destroy — VMID for a QEMU VM or CTID for an LXC container. |
| `kind` | string | no | Guest type: `lxc` for a container or `qemu` for a VM. (default: `"lxc"`) |
| `node` | string (nullable) | no | PVE node the guest runs on. Omit to resolve it automatically from the cluster. (default: `null`) |
| `purge` | boolean | no | If true, also remove the guest from replication/backup jobs and HA resources referencing it. (default: `false`) |
| `force` | boolean | no | Force removal even if the guest is still running or the backend reports an inconsistent state. (default: `false`) |
| `confirm` | boolean | no | Leave `false` (default) to get a dry-run PLAN naming exactly what will be destroyed; set `true` to execute. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_diagnose`

READ-ONLY: gather node health evidence — status + storage usage + recent failed tasks + flags.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node to gather health evidence for. Omit to use the configured default node. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_disk_move`

MUTATION: move a guest disk to another storage. Dry-run by default — the PLAN shows
source->target and whether the source copy is deleted (delete_source=True is HIGH). confirm=True
to execute. Async — returns a task UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric ID of the guest — VMID for a QEMU VM or CTID for an LXC container. |
| `disk` | string | yes | Disk key to move, e.g. `scsi0` or `rootfs`. |
| `target_storage` | string | yes | Storage backend name to move the disk to. |
| `kind` | string | no | Guest type: `lxc` for a container or `qemu` for a VM. (default: `"lxc"`) |
| `node` | string (nullable) | no | PVE node the guest runs on. Omit to resolve it automatically from the cluster. (default: `null`) |
| `delete_source` | boolean | no | If true, delete the source copy after the move (HIGH risk); if false (default), keep it. (default: `false`) |
| `confirm` | boolean | no | Leave `false` (default) to get a dry-run PLAN; set `true` to execute the move. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_disk_resize`

MUTATION: grow a guest disk (e.g. size='+10G'). GROW ONLY — a shrink is refused (destructive).
Dry-run by default; confirm=True to execute. Async — returns a task UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric ID of the guest — VMID for a QEMU VM or CTID for an LXC container. |
| `disk` | string | yes | Disk key to resize, e.g. `scsi0` or `rootfs`. |
| `size` | string | yes | New size, as a grow-only delta like `+10G` (shrinking is refused as destructive). |
| `kind` | string | no | Guest type: `lxc` for a container or `qemu` for a VM. (default: `"lxc"`) |
| `node` | string (nullable) | no | PVE node the guest runs on. Omit to resolve it automatically from the cluster. (default: `null`) |
| `confirm` | boolean | no | Leave `false` (default) to get a dry-run PLAN; set `true` to execute the resize. (default: `false`) |
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
| `name` | string | yes | Name for the new alias, referenced by rules as this name. |
| `cidr` | string | yes | IP address or CIDR network the alias resolves to. |
| `scope` | string | no | Firewall scope: 'cluster' or 'guest' (no node-scope aliases in the PVE API). (default: `"cluster"`) |
| `node` | string (nullable) | no | Node name, required for scope='guest'. (default: `null`) |
| `vmid` | string (nullable) | no | Guest VMID/CTID, required for scope='guest'. (default: `null`) |
| `kind` | string (nullable) | no | Guest kind for scope='guest': 'qemu' or 'lxc'. (default: `null`) |
| `comment` | string (nullable) | no | Free-text comment stored with the alias. (default: `null`) |
| `confirm` | boolean | no | Set True to execute the mutation; False (default) only returns a dry-run PLAN. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_alias_delete`

MUTATION: delete a firewall alias. Dry-run by default — the PLAN shows the current alias.
PVE refuses while any rule still references the alias. No UNDO: re-create to revert.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the alias to delete. |
| `scope` | string | no | Firewall scope: 'cluster' or 'guest' (no node-scope aliases in the PVE API). (default: `"cluster"`) |
| `node` | string (nullable) | no | Node name, required for scope='guest'. (default: `null`) |
| `vmid` | string (nullable) | no | Guest VMID/CTID, required for scope='guest'. (default: `null`) |
| `kind` | string (nullable) | no | Guest kind for scope='guest': 'qemu' or 'lxc'. (default: `null`) |
| `digest` | string (nullable) | no | Optimistic-lock digest from the PLAN preview; pass on confirm to abort if the alias changed since. (default: `null`) |
| `confirm` | boolean | no | Set True to execute the mutation; False (default) only returns a dry-run PLAN. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_alias_list`

List firewall aliases (named CIDRs) for the given scope (read). Scope = cluster
or guest only — the PVE API has no node-scope aliases (node firewall = options/rules/log).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `scope` | string | no | Firewall scope: 'cluster' or 'guest' (no node-scope aliases in the PVE API). (default: `"cluster"`) |
| `node` | string (nullable) | no | Node name, required for scope='guest'. (default: `null`) |
| `vmid` | string (nullable) | no | Guest VMID/CTID, required for scope='guest'. (default: `null`) |
| `kind` | string (nullable) | no | Guest kind for scope='guest': 'qemu' or 'lxc'. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_alias_update`

MUTATION: update a firewall alias. Dry-run by default — the PLAN shows the current alias and
the fields being changed. Changing the CIDR silently alters every referencing rule's match set.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the existing alias to update. |
| `scope` | string | no | Firewall scope: 'cluster' or 'guest' (no node-scope aliases in the PVE API). (default: `"cluster"`) |
| `node` | string (nullable) | no | Node name, required for scope='guest'. (default: `null`) |
| `vmid` | string (nullable) | no | Guest VMID/CTID, required for scope='guest'. (default: `null`) |
| `kind` | string (nullable) | no | Guest kind for scope='guest': 'qemu' or 'lxc'. (default: `null`) |
| `cidr` | string (nullable) | no | New IP address/CIDR the alias should resolve to; omit to leave unchanged. (default: `null`) |
| `comment` | string (nullable) | no | New free-text comment; omit to leave unchanged. (default: `null`) |
| `rename` | string (nullable) | no | New name to rename the alias to; omit to keep the current name. (default: `null`) |
| `digest` | string (nullable) | no | Optimistic-lock digest from the PLAN preview; pass on confirm to abort if the alias changed since. (default: `null`) |
| `confirm` | boolean | no | Set True to execute the mutation; False (default) only returns a dry-run PLAN. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_ipset_create`

MUTATION: create an empty IP set. Dry-run by default — the PLAN shows the name and scope.
Passive until a rule references it as '+name' and entries are added.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name for the new IP set, referenced by rules as '+name'. |
| `scope` | string | no | Firewall scope: 'cluster' or 'guest' (no node-scope ipsets in the PVE API). (default: `"cluster"`) |
| `node` | string (nullable) | no | Node name, required for scope='guest'. (default: `null`) |
| `vmid` | string (nullable) | no | Guest VMID/CTID, required for scope='guest'. (default: `null`) |
| `kind` | string (nullable) | no | Guest kind for scope='guest': 'qemu' or 'lxc'. (default: `null`) |
| `comment` | string (nullable) | no | Free-text comment stored with the IP set. (default: `null`) |
| `confirm` | boolean | no | Set True to execute the mutation; False (default) only returns a dry-run PLAN. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_ipset_delete`

MUTATION: delete an IP set. Dry-run by default — the PLAN shows member count and the
force semantics. force=True WIPES all members; PVE refuses while a rule references the set.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the IP set to delete. |
| `scope` | string | no | Firewall scope: 'cluster' or 'guest' (no node-scope ipsets in the PVE API). (default: `"cluster"`) |
| `node` | string (nullable) | no | Node name, required for scope='guest'. (default: `null`) |
| `vmid` | string (nullable) | no | Guest VMID/CTID, required for scope='guest'. (default: `null`) |
| `kind` | string (nullable) | no | Guest kind for scope='guest': 'qemu' or 'lxc'. (default: `null`) |
| `force` | boolean | no | If True, wipe all member entries so the (now-empty) IP set can be deleted. (default: `false`) |
| `confirm` | boolean | no | Set True to execute the mutation; False (default) only returns a dry-run PLAN. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_ipset_entry_add`

MUTATION: add an IP/Network entry to an IP set. Dry-run by default — the PLAN shows the
entry and warns it changes every referencing rule's match set. nomatch=True = exclusion.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the IP set to add the entry to. |
| `cidr` | string | yes | IP address or CIDR network to add as a member entry. |
| `scope` | string | no | Firewall scope: 'cluster' or 'guest' (no node-scope ipsets in the PVE API). (default: `"cluster"`) |
| `node` | string (nullable) | no | Node name, required for scope='guest'. (default: `null`) |
| `vmid` | string (nullable) | no | Guest VMID/CTID, required for scope='guest'. (default: `null`) |
| `kind` | string (nullable) | no | Guest kind for scope='guest': 'qemu' or 'lxc'. (default: `null`) |
| `comment` | string (nullable) | no | Free-text comment stored with the entry. (default: `null`) |
| `nomatch` | boolean | no | If True, this entry is an exclusion (negative match) rather than an inclusion. (default: `false`) |
| `confirm` | boolean | no | Set True to execute the mutation; False (default) only returns a dry-run PLAN. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_ipset_entry_remove`

MUTATION: remove an IP/Network entry from an IP set. Dry-run by default — the PLAN shows the
entry and warns it changes every referencing rule's match set (may open or close access).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the IP set to remove the entry from. |
| `cidr` | string | yes | IP address or CIDR network of the member entry to remove. |
| `scope` | string | no | Firewall scope: 'cluster' or 'guest' (no node-scope ipsets in the PVE API). (default: `"cluster"`) |
| `node` | string (nullable) | no | Node name, required for scope='guest'. (default: `null`) |
| `vmid` | string (nullable) | no | Guest VMID/CTID, required for scope='guest'. (default: `null`) |
| `kind` | string (nullable) | no | Guest kind for scope='guest': 'qemu' or 'lxc'. (default: `null`) |
| `digest` | string (nullable) | no | Optimistic-lock digest from the PLAN preview; pass on confirm to abort if the set changed since. (default: `null`) |
| `confirm` | boolean | no | Set True to execute the mutation; False (default) only returns a dry-run PLAN. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_options_get`

Get firewall options (enable flag, policy, log rate, …) for the given scope (read).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `scope` | string | no | Firewall scope: 'cluster', 'node', or 'guest'. (default: `"cluster"`) |
| `node` | string (nullable) | no | Node name, required for scope='node' or scope='guest'. (default: `null`) |
| `vmid` | string (nullable) | no | Guest VMID/CTID, required for scope='guest'. (default: `null`) |
| `kind` | string (nullable) | no | Guest kind for scope='guest': 'qemu' or 'lxc'. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_options_set`

MUTATION: set firewall options for a scope (policy_in/out, log levels, ebtables, log_ratelimit,
...). `options` is a key->value bag; `delete` unsets keys. Dry-run by default — the PLAN shows the
current values and flags lockout risk. RISK_HIGH when enabling the firewall or changing a policy.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `scope` | string | no | Firewall scope: 'cluster', 'node', or 'guest'. (default: `"cluster"`) |
| `node` | string (nullable) | no | Node name, required for scope='node' or scope='guest'. (default: `null`) |
| `vmid` | string (nullable) | no | Guest VMID/CTID, required for scope='guest'. (default: `null`) |
| `kind` | string (nullable) | no | Guest kind for scope='guest': 'qemu' or 'lxc'. (default: `null`) |
| `options` | object (nullable) | no | Key-value bag of firewall options to set, e.g. policy_in, policy_out, log_ratelimit, enable, ebtables. (default: `null`) |
| `delete` | array<string> (nullable) | no | List of option keys to unset/remove. (default: `null`) |
| `digest` | string (nullable) | no | Optimistic-lock digest from the PLAN preview; pass on confirm to abort if the options changed since. (default: `null`) |
| `confirm` | boolean | no | Set True to execute the mutation; False (default) only returns a dry-run PLAN. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_rule_add`

MUTATION: add a new firewall rule. Dry-run by default — the PLAN shows scope, direction,
action, and key address/port fields. Re-call with confirm=True to execute. Synchronous.

WARNING: a misplaced DROP/REJECT can cause a connectivity lockout.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `action` | string | yes | Rule action: 'ACCEPT', 'DROP', or 'REJECT'. |
| `direction` | string | no | Traffic direction the rule matches: 'in' or 'out'. (default: `"in"`) |
| `scope` | string | no | Firewall scope: 'cluster', 'node', or 'guest'. (default: `"cluster"`) |
| `node` | string (nullable) | no | Node name, required for scope='node' or scope='guest'. (default: `null`) |
| `vmid` | string (nullable) | no | Guest VMID/CTID, required for scope='guest'. (default: `null`) |
| `kind` | string (nullable) | no | Guest kind for scope='guest': 'qemu' or 'lxc'. (default: `null`) |
| `source` | string (nullable) | no | Source address/CIDR/alias to match, or None for any. (default: `null`) |
| `dest` | string (nullable) | no | Destination address/CIDR/alias to match, or None for any. (default: `null`) |
| `proto` | string (nullable) | no | IP protocol to match, e.g. 'tcp', 'udp', 'icmp'. (default: `null`) |
| `dport` | string (nullable) | no | Destination port or port range to match, e.g. '22' or '8000:8010'. (default: `null`) |
| `sport` | string (nullable) | no | Source port or port range to match, e.g. '22' or '8000:8010'. (default: `null`) |
| `comment` | string (nullable) | no | Free-text comment stored with the rule. (default: `null`) |
| `enable` | boolean | no | Whether the rule is active immediately (True) or created disabled (False). (default: `true`) |
| `confirm` | boolean | no | Set True to execute the mutation; False (default) only returns a dry-run PLAN. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_rule_remove`

MUTATION: delete a firewall rule by position. Dry-run by default — the PLAN shows the rule
at that position AND the optimistic-lock digest. Positions SHIFT after inserts/deletes — pass the
digest from the plan back as `digest=` on confirm so PVE rejects the delete if the rule list moved
since the preview (otherwise a concurrent insert can shift positions and remove the wrong rule).
Synchronous.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `pos` | integer | yes | Rule position (0-based index) in the target scope's rule list. |
| `scope` | string | no | Firewall scope: 'cluster', 'node', or 'guest'. (default: `"cluster"`) |
| `node` | string (nullable) | no | Node name, required for scope='node' or scope='guest'. (default: `null`) |
| `vmid` | string (nullable) | no | Guest VMID/CTID, required for scope='guest'. (default: `null`) |
| `kind` | string (nullable) | no | Guest kind for scope='guest': 'qemu' or 'lxc'. (default: `null`) |
| `digest` | string (nullable) | no | Optimistic-lock digest from the PLAN preview; pass on confirm to abort if the rule list changed since. (default: `null`) |
| `confirm` | boolean | no | Set True to execute the mutation; False (default) only returns a dry-run PLAN. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_rule_update`

MUTATION: update an existing firewall rule at position `pos`. Dry-run by default — the PLAN
shows the rule's current state, the fields being changed, AND the optimistic-lock digest. Pass the
digest from the plan back as `digest=` on confirm so PVE rejects the update if the rule list moved
since the preview (positions shift and the wrong rule can be updated otherwise). Synchronous.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `pos` | integer | yes | Rule position (0-based index) in the target scope's rule list. |
| `scope` | string | no | Firewall scope: 'cluster', 'node', or 'guest'. (default: `"cluster"`) |
| `node` | string (nullable) | no | Node name, required for scope='node' or scope='guest'. (default: `null`) |
| `vmid` | string (nullable) | no | Guest VMID/CTID, required for scope='guest'. (default: `null`) |
| `kind` | string (nullable) | no | Guest kind for scope='guest': 'qemu' or 'lxc'. (default: `null`) |
| `action` | string (nullable) | no | New rule action: 'ACCEPT', 'DROP', or 'REJECT'; omit to leave unchanged. (default: `null`) |
| `direction` | string (nullable) | no | New traffic direction: 'in' or 'out'; omit to leave unchanged. (default: `null`) |
| `source` | string (nullable) | no | New source address/CIDR/alias to match; omit to leave unchanged. (default: `null`) |
| `dest` | string (nullable) | no | New destination address/CIDR/alias to match; omit to leave unchanged. (default: `null`) |
| `proto` | string (nullable) | no | New IP protocol to match, e.g. 'tcp'/'udp'/'icmp'; omit to leave unchanged. (default: `null`) |
| `dport` | string (nullable) | no | New destination port or port range; omit to leave unchanged. (default: `null`) |
| `sport` | string (nullable) | no | New source port or port range; omit to leave unchanged. (default: `null`) |
| `comment` | string (nullable) | no | New free-text comment; omit to leave unchanged. (default: `null`) |
| `enable` | boolean (nullable) | no | New enabled state for the rule; omit to leave unchanged. (default: `null`) |
| `digest` | string (nullable) | no | Optimistic-lock digest from the PLAN preview; pass on confirm to abort if the rule list changed since. (default: `null`) |
| `confirm` | boolean | no | Set True to execute the mutation; False (default) only returns a dry-run PLAN. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_rules_list`

List firewall rules for the given scope (cluster, node, or guest) (read-only).

Returns the active rules at that scope level, including action, direction, protocol,
and address/port fields. Use pve_firewall_options_get to read firewall settings
(enable flag, policy, log rate).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `scope` | string | no | Firewall scope: 'cluster', 'node', or 'guest'. (default: `"cluster"`) |
| `node` | string (nullable) | no | Node name, required for scope='node' or scope='guest'. (default: `null`) |
| `vmid` | string (nullable) | no | Guest VMID/CTID, required for scope='guest'. (default: `null`) |
| `kind` | string (nullable) | no | Guest kind for scope='guest': 'qemu' or 'lxc'. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_security_group_create`

MUTATION: create an empty cluster security group. Dry-run by default — the PLAN shows the
name. Passive until rules are added and a rule references it (type=group).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `group` | string | yes | Name for the new cluster security group. |
| `comment` | string (nullable) | no | Free-text comment stored with the group. (default: `null`) |
| `confirm` | boolean | no | Set True to execute the mutation; False (default) only returns a dry-run PLAN. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_security_group_delete`

MUTATION: delete a cluster security group. Dry-run by default — the PLAN shows how many rules
the group holds. PVE refuses while the group is non-empty or still referenced by a rule.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `group` | string | yes | Name of the cluster security group to delete. |
| `confirm` | boolean | no | Set True to execute the mutation; False (default) only returns a dry-run PLAN. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_set_enabled`

MUTATION (HIGH RISK): toggle the firewall on or off for the given scope. Dry-run by default.
RISK_HIGH both directions: enabling may instantly lock you out (default-DROP, no ACCEPT for 22/8006);
disabling strips all protection. Cluster scope = master kill-switch. Synchronous.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `enabled` | boolean | yes | Desired firewall state: True to turn on, False to turn off. |
| `scope` | string | no | Firewall scope: 'cluster', 'node', or 'guest'. (default: `"cluster"`) |
| `node` | string (nullable) | no | Node name, required for scope='node' or scope='guest'. (default: `null`) |
| `vmid` | string (nullable) | no | Guest VMID/CTID, required for scope='guest'. (default: `null`) |
| `kind` | string (nullable) | no | Guest kind for scope='guest': 'qemu' or 'lxc'. (default: `null`) |
| `confirm` | boolean | no | Set True to execute the mutation; False (default) only returns a dry-run PLAN. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_group_create`

MUTATION: create an (empty) group. Dry-run by default (additive, LOW risk).
Returns the plan preview; confirm=True to execute. The group is inert until users are
added or an ACL entry grants it privileges.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `groupid` | string | yes | New group id. |
| `comment` | string (nullable) | no | Optional free-text comment. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_group_delete`

MUTATION (HIGH): delete a group. Dry-run by default — the PLAN reads members and warns ACLs
granted to/on the group are orphaned. confirm=True.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `groupid` | string | yes | Group id to delete. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_group_get`

Get a group's full config (read-only). Returns groupid, comment, and member list (users in
the group). Use pve_group_create/update/delete to manage the group; use pve_acl_list to see
ACL entries referencing this group.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `groupid` | string | yes | Group id to look up. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_group_update`

MUTATION: update a group's comment. Dry-run by default (additive, LOW risk).
Returns the plan preview; confirm=True to execute. Does not modify group membership.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `groupid` | string | yes | Group id to update. |
| `comment` | string (nullable) | no | New free-text comment. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
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
| `vmid` | string | yes | Numeric ID of the guest — VMID for a QEMU VM or CTID for an LXC container. |
| `kind` | string | no | Guest type: `lxc` for a container or `qemu` for a VM. (default: `"lxc"`) |
| `node` | string (nullable) | no | PVE node the guest runs on. Omit to resolve it automatically from the cluster. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_guest_config_revert`

MUTATION (UNDO): re-apply a previously captured guest config (the prior_config returned by
pve_guest_config_set). Dry-run by default; confirm=True to execute. Synchronous.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric ID of the guest — VMID for a QEMU VM or CTID for an LXC container. |
| `prior_config` | object | yes | The prior config dict previously returned by pve_guest_config_set, to re-apply. |
| `kind` | string | no | Guest type: `lxc` for a container or `qemu` for a VM. (default: `"lxc"`) |
| `node` | string (nullable) | no | PVE node the guest runs on. Omit to resolve it automatically from the cluster. (default: `null`) |
| `confirm` | boolean | no | Leave `false` (default) to get a dry-run PLAN; set `true` to execute the revert. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_guest_config_set`

MUTATION: edit a guest's config (cores/memory/net/onboot/...). Dry-run by default — the PLAN
shows the exact per-key diff; confirm=True to execute. Captures the prior config first so the
change is revertible via pve_guest_config_revert. Synchronous.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric ID of the guest — VMID for a QEMU VM or CTID for an LXC container. |
| `changes` | object | yes | Config keys to change, e.g. {'cores': 4, 'memory': 2048, 'onboot': 1}. |
| `kind` | string | no | Guest type: `lxc` for a container or `qemu` for a VM. (default: `"lxc"`) |
| `node` | string (nullable) | no | PVE node the guest runs on. Omit to resolve it automatically from the cluster. (default: `null`) |
| `confirm` | boolean | no | Leave `false` (default) to get a dry-run PLAN with the per-key diff; set `true` to execute. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_guest_migrate`

MUTATION: migrate a guest to a different node. Dry-run by default — the PLAN shows the
guest's live state, the source→target, and the honest blast radius (LXC 'online' is
stop→move→start, NOT zero-downtime; QEMU live migration requires shared storage).
confirm=True to execute. Async — returns a task UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric VMID/CTID of the guest to migrate. |
| `target` | string | yes | Destination node name to migrate the guest to. |
| `kind` | string | no | Guest type: 'lxc' or 'qemu'. (default: `"lxc"`) |
| `node` | string (nullable) | no | Source node name; defaults to the configured node. (default: `null`) |
| `online` | boolean | no | QEMU: live migration (zero-downtime, needs shared storage). LXC: stop-move-start restart migration (real downtime). False = offline migration. (default: `false`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the migration. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_guest_power`

MUTATION: start/stop/reboot/shutdown a guest.

Dry-run by default: without confirm=True you get a PLAN — the exact change, the guest's live
state, blast radius, and risk (with no-op detection) — recorded to the ledger. Re-call with
confirm=True to execute. The plan is recorded on BOTH paths: even a one-shot confirm=True call
records its plan before mutating — no plan, no mutation.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric ID of the guest — VMID for a QEMU VM or CTID for an LXC container. |
| `action` | string | yes | Power action to perform: `start`, `stop`, `reboot`, or `shutdown`. |
| `kind` | string | no | Guest type: `lxc` for a container or `qemu` for a VM. (default: `"lxc"`) |
| `node` | string (nullable) | no | PVE node the guest runs on. Omit to resolve it automatically from the cluster. (default: `null`) |
| `confirm` | boolean | no | Leave `false` (default) to get a dry-run PLAN with blast radius; set `true` to execute the action. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_guest_status`

Read the operational status and current configuration of a single guest (kind='lxc' or
'qemu') (read-only). Returns the guest's runtime state and resource utilization
(CPU/memory/disk/network/uptime) — operational metrics, not its stored configuration.
Use pve_guest_config_get for the full configuration.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric ID of the guest — VMID for a QEMU VM or CTID for an LXC container. |
| `kind` | string | no | Guest type: `lxc` for a container or `qemu` for a VM. (default: `"lxc"`) |
| `node` | string (nullable) | no | PVE node the guest runs on. Omit to resolve it automatically from the cluster. (default: `null`) |
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
| `vmid` | string | yes | Numeric VMID/CTID of the guest to add to HA management. |
| `kind` | string | no | Guest type: 'lxc' or 'qemu'. (default: `"lxc"`) |
| `group` | string (nullable) | no | HA group to assign (PVE 8 only; PVE 9 removed groups in favor of HA rules — omit on PVE 9). (default: `null`) |
| `state` | string (nullable) | no | Desired HA state, e.g. 'started', 'stopped', 'disabled' ('stopped' has the CRM stop the guest). (default: `null`) |
| `max_restart` | integer (nullable) | no | Max number of restart attempts the CRM makes before giving up. (default: `null`) |
| `max_relocate` | integer (nullable) | no | Max number of relocation attempts the CRM makes before giving up. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the change. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_ha_resource_remove`

MUTATION: remove a guest from HA management. Dry-run by default — the PLAN shows the SID
and that this loses automated failover protection (guest itself is NOT stopped).
confirm=True to execute. Synchronous (pmxcfs config write).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric VMID/CTID of the guest to remove from HA management. |
| `kind` | string | no | Guest type: 'lxc' or 'qemu'. (default: `"lxc"`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the change. (default: `false`) |
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
| `rule` | string | yes | New HA rule ID (name used to reference this rule). |
| `rule_type` | string | yes | Rule type: 'node-affinity' (requires nodes) or 'resource-affinity' (requires affinity). |
| `resources` | string | yes | Comma-separated HA resource SIDs the rule applies to, e.g. 'vm:100,ct:101'. |
| `comment` | string (nullable) | no | Free-text comment stored with the rule. (default: `null`) |
| `disable` | boolean | no | If True, the rule is created disabled (no effect until enabled). (default: `false`) |
| `nodes` | string (nullable) | no | Comma-separated node list with optional priority, e.g. 'pve1:2,pve2' — required for rule_type='node-affinity'. (default: `null`) |
| `strict` | boolean | no | node-affinity only: if True, resources may run ONLY on the listed nodes (availability risk if all are down). (default: `false`) |
| `affinity` | string (nullable) | no | 'positive' (keep resources together) or 'negative' (keep resources apart) — required for rule_type='resource-affinity'. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the change. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_ha_rule_delete`

MUTATION: delete an HA rule. Dry-run by default — the PLAN shows the current rule and that
its resources lose this placement constraint (CRM may migrate them). confirm=True to execute.
Synchronous. RISK_MEDIUM.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `rule` | string | yes | HA rule ID to delete. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_ha_rule_update`

MUTATION: update an HA rule. Dry-run by default — the PLAN shows the current rule and the
fields being changed. `delete` unsets keys. confirm=True to execute. Synchronous.
RISK_MEDIUM — may trigger CRM migration of affected resources.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `rule` | string | yes | HA rule ID to update. |
| `comment` | string (nullable) | no | New free-text comment for the rule. (default: `null`) |
| `disable` | boolean (nullable) | no | True to disable the rule, False to enable it, omit to leave unchanged. (default: `null`) |
| `resources` | string (nullable) | no | New comma-separated HA resource SIDs the rule applies to, e.g. 'vm:100,ct:101'. (default: `null`) |
| `rule_type` | string (nullable) | no | New rule type: 'node-affinity' or 'resource-affinity'. (default: `null`) |
| `nodes` | string (nullable) | no | New comma-separated node list with optional priority, e.g. 'pve1:2,pve2' (node-affinity rules). (default: `null`) |
| `strict` | boolean (nullable) | no | node-affinity only: True restricts resources to ONLY the listed nodes. (default: `null`) |
| `affinity` | string (nullable) | no | 'positive' or 'negative' (resource-affinity rules). (default: `null`) |
| `delete` | array<string> (nullable) | no | List of field names to unset on the rule, e.g. ['strict', 'nodes']. (default: `null`) |
| `digest` | string (nullable) | no | Expected config digest for optimistic-locking; PUT is rejected if the stored digest differs. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the change. (default: `false`) |
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
| `node` | string | yes | PVE node name to list physical hardware devices on |
| `hw_type` | string | no | Device class to list: 'pci' (default) or 'usb' (default: `"pci"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_ipset_list`

List IP sets for the given scope (read). Scope = cluster or guest only —
the PVE API has no node-scope ipsets (node firewall = options/rules/log).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `scope` | string | no | Firewall scope: 'cluster' or 'guest' (no node-scope ipsets in the PVE API). (default: `"cluster"`) |
| `node` | string (nullable) | no | Node name, required for scope='guest'. (default: `null`) |
| `vmid` | string (nullable) | no | Guest VMID/CTID, required for scope='guest'. (default: `null`) |
| `kind` | string (nullable) | no | Guest kind for scope='guest': 'qemu' or 'lxc'. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_list_guests`

List all VMs and LXC containers on a node with their current state (read-only). Returns
a list of guest objects, each with VMID, name, type (lxc or qemu), and status. Works across
both kinds in a single call.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name to list guests on. Omit to list guests across the whole cluster. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_mapping_pci_create`

MUTATION: create a PCI cluster passthrough mapping. Dry-run by default.
confirm=True to execute. Smoke-confirm: POST body shape (id in body) against a live PVE instance.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `mapping_id` | string | yes | Unique ID for the new PCI cluster passthrough mapping |
| `description` | string (nullable) | no | Optional free-text description stored with the mapping (default: `null`) |
| `map` | string (nullable) | no | PCI device map string(s) defining the physical device(s) covered by this mapping (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the creation (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_mapping_pci_delete`

MUTATION: delete a PCI cluster mapping. Dry-run by default.
confirm=True to execute. VMs referencing this mapping lose the device path.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `mapping_id` | string | yes | ID of the PCI cluster mapping to delete |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion (default: `false`) |
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
| `mapping_id` | string | yes | ID of the existing PCI cluster mapping to update |
| `description` | string (nullable) | no | Optional free-text description to set on the mapping (default: `null`) |
| `map` | string (nullable) | no | PCI device map string(s) defining the physical device(s) covered by this mapping (default: `null`) |
| `digest` | string (nullable) | no | Optional config digest for optimistic-concurrency check against the current config (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the update (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_mapping_usb_create`

MUTATION: create a USB cluster passthrough mapping. Dry-run by default.
confirm=True to execute. Smoke-confirm: POST body shape (id in body) against a live PVE instance.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `mapping_id` | string | yes | Unique ID for the new USB cluster passthrough mapping |
| `description` | string (nullable) | no | Optional free-text description stored with the mapping (default: `null`) |
| `map` | string (nullable) | no | USB device map string(s) defining the physical device(s) covered by this mapping (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the creation (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_mapping_usb_delete`

MUTATION: delete a USB cluster mapping. Dry-run by default.
confirm=True to execute. VMs referencing this mapping lose the USB device path.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `mapping_id` | string | yes | ID of the USB cluster mapping to delete |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion (default: `false`) |
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
| `mapping_id` | string | yes | ID of the existing USB cluster mapping to update |
| `description` | string (nullable) | no | Optional free-text description to set on the mapping (default: `null`) |
| `map` | string (nullable) | no | USB device map string(s) defining the physical device(s) covered by this mapping (default: `null`) |
| `digest` | string (nullable) | no | Optional config digest for optimistic-concurrency check against the current config (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the update (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_metrics_server_delete`

MUTATION: delete a PVE metrics server definition. Dry-run by default.
confirm=True to execute. Metrics forwarding to this server ceases; no data loss.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `metrics_id` | string | yes | ID of the metrics server definition to delete |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion (default: `false`) |
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
| `metrics_id` | string | yes | Unique ID of the metrics server definition to create or update |
| `metrics_type` | string (nullable) | no | Metrics backend type, e.g. 'influxdb' or 'graphite' (default: `null`) |
| `server` | string (nullable) | no | Hostname or IP address of the metrics server (default: `null`) |
| `port` | integer (nullable) | no | TCP/UDP port the metrics server listens on (default: `null`) |
| `disable` | boolean (nullable) | no | True disables forwarding to this metrics server without deleting the definition (default: `null`) |
| `comment` | string (nullable) | no | Optional free-text comment stored with the metrics server definition (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the create/update (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_network_apply`

MUTATION (HIGH RISK): apply staged network config changes to the live network stack.
Dry-run by default — the PLAN surfaces pending interfaces. confirm=True to execute.
A misconfigured interface can lose SSH/API access; recovery requires console/physical access.
May return a UPID (async) or None (sync) — outcome='submitted' in either case.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | Node to apply staged network config on; defaults to the configured node. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True applies the staged config to the live network stack. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_network_iface_create`

MUTATION: create a new network interface config (staged — not live until pve_network_apply).
Dry-run by default; confirm=True to execute. Synchronous.
`options` carries type-dependent fields (address, netmask, gateway, bridge_ports, …).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `iface` | string | yes | New interface name to create, e.g. vmbr1 or eth0.100. |
| `iface_type` | string | yes | Interface type: bridge, bond, vlan, eth, or alias. |
| `node` | string (nullable) | no | Node to create the interface on; defaults to the configured node. (default: `null`) |
| `options` | object (nullable) | no | Type-dependent fields: address, netmask, gateway, bridge_ports, etc. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True stages the interface (still not live until pve_network_apply). (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_network_iface_update`

MUTATION: update an existing network interface config (staged — not live until pve_network_apply).
Dry-run by default; confirm=True to execute. Synchronous.
`options` carries fields to update (address, netmask, bridge_ports, …).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `iface` | string | yes | Existing interface name to update, e.g. vmbr1 or eth0.100. |
| `node` | string (nullable) | no | Node the interface lives on; defaults to the configured node. (default: `null`) |
| `options` | object (nullable) | no | Fields to update: address, netmask, bridge_ports, etc. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True stages the update (still not live until pve_network_apply). (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_network_list`

List network interfaces on a node (read-only). Returns iface name, type
(bridge/bond/vlan/eth/alias), method, and address. Filter by type with iface_type.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | Node name to list interfaces on; defaults to the configured node. (default: `null`) |
| `iface_type` | string (nullable) | no | Filter to one interface type: bridge, bond, vlan, eth, or alias. (default: `null`) |
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
| `account` | string | yes | Name of the ACME account (created via pve_acme_account_create) to associate with the node. |
| `domains` | array<string> | yes | Domain names to request a certificate for; replaces any existing acmedomainN entries on the node. |
| `node` | string (nullable) | no | Target PVE node name; omit to use the configured default node. (default: `null`) |
| `plugin` | string (nullable) | no | ACME DNS plugin ID for a DNS-01 challenge; omit to use standalone http-01 instead. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the node config change. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_cert_delete`

MUTATION: delete the custom TLS certificate from a PVE node.

RISK_MEDIUM: PVE reverts to its self-signed certificate (recoverable by re-uploading).
restart=True reloads pveproxy after deletion. confirm=True to execute.

DELETE /nodes/{node}/certificates/custom
Smoke-confirm: endpoint and params shape not live-verified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name to delete the custom certificate from; defaults to the configured node if omitted. (default: `null`) |
| `restart` | boolean | no | If True, reload pveproxy after deletion to apply the reverted self-signed certificate immediately. (default: `false`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion. (default: `false`) |
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
| `certificates` | string | yes | PEM-encoded certificate chain (public, may appear in plans/logs). |
| `key` | string (nullable) | no | PEM-encoded TLS private key matching the certificate; a secret, unconditionally redacted in all output. (default: `null`) |
| `node` | string (nullable) | no | PVE node name to upload the certificate to; defaults to the configured node if omitted. (default: `null`) |
| `force` | boolean | no | If True, overwrite an existing custom certificate without requiring it be replaced explicitly. (default: `false`) |
| `restart` | boolean | no | If True, reload pveproxy after upload to apply the new certificate immediately (brief service interruption). (default: `false`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the certificate upload. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_certificates`

List TLS certificates configured on a Proxmox node (read-only). Returns a
list of certificate dicts with filename, subject, issuer, validity dates
(notbefore/notafter), SANs, and fingerprint.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name; defaults to the configured node (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_disk_initgpt`

MUTATION: initialize a GPT partition table on a node disk.

RISK_HIGH: overwrites the existing partition table on the named disk; irreversible.
confirm=True to execute.

POST /nodes/{node}/disks/initgpt
Smoke-confirm: endpoint and body shape not live-verified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `disk` | string | yes | Device path/identifier of the disk to initialize with a new GPT partition table (e.g. /dev/sda); overwrites the existing partition table. |
| `node` | string (nullable) | no | PVE node name the disk lives on; defaults to the configured node if omitted. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the irreversible GPT init. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_disk_smart`

Get SMART health data for a disk on a PVE node (read).

GET /nodes/{node}/disks/smart?disk=… — SMART attributes and health status.
Smoke-confirm: GET (read) only — this tool does NOT trigger a self-test.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `disk` | string | yes | Device path/identifier of the disk to query (e.g. /dev/sda), as listed by pve_node_disks_list. |
| `node` | string (nullable) | no | PVE node name the disk lives on; defaults to the configured node if omitted. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_disk_wipe`

MUTATION: wipe ALL data and the partition table on a node disk.

RISK_HIGH, NO UNDO: DESTROYS all data, partitions, and filesystems on the named disk.
This is irreversible — all data is permanently erased. confirm=True to execute.

PUT /nodes/{node}/disks/wipedisk
Smoke-confirm: endpoint and body shape not live-verified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `disk` | string | yes | Device path/identifier of the disk to wipe (e.g. /dev/sda); ALL data and the partition table are destroyed. |
| `node` | string (nullable) | no | PVE node name the disk lives on; defaults to the configured node if omitted. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the irreversible wipe. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_disks_list`

List physical disks on a PVE node (read).

GET /nodes/{node}/disks/list — physical disk inventory and health info.
Smoke-confirm: response shape not live-verified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name to query; defaults to the configured node if omitted. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_dns`

Read a Proxmox node's DNS configuration (read-only). Returns a dict with
search domain and configured nameservers (dns1/dns2/dns3). Use pve_node_dns_set
to change it.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name; defaults to the configured node (default: `null`) |
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
| `search` | string (nullable) | no | DNS search domain to set on the node. (default: `null`) |
| `dns1` | string (nullable) | no | Primary DNS resolver IP address. (default: `null`) |
| `dns2` | string (nullable) | no | Secondary DNS resolver IP address. (default: `null`) |
| `dns3` | string (nullable) | no | Tertiary DNS resolver IP address. (default: `null`) |
| `node` | string (nullable) | no | PVE node name to configure; defaults to the configured node if omitted. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the DNS change. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_hosts_get`

Get the /etc/hosts content of a PVE node (read).

GET /nodes/{node}/hosts — returns {data, digest}.
Smoke-confirm: response shape not live-verified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name to query; defaults to the configured node if omitted. (default: `null`) |
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
| `data` | string | yes | Full replacement content for the node's /etc/hosts file. |
| `node` | string (nullable) | no | PVE node name to configure; defaults to the configured node if omitted. (default: `null`) |
| `digest` | string (nullable) | no | Expected content digest of the current /etc/hosts, for optimistic-concurrency conflict detection. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the replacement. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_journal`

Fetch journal entries from a PVE node (read; returns log-line strings). lastentries capped at 5000.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name; defaults to the configured node (default: `null`) |
| `lastentries` | integer | no | Number of most-recent journal lines to return, capped at 5000 (default: `100`) |
| `since` | string (nullable) | no | Only return entries at or after this timestamp (journalctl-compatible format) (default: `null`) |
| `until` | string (nullable) | no | Only return entries at or before this timestamp (journalctl-compatible format) (default: `null`) |
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
| `target` | string | yes | Destination PVE node name to migrate guests to. |
| `node` | string (nullable) | no | Source PVE node name whose guests to migrate; defaults to the configured node if omitted. (default: `null`) |
| `vms` | string (nullable) | no | Optional comma-separated list of VMIDs/CTIDs to limit the scope; omit to migrate all guests on the node. (default: `null`) |
| `maxworkers` | integer (nullable) | no | Maximum number of parallel migration workers to run. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the bulk migration. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_rrddata`

Fetch RRD (round-robin database) time-series telemetry for a PVE node
(read-only). Returns a list of data-point dicts with timestamps and metrics
(cpu, memory, disk, network) over the specified timeframe, optionally
aggregated by consolidation function (AVERAGE or MAX).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name; defaults to the configured node (default: `null`) |
| `timeframe` | string | no | RRD time window: 'hour', 'day', 'week', 'month', or 'year' (default: `"hour"`) |
| `cf` | string (nullable) | no | RRD consolidation function: 'AVERAGE' or 'MAX'; defaults to server-side default (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_service_control`

MUTATION: start/stop/restart/reload a service on a PVE node. Dry-run by default — the
PLAN flags lockout-class services (sshd/pveproxy/pvedaemon/pve-cluster/corosync/networking/
...) as HIGH because stop/restart can sever the management plane or break quorum. There is
NO auto-undo for a service control. confirm=True to execute. Async — returns a task UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `service` | string | yes | systemd service name to control, e.g. 'pveproxy' or 'sshd' |
| `action` | string | yes | Control action: 'start', 'stop', 'restart', or 'reload' |
| `node` | string (nullable) | no | PVE node name; defaults to the configured node (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the service control (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_service_status`

Get the current state of a single service on a PVE node (read).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `service` | string | yes | systemd service name, e.g. 'pveproxy' or 'sshd' |
| `node` | string (nullable) | no | PVE node name; defaults to the configured node (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_services_list`

List all services on a PVE node (read-only). Returns a list of service dicts
with name, state (running/dead/inactive), and description for each service.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name; defaults to the configured node (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_startall`

MUTATION: start all (or filtered) guests on a PVE node.

RISK_MEDIUM. Reversible — the inverse of pve_node_stopall. vms = optional CSV of VMIDs
to filter the scope. confirm=True to execute.

POST /nodes/{node}/startall
Smoke-confirm: endpoint and vms param format not live-verified. May return task UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name whose guests to start; defaults to the configured node if omitted. (default: `null`) |
| `vms` | string (nullable) | no | Optional comma-separated list of VMIDs/CTIDs to limit the scope; omit to start all guests on the node. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the bulk start. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_status`

Read Proxmox node health and resource status (read-only). Returns node metrics including
total capacity, current usage, CPU, memory, disk state, and operational status. See pve_diagnose
for detailed per-node diagnostics including failed tasks.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name to query. Omit to use the configured default node. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_stopall`

MUTATION: stop ALL (or filtered) running guests on a PVE node.

RISK_HIGH — fleet-wide service outage unless vms filters the scope.
Reversible via pve_node_startall, but guests must be restarted inside. confirm=True to execute.

POST /nodes/{node}/stopall
Smoke-confirm: endpoint and vms param format not live-verified. May return task UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name whose guests to stop; defaults to the configured node if omitted. (default: `null`) |
| `vms` | string (nullable) | no | Optional comma-separated list of VMIDs/CTIDs to limit the scope; omit to stop ALL guests on the node. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the bulk stop. (default: `false`) |
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
| `backend` | string | yes | Storage backend type to create: one of lvm, lvmthin, zfs, directory. |
| `name` | string | yes | Name to assign to the new storage backend. |
| `devices` | string (nullable) | no | Disk device(s) consumed by the new backend: comma-separated list for zfs, a single disk path for lvm/lvmthin/directory. (default: `null`) |
| `node` | string (nullable) | no | PVE node name to create the backend on; defaults to the configured node if omitted. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the creation. (default: `false`) |
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
| `backend` | string | yes | Storage backend type to destroy: one of lvm, lvmthin, zfs, directory. |
| `name` | string | yes | Name of the storage backend to destroy. |
| `node` | string (nullable) | no | PVE node name the backend lives on; defaults to the configured node if omitted. (default: `null`) |
| `cleanup` | boolean | no | If True, also removes the underlying disk data/partitions during backend removal. (default: `false`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the irreversible destroy. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_storage_backend_list`

List storage backends of a type on a PVE node (read).

backend ∈ {lvm, lvmthin, zfs, directory}.
GET /nodes/{node}/disks/{backend}
Smoke-confirm: response shape not live-verified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `backend` | string | yes | Storage backend type to list: one of lvm, lvmthin, zfs, directory. |
| `node` | string (nullable) | no | PVE node name to query; defaults to the configured node if omitted. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_subscription`

Read a Proxmox node's subscription status (read-only). Returns a dict with
status, product name, check time, next due date, and subscription level.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name; defaults to the configured node (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_syslog`

Fetch syslog entries from a PVE node (read). limit capped at 5000.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name; defaults to the configured node (default: `null`) |
| `limit` | integer | no | Maximum number of syslog entries to return, capped at 5000 (default: `100`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_time_get`

Get the current time and timezone of a PVE node (read).

GET /nodes/{node}/time — returns {localtime, time, timezone}.
Smoke-confirm: response shape not live-verified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name to query; defaults to the configured node if omitted. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_time_set`

MUTATION: set the timezone on a PVE node.

RISK_LOW. CAPTURE: reads the current timezone before planning; if unreadable → complete=False.
Revert by re-applying the captured timezone. confirm=True to execute.

PUT /nodes/{node}/time
Smoke-confirm: endpoint and body shape not live-verified.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `timezone` | string | yes | IANA timezone name to set on the node (e.g. America/Chicago, UTC). |
| `node` | string (nullable) | no | PVE node name to configure; defaults to the configured node if omitted. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the timezone change. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_notification_endpoint_create`

MUTATION: create a PVE notification endpoint. ep_type = gotify|smtp|sendmail|webhook.
Dry-run by default. confirm=True to execute. `options` carries the endpoint-specific config
(sendmail: {"mailto-user":"root@pam"}; gotify: {"server":..,"token":..}; webhook: {"url":..}).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ep_type` | string | yes | Notification endpoint type: 'gotify', 'smtp', 'sendmail', or 'webhook' |
| `name` | string | yes | Unique name for the new notification endpoint |
| `comment` | string (nullable) | no | Optional free-text comment stored with the endpoint (default: `null`) |
| `options` | object (nullable) | no | Endpoint-specific config fields, e.g. sendmail: {'mailto-user':'root@pam'}; gotify: {'server':.., 'token':..}; webhook: {'url':..} (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the creation (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_notification_endpoint_delete`

MUTATION: delete a PVE notification endpoint. ep_type = gotify|smtp|sendmail|webhook.
Dry-run by default — captures current config. confirm=True to execute.
WARN: matchers referencing this endpoint will silently fail until it is restored.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ep_type` | string | yes | Notification endpoint type: 'gotify', 'smtp', 'sendmail', or 'webhook' |
| `name` | string | yes | Name of the notification endpoint to delete |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion (default: `false`) |
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
| `ep_type` | string | yes | Notification endpoint type: 'gotify', 'smtp', 'sendmail', or 'webhook' |
| `name` | string | yes | Name of the existing notification endpoint to update |
| `comment` | string (nullable) | no | Optional free-text comment to set on the endpoint (default: `null`) |
| `options` | object (nullable) | no | Endpoint-specific fields to change, same shape as create (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the update (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_notification_matcher_delete`

MUTATION: delete a PVE notification matcher. Dry-run by default.
confirm=True to execute. WARN: alerts matching this filter go un-routed after deletion.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the notification matcher to delete |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_notification_matcher_set`

MUTATION: create-or-update a PVE notification matcher (alert routing rule).
Dry-run by default. confirm=True to execute.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the notification matcher (alert routing rule) to create or update |
| `comment` | string (nullable) | no | Optional free-text comment stored with the matcher (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the create/update (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_notification_test`

MUTATION: send a test notification to a PVE notification target. Dry-run by default.
confirm=True to execute. SENDS A REAL NOTIFICATION — recipients will receive it.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the notification target to send a test notification to |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True sends a real test notification (default: `false`) |
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
| `poolid` | string | yes | New pool ID to create. |
| `comment` | string (nullable) | no | Free-text comment stored with the pool. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the creation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_pool_delete`

MUTATION: delete a resource pool. Dry-run by default — the PLAN warns ACLs on /pool/{poolid}
are orphaned and the pool must be empty first (members are NOT deleted). confirm=True to
execute. Synchronous.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `poolid` | string | yes | Pool ID to delete; the pool must be empty first. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_pool_get`

Retrieve a single resource pool's configuration and complete member list by pool ID
(read-only). Returns the pool's config including all VMs and storage resources assigned.
Use pve_pools_list to enumerate all pools.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `poolid` | string | yes | Pool ID to look up. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_pool_update`

MUTATION: add (delete=False) or remove (delete=True) pool members. Dry-run by default —
the PLAN notes membership re-scopes ACL coverage. confirm=True to execute. Synchronous.
delete=True with no vms/storage is refused (ambiguous).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `poolid` | string | yes | Pool ID to update. |
| `vms` | string (nullable) | no | Comma-separated VMID/CTID list to add or remove from the pool. (default: `null`) |
| `storage` | string (nullable) | no | Comma-separated storage ID list to add or remove from the pool. (default: `null`) |
| `delete` | boolean | no | False (default) adds the given vms/storage as members; True removes them instead. (default: `false`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the change. (default: `false`) |
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
| `realm` | string | yes | New realm id/name. |
| `realm_type` | string | yes | Realm type: 'pam', 'pve', 'ldap', 'ad', or 'openid'. |
| `comment` | string (nullable) | no | Optional free-text comment. (default: `null`) |
| `options` | object (nullable) | no | Type-specific config fields passed verbatim to PVE (e.g. ldap: server1/base_dn/user_attr; ad: domain/server1; openid: issuer-url/client-id). (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_realm_delete`

MUTATION (HIGH, lockout-class): delete an auth realm. Dry-run by default — the PLAN reads
users to count who can no longer log in, and refuses built-in pam/pve. confirm=True.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes | Realm id to delete (built-in 'pam'/'pve' are refused). |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_realm_get`

Get a realm's full config (read-only). Returns realm type, comment, TFA requirement, and
type-specific settings (server/base_dn for ldap; domain/server1 for ad; issuer-url/client-id
for openid). Use pve_realm_create/update/delete to manage realms.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes | Realm id to look up, e.g. 'pam', 'pve', or a configured ldap/ad/openid realm name. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_realm_update`

MUTATION: update a realm. Dry-run by default — built-in pam/pve realms are flagged HIGH
(changing them risks breaking logins). confirm=True. `options` carries type-specific fields
(server1/base_dn/etc.) passed verbatim; PVE validates them.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes | Realm id to update. |
| `comment` | string (nullable) | no | New free-text comment; omit to leave unchanged. (default: `null`) |
| `options` | object (nullable) | no | Type-specific config fields to update, passed verbatim to PVE (e.g. server1/base_dn/etc.). (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
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
| `rep_id` | string | yes | Unique ID for the new replication job. |
| `rep_type` | string | yes | Replication job type, typically 'local'. |
| `target` | string | yes | Target node (or node/storage) to replicate to. |
| `schedule` | string (nullable) | no | Proxmox calendar-event schedule string; omit for the default cadence. (default: `null`) |
| `rate` | number (nullable) | no | Bandwidth limit in MB/s; omit for unlimited. (default: `null`) |
| `disable` | boolean (nullable) | no | If true, create the job in a disabled state. (default: `null`) |
| `comment` | string (nullable) | no | Free-text note stored on the job. (default: `null`) |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the creation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_replication_delete`

MUTATION: delete a PVE replication job. Dry-run by default — captures current config.
confirm=True to execute. Replication ceases; existing replicated data is NOT removed.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `rep_id` | string | yes | ID of the replication job to delete. |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_replication_update`

MUTATION: update a PVE replication job. Dry-run by default — captures current config.
confirm=True to execute. Config-only; in-flight replication is not immediately disrupted.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `rep_id` | string | yes | ID of the existing replication job to update. |
| `schedule` | string (nullable) | no | New Proxmox calendar-event schedule string; omit to leave unchanged. (default: `null`) |
| `rate` | number (nullable) | no | New bandwidth limit in MB/s; omit to leave unchanged. (default: `null`) |
| `disable` | boolean (nullable) | no | Whether the job is disabled; omit to leave unchanged. (default: `null`) |
| `comment` | string (nullable) | no | New free-text note; omit to leave unchanged. (default: `null`) |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the update. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_restore`

MUTATION (DESTRUCTIVE if it overwrites an existing guest): restore a guest from a backup
archive. Dry-run by default — the PLAN states whether it CREATES or OVERWRITES. confirm=True to
execute. Async — returns a task UPID. pool: place the restored guest in a resource pool.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric ID for the restored guest — new if free, existing to overwrite. |
| `archive` | string | yes | Volume ID of the backup archive to restore from. |
| `storage` | string | yes | Storage ID to restore the guest's disks onto (LXC only; ignored for QEMU). |
| `kind` | string | no | Guest type: lxc or qemu. (default: `"lxc"`) |
| `node` | string (nullable) | no | Proxmox node to restore onto; defaults to the configured node if omitted. (default: `null`) |
| `force` | boolean | no | If vmid already exists, overwrite/destroy the existing guest instead of failing. (default: `false`) |
| `pool` | string (nullable) | no | Resource pool to place the restored guest in. (default: `null`) |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the restore. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_role_create`

MUTATION: create a custom role with an optional privilege set. Dry-run by default (MEDIUM
risk — inert until an ACL entry references it). Returns the plan preview; confirm=True to
execute. privs format: comma-separated privilege names (e.g. 'VM.PowerMgmt,VM.Config.Disk').

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `roleid` | string | yes | New role id. |
| `privs` | string (nullable) | no | Comma-separated privilege names for the role, e.g. 'VM.PowerMgmt,VM.Config.Disk'. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_role_delete`

MUTATION (HIGH): delete a role. Dry-run by default — the PLAN reads ACLs to count grants
that will break, and refuses built-in roles. confirm=True.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `roleid` | string | yes | Role id to delete (built-in roles are refused). |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_role_update`

MUTATION: change a role's privileges. Dry-run by default — built-in roles (Administrator,
PVEAdmin, …) are flagged HIGH (changing them re-scopes every ACL using them). confirm=True.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `roleid` | string | yes | Role id to update. |
| `privs` | string (nullable) | no | Comma-separated privilege names to set (or add, if append=True). (default: `null`) |
| `append` | boolean (nullable) | no | If True, add `privs` to the role's existing privileges instead of replacing them. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
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
| `vmid` | string | yes | Numeric ID of the guest — VMID for a QEMU VM or CTID for an LXC container. |
| `snapname` | string | yes | Name of the snapshot to roll the guest back to. |
| `kind` | string | no | Guest type: `lxc` for a container or `qemu` for a VM. (default: `"lxc"`) |
| `node` | string (nullable) | no | PVE node the guest runs on. Omit to resolve it automatically from the cluster. (default: `null`) |
| `confirm` | boolean | no | Leave `false` (default) to get a dry-run PLAN with blast radius; set `true` to execute the rollback. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_apply`

MUTATION (HIGH RISK): apply pending SDN config changes (cluster-scoped).
Dry-run by default — the PLAN surfaces pending zones/vnets. confirm=True to execute.
A misconfigured SDN can disrupt virtual networking for ALL guests cluster-wide.
May return a UPID (async) or None (sync) — outcome='submitted' in either case.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True applies pending SDN config cluster-wide. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_subnet_create`

MUTATION: create an SDN subnet (PENDING). `subnet` is a CIDR (e.g. 10.0.0.0/24); `options`
carries gateway/snat/dhcp params. Dry-run by default. RISK_LOW (staging; inert until apply).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vnet` | string | yes | SDN vnet name the subnet belongs to. |
| `subnet` | string | yes | Subnet CIDR to create, e.g. 10.0.0.0/24. |
| `options` | object (nullable) | no | Subnet options such as gateway, snat, and dhcp. (default: `null`) |
| `lock_token` | string (nullable) | no | SDN cluster lock token to use for this write, if one is held. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the staged mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_subnet_delete`

MUTATION: delete an SDN subnet (PENDING). `subnet` is the id from pve_sdn_subnet_list.
Dry-run by default. RISK_MEDIUM (staging a removal an apply would enact).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vnet` | string | yes | SDN vnet name the subnet belongs to. |
| `subnet` | string | yes | Subnet id (CIDR) from pve_sdn_subnet_list to delete. |
| `lock_token` | string (nullable) | no | SDN cluster lock token to use for this write, if one is held. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the staged mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_subnet_list`

List subnets in a vnet (read-only). Returns subnet CIDR, gateway, dhcp,
snat, and dns settings. Use pve_sdn_subnet_create to add and pve_sdn_apply to
commit.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vnet` | string | yes | SDN vnet name whose subnets to list. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_subnet_update`

MUTATION: update an SDN subnet (PENDING). `subnet` is the id from pve_sdn_subnet_list.
Dry-run by default. RISK_LOW (staging).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vnet` | string | yes | SDN vnet name the subnet belongs to. |
| `subnet` | string | yes | Subnet id (CIDR) from pve_sdn_subnet_list to update. |
| `options` | object (nullable) | no | Subnet fields to set (gateway, snat, dhcp, etc). (default: `null`) |
| `delete` | array<string> (nullable) | no | Subnet option keys to unset. (default: `null`) |
| `digest` | string (nullable) | no | Expected config digest for optimistic-concurrency checking. (default: `null`) |
| `lock_token` | string (nullable) | no | SDN cluster lock token to use for this write, if one is held. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the staged mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_vnet_create`

MUTATION: create an SDN vnet in a zone (PENDING). `options` carries tag/alias/vlanaware/etc.
Dry-run by default. RISK_LOW (staging; inert until pve_sdn_apply).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vnet` | string | yes | New SDN vnet name to create. |
| `zone` | string | yes | SDN zone id the vnet belongs to. |
| `options` | object (nullable) | no | Vnet options such as tag, alias, and vlanaware. (default: `null`) |
| `lock_token` | string (nullable) | no | SDN cluster lock token to use for this write, if one is held. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the staged mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_vnet_delete`

MUTATION: delete an SDN vnet (PENDING). Dry-run by default — the PLAN shows the current vnet.
PVE refuses if a subnet still references it. RISK_MEDIUM.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vnet` | string | yes | Existing SDN vnet name to delete. |
| `lock_token` | string (nullable) | no | SDN cluster lock token to use for this write, if one is held. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the staged mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_vnet_update`

MUTATION: update an SDN vnet (PENDING — inert until pve_sdn_apply).
Options sets fields (tag/alias/vlanaware/etc), delete removes keys. Dry-run
by default. RISK_LOW (staging, no live network effect).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vnet` | string | yes | Existing SDN vnet name to update. |
| `options` | object (nullable) | no | Vnet fields to set (tag, alias, vlanaware, etc). (default: `null`) |
| `delete` | array<string> (nullable) | no | Vnet option keys to unset. (default: `null`) |
| `digest` | string (nullable) | no | Expected config digest for optimistic-concurrency checking. (default: `null`) |
| `lock_token` | string (nullable) | no | SDN cluster lock token to use for this write, if one is held. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the staged mutation. (default: `false`) |
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
| `zone` | string | yes | New SDN zone id to create. |
| `zone_type` | string | yes | Zone type: simple, vlan, qinq, vxlan, evpn, or faucet. |
| `options` | object (nullable) | no | Type-specific zone options (e.g. bridge, mtu, controller). (default: `null`) |
| `lock_token` | string (nullable) | no | SDN cluster lock token to use for this write, if one is held. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the staged mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_zone_delete`

MUTATION: delete an SDN zone (PENDING). Dry-run by default — the PLAN shows the current zone.
PVE refuses if a vnet still references it. RISK_MEDIUM (staging a removal an apply would enact).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `zone` | string | yes | Existing SDN zone id to delete. |
| `lock_token` | string (nullable) | no | SDN cluster lock token to use for this write, if one is held. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the staged mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_zone_update`

MUTATION: update an SDN zone (PENDING). `options` sets fields; `delete` unsets keys.
Dry-run by default. RISK_LOW (staging; inert until pve_sdn_apply).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `zone` | string | yes | Existing SDN zone id to update. |
| `options` | object (nullable) | no | Zone fields to set (type-specific, e.g. bridge, mtu, controller). (default: `null`) |
| `delete` | array<string> (nullable) | no | Zone option keys to unset. (default: `null`) |
| `digest` | string (nullable) | no | Expected config digest for optimistic-concurrency checking. (default: `null`) |
| `lock_token` | string (nullable) | no | SDN cluster lock token to use for this write, if one is held. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the staged mutation. (default: `false`) |
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
| `vmid` | string | yes | Numeric ID of the guest — VMID for a QEMU VM or CTID for an LXC container. |
| `snapname` | string | yes | Name for the new snapshot. |
| `kind` | string | no | Guest type: `lxc` for a container or `qemu` for a VM. (default: `"lxc"`) |
| `node` | string (nullable) | no | PVE node the guest runs on. Omit to resolve it automatically from the cluster. (default: `null`) |
| `description` | string (nullable) | no | Optional free-text description stored on the snapshot. (default: `null`) |
| `confirm` | boolean | no | Leave `false` (default) to get a dry-run PLAN; set `true` to execute the snapshot creation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_snapshot_delete`

MUTATION: delete a snapshot (removes a restore point). Dry-run by default; confirm=True to execute.
Async -> UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric ID of the guest — VMID for a QEMU VM or CTID for an LXC container. |
| `snapname` | string | yes | Name of the snapshot to delete. |
| `kind` | string | no | Guest type: `lxc` for a container or `qemu` for a VM. (default: `"lxc"`) |
| `node` | string (nullable) | no | PVE node the guest runs on. Omit to resolve it automatically from the cluster. (default: `null`) |
| `force` | boolean | no | Force removal even if the snapshot has children or the backend reports an inconsistent state. (default: `false`) |
| `confirm` | boolean | no | Leave `false` (default) to get a dry-run PLAN; set `true` to execute the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_snapshot_list`

List a guest's snapshots (read-only). Returns each snapshot's name, description, parent,
and creation time, plus the synthetic 'current' node showing live state. Works for both VMs
and containers (kind='qemu' or 'lxc'). Use pve_snapshot_create / pve_rollback to act on them.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric ID of the guest — VMID for a QEMU VM or CTID for an LXC container. |
| `kind` | string | no | Guest type: `lxc` for a container or `qemu` for a VM. (default: `"lxc"`) |
| `node` | string (nullable) | no | PVE node the guest runs on. Omit to resolve it automatically from the cluster. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_storage_config_get`

Retrieve a single storage definition from storage.cfg by storage ID (read-only).
Returns the storage's complete configuration including type, paths, servers, and access
settings. Use pve_storage_config_list to enumerate all storages.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes | Storage ID to look up. |
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
| `storage` | string | yes | Storage backend name to list content from. |
| `node` | string (nullable) | no | PVE node hosting the storage. Omit to use the configured default node. (default: `null`) |
| `content` | string (nullable) | no | Filter by content type: `iso`, `vztmpl`, or `backup`. Omit to list all content. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_storage_content_delete`

MUTATION: delete a content volume (ISO / template / backup) from storage. Dry-run by default
(HIGH risk for a backup volume); confirm=True. Async — UPID or null.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes | Storage backend name the content volume lives on. |
| `volid` | string | yes | Volume ID of the content to delete (ISO, template, or backup), e.g. `local:vztmpl/debian-12.tar.zst`. |
| `node` | string (nullable) | no | PVE node hosting the storage. Omit to use the configured default node. (default: `null`) |
| `confirm` | boolean | no | Leave `false` (default) to get a dry-run PLAN — HIGH risk for a backup volume; set `true` to execute the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_storage_create`

MUTATION: define a new storage (storage.cfg). Dry-run by default. confirm=True to execute.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes | New storage ID (name used across the cluster). |
| `storage_type` | string | yes | PVE storage driver type, e.g. 'dir', 'nfs', 'pbs'. |
| `content` | string (nullable) | no | Comma-separated content types to allow, e.g. 'iso,backup,images'. (default: `null`) |
| `path` | string (nullable) | no | Filesystem path (required for storage_type='dir'). (default: `null`) |
| `server` | string (nullable) | no | Remote host address (required for nfs/cifs/pbs). (default: `null`) |
| `export` | string (nullable) | no | NFS export path (required for storage_type='nfs'). (default: `null`) |
| `nodes` | string (nullable) | no | Comma-separated node list this storage is available on; omit for all nodes. (default: `null`) |
| `disable` | boolean | no | If True, storage is created in a disabled state. (default: `false`) |
| `shared` | boolean | no | If True, marks storage as shared across all nodes. (default: `false`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the creation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_storage_delete`

MUTATION (HIGH): remove a storage definition cluster-wide. Dry-run by default — the PLAN
warns guest disks/backups living only there become inaccessible (data not erased). confirm=True.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes | Storage ID to remove cluster-wide (definition only; data on disk is not erased). |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_storage_download`

MUTATION: download an ISO (content=iso) or CT template (content=vztmpl) from a URL into a
storage. Dry-run by default; confirm=True. Async — returns a UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes | Storage backend name to download the file into. |
| `content` | string | yes | Content type of the downloaded file: `iso` or `vztmpl`. |
| `url` | string | yes | Source URL to download the ISO or CT template from. |
| `filename` | string | yes | Filename to save the downloaded content as on the storage. |
| `node` | string (nullable) | no | PVE node hosting the storage. Omit to use the configured default node. (default: `null`) |
| `checksum` | string (nullable) | no | Expected checksum of the downloaded file, used to verify integrity. (default: `null`) |
| `checksum_algorithm` | string (nullable) | no | Algorithm the checksum was computed with (e.g. `sha256`). Required if checksum is given. (default: `null`) |
| `confirm` | boolean | no | Leave `false` (default) to get a dry-run PLAN; set `true` to execute the download. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_storage_status`

Read a storage backend's capacity and state (read-only). Returns total size, used space,
available free space, and enabled status. Use pve_storage_content to list ISOs, templates,
and backups stored on it.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes | Storage backend name to read capacity and state for. |
| `node` | string (nullable) | no | PVE node hosting the storage. Omit to use the configured default node. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_storage_update`

MUTATION: update a storage definition. Dry-run by default (disable=True warns guests lose
disk access). confirm=True to execute.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes | Storage ID to update. |
| `content` | string (nullable) | no | New comma-separated content type list, e.g. 'iso,backup,images'. (default: `null`) |
| `nodes` | string (nullable) | no | New comma-separated node restriction list. (default: `null`) |
| `disable` | boolean (nullable) | no | True to disable, False to enable, omit to leave unchanged. (default: `null`) |
| `shared` | boolean (nullable) | no | True/False to set sharedness; omit to leave unchanged (must stay None for network-backed types like nfs/cifs/pbs, which reject an explicit shared flag). (default: `null`) |
| `delete` | string (nullable) | no | Comma-separated list of config fields to unset on the storage definition. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the change. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_task_log`

Retrieve a task's log output by UPID (read-only). Returns the task's log lines with
line numbers, paginated via start/limit. Use pve_task_wait for completion polling, or
pve_tasks_list to find a UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `upid` | string | yes | The task's Unique Process ID (UPID) string returned by an async operation. |
| `node` | string (nullable) | no | Node the task ran on; defaults to the configured node. (default: `null`) |
| `start` | integer | no | Line offset to start returning log output from (for pagination). (default: `0`) |
| `limit` | integer | no | Max number of log lines to return. (default: `50`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_task_status`

Status of an async Proxmox task (running/stopped + exit status) — poll snapshot/rollback ops (read).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `upid` | string | yes | Proxmox task UPID (unique process ID) returned by an async operation. |
| `node` | string (nullable) | no | PVE node the task is running on. Omit to resolve it automatically. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_task_stop`

MUTATION (HIGH): stop (cancel) a running task. Dry-run by default — the PLAN warns that
stopping a backup/restore/migration/clone mid-flight can leave the target inconsistent, with
NO undo. confirm=True to execute. Synchronous cancellation signal (returns null).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `upid` | string | yes | The task's Unique Process ID (UPID) string to cancel. |
| `node` | string (nullable) | no | Node the task is running on; defaults to the configured node. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the cancellation. (default: `false`) |
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
| `upid` | string | yes | The task's Unique Process ID (UPID) string to poll for completion. |
| `node` | string (nullable) | no | Node the task ran on; defaults to the configured node. (default: `null`) |
| `timeout` | integer | no | Max seconds to wait for the task to reach a terminal state, clamped to 1-600. (default: `120`) |
| `interval` | integer | no | Seconds between status polls, clamped to 1-60. (default: `2`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_tasks_list`

List recent tasks on a node (read). limit 1-1000 (clamped).

Caveat: this is a windowed, per-node slice — node defaults to the configured node, and
only the `limit` most-recent tasks return. A task on another node or outside the window
is absent without being dead. Never conclude a backup failed from absence here — verify
against pve_backup_list or pbs_snapshots_list.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | Node to list tasks from; defaults to the configured node. (default: `null`) |
| `limit` | integer | no | Max number of most-recent tasks to return, clamped to 1-1000. (default: `50`) |
| `errors` | boolean | no | If True, only return tasks that ended in error. (default: `false`) |
| `vmid` | string (nullable) | no | Optional VMID/CTID to filter tasks to a single guest. (default: `null`) |
| `typefilter` | string (nullable) | no | Optional task-type filter, e.g. 'vzdump', 'qmigrate' (PVE task type string). (default: `null`) |
| `statusfilter` | string (nullable) | no | Optional status filter, e.g. 'running', 'stopped'. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_template_convert`

MUTATION (IRREVERSIBLE): convert a guest into a template — effectively one-way. Dry-run by
default (the PLAN flags it HIGH/irreversible); confirm=True to execute.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric ID of the guest to convert into a template. |
| `node` | string (nullable) | no | PVE node the guest runs on. Omit to resolve it automatically from the cluster. (default: `null`) |
| `kind` | string | no | Guest type: `lxc` for a container or `qemu` for a VM. (default: `"qemu"`) |
| `confirm` | boolean | no | Leave `false` (default) to get a dry-run PLAN flagging this as HIGH/irreversible; set `true` to execute. (default: `false`) |
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
| `userid` | string | yes | User id whose TFA factor to delete, format 'user@realm'. |
| `tfa_id` | string | yes | Id of the TFA factor to delete. |
| `password` | string (nullable) | no | The user's current password, if PVE requires re-authentication for this mutation; never logged. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_tfa_get`

Read a user's TFA entries (read-only). Returns list of entries if tfa_id is omitted; a
single entry dict if tfa_id is specified. Each entry includes factor type, id, and metadata.
Use pve_tfa_delete (confirm=True) to remove a factor (RISK_HIGH — can lock the user out).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | User id whose TFA entries to read, format 'user@realm'. |
| `tfa_id` | string (nullable) | no | Specific TFA entry id to return; omit to return all of the user's entries. (default: `null`) |
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
| `userid` | string | yes | Owning user, format 'user@realm'. |
| `tokenid` | string | yes | Name for the new API token, unique per user. |
| `privsep` | boolean | no | Privilege separation: True (default) restricts the token to its own ACL grants; False lets it inherit ALL owner permissions. (default: `true`) |
| `comment` | string (nullable) | no | Optional free-text comment describing the token's purpose. (default: `null`) |
| `expire` | integer (nullable) | no | Optional token expiry as a Unix timestamp; None means no expiry. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_token_revoke`

MUTATION (IRREVERSIBLE): permanently revoke an API token.

Dry-run by default — the PLAN flags HIGH: revocation is permanent, the secret is gone forever.
confirm=True to execute. Synchronous.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | Owning user, format 'user@realm'. |
| `tokenid` | string | yes | Name of the API token to revoke. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_tokens_list`

List API tokens for a specific user (read-only). Returns each token's id, comment, expiry,
and privsep (privilege separation) flag — NOT the secret (shown only at creation). userid
format: 'user@realm'. Use pve_token_create/revoke to manage tokens.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | Owning user, format 'user@realm'. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_user_create`

MUTATION: create a user. Dry-run by default (note: password is set separately — the user
cannot log in until then). confirm=True to execute.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | New user id, format 'user@realm'. |
| `comment` | string (nullable) | no | Optional free-text comment. (default: `null`) |
| `email` | string (nullable) | no | Optional email address. (default: `null`) |
| `enable` | boolean (nullable) | no | Whether the account can log in; None defers to PVE's default (enabled). (default: `null`) |
| `expire` | integer (nullable) | no | Optional account expiry as a Unix timestamp; None means no expiry. (default: `null`) |
| `groups` | string (nullable) | no | Comma-separated list of group ids to add the user to. (default: `null`) |
| `firstname` | string (nullable) | no | Optional first name. (default: `null`) |
| `lastname` | string (nullable) | no | Optional last name. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_user_delete`

MUTATION (HIGH): delete a user. Dry-run by default — the PLAN reads the user's ACLs/tokens
to show what access vanishes (permanent, no undo; admin = lockout risk). confirm=True.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | User id to delete, format 'user@realm'. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_user_get`

Get a user's full config (read-only). Returns userid, enabled flag, expiry, email, comment,
group membership, API tokens, and firstname/lastname. Use pve_user_create/update/delete to
modify the user; use pve_acl_list to see their effective permissions.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | User id to look up, format 'user@realm'. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_user_update`

MUTATION: update a user (enable=False stops login; group changes re-scope access).
Dry-run by default. confirm=True to execute.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | User id to update, format 'user@realm'. |
| `comment` | string (nullable) | no | Optional free-text comment; omit to leave unchanged. (default: `null`) |
| `email` | string (nullable) | no | Optional email address; omit to leave unchanged. (default: `null`) |
| `enable` | boolean (nullable) | no | Whether the account can log in; False stops login. Omit to leave unchanged. (default: `null`) |
| `expire` | integer (nullable) | no | Account expiry as a Unix timestamp; omit to leave unchanged. (default: `null`) |
| `groups` | string (nullable) | no | Comma-separated list of group ids; replaces membership unless append=True. (default: `null`) |
| `firstname` | string (nullable) | no | Optional first name; omit to leave unchanged. (default: `null`) |
| `lastname` | string (nullable) | no | Optional last name; omit to leave unchanged. (default: `null`) |
| `append` | boolean (nullable) | no | If True, add `groups` to existing membership instead of replacing it. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
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
| `name` | string | yes | Name for the new PBS datastore. |
| `path` | string | yes | Filesystem path on the PBS node where the datastore will be created. |
| `gc_schedule` | string (nullable) | no | Garbage-collection schedule as a PBS calendar-event string (e.g. 'daily'). (default: `null`) |
| `prune_schedule` | string (nullable) | no | Prune-job schedule as a PBS calendar-event string (e.g. 'daily'). (default: `null`) |
| `notification_mode` | string (nullable) | no | Notification delivery mode for this datastore (PBS notification-mode value). (default: `null`) |
| `comment` | string (nullable) | no | Free-text comment/description for the datastore. (default: `null`) |
| `confirm` | boolean | no | Set True to execute; False (default) only returns the dry-run plan. (default: `false`) |
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
| `name` | string | yes | PBS datastore name to delete. |
| `destroy_data` | boolean | no | If True, destroys all backup data (HIGH, no undo); default only detaches config. (default: `false`) |
| `keep_job_configs` | boolean | no | If True, keep job configs referencing this datastore instead of removing them. (default: `false`) |
| `confirm` | boolean | no | Set True to execute; False (default) only returns the dry-run plan. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_datastore_get`

Get full config of one PBS datastore by name (read). Returns path, gc-schedule, etc.
For runtime usage stats use pbs_datastore_status instead. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | PBS datastore name. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_datastore_status`

Get runtime usage statistics for one PBS datastore (read-only). Returns total
capacity, used bytes, and available bytes. Use pbs_datastores_list to enumerate
datastores (with backend type) or pbs_gc_status for garbage-collection state.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes | PBS datastore name. |
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
| `name` | string | yes | PBS datastore name to update. |
| `gc_schedule` | string (nullable) | no | Garbage-collection schedule as a PBS calendar-event string (e.g. 'daily'). (default: `null`) |
| `prune_schedule` | string (nullable) | no | Prune-job schedule as a PBS calendar-event string (e.g. 'daily'). (default: `null`) |
| `notification_mode` | string (nullable) | no | Notification delivery mode for this datastore (PBS notification-mode value). (default: `null`) |
| `comment` | string (nullable) | no | Free-text comment/description for the datastore. (default: `null`) |
| `confirm` | boolean | no | Set True to execute; False (default) only returns the dry-run plan. (default: `false`) |
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
| `store` | string | yes | PBS datastore name to run garbage collection on. |
| `confirm` | boolean | no | Set True to execute; False (default) only returns the dry-run plan. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_gc_status`

Get garbage-collection status for one PBS datastore (read-only). Returns GC
schedule, current state, disk/index statistics, and pending/removed chunk counts.
Use pbs_gc_start to execute garbage collection or pbs_datastore_status for capacity.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes | PBS datastore name. |
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
| `store` | string | yes | PBS datastore name. |
| `backup_type` | string | yes | Backup type of the group: 'vm', 'ct', or 'host'. |
| `backup_id` | string | yes | Backup group ID (e.g. VMID/CTID or host name). |
| `new_owner` | string | yes | PBS auth ID (user@realm or api-token) to become the new owner of the backup group. |
| `ns` | string (nullable) | no | Namespace path the backup group lives in; omit for the root namespace. (default: `null`) |
| `confirm` | boolean | no | Set True to execute; False (default) only returns the dry-run plan. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_job_create`

MUTATION: create a PBS scheduled job. job_type = sync|verify|prune. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PBS_* config. Config-only; no existing data affected.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `job_type` | string | yes | PBS job type: sync \| verify \| prune. |
| `job_id` | string | yes | Unique ID for the new PBS scheduled job. |
| `store` | string (nullable) | no | PBS datastore the job operates on. (default: `null`) |
| `schedule` | string (nullable) | no | Proxmox calendar-event schedule string for the job. (default: `null`) |
| `ns` | string (nullable) | no | PBS namespace the job operates on; omit for the root namespace. (default: `null`) |
| `comment` | string (nullable) | no | Free-text note stored on the job. (default: `null`) |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the creation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_job_delete`

MUTATION: delete a PBS scheduled job. job_type = sync|verify|prune. Dry-run by default —
captures current config. confirm=True to execute. Schedule removed; backup data NOT deleted.
Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `job_type` | string | yes | PBS job type: sync \| verify \| prune. |
| `job_id` | string | yes | ID of the PBS scheduled job to delete. |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_job_run`

MUTATION: trigger a PBS scheduled job immediately. job_type = sync|verify|prune.
Dry-run by default. confirm=True to execute. Async — returns UPID.
Needs PROXIMO_PBS_* config. Prune runs may delete snapshots per the retention policy.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `job_type` | string | yes | PBS job type: sync \| verify \| prune. |
| `job_id` | string | yes | ID of the PBS scheduled job to trigger immediately. |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the run. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_job_update`

MUTATION: update a PBS scheduled job. job_type = sync|verify|prune. Dry-run by default —
captures current config. confirm=True to execute. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `job_type` | string | yes | PBS job type: sync \| verify \| prune. |
| `job_id` | string | yes | ID of the existing PBS scheduled job to update. |
| `schedule` | string (nullable) | no | New Proxmox calendar-event schedule string; omit to leave unchanged. (default: `null`) |
| `ns` | string (nullable) | no | New PBS namespace the job operates on; omit to leave unchanged. (default: `null`) |
| `comment` | string (nullable) | no | New free-text note; omit to leave unchanged. (default: `null`) |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the update. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_jobs_list`

List all PBS scheduled jobs of the given type (read). job_type = sync|verify|prune.
Returns all jobs with their configs. Raises on invalid job_type. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `job_type` | string | yes | Scheduled-job type to list: 'sync', 'verify', or 'prune'. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_namespace_create`

MUTATION: create a namespace within a PBS datastore. Dry-run by default (additive, LOW).
confirm=True to execute. Synchronous.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes | PBS datastore name. |
| `name` | string | yes | Namespace name/segment to create. |
| `parent` | string (nullable) | no | Parent namespace path to create under; omit for the root namespace. (default: `null`) |
| `confirm` | boolean | no | Set True to execute; False (default) only returns the dry-run plan. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_namespace_delete`

MUTATION: delete a namespace from a PBS datastore. Dry-run by default — delete_groups=True
is HIGH (it deletes all backup groups/snapshots inside the namespace, no undo). confirm=True
to execute. Synchronous.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes | PBS datastore name. |
| `ns` | string | yes | Namespace path to delete. |
| `delete_groups` | boolean | no | If True, deletes groups/snapshots in namespace (HIGH, no undo); else must be empty. (default: `false`) |
| `confirm` | boolean | no | Set True to execute; False (default) only returns the dry-run plan. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_namespaces_list`

List namespaces within a PBS datastore with optional hierarchical filtering (read-only).
Returns each namespace's hierarchical path (the `ns` field); optionally filter by
parent namespace or limit recursion depth. Use pbs_namespace_create to add namespaces.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes | PBS datastore name. |
| `parent` | string (nullable) | no | Parent namespace path to list children of; omit for the root namespace. (default: `null`) |
| `max_depth` | integer (nullable) | no | Maximum recursion depth below the parent namespace. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_prune`

MUTATION: prune backup snapshots per a retention policy. TWO safety gates: confirm
(Proximo dry-run vs execute) AND dry_run (PBS-side preview). dry_run=True (default) only
previews; dry_run=False DELETES recovery points (PLAN is HIGH, no undo). confirm=True to
execute. Synchronous — returns prune decisions.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes | PBS datastore name to prune. |
| `keep_last` | integer (nullable) | no | Number of most-recent backups to always keep. (default: `null`) |
| `keep_daily` | integer (nullable) | no | Number of daily backups to keep. (default: `null`) |
| `keep_weekly` | integer (nullable) | no | Number of weekly backups to keep. (default: `null`) |
| `keep_monthly` | integer (nullable) | no | Number of monthly backups to keep. (default: `null`) |
| `keep_yearly` | integer (nullable) | no | Number of yearly backups to keep. (default: `null`) |
| `ns` | string (nullable) | no | Namespace path to scope pruning to; omit for the root namespace. (default: `null`) |
| `backup_type` | string (nullable) | no | Backup type filter: 'vm', 'ct', or 'host'. (default: `null`) |
| `backup_id` | string (nullable) | no | Backup group ID (e.g. VMID/CTID or host name) to scope pruning to. (default: `null`) |
| `dry_run` | boolean | no | PBS-side preview: True (default) previews only; False actually deletes snapshots. (default: `true`) |
| `confirm` | boolean | no | Proximo dry-run gate: True executes (subject to dry_run); default only plans. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_realm_sync`

MUTATION: sync PBS auth realm (LDAP/AD) users. Dry-run by default.
confirm=True to execute. Async — returns UPID. Needs PROXIMO_PBS_* config.
remove_vanished=True also removes PBS users no longer in the directory.
(2026-07-10 audit: the old 'scope' param was dropped — PBS /sync has no such field.)

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes | PBS LDAP/AD auth realm ID to sync users from. |
| `remove_vanished` | boolean (nullable) | no | If true, also delete PBS users no longer present in the directory. (default: `null`) |
| `dry_run` | boolean (nullable) | no | If true, ask PBS itself to preview the sync without applying it (separate from the tool's own confirm gate). (default: `null`) |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the sync. (default: `false`) |
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
| `name` | string | yes | Name for the new PBS remote sync-source. |
| `host` | string | yes | Hostname or IP address of the remote PBS server. |
| `auth_id` | string | yes | PBS auth ID (user@realm or api-token) used to authenticate to the remote. |
| `password` | string | yes | Password or API token secret for auth_id; redacted from all plans/logs/ledger. |
| `fingerprint` | string (nullable) | no | TLS cert fingerprint of the remote PBS server (public data, not redacted). (default: `null`) |
| `port` | integer (nullable) | no | TCP port of the remote PBS API; defaults to the standard PBS port if omitted. (default: `null`) |
| `comment` | string (nullable) | no | Free-text comment/description for the remote. (default: `null`) |
| `confirm` | boolean | no | Set True to execute; False (default) only returns the dry-run plan. (default: `false`) |
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
| `name` | string | yes | PBS remote sync-source name to delete. |
| `confirm` | boolean | no | Set True to execute; False (default) only returns the dry-run plan. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_remote_get`

Get the config of one PBS remote sync-source by name (read). No password returned.
Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | PBS remote sync-source name. |
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
| `name` | string | yes | PBS remote sync-source name to update. |
| `host` | string (nullable) | no | New hostname or IP address of the remote PBS server. (default: `null`) |
| `auth_id` | string (nullable) | no | New PBS auth ID (user@realm or api-token) used to authenticate to the remote. (default: `null`) |
| `password` | string (nullable) | no | New password or API token secret; redacted from plans/logs/ledger. (default: `null`) |
| `fingerprint` | string (nullable) | no | New TLS cert fingerprint of the remote PBS server (public data, not redacted). (default: `null`) |
| `port` | integer (nullable) | no | New TCP port of the remote PBS API. (default: `null`) |
| `comment` | string (nullable) | no | New free-text comment/description for the remote. (default: `null`) |
| `confirm` | boolean | no | Set True to execute; False (default) only returns the dry-run plan. (default: `false`) |
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
| `store` | string | yes | PBS datastore name. |
| `backup_type` | string | yes | Backup type of the snapshot: 'vm', 'ct', or 'host'. |
| `backup_id` | string | yes | Backup group ID (e.g. VMID/CTID or host name). |
| `backup_time` | integer | yes | Snapshot timestamp as a Unix epoch integer, identifying the exact backup run. |
| `ns` | string (nullable) | no | Namespace path the snapshot lives in; omit for the root namespace. (default: `null`) |
| `confirm` | boolean | no | Set True to execute; False (default) only returns the dry-run plan. (default: `false`) |
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
| `store` | string | yes | PBS datastore name. |
| `backup_type` | string | yes | Backup type of the snapshot: 'vm', 'ct', or 'host'. |
| `backup_id` | string | yes | Backup group ID (e.g. VMID/CTID or host name). |
| `backup_time` | integer | yes | Snapshot timestamp as a Unix epoch integer, identifying the exact backup run. |
| `notes` | string | yes | Free-text notes to attach to the snapshot, replacing any existing notes. |
| `ns` | string (nullable) | no | Namespace path the snapshot lives in; omit for the root namespace. (default: `null`) |
| `confirm` | boolean | no | Set True to execute; False (default) only returns the dry-run plan. (default: `false`) |
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
| `store` | string | yes | PBS datastore name. |
| `backup_type` | string | yes | Backup type of the snapshot: 'vm', 'ct', or 'host'. |
| `backup_id` | string | yes | Backup group ID (e.g. VMID/CTID or host name). |
| `backup_time` | integer | yes | Snapshot timestamp as a Unix epoch integer, identifying the exact backup run. |
| `protected` | boolean | yes | True shields the snapshot from pruning/GC (LOW); False allows auto-deletion (HIGH). |
| `ns` | string (nullable) | no | Namespace path the snapshot lives in; omit for the root namespace. (default: `null`) |
| `confirm` | boolean | no | Set True to execute; False (default) only returns the dry-run plan. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_snapshots_list`

List backup snapshots in a PBS datastore with optional filters (read-only). Returns
snapshot metadata including backup type, ID, timestamp, size, owner, and protection
status; filter by namespace, backup_type (vm/ct/host), or backup_id.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes | PBS datastore name. |
| `ns` | string (nullable) | no | Namespace path to filter by; omit for the root namespace. (default: `null`) |
| `backup_type` | string (nullable) | no | Backup type filter: 'vm', 'ct', or 'host'. (default: `null`) |
| `backup_id` | string (nullable) | no | Backup group ID (e.g. VMID/CTID or host name) to filter by. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_tasks_list`

List PBS tasks on a node (read). Defaults to 'localhost' (standard single-node PBS name).
Optionally filter: running=True for active tasks, errors=True for failed tasks.
Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name; defaults to 'localhost' (standard single-node PBS name). (default: `"localhost"`) |
| `limit` | integer (nullable) | no | Maximum number of tasks to return. (default: `null`) |
| `running` | boolean (nullable) | no | If True, return only currently-running tasks. (default: `null`) |
| `errors` | boolean (nullable) | no | If True, return only tasks that ended in error. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_traffic_control_delete`

MUTATION (LOW): remove a PBS traffic-control (bandwidth-limit) rule. Dry-run by default.

After deletion: backups run unthrottled on the matched network.
Recoverable by re-creating the rule with pbs_traffic_control_upsert. confirm=True to execute.

DELETE /config/traffic-control/{name}
Smoke-confirm: response shape on success.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Traffic-control rule name to delete. |
| `confirm` | boolean | no | Set True to execute; False (default) only returns the dry-run plan. (default: `false`) |
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
| `name` | string | yes | Traffic-control rule name; creates it if new, updates it if it already exists. |
| `rate_in` | integer (nullable) | no | Sustained inbound bandwidth limit in bytes/second. (default: `null`) |
| `rate_out` | integer (nullable) | no | Sustained outbound bandwidth limit in bytes/second. (default: `null`) |
| `network` | string (nullable) | no | Network/CIDR this rule applies to. (default: `null`) |
| `burst_in` | integer (nullable) | no | Inbound burst bandwidth allowance in bytes. (default: `null`) |
| `burst_out` | integer (nullable) | no | Outbound burst bandwidth allowance in bytes. (default: `null`) |
| `timeframe` | string (nullable) | no | Time window this rule is active (PBS traffic-control timeframe format). (default: `null`) |
| `comment` | string (nullable) | no | Free-text comment/description for the rule. (default: `null`) |
| `confirm` | boolean | no | Set True to execute; False (default) only returns the dry-run plan. (default: `false`) |
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
| `store` | string | yes | PBS datastore name to verify. |
| `ns` | string (nullable) | no | Namespace path to scope verification to; omit for the root namespace. (default: `null`) |
| `backup_type` | string (nullable) | no | Backup type filter: 'vm', 'ct', or 'host'. (default: `null`) |
| `backup_id` | string (nullable) | no | Backup group ID (e.g. VMID/CTID or host name) to scope verification to. (default: `null`) |
| `confirm` | boolean | no | Set True to execute; False (default) only returns the dry-run plan. (default: `false`) |
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
| `name` | string | yes | Name for the new BCC action object. |
| `target` | string | yes | BCC recipient email address. |
| `info` | string (nullable) | no | Optional free-text description. (default: `null`) |
| `original` | boolean (nullable) | no | If True, BCC the original unmodified mail instead of the processed copy. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_action_bcc_update`

MUTATION (MEDIUM): update a BCC action object in the PMG RuleDB. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: PUT /config/ruledb/action/bcc/{id}.
id_: compound action object ID (e.g. '13_26') from pmg_action_objects_list.
Only non-None fields are sent; omitted fields keep current values.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Compound action object ID (e.g. '13_26') from pmg_action_objects_list. |
| `name` | string (nullable) | no | New action object name; omit to keep current value. (default: `null`) |
| `target` | string (nullable) | no | New BCC recipient email address; omit to keep current value. (default: `null`) |
| `info` | string (nullable) | no | New free-text description; omit to keep current value. (default: `null`) |
| `original` | boolean (nullable) | no | If True, BCC the original unmodified mail instead of the processed copy. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
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
| `id_` | string | yes | Compound action object ID (e.g. '13_26') from pmg_action_objects_list. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_action_disclaimer_create`

MUTATION (LOW): create a disclaimer action object in the PMG RuleDB. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/action/disclaimer.
name: action name. disclaimer: disclaimer text. position: start|end.
add_separator: maps to API param 'add-separator' (bool).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name for the new disclaimer action object. |
| `disclaimer` | string | yes | Disclaimer text to append/prepend to mail. |
| `info` | string (nullable) | no | Optional free-text description. (default: `null`) |
| `position` | string (nullable) | no | Where to insert the disclaimer: 'start' or 'end'. (default: `null`) |
| `add_separator` | boolean (nullable) | no | Insert a separator line before the disclaimer; maps to API param 'add-separator'. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_action_disclaimer_update`

MUTATION (MEDIUM): update a disclaimer action object in the PMG RuleDB. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: PUT /config/ruledb/action/disclaimer/{id}.
id_: compound action object ID (e.g. '13_26') from pmg_action_objects_list.
position: start|end (validated). add_separator → 'add-separator'. Only non-None fields sent.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Compound action object ID (e.g. '13_26') from pmg_action_objects_list. |
| `name` | string (nullable) | no | New action object name; omit to keep current value. (default: `null`) |
| `disclaimer` | string (nullable) | no | New disclaimer text; omit to keep current value. (default: `null`) |
| `info` | string (nullable) | no | New free-text description; omit to keep current value. (default: `null`) |
| `position` | string (nullable) | no | Where to insert the disclaimer: 'start' or 'end'. (default: `null`) |
| `add_separator` | boolean (nullable) | no | Insert a separator line before the disclaimer; maps to API param 'add-separator'. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_action_field_create`

MUTATION (LOW): create a field-modification action object in the PMG RuleDB. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/action/field.
name: action object name. field: mail header field to set. value: value to assign.
info: optional description.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name for the new field-modification action object. |
| `field` | string | yes | Mail header field to set. |
| `value` | string | yes | Value to assign to the header field. |
| `info` | string (nullable) | no | Optional free-text description. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_action_field_update`

MUTATION (MEDIUM): update a field-modification action object in the PMG RuleDB. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: PUT /config/ruledb/action/field/{id}.
id_: compound action object ID (e.g. '13_26') from pmg_action_objects_list.
name, field, value all required — PMG 9.1 field action PUT rejects partial updates (400).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Compound action object ID (e.g. '13_26') from pmg_action_objects_list. |
| `name` | string | yes | New action object name; required (PMG rejects partial updates). |
| `field` | string | yes | New mail header field to set; required (PMG rejects partial updates). |
| `value` | string | yes | New value to assign to the header field; required (PMG rejects partial updates). |
| `info` | string (nullable) | no | New free-text description; omit to keep current value. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_action_notification_create`

MUTATION (LOW): create a notification action object in the PMG RuleDB. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/action/notification.
name: action name. to: notification recipient. subject: notification subject.
body_text: notification body (maps to API param 'body'). attach: attach original message.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name for the new notification action object. |
| `to` | string | yes | Notification recipient email address. |
| `subject` | string | yes | Notification email subject line. |
| `body_text` | string | yes | Notification email body text; maps to API param 'body'. |
| `info` | string (nullable) | no | Optional free-text description. (default: `null`) |
| `attach` | boolean (nullable) | no | If True, attach the original message to the notification. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
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
| `id_` | string | yes | Compound action object ID (e.g. '13_26') from pmg_action_objects_list. |
| `name` | string | yes | New action object name; required (PMG rejects partial updates). |
| `to` | string | yes | New notification recipient email address; required (PMG rejects partial updates). |
| `subject` | string | yes | New notification subject line; required (PMG rejects partial updates). |
| `body_text` | string | yes | New notification body text; maps to API param 'body'; required (PMG rejects partial updates). |
| `info` | string (nullable) | no | New free-text description; omit to keep current value. (default: `null`) |
| `attach` | boolean (nullable) | no | If True, attach the original message to the notification. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
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
| `name` | string | yes | Name for the new remove-attachments action object. |
| `text` | string | yes | Replacement text inserted in place of removed attachments. |
| `info` | string (nullable) | no | Optional free-text description. (default: `null`) |
| `all_` | boolean (nullable) | no | If True, remove all attachments; maps to API param 'all'. (default: `null`) |
| `quarantine` | boolean (nullable) | no | If True, quarantine removed attachments instead of discarding them. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_action_removeattachments_update`

MUTATION (MEDIUM): update a remove-attachments action object in the PMG RuleDB. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: PUT /config/ruledb/action/removeattachments/{id}.
id_: compound action object ID (e.g. '13_26') from pmg_action_objects_list.
all_: maps to API param 'all' (bool). Only non-None fields are sent.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Compound action object ID (e.g. '13_26') from pmg_action_objects_list. |
| `name` | string (nullable) | no | New action object name; omit to keep current value. (default: `null`) |
| `text` | string (nullable) | no | New replacement text; omit to keep current value. (default: `null`) |
| `info` | string (nullable) | no | New free-text description; omit to keep current value. (default: `null`) |
| `all_` | boolean (nullable) | no | If True, remove all attachments; maps to API param 'all'. (default: `null`) |
| `quarantine` | boolean (nullable) | no | If True, quarantine removed attachments instead of discarding them. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
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
| `node` | string (nullable) | no | PMG node name; defaults to the configured node. (default: `null`) |
| `notify` | string | no | Notification mode: always\|error\|never (default never). (default: `"never"`) |
| `statistic` | boolean | no | Whether to include mail statistics in the backup (default True). (default: `true`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_doctor`

PMG connectivity + credential/permission preflight (read). Checks /nodes/{node}/version
and /access/users. A successful /version call means ticket login also succeeded —
connectivity and credentials are proven together. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified: PMG has no /access/permissions endpoint (that is PVE-only);
/access/users is the closest equivalent and returns the same user/role information.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_domain_create`

MUTATION (LOW): create a managed mail domain. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: POST /config/domains.
domain: domain name to add (e.g. 'example.com').

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `domain` | string | yes | Domain name to add as a managed mail domain, e.g. 'example.com'. |
| `comment` | string (nullable) | no | Optional free-text comment stored with the domain. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_domain_delete`

MUTATION (MEDIUM): delete a managed mail domain. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: DELETE /config/domains/{domain}.
Mail routing rules referencing this domain may break — review before confirming.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `domain` | string | yes | Managed mail domain name to delete, e.g. 'example.com'. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
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
| `cidr` | string | yes | Network in CIDR notation to trust as an internal relay, e.g. '10.0.0.0/8'. |
| `comment` | string (nullable) | no | Optional free-text comment stored with the mynetworks entry. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_mynetworks_remove`

MUTATION (MEDIUM): remove a CIDR from the PMG mynetworks trusted relay list. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: DELETE /config/mynetworks/{cidr} (CIDR URL-encoded).
Internal senders in the range will be subject to spam filtering after removal.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `cidr` | string | yes | Network in CIDR notation to remove from the trusted mynetworks list. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_node_rrddata`

Get PMG node RRD performance data (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /nodes/{node}/rrddata.
timeframe: REQUIRED — hour|day|week|month|year.
cf: consolidation function AVERAGE|MAX (optional).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `timeframe` | string | yes | RRD timeframe: hour\|day\|week\|month\|year. |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node. (default: `null`) |
| `cf` | string (nullable) | no | RRD consolidation function: AVERAGE\|MAX. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_node_status`

Get PMG node cpu/mem/disk/uptime status (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified: /nodes/{node}/status path and response shape confirmed via
pmg-smoke.py W1 round-trip (node_status PASS).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_node_syslog`

Get PMG node syslog entries (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /nodes/{node}/syslog.
limit: max entries; service: filter by service name.
since/until: time range; start: pagination offset.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node. (default: `null`) |
| `limit` | integer (nullable) | no | Maximum syslog entries to return. (default: `null`) |
| `service` | string (nullable) | no | Filter syslog entries by service name. (default: `null`) |
| `since` | string (nullable) | no | Only return entries at or after this time (journalctl-style time spec). (default: `null`) |
| `until` | string (nullable) | no | Only return entries at or before this time (journalctl-style time spec). (default: `null`) |
| `start` | integer (nullable) | no | Pagination offset into the syslog entries. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_postfix_flush`

MUTATION (LOW): flush all Postfix queues (immediate re-delivery attempt). Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: POST /nodes/{node}/postfix/flush_queues.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_postfix_qshape`

Get PMG Postfix queue shape (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified: /nodes/{node}/postfix/qshape returns a list of
dicts (one row per domain + a TOTAL row with queue-age bucket counts).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node. (default: `null`) |
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
| `action` | string | yes | Action to apply: deliver\|delete\|mark-seen\|mark-unseen\|blocklist\|welcomelist. |
| `mail_ids` | string | yes | Single quarantined mail ID, or a comma-separated list of IDs, to act on. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_attachment`

List attachment quarantine entries (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /quarantine/attachment.
pmail: per-user scope — defaults to authenticated user (api.config.username).
Maps start/end Unix epoch → starttime/endtime query params.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `pmail` | string (nullable) | no | Scope the attachment quarantine read to this user's mailbox; defaults to the authenticated PMG user. (default: `null`) |
| `start` | integer (nullable) | no | Unix epoch start of the window; omit for no lower bound. (default: `null`) |
| `end` | integer (nullable) | no | Unix epoch end of the window; omit for no upper bound. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_blocklist_add`

MUTATION (LOW): add an address to the quarantine blocklist. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: POST /quarantine/blocklist.
pmail: scope to a per-user blocklist (optional).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `address` | string | yes | Email address to add to the quarantine blocklist. |
| `pmail` | string (nullable) | no | Scope the blocklist entry to this user's mailbox; defaults to the authenticated PMG user. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_blocklist_list`

List PMG quarantine blocklist entries (read). Optional pmail to scope to one user.
Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: /quarantine/blocklist.
pmail: scopes the read to one user's blocklist; ALWAYS sent, defaulting to the authenticated
PMG user when omitted — so an empty result means "none for that user", not "none globally".

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `pmail` | string (nullable) | no | Scope the blocklist read to this user's mailbox; defaults to the authenticated PMG user. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_blocklist_remove`

MUTATION (LOW): remove an address from the quarantine blocklist. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: DELETE /quarantine/blocklist.
pmail: optional per-user scope (defaults to authenticated user).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `address` | string | yes | Email address to remove from the quarantine blocklist. |
| `pmail` | string (nullable) | no | Scope the blocklist removal to this user's mailbox; defaults to the authenticated PMG user. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
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
| `start` | integer (nullable) | no | Unix epoch start of the window; omit for no lower bound. (default: `null`) |
| `end` | integer (nullable) | no | Unix epoch end of the window; omit for no upper bound. (default: `null`) |
| `quarantine_type` | string | no | Quarantine type to list users for: spam\|virus\|attachment (default spam). (default: `"spam"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_virus`

List virus quarantine entries (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /quarantine/virus.
pmail: per-user scope — defaults to authenticated user (api.config.username).
Maps start/end Unix epoch → starttime/endtime query params.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `pmail` | string (nullable) | no | Scope the virus quarantine read to this user's mailbox; defaults to the authenticated PMG user. (default: `null`) |
| `start` | integer (nullable) | no | Unix epoch start of the window; omit for no lower bound. (default: `null`) |
| `end` | integer (nullable) | no | Unix epoch end of the window; omit for no upper bound. (default: `null`) |
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
| `address` | string | yes | Email address to add to the quarantine welcomelist. |
| `pmail` | string (nullable) | no | Scope the welcomelist entry to this user's mailbox; defaults to the authenticated PMG user. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_welcomelist_list`

List PMG quarantine welcomelist entries (read). Optional pmail to scope to one user.
Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /quarantine/welcomelist.
pmail defaults to the authenticated user when not provided.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `pmail` | string (nullable) | no | Scope the welcomelist read to this user's mailbox; defaults to the authenticated PMG user. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_welcomelist_remove`

MUTATION (LOW): remove an address from the quarantine welcomelist. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: DELETE /quarantine/welcomelist.
pmail: optional per-user scope (defaults to authenticated user).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `address` | string | yes | Email address to remove from the quarantine welcomelist. |
| `pmail` | string (nullable) | no | Scope the welcomelist removal to this user's mailbox; defaults to the authenticated PMG user. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
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
| `id_` | string | yes | Rule ID to attach the action group to. |
| `ogroup` | string | yes | Numeric action group ID from pmg_action_objects_list to attach to the rule. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_action_detach`

MUTATION (MEDIUM): detach an action group from a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 live-verified path: DELETE /config/ruledb/rules/{id}/action/{ogroup} (singular; /actions returns 501).
id_: rule ID. ogroup: numeric action group ID to detach.
Only affects mail flow if the rule is active.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Rule ID to detach the action group from. |
| `ogroup` | string | yes | Numeric action group ID currently attached to the rule to detach. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_actions_list`

List the 'actions' objects attached to a PMG RuleDB rule (read). Needs PROXIMO_PMG_* config.

PMG 9.1: reads GET /config/ruledb/rules/{id}/config and extracts the embedded 'action' list —
the dedicated .../actions path returns HTTP 501 (not implemented), so it is NOT used.
id_: rule ID (positive integer string, e.g. '100').

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | RuleDB rule ID (positive integer string, e.g. '100'). |
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
| `name` | string | yes | Name for the new RuleDB rule. |
| `priority` | integer | yes | Rule priority 0-100; lower numbers are evaluated with higher priority. |
| `active` | boolean | no | Whether the rule is active on creation; defaults False since active rules affect live mail processing. (default: `false`) |
| `direction` | integer (nullable) | no | Mail direction the rule applies to: 0=inbound, 1=outbound, 2=both. (default: `null`) |
| `from_and` | boolean (nullable) | no | AND (True) vs OR (False) logic across attached 'from' groups. (default: `null`) |
| `from_invert` | boolean (nullable) | no | If True, invert the 'from' group match. (default: `null`) |
| `to_and` | boolean (nullable) | no | AND (True) vs OR (False) logic across attached 'to' groups. (default: `null`) |
| `to_invert` | boolean (nullable) | no | If True, invert the 'to' group match. (default: `null`) |
| `what_and` | boolean (nullable) | no | AND (True) vs OR (False) logic across attached 'what' groups. (default: `null`) |
| `what_invert` | boolean (nullable) | no | If True, invert the 'what' group match. (default: `null`) |
| `when_and` | boolean (nullable) | no | AND (True) vs OR (False) logic across attached 'when' groups. (default: `null`) |
| `when_invert` | boolean (nullable) | no | If True, invert the 'when' group match. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_delete`

MUTATION (MEDIUM): delete a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/rules/{id}.
id_: rule ID (positive integer string, e.g. '100').
WARNING: permanently removes the rule and all its group bindings.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Rule ID (positive integer string, e.g. '100'). |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_from_attach`

MUTATION (MEDIUM): attach a 'from' (sender/who) group to a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/rules/{id}/from.
id_: rule ID. ogroup: numeric who-group ID from pmg_who_groups_list.
Only affects mail flow if the rule is active.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Rule ID to attach the group to. |
| `ogroup` | string | yes | Numeric 'who' group ID from pmg_who_groups_list to attach as the 'from' condition. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_from_detach`

MUTATION (MEDIUM): detach a 'from' (sender/who) group from a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/rules/{id}/from/{ogroup}.
id_: rule ID. ogroup: numeric who-group ID to detach.
Only affects mail flow if the rule is active.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Rule ID to detach the group from. |
| `ogroup` | string | yes | Numeric 'who' group ID currently attached as the 'from' condition to detach. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_from_list`

List the 'from' objects attached to a PMG RuleDB rule (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules/{id}/from.
id_: rule ID (positive integer string, e.g. '100').

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | RuleDB rule ID (positive integer string, e.g. '100'). |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_get`

Get a PMG RuleDB rule's configuration (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules/{id}/config.
id_: rule ID (positive integer string, e.g. '100').

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | RuleDB rule ID (positive integer string, e.g. '100'). |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_to_attach`

MUTATION (MEDIUM): attach a 'to' (recipient/who) group to a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/rules/{id}/to.
id_: rule ID. ogroup: numeric who-group ID from pmg_who_groups_list.
Only affects mail flow if the rule is active.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Rule ID to attach the group to. |
| `ogroup` | string | yes | Numeric 'who' group ID from pmg_who_groups_list to attach as the 'to' condition. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_to_detach`

MUTATION (MEDIUM): detach a 'to' (recipient/who) group from a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/rules/{id}/to/{ogroup}.
id_: rule ID. ogroup: numeric who-group ID to detach.
Only affects mail flow if the rule is active.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Rule ID to detach the group from. |
| `ogroup` | string | yes | Numeric 'who' group ID currently attached as the 'to' condition to detach. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_to_list`

List the 'to' objects attached to a PMG RuleDB rule (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules/{id}/to.
id_: rule ID (positive integer string, e.g. '100').

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | RuleDB rule ID (positive integer string, e.g. '100'). |
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
| `id_` | string | yes | Rule ID (positive integer string, e.g. '100'). |
| `name` | string (nullable) | no | New rule name; omit to keep current value. (default: `null`) |
| `priority` | integer (nullable) | no | New rule priority 0-100; lower numbers are evaluated with higher priority. (default: `null`) |
| `active` | boolean (nullable) | no | Whether the rule is active; True begins live mail processing under this rule. (default: `null`) |
| `direction` | integer (nullable) | no | Mail direction the rule applies to: 0=inbound, 1=outbound, 2=both. (default: `null`) |
| `from_and` | boolean (nullable) | no | AND (True) vs OR (False) logic across attached 'from' groups. (default: `null`) |
| `from_invert` | boolean (nullable) | no | If True, invert the 'from' group match. (default: `null`) |
| `to_and` | boolean (nullable) | no | AND (True) vs OR (False) logic across attached 'to' groups. (default: `null`) |
| `to_invert` | boolean (nullable) | no | If True, invert the 'to' group match. (default: `null`) |
| `what_and` | boolean (nullable) | no | AND (True) vs OR (False) logic across attached 'what' groups. (default: `null`) |
| `what_invert` | boolean (nullable) | no | If True, invert the 'what' group match. (default: `null`) |
| `when_and` | boolean (nullable) | no | AND (True) vs OR (False) logic across attached 'when' groups. (default: `null`) |
| `when_invert` | boolean (nullable) | no | If True, invert the 'when' group match. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_what_attach`

MUTATION (MEDIUM): attach a 'what' (content) group to a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/rules/{id}/what.
id_: rule ID. ogroup: numeric what-group ID from pmg_what_groups_list.
Only affects mail flow if the rule is active.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Rule ID to attach the group to. |
| `ogroup` | string | yes | Numeric 'what' group ID from pmg_what_groups_list to attach as a content condition. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_what_detach`

MUTATION (MEDIUM): detach a 'what' (content) group from a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/rules/{id}/what/{ogroup}.
id_: rule ID. ogroup: numeric what-group ID to detach.
Only affects mail flow if the rule is active.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Rule ID to detach the group from. |
| `ogroup` | string | yes | Numeric 'what' group ID currently attached as a content condition to detach. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_what_list`

List the 'what' objects attached to a PMG RuleDB rule (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules/{id}/what.
id_: rule ID (positive integer string, e.g. '100').

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | RuleDB rule ID (positive integer string, e.g. '100'). |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_when_attach`

MUTATION (MEDIUM): attach a 'when' (timeframe) group to a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: POST /config/ruledb/rules/{id}/when.
id_: rule ID. ogroup: numeric when-group ID from pmg_when_groups_list.
Only affects mail flow if the rule is active.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Rule ID to attach the group to. |
| `ogroup` | string | yes | Numeric 'when' group ID from pmg_when_groups_list to attach as a timeframe condition. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_when_detach`

MUTATION (MEDIUM): detach a 'when' (timeframe) group from a PMG RuleDB rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/rules/{id}/when/{ogroup}.
id_: rule ID. ogroup: numeric when-group ID to detach.
Only affects mail flow if the rule is active.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Rule ID to detach the group from. |
| `ogroup` | string | yes | Numeric 'when' group ID currently attached as a timeframe condition to detach. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_when_list`

List the 'when' objects attached to a PMG RuleDB rule (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules/{id}/when.
id_: rule ID (positive integer string, e.g. '100').

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | RuleDB rule ID (positive integer string, e.g. '100'). |
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
| `service` | string | yes | PMG service name, e.g. postfix, pmgproxy, pmgdaemon, clamav, spamassassin. |
| `action` | string | yes | Control action: start\|stop\|restart\|reload. |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_service_status`

Get the status of a PMG system service (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: /nodes/{node}/services/{service}/state.
service: e.g. 'postfix', 'pmgproxy', 'pmgdaemon', 'pmgmirror', 'pmgtunnel',
         'pmg-smtp-filter', 'clamav', 'spamassassin'. No hardcoded enum —
         pass any valid service name; unknown names return a PMG 404.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `service` | string | yes | PMG service name, e.g. postfix, pmgproxy, pmgdaemon, pmgmirror, pmgtunnel, pmg-smtp-filter, clamav, spamassassin. |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node. (default: `null`) |
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
| `bounce_score` | integer (nullable) | no | Spam score threshold added for bounce/NDR-shaped messages; omit to leave unchanged. (default: `null`) |
| `clamav_heuristic_score` | integer (nullable) | no | Spam score added when ClamAV heuristic detection fires; omit to leave unchanged. (default: `null`) |
| `extract_text` | boolean (nullable) | no | Whether to extract text from attachments for spam scanning; omit to leave unchanged. (default: `null`) |
| `languages` | string (nullable) | no | Space-separated language codes used for spam language-based scoring; omit to leave unchanged. (default: `null`) |
| `maxspamsize` | integer (nullable) | no | Maximum message size in bytes scanned for spam; omit to leave unchanged. (default: `null`) |
| `rbl_checks` | boolean (nullable) | no | Whether to enable RBL (realtime blocklist) checks; omit to leave unchanged. (default: `null`) |
| `use_awl` | boolean (nullable) | no | Whether to enable the auto-whitelist; omit to leave unchanged. (default: `null`) |
| `use_bayes` | boolean (nullable) | no | Whether to enable Bayesian spam classification; omit to leave unchanged. (default: `null`) |
| `use_razor` | boolean (nullable) | no | Whether to enable Razor collaborative spam filtering; omit to leave unchanged. (default: `null`) |
| `wl_bounce_relays` | string (nullable) | no | Whitelisted bounce-relay hosts, space-separated; omit to leave unchanged. (default: `null`) |
| `delete` | string (nullable) | no | Comma-separated field names to reset to their PMG defaults. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_statistics_domains`

Get PMG per-domain mail statistics (read). Optional Unix epoch start/end timespan.
Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: /statistics/domains.
Maps start/end params → starttime/endtime query params.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | integer (nullable) | no | Unix epoch start of the stats window; omit for no lower bound. (default: `null`) |
| `end` | integer (nullable) | no | Unix epoch end of the stats window; omit for no upper bound. (default: `null`) |
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
| `start` | integer (nullable) | no | Unix epoch start of the window; omit for no lower bound. (default: `null`) |
| `end` | integer (nullable) | no | Unix epoch end of the window; omit for no upper bound. (default: `null`) |
| `timespan` | integer | no | Histogram bucket size in seconds, 3600-31622400 (default 3600 = 1 hour). (default: `3600`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_statistics_receiver`

Get per-recipient mail statistics (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /statistics/receiver.
filter_: optional search string; orderby: raw sort spec passthrough.
Maps start/end Unix epoch → starttime/endtime query params.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | integer (nullable) | no | Unix epoch start of the window; omit for no lower bound. (default: `null`) |
| `end` | integer (nullable) | no | Unix epoch end of the window; omit for no upper bound. (default: `null`) |
| `filter_` | string (nullable) | no | Optional search string to filter recipients. (default: `null`) |
| `orderby` | string (nullable) | no | Raw sort spec passed through to the PMG API. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_statistics_recent`

Get PMG recent mail statistics (read). hours: 1-24 window. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: /statistics/recent.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `hours` | integer | no | Lookback window in hours, 1-24 (default 1). (default: `1`) |
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
| `start` | integer (nullable) | no | Unix epoch start of the window; omit for no lower bound. (default: `null`) |
| `end` | integer (nullable) | no | Unix epoch end of the window; omit for no upper bound. (default: `null`) |
| `filter_` | string (nullable) | no | Optional search string to filter senders. (default: `null`) |
| `orderby` | string (nullable) | no | Accepted for compatibility but ignored — PMG 9.1 rejects orderby on this endpoint. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_statistics_spamscores`

Get PMG spam score distribution statistics (read). Optional Unix epoch start/end timespan.
Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: /statistics/spamscores.
Maps start/end params → starttime/endtime query params.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | integer (nullable) | no | Unix epoch start of the stats window; omit for no lower bound. (default: `null`) |
| `end` | integer (nullable) | no | Unix epoch end of the stats window; omit for no upper bound. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_statistics_virus`

Get PMG virus statistics (read). Optional Unix epoch start/end timespan.
Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: /statistics/virus.
Maps start/end params → starttime/endtime query params.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | integer (nullable) | no | Unix epoch start of the stats window; omit for no lower bound. (default: `null`) |
| `end` | integer (nullable) | no | Unix epoch end of the stats window; omit for no upper bound. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_tasks_list`

List PMG tasks on a node (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /nodes/{node}/tasks.
start: pagination offset; limit: max entries.
errors: True = only failed tasks; userfilter/typefilter/statusfilter: text filters.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node. (default: `null`) |
| `start` | integer (nullable) | no | Pagination offset into the task list. (default: `null`) |
| `limit` | integer (nullable) | no | Maximum tasks to return. (default: `null`) |
| `userfilter` | string (nullable) | no | Filter tasks by the user that started them. (default: `null`) |
| `errors` | boolean (nullable) | no | If True, return only failed tasks. (default: `null`) |
| `typefilter` | string (nullable) | no | Filter tasks by task type. (default: `null`) |
| `since` | integer (nullable) | no | Unix epoch: only tasks started at or after this time. (default: `null`) |
| `until` | integer (nullable) | no | Unix epoch: only tasks started at or before this time. (default: `null`) |
| `statusfilter` | string (nullable) | no | Filter tasks by status text. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_tracker_detail`

Get tracking detail for a specific mail ID (read). Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: GET /nodes/{node}/tracker/{id}.
id_: mail/queue tracker ID, validated path-segment-safe (rejects '..', '/',
control/whitespace chars) before use — see _check_tracker_id.
Maps start/end Unix epoch → starttime/endtime query params.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Mail/queue tracker ID to fetch detail for. |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node. (default: `null`) |
| `start` | integer (nullable) | no | Unix epoch start of the tracker window; omit for no lower bound. (default: `null`) |
| `end` | integer (nullable) | no | Unix epoch end of the tracker window; omit for no upper bound. (default: `null`) |
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
| `node` | string (nullable) | no | PMG node name; defaults to the configured node. (default: `null`) |
| `start` | integer (nullable) | no | Unix epoch start of the tracker window; omit for no lower bound. (default: `null`) |
| `end` | integer (nullable) | no | Unix epoch end of the tracker window; omit for no upper bound. (default: `null`) |
| `from_` | string (nullable) | no | Filter by envelope sender address. (default: `null`) |
| `target` | string (nullable) | no | Filter by recipient address. (default: `null`) |
| `xfilter` | string (nullable) | no | Free-text filter applied to tracker entries. (default: `null`) |
| `ndr` | boolean (nullable) | no | If set, filter to (or exclude) non-delivery-report entries. (default: `null`) |
| `greylist` | boolean (nullable) | no | If set, filter to (or exclude) greylisted entries. (default: `null`) |
| `limit` | integer | no | Maximum entries to return, 0-100000 (default 2000). (default: `2000`) |
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
| `domain` | string | yes | Destination domain the transport rule applies to. |
| `host` | string | yes | Next-hop relay hostname or IP for mail to this domain. |
| `comment` | string (nullable) | no | Optional free-text comment stored with the transport rule. (default: `null`) |
| `port` | integer | no | TCP port to connect to on the relay host, 1-65535 (default 25). (default: `25`) |
| `protocol` | string | no | Transport protocol: smtp\|lmtp (default smtp). (default: `"smtp"`) |
| `use_mx` | boolean | no | Whether to use MX lookup for the relay host (default True). (default: `true`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_transport_delete`

MUTATION (MEDIUM): delete a mail transport rule. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

PMG 9.1 live-verified path via pmgsh ls: DELETE /config/transport/{domain}.
Mail for the domain will fall back to default PMG routing (MX lookup).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `domain` | string | yes | Destination domain whose transport rule should be deleted. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
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
| `name` | string | yes | Name for the new 'what' object group. |
| `info` | string (nullable) | no | Optional free-text description of the group. (default: `null`) |
| `and_` | boolean (nullable) | no | AND (True) vs OR (False) logic across group members; maps to API param 'and'. (default: `null`) |
| `invert` | boolean (nullable) | no | If True, invert the group's match result. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_what_group_delete`

MUTATION (MEDIUM): delete a PMG RuleDB 'what' object group. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/what/{ogroup}.
ogroup: numeric ID string (e.g. '8') from pmg_what_groups_list.
WARNING: also removes all objects within the group.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | Numeric 'what' object group ID (e.g. '8') from pmg_what_groups_list. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_what_group_get`

Get a PMG RuleDB 'what' object group's configuration (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/what/{ogroup}/config.
ogroup: numeric ID string (e.g. '2') from the matching pmg_*_groups_list — NOT the group name.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | 'what' object group numeric ID (e.g. '2') from pmg_what_groups_list — not the group name. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_what_group_objects`

List the objects in a PMG RuleDB 'what' object group (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/what/{ogroup}/objects.
ogroup: numeric ID string (e.g. '2') from the matching pmg_*_groups_list — NOT the group name.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | 'what' object group numeric ID (e.g. '2') from pmg_what_groups_list — not the group name. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_what_group_update`

MUTATION (MEDIUM): update a PMG RuleDB 'what' object group config. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: PUT /config/ruledb/what/{ogroup}/config.
ogroup: numeric ID string (e.g. '8') from pmg_what_groups_list.
Only non-None fields are sent to PMG; omitted fields keep current values.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | Numeric 'what' object group ID (e.g. '8') from pmg_what_groups_list. |
| `name` | string (nullable) | no | New name for the group; omit to keep current value. (default: `null`) |
| `info` | string (nullable) | no | New free-text description; omit to keep current value. (default: `null`) |
| `and_` | boolean (nullable) | no | AND (True) vs OR (False) logic across group members; maps to API param 'and'. (default: `null`) |
| `invert` | boolean (nullable) | no | If True, invert the group's match result. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
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
| `ogroup` | string | yes | Numeric 'what' object group ID (e.g. '8') from pmg_what_groups_list. |
| `type_` | string | yes | Object type: contenttype\|matchfield\|spamfilter\|virusfilter\|filenamefilter\|archivefilter\|archivefilenamefilter. |
| `contenttype` | string (nullable) | no | MIME content type to match; used for type_='contenttype'/'archivefilter'. (default: `null`) |
| `only_content` | boolean (nullable) | no | Match content only, not filename; maps to API param 'only-content'. (default: `null`) |
| `field` | string (nullable) | no | Mail header field name to match; used for type_='matchfield'. (default: `null`) |
| `value` | string (nullable) | no | Value/pattern to match against the field; used for type_='matchfield'. (default: `null`) |
| `top_part_only` | boolean (nullable) | no | Restrict match to the top MIME part only; maps to API param 'top-part-only'. (default: `null`) |
| `spamlevel` | integer (nullable) | no | Spam score threshold; used for type_='spamfilter'. (default: `null`) |
| `filename` | string (nullable) | no | Filename pattern to match; used for type_='filenamefilter'/'archivefilenamefilter'. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
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
| `ogroup` | string | yes | Numeric 'what' object group ID (e.g. '8') from pmg_what_groups_list. |
| `id_` | string | yes | Object ID (numeric string) from pmg_what_group_objects. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
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
| `ogroup` | string | yes | Numeric 'what' object group ID (e.g. '8') from pmg_what_groups_list. |
| `type_` | string | yes | Object type: contenttype\|matchfield\|spamfilter\|virusfilter\|filenamefilter\|archivefilter\|archivefilenamefilter. |
| `id_` | string | yes | Object ID (numeric string) from pmg_what_group_objects. |
| `contenttype` | string (nullable) | no | New MIME content type; used for type_='contenttype'/'archivefilter'. (default: `null`) |
| `only_content` | boolean (nullable) | no | Match content only, not filename; maps to API param 'only-content'. (default: `null`) |
| `field` | string (nullable) | no | Mail header field name to match; used for type_='matchfield'. (default: `null`) |
| `value` | string (nullable) | no | Value/pattern to match against the field; used for type_='matchfield'. (default: `null`) |
| `top_part_only` | boolean (nullable) | no | Restrict match to the top MIME part only; maps to API param 'top-part-only'. (default: `null`) |
| `spamlevel` | integer (nullable) | no | New spam score threshold; used for type_='spamfilter'. (default: `null`) |
| `filename` | string (nullable) | no | New filename pattern; used for type_='filenamefilter'/'archivefilenamefilter'. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
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
| `name` | string | yes | Name for the new 'when' object group. |
| `info` | string (nullable) | no | Optional free-text description of the group. (default: `null`) |
| `and_` | boolean (nullable) | no | AND (True) vs OR (False) logic across group members; maps to API param 'and'. (default: `null`) |
| `invert` | boolean (nullable) | no | If True, invert the group's match result. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_when_group_delete`

MUTATION (MEDIUM): delete a PMG RuleDB 'when' object group. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/when/{ogroup}.
ogroup: numeric ID string (e.g. '4') from pmg_when_groups_list.
WARNING: also removes all objects within the group.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | Numeric 'when' object group ID (e.g. '4') from pmg_when_groups_list. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_when_group_get`

Get a PMG RuleDB 'when' object group's configuration (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/when/{ogroup}/config.
ogroup: numeric ID string (e.g. '2') from the matching pmg_*_groups_list — NOT the group name.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | 'when' object group numeric ID (e.g. '2') from pmg_when_groups_list — not the group name. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_when_group_objects`

List the objects in a PMG RuleDB 'when' object group (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/when/{ogroup}/objects.
ogroup: numeric ID string (e.g. '2') from the matching pmg_*_groups_list — NOT the group name.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | 'when' object group numeric ID (e.g. '2') from pmg_when_groups_list — not the group name. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_when_group_update`

MUTATION (MEDIUM): update a PMG RuleDB 'when' object group config. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: PUT /config/ruledb/when/{ogroup}/config.
ogroup: numeric ID string (e.g. '4') from pmg_when_groups_list.
Only non-None fields are sent to PMG; omitted fields keep current values.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | Numeric 'when' object group ID (e.g. '4') from pmg_when_groups_list. |
| `name` | string (nullable) | no | New name for the group; omit to keep current value. (default: `null`) |
| `info` | string (nullable) | no | New free-text description; omit to keep current value. (default: `null`) |
| `and_` | boolean (nullable) | no | AND (True) vs OR (False) logic across group members; maps to API param 'and'. (default: `null`) |
| `invert` | boolean (nullable) | no | If True, invert the group's match result. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
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
| `ogroup` | string | yes | Numeric 'when' object group ID (e.g. '4') from pmg_when_groups_list. |
| `start` | string | yes | Timeframe start time in H:i format (e.g. '08:00'). |
| `end` | string | yes | Timeframe end time in H:i format (e.g. '17:00'). |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
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
| `ogroup` | string | yes | Numeric 'when' object group ID (e.g. '4') from pmg_when_groups_list. |
| `id_` | string | yes | Object ID (numeric string) from pmg_when_group_objects. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
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
| `ogroup` | string | yes | Numeric 'when' object group ID (e.g. '4') from pmg_when_groups_list. |
| `id_` | string | yes | Object ID (numeric string) from pmg_when_group_objects. |
| `start` | string | yes | New timeframe start time in H:i format (e.g. '08:00'); required, PMG rejects partial updates. |
| `end` | string | yes | New timeframe end time in H:i format (e.g. '17:00'); required, PMG rejects partial updates. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
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
| `name` | string | yes | Name for the new 'who' object group. |
| `info` | string (nullable) | no | Optional free-text description of the group. (default: `null`) |
| `and_` | boolean (nullable) | no | AND (True) vs OR (False) logic across group members; maps to API param 'and'. (default: `null`) |
| `invert` | boolean (nullable) | no | If True, invert the group's match result. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_who_group_delete`

MUTATION (MEDIUM): delete a PMG RuleDB 'who' object group. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/who/{ogroup}.
ogroup: numeric ID string (e.g. '2') from pmg_who_groups_list.
WARNING: also removes all objects within the group.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | Numeric 'who' object group ID (e.g. '2') from pmg_who_groups_list. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_who_group_get`

Get a PMG RuleDB 'who' object group's configuration (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/who/{ogroup}/config.
ogroup: numeric ID string (e.g. '2') from the matching pmg_*_groups_list — NOT the group name.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | 'who' object group numeric ID (e.g. '2') from pmg_who_groups_list — not the group name. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_who_group_objects`

List the objects in a PMG RuleDB 'who' object group (read). Needs PROXIMO_PMG_* config.

PMG 9.1 pmgsh-verified path: GET /config/ruledb/who/{ogroup}/objects.
ogroup: numeric ID string (e.g. '2') from the matching pmg_*_groups_list — NOT the group name.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | 'who' object group numeric ID (e.g. '2') from pmg_who_groups_list — not the group name. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_who_group_update`

MUTATION (MEDIUM): update a PMG RuleDB 'who' object group config. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.
PMG 9.1 pmgsh-verified path: PUT /config/ruledb/who/{ogroup}/config.
ogroup: numeric ID string (e.g. '2') from pmg_who_groups_list.
Only non-None fields are sent to PMG; omitted fields keep current values.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | Numeric 'who' object group ID (e.g. '2') from pmg_who_groups_list. |
| `name` | string (nullable) | no | New name for the group; omit to keep current value. (default: `null`) |
| `info` | string (nullable) | no | New free-text description; omit to keep current value. (default: `null`) |
| `and_` | boolean (nullable) | no | AND (True) vs OR (False) logic across group members; maps to API param 'and'. (default: `null`) |
| `invert` | boolean (nullable) | no | If True, invert the group's match result. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
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
| `ogroup` | string | yes | Numeric 'who' object group ID (e.g. '2') from pmg_who_groups_list. |
| `type_` | string | yes | Object type: email\|domain\|regex\|ip\|network\|ldap — selects which sub-path/fields apply. |
| `email` | string (nullable) | no | Email address to match; required when type_='email'. (default: `null`) |
| `domain` | string (nullable) | no | Domain to match; required when type_='domain'. (default: `null`) |
| `regex` | string (nullable) | no | Regex pattern to match; required when type_='regex'. (default: `null`) |
| `ip` | string (nullable) | no | IP address to match; required when type_='ip'. (default: `null`) |
| `cidr` | string (nullable) | no | CIDR network to match; required when type_='network'. (default: `null`) |
| `mode` | string (nullable) | no | LDAP lookup mode; used when type_='ldap'. (default: `null`) |
| `profile` | string (nullable) | no | LDAP profile name; used when type_='ldap'. (default: `null`) |
| `group` | string (nullable) | no | LDAP group name; used when type_='ldap'. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
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
| `ogroup` | string | yes | Numeric 'who' object group ID (e.g. '2') from pmg_who_groups_list. |
| `id_` | string | yes | Object ID (numeric string) from pmg_who_group_objects. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
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
| `ogroup` | string | yes | Numeric 'who' object group ID (e.g. '2') from pmg_who_groups_list. |
| `type_` | string | yes | Object type: email\|domain\|regex\|ip\|network\|ldap — selects which sub-path/fields apply. |
| `id_` | string | yes | Object ID (numeric string) from pmg_who_group_objects. |
| `email` | string (nullable) | no | New email address; used when type_='email'. (default: `null`) |
| `domain` | string (nullable) | no | New domain; used when type_='domain'. (default: `null`) |
| `regex` | string (nullable) | no | New regex pattern; used when type_='regex'. (default: `null`) |
| `ip` | string (nullable) | no | New IP address; used when type_='ip'. (default: `null`) |
| `cidr` | string (nullable) | no | New CIDR network; used when type_='network'. (default: `null`) |
| `mode` | string (nullable) | no | LDAP lookup mode; used when type_='ldap'. (default: `null`) |
| `profile` | string (nullable) | no | LDAP profile name; used when type_='ldap'. (default: `null`) |
| `group` | string (nullable) | no | LDAP group name; used when type_='ldap'. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

## Proxmox Datacenter Manager (PDM)

#### `pdm_acl_list`

DIAGNOSE (LOW): list PDM access control entries.
path: optional ACL path filter (e.g. '/'). exact: if True, exact path only.
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `path` | string (nullable) | no | Optional ACL path filter, e.g. '/'; omit to list all entries. (default: `null`) |
| `exact` | boolean | no | If true, match the given path exactly rather than including sub-paths. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_node_status`

DIAGNOSE (LOW): get resource stats for a PDM node. Defaults to 'localhost'
(PDM is a single-node appliance). Shape equals PVE node status;
live-prove-pending. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PDM node name; PDM is single-node so this defaults to 'localhost'. (default: `"localhost"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pbs_datastores_list`

DIAGNOSE (LOW): list datastores on a PDM-registered PBS remote.
remote: remote name from pdm_remotes_list.
Live-verified shape: [{"name","path"}, ...] (PDM 1.1 -> PBS 4.2).
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered PBS remote name, from pdm_remotes_list. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pbs_remote_status`

DIAGNOSE (LOW): get node status for a PDM-registered PBS remote.
remote: remote name from pdm_remotes_list.
Live-verified (PDM 1.1 -> PBS 4.2).
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered PBS remote name, from pdm_remotes_list. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pbs_snapshots_list`

DIAGNOSE (LOW): list backup snapshots in a datastore on a PDM-registered PBS remote.
remote: remote name. datastore: PBS datastore name. ns: optional namespace filter.
Live-verified path (PDM 1.1 -> PBS 4.2); empty datastore returns [].
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered PBS remote name, from pdm_remotes_list. |
| `datastore` | string | yes | PBS datastore name on the remote to list snapshots from. |
| `ns` | string (nullable) | no | Optional PBS namespace filter; omit to use the default namespace. (default: `null`) |
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
| `remote` | string | yes | PDM-registered PVE remote name, from pdm_remotes_list. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_config`

DIAGNOSE (LOW): get LXC config from a PDM-registered PVE remote.
remote: remote name. vmid: numeric CT ID.
node, snapshot: optional query params (node is NOT required).
state: REQUIRED by PDM ("active" = current config) — defaults to "active"; PDM 400s if omitted.
Live-proven 2026-06-27 against a registered PVE remote. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered PVE remote name, from pdm_remotes_list. |
| `vmid` | string | yes | Numeric CT ID on the remote. |
| `node` | string (nullable) | no | Optional PVE node name; not required for PDM to resolve the container. (default: `null`) |
| `snapshot` | string (nullable) | no | Optional snapshot name to read config from instead of the live config. (default: `null`) |
| `state` | string | no | PDM config-state selector, required by the PDM API; 'active' returns the current config. (default: `"active"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_list`

DIAGNOSE (LOW): list LXC containers across a PDM-registered PVE remote (cluster-wide).
remote: remote name. node: OPTIONAL filter to one PVE node.
Shape equals PVE lxc list; live-proven 2026-06-27 against a registered PVE remote.
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered PVE remote name, from pdm_remotes_list. |
| `node` | string (nullable) | no | Optional PVE node name to restrict the listing to; omit to list cluster-wide. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_migrate`

MUTATION: migrate a container to another node within the remote's cluster (through PDM).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered remote (Proxmox cluster) hosting the container. |
| `vmid` | string | yes | Numeric CTID of the container to migrate, as a string. |
| `target` | string | yes | Destination node name within the same remote's cluster. |
| `online` | boolean | no | True live-migrates the container; else it must be stopped. (default: `false`) |
| `confirm` | boolean | no | False (default) returns a PLAN only; True submits it. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_power`

MUTATION: start/stop/shutdown a container on a PDM-registered remote (through PDM).

Dry-run by default (PLAN); confirm=True to submit. Task-backed → 'submitted'.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered remote (Proxmox cluster) hosting the container. |
| `vmid` | string | yes | Numeric CTID of the target container, as a string. |
| `action` | string | yes | Power action: 'start', 'stop', or 'shutdown'. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_remote_migrate`

MUTATION: migrate a container to a DIFFERENT PDM-registered remote
(datacenter-to-datacenter).

target_bridge and target_storage mappings are required (e.g. 'vmbr0:vmbr0',
'local-lvm:local-lvm'). delete=True removes the source after a successful move
(destructive). Dry-run by default (PLAN); confirm=True to submit.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered remote (Proxmox cluster) hosting the container. |
| `vmid` | string | yes | Numeric CTID of the container to migrate, as a string. |
| `target_remote` | string | yes | Destination PDM-registered remote (a different datacenter). |
| `target_bridge` | string | yes | Source-to-target network bridge mapping, e.g. 'vmbr0:vmbr0'. |
| `target_storage` | string | yes | Source-to-target storage mapping, e.g. 'local-lvm:local-lvm'. |
| `target_vmid` | string (nullable) | no | CTID on the destination; omit to keep same CTID. (default: `null`) |
| `online` | boolean | no | True live-migrates the container; else it must be stopped. (default: `false`) |
| `delete` | boolean | no | True deletes container after successful move (destructive). (default: `false`) |
| `confirm` | boolean | no | False (default) returns a PLAN only; True submits it. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_snapshot_create`

MUTATION: snapshot a container on a PDM-registered remote (through PDM).

Containers have no RAM state, so there is no vmstate option. Dry-run by default.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered remote (Proxmox cluster) hosting the container. |
| `vmid` | string | yes | Numeric CTID of the target container, as a string. |
| `snapname` | string | yes | Name to give the new snapshot. |
| `description` | string (nullable) | no | Optional free-text note stored with the snapshot. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a PLAN only; True creates it. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_snapshot_delete`

MUTATION: delete a container snapshot on a PDM-registered remote. Irreversible; no UNDO.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered remote (Proxmox cluster) hosting the container. |
| `vmid` | string | yes | Numeric CTID of the target container, as a string. |
| `snapname` | string | yes | Name of the snapshot to delete. |
| `confirm` | boolean | no | False (default) returns a PLAN only; True deletes it. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_snapshot_rollback`

MUTATION: roll a container back to a snapshot on a PDM-registered remote (through PDM).

DESTRUCTIVE. Takes an auto safety-snapshot first (fail-closed). Dry-run by default.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered remote (Proxmox cluster) hosting the container. |
| `vmid` | string | yes | Numeric CTID of the target container, as a string. |
| `snapname` | string | yes | Name of the snapshot to roll back to. |
| `confirm` | boolean | no | False (default) returns a PLAN only; True runs it. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_node_list`

DIAGNOSE (LOW): list nodes in a PDM-registered PVE remote.
remote: remote name from pdm_remotes_list.
Shape equals PVE /nodes; live-proven 2026-06-27 against a registered PVE remote.
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered PVE remote name, from pdm_remotes_list. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_qemu_config`

DIAGNOSE (LOW): get VM config from a PDM-registered PVE remote.
remote: remote name. vmid: numeric VM ID.
node, snapshot: optional query params (node is NOT required).
state: REQUIRED by PDM ("active" = current config) — defaults to "active"; PDM 400s if omitted.
Live-proven 2026-06-27 against a registered PVE remote. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered PVE remote name, from pdm_remotes_list. |
| `vmid` | string | yes | Numeric VM ID on the remote. |
| `node` | string (nullable) | no | Optional PVE node name; not required for PDM to resolve the VM. (default: `null`) |
| `snapshot` | string (nullable) | no | Optional snapshot name to read config from instead of the live config. (default: `null`) |
| `state` | string | no | PDM config-state selector, required by the PDM API; 'active' returns the current config. (default: `"active"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_qemu_list`

DIAGNOSE (LOW): list VMs across a PDM-registered PVE remote (cluster-wide).
remote: remote name. node: OPTIONAL filter to one PVE node.
Shape equals PVE qemu list; live-proven 2026-06-27 against a registered PVE remote.
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered PVE remote name, from pdm_remotes_list. |
| `node` | string (nullable) | no | Optional PVE node name to restrict the listing to; omit to list cluster-wide. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_qemu_migrate`

MUTATION: migrate a VM to another node within the remote's cluster (through PDM).

online=True migrates a running VM. Dry-run by default (PLAN); confirm=True to submit.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered remote (Proxmox cluster) currently hosting the VM. |
| `vmid` | string | yes | Numeric VMID of the VM to migrate, as a string. |
| `target` | string | yes | Destination node name within the same remote's cluster. |
| `online` | boolean | no | True live-migrates the VM; else it must be stopped. (default: `false`) |
| `confirm` | boolean | no | False (default) returns a PLAN only; True submits it. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_qemu_power`

MUTATION: start/stop/shutdown/resume a VM on a PDM-registered remote (through PDM).

Dry-run by default: returns a PLAN (live state, blast radius, risk) recorded to the
ledger. Re-call with confirm=True to submit. Task-backed → status='submitted'.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered remote (Proxmox cluster) hosting the VM. |
| `vmid` | string | yes | Numeric VMID of the target VM, as a string. |
| `action` | string | yes | Power action: 'start', 'stop', 'shutdown', or 'resume'. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_qemu_remote_migrate`

MUTATION: migrate a VM to a DIFFERENT PDM-registered remote (datacenter-to-datacenter).

target_bridge and target_storage mappings are required (e.g. 'vmbr0:vmbr0',
'local-lvm:local-lvm'). delete=True removes the source after a successful move (destructive).
Dry-run by default (PLAN); confirm=True to submit.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered remote (Proxmox cluster) currently hosting the VM. |
| `vmid` | string | yes | Numeric VMID of the VM to migrate, as a string. |
| `target_remote` | string | yes | Destination PDM-registered remote (a different datacenter). |
| `target_bridge` | string | yes | Source-to-target network bridge mapping, e.g. 'vmbr0:vmbr0'. |
| `target_storage` | string | yes | Source-to-target storage mapping, e.g. 'local-lvm:local-lvm'. |
| `target_vmid` | string (nullable) | no | VMID on the destination; omit to keep same VMID. (default: `null`) |
| `online` | boolean | no | True live-migrates the VM; else it must be stopped. (default: `false`) |
| `delete` | boolean | no | True deletes source VM after successful move (irreversible). (default: `false`) |
| `confirm` | boolean | no | False (default) returns a PLAN only; True submits it. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_qemu_snapshot_create`

MUTATION: snapshot a VM on a PDM-registered remote (through PDM).

vmstate=True includes the VM's RAM state. Additive (LOW risk). Dry-run by default.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered remote (Proxmox cluster) hosting the VM. |
| `vmid` | string | yes | Numeric VMID of the target VM, as a string. |
| `snapname` | string | yes | Name to give the new snapshot. |
| `description` | string (nullable) | no | Optional free-text note stored with the snapshot. (default: `null`) |
| `vmstate` | boolean | no | True includes the VM's RAM state (larger, slower snapshot). (default: `false`) |
| `confirm` | boolean | no | False (default) returns a PLAN only; True creates it. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_qemu_snapshot_delete`

MUTATION: delete a VM snapshot on a PDM-registered remote. Irreversible; no UNDO. Dry-run by default.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered remote (Proxmox cluster) hosting the VM. |
| `vmid` | string | yes | Numeric VMID of the target VM, as a string. |
| `snapname` | string | yes | Name of the snapshot to delete. |
| `confirm` | boolean | no | False (default) returns a PLAN only; True deletes it. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_qemu_snapshot_rollback`

MUTATION: roll a VM back to a snapshot on a PDM-registered remote (through PDM).

DESTRUCTIVE (discards current state). Takes an auto safety-snapshot first (fail-closed:
no snapshot, no rollback). Dry-run by default (PLAN); confirm=True to submit.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered remote (Proxmox cluster) hosting the VM. |
| `vmid` | string | yes | Numeric VMID of the target VM, as a string. |
| `snapname` | string | yes | Name of the snapshot to roll back to. |
| `confirm` | boolean | no | False (default) returns a PLAN only; True runs it. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_resources`

DIAGNOSE (LOW): list resources on a PDM-registered PVE remote.
remote: remote name from pdm_remotes_list.
kind: optional filter (vm, storage, node, sdn, ...).
Shape equals PVE cluster/resources; live-proven 2026-06-27 against a registered PVE remote.
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered PVE remote name, from pdm_remotes_list. |
| `kind` | string (nullable) | no | Optional resource-type filter, e.g. 'vm', 'storage', 'node', 'sdn'. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_remote_config_get`

DIAGNOSE (LOW): get configuration for one PDM-registered remote (no secrets returned).
remote_id: the remote name as shown in pdm_remotes_list.
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote_id` | string | yes | Remote name as shown in pdm_remotes_list. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_remote_version`

DIAGNOSE (LOW): get version info for one PDM-registered remote.
remote_id: the remote name as shown in pdm_remotes_list.
Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote_id` | string | yes | Remote name as shown in pdm_remotes_list. |
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
| `include_tokens` | boolean | no | If true, include API token entries alongside user accounts. (default: `false`) |
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
| `ctid` | string | yes | Numeric CTID of the LXC container to diagnose. |
| `kind` | string | no | Guest type; only `lxc` is meaningful here since diagnostics are container-specific. (default: `"lxc"`) |
| `node` | string (nullable) | no | PVE node the container runs on. Omit to resolve it automatically from the cluster. (default: `null`) |
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
| `ctid` | string | yes | Numeric CTID of the target LXC container (allowlist-scoped). |
| `command` | array<string> | yes | Argv list to run inside the container (not a shell string). |
| `snapshot` | boolean | no | Take a fail-closed auto-undo snapshot before running. (default: `false`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; true executes. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `ct_logs`

Tail journalctl for a systemd unit inside a container (read-only). Returns the command's
returncode, stdout, and stderr. Container-specific diagnostic; gated by the CTID allowlist
when PROXIMO_ENABLE_EXEC is set. Fails closed if exec is disabled.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ctid` | string | yes | Numeric CTID of the LXC container to read logs from. |
| `unit` | string | yes | Name of the systemd unit to tail journalctl for (e.g. `nginx.service`). |
| `lines` | integer | no | Number of most-recent log lines to return. (default: `50`) |
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
| `ctid` | string | yes | Numeric CTID of the container running PostgreSQL (allowlist-scoped). |
| `sql` | string | yes | SQL to run via psql inside the container, as the database OS user. |
| `db` | string | no | Target database name. (default: `"postgres"`) |
| `snapshot` | boolean | no | Take a fail-closed auto-undo snapshot before running. (default: `false`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; true executes. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

## Core / trust spine

#### `audit_verify`

Verify the tamper-evident audit ledger's hash chain — PROVE the log is intact.

Pass `expected_head` (the head() value you pinned off-box) to also catch tail
truncation, a forged tail-append, or a full file replacement — a forward walk
alone can't see those. Falls back to PROXIMO_AUDIT_EXPECTED_HEAD when omitted.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `expected_head` | string (nullable) | no | 64-char hex head() value pinned off-box; verifying against it also catches tail truncation, a forged tail-append, or a full ledger replacement. Omit to fall back to PROXIMO_AUDIT_EXPECTED_HEAD. (default: `null`) |
