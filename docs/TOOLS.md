# Proximo — tool reference

The complete external interface of Proximo **v0.22.0**: every MCP tool it exposes, with its inputs. This file is generated from the live server's `tools/list` output (via `lhm.plugin.json`) by [`scripts/gen_tools_doc.py`](../scripts/gen_tools_doc.py) — do not hand-edit.

**Interface conventions.** Proximo speaks the [Model Context Protocol](https://modelcontextprotocol.io); each tool is also self-describing at runtime over the standard `tools/list` method. **Inputs** are the typed parameters listed per tool below. **Output** is a structured JSON result: read tools return the requested data; every mutating tool first returns a **PLAN** preview (the action and its blast radius) rather than acting, and each call is recorded in the tamper-evident audit ledger. Which tools are registered depends on `PROXIMO_SURFACES` and whether the opt-in exec/agent edges are enabled; this reference lists the **full** catalog.

**493 tools** across 7 surfaces.

## Contents

- [Proxmox VE — in-guest agent (opt-in)](#proxmox-ve--in-guest-agent-opt-in) — 6
- [Proxmox VE (PVE)](#proxmox-ve-pve) — 191
- [Proxmox Backup Server (PBS)](#proxmox-backup-server-pbs) — 147
- [Proxmox Mail Gateway (PMG)](#proxmox-mail-gateway-pmg) — 110
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

Requires PROXIMO_ENABLE_AGENT=1, the VMID in PROXIMO_AGENT_ALLOWLIST, and a running guest agent
inside the VM. No confirm needed — read-only. File path must be absolute. To write instead use
pve_agent_file_write. Returns {"bytes-read": int, "content": str} — text round-trips exactly;
the ledger records only the file path, never the content.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric VM ID of the guest to read from via the qemu-agent. |
| `file` | string | yes | Absolute path of the file to read inside the guest. |
| `node` | string (nullable) | no | Proxmox node name hosting the guest; auto-detected if omitted. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_agent_file_write`

MUTATION: write a file inside the guest via the qemu-agent.

Requires PROXIMO_ENABLE_AGENT=1, the VMID in PROXIMO_AGENT_ALLOWLIST, and a running guest agent
inside the VM. Dry-run by default (returns a PLAN); confirm=True executes and returns
{"status": "ok", "result": None}. File path must be absolute; content is UNCONDITIONALLY
redacted from the ledger (fingerprint only). Overwrites the target file whole — irreversible,
no undo primitive on this plane. To read a file instead use pve_agent_file_read; text content
round-trips byte-identical, binary/encoded content is unconfirmed.

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

Requires PROXIMO_ENABLE_AGENT=1, the VMID in PROXIMO_AGENT_ALLOWLIST, and a running guest agent
inside the VM. Dry-run by default (returns a PLAN); confirm=True executes and returns
{"status": "ok", "result": <raw qemu-agent response>}. command: fsfreeze-freeze | fsfreeze-thaw
| fstrim — freeze stalls guest I/O until thawed, so always pair them. Irreversible; no undo
primitive on this plane.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric VM ID of the guest to operate on via the qemu-agent. |
| `command` | string | yes | Filesystem operation: fsfreeze-freeze, fsfreeze-thaw, or fstrim. |
| `node` | string (nullable) | no | Proxmox node name hosting the guest; auto-detected if omitted. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the command. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_agent_info`

READ-ONLY: query the qemu-agent on a guest (ping, osinfo, hostname, users, exec-status, …).

Requires PROXIMO_ENABLE_AGENT=1, the VMID in PROXIMO_AGENT_ALLOWLIST, and a running guest agent
inside the VM. No confirm needed — read-only. Returns a dict of the raw qemu-agent response
fields for the chosen command; for command='exec-status', run pve_agent_exec first and pass its
returned pid here to poll for completion.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric VM ID of the guest to query via the qemu-agent. |
| `command` | string | no | qemu-agent query: ping, info, get-fsinfo, get-host-name, get-osinfo, get-time, get-timezone, get-users, get-vcpus, network-get-interfaces, get-memory-blocks, fsfreeze-status, or exec-status. (default: `"info"`) |
| `pid` | integer (nullable) | no | Process id returned by pve_agent_exec; required only when command='exec-status'. (default: `null`) |
| `node` | string (nullable) | no | Proxmox node name hosting the guest; auto-detected if omitted. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_agent_set_password`

MUTATION: set a guest OS user's password via the qemu-agent.

Requires PROXIMO_ENABLE_AGENT=1, the VMID in PROXIMO_AGENT_ALLOWLIST, and a running guest agent
inside the VM. Dry-run by default (returns a PLAN); confirm=True executes and returns
{"status": "ok", "result": None}. Password is UNCONDITIONALLY redacted from the ledger
(fingerprint only — "[redacted]"). Irreversible without knowledge of the old password; no undo
primitive on this plane.

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

Dry-run by default (returns a PLAN) — it surfaces the critical Proxmox gotcha: a specific-path
ACL REPLACES inherited grants (SHADOW) and revoking can RESTORE them (WIDEN). confirm=True
executes and returns a dict; synchronous, no UPID. Use pve_acl_list to see current entries,
pve_overbroad_grants to find over-broad ones, or pve_acl_prune to narrow/remove one.

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

Dry-run by default (returns a PLAN naming every principal losing/gaining what, and flagging
shadow/widen gotchas); confirm=True executes and returns a dict. Non-atomic — a revoke PUT
then an optional narrower re-grant PUT — but safe-direction: a partial failure only narrows
access, never widens it. Synchronous. roleid = the over-broad role to remove (from detection).

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

Additive — does not affect any existing account. Pair with pve_acme_plugin_create (DNS-01) or
standalone http-01, then pve_node_acme_domains_set + pve_acme_cert_order, to actually issue a
cert; to remove an account instead use pve_acme_account_delete. confirm=True executes and
returns {"status": "ok"}; the default returns a dry-run PLAN dict. Smoke-confirm: POST body
shape (name in body) against a live PVE instance.

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

HIGH risk: TLS lockout at cert expiry if this is the only account. The account key is
destroyed — registering again with pve_acme_account_create creates a DIFFERENT CA account, not
a restore of this one. The dry-run PLAN captures the current config as evidence only.
confirm=True executes and returns {"status": "ok"}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the ACME account to deactivate and delete from the CA. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the irreversible deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acme_account_update`

MUTATION: update ACME account contact info. Dry-run by default.

LOW risk — metadata update only, no cert impact. To delete the account instead use
pve_acme_account_delete. The dry-run PLAN includes the account's current config (contact,
directory, tos); confirm=True executes and returns {"status": "ok"}.

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
a task UPID (poll pve_task_status/pve_task_wait). MEDIUM: CA-validated, installed only on
success (a failure can't lock you out); reloads pveproxy on success. force=renew even if more
than 30 days to expiry. To order a fresh cert instead use pve_acme_cert_order; to revert to
self-signed use pve_node_cert_delete. confirm=True to execute. Smoke-confirm: PUT shape + async
UPID against a live PVE instance.

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

Additive — does not affect any existing plugin. dns_api = DNS provider name (e.g. 'cf',
'route53'). Reference plugin_id from pve_node_acme_domains_set(plugin=...) to drive a DNS-01
challenge with it; to remove the plugin use pve_acme_plugin_delete. confirm=True executes and
returns {"status": "ok"}; the default returns a dry-run PLAN dict. Smoke-confirm: POST body
shape (id in body) against a live PVE instance.

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

HIGH risk: cert auto-renewal breaks for every domain using this plugin — TLS lockout at cert
expiry unless a fallback challenge method is configured. No UNDO primitive — recreate with
pve_acme_plugin_create, but the credentials must be re-supplied by the caller. The dry-run PLAN
captures the current config (credential redacted) as evidence only; confirm=True executes and
returns {"status": "ok"}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `plugin_id` | string | yes | Identifier of the ACME DNS challenge plugin to delete. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_acme_plugin_update`

MUTATION: update an ACME DNS challenge plugin. Dry-run by default.

MEDIUM risk — invalid new credentials break cert renewal for every domain using this plugin
at the next attempt. To remove a plugin instead use pve_acme_plugin_delete. The dry-run PLAN
includes the plugin's current config with any DNS-provider credential redacted; confirm=True
executes and returns {"status": "ok"}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `plugin_id` | string | yes | Identifier of the existing ACME DNS challenge plugin to update. |
| `dns_api` | string (nullable) | no | New DNS provider API name for a DNS-01 challenge; maps to PVE's 'api' field. Omit to leave unchanged. (default: `null`) |
| `data` | string (nullable) | no | New plugin-specific credential/config data; omit to leave unchanged. (default: `null`) |
| `disable` | boolean (nullable) | no | Set to enable/disable the plugin; omit to leave unchanged. (default: `null`) |
| `digest` | string (nullable) | no | Config digest for optimistic-locking the update against concurrent changes; omit to skip the check. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the update. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_apt_changelog`

READ-ONLY: get a package's changelog text on a PVE node.

GET /nodes/{node}/apt/changelog?name=…[&version=…]. Smoke-confirm: shape not live-verified.
The returned text is UPSTREAM/package-maintainer-authored (not Proxmox-authored) — classified
ADVERSARIAL content (taint.ADVERSARIAL_TOOLS), unlike the other six pve_apt_* tools. Proxmox's
API deliberately does not expose upgrade execution; the upgrade itself happens at your
console. This tool governs visibility only.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Package name to fetch the changelog for (e.g. as listed by pve_apt_updates_list). |
| `node` | string (nullable) | no | PVE node name to query; defaults to the configured node if omitted. (default: `null`) |
| `version` | string (nullable) | no | Specific package version to fetch the changelog for; omit for the latest available. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_apt_repositories_get`

READ-ONLY: get the current APT repository configuration of a PVE node.

GET /nodes/{node}/apt/repositories. Smoke-confirm: shape not live-verified — expected
{files, errors, digest, infos, standard-repos}. `files[].path` + entry index are the
coordinates pve_apt_repository_set needs; `standard-repos[].handle` is what
pve_apt_repository_add needs. Proxmox's API deliberately does not expose upgrade execution;
the upgrade itself happens at your console. This tool governs visibility and repo config only.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name to query; defaults to the configured node if omitted. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_apt_repository_add`

MUTATION: add a standard repository to the configuration on a PVE node.

RISK_MEDIUM: adds a new package source — affects the NEXT upgrade's package provenance.
CAPTURE: reads current repository state before planning (also readable directly via
pve_apt_repositories_get); if unreadable -> complete=False. No automatic revert: removing an
added repository requires pve_apt_repository_set to disable the resulting entry (there is no
repository-delete endpoint). Proxmox's API deliberately does not expose upgrade execution;
the upgrade itself happens at your console. This tool governs repo config only. Dry-run by
default (returns a PLAN); confirm=True executes (PUT, Smoke-confirm) and returns
{"status": "ok", "result": None}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `handle` | string | yes | Handle identifying the standard repository to add (as returned by pve_apt_repositories_get's standard-repos list, e.g. 'no-subscription'). |
| `node` | string (nullable) | no | PVE node name to configure; defaults to the configured node if omitted. (default: `null`) |
| `digest` | string (nullable) | no | Expected content digest of the repositories file, for optimistic-concurrency conflict detection. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the addition. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_apt_repository_set`

MUTATION: enable/disable one APT repository entry on a PVE node, by file path + index.

RISK_MEDIUM: changes where packages come from — affects the NEXT upgrade's package
provenance. CAPTURE: reads current repository state before planning (also readable directly
via pve_apt_repositories_get); if unreadable -> complete=False. Proxmox's API deliberately
does not expose upgrade execution; the upgrade itself happens at your console. This tool
governs repo config only. Dry-run by default (returns a PLAN); confirm=True executes (POST,
Smoke-confirm) and returns {"status": "ok", "result": None}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `path` | string | yes | Absolute path of the sources file containing the repository entry (as returned by pve_apt_repositories_get). |
| `index` | integer | yes | 0-based index of the repository entry within that file (as returned by pve_apt_repositories_get). |
| `node` | string (nullable) | no | PVE node name to configure; defaults to the configured node if omitted. (default: `null`) |
| `enabled` | boolean (nullable) | no | Set the entry's enabled state; omit to leave the enabled state unchanged. (default: `null`) |
| `digest` | string (nullable) | no | Expected content digest of the repositories file, for optimistic-concurrency conflict detection. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the change. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_apt_update_refresh`

MUTATION: resynchronize the APT package index on a PVE node (apt-get update).

RISK_LOW: no package state change — refreshes the local index cache only. Proxmox's API
deliberately does not expose upgrade execution; the upgrade itself happens at your console.
This tool governs visibility only — it does NOT install or upgrade any package. Idempotent —
safe to re-run any time. Dry-run by default (returns a PLAN); confirm=True executes (POST,
Smoke-confirm) and returns {"status": "submitted"|"ok", "result": <task UPID | None>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name to refresh; defaults to the configured node if omitted. (default: `null`) |
| `notify` | boolean (nullable) | no | If True, ask Proxmox to send a notification email about newly available packages. (default: `null`) |
| `quiet` | boolean (nullable) | no | If True, ask Proxmox to omit progress output suitable only for interactive logging. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the index refresh. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_apt_updates_list`

READ-ONLY: list available package updates (cached apt index) on a PVE node.

GET /nodes/{node}/apt/update. Smoke-confirm: shape not live-verified — expected per-package
dicts (Package/Title/Description/Origin/Version/OldVersion/Priority/Section/Arch). Proxmox's
API deliberately does not expose upgrade execution; the upgrade itself happens at your
console. This tool governs visibility only. To refresh this list first use
pve_apt_update_refresh.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name to query; defaults to the configured node if omitted. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_apt_versions`

READ-ONLY: get installed versions of important Proxmox packages on a PVE node.

GET /nodes/{node}/apt/versions. Smoke-confirm: shape not live-verified — expected per-package
dicts (Package/Version/OldVersion + CurrentState/RunningKernel/ManagerVersion). Proxmox's API
deliberately does not expose upgrade execution; the upgrade itself happens at your console.
This tool governs visibility only.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name to query; defaults to the configured node if omitted. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_backup`

MUTATION: back up a guest with vzdump. Dry-run by default; confirm=True to execute.
mode: snapshot (online, brief) | suspend | stop (HALTS the guest). Async — returns a task UPID.
This is a one-off run; for a recurring schedule use pve_backup_job_create instead.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric ID of the guest (VM or CT) to back up. |
| `storage` | string | yes | Storage ID to write the backup archive to. |
| `mode` | string | no | Backup mode: snapshot (online, brief) \| suspend (RAM-quiesced pause) \| stop (HALTS the guest). (default: `"snapshot"`) |
| `compress` | string | no | Compression algorithm for the archive, e.g. zstd, gzip, lzo, or 0 (no compression). (default: `"zstd"`) |
| `kind` | string | no | Guest type: lxc or qemu. (default: `"lxc"`) |
| `node` | string (nullable) | no | Proxmox node hosting the guest; defaults to the configured node if omitted. (default: `null`) |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the backup. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_backup_delete`

MUTATION: delete a backup archive (removes a recovery point). Dry-run by default; confirm=True
to execute. Irreversible — deleting the last backup of a guest leaves no recovery point; the
PLAN reports how many other backups of the same guest remain. Check the archive list first with
pve_backup_list. Async — may return a task UPID or null depending on storage.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes | Storage ID holding the backup archive. |
| `volid` | string | yes | Volume ID of the backup archive to delete (as returned by pve_backup_list). |
| `node` | string (nullable) | no | Proxmox node hosting the storage; defaults to the configured node if omitted. (default: `null`) |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_backup_freshness`

READ-ONLY: backup-freshness fence — walks ACTUAL backup archives per guest and compares
their age against what enabled backup jobs promise; a job or task reporting OK is never
treated as evidence a backup exists. Verdicts per guest: fresh | stale | never | uncovered |
unknown; an unreadable storage always yields unknown + complete=false, never a clean bill.
Returns a dict of {guests, jobs, counts, flags, complete, …}. For the raw archive list use
pve_backup_list; for job configuration use pve_backup_job_list.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `max_age_hours` | number (nullable) | no | Override for max acceptable backup age in hours; if omitted, age expectation is derived from each guest's backup job schedule. (default: `null`) |
| `grace_hours` | number | no | Hours of slack padded onto each job's parsed cadence before a backup is flagged stale. (default: `6.0`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_backup_job_create`

MUTATION: create a PVE cluster backup job — a persistent vzdump schedule, distinct from a
one-off pve_backup run. Dry-run by default; confirm=True to execute and returns synchronously
(no task UPID). Config-only; existing backups are NOT affected. Guest selection is mutually
exclusive — pass at most one of vmid, all_guests, or pool; exclude filters all_guests. To
modify an existing job use pve_backup_job_update; to remove one use pve_backup_job_delete.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `job_id` | string | yes | Unique ID for the new PVE backup job. |
| `schedule` | string | yes | Proxmox calendar-event schedule string, e.g. 'sat 02:00' or a systemd.time-style spec. |
| `storage` | string | yes | Storage ID the job writes backups to. |
| `mode` | string (nullable) | no | Backup mode: snapshot \| suspend \| stop; defaults to Proxmox's own default if omitted. (default: `null`) |
| `compress` | string (nullable) | no | Compression algorithm for archives, e.g. zstd, gzip, lzo, or 0 (no compression). (default: `null`) |
| `vmid` | string (nullable) | no | CSV of guest IDs to include; mutually exclusive with all_guests and pool. (default: `null`) |
| `all_guests` | boolean (nullable) | no | If true, back up every guest on the cluster; mutually exclusive with vmid and pool. (default: `null`) |
| `pool` | string (nullable) | no | Resource pool of guests to back up; mutually exclusive with vmid and all_guests. (default: `null`) |
| `exclude` | string (nullable) | no | CSV of guest IDs to exclude when all_guests=True. (default: `null`) |
| `enabled` | boolean (nullable) | no | Whether the job is active; defaults to enabled if omitted. (default: `null`) |
| `comment` | string (nullable) | no | Free-text note stored on the job. (default: `null`) |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the creation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_backup_job_delete`

MUTATION: delete a PVE cluster backup job. Dry-run by default — the PLAN captures current
config (no snapshot/UNDO primitive on this plane; re-create with pve_backup_job_create to
restore the schedule). confirm=True to execute and returns synchronously (no task UPID).
Schedule removed; existing backups are NOT deleted.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `job_id` | string | yes | ID of the PVE backup job to delete. |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_backup_job_list`

READ-ONLY: list all PVE cluster backup jobs and guests not covered by any job.
Returns {jobs: [...], unprotected_guests: [...]}. For the actual archives on storage use
pve_backup_list; for a per-guest freshness verdict against these jobs' promises use
pve_backup_freshness.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_backup_job_update`

MUTATION: update a PVE cluster backup job. Dry-run by default — the PLAN captures current
config so you can revert manually; confirm=True to execute and returns synchronously (no task
UPID). Config-only; no impact on existing backups. To create a new job use
pve_backup_job_create; to remove one use pve_backup_job_delete.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `job_id` | string | yes | ID of the existing PVE backup job to update. |
| `schedule` | string (nullable) | no | New Proxmox calendar-event schedule string; omit to leave unchanged. (default: `null`) |
| `storage` | string (nullable) | no | New storage ID for the job's backups; omit to leave unchanged. (default: `null`) |
| `mode` | string (nullable) | no | New backup mode: snapshot \| suspend \| stop; omit to leave unchanged. (default: `null`) |
| `compress` | string (nullable) | no | New compression algorithm, e.g. zstd, gzip, lzo, or 0 (no compression); omit to leave unchanged. (default: `null`) |
| `vmid` | string (nullable) | no | New CSV of guest IDs the job covers; omit to leave unchanged. (default: `null`) |
| `enabled` | boolean (nullable) | no | Whether the job is active; omit to leave unchanged. (default: `null`) |
| `comment` | string (nullable) | no | New free-text note; omit to leave unchanged. (default: `null`) |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the update. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_backup_list`

READ-ONLY: list backup archives in a storage. Ground truth for whether a backup exists —
a backup missing from a pve_tasks_list slice (other node, or outside its limit window)
still shows here. Returns a list of dicts (volid, size, ctime, …).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes | Storage ID to list backup archives from. |
| `node` | string (nullable) | no | Proxmox node hosting the storage; defaults to the configured node if omitted. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_clone`

MUTATION: clone a guest to a new id. Dry-run by default; confirm=True. Async — returns a
UPID (poll with pve_task_status). pool: place the new guest in a resource pool (needed when
the token is pool-scoped). storage: target storage for the full clone's disks (full=True
only) — keeps a clone off the source storage; refused for a linked clone (PVE only honors it
on a full clone). To create a guest from scratch instead use pve_create_vm / pve_create_container.

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

MUTATION: set cloud-init fields (ciuser/sshkeys/ipconfigN/...) on a QEMU guest — kind='lxc'
is refused (cloud-init is QEMU-only). Dry-run by default with secrets masked in the PLAN;
confirm=True to execute. Synchronous; the return carries a top-level undo_record key beside
status/result (secret fields excluded). Effects apply on next reboot + cloud-init regen, not live. Read current
values with pve_cloudinit_get.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric VMID of the QEMU guest to set cloud-init config on. |
| `changes` | object | yes | Cloud-init fields to change, e.g. {'ciuser': 'admin', 'sshkeys': '...', 'ipconfig0': 'ip=dhcp'}. |
| `node` | string (nullable) | no | PVE node the guest runs on. Omit to resolve it automatically from the cluster. (default: `null`) |
| `kind` | string | no | Guest type; cloud-init applies to `qemu` guests. (default: `"qemu"`) |
| `confirm` | boolean | no | Leave `false` (default) to get a dry-run PLAN with secrets masked; set `true` to execute. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_cluster_resources`

READ-ONLY: list all resources across the cluster (VMs, nodes, storage, SDN).

resource_type: optional filter — 'vm', 'storage', 'node', or 'sdn'; omit for all types.
No state change. Returns a list of PVE resource dicts (shape varies by type). For overall
cluster health/quorum use pve_cluster_status; to list only guests use pve_list_guests.

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

MUTATION: create a new LXC container. Dry-run by default; confirm=True. Async — returns a
UPID (poll with pve_task_status). `options` carries extra create params (cores, memory, net0,
rootfs, password, ...). For a QEMU VM use pve_create_vm; to copy an existing guest instead
use pve_clone.

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

MUTATION: create a new QEMU VM. Dry-run by default; confirm=True. Async — returns a UPID
(poll with pve_task_status). `options` carries create params (cores, memory, net0, scsi0,
ostype, ...). For an LXC container use pve_create_container; to copy an existing guest
instead use pve_clone.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vmid` | string | yes | Numeric VMID to assign to the new QEMU VM. |
| `node` | string (nullable) | no | PVE node to create the VM on. Omit to use the configured default node. (default: `null`) |
| `options` | object (nullable) | no | Extra Proxmox create params (e.g. cores, memory, net0, scsi0, ostype) merged into the request. (default: `null`) |
| `confirm` | boolean | no | Leave `false` (default) to get a dry-run PLAN; set `true` to execute the creation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_delete_guest`

MUTATION (DESTRUCTIVE, IRREVERSIBLE): permanently destroy a guest and its disks. Dry-run by
default — the PLAN names exactly what will be destroyed, including cascade effects on backup/
HA/replication references. confirm=True to execute. Async — returns the task UPID; poll with
pve_task_status. No undo once confirmed.

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

READ-ONLY: gather one node's health evidence in a single call — node status, storage usage,
recent failed tasks, and advisory flags — for triage.

No state change and no side effects. This inspects *node* health; to instead verify your token's
connectivity and effective permissions use pve_doctor, and for in-container evidence use
ct_diagnose. Returns a dict of the gathered sections; omit `node` to use the configured default.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node to gather health evidence for. Omit to use the configured default node. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_disk_move`

MUTATION: move a guest disk to another storage. Dry-run by default — the PLAN shows
source->target and whether the source copy is deleted (delete_source=True is HIGH, no easy
undo). confirm=True to execute. Async — returns a task UPID (poll with pve_task_status). To
grow a disk in place instead of relocating it use pve_disk_resize.

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

MUTATION: grow a guest disk (e.g. size='+10G'). GROW ONLY — a shrink is refused as
destructive, and an ambiguous absolute size is refused too unless the current size can be
verified first. Dry-run by default; confirm=True to execute. Async — returns a task UPID
(poll with pve_task_status). To move a disk to different storage instead use pve_disk_move.

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
Returns a dict with reachable/version, the can/cannot capability map, config, and advisory flags.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_alias_create`

MUTATION: create a firewall alias (named CIDR). Dry-run by default — the PLAN shows the
name, CIDR, and scope. Re-call with confirm=True to execute. Passive until a rule references it.
Synchronous — confirm=True returns {"status": "ok", "result": None}; no task UPID to poll.

No UNDO: revert by deleting the alias with pve_firewall_alias_delete. To change an existing
alias instead, use pve_firewall_alias_update.

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
PVE refuses while any rule still references the alias. No UNDO: re-create it with
pve_firewall_alias_create to revert. Synchronous — confirm=True returns
{"status": "ok", "result": None}; no task UPID to poll.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the alias to delete. |
| `scope` | string | no | Firewall scope: 'cluster' or 'guest' (no node-scope aliases in the PVE API). (default: `"cluster"`) |
| `node` | string (nullable) | no | Node name, required for scope='guest'. (default: `null`) |
| `vmid` | string (nullable) | no | Guest VMID/CTID, required for scope='guest'. (default: `null`) |
| `kind` | string (nullable) | no | Guest kind for scope='guest': 'qemu' or 'lxc'. (default: `null`) |
| `digest` | string (nullable) | no | Optimistic-lock digest forwarded to PVE to abort if the alias changed; this tool's PLAN does not surface a digest to copy (only the rule tools do). (default: `null`) |
| `confirm` | boolean | no | Set True to execute the mutation; False (default) only returns a dry-run PLAN. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_alias_list`

READ-ONLY: list firewall aliases (named CIDRs) for the given scope. Scope = cluster
or guest only — the PVE API has no node-scope aliases (node firewall = options/rules/log).

No state change. Returns a list of alias dicts (name, cidr, comment, ipversion). To create,
change, or remove an alias use pve_firewall_alias_create / pve_firewall_alias_update /
pve_firewall_alias_delete.

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
Synchronous — confirm=True returns {"status": "ok", "result": None}; no task UPID to poll.

Requires at least one of cidr/comment/rename. No UNDO — revert by setting it back to its prior
value; to create a new alias instead use pve_firewall_alias_create.

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
| `digest` | string (nullable) | no | Optimistic-lock digest forwarded to PVE to abort if the alias changed; this tool's PLAN does not surface a digest to copy (only the rule tools do). (default: `null`) |
| `confirm` | boolean | no | Set True to execute the mutation; False (default) only returns a dry-run PLAN. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_ipset_create`

MUTATION: create an empty IP set. Dry-run by default — the PLAN shows the name and scope.
Passive until a rule references it as '+name' and entries are added via
pve_firewall_ipset_entry_add. Synchronous — confirm=True returns
{"status": "ok", "result": None}; no task UPID to poll.

No UNDO: revert by deleting it with pve_firewall_ipset_delete.

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
Synchronous — confirm=True returns {"status": "ok", "result": None}; no task UPID to poll.

No UNDO: re-create it with pve_firewall_ipset_create and re-add members to revert.

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
Synchronous — confirm=True returns {"status": "ok", "result": None}; no task UPID to poll.

No UNDO: revert by removing the entry with pve_firewall_ipset_entry_remove.

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
Synchronous — confirm=True returns {"status": "ok", "result": None}; no task UPID to poll.

No UNDO: revert by re-adding the entry with pve_firewall_ipset_entry_add.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the IP set to remove the entry from. |
| `cidr` | string | yes | IP address or CIDR network of the member entry to remove. |
| `scope` | string | no | Firewall scope: 'cluster' or 'guest' (no node-scope ipsets in the PVE API). (default: `"cluster"`) |
| `node` | string (nullable) | no | Node name, required for scope='guest'. (default: `null`) |
| `vmid` | string (nullable) | no | Guest VMID/CTID, required for scope='guest'. (default: `null`) |
| `kind` | string (nullable) | no | Guest kind for scope='guest': 'qemu' or 'lxc'. (default: `null`) |
| `digest` | string (nullable) | no | Optimistic-lock digest forwarded to PVE to abort if the set changed; this tool's PLAN does not surface a digest to copy (only the rule tools do). (default: `null`) |
| `confirm` | boolean | no | Set True to execute the mutation; False (default) only returns a dry-run PLAN. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_options_get`

READ-ONLY: get the firewall option block (enable flag, default in/out policy, log rate limit,
…) at cluster, node, or guest scope.

No state change. Pair with pve_firewall_options_set to change these, and pve_firewall_rules_list
to read the rules themselves. scope='node' requires `node`; scope='guest' requires `node`, `vmid`,
and `kind` ('qemu'|'lxc'). Returns the option block as a dict.

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
Synchronous — confirm=True returns {"status": "ok", "result": None}; no task UPID to poll.

To read current values first use pve_firewall_options_get; to toggle just the enable flag use
the focused pve_firewall_set_enabled. No UNDO — revert by setting the prior values.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `scope` | string | no | Firewall scope: 'cluster', 'node', or 'guest'. (default: `"cluster"`) |
| `node` | string (nullable) | no | Node name, required for scope='node' or scope='guest'. (default: `null`) |
| `vmid` | string (nullable) | no | Guest VMID/CTID, required for scope='guest'. (default: `null`) |
| `kind` | string (nullable) | no | Guest kind for scope='guest': 'qemu' or 'lxc'. (default: `null`) |
| `options` | object (nullable) | no | Key-value bag of firewall options to set, e.g. policy_in, policy_out, log_ratelimit, enable, ebtables. (default: `null`) |
| `delete` | array<string> (nullable) | no | List of option keys to unset/remove. (default: `null`) |
| `digest` | string (nullable) | no | Optimistic-lock digest forwarded to PVE to abort if the options changed; this tool's PLAN does not surface a digest to copy (only the rule tools do). (default: `null`) |
| `confirm` | boolean | no | Set True to execute the mutation; False (default) only returns a dry-run PLAN. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_rule_add`

MUTATION: add a new firewall rule. Dry-run by default — the PLAN shows scope, direction,
action, and key address/port fields. Re-call with confirm=True to execute. Synchronous —
confirm=True returns {"status": "ok", "result": None}; no task UPID to poll.

WARNING: a misplaced DROP/REJECT can cause a connectivity lockout. PVE always inserts the
new rule at position 0 (top), taking precedence over existing rules. No UNDO — revert by
removing it with pve_firewall_rule_remove.

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
Synchronous — confirm=True returns {"status": "ok", "result": None}; no task UPID to poll.

No UNDO: firewall config isn't in guest snapshots — revert by re-adding the rule with
pve_firewall_rule_add.

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
since the preview (positions shift and the wrong rule can be updated otherwise). Synchronous —
confirm=True returns {"status": "ok", "result": None}; no task UPID to poll.

Only the fields you pass are changed; omitted ones keep their current value. No UNDO — revert
by updating the rule back to its prior values, or remove it with pve_firewall_rule_remove.

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
name. Passive until rules are added and a rule references it (type=group). Synchronous —
confirm=True returns {"status": "ok", "result": None}; no task UPID to poll.

No UNDO: revert by deleting it with pve_firewall_security_group_delete.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `group` | string | yes | Name for the new cluster security group. |
| `comment` | string (nullable) | no | Free-text comment stored with the group. (default: `null`) |
| `confirm` | boolean | no | Set True to execute the mutation; False (default) only returns a dry-run PLAN. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_security_group_delete`

MUTATION: delete a cluster security group. Dry-run by default — the PLAN shows how many rules
the group holds. PVE refuses while the group is non-empty or still referenced by a rule.
Synchronous — confirm=True returns {"status": "ok", "result": None}; no task UPID to poll.

No UNDO: re-create it with pve_firewall_security_group_create and re-add its rules to revert.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `group` | string | yes | Name of the cluster security group to delete. |
| `confirm` | boolean | no | Set True to execute the mutation; False (default) only returns a dry-run PLAN. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_firewall_set_enabled`

MUTATION (HIGH RISK): toggle the firewall on or off for the given scope. Dry-run by default.
RISK_HIGH both directions: enabling may instantly lock you out (default-DROP, no ACCEPT for 22/8006);
disabling strips all protection. Cluster scope = master kill-switch. Synchronous — confirm=True
returns {"status": "ok", "result": None}; no task UPID to poll.

This is the focused tool for just the enable flag; for policy/log-level/ebtables options use
pve_firewall_options_set. No UNDO — re-toggle manually to revert.

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

MUTATION: create an (empty) group. Dry-run by default (additive, LOW risk); confirm=True
executes and returns a dict, synchronous with no UPID. The group is inert until users are
added (pve_user_update/pve_user_create with groups=) or pve_acl_modify grants it privileges.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `groupid` | string | yes | New group id. |
| `comment` | string (nullable) | no | Optional free-text comment. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_group_delete`

MUTATION (HIGH): delete a group. Dry-run by default — the PLAN reads members and warns ACLs
granted to/on the group are orphaned (permanent, no undo). confirm=True executes and returns a
dict; synchronous, no UPID. Use pve_group_get first to see current members.

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

MUTATION: update a group's comment. Dry-run by default (comment-only replace, LOW risk); confirm=True
executes and returns a dict, synchronous with no UPID. Does not modify group membership — use
pve_user_update (groups=) to add/remove members, or pve_group_get to see current members.

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

READ-ONLY: read a guest's current configuration (kind='lxc' or 'qemu'). Returns the
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
pve_guest_config_set). Dry-run by default; confirm=True to execute. Synchronous — returns
{reverted_to_keys, deleted, skipped_unsettable}; computed/read-only keys in prior_config are
silently skipped rather than rejected.

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
shows the exact per-key diff; confirm=True to execute. Synchronous — returns
{prior_config, applied, deleted}; prior_config is what makes the change revertible via
pve_guest_config_revert.

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
confirm=True to execute. Async — returns a task UPID; poll with pve_task_status. To drive
the same move through PDM instead, use pdm_pve_lxc_migrate or pdm_pve_qemu_migrate.

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
state, blast radius, and risk (with no-op detection) — recorded to the ledger even on a
one-shot confirm=True call (no plan, no mutation). confirm=True submits the action (async)
and returns the task UPID — poll it with pve_task_status.

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

READ-ONLY: list all HA resource groups. PVE-8 only — PVE 9 migrated groups to rules
(use pve_ha_rules_list); on PVE 9 this raises a clear ProximoError pointing there instead
of a raw 500. No state change. Returns a list of group dicts (group, nodes, restricted,
comment) on PVE 8.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_ha_resource_add`

MUTATION: add a guest to HA management. Dry-run by default — the PLAN shows the SID,
group, initial state, and blast radius (state='stopped' is HIGH: CRM will stop the guest).
confirm=True to execute. Synchronous (pmxcfs config write; CRM enforces state asynchronously) —
typically returns null, not a UPID. To remove HA management use pve_ha_resource_remove.

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
confirm=True to execute. Synchronous (pmxcfs config write) — typically returns null, not a
UPID. To re-add HA management use pve_ha_resource_add.

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
confirm=True to execute. Synchronous (pmxcfs config write, no UPID). RISK_MEDIUM — constrains
CRM placement. View rules with pve_ha_rules_list; change one with pve_ha_rule_update.

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
Synchronous (pmxcfs config write, no UPID) — no undo; re-create with pve_ha_rule_create to
revert. RISK_MEDIUM.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `rule` | string | yes | HA rule ID to delete. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_ha_rule_update`

MUTATION: update an HA rule. Dry-run by default — the PLAN shows the current rule and the
fields being changed. `delete` unsets keys. confirm=True to execute. Synchronous (pmxcfs
config write, no UPID). RISK_MEDIUM — may trigger CRM migration of affected resources.
To create a new rule use pve_ha_rule_create; to remove one use pve_ha_rule_delete.

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

READ-ONLY: list High-Availability rules on the cluster (PVE 9+).

No state change. PVE 9 replaced HA groups with rules; on PVE 8 use pve_ha_groups_list instead.
Returns a list of rule dicts. To see which guests are actually HA-managed use pve_ha_resources_list.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_hardware_list`

READ-ONLY: list physical PCI or USB devices attached to a PVE node
(hw_type: 'pci' default or 'usb').

No state change. Returns {"devices": [...]} — the node's raw hardware inventory,
distinct from the cluster-scope passthrough mappings that VMs actually reference
(pve_mapping_pci_list / pve_mapping_usb_list).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | yes | PVE node name to list physical hardware devices on |
| `hw_type` | string | no | Device class to list: 'pci' (default) or 'usb' (default: `"pci"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_ipset_list`

READ-ONLY: list IP sets for the given scope. Scope = cluster or guest only —
the PVE API has no node-scope ipsets (node firewall = options/rules/log).

No state change. Returns a list of IPSet dicts. To create/delete a set use
pve_firewall_ipset_create/pve_firewall_ipset_delete; to edit membership use
pve_firewall_ipset_entry_add/pve_firewall_ipset_entry_remove.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `scope` | string | no | Firewall scope: 'cluster' or 'guest' (no node-scope ipsets in the PVE API). (default: `"cluster"`) |
| `node` | string (nullable) | no | Node name, required for scope='guest'. (default: `null`) |
| `vmid` | string (nullable) | no | Guest VMID/CTID, required for scope='guest'. (default: `null`) |
| `kind` | string (nullable) | no | Guest kind for scope='guest': 'qemu' or 'lxc'. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_list_guests`

READ-ONLY: list all VMs and LXC containers on a node with their current state. Returns
a list of guest objects, each with VMID, name, type (lxc or qemu), and status — works across
both kinds in a single call. For one guest's runtime detail use pve_guest_status; for its
stored config use pve_guest_config_get.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name to list guests on. Omit to list guests across the whole cluster. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_mapping_pci_create`

MUTATION: create a PCI cluster passthrough mapping. Dry-run by default (returns a
PLAN); confirm=True executes and returns {"status": "ok", "result": null} (no further payload).
Additive — MEDIUM risk, since a mismatched IOMMU/VFIO map can prevent VMs from starting.
To modify an existing mapping use pve_mapping_pci_update; to remove one use
pve_mapping_pci_delete.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `mapping_id` | string | yes | Unique ID for the new PCI cluster passthrough mapping |
| `description` | string (nullable) | no | Optional free-text description stored with the mapping (default: `null`) |
| `map` | string (nullable) | no | PCI device map string(s) defining the physical device(s) covered by this mapping (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the creation (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_mapping_pci_delete`

MUTATION: delete a PCI cluster mapping. Dry-run by default (captures current config
into the PLAN); confirm=True executes and returns {"status": "ok", "result": null} (no further payload).
VMs referencing this mapping lose the device path and may fail to start. No UNDO
primitive — re-create with pve_mapping_pci_create to restore.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `mapping_id` | string | yes | ID of the PCI cluster mapping to delete |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_mapping_pci_list`

READ-ONLY: list all PCI device mappings at cluster scope.

No state change. Returns a list of dicts defining passthrough mappings for PCI devices
assignable to VMs (PCI mapping is VM-only — LXC has no PCI-passthrough config), each with
mapping ID, device list, and description. To see the
raw physical devices on a node use pve_hardware_list; to create a mapping use
pve_mapping_pci_create.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_mapping_pci_update`

MUTATION: update a PCI cluster mapping. Dry-run by default (reads current config into
the PLAN); confirm=True executes and returns {"status": "ok", "result": null} (no further payload).
MEDIUM risk — a running VM holding this mapping may need a restart to pick up the new
device path. No snapshot primitive; re-apply the captured config to revert, or use
pve_mapping_pci_delete to remove the mapping outright.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `mapping_id` | string | yes | ID of the existing PCI cluster mapping to update |
| `description` | string (nullable) | no | Optional free-text description to set on the mapping (default: `null`) |
| `map` | string (nullable) | no | PCI device map string(s) defining the physical device(s) covered by this mapping (default: `null`) |
| `digest` | string (nullable) | no | Optional config digest for optimistic-concurrency check against the current config (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the update (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_mapping_usb_create`

MUTATION: create a USB cluster passthrough mapping. Dry-run by default (returns a
PLAN); confirm=True executes and returns {"status": "ok", "result": null} (no further payload).
Additive — MEDIUM risk, since a mismatched USB device ID can prevent VMs from acquiring
the device. To modify an existing mapping use pve_mapping_usb_update; to remove one use
pve_mapping_usb_delete.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `mapping_id` | string | yes | Unique ID for the new USB cluster passthrough mapping |
| `description` | string (nullable) | no | Optional free-text description stored with the mapping (default: `null`) |
| `map` | string (nullable) | no | USB device map string(s) defining the physical device(s) covered by this mapping (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the creation (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_mapping_usb_delete`

MUTATION: delete a USB cluster mapping. Dry-run by default (captures current config
into the PLAN); confirm=True executes and returns {"status": "ok", "result": null} (no further payload).
VMs referencing this mapping lose the USB device path and may fail to start. No UNDO
primitive — re-create with pve_mapping_usb_create to restore.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `mapping_id` | string | yes | ID of the USB cluster mapping to delete |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_mapping_usb_list`

READ-ONLY: list all USB device mappings at cluster scope.

No state change. Returns a list of dicts defining passthrough mappings for USB devices
assignable to VMs/LXCs, each with mapping ID, device list, and description. To see the
raw physical devices on a node use pve_hardware_list; to create a mapping use
pve_mapping_usb_create.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_mapping_usb_update`

MUTATION: update a USB cluster mapping. Dry-run by default (reads current config into
the PLAN); confirm=True executes and returns {"status": "ok", "result": null} (no further payload).
MEDIUM risk — a running VM holding this mapping may lose USB passthrough until
restarted. No snapshot primitive; re-apply the captured config to revert, or use
pve_mapping_usb_delete to remove the mapping outright.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `mapping_id` | string | yes | ID of the existing USB cluster mapping to update |
| `description` | string (nullable) | no | Optional free-text description to set on the mapping (default: `null`) |
| `map` | string (nullable) | no | USB device map string(s) defining the physical device(s) covered by this mapping (default: `null`) |
| `digest` | string (nullable) | no | Optional config digest for optimistic-concurrency check against the current config (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the update (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_metrics_server_delete`

MUTATION: delete a PVE metrics server definition. Dry-run by default. confirm=True
executes and returns {"status": "ok", "result": null} (no further payload). Metrics forwarding to this
server ceases; no data loss, and config is re-creatable with pve_metrics_server_set.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `metrics_id` | string | yes | ID of the metrics server definition to delete |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_metrics_server_list`

READ-ONLY: list all PVE metrics server definitions.

No state change. Returns a list of dicts for each configured metrics forwarding target
(InfluxDB, Graphite, etc.), with id, type, server address, and port. To create or update
one use pve_metrics_server_set; to remove one use pve_metrics_server_delete.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_metrics_server_set`

MUTATION: create-or-update a PVE metrics server definition. Dry-run by default
(returns a PLAN); confirm=True executes and returns {"status": "ok", "result": null} (no further
payload). Config-only — metrics forwarding adjusts to the new settings immediately; no
snapshot primitive, so re-apply this same tool to revert. To remove it use
pve_metrics_server_delete.

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

Stage changes first with pve_network_iface_create / pve_network_iface_update — this applies
whatever is currently staged; for SDN changes use pve_sdn_apply instead (a separate,
cluster-scoped commit). Dry-run by default — the PLAN surfaces pending interfaces. confirm=True
executes with no automatic undo; a misconfigured interface can lose SSH/API access, requiring
console/physical access to recover. May return a UPID (async) or None (sync) — outcome='submitted'
in either case.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | Node to apply staged network config on; defaults to the configured node. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True applies the staged config to the live network stack. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_network_iface_create`

MUTATION: create a new network interface config (staged — not live until pve_network_apply).

`options` carries type-dependent fields (address, netmask, gateway, bridge_ports, …). To
update an existing interface instead use pve_network_iface_update. Dry-run by default (returns
a PLAN); confirm=True stages the interface, synchronously, and returns {status, result} —
result is often None. RISK_MEDIUM (staged change, reversible before apply).

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

`options` carries fields to update (address, netmask, bridge_ports, …); the interface's type
is preserved automatically and cannot be changed here — recreate via pve_network_iface_create
for a type change. Dry-run by default (returns a PLAN); confirm=True stages the update and
returns {status, result} — result is often None. RISK_MEDIUM (staged change, reversible before apply).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `iface` | string | yes | Existing interface name to update, e.g. vmbr1 or eth0.100. |
| `node` | string (nullable) | no | Node the interface lives on; defaults to the configured node. (default: `null`) |
| `options` | object (nullable) | no | Fields to update: address, netmask, bridge_ports, etc. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True stages the update (still not live until pve_network_apply). (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_network_list`

READ-ONLY: list network interfaces (bridges/bonds/VLANs/etc) on a PVE node.

No state change. Returns a list of dicts with iface name, type (bridge/bond/vlan/eth/alias),
method, and address; filter by type with iface_type. For SDN zones/vnets use
pve_sdn_zones_list / pve_sdn_vnets_list instead — that's a separate, cluster-scoped layer.

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
executes and returns {"status": "ok"}; the default returns a dry-run PLAN dict. Smoke-confirm:
node-config body shape against a live PVE instance.

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

RISK_MEDIUM: PVE reverts to its self-signed certificate — recoverable by re-uploading via
pve_node_cert_upload (to view current certs first use pve_node_certificates). restart=True
reloads pveproxy after deletion. Dry-run by default (returns a PLAN); confirm=True executes
(DELETE, Smoke-confirm) and returns {"status": "ok", "result": None}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name to delete the custom certificate from; defaults to the configured node if omitted. (default: `null`) |
| `restart` | boolean | no | If True, reload pveproxy after deletion to apply the reverted self-signed certificate immediately. (default: `false`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_cert_upload`

MUTATION: upload a custom TLS certificate to a PVE node.

RISK_HIGH, NO UNDO. A malformed cert/key can lock you out of the PVE web UI and API.
restart=True reloads pveproxy after upload (brief service interruption). To view the
node's currently configured certs use pve_node_certificates.

PRIVATE KEY REDACTION: the 'key' param is a TLS private key (secret). It is
UNCONDITIONALLY redacted — it NEVER appears in the plan, change, current state,
detail, or ledger (regardless of redact_ledger setting). Only {"key": "[redacted]"}
is recorded. The cert body (certificates) is public and may appear in plans/logs.

Revert: re-upload a correct cert, or use pve_node_cert_delete to revert to self-signed.
Dry-run by default (returns a PLAN); confirm=True executes (POST, Smoke-confirm) and
returns {"status": "ok", "result": <dict | None>}.

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

READ-ONLY: list TLS certificates configured on a Proxmox node.

No state change. Returns a list of certificate dicts with filename, subject, issuer,
validity dates (notbefore/notafter), SANs, and fingerprint. To add or replace a
certificate use pve_node_cert_upload; to remove one use pve_node_cert_delete.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name; defaults to the configured node (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_disk_initgpt`

MUTATION: initialize a GPT partition table on a node disk.

RISK_HIGH: overwrites the existing partition table on the named disk; irreversible —
less destructive than pve_node_disk_wipe, which also erases the underlying data.
Dry-run by default (returns a PLAN); confirm=True executes (POST /disks/initgpt,
Smoke-confirm) and returns {"status": "submitted", "result": <task UPID | None>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `disk` | string | yes | Device path/identifier of the disk to initialize with a new GPT partition table (e.g. /dev/sda); overwrites the existing partition table. |
| `node` | string (nullable) | no | PVE node name the disk lives on; defaults to the configured node if omitted. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the irreversible GPT init. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_disk_smart`

READ-ONLY: get SMART health data for one disk on a PVE node.

GET /nodes/{node}/disks/smart?disk=…. VERIFIED live (PVE 9.2): returns a dict
(health, type, text/attributes). This GET form does NOT trigger a self-test.
To list all disks first use pve_node_disks_list.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `disk` | string | yes | Device path/identifier of the disk to query (e.g. /dev/sda), as listed by pve_node_disks_list. |
| `node` | string (nullable) | no | PVE node name the disk lives on; defaults to the configured node if omitted. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_disk_wipe`

MUTATION: wipe ALL data and the partition table on a node disk.

RISK_HIGH, NO UNDO: DESTROYS all data, partitions, and filesystems on the named disk —
more destructive than pve_node_disk_initgpt, which only overwrites the partition table.
Dry-run by default (returns a PLAN); confirm=True executes (PUT /disks/wipedisk,
Smoke-confirm) and returns {"status": "submitted", "result": <task UPID | None>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `disk` | string | yes | Device path/identifier of the disk to wipe (e.g. /dev/sda); ALL data and the partition table are destroyed. |
| `node` | string (nullable) | no | PVE node name the disk lives on; defaults to the configured node if omitted. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the irreversible wipe. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_disks_list`

READ-ONLY: list physical disks on a PVE node.

GET /nodes/{node}/disks/list. VERIFIED live (PVE 9.2): returns a list of dicts
(devpath/health/size/model/serial/used). For one disk's SMART detail use
pve_node_disk_smart.

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
mode as node hosts_set). CAPTURE: reads current DNS config before planning (also readable
directly via pve_node_dns); if unreadable → complete=False. Dry-run by default (returns a
PLAN); confirm=True executes (PUT, Smoke-confirm) and returns {"status": "ok", "result": None}.

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

READ-ONLY: get the /etc/hosts content of a PVE node.

GET /nodes/{node}/hosts. VERIFIED live (PVE 9.2): returns a dict {data, digest} —
digest is used for optimistic-concurrency on a follow-up pve_node_hosts_set.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name to query; defaults to the configured node if omitted. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_hosts_set`

MUTATION: replace the /etc/hosts file on a PVE node.

RISK_MEDIUM. CAPTURE: reads current /etc/hosts before planning (also readable directly via
pve_node_hosts_get; revert by re-applying captured content); if unreadable → complete=False.
A bad /etc/hosts can break name resolution. Dry-run by default (returns a PLAN); confirm=True
executes (POST, Smoke-confirm) and returns {"status": "ok", "result": None}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `data` | string | yes | Full replacement content for the node's /etc/hosts file. |
| `node` | string (nullable) | no | PVE node name to configure; defaults to the configured node if omitted. (default: `null`) |
| `digest` | string (nullable) | no | Expected content digest of the current /etc/hosts, for optimistic-concurrency conflict detection. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the replacement. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_journal`

READ-ONLY: fetch systemd journal lines from a PVE node for log inspection.

No state change. Returns a list of journal-line strings. Narrow with since/until (timestamp
format per PVE — typically epoch seconds or ISO 8601) and lastentries (most-recent N, max 5000;
higher is rejected with an error). For the classic syslog view
use pve_node_syslog; for one service's current state use pve_node_service_status.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name; defaults to the configured node (default: `null`) |
| `lastentries` | integer | no | Number of most-recent journal lines to return, max 5000 (values above are rejected) (default: `100`) |
| `since` | string (nullable) | no | Only return entries at or after this timestamp (journalctl-compatible format) (default: `null`) |
| `until` | string (nullable) | no | Only return entries at or before this timestamp (journalctl-compatible format) (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_migrateall`

MUTATION: migrate all (or filtered) guests from a node to a target node.

RISK_HIGH, NOT auto-reversible: reversal requires a second pve_node_migrateall back,
which may not restore the original state. target = destination node name (required).
For a single guest instead of the whole node use pve_guest_migrate. Dry-run by default
(returns a PLAN); confirm=True executes (POST, Smoke-confirm) and returns
{"status": "submitted", "result": <task UPID | None>} — poll with pve_task_status.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `target` | string | yes | Destination PVE node name to migrate guests to. |
| `node` | string (nullable) | no | Source PVE node name whose guests to migrate; defaults to the configured node if omitted. (default: `null`) |
| `vms` | string (nullable) | no | Optional comma-separated list of VMIDs/CTIDs to limit the scope; omit to migrate all guests on the node. (default: `null`) |
| `maxworkers` | integer (nullable) | no | Maximum number of parallel migration workers to run. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the bulk migration. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_rrddata`

READ-ONLY: fetch RRD (round-robin database) time-series telemetry for a PVE node.

No state change. Returns a list of data-point dicts with timestamps and per-metric values
(the exact metric keys vary by PVE version) over the specified timeframe, optionally aggregated by
consolidation function (AVERAGE or MAX). Node-level only, not per-guest.

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
NO auto-undo for a service control. confirm=True executes and returns
{"status": "submitted", "result": <UPID>} — poll that UPID with pve_task_status. Check
current state first with pve_node_service_status.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `service` | string | yes | systemd service name to control, e.g. 'pveproxy' or 'sshd' |
| `action` | string | yes | Control action: 'start', 'stop', 'restart', or 'reload' |
| `node` | string (nullable) | no | PVE node name; defaults to the configured node (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the service control (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_service_status`

READ-ONLY: get one systemd service's current state on a PVE node (e.g. pveproxy, sshd).

No state change. Returns a dict with the service's name, state (running/dead/inactive) and
description. To list every service use pve_node_services_list; to *change* a service's run state
use pve_node_service_control.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `service` | string | yes | systemd service name, e.g. 'pveproxy' or 'sshd' |
| `node` | string (nullable) | no | PVE node name; defaults to the configured node (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_services_list`

READ-ONLY: list all services on a PVE node.

No state change. Returns a list of service dicts with name, state (running/dead/
inactive), and description for each service. For one service's current state use
pve_node_service_status; to change a service's run state use pve_node_service_control.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name; defaults to the configured node (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_startall`

MUTATION: start all (or filtered) guests on a PVE node.

RISK_MEDIUM. Reversible — the inverse of pve_node_stopall. For a single guest instead of
the whole node use pve_guest_power. vms = optional CSV of VMIDs to filter the scope.
Dry-run by default (returns a PLAN); confirm=True executes (POST, Smoke-confirm on the
vms param format) and returns {"status": "submitted", "result": <task UPID | None>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name whose guests to start; defaults to the configured node if omitted. (default: `null`) |
| `vms` | string (nullable) | no | Optional comma-separated list of VMIDs/CTIDs to limit the scope; omit to start all guests on the node. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the bulk start. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_status`

READ-ONLY: read Proxmox node health and resource status. Returns node metrics including
total capacity, current usage, CPU, memory, disk state, and operational status. See pve_diagnose
for detailed per-node diagnostics including failed tasks.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name to query. Omit to use the configured default node. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_stopall`

MUTATION: stop ALL (or filtered) running guests on a PVE node.

RISK_HIGH — fleet-wide service outage unless vms filters the scope. For a single guest
instead of the whole node use pve_guest_power. Reversible via pve_node_startall, but
guests must be restarted inside. Dry-run by default (returns a PLAN); confirm=True
executes (POST, Smoke-confirm on the vms param format) and returns
{"status": "submitted", "result": <task UPID | None>}.

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

RISK_HIGH: FORMATS the named disk(s) immediately — any pre-existing data is destroyed,
irreversibly. To see what already exists use pve_node_storage_backend_list; to remove
one use pve_node_storage_backend_delete. Dry-run by default (returns a PLAN);
confirm=True executes (POST, Smoke-confirm) and returns
{"status": "submitted", "result": <task UPID | None>}.

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

To create one instead use pve_node_storage_backend_create; to see what exists first
use pve_node_storage_backend_list. Dry-run by default (returns a PLAN); confirm=True
executes (DELETE, Smoke-confirm) and returns
{"status": "submitted", "result": <task UPID | None>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `backend` | string | yes | Storage backend type to destroy: one of lvm, lvmthin, zfs, directory. |
| `name` | string | yes | Name of the storage backend to destroy. |
| `node` | string (nullable) | no | PVE node name the backend lives on; defaults to the configured node if omitted. (default: `null`) |
| `cleanup` | boolean | no | If True, also removes the underlying disk data/partitions during backend removal. (default: `false`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the irreversible destroy. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_storage_backend_list`

READ-ONLY: list storage backends of a type on a PVE node.

backend ∈ {lvm, lvmthin, zfs, directory}. GET /nodes/{node}/disks/{backend}.
VERIFIED live (PVE 9.2): lvm returns a VG-tree dict; lvmthin/zfs/directory return a
list. To create or destroy a backend use pve_node_storage_backend_create /
pve_node_storage_backend_delete.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `backend` | string | yes | Storage backend type to list: one of lvm, lvmthin, zfs, directory. |
| `node` | string (nullable) | no | PVE node name to query; defaults to the configured node if omitted. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_subscription`

READ-ONLY: read a Proxmox node's subscription status.

No state change. Returns a dict with status, product name, check time, next due
date, and subscription level.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name; defaults to the configured node (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_syslog`

READ-ONLY: fetch syslog entries from a PVE node for log inspection.

No state change. Returns a list of entry dicts, up to `limit` (max 5000; higher is rejected with an error).
For the systemd journal (with since/until filtering) use pve_node_journal instead.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name; defaults to the configured node (default: `null`) |
| `limit` | integer | no | Maximum number of syslog entries to return, max 5000 (values above are rejected) (default: `100`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_time_get`

READ-ONLY: get the current time and timezone of a PVE node.

GET /nodes/{node}/time. VERIFIED live (PVE 9.2): returns a dict
{localtime, time, timezone}. To change the timezone use pve_node_time_set.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PVE node name to query; defaults to the configured node if omitted. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_node_time_set`

MUTATION: set the timezone on a PVE node.

RISK_LOW. CAPTURE: reads the current timezone before planning (also readable directly via
pve_node_time_get); if unreadable → complete=False. Revert by re-applying the captured
timezone. Dry-run by default (returns a PLAN); confirm=True executes (PUT, Smoke-confirm)
and returns {"status": "ok", "result": None}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `timezone` | string | yes | IANA timezone name to set on the node (e.g. America/Chicago, UTC). |
| `node` | string (nullable) | no | PVE node name to configure; defaults to the configured node if omitted. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the timezone change. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_notification_endpoint_create`

MUTATION: create a PVE notification endpoint. ep_type = gotify|smtp|sendmail|webhook.
`options` carries the endpoint-specific config (sendmail: {"mailto-user":"root@pam"};
gotify: {"server":..,"token":..}; webhook: {"url":..}). Additive, low risk. Dry-run by
default (returns a PLAN); confirm=True executes and returns {"status": "ok", "result": null} (no further
payload). To modify an existing endpoint instead use pve_notification_endpoint_update.

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
Dry-run by default — captures current config. confirm=True executes and returns
{"status": "ok", "result": null} (no further payload). No UNDO primitive — matchers referencing this
endpoint silently fail until it is re-created with pve_notification_endpoint_create.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ep_type` | string | yes | Notification endpoint type: 'gotify', 'smtp', 'sendmail', or 'webhook' |
| `name` | string | yes | Name of the notification endpoint to delete |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_notification_endpoint_list`

READ-ONLY: list all PVE notification endpoints.

No state change. Returns a list of dicts for each configured delivery channel (gotify,
smtp, sendmail, webhook) with type, name, and endpoint-specific config. To add one use
pve_notification_endpoint_create; to remove one use pve_notification_endpoint_delete.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_notification_endpoint_update`

MUTATION: update a PVE notification endpoint. ep_type = gotify|smtp|sendmail|webhook.
`options` carries the endpoint-specific fields to change (same shape as create). Dry-run
by default — captures current config into the PLAN; confirm=True executes and returns
{"status": "ok", "result": null} (no further payload). No snapshot primitive; re-apply the captured
config to revert, or use pve_notification_endpoint_create to make a new one instead.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ep_type` | string | yes | Notification endpoint type: 'gotify', 'smtp', 'sendmail', or 'webhook' |
| `name` | string | yes | Name of the existing notification endpoint to update |
| `comment` | string (nullable) | no | Optional free-text comment to set on the endpoint (default: `null`) |
| `options` | object (nullable) | no | Endpoint-specific fields to change, same shape as create (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the update (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_notification_matcher_delete`

MUTATION: delete a PVE notification matcher. Dry-run by default. confirm=True
executes and returns {"status": "ok", "result": null} (no further payload). No UNDO primitive — alerts
matching this filter go un-routed until re-created with pve_notification_matcher_set.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the notification matcher to delete |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_notification_matcher_set`

MUTATION: create-or-update a PVE notification matcher (alert routing rule). Dry-run
by default (returns a PLAN); confirm=True executes and returns {"status": "ok", "result": null} (no
further payload). No snapshot primitive — re-apply with this same tool to restore after
deletion. To remove a matcher use pve_notification_matcher_delete.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the notification matcher (alert routing rule) to create or update |
| `comment` | string (nullable) | no | Optional free-text comment stored with the matcher (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the create/update (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_notification_test`

MUTATION: send a test notification to a PVE notification target. Dry-run by default
(returns a PLAN, nothing is sent); confirm=True SENDS A REAL NOTIFICATION to the target's
recipients and returns {"status": "ok", "result": null}. No config changes. `name` is an existing
endpoint or matcher name — see pve_notification_endpoint_list for endpoint names.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the notification target to send a test notification to |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True sends a real test notification (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_overbroad_grants`

READ-ONLY: surface over-broad ACL grants — Administrator-role assignments or grants on the
root '/' path — as a least-privilege diagnostic.

No state change; this only reports, it does not revoke anything. Returns a list of the flagged ACL
entries (empty when none). Use pve_acl_list for the full ACL and pve_acl_modify to tighten a finding.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_pool_create`

MUTATION: create an (empty) resource pool. Dry-run by default (PLAN = additive, LOW).
confirm=True to execute. Synchronous — typically returns null, no members yet; add
guests/storage with pve_pool_update.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `poolid` | string | yes | New pool ID to create. |
| `comment` | string (nullable) | no | Free-text comment stored with the pool. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the creation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_pool_delete`

MUTATION: delete a resource pool. Dry-run by default — the PLAN warns ACLs on /pool/{poolid}
are orphaned and the pool must be empty first (members are NOT deleted; empty it first with
pve_pool_update). confirm=True to execute. Synchronous — returns null.

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
the PLAN notes membership re-scopes ACL coverage. confirm=True to execute. Synchronous, no
UPID. delete=True with no vms/storage is refused (ambiguous). To remove the pool itself use
pve_pool_delete.

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

MUTATION: create an auth realm. Dry-run by default; confirm=True executes and returns a
dict, synchronous with no UPID. `options` carries the type-specific fields PVE requires (ldap:
server1/base_dn/user_attr; ad: domain/server1; openid: issuer-url/client-id) — passed verbatim;
PVE validates them. Use pve_realms_list to see configured realms first.

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
users to count who can no longer log in, and refuses built-in pam/pve (permanent, no undo).
confirm=True executes and returns a dict; synchronous, no UPID. Use pve_users_list to see who
authenticates through the realm first.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes | Realm id to delete (built-in 'pam'/'pve' are refused). |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_realm_get`

Get a realm's full config (read-only). Returns realm type, comment, TFA requirement, and
type-specific settings (server1/base_dn for ldap; domain/server1 for ad; issuer-url/client-id
for openid). Use pve_realm_create/update/delete to manage realms.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes | Realm id to look up, e.g. 'pam', 'pve', or a configured ldap/ad/openid realm name. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_realm_update`

MUTATION: update a realm. Dry-run by default — built-in pam/pve realms are flagged HIGH
(changing them risks breaking logins). confirm=True executes and returns a dict; synchronous,
no UPID. `options` carries type-specific fields (server1/base_dn/etc.) passed verbatim; PVE
validates them. Use pve_realm_get to see current config first.

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

MUTATION: create a PVE replication job. Dry-run by default; confirm=True to execute and
returns synchronously (no task UPID) — additive, no existing data affected. rep_type is
typically 'local'. To modify an existing job use pve_replication_update; to remove one use
pve_replication_delete.

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

MUTATION: delete a PVE replication job. Dry-run by default — the PLAN captures current
config (no UNDO primitive on this plane; re-create with pve_replication_create to restore).
confirm=True to execute and returns synchronously (no task UPID). Replication ceases; existing
replicated data on the target is NOT removed.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `rep_id` | string | yes | ID of the replication job to delete. |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_replication_update`

MUTATION: update a PVE replication job. Dry-run by default — the PLAN captures current
config for manual revert; confirm=True to execute and returns synchronously (no task UPID).
Config-only; in-flight replication is not immediately disrupted. To create a new job use
pve_replication_create; to remove one use pve_replication_delete.

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
archive. Dry-run by default — the PLAN reads live guest state and states whether it CREATES or
OVERWRITES. confirm=True to execute. Async — returns a task UPID. Find the archive's volid
first with pve_backup_list.

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
risk — inert until an ACL entry references it). confirm=True executes and returns a dict,
synchronous with no UPID. privs format: comma-separated privilege names (e.g.
'VM.PowerMgmt,VM.Config.Disk'). Use pve_acl_modify to assign the new role to a principal.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `roleid` | string | yes | New role id. |
| `privs` | string (nullable) | no | Comma-separated privilege names for the role, e.g. 'VM.PowerMgmt,VM.Config.Disk'. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_role_delete`

MUTATION (HIGH): delete a role. Dry-run by default — the PLAN reads ACLs to count grants
that will break, and refuses built-in roles (permanent, no undo). confirm=True executes and
returns a dict; synchronous, no UPID. Use pve_acl_list to see which grants reference the role first.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `roleid` | string | yes | Role id to delete (built-in roles are refused). |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_role_update`

MUTATION: change a role's privileges. Dry-run by default — built-in roles (Administrator,
PVEAdmin, …) are flagged HIGH (changing them re-scopes every ACL using them). confirm=True
executes and returns a dict; synchronous, no UPID. Use pve_roles_list to see current roles
and privileges first.

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
Dry-run by default (the PLAN spells out the blast radius); confirm=True to execute. Async —
returns the task UPID, poll with pve_task_status. To create a restore point first use
pve_snapshot_create.

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

Stage zones/vnets/subnets first with pve_sdn_zone_create / pve_sdn_vnet_create /
pve_sdn_subnet_create — this applies whatever is pending; for interface/bridge changes use
pve_network_apply instead. Dry-run by default — the PLAN surfaces pending zones/vnets.
confirm=True executes with no automatic undo, disrupting virtual networking for ALL guests
cluster-wide if misconfigured. May return a UPID (async) or None (sync) — outcome='submitted'
in either case.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True applies pending SDN config cluster-wide. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_subnet_create`

MUTATION: create an SDN subnet (PENDING). `subnet` is a CIDR (e.g. 10.0.0.0/24); `options`
carries gateway/snat/dhcp params.

To update this subnet use pve_sdn_subnet_update; to remove it use pve_sdn_subnet_delete.
Dry-run by default (returns a PLAN); confirm=True creates the pending subnet and returns
{status, result}. RISK_LOW (staging; inert until apply).

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

To create a subnet instead use pve_sdn_subnet_create. Dry-run by default (returns a PLAN);
confirm=True stages the removal and returns {status, result}; no config UNDO — re-create the
subnet to revert. RISK_MEDIUM (staging a removal an apply would enact).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vnet` | string | yes | SDN vnet name the subnet belongs to. |
| `subnet` | string | yes | Subnet id (CIDR) from pve_sdn_subnet_list to delete. |
| `lock_token` | string (nullable) | no | SDN cluster lock token to use for this write, if one is held. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the staged mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_subnet_list`

READ-ONLY: list the subnets configured in a vnet. Returns a list of subnet dicts
(the exact field set is not guaranteed by this endpoint). Use pve_sdn_subnet_create to
add one and pve_sdn_apply to commit.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vnet` | string | yes | SDN vnet name whose subnets to list. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_subnet_update`

MUTATION: update an SDN subnet (PENDING). `subnet` is the id from pve_sdn_subnet_list.

To create a subnet use pve_sdn_subnet_create; to remove one use pve_sdn_subnet_delete. Dry-run
by default (returns a PLAN); confirm=True stages the edit and returns {status, result}.
RISK_LOW (staging).

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

To update an existing vnet use pve_sdn_vnet_update; to remove one use pve_sdn_vnet_delete.
Dry-run by default (returns a PLAN); confirm=True creates the pending vnet and returns
{status, result}. RISK_LOW (staging; inert until pve_sdn_apply).

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

To create a vnet instead use pve_sdn_vnet_create. PVE refuses if a subnet still references it.
confirm=True stages the removal and returns {status, result}; no config UNDO — re-create the
vnet to revert. RISK_MEDIUM.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `vnet` | string | yes | Existing SDN vnet name to delete. |
| `lock_token` | string (nullable) | no | SDN cluster lock token to use for this write, if one is held. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the staged mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_vnet_update`

MUTATION: update an SDN vnet (PENDING — inert until pve_sdn_apply).

`options` sets fields (tag/alias/vlanaware/etc), `delete` removes keys. To create a vnet use
pve_sdn_vnet_create; to remove one use pve_sdn_vnet_delete. Dry-run by default (returns a
PLAN); confirm=True stages the edit and returns {status, result}. RISK_LOW (staging, no live
network effect).

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

`zone_type` is simple/vlan/qinq/vxlan/evpn/faucet; `options` carries type-specific params. To
update an existing zone use pve_sdn_zone_update; to remove one use pve_sdn_zone_delete. Dry-run
by default (returns a PLAN); confirm=True creates the pending zone, returning {status, result}.
RISK_LOW (staging, no live network effect).

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

To create a zone instead use pve_sdn_zone_create. PVE refuses if a vnet still references it.
confirm=True stages the removal and returns {status, result}; no config UNDO — re-create the
zone to revert. RISK_MEDIUM (staging a removal an apply would enact).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `zone` | string | yes | Existing SDN zone id to delete. |
| `lock_token` | string (nullable) | no | SDN cluster lock token to use for this write, if one is held. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the staged mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_sdn_zone_update`

MUTATION: update an SDN zone (PENDING). `options` sets fields; `delete` unsets keys.

To create a new zone use pve_sdn_zone_create; to remove one use pve_sdn_zone_delete. Dry-run
by default (returns a PLAN); confirm=True stages the edit and returns {status, result}.
RISK_LOW (staging; inert until pve_sdn_apply).

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

Returns each group's id (keyed `group`), comment, and digest. A security group is a reusable
named rule set you attach to a VM/node firewall; use pve_firewall_rules_list to read
a specific scope's active rules.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_snapshot_create`

MUTATION: create a snapshot (a restore point). Dry-run by default; confirm=True to execute.
Async — returns the task UPID; poll pve_task_status. Needs snapshot-capable storage (ZFS/BTRFS/LVM-thin).
To restore to a snapshot use pve_rollback; to remove one use pve_snapshot_delete; to list them
use pve_snapshot_list.

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

MUTATION: delete a snapshot (removes a restore point) — you can't roll back to it afterward.
Dry-run by default; confirm=True to execute. Async — returns the task UPID, poll with
pve_task_status. To create a snapshot instead of removing one use pve_snapshot_create.

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

READ-ONLY: list all storage definitions from storage.cfg cluster-wide. No state change.
Returns a list of storage dicts with IDs, types, paths, and server addresses. Use
pve_storage_config_get to fetch a single storage's complete configuration.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_storage_content`

READ-ONLY: list the volumes a storage holds — ISO images, container templates, backups, disks.

No state change. Optionally filter by content type (iso | vztmpl | backup); omit to list all.
Returns a list of volume dicts (volid, size, content type, …); use it to find a volid to pass to
restore/clone tools. To *define* a new storage use pve_storage_create.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes | Storage backend name to list content from. |
| `node` | string (nullable) | no | PVE node hosting the storage. Omit to use the configured default node. (default: `null`) |
| `content` | string (nullable) | no | Filter by content type: `iso`, `vztmpl`, or `backup`. Omit to list all content. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_storage_content_delete`

MUTATION: delete a content volume (ISO / template / backup / disk image) from storage.
Dry-run by default — escalates to HIGH risk for a backup volume or a disk still attached to a
guest; confirm=True to execute. Async — returns a UPID or null. Use pve_storage_content to
find a volid first.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes | Storage backend name the content volume lives on. |
| `volid` | string | yes | Volume ID of the content to delete (ISO, template, or backup), e.g. `local:vztmpl/debian-12.tar.zst`. |
| `node` | string (nullable) | no | PVE node hosting the storage. Omit to use the configured default node. (default: `null`) |
| `confirm` | boolean | no | Leave `false` (default) to get a dry-run PLAN — HIGH risk for a backup volume; set `true` to execute the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_storage_create`

MUTATION: define a new cluster storage entry in storage.cfg (dir / nfs / pbs / cifs / …).

This registers a storage *definition* the cluster can use; it does NOT format disks or provision
a backend — to create a disk-backed backend (lvm/zfs/directory) on a node use
pve_node_storage_backend_create. Required params depend on storage_type (dir needs `path`; nfs
needs `server`+`export`). MEDIUM risk — a bad definition can fail to mount and slow cluster
storage enumeration; no existing data is touched. Dry-run by default (returns a PLAN);
confirm=True writes storage.cfg (the confirm result payload is typically null).

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
warns guest disks/backups living only there become inaccessible (data not erased). confirm=True
executes — typically returns null; no undo except re-adding via pve_storage_create with the
same config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `storage` | string | yes | Storage ID to remove cluster-wide (definition only; data on disk is not erased). |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_storage_download`

MUTATION: download an ISO (content=iso) or CT template (content=vztmpl) from a URL into a
storage. Dry-run by default; confirm=True. Async — returns a UPID (poll with pve_task_status).
The URL and its content are operator-trusted — Proximo does not verify or sandbox what it
fetches. Use pve_storage_content to see what's already on a storage.

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
disk access cluster-wide; a `nodes` change strands guests on excluded nodes). confirm=True to
execute (synchronous, no UPID). The storage type itself can't be changed here — use
pve_storage_delete then pve_storage_create instead.

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

READ-ONLY: get an async Proxmox task's status by its UPID — running vs stopped, plus the
exit status once it has finished.

No state change. Use it to poll long-running ops (migrate, snapshot, rollback, backup) that
return a UPID. Returns a dict with `status` and `exitstatus`. To block until the task completes
use pve_task_wait, and for its log output use pve_task_log. Pass `node` for a task on a
non-default node; omitting it falls back to the configured default node (the UPID is not parsed for the node).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `upid` | string | yes | Proxmox task UPID (unique process ID) returned by an async operation. |
| `node` | string (nullable) | no | PVE node the task is running on. Omit to resolve it automatically. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_task_stop`

MUTATION (HIGH): stop (cancel) a running task. Dry-run by default — the PLAN warns that
stopping a backup/restore/migration/clone mid-flight can leave the target inconsistent, with
NO undo. confirm=True to execute. Synchronous cancellation signal (returns null, not a UPID) —
the task may run briefly before it sees the signal. Find UPIDs to stop via pve_tasks_list.

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

READ-ONLY: list recent tasks on a node. limit max 1000 (higher is truncated; 0 or negative
is rejected). No state change; returns a list of task dicts. Use pve_task_log for a task's full log.

Caveat: this is a windowed, per-node slice — node defaults to the configured node, and
only the `limit` most-recent tasks return. A task on another node or outside the window
is absent without being dead. Never conclude a backup failed from absence here — verify
against pve_backup_list or pbs_snapshots_list.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | Node to list tasks from; defaults to the configured node. (default: `null`) |
| `limit` | integer | no | Max number of most-recent tasks to return, max 1000 (0 or negative is rejected). (default: `50`) |
| `errors` | boolean | no | If True, only return tasks that ended in error. (default: `false`) |
| `vmid` | string (nullable) | no | Optional VMID/CTID to filter tasks to a single guest. (default: `null`) |
| `typefilter` | string (nullable) | no | Optional task-type filter, e.g. 'vzdump', 'qmigrate' (PVE task type string). (default: `null`) |
| `statusfilter` | string (nullable) | no | Optional status filter, e.g. 'running', 'stopped'. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_template_convert`

MUTATION (IRREVERSIBLE): convert a guest into a template — effectively one-way; kind='lxc'
is refused (this endpoint is QEMU-only — LXC uses a separate, out-of-scope template endpoint).
Dry-run by default (the PLAN flags it HIGH/irreversible, and separately warns if the guest is
already a template); confirm=True executes, recorded as submitted (async).

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
logged. confirm=True executes and returns a dict; no UNDO (the factor must be re-enrolled).

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

List all per-user TFA (two-factor) entries across the cluster (read-only). Returns the
configured TFA entries; the exact shape varies by PVE version (typically per-user with a
nested `entries` list of factor type/id). Use pve_tfa_get
for one user's entries; use pve_tfa_delete (confirm=True) to remove a factor (RISK_HIGH).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_token_create`

MUTATION: create an API token for a user.

Dry-run by default — the PLAN shows risk (privsep=False is HIGH: token inherits ALL owner perms).
confirm=True executes and returns a dict whose result carries the token secret (value) ONCE —
it is never written to the audit ledger and cannot be retrieved again. Synchronous. Use
pve_tokens_list to see a user's existing tokens, or pve_token_revoke to remove one.

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
confirm=True executes and returns a dict; synchronous, no UPID. Use pve_tokens_list to see a
user's tokens first, or pve_token_create to issue a new one instead.

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
cannot log in until then). confirm=True executes and returns a dict; synchronous, no UPID.
Use pve_user_update to change it afterward, or pve_user_delete to remove it.

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
to show what access vanishes (permanent, no undo; admin = lockout risk). confirm=True executes
and returns a dict; synchronous, no UPID. To disable login without deleting, use
pve_user_update (enable=False) instead.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | User id to delete, format 'user@realm'. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_user_get`

Get a user's full config (read-only). Returns userid, enabled flag, expiry, email, comment,
group membership, API tokens, and firstname/lastname. Use pve_user_create/update/delete to
modify the user; use pve_acl_list to see the cluster's raw ACL entries (not a resolved
per-user effective-permission view).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | User id to look up, format 'user@realm'. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pve_user_update`

MUTATION: update a user (enable=False stops login; group changes re-scope access).
Dry-run by default. confirm=True executes and returns a dict; synchronous, no UPID. Use
pve_user_get to see current state first, or pve_user_delete to remove the user instead.

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

#### `pbs_acl_get`

READ-ONLY: list PBS ACL entries. Returns each entry's path, roleid, ugid (the
user/token/group id), ugid_type ('user' or 'group'), and propagate flag. Use pbs_acl_update
to grant/revoke, or pbs_roles_list to see PBS's fixed set of built-in roles. Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `path` | string (nullable) | no | ACL path to filter by; omit to return every entry on the server. (default: `null`) |
| `exact` | boolean (nullable) | no | If True (with path set), return only entries at the exact path, not the subtree. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_acl_update`

MUTATION (HIGH): grant or revoke a PBS ACL entry (PUT /access/acl) — this GRANTS or
REVOKES AUTHORITY, so it is treated as HIGH risk unconditionally on this plane (PBS's
ACL-inheritance/shadow semantics are not schema-documented or live-verified here, unlike
PVE's plan_acl_modify which computes a shadow/widen preview — every change here is flagged
HIGH rather than risk under-flagging one this module cannot yet analyze).

Dry-run by default (reads the current entries at this exact path for context). Exactly one
of auth_id (a user or token principal) / group is required — PBS's PUT /access/acl carries
a single 'role' (not PVE's comma-separated multi-role list) and folds user+token identity
into one 'auth-id' field. delete=False = grant; delete=True = revoke. confirm=True executes
and returns a dict; synchronous, no UPID. Use pbs_acl_get to see current entries or
pbs_roles_list to see PBS's fixed set of built-in roles. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `path` | string | yes | ACL path the entry applies to, e.g. '/datastore/ds1' or '/'. |
| `role` | string | yes | A single PBS role id to grant or revoke, e.g. 'DatastoreAdmin'. |
| `auth_id` | string (nullable) | no | User or token principal ('user@realm' or 'user@realm!token-name'). Exactly one of auth_id/group is required. (default: `null`) |
| `group` | string (nullable) | no | Group principal. Exactly one of auth_id/group is required. (default: `null`) |
| `propagate` | boolean (nullable) | no | Whether the grant propagates to child paths below `path`; omit for PBS's default (true). (default: `null`) |
| `delete` | boolean | no | False to grant the role, True to revoke it. (default: `false`) |
| `digest` | string (nullable) | no | Optional SHA256 config digest to prevent concurrent modifications. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_acme_account_create`

MUTATION: register a new ACME account with the CA. Dry-run by default.

Additive — does not affect any existing account. Pair with pbs_acme_plugin_create (DNS-01
challenge), then pbs_acme_cert_order, to actually issue a cert; to remove an account instead
use pbs_acme_account_delete. confirm=True executes (POST /config/acme/account, synchronous —
PBS returns null) and returns {"status": "ok", "result": None}; the default returns a dry-run
PLAN dict. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `contact` | string | yes | Contact email address for the ACME account (CA renewal/expiry notices). |
| `name` | string (nullable) | no | Name to register the account under; omit to let PBS assign a default name. (default: `null`) |
| `directory` | string (nullable) | no | ACME directory URL of the CA to register with; omit to use PBS's default CA. (default: `null`) |
| `eab_hmac_key` | string (nullable) | no | HMAC key for External Account Binding (required by some CAs, e.g. ZeroSSL). Redacted from the PLAN preview and the audit ledger, but IS sent to PBS on confirm=True. (default: `null`) |
| `eab_kid` | string (nullable) | no | Key identifier for External Account Binding; pairs with eab_hmac_key. (default: `null`) |
| `tos_url` | string (nullable) | no | URL of the CA's terms-of-service to accept; omit to accept the CA's default ToS. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the account registration. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_acme_account_delete`

MUTATION: IRREVERSIBLE — DEACTIVATES an ACME account at the CA (not just local config
removal) and deletes the local record. Dry-run by default.

HIGH risk: TLS lockout at cert expiry if this is the only account. The account key is
destroyed — registering again with pbs_acme_account_create creates a DIFFERENT CA account,
not a restore of this one. force=delete local data even if the CA refuses to deactivate
(PBS-only escape hatch; PVE's equivalent tool has no such flag). The dry-run PLAN captures the
current config as evidence only. confirm=True executes (synchronous — PBS returns null) and
returns {"status": "ok", "result": None}. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the ACME account to deactivate and delete from the CA. |
| `force` | boolean | no | Delete the local account record even if the CA refuses to deactivate it. (default: `false`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the irreversible deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_acme_account_get`

READ-ONLY: get one PBS ACME account's full config (account/directory/location/tos). Does
NOT include eab_hmac_key — PBS never returns it on read. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the ACME account. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_acme_account_list`

READ-ONLY: list registered PBS ACME account NAMES (the schema's own response item is
`{"name": str}` only — use pbs_acme_account_get for full account detail). Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_acme_account_update`

MUTATION: update ACME account contact info. Dry-run by default.

LOW risk — metadata update only, no cert impact. PBS's PUT accepts ONLY contact (no eab/tos
fields on update — those are create-only). To delete the account instead use
pbs_acme_account_delete. confirm=True executes (synchronous — PBS returns null) and returns
{"status": "ok", "result": None}. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the existing ACME account to update. |
| `contact` | string (nullable) | no | New contact email address for the ACME account; omit to leave unchanged. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the update. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_acme_cert_order`

MUTATION: order a NEW ACME TLS certificate for a PBS node. Dry-run by default.

MEDIUM (mirrors pve_acme_cert_order's rating): the cert is CA-validated and installed ONLY on
a successful challenge — a failed challenge leaves the existing cert untouched. PBS's schema
declares a null return (unlike PVE's task UPID) — this does NOT mean issuance is synchronous;
the ACME challenge round-trip with the CA still happens on the PBS side after this call
returns, and there is nothing to poll here (no UPID exists to wait on). PBS has NO ACME cert
revoke (unlike PVE). force=overwrite existing files. confirm=True executes (POST
/nodes/{node}/certificates/acme/certificate) and returns {"status": "ok", "result": None}.
Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `force` | boolean | no | Overwrite existing certificate files on the node if already present. (default: `false`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True submits the ACME order. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_acme_cert_renew`

MUTATION: renew the existing ACME TLS certificate for a PBS node. Dry-run by default.

MEDIUM (mirrors pve_acme_cert_renew's rating): CA-validated, installed only on success (a
failure can't lock you out). Same null-return honesty as pbs_acme_cert_order — PBS declares
no return value for this call, but the renewal itself still completes asynchronously on the
PBS side; there is no UPID to poll. force=renew even if not yet within the renewal lead time.
PBS has NO ACME cert revoke. confirm=True executes (PUT /nodes/{node}/certificates/acme/
certificate) and returns {"status": "ok", "result": None}. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `force` | boolean | no | Renew even if the current certificate is not yet within its renewal lead time. (default: `false`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True submits the ACME renewal. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_acme_challenge_schema`

READ-ONLY: list the catalog of known ACME challenge plugin types (id/name/schema/type per
entry) — the parameter schema each plugin `type`+`data` pairing must satisfy. No params.
Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_acme_directories`

READ-ONLY: list PBS's built-in catalog of known ACME CA directory endpoints (name + URL
pairs, e.g. Let's Encrypt production/staging). No params. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_acme_plugin_create`

MUTATION: create an ACME DNS challenge plugin. Dry-run by default.

Additive — does not affect any existing plugin. dns_api = DNS provider name (e.g. 'cf',
'route53'). Reference plugin_id when ordering a cert via a DNS-01 challenge; to remove the
plugin use pbs_acme_plugin_delete. confirm=True executes (POST /config/acme/plugins,
synchronous — PBS returns null) and returns {"status": "ok", "result": None}. Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `plugin_id` | string | yes | Identifier for the new ACME DNS challenge plugin (1-32 chars, alnum/_/./- ; config/acme/plugins/{plugin_id}). |
| `plugin_type` | string | yes | ACME challenge plugin type (e.g. 'dns' or 'standalone'). PBS's own schema declares no enum here — validated defensively by charset only; see pbs_acme_challenge_schema for the live catalog of known types. |
| `dns_api` | string (nullable) | no | DNS provider API name for a DNS-01 challenge (e.g. 'cf', 'route53'); maps to PBS's 'api' field. (default: `null`) |
| `data` | string (nullable) | no | Base64-encoded plugin credential/config data (e.g. DNS provider API tokens) required by the challenge type. Redacted from the PLAN preview and the audit ledger, but IS sent to PBS on confirm=True. (default: `null`) |
| `disable` | boolean (nullable) | no | Set to disable the plugin on creation; omit to leave it enabled. (default: `null`) |
| `validation_delay` | integer (nullable) | no | Extra delay in seconds (0-172800) to wait before requesting validation — copes with long DNS TTLs. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the plugin creation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_acme_plugin_delete`

MUTATION: delete an ACME DNS challenge plugin. Dry-run by default.

HIGH risk: cert auto-renewal breaks for every domain using this plugin — TLS lockout at cert
expiry unless a fallback challenge method is configured. No UNDO primitive — recreate with
pbs_acme_plugin_create, but the credentials must be re-supplied by the caller. The dry-run
PLAN captures the current config (credential redacted) as evidence only; confirm=True executes
(synchronous — PBS returns null) and returns {"status": "ok", "result": None}. Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `plugin_id` | string | yes | Identifier of the ACME DNS challenge plugin to delete. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_acme_plugin_get`

READ-ONLY: get one PBS ACME plugin's full config, INCLUDING the raw `data` credential
blob (PBS does not strip it on read). Handle the result as sensitive. Needs PROXIMO_PBS_*
config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `plugin_id` | string | yes | ID of the ACME DNS challenge plugin. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_acme_plugin_update`

MUTATION: update an ACME DNS challenge plugin. Dry-run by default.

MEDIUM risk — invalid new credentials break cert renewal for every domain using this plugin
at the next attempt. To remove a plugin instead use pbs_acme_plugin_delete. The dry-run PLAN
includes the plugin's current config with the credential blob redacted (PBS DOES return it on
read — see module docstring); confirm=True executes (PUT /config/acme/plugins/{id},
synchronous — PBS returns null) and returns {"status": "ok", "result": None}. Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `plugin_id` | string | yes | Identifier of the existing ACME DNS challenge plugin to update. |
| `dns_api` | string (nullable) | no | New DNS provider API name; maps to PBS's 'api' field. Omit to leave unchanged. (default: `null`) |
| `data` | string (nullable) | no | New base64-encoded plugin credential/config data; omit to leave unchanged. Redacted from the PLAN preview and the audit ledger, but IS sent to PBS on confirm=True. (default: `null`) |
| `disable` | boolean (nullable) | no | Set to enable/disable the plugin; omit to leave unchanged. (default: `null`) |
| `validation_delay` | integer (nullable) | no | New validation-delay in seconds (0-172800); omit to leave unchanged. (default: `null`) |
| `digest` | string (nullable) | no | Config digest for optimistic-locking the update against concurrent changes; omit to skip the check. (default: `null`) |
| `delete` | array<string> (nullable) | no | Property names to clear: 'disable' and/or 'validation-delay' (the only two the schema allows). (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the update. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_acme_plugins_list`

READ-ONLY: list all configured PBS ACME DNS challenge plugins, INCLUDING the raw `data`
credential blob for each (PBS does not strip it on read). Handle the result as sensitive.
Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_acme_tos`

READ-ONLY: get the Terms-of-Service URL for an ACME directory (or None if the CA
advertises no ToS). The PBS host fetches the given directory URL live (https-only,
validated) and the response is authored by whoever controls that URL — classified
ADVERSARIAL in the taint control for exactly that reason. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `directory` | string (nullable) | no | ACME directory URL to look up the Terms of Service for; omit to use PBS's default CA. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_apt_changelog`

READ-ONLY: get a package's changelog text on a PBS node.

GET /nodes/{node}/apt/changelog?name=…[&version=…]. Smoke-confirm: shape not live-verified.
The returned text is UPSTREAM/package-maintainer-authored (not Proxmox-authored) —
classified ADVERSARIAL content (taint.ADVERSARIAL_TOOLS), like pve_apt_changelog and
pmg_apt_changelog. Proxmox's API deliberately does not expose upgrade execution; the upgrade
itself happens at your console. This tool governs visibility only. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Package name to fetch the changelog for (e.g. as listed by pbs_apt_updates_list). |
| `node` | string | no | PBS node name; defaults to 'localhost' (standard single-node PBS name). (default: `"localhost"`) |
| `version` | string (nullable) | no | Specific package version to fetch the changelog for; omit for the latest available. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_apt_repositories_get`

READ-ONLY: get the current APT repository configuration of a PBS node.

GET /nodes/{node}/apt/repositories. Smoke-confirm: shape not live-verified — expected
{files, errors, digest, infos, standard-repos}. `files[].path` + entry index are the
coordinates pbs_apt_repository_set needs; `standard-repos[].handle` is what
pbs_apt_repository_add needs. Proxmox's API deliberately does not expose upgrade execution;
the upgrade itself happens at your console. This tool governs visibility and repo config
only. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name; defaults to 'localhost' (standard single-node PBS name). (default: `"localhost"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_apt_repository_add`

MUTATION: add a standard repository to the configuration on a PBS node.

RISK_MEDIUM: adds a new package source — affects the NEXT upgrade's package provenance.
CAPTURE: reads current repository state before planning (also readable directly via
pbs_apt_repositories_get); if unreadable -> complete=False. No automatic revert: removing an
added repository requires pbs_apt_repository_set to disable the resulting entry (there is no
repository-delete endpoint). Proxmox's API deliberately does not expose upgrade execution;
the upgrade itself happens at your console. This tool governs repo config only. Dry-run by
default (returns a PLAN); confirm=True executes (PUT, Smoke-confirm) and returns
{"status": "ok", "result": None}. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `handle` | string | yes | Handle identifying the standard repository to add (as returned by pbs_apt_repositories_get's standard-repos list, e.g. 'no-subscription'). PBS requires a lowercase-leading handle. |
| `node` | string | no | PBS node name; defaults to 'localhost' (standard single-node PBS name). (default: `"localhost"`) |
| `digest` | string (nullable) | no | Expected SHA-256 content digest (64 hex chars) of the repositories file, for optimistic-concurrency conflict detection. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the addition. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_apt_repository_set`

MUTATION: enable/disable one APT repository entry on a PBS node, by file path + index.

RISK_MEDIUM: changes where packages come from — affects the NEXT upgrade's package
provenance. CAPTURE: reads current repository state before planning (also readable directly
via pbs_apt_repositories_get); if unreadable -> complete=False. Proxmox's API deliberately
does not expose upgrade execution; the upgrade itself happens at your console. This tool
governs repo config only. Dry-run by default (returns a PLAN); confirm=True executes (POST,
Smoke-confirm) and returns {"status": "ok", "result": None}. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `path` | string | yes | Absolute path of the sources file containing the repository entry (as returned by pbs_apt_repositories_get). |
| `index` | integer | yes | 0-based index of the repository entry within that file (as returned by pbs_apt_repositories_get). |
| `node` | string | no | PBS node name; defaults to 'localhost' (standard single-node PBS name). (default: `"localhost"`) |
| `enabled` | boolean (nullable) | no | Set the entry's enabled state; omit to leave the enabled state unchanged. (default: `null`) |
| `digest` | string (nullable) | no | Expected SHA-256 content digest (64 hex chars) of the repositories file, for optimistic-concurrency conflict detection. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the change. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_apt_update_refresh`

MUTATION: resynchronize the APT package index on a PBS node (apt-get update).

RISK_LOW: no package state change — refreshes the local index cache only. Proxmox's API
deliberately does not expose upgrade execution; the upgrade itself happens at your console.
This tool governs visibility only — it does NOT install or upgrade any package. Idempotent —
safe to re-run any time. Dry-run by default (returns a PLAN); confirm=True executes (POST,
Smoke-confirm) and returns {"status": "submitted"|"ok", "result": <task UPID | None>}.
Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name; defaults to 'localhost' (standard single-node PBS name). (default: `"localhost"`) |
| `notify` | boolean (nullable) | no | If True, ask PBS to send a notification email about newly available packages. (default: `null`) |
| `quiet` | boolean (nullable) | no | If True, ask PBS to omit progress output suitable only for interactive logging. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the index refresh. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_apt_updates_list`

READ-ONLY: list available package updates (cached apt index) on a PBS node.

GET /nodes/{node}/apt/update. Smoke-confirm: shape not live-verified — expected per-package
dicts (Package/Title/Description/Origin/Version/OldVersion/Priority/Section/Arch). Proxmox's
API deliberately does not expose upgrade execution; the upgrade itself happens at your
console. This tool governs visibility only. To refresh this list first use
pbs_apt_update_refresh. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name; defaults to 'localhost' (standard single-node PBS name). (default: `"localhost"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_apt_versions`

READ-ONLY: get installed versions of important Proxmox Backup Server packages on a PBS node.

GET /nodes/{node}/apt/versions. Smoke-confirm: shape not live-verified — expected
per-package dicts (Package/Version/OldVersion + Arch/...). Proxmox's API deliberately does
not expose upgrade execution; the upgrade itself happens at your console. This tool governs
visibility only. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name; defaults to 'localhost' (standard single-node PBS name). (default: `"localhost"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_datastore_create`

MUTATION (MEDIUM): create a new PBS datastore at the given path.

Dry-run by default — additive, but a misconfigured path can conflict with existing storage.
PBS datastore creation is an async worker task (UPID) → outcome='submitted' (not 'ok').
No rollback primitive. confirm=True to execute. Use pbs_datastores_list to check for
name/path collisions first, or pbs_datastore_update to modify it afterward.

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
To recover from a destroy_data=False detach, re-add with pbs_datastore_create at the
same path.

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
Use pbs_datastore_get to inspect current config, or pbs_datastore_delete to remove the
datastore instead.

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
permanently removes unreferenced chunks (no undo). confirm=True to execute; returns the
UPID (async task) — check progress with pbs_gc_status or pbs_tasks_list.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes | PBS datastore name to run garbage collection on. |
| `confirm` | boolean | no | Set True to execute; False (default) only returns the dry-run plan. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_gc_status`

Get garbage-collection status for one PBS datastore (read-only). Returns current GC
state, disk/index statistics, and pending/removed chunk counts (the GC schedule field
appears only when a schedule is configured on the datastore).
Use pbs_gc_start to execute garbage collection or pbs_datastore_status for capacity.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes | PBS datastore name. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_group_change_owner`

MUTATION (MEDIUM): reassign the owner of a PBS backup group. Dry-run by default.

The new owner controls deletion and prune of this backup group.
The previous owner loses those permissions immediately. Use pbs_snapshots_list to see
the group's current owner first.
No PBS snapshot primitive — revert by re-assigning the owner back. confirm=True to execute.

POST /admin/datastore/{store}/change-owner
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

MUTATION: create a PBS scheduled job. job_type = sync|verify|prune. Dry-run by default;
confirm=True to execute and returns synchronously (no task UPID) — additive, no existing data
affected. Needs PROXIMO_PBS_* config. To modify use pbs_job_update, to remove use
pbs_job_delete, or to run it once immediately (bypassing the schedule) use pbs_job_run.

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
the PLAN captures current config (no UNDO primitive; re-create with pbs_job_create to restore
the schedule). confirm=True to execute and returns synchronously (no task UPID). Schedule
removed, backup data NOT deleted. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `job_type` | string | yes | PBS job type: sync \| verify \| prune. |
| `job_id` | string | yes | ID of the PBS scheduled job to delete. |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_job_run`

MUTATION: trigger a PBS scheduled job immediately, outside its normal schedule.
job_type = sync|verify|prune. Dry-run by default; confirm=True to execute. Async — returns
a UPID; check progress with pbs_tasks_list. Risk depends on job_type: prune runs permanently
DELETE snapshots per the retention policy, sync may add/remove directory data, verify is
read-only. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `job_type` | string | yes | PBS job type: sync \| verify \| prune. |
| `job_id` | string | yes | ID of the PBS scheduled job to trigger immediately. |
| `confirm` | boolean | no | Gate: false returns a dry-run PLAN, true executes the run. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_job_update`

MUTATION: update a PBS scheduled job. job_type = sync|verify|prune. Dry-run by default —
the PLAN captures current config for manual revert; confirm=True to execute and returns
synchronously (no task UPID). Config-only; existing backup data is unaffected. Needs
PROXIMO_PBS_* config. To create use pbs_job_create; to remove use pbs_job_delete.

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

READ-ONLY: list all PBS scheduled jobs of the given type. job_type = sync|verify|prune.
Returns all jobs with their configs; raises on invalid job_type. Use pbs_job_create,
pbs_job_update, or pbs_job_delete to manage one. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `job_type` | string | yes | Scheduled-job type to list: 'sync', 'verify', or 'prune'. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_namespace_create`

MUTATION: create a namespace within a PBS datastore. Dry-run by default (additive, LOW).
confirm=True to execute — returns {"status": "ok", "result": null}. Use pbs_namespaces_list to check for
name collisions first, or pbs_namespace_delete to remove one.

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
to execute — returns {"status": "ok", "result": null}. Use pbs_namespaces_list to confirm it's empty first,
or pbs_namespace_create to recreate an empty namespace afterward.

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

#### `pbs_node_cert_delete`

MUTATION (MEDIUM): delete the custom TLS certificate on a PBS node; PBS regenerates a
self-signed one. Dry-run by default. NOTE: PBS's 'restart' param on this endpoint is
documented as ignored — not exposed here. confirm=True executes (DELETE
/nodes/{node}/certificates/custom) and returns {"status": "ok", "result": None}. Recoverable
by re-uploading (pbs_node_cert_upload). Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_cert_upload`

MUTATION (HIGH, no undo): upload a custom TLS certificate to a PBS node. A malformed
cert/key can lock you out of the PBS web UI and API. Dry-run by default.

PRIVATE KEY REDACTION: `key` is UNCONDITIONALLY redacted — never appears in the plan, change,
detail, or ledger. Only {"key": "[redacted]"} is recorded. NOTE: PBS's own schema documents a
'restart' param on this endpoint as ignored ("UI compatibility parameter") — deliberately not
exposed here.

confirm=True executes (POST /nodes/{node}/certificates/custom) and returns
{"status": "ok", "result": [...cert info dicts...]}. Revert with pbs_node_cert_delete. Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `certificates` | string | yes | PEM-encoded certificate chain (public, may appear in plans/logs). |
| `key` | string (nullable) | no | PEM-encoded TLS private key matching the certificate; a secret, unconditionally redacted in all output. (default: `null`) |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `force` | boolean | no | If True, overwrite an existing custom certificate. (default: `false`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the certificate upload. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_certificates_list`

READ-ONLY: list TLS certificates configured on a PBS node. Returns filename/subject/
issuer/validity dates/fingerprint per certificate. Use pbs_node_cert_upload to add/replace, or
pbs_node_cert_delete to remove. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_disk_directory_create`

MUTATION: format a disk and mount it as a directory datastore on a PBS node.

RISK_HIGH: FORMATS the named disk immediately — any pre-existing data is destroyed,
irreversibly. To see what already exists use pbs_node_disk_directory_list; to remove one use
pbs_node_disk_directory_delete (note: PBS's delete has NO cleanup-disks option — it never
wipes the disk). Dry-run by default (returns a PLAN); confirm=True executes (POST
/nodes/{node}/disks/directory, Smoke-confirm) and returns
{"status": "submitted", "result": <task UPID | None>}. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `disk` | string | yes | Bare whole-disk name to format (e.g. 'sda') — NOT a /dev/ path. |
| `name` | string | yes | Datastore name to create (3-32 chars, alnum/underscore start). |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `filesystem` | string (nullable) | no | Filesystem to format with: 'ext4' or 'xfs'. PBS default is ext4 if omitted. (default: `null`) |
| `add_datastore` | boolean (nullable) | no | If True, also register a PBS datastore using this directory. (default: `null`) |
| `removable_datastore` | boolean (nullable) | no | If True, mark the datastore as removable media. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the creation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_disk_directory_delete`

MUTATION: remove a directory datastore's mount unit and config mapping on a PBS node.

RISK_HIGH: irreversibly destroys the datastore mapping. UNLIKE PVE's equivalent, PBS exposes
NO cleanup-disks option here — the underlying disk data is NEVER wiped by this call, only the
mount unit and config mapping are removed. This call is SYNCHRONOUS on PBS (unlike PVE's async
version): confirm=True executes (DELETE /nodes/{node}/disks/directory/{name}) and returns
{"status": "ok", "result": None} directly, not "submitted". Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Datastore name (directory backend) to remove. |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the removal. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_disk_directory_list`

READ-ONLY: list systemd datastore mount units (the directory backend) on a PBS node.
Returns device/name/path/removable/unitfile/filesystem/options per mount. Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_disk_initgpt`

MUTATION: initialize a GPT partition table on a whole PBS disk.

RISK_HIGH: overwrites the existing partition table on the named disk; irreversible — less
destructive than pbs_node_disk_wipe, which also erases the underlying data and accepts a
partition target. Dry-run by default (returns a PLAN); confirm=True executes (POST
/nodes/{node}/disks/initgpt, Smoke-confirm) and returns
{"status": "submitted", "result": <task UPID | None>}. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `disk` | string | yes | Bare WHOLE-disk name to initialize with a new GPT partition table (e.g. 'sda', 'nvme0n1') — NOT a /dev/ path and NOT a partition; overwrites the existing partition table. |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `uuid` | string (nullable) | no | Optional UUID to assign to the new GPT table. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the irreversible GPT init. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_disk_smart`

READ-ONLY: get SMART attributes and health for one disk on a PBS node. Returns {status,
attributes, wearout}. This is the GET form — it does NOT trigger a self-test. Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `disk` | string | yes | Bare block device name (e.g. 'sda', 'nvme0n1') — NOT a /dev/ path. As listed by pbs_node_disks_list. |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `healthonly` | boolean (nullable) | no | If True, returns only the health status (not the full attribute table). (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_disk_wipe`

MUTATION: wipe ALL data and the partition table on a PBS disk or partition.

RISK_HIGH, NO UNDO: DESTROYS all data, partitions, and filesystems on the named device — more
destructive than pbs_node_disk_initgpt, which only overwrites the partition table. Unlike
initgpt, 'disk' here MAY be a partition, not just a whole disk. Dry-run by default (returns a
PLAN); confirm=True executes (PUT /nodes/{node}/disks/wipedisk, Smoke-confirm) and returns
{"status": "submitted", "result": <task UPID | None>}. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `disk` | string | yes | Bare block device or partition name to wipe (e.g. 'sda', 'sda1', 'nvme0n1p1') — NOT a /dev/ path. ALL data on the target is destroyed. |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the irreversible wipe. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_disk_zfs_create`

MUTATION: create a zpool from disks and mount it as a zfs datastore on a PBS node.

RISK_HIGH: FORMATS the named device(s) immediately — any pre-existing data is destroyed,
irreversibly. Unlike the directory backend, PBS's API has NO delete endpoint for a zfs backend
at all (module docstring gap #3) — once created, this zpool cannot be destroyed through this
API. Dry-run by default (returns a PLAN, which names this no-delete gap explicitly);
confirm=True executes (POST /nodes/{node}/disks/zfs, Smoke-confirm) and returns
{"status": "submitted", "result": <task UPID | None>}. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `devices` | string | yes | Comma-separated bare disk names to consume (e.g. 'sda,sdb') — NOT /dev/ paths. |
| `name` | string | yes | Datastore name to create (3-32 chars, alnum/underscore start). |
| `raidlevel` | string | yes | ZFS RAID level: single, mirror, raid10, raidz, raidz2, or raidz3. (No dRAID — PBS's schema doesn't offer it, unlike PVE.) |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `ashift` | integer (nullable) | no | Pool sector size exponent, 9-16 (PBS default 12 if omitted). (default: `null`) |
| `compression` | string (nullable) | no | ZFS compression algorithm: gzip, lz4, lzjb, zle, zstd, on, or off. (default: `null`) |
| `add_datastore` | boolean (nullable) | no | If True, also register a PBS datastore using this zpool. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the creation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_disk_zfs_get`

READ-ONLY: get one zpool's status/vdev tree on a PBS node. This endpoint also exists on
PVE at the identical path+verb, but Proximo has never built a wrapper for it there — a gap in
Proximo's own PVE coverage, not a PBS-only feature. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | ZFS pool name (must start with a letter). |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_disk_zfs_list`

READ-ONLY: list zpools (the zfs backend) on a PBS node. Returns name/health/size/alloc/
free/frag/dedup per pool (summary only — for one pool's full vdev tree use
pbs_node_disk_zfs_get). Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_disks_list`

READ-ONLY: list physical disks on a PBS node. Returns name/devpath/disk-type/size/status/
used/model/serial/wwn/wearout/rpm/gpt/partitions per disk. For one disk's SMART detail use
pbs_node_disk_smart. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `include_partitions` | boolean (nullable) | no | Also include partitions in the result. (default: `null`) |
| `skipsmart` | boolean (nullable) | no | Skip SMART checks (faster, less detail). (default: `null`) |
| `usage_type` | string (nullable) | no | Filter by usage: one of unused, mounted, lvm, zfs, devicemapper, partitions, filesystem. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_dns_get`

READ-ONLY: read a PBS node's DNS resolver configuration. Returns {search, dns1, dns2,
dns3, digest}. Use pbs_node_dns_set to change it. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name (or 'localhost', the standard single-node PBS hostname). (default: `"localhost"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_dns_set`

MUTATION (MEDIUM): update DNS resolver configuration on a PBS node. Dry-run by default —
the PLAN reads the node's current DNS config first (CAPTURE-or-declare). confirm=True executes
(PUT /nodes/{node}/dns) and returns {"status": "ok", "result": None}. Needs PROXIMO_PBS_*
config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `search` | string (nullable) | no | DNS search domain to set. (default: `null`) |
| `dns1` | string (nullable) | no | Primary DNS resolver IP address. (default: `null`) |
| `dns2` | string (nullable) | no | Secondary DNS resolver IP address. (default: `null`) |
| `dns3` | string (nullable) | no | Tertiary DNS resolver IP address. (default: `null`) |
| `delete_props` | array<string> (nullable) | no | Property names to clear. (default: `null`) |
| `digest` | string (nullable) | no | Optional SHA256 config digest for optimistic-concurrency conflict detection. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the DNS change. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_journal`

READ-ONLY: fetch systemd journal lines from a PBS node. Returns a list of journal-line
strings. Note: since/until here are UNIX-epoch INTEGERS (the /journal convention on both PBS
and PVE); the free-text date-time-string form is on the /syslog endpoint, not here. For the
classic syslog view use pbs_node_syslog. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `lastentries` | integer (nullable) | no | Limit to the last N lines; conflicts with a cursor/time range. (default: `null`) |
| `since` | integer (nullable) | no | Display log since this UNIX epoch (integer); conflicts with startcursor. (default: `null`) |
| `until` | integer (nullable) | no | Display log until this UNIX epoch (integer); conflicts with endcursor. (default: `null`) |
| `startcursor` | string (nullable) | no | Start after this journal cursor token; conflicts with since. (default: `null`) |
| `endcursor` | string (nullable) | no | End before this journal cursor token; conflicts with until. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_network_iface_create`

MUTATION (MEDIUM): create a network interface configuration on a PBS node (staged, written
to interfaces.new — NOT live until pbs_node_network_reload). Dry-run by default (checks for a
name collision). confirm=True executes (POST /nodes/{node}/network) and returns
{"status": "submitted", "result": None}. Apply with pbs_node_network_reload (RISK_HIGH) or
discard with pbs_node_network_revert. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `iface` | string | yes | New network interface name. |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `iface_type` | string (nullable) | no | Interface type: one of loopback, eth, bridge, bond, vlan, alias, unknown. PBS marks this OPTIONAL even on create. (default: `null`) |
| `options` | object (nullable) | no | Additional interface fields (cidr, gateway, bridge_ports, bond_mode, mtu, autostart, comments, ...) forwarded verbatim. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the creation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_network_iface_delete`

MUTATION (MEDIUM): remove a network interface's staged configuration on a PBS node (NOT
live until pbs_node_network_reload). Dry-run by default — reads the interface's current
config. confirm=True executes (DELETE /nodes/{node}/network/{iface}) and returns
{"status": "ok", "result": None}. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `iface` | string | yes | Network interface name to remove. |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `digest` | string (nullable) | no | Optional SHA256 config digest for optimistic-concurrency conflict detection. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the removal. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_network_iface_get`

READ-ONLY: read one network interface's configuration on a PBS node. Needs PROXIMO_PBS_*
config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `iface` | string | yes | Network interface name, e.g. 'eth0' or 'vmbr0'. |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_network_iface_update`

MUTATION (MEDIUM): update a network interface's configuration on a PBS node (staged — NOT
live until pbs_node_network_reload). Dry-run by default — reads the interface's current
config. Unlike PVE, PBS does not require re-sending 'type'. confirm=True executes (PUT
/nodes/{node}/network/{iface}) and returns {"status": "ok", "result": None}. Apply with
pbs_node_network_reload (RISK_HIGH) or discard with pbs_node_network_revert. Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `iface` | string | yes | Existing network interface name to update. |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `iface_type` | string (nullable) | no | Interface type: one of loopback, eth, bridge, bond, vlan, alias, unknown; omit to leave unchanged. (default: `null`) |
| `options` | object (nullable) | no | Interface fields to change (cidr, gateway, bridge_ports, mtu, autostart, comments, ...) forwarded verbatim. (default: `null`) |
| `delete_props` | array<string> (nullable) | no | Property names to clear. (default: `null`) |
| `digest` | string (nullable) | no | Optional SHA256 config digest for optimistic-concurrency conflict detection. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the update. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_network_list`

READ-ONLY: list network interfaces on a PBS node (with config digest). Use
pbs_node_network_iface_get for one interface's full config. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_network_reload`

MUTATION (HIGH): apply staged network configuration changes on a PBS node — makes
interfaces.new live. Dry-run by default. *** CONNECTIVITY-LOCKOUT RISK *** a misconfigured
interface can drop SSH/API access; recovery requires console/physical access. confirm=True
executes (PUT /nodes/{node}/network) and returns {"status": "ok", "result": None}. Review
staged changes with pbs_node_network_list first; discard them instead with
pbs_node_network_revert. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True applies the staged changes. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_network_revert`

MUTATION (LOW): discard staged network configuration changes on a PBS node (interfaces.new
reverted) — the live config is untouched; safe. Dry-run by default. confirm=True executes
(DELETE /nodes/{node}/network) and returns {"status": "ok", "result": None}. Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True discards the staged changes. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_service_control`

MUTATION: start/stop/restart/reload a service on a PBS node. Dry-run by default — the PLAN
flags lockout-class services (proxmox-backup/proxmox-backup-proxy/sshd/networking/ifupdown2/
chrony) as HIGH because stop/restart can sever management access or break backup jobs. There
is NO auto-undo. confirm=True executes (POST /nodes/{node}/services/{service}/{action}) and
returns {"status": "ok", "result": None}. Check current state first with
pbs_node_service_status. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `service` | string | yes | systemd service name to control, e.g. 'proxmox-backup-proxy' or 'sshd'. |
| `action` | string | yes | Control action: 'start', 'stop', 'restart', or 'reload'. |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the service control. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_service_status`

READ-ONLY: get one systemd service's current state on a PBS node. Use
pbs_node_services_list to list every service; pbs_node_service_control to change run state.
Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `service` | string | yes | systemd service name, e.g. 'proxmox-backup-proxy' or 'sshd'. |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_services_list`

READ-ONLY: list all systemd services on a PBS node. Returns desc/name/service/state/
unit-state per service. Use pbs_node_service_status for one service's state, or
pbs_node_service_control to change a service's run state. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_status`

READ-ONLY: read a PBS node's memory/CPU/(root) disk usage. NOTE: PBS's own schema also
exposes POST /nodes/{node}/status ("Reboot or shutdown the node") — deliberately NOT built
here (mirrors PVE's identical, also-never-built POST /nodes/{node}/status; too dangerous for
the default surface, same posture as the excluded node/execute endpoint). Needs PROXIMO_PBS_*
config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_subscription_check`

MUTATION (LOW): check and refresh a PBS node's subscription status by contacting Proxmox's
server. Dry-run by default. No key/identity change — status-cache refresh only. confirm=True
executes (POST /nodes/{node}/subscription) and returns {"status": "ok", "result": None}.
Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `force` | boolean | no | If True, always re-check even if the cached status is fresh. (default: `false`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the check. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_subscription_delete`

MUTATION (MEDIUM): delete the locally-stored subscription info on a PBS node. Dry-run by
default. confirm=True executes (DELETE /nodes/{node}/subscription) and returns
{"status": "ok", "result": None}. Reversible via pbs_node_subscription_set. Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_subscription_get`

READ-ONLY: read a PBS node's subscription status. Use pbs_node_subscription_set to
install/change a key, pbs_node_subscription_check to force a status refresh, or
pbs_node_subscription_delete to remove the record. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_subscription_set`

MUTATION (MEDIUM): install and validate a subscription key on a PBS node. Dry-run by
default. confirm=True executes (PUT /nodes/{node}/subscription) and returns
{"status": "ok", "result": None}. Reversible via pbs_node_subscription_delete. Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `key` | string | yes | Subscription key to install. |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the installation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_syslog`

READ-ONLY: fetch syslog entries from a PBS node. Returns a list of {n, t} dicts (n=line
number, t=text). For the systemd journal (with epoch/cursor filtering) use pbs_node_journal
instead. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `limit` | integer (nullable) | no | Max number of syslog entries to return. (default: `null`) |
| `start` | integer (nullable) | no | Start line number. (default: `null`) |
| `since` | string (nullable) | no | Display log since this date-time string. (default: `null`) |
| `until` | string (nullable) | no | Display log until this date-time string. (default: `null`) |
| `service` | string (nullable) | no | Filter to one systemd service's lines. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_task_log`

READ-ONLY: retrieve a PBS task's log output by UPID, paginated via start/limit. Use
pbs_tasks_list to find UPIDs, or pbs_node_task_status for the terminal status only. Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `upid` | string | yes | The task's Unique Process ID (UPID) string. |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `start` | integer | no | Line offset to start returning log output from (for pagination). (default: `0`) |
| `limit` | integer | no | Max number of log lines to return. (default: `50`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_task_status`

READ-ONLY: get one PBS task's status by UPID (status/exitstatus/pid/starttime/...). Use
pbs_tasks_list to find UPIDs, or pbs_node_task_log for the full log. Needs PROXIMO_PBS_*
config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `upid` | string | yes | The task's Unique Process ID (UPID) string. |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_task_stop`

MUTATION (HIGH): stop (cancel) a running PBS task. Dry-run by default — the PLAN warns that
stopping a backup/restore/verify/sync/prune/GC task mid-flight can leave the datastore or a
snapshot inconsistent, with NO undo. confirm=True executes (DELETE
/nodes/{node}/tasks/{upid}) and returns {"status": "ok", "result": None} — a cancellation
signal, not immediate. Find UPIDs via pbs_tasks_list. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `upid` | string | yes | The task's Unique Process ID (UPID) string to cancel. |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the cancellation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_time_get`

READ-ONLY: read a PBS node's current time and timezone. Returns {localtime, time,
timezone}. Use pbs_node_time_set to change the timezone. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_node_time_set`

MUTATION (LOW): set the timezone on a PBS node. Dry-run by default — reads the current
timezone first (also readable via pbs_node_time_get). confirm=True executes (PUT
/nodes/{node}/time) and returns {"status": "ok", "result": None}. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `timezone` | string | yes | IANA timezone name to set on the node (e.g. UTC, America/Chicago). |
| `node` | string | no | PBS node name (or 'localhost'). (default: `"localhost"`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the timezone change. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_notification_endpoint_create`

MUTATION: create a PBS notification endpoint. ep_type = gotify|sendmail|smtp|webhook.
`options` carries the endpoint-specific config. Additive, RISK_LOW. Dry-run by default
(returns a PLAN — any secret in `options` is masked to "[redacted]" in the preview);
confirm=True executes (POST .../endpoints/{type}, synchronous — PBS returns null, not a task)
and returns {"status": "ok", "result": None}. To modify an existing endpoint use
pbs_notification_endpoint_update. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ep_type` | string | yes | Notification endpoint type: 'gotify', 'sendmail', 'smtp', or 'webhook'. |
| `name` | string | yes | Unique name for the new notification endpoint (2-32 chars, alnum start). |
| `comment` | string (nullable) | no | Optional free-text comment stored with the endpoint. (default: `null`) |
| `disable` | boolean (nullable) | no | If True, create the endpoint disabled. (default: `null`) |
| `options` | object (nullable) | no | Type-specific config fields, e.g. gotify: {'server':.., 'token':..}; sendmail: {'mailto':[..]}; smtp: {'server':.., 'port':.., 'mailto':[..]}; webhook: {'url':.., 'method':.., 'header':[..], 'secret':[..]}. Credential-shaped keys (token/password/secret/header) are redacted from the PLAN preview and the audit ledger, but ARE sent to PBS on confirm=True. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the creation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_notification_endpoint_delete`

MUTATION: delete a PBS notification endpoint. ep_type = gotify|sendmail|smtp|webhook.
Dry-run by default — captures current config (secrets masked). confirm=True executes
(DELETE .../endpoints/{type}/{name}, synchronous — PBS returns null) and returns
{"status": "ok", "result": None}. No UNDO primitive — matchers referencing this endpoint
silently fail until it is re-created with pbs_notification_endpoint_create. Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ep_type` | string | yes | Notification endpoint type: 'gotify', 'sendmail', 'smtp', or 'webhook'. |
| `name` | string | yes | Name of the notification endpoint to delete. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_notification_endpoint_get`

READ-ONLY: get one PBS notification endpoint's full type-specific config. Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ep_type` | string | yes | Notification endpoint type: 'gotify', 'sendmail', 'smtp', or 'webhook'. |
| `name` | string | yes | Name of the notification endpoint. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_notification_endpoint_list`

READ-ONLY: list PBS notification endpoints with their full type-specific config.
Aggregates GET .../endpoints/{type} across all 4 types (or just one if ep_type is given) —
PBS's own GET .../endpoints (no type) is a directory index, not a usable list. Each item is
tagged with its 'type' (the per-type responses don't carry one). Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ep_type` | string (nullable) | no | Optional filter: one of gotify, sendmail, smtp, webhook. Omit to aggregate all 4 types. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_notification_endpoint_update`

MUTATION: update a PBS notification endpoint. ep_type = gotify|sendmail|smtp|webhook.
Dry-run by default — captures current config into the PLAN (secrets masked); confirm=True
executes (PUT .../endpoints/{type}/{name}, synchronous — PBS returns null) and returns
{"status": "ok", "result": None}. No snapshot primitive; re-apply the captured config to
revert, or use pbs_notification_endpoint_create to make a new one instead. Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ep_type` | string | yes | Notification endpoint type: 'gotify', 'sendmail', 'smtp', or 'webhook'. |
| `name` | string | yes | Name of the existing notification endpoint to update. |
| `comment` | string (nullable) | no | Optional free-text comment to set on the endpoint. (default: `null`) |
| `disable` | boolean (nullable) | no | True disables the endpoint; False re-enables it. (default: `null`) |
| `digest` | string (nullable) | no | Optimistic-lock: 64-char lowercase hex SHA-256 of the config PBS last returned. If set and stale, PBS rejects the update. (default: `null`) |
| `options` | object (nullable) | no | Type-specific fields to change, same shape as create. Credential-shaped keys (token/password/secret/header) are redacted from the PLAN preview and the audit ledger, but ARE sent to PBS on confirm=True. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the update. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_notification_matcher_delete`

MUTATION: delete a PBS notification matcher. Dry-run by default. confirm=True executes
(DELETE .../matchers/{name}, synchronous — PBS returns null) and returns
{"status": "ok", "result": None}. No UNDO primitive — alerts matching this filter go
un-routed until re-created with pbs_notification_matcher_set. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the notification matcher to delete. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the deletion. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_notification_matcher_field_values`

READ-ONLY: list all known (field, value) pairs the system currently recognizes for
matcher rules. No params. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_notification_matcher_fields`

READ-ONLY: list all known metadata field NAMES a matcher's match-field rule can target
(e.g. 'type', 'datastore'). No params. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_notification_matcher_get`

READ-ONLY: get one PBS notification matcher's full config. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the notification matcher. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_notification_matcher_set`

MUTATION: create-or-update a PBS notification matcher (alert routing rule). One safe read
of the matchers collection decides create (POST, name in body) vs update (PUT .../{name}) —
`digest`/`delete` only apply to the update branch. Dry-run by default (returns a PLAN);
confirm=True executes (synchronous — PBS returns null) and returns
{"status": "ok", "result": None}. No snapshot primitive — re-apply with this same tool to
restore after deletion. To remove a matcher use pbs_notification_matcher_delete. Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the notification matcher (alert routing rule) to create or update (2-32 chars, alnum start). |
| `comment` | string (nullable) | no | Optional free-text comment stored with the matcher. (default: `null`) |
| `mode` | string (nullable) | no | How match-* filters combine: 'all' (default on PBS) or 'any'. (default: `null`) |
| `match_severity` | array<string> (nullable) | no | Severity levels to match (e.g. ['error','warning']). (default: `null`) |
| `match_field` | array<string> (nullable) | no | Metadata field filters to match (see pbs_notification_matcher_fields for known names). (default: `null`) |
| `match_calendar` | array<string> (nullable) | no | Calendar-event time-window filters to match. (default: `null`) |
| `invert_match` | boolean (nullable) | no | If True, invert the whole filter's match result. (default: `null`) |
| `target` | array<string> (nullable) | no | Names of endpoints/targets to notify when this matcher fires. (default: `null`) |
| `disable` | boolean (nullable) | no | If True, disable this matcher without deleting it. (default: `null`) |
| `digest` | string (nullable) | no | Optimistic-lock (update only): 64-char lowercase hex SHA-256 of the config PBS last returned. Ignored on create — PBS's own create schema has no digest field. (default: `null`) |
| `delete` | array<string> (nullable) | no | Update only: property names to clear (e.g. ['comment','target']). Ignored on create. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the create/update. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_notification_matchers_list`

READ-ONLY: list all PBS notification matchers (alert routing rules). Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_notification_target_test`

MUTATION: send a REAL test notification to a PBS notification target. Dry-run by default
(returns a PLAN, nothing is sent); confirm=True SENDS A REAL NOTIFICATION to the target's
recipients/webhook/gotify server and returns {"status": "ok", "result": None} (synchronous —
PBS returns null). No config changes. `name` is an existing endpoint or matcher name — see
pbs_notification_targets_list for target names. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Name of the notification target (endpoint or matcher) to send a test notification to. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True SENDS A REAL test notification. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_notification_targets_list`

READ-ONLY: list all PBS notification targets (the unified list — name, type, comment,
disable, origin — across every endpoint type). For an endpoint's full type-specific config
use pbs_notification_endpoint_get. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_permissions_get`

READ-ONLY: resolve effective privileges for a PBS user/token. Returns a map of ACL path
to a map of privilege name to propagate-bit — the RESOLVED (inherited + direct) view, unlike
pbs_acl_get's raw entry list. Use pbs_acl_get to see the raw ACL entries this resolves from.
Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `auth_id` | string (nullable) | no | User or token to resolve permissions for ('user@realm' or 'user@realm!token-name'); omit for the calling credential's own permissions. (default: `null`) |
| `path` | string (nullable) | no | ACL path to scope the result to; omit for every path the principal has any privilege on. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_prune`

MUTATION: prune backup snapshots per a retention policy. TWO safety gates: confirm
(Proximo dry-run vs execute) AND dry_run (PBS-side preview). dry_run=True (default) only
previews; dry_run=False DELETES recovery points (PLAN is HIGH, no undo). confirm=True to
execute. Synchronous — returns prune decisions. For one specific snapshot use
pbs_snapshot_delete instead.

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

#### `pbs_realm_ad_create`

MUTATION (MEDIUM): create an AD authentication realm. Dry-run by default.

PASSWORD REDACTION: `password` (the AD bind password), when supplied, is UNCONDITIONALLY
redacted from the plan, detail, and audit ledger (only {"password": "[redacted]"} is
recorded). confirm=True executes and returns a dict; synchronous, no UPID. Use
pbs_realm_ad_update to change it afterward, or pbs_realm_ad_delete to remove it. Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes | New AD realm name. |
| `server1` | string | yes | Primary AD server address. |
| `base_dn` | string (nullable) | no | LDAP base DN to search under; optional for AD. (default: `null`) |
| `bind_dn` | string (nullable) | no | LDAP bind DN for the service account. (default: `null`) |
| `capath` | string (nullable) | no | Path to a CA certificate file or directory to trust for TLS. (default: `null`) |
| `comment` | string (nullable) | no | Optional free-text comment. (default: `null`) |
| `default` | boolean (nullable) | no | True to make this the default realm preselected on login. (default: `null`) |
| `filter` | string (nullable) | no | Custom LDAP search filter for user sync. (default: `null`) |
| `mode` | string (nullable) | no | LDAP connection type: 'ldap', 'ldap+starttls', or 'ldaps'. (default: `null`) |
| `password` | string (nullable) | no | AD bind password for the service account; redacted from all plans/logs/ledger. (default: `null`) |
| `port` | integer (nullable) | no | AD server port. (default: `null`) |
| `server2` | string (nullable) | no | Fallback AD server address. (default: `null`) |
| `sync_attributes` | string (nullable) | no | Comma-separated key=value LDAP-attribute-to-PBS-field sync map, forwarded verbatim. (default: `null`) |
| `sync_defaults_options` | string (nullable) | no | Default sync-run options string, forwarded verbatim (exact syntax not live-verified). (default: `null`) |
| `user_classes` | string (nullable) | no | Comma-separated allowed objectClass values for user sync. (default: `null`) |
| `verify` | boolean (nullable) | no | Whether to verify the AD server's TLS certificate. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_realm_ad_delete`

MUTATION (MEDIUM): permanently delete an AD realm. Dry-run by default — the PLAN reads the
realm's current config and flags that any users authenticating via it lose login access.
confirm=True executes and returns a dict; synchronous, no UPID. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes | AD realm name to delete. |
| `digest` | string (nullable) | no | Optional SHA256 config digest to prevent concurrent modifications. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_realm_ad_get`

READ-ONLY: get one AD realm's config. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes | AD realm name to look up. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_realm_ad_list`

READ-ONLY: list configured AD realms. Use pbs_realm_ad_get for one realm's full config.
Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_realm_ad_update`

MUTATION (MEDIUM): update an AD realm's config. Dry-run by default — the PLAN reads the
realm's current config first. `password`, if supplied, is redacted identically to
pbs_realm_ad_create's. confirm=True executes and returns a dict; synchronous, no UPID. Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes | AD realm name to update. |
| `base_dn` | string (nullable) | no | LDAP base DN; omit to leave unchanged. (default: `null`) |
| `bind_dn` | string (nullable) | no | LDAP bind DN; omit to leave unchanged. (default: `null`) |
| `capath` | string (nullable) | no | CA certificate path; omit to leave unchanged. (default: `null`) |
| `comment` | string (nullable) | no | Optional free-text comment; omit to leave unchanged. (default: `null`) |
| `default` | boolean (nullable) | no | Default-realm-on-login flag; omit to leave unchanged. (default: `null`) |
| `filter` | string (nullable) | no | Custom LDAP search filter; omit to leave unchanged. (default: `null`) |
| `mode` | string (nullable) | no | LDAP connection type; omit to leave unchanged. (default: `null`) |
| `password` | string (nullable) | no | New AD bind password; redacted from all plans/logs/ledger. (default: `null`) |
| `port` | integer (nullable) | no | AD server port; omit to leave unchanged. (default: `null`) |
| `server1` | string (nullable) | no | Primary AD server address; omit to leave unchanged. (default: `null`) |
| `server2` | string (nullable) | no | Fallback AD server address; omit to leave unchanged. (default: `null`) |
| `sync_attributes` | string (nullable) | no | Sync-attribute map string; omit to leave unchanged. (default: `null`) |
| `sync_defaults_options` | string (nullable) | no | Sync-defaults options string; omit to leave unchanged. (default: `null`) |
| `user_classes` | string (nullable) | no | Allowed objectClass values; omit to leave unchanged. (default: `null`) |
| `verify` | boolean (nullable) | no | TLS verification flag; omit to leave unchanged. (default: `null`) |
| `delete_props` | array<string> (nullable) | no | Property names to clear. (default: `null`) |
| `digest` | string (nullable) | no | Optional SHA256 config digest to prevent concurrent modifications. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_realm_ldap_create`

MUTATION (MEDIUM): create an LDAP authentication realm. Dry-run by default. `base_dn` and
`user_attr` are REQUIRED (unlike AD, which needs neither on create).

PASSWORD REDACTION: `password` is UNCONDITIONALLY redacted identically to
pbs_realm_ad_create's. confirm=True executes and returns a dict; synchronous, no UPID. Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes | New LDAP realm name. |
| `server1` | string | yes | Primary LDAP server address. |
| `base_dn` | string | yes | LDAP base DN to search under (required for LDAP, unlike AD). |
| `user_attr` | string | yes | Username attribute used to map a userid to an LDAP dn (required for LDAP). |
| `bind_dn` | string (nullable) | no | LDAP bind DN for the service account. (default: `null`) |
| `capath` | string (nullable) | no | Path to a CA certificate file or directory to trust for TLS. (default: `null`) |
| `comment` | string (nullable) | no | Optional free-text comment. (default: `null`) |
| `default` | boolean (nullable) | no | True to make this the default realm preselected on login. (default: `null`) |
| `filter` | string (nullable) | no | Custom LDAP search filter for user sync. (default: `null`) |
| `mode` | string (nullable) | no | LDAP connection type: 'ldap', 'ldap+starttls', or 'ldaps'. (default: `null`) |
| `password` | string (nullable) | no | LDAP bind password for the service account; redacted from all plans/logs/ledger. (default: `null`) |
| `port` | integer (nullable) | no | LDAP server port. (default: `null`) |
| `server2` | string (nullable) | no | Fallback LDAP server address. (default: `null`) |
| `sync_attributes` | string (nullable) | no | Comma-separated key=value LDAP-attribute-to-PBS-field sync map, forwarded verbatim. (default: `null`) |
| `sync_defaults_options` | string (nullable) | no | Default sync-run options string, forwarded verbatim (exact syntax not live-verified). (default: `null`) |
| `user_classes` | string (nullable) | no | Comma-separated allowed objectClass values for user sync. (default: `null`) |
| `verify` | boolean (nullable) | no | Whether to verify the LDAP server's TLS certificate. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_realm_ldap_delete`

MUTATION (MEDIUM): permanently delete an LDAP realm. Dry-run by default — the PLAN reads
the realm's current config and flags that any users authenticating via it lose login access.
confirm=True executes and returns a dict; synchronous, no UPID. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes | LDAP realm name to delete. |
| `digest` | string (nullable) | no | Optional SHA256 config digest to prevent concurrent modifications. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_realm_ldap_get`

READ-ONLY: get one LDAP realm's config. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes | LDAP realm name to look up. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_realm_ldap_list`

READ-ONLY: list configured LDAP realms. Use pbs_realm_ldap_get for one realm's full
config. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_realm_ldap_update`

MUTATION (MEDIUM): update an LDAP realm's config. Dry-run by default — the PLAN reads the
realm's current config first. `password`, if supplied, is redacted identically to
pbs_realm_ldap_create's. confirm=True executes and returns a dict; synchronous, no UPID.
Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes | LDAP realm name to update. |
| `base_dn` | string (nullable) | no | LDAP base DN; omit to leave unchanged. (default: `null`) |
| `bind_dn` | string (nullable) | no | LDAP bind DN; omit to leave unchanged. (default: `null`) |
| `capath` | string (nullable) | no | CA certificate path; omit to leave unchanged. (default: `null`) |
| `comment` | string (nullable) | no | Optional free-text comment; omit to leave unchanged. (default: `null`) |
| `default` | boolean (nullable) | no | Default-realm-on-login flag; omit to leave unchanged. (default: `null`) |
| `filter` | string (nullable) | no | Custom LDAP search filter; omit to leave unchanged. (default: `null`) |
| `mode` | string (nullable) | no | LDAP connection type; omit to leave unchanged. (default: `null`) |
| `password` | string (nullable) | no | New LDAP bind password; redacted from all plans/logs/ledger. (default: `null`) |
| `port` | integer (nullable) | no | LDAP server port; omit to leave unchanged. (default: `null`) |
| `server1` | string (nullable) | no | Primary LDAP server address; omit to leave unchanged. (default: `null`) |
| `server2` | string (nullable) | no | Fallback LDAP server address; omit to leave unchanged. (default: `null`) |
| `sync_attributes` | string (nullable) | no | Sync-attribute map string; omit to leave unchanged. (default: `null`) |
| `sync_defaults_options` | string (nullable) | no | Sync-defaults options string; omit to leave unchanged. (default: `null`) |
| `user_attr` | string (nullable) | no | Username attribute; omit to leave unchanged. (default: `null`) |
| `user_classes` | string (nullable) | no | Allowed objectClass values; omit to leave unchanged. (default: `null`) |
| `verify` | boolean (nullable) | no | TLS verification flag; omit to leave unchanged. (default: `null`) |
| `delete_props` | array<string> (nullable) | no | Property names to clear. (default: `null`) |
| `digest` | string (nullable) | no | Optional SHA256 config digest to prevent concurrent modifications. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_realm_openid_create`

MUTATION (MEDIUM): create an OpenID authentication realm. Dry-run by default.

CLIENT-KEY REDACTION: `client_key` (the OAuth client secret), when supplied, is
UNCONDITIONALLY redacted from the plan, detail, and audit ledger (only
{"client-key": "[redacted]"} is recorded). confirm=True executes and returns a dict;
synchronous, no UPID. NOTE: the browser-based auth-url/login handshake is out of scope for
this plane (token-auth-shaped tools only) — see module docstring. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes | New OpenID realm name. |
| `issuer_url` | string | yes | OpenID issuer URL. |
| `client_id` | string | yes | OpenID client id. |
| `client_key` | string (nullable) | no | OpenID client secret; redacted from all plans/logs/ledger. (default: `null`) |
| `comment` | string (nullable) | no | Optional free-text comment. (default: `null`) |
| `default` | boolean (nullable) | no | True to make this the default realm preselected on login. (default: `null`) |
| `acr_values` | string (nullable) | no | OpenID ACR list string, forwarded verbatim. (default: `null`) |
| `audiences` | string (nullable) | no | OpenID audience list string, forwarded verbatim. (default: `null`) |
| `autocreate` | boolean (nullable) | no | Automatically create PBS users on first login if they don't exist. (default: `null`) |
| `prompt` | string (nullable) | no | OpenID prompt parameter. (default: `null`) |
| `scopes` | string (nullable) | no | OpenID scope list, SPACE-separated (schema default: 'email profile'). (default: `null`) |
| `username_claim` | string (nullable) | no | Claim to use as the unique username; the identity provider must guarantee uniqueness. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_realm_openid_delete`

MUTATION (MEDIUM): permanently delete an OpenID realm. Dry-run by default — the PLAN reads
the realm's current config and flags that any users authenticating via it lose login access.
confirm=True executes and returns a dict; synchronous, no UPID. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes | OpenID realm name to delete. |
| `digest` | string (nullable) | no | Optional SHA256 config digest to prevent concurrent modifications. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_realm_openid_get`

READ-ONLY: get one OpenID realm's config (never includes client_key). Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes | OpenID realm name to look up. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_realm_openid_list`

READ-ONLY: list configured OpenID realms. Use pbs_realm_openid_get for one realm's full
config. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_realm_openid_update`

MUTATION (MEDIUM): update an OpenID realm's config. Dry-run by default — the PLAN reads
the realm's current config first. `client_key`, if supplied, is redacted identically to
pbs_realm_openid_create's. confirm=True executes and returns a dict; synchronous, no UPID.

NOTE: there is NO username_claim parameter here — the live PBS schema makes it create-only
(set it at pbs_realm_openid_create time); PUT is additionalProperties:false, so accepting it
here would only hard-fail the whole update server-side. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `realm` | string | yes | OpenID realm name to update. |
| `issuer_url` | string (nullable) | no | OpenID issuer URL; omit to leave unchanged. (default: `null`) |
| `client_id` | string (nullable) | no | OpenID client id; omit to leave unchanged. (default: `null`) |
| `client_key` | string (nullable) | no | New OpenID client secret; redacted from all plans/logs/ledger. (default: `null`) |
| `comment` | string (nullable) | no | Optional free-text comment; omit to leave unchanged. (default: `null`) |
| `default` | boolean (nullable) | no | Default-realm-on-login flag; omit to leave unchanged. (default: `null`) |
| `acr_values` | string (nullable) | no | OpenID ACR list string; omit to leave unchanged. (default: `null`) |
| `audiences` | string (nullable) | no | OpenID audience list string; omit to leave unchanged. (default: `null`) |
| `autocreate` | boolean (nullable) | no | Autocreate-on-login flag; omit to leave unchanged. (default: `null`) |
| `prompt` | string (nullable) | no | OpenID prompt parameter; omit to leave unchanged. (default: `null`) |
| `scopes` | string (nullable) | no | OpenID scope list, SPACE-separated; omit to leave unchanged. (default: `null`) |
| `delete_props` | array<string> (nullable) | no | Property names to clear. (default: `null`) |
| `digest` | string (nullable) | no | Optional SHA256 config digest to prevent concurrent modifications. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_realm_pam_get`

READ-ONLY: get the built-in PAM realm's config (comment/default only). Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_realm_pam_set`

MUTATION (MEDIUM): update the built-in PAM realm's comment/default-preselect flag. Dry-run
by default. PAM has NO delete endpoint — the worst case here is a comment/default change, not
a lockout. confirm=True executes and returns a dict; synchronous, no UPID. Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `comment` | string (nullable) | no | Optional free-text comment; omit to leave unchanged. (default: `null`) |
| `default` | boolean (nullable) | no | Default-realm-on-login flag; omit to leave unchanged. (default: `null`) |
| `delete_props` | array<string> (nullable) | no | Property names to clear. (default: `null`) |
| `digest` | string (nullable) | no | Optional SHA256 config digest to prevent concurrent modifications. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_realm_pbs_get`

READ-ONLY: get the built-in PBS-auth realm's config (comment/default only). Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_realm_pbs_set`

MUTATION (MEDIUM): update the built-in PBS-auth realm's comment/default-preselect flag.
Dry-run by default. This realm has NO delete endpoint — the worst case here is a
comment/default change, not a lockout. confirm=True executes and returns a dict;
synchronous, no UPID. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `comment` | string (nullable) | no | Optional free-text comment; omit to leave unchanged. (default: `null`) |
| `default` | boolean (nullable) | no | Default-realm-on-login flag; omit to leave unchanged. (default: `null`) |
| `delete_props` | array<string> (nullable) | no | Property names to clear. (default: `null`) |
| `digest` | string (nullable) | no | Optional SHA256 config digest to prevent concurrent modifications. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_realm_sync`

MUTATION: sync PBS auth realm (LDAP/AD) users into PBS. Dry-run by default; confirm=True to
execute. Async — returns a UPID; check progress with pbs_tasks_list. remove_vanished=True
additionally DELETES PBS users no longer present in the directory (recoverable only by
re-sync, not a true undo). Needs PROXIMO_PBS_* config. (2026-07-10 audit: the old 'scope'
param was dropped — PBS /sync has no such field.)

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

READ-ONLY: get the config of one PBS remote sync-source by name. Returns a dict; no
password returned. Use pbs_remotes_list to list all remotes, or pbs_remote_update to
change this one. Needs PROXIMO_PBS_* config.

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
Use pbs_remote_get to inspect current config first.

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

READ-ONLY: list all PBS remote sync-sources. Returns a list of remote config dicts;
passwords are never included (PBS never returns them, and this strips defensively too).
Use pbs_remote_get for one remote's config. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_roles_list`

READ-ONLY: list PBS's built-in roles. Returns each role's id, privilege list, and
comment. PBS roles are a FIXED enum (Admin, Audit, NoAccess, Datastore*/Remote*/Tape* roles)
— unlike PVE, there is no create/update/delete endpoint for PBS roles. Use pbs_acl_update to
assign a role to a principal. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_snapshot_delete`

MUTATION (HIGH): delete a specific backup snapshot (a recovery point) from a PBS
datastore. Dry-run by default. Permanent — no undo. confirm=True to execute. Synchronous.
To shield a snapshot instead of deleting it use pbs_snapshot_protected_set(protected=True);
for bulk retention-based deletion use pbs_prune.

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
Does not affect backup data, retention, or protection — to shield the snapshot from
pruning/GC use pbs_snapshot_protected_set instead.
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
To annotate rather than protect a snapshot use pbs_snapshot_notes_set; to delete it
outright use pbs_snapshot_delete.

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

READ-ONLY: list backup snapshots in a PBS datastore with optional filters. Returns
snapshot metadata including backup type, ID, timestamp, size, owner, and protection
status; filter by namespace, backup_type (vm/ct/host), or backup_id. To delete one use
pbs_snapshot_delete; to change its protected flag or notes use pbs_snapshot_protected_set
or pbs_snapshot_notes_set.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `store` | string | yes | PBS datastore name. |
| `ns` | string (nullable) | no | Namespace path to filter by; omit for the root namespace. (default: `null`) |
| `backup_type` | string (nullable) | no | Backup type filter: 'vm', 'ct', or 'host'. (default: `null`) |
| `backup_id` | string (nullable) | no | Backup group ID (e.g. VMID/CTID or host name) to filter by. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_tasks_list`

READ-ONLY: list PBS tasks on a node. Defaults to 'localhost' (standard single-node PBS
name). Returns a list of task dicts; filter running=True for active tasks or errors=True
for failed ones. Use this to check on a UPID returned by pbs_gc_start, pbs_verify_start,
pbs_datastore_create, or pbs_datastore_delete. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PBS node name; defaults to 'localhost' (standard single-node PBS name). (default: `"localhost"`) |
| `limit` | integer (nullable) | no | Maximum number of tasks to return. (default: `null`) |
| `running` | boolean (nullable) | no | If True, return only currently-running tasks. (default: `null`) |
| `errors` | boolean (nullable) | no | If True, return only tasks that ended in error. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_tfa_add`

MUTATION (MEDIUM): add a TFA entry for a user. Dry-run by default.

SECRET-BEARING RESPONSE for type='recovery': confirm=True's result carries
{"recovery": [<one-time codes>], ...} — SERVER-GENERATED secret material, shown ONCE and
never retrievable again. It is never written to the audit ledger (the `detail=` dict below
never includes 'recovery'/'challenge'/'id'). `password`, if supplied, is UNCONDITIONALLY
redacted identically to pbs_user_create's. For type='totp', the caller supplies the secret
(via `totp`) — PBS does not generate one server-side for that type. confirm=True executes and
returns a dict; synchronous, no UPID. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | PBS user id to add a TFA entry for, format 'user@realm'. |
| `tfa_type` | string | yes | TFA entry type: 'totp', 'u2f', 'webauthn', 'recovery', or 'yubico'. |
| `description` | string (nullable) | no | Optional description to distinguish this entry from the user's others. (default: `null`) |
| `password` | string (nullable) | no | The ACTING user's own current password (re-authenticates the change); redacted from all plans/logs/ledger. (default: `null`) |
| `totp` | string (nullable) | no | For type='totp': the totp: URI the caller generated (PBS does not generate this). (default: `null`) |
| `value` | string (nullable) | no | Registration/verification value (e.g. the current TOTP code, or a WebAuthn/U2F challenge response). (default: `null`) |
| `challenge` | string (nullable) | no | For u2f: the original challenge string being responded to. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_tfa_delete`

MUTATION (HIGH, IRREVERSIBLE): permanently remove one TFA factor from a user. HIGH because
it WEAKENS authentication — an account-takeover enabler, and a lockout if it's the user's last
factor on a TFA-required realm. Dry-run by default — the PLAN flags the permanence and the
takeover/lockout risk. `password`, if supplied, is redacted identically to pbs_tfa_add's.
confirm=True executes and returns a dict; synchronous, no UPID. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | PBS user id, format 'user@realm'. |
| `tfa_id` | string | yes | TFA entry id to remove. |
| `password` | string (nullable) | no | The ACTING user's own current password; redacted from all plans/logs/ledger. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_tfa_entry_get`

READ-ONLY: get one TFA entry. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | PBS user id, format 'user@realm'. |
| `tfa_id` | string | yes | TFA entry id (from pbs_tfa_user_get). |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_tfa_list`

READ-ONLY: list ALL users' TFA configuration (per-user entries + lock state). Use
pbs_tfa_user_get to scope to one user. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_tfa_unlock`

MUTATION (HIGH): clear a user's TOTP lockout (PUT /access/users/{userid}/unlock-tfa — note
the path lives under /access/users/, not /access/tfa/{userid}/). HIGH because it removes the
anti-brute-force throttle guarding a 6-digit TOTP keyspace — an account-takeover enabler if
the lockout was triggered by a real guessing attack. Dry-run by default. confirm=True executes
and returns a dict whose result is a bool: whether the user was previously locked out.
Synchronous. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | PBS user id to clear a TOTP lockout for, format 'user@realm'. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_tfa_update`

MUTATION (MEDIUM): update a TFA entry's description/enabled flag. Dry-run by default —
the PLAN reads the current entry first. `password`, if supplied, is redacted identically to
pbs_tfa_add's. confirm=True executes and returns a dict; synchronous, no UPID. Needs
PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | PBS user id, format 'user@realm'. |
| `tfa_id` | string | yes | TFA entry id to update. |
| `description` | string (nullable) | no | New description; omit to leave unchanged. (default: `null`) |
| `enable` | boolean (nullable) | no | Whether the entry is currently enabled; False disables it immediately. Omit to leave unchanged. (default: `null`) |
| `password` | string (nullable) | no | The ACTING user's own current password; redacted from all plans/logs/ledger. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_tfa_user_get`

READ-ONLY: list one user's TFA entries. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | PBS user id, format 'user@realm'. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_tfa_webauthn_get`

READ-ONLY: get the server-wide WebAuthn relying-party config (id/origin/rp/
allow-subdomains). Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_tfa_webauthn_set`

MUTATION (MEDIUM): update the server-wide WebAuthn config. Dry-run by default — the PLAN
reads the current config and calls out that changing `rp_id` WILL break every existing
WebAuthn credential on the server, and `origin` MAY. confirm=True executes and returns a
dict; synchronous, no UPID. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `rp_id` | string (nullable) | no | Relying party ID (the domain name, no protocol/port/path). Changing this WILL break every existing WebAuthn credential on the server. (default: `null`) |
| `origin` | string (nullable) | no | Site origin (https:// URL, or http://localhost). Changing this MAY break existing WebAuthn credentials. (default: `null`) |
| `rp_name` | string (nullable) | no | Relying party display name (any text identifier). Changing this MAY break existing credentials. (default: `null`) |
| `allow_subdomains` | boolean (nullable) | no | Whether subdomains of origin are considered valid too. Defaults to true per PBS. (default: `null`) |
| `delete_props` | array<string> (nullable) | no | Property names to clear. (default: `null`) |
| `digest` | string (nullable) | no | Optional SHA256 config digest to prevent concurrent modifications. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_token_create`

MUTATION (MEDIUM): create an API token for a PBS user.

Dry-run by default. PBS has NO privsep concept (unlike PVE) — the new token has NO
privileges until an ACL entry grants it some (pbs_acl_update with
auth_id='{userid}!{token_name}'). confirm=True executes and returns a dict whose result
carries the token secret (value) ONCE — it is never written to the audit ledger and cannot
be retrieved again (only regenerated via pbs_token_update, which invalidates it).
Synchronous. Use pbs_user_tokens_list to see a user's existing tokens, or pbs_token_delete to
remove one. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | Owning PBS user, format 'user@realm'. |
| `token_name` | string | yes | Name for the new API token, unique per user. |
| `comment` | string (nullable) | no | Optional free-text comment describing the token's purpose. (default: `null`) |
| `enable` | boolean (nullable) | no | Whether the token is usable immediately; None defers to PBS's default (enabled). (default: `null`) |
| `expire` | integer (nullable) | no | Optional token expiry as a Unix timestamp; None/0 means no expiry. (default: `null`) |
| `digest` | string (nullable) | no | Optional SHA256 config digest to prevent concurrent modifications. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_token_delete`

MUTATION (MEDIUM, IRREVERSIBLE): permanently revoke a PBS API token. Dry-run by default —
the PLAN flags that revocation is permanent, the secret is gone forever, and any integration
using it loses PBS API access immediately. confirm=True executes and returns a dict;
synchronous, no UPID. Use pbs_user_tokens_list to see a user's tokens first, or
pbs_token_create to issue a new one instead. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | Owning PBS user, format 'user@realm'. |
| `token_name` | string | yes | Name of the API token to revoke. |
| `digest` | string (nullable) | no | Optional SHA256 config digest to prevent concurrent modifications. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_token_update`

MUTATION: update a PBS API token's metadata. Dry-run by default.

RISK IS CONDITIONAL: regenerate=False is MEDIUM (metadata-only); regenerate=True is HIGH —
it issues a brand-new secret and invalidates the OLD one IMMEDIATELY, with no grace period,
breaking any integration still using it. When regenerate=True, confirm=True's result carries
the NEW secret ONCE (key 'secret') — same never-in-ledger contract as pbs_token_create: the
detail dict passed to the audit ledger never contains it.

confirm=True executes and returns a dict; synchronous, no UPID. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | Owning PBS user, format 'user@realm'. |
| `token_name` | string | yes | Name of the API token to update. |
| `comment` | string (nullable) | no | Optional free-text comment; omit to leave unchanged. (default: `null`) |
| `enable` | boolean (nullable) | no | Whether the token is usable; False disables it immediately. Omit to leave unchanged. (default: `null`) |
| `expire` | integer (nullable) | no | Token expiry as a Unix timestamp; omit to leave unchanged. (default: `null`) |
| `regenerate` | boolean | no | If True, issue a BRAND-NEW secret and invalidate the old one immediately (RISK_HIGH — any system using the old token loses access instantly). (default: `false`) |
| `delete_props` | array<string> (nullable) | no | Property names to clear: only 'comment' is supported by PBS on this endpoint. (default: `null`) |
| `digest` | string (nullable) | no | Optional SHA256 config digest to prevent concurrent modifications. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_traffic_control_delete`

MUTATION (MEDIUM): remove a PBS traffic-control (bandwidth-limit) rule. Dry-run by default.

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
No rollback primitive. confirm=True to execute. Use pbs_traffic_controls_list to see
existing rules first, or pbs_traffic_control_delete to remove one.

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

READ-ONLY: list all PBS traffic-control bandwidth-limit rules. Returns active rules
with their rate-in/rate-out limits, network targets, and comment. Use
pbs_traffic_control_upsert to create or modify rules. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_user_create`

MUTATION (MEDIUM): create a PBS user. Dry-run by default.

PASSWORD REDACTION: `password` is OPTIONAL and, when supplied, a real credential — it is
UNCONDITIONALLY redacted from the plan, detail, and audit ledger (only
{"password": "[redacted]"} is recorded; omitted entirely when no password was given).

confirm=True executes and returns a dict; synchronous, no UPID. Use pbs_user_update to
change it afterward, or pbs_user_delete to remove it. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | New PBS user id, format 'user@realm'. |
| `comment` | string (nullable) | no | Optional free-text comment. (default: `null`) |
| `email` | string (nullable) | no | Optional email address. (default: `null`) |
| `enable` | boolean (nullable) | no | Whether the account can log in; None defers to PBS's default (enabled). (default: `null`) |
| `expire` | integer (nullable) | no | Optional account expiry as a Unix timestamp; None/0 means no expiry. (default: `null`) |
| `firstname` | string (nullable) | no | Optional first name. (default: `null`) |
| `lastname` | string (nullable) | no | Optional last name. (default: `null`) |
| `password` | string (nullable) | no | Optional initial password (min 8 chars per PBS); redacted from all plans/logs/ledger. Can also be set later via a separate password-change flow. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_user_delete`

MUTATION (MEDIUM): delete a PBS user. Dry-run by default — the PLAN reads the user's
current config and tokens to show what vanishes with it (permanent, no undo — any tokens
owned by this user are removed with it, and ACL entries granted directly to this userid
become orphaned). confirm=True executes and returns a dict; synchronous, no UPID. To disable
login without deleting, use pbs_user_update (enable=False) instead. Needs PROXIMO_PBS_*
config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | PBS user id to delete, format 'user@realm'. |
| `digest` | string (nullable) | no | Optional SHA256 config digest to prevent concurrent modifications. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_user_get`

READ-ONLY: get a PBS user's config. Returns userid, enabled flag, expiry, email, comment,
firstname/lastname (no tokens, no secrets). Use pbs_user_tokens_list for the user's API
tokens, or pbs_user_create/update/delete to manage the user. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | PBS user id to look up, format 'user@realm'. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_user_token_get`

READ-ONLY: get one PBS API token's metadata. Returns comment, expiry, enabled flag,
token-name, and tokenid — NOT the secret. Use pbs_user_tokens_list to enumerate a user's
tokens first. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | Owning PBS user, format 'user@realm'. |
| `token_name` | string | yes | Token name (the part after '!' in the full tokenid). |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_user_tokens_list`

READ-ONLY: list API tokens for a PBS user. Returns each token's token-name, tokenid,
comment, expiry, and enabled flag — NOT the secret (shown only once, at creation or
regeneration). Use pbs_token_create/update/delete to manage tokens. Needs PROXIMO_PBS_*
config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | Owning PBS user, format 'user@realm'. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_user_update`

MUTATION (MEDIUM): update a PBS user (enable=False stops login immediately). Dry-run by
default — the PLAN reads the user's current config first.

NOTE: this tool does NOT accept a password parameter — PBS's own PUT /access/users
'password' field is documented as ignored ("use PUT /access/password instead"); exposing a
working-looking no-op parameter here would mislead a caller into thinking it changed the
password.

confirm=True executes and returns a dict; synchronous, no UPID. Use pbs_user_get to see
current state first, or pbs_user_delete to remove the user instead. Needs PROXIMO_PBS_*
config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `userid` | string | yes | PBS user id to update, format 'user@realm'. |
| `comment` | string (nullable) | no | Optional free-text comment; omit to leave unchanged. (default: `null`) |
| `email` | string (nullable) | no | Optional email address; omit to leave unchanged. (default: `null`) |
| `enable` | boolean (nullable) | no | Whether the account can log in; False stops login. Omit to leave unchanged. (default: `null`) |
| `expire` | integer (nullable) | no | Account expiry as a Unix timestamp; omit to leave unchanged. (default: `null`) |
| `firstname` | string (nullable) | no | Optional first name; omit to leave unchanged. (default: `null`) |
| `lastname` | string (nullable) | no | Optional last name; omit to leave unchanged. (default: `null`) |
| `delete_props` | array<string> (nullable) | no | Property names to clear: any of 'comment', 'firstname', 'lastname', 'email'. (default: `null`) |
| `digest` | string (nullable) | no | Optional SHA256 config digest to prevent concurrent modifications. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN preview; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_users_list`

READ-ONLY: list all PBS users. Returns each user's userid, enabled flag, expiry, email,
comment, and firstname/lastname; include_tokens=True also embeds token metadata (never
secrets). Use pbs_user_get for one user's full config or pbs_user_tokens_list for a
dedicated token listing. Needs PROXIMO_PBS_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `include_tokens` | boolean | no | If True, embed each user's API tokens (metadata only, no secrets) in the result. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pbs_verify_start`

MUTATION: start an integrity verification run on a PBS datastore. Dry-run by default —
non-destructive (read-only check) but heavy I/O. confirm=True to execute; returns the
UPID (async task) — check progress with pbs_tasks_list.

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

List existing action objects with pmg_action_objects_list; attach this one to a rule with
pmg_ruledb_rule_action_attach. Needs PROXIMO_PMG_* config. confirm=True executes and returns
{"status": "ok", "result": <PMG's raw API response>}.

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

id_ comes from pmg_action_objects_list; to create a new one instead use pmg_action_bcc_create.
Only non-None fields are sent, others keep their current value. confirm=True executes and
returns {"status": "ok", "result": <PMG's raw API response>}.

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

Irreversible. PMG rejects deletion of non-editable (built-in) system action objects — check
the 'editable' flag via pmg_action_objects_list first. confirm=True executes and returns
{"status": "ok", "result": <PMG's raw API response>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Compound action object ID (e.g. '13_26') from pmg_action_objects_list. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_action_disclaimer_create`

MUTATION (LOW): create a disclaimer action object in the PMG RuleDB. Dry-run by default.

List existing action objects with pmg_action_objects_list; attach this one to a rule with
pmg_ruledb_rule_action_attach. Needs PROXIMO_PMG_* config. confirm=True executes and returns
{"status": "ok", "result": <PMG's raw API response>}.

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

id_ comes from pmg_action_objects_list. Only non-None fields are sent, others keep their
current value. confirm=True executes and returns {"status": "ok",
"result": <PMG's raw API response>}.

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

List existing action objects with pmg_action_objects_list; attach this one to a rule with
pmg_ruledb_rule_action_attach. Needs PROXIMO_PMG_* config. confirm=True executes and returns
{"status": "ok", "result": <PMG's raw API response>}.

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

id_ comes from pmg_action_objects_list; to create a new one instead use
pmg_action_field_create. confirm=True executes and returns {"status": "ok",
"result": <PMG's raw API response>}.

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

List existing action objects with pmg_action_objects_list; attach this one to a rule with
pmg_ruledb_rule_action_attach. Needs PROXIMO_PMG_* config. confirm=True executes and returns
{"status": "ok", "result": <PMG's raw API response>}.

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

id_ comes from pmg_action_objects_list; to create a new one instead use
pmg_action_notification_create. confirm=True executes and returns {"status": "ok",
"result": <PMG's raw API response>}.

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

READ-ONLY: list all PMG RuleDB action objects, including non-editable. Needs PROXIMO_PMG_* config.

Returns a list of dicts; each carries an 'editable' flag — non-editable ones are PMG built-ins
and cannot be modified via the API. For one rule's attached actions use
pmg_ruledb_rule_actions_list instead.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_action_removeattachments_create`

MUTATION (LOW): create a remove-attachments action object in the PMG RuleDB. Dry-run by default.

List existing action objects with pmg_action_objects_list; attach this one to a rule with
pmg_ruledb_rule_action_attach. Needs PROXIMO_PMG_* config. confirm=True executes and returns
{"status": "ok", "result": <PMG's raw API response>}.

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

id_ comes from pmg_action_objects_list. Only non-None fields are sent, others keep their
current value. confirm=True executes and returns {"status": "ok",
"result": <PMG's raw API response>}.

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

#### `pmg_apt_changelog`

READ-ONLY: get a package's changelog text on a PMG node.

GET /nodes/{node}/apt/changelog?name=…[&version=…]. Smoke-confirm: shape not live-verified.
The returned text is UPSTREAM/package-maintainer-authored (not Proxmox-authored) —
classified ADVERSARIAL content (taint.ADVERSARIAL_TOOLS), like pve_apt_changelog and
pbs_apt_changelog. Proxmox's API deliberately does not expose upgrade execution; the upgrade
itself happens at your console. This tool governs visibility only. Needs PROXIMO_PMG_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Package name to fetch the changelog for (e.g. as listed by pmg_apt_updates_list). |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node if omitted. (default: `null`) |
| `version` | string (nullable) | no | Specific package version to fetch the changelog for; omit for the latest available. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_apt_repositories_get`

READ-ONLY: get the current APT repository configuration of a PMG node.

GET /nodes/{node}/apt/repositories. Smoke-confirm: shape not live-verified — expected
{files, errors, digest, infos, standard-repos}. `files[].path` + entry index are the
coordinates pmg_apt_repository_set needs; `standard-repos[].handle` is what
pmg_apt_repository_add needs. Proxmox's API deliberately does not expose upgrade execution;
the upgrade itself happens at your console. This tool governs visibility and repo config
only. Needs PROXIMO_PMG_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node if omitted. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_apt_repository_add`

MUTATION: add a standard repository to the configuration on a PMG node.

RISK_MEDIUM: adds a new package source — affects the NEXT upgrade's package provenance.
CAPTURE: reads current repository state before planning (also readable directly via
pmg_apt_repositories_get); if unreadable -> complete=False. No automatic revert: removing an
added repository requires pmg_apt_repository_set to disable the resulting entry (there is no
repository-delete endpoint). Proxmox's API deliberately does not expose upgrade execution;
the upgrade itself happens at your console. This tool governs repo config only. Dry-run by
default (returns a PLAN); confirm=True executes (PUT, Smoke-confirm) and returns
{"status": "ok", "result": None}. Needs PROXIMO_PMG_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `handle` | string | yes | Handle identifying the standard repository to add (as returned by pmg_apt_repositories_get's standard-repos list, e.g. 'no-subscription'). |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node if omitted. (default: `null`) |
| `digest` | string (nullable) | no | Expected content digest of the repositories file, for optimistic-concurrency conflict detection. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the addition. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_apt_repository_set`

MUTATION: enable/disable one APT repository entry on a PMG node, by file path + index.

RISK_MEDIUM: changes where packages come from — affects the NEXT upgrade's package
provenance. CAPTURE: reads current repository state before planning (also readable directly
via pmg_apt_repositories_get); if unreadable -> complete=False. Proxmox's API deliberately
does not expose upgrade execution; the upgrade itself happens at your console. This tool
governs repo config only. Dry-run by default (returns a PLAN); confirm=True executes (POST,
Smoke-confirm) and returns {"status": "ok", "result": None}. Needs PROXIMO_PMG_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `path` | string | yes | Absolute path of the sources file containing the repository entry (as returned by pmg_apt_repositories_get). |
| `index` | integer | yes | 0-based index of the repository entry within that file (as returned by pmg_apt_repositories_get). |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node if omitted. (default: `null`) |
| `enabled` | boolean (nullable) | no | Set the entry's enabled state; omit to leave the enabled state unchanged. (default: `null`) |
| `digest` | string (nullable) | no | Expected content digest of the repositories file, for optimistic-concurrency conflict detection. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the change. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_apt_update_refresh`

MUTATION: resynchronize the APT package index on a PMG node (apt-get update).

RISK_LOW: no package state change — refreshes the local index cache only. Proxmox's API
deliberately does not expose upgrade execution; the upgrade itself happens at your console.
This tool governs visibility only — it does NOT install or upgrade any package. Idempotent —
safe to re-run any time. Dry-run by default (returns a PLAN); confirm=True executes (POST,
Smoke-confirm) and returns {"status": "submitted"|"ok", "result": <task id | None>}.
Needs PROXIMO_PMG_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node if omitted. (default: `null`) |
| `notify` | boolean (nullable) | no | If True, ask PMG to send a notification email about newly available packages. (default: `null`) |
| `quiet` | boolean (nullable) | no | If True, ask PMG to omit progress output suitable only for interactive logging. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes the index refresh. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_apt_updates_list`

READ-ONLY: list available package updates (cached apt index) on a PMG node.

GET /nodes/{node}/apt/update. Smoke-confirm: shape not live-verified. Proxmox's API
deliberately does not expose upgrade execution; the upgrade itself happens at your console.
This tool governs visibility only. To refresh this list first use pmg_apt_update_refresh.
Needs PROXIMO_PMG_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node if omitted. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_apt_versions`

READ-ONLY: get installed versions of important Proxmox packages on a PMG node.

GET /nodes/{node}/apt/versions. Smoke-confirm: shape not live-verified. Proxmox's API
deliberately does not expose upgrade execution; the upgrade itself happens at your console.
This tool governs visibility only. Needs PROXIMO_PMG_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node if omitted. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_backup_create`

MUTATION (LOW): create a PMG configuration backup. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

Additive — writes a new backup .tar.gz to /var/lib/pmg/backup/ on the target node; does not
touch existing backups or live config. Dry-run returns a PLAN; confirm=True executes and
returns {"status": "ok", "result": ...}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node. (default: `null`) |
| `notify` | string | no | Notification mode: always\|error\|never (default never). (default: `"never"`) |
| `statistic` | boolean | no | Whether to include mail statistics in the backup (default True). (default: `true`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_doctor`

READ-ONLY: PMG connectivity + credential/permission preflight — checks the global /version
endpoint and /access/users. Needs PROXIMO_PMG_* config.

Returns a dict with "version" and "permissions" keys; a successful call proves connectivity
and credentials together. Run this first when diagnosing PMG trouble, before other pmg_* tools.
PMG has no /access/permissions endpoint (that is PVE-only); "permissions" here is /access/users.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_domain_create`

MUTATION (LOW): create a managed mail domain. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

domain: domain name to add (e.g. 'example.com'). Dry-run returns a PLAN; confirm=True executes
and returns {"status": "ok", "result": ...}. Additive — reverse with pmg_domain_delete; list
current domains with pmg_domains_list.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `domain` | string | yes | Domain name to add as a managed mail domain, e.g. 'example.com'. |
| `comment` | string (nullable) | no | Optional free-text comment stored with the domain. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_domain_delete`

MUTATION (MEDIUM): delete a managed mail domain. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

Mail routing rules referencing this domain may break — review before confirming. No UNDO
primitive; recreate with pmg_domain_create if needed. Dry-run returns a PLAN; confirm=True
executes and returns {"status": "ok", "result": ...}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `domain` | string | yes | Managed mail domain name to delete, e.g. 'example.com'. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_domains_list`

READ-ONLY: list PMG managed mail domains. Needs PROXIMO_PMG_* config.

Returns a list of domain dicts (domain name + comment). Use pmg_domain_create/pmg_domain_delete
to manage domains.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_mynetworks_add`

MUTATION (LOW): add a CIDR to the PMG mynetworks trusted relay list. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

Only add CIDRs you control — trusted networks bypass spam filtering. Additive — reverse with
pmg_mynetworks_remove. Dry-run returns a PLAN; confirm=True executes and returns
{"status": "ok", "result": ...}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `cidr` | string | yes | Network in CIDR notation to trust as an internal relay, e.g. '10.0.0.0/8'. |
| `comment` | string (nullable) | no | Optional free-text comment stored with the mynetworks entry. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_mynetworks_remove`

MUTATION (MEDIUM): remove a CIDR from the PMG mynetworks trusted relay list. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

Internal senders in the range become subject to spam filtering after removal. No UNDO
primitive; re-add with pmg_mynetworks_add if needed. Dry-run returns a PLAN; confirm=True
executes and returns {"status": "ok", "result": ...}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `cidr` | string | yes | Network in CIDR notation to remove from the trusted mynetworks list. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_node_rrddata`

READ-ONLY: get PMG node RRD performance data. Needs PROXIMO_PMG_* config.

Returns a list of time-series dicts over the given timeframe (hour|day|week|month|year). For
a PVE hypervisor node's RRD data use pve_node_rrddata instead.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `timeframe` | string | yes | RRD timeframe: hour\|day\|week\|month\|year. |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node. (default: `null`) |
| `cf` | string (nullable) | no | RRD consolidation function: AVERAGE\|MAX. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_node_status`

READ-ONLY: get PMG node cpu/mem/disk/uptime status. Needs PROXIMO_PMG_* config.

Returns a dict with cpu/memory/disk/uptime fields for the node. This is the PMG node
(Proxmox Mail Gateway); for a PVE hypervisor node use pve_node_status instead.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_node_syslog`

READ-ONLY: get PMG node syslog entries. Needs PROXIMO_PMG_* config.

Returns a list of log-entry dicts. For a PVE hypervisor node's syslog use pve_node_syslog
instead; for RRD performance data use pmg_node_rrddata.

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

Dry-run returns a PLAN; confirm=True executes and returns {"status": "ok", "result": ...}.
Triggers redelivery attempts only — does not clear or drop queued mail. Check queue state
with pmg_postfix_qshape before and after.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_postfix_qshape`

READ-ONLY: get PMG Postfix queue shape. Needs PROXIMO_PMG_* config.

Returns a list of dicts, one row per domain plus a TOTAL row, each with queue-age bucket
counts. To force immediate re-delivery of the queued mail use pmg_postfix_flush.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_action`

MUTATION (MEDIUM; HIGH for action='delete' — permanent, irreversible). Apply an action to
quarantined message(s). Dry-run by default; confirm=True to execute. Needs PROXIMO_PMG_* config.

action: deliver|delete|mark-seen|mark-unseen|blocklist|welcomelist. Get mail_ids from
pmg_quarantine_spam (or the virus/attachment quarantine lists). Dry-run returns a PLAN;
confirm=True executes and returns {"status": "ok", "result": ...}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `action` | string | yes | Action to apply: deliver\|delete\|mark-seen\|mark-unseen\|blocklist\|welcomelist. |
| `mail_ids` | string | yes | Single quarantined mail ID, or a comma-separated list of IDs, to act on. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_attachment`

READ-ONLY: list attachment quarantine entries. Needs PROXIMO_PMG_* config.

Returns a list of dicts, one per quarantined attachment. pmail defaults to the authenticated
user when omitted. For spam quarantine use pmg_quarantine_spam; to act on entries use
pmg_quarantine_action.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `pmail` | string (nullable) | no | Scope the attachment quarantine read to this user's mailbox; defaults to the authenticated PMG user. (default: `null`) |
| `start` | integer (nullable) | no | Unix epoch start of the window; omit for no lower bound. (default: `null`) |
| `end` | integer (nullable) | no | Unix epoch end of the window; omit for no upper bound. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_blocklist_add`

MUTATION (LOW): add an address to the quarantine blocklist. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

Dry-run returns a PLAN; confirm=True executes and returns {"status": "ok", "result": ...}.
Additive — reverse with pmg_quarantine_blocklist_remove. View current entries with
pmg_quarantine_blocklist_list. pmail scopes the entry to a per-user blocklist (optional).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `address` | string | yes | Email address to add to the quarantine blocklist. |
| `pmail` | string (nullable) | no | Scope the blocklist entry to this user's mailbox; defaults to the authenticated PMG user. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_blocklist_list`

READ-ONLY: list PMG quarantine blocklist entries. Optional pmail to scope to one user.
Needs PROXIMO_PMG_* config.

Returns a list of blocklist-entry dicts. pmail is ALWAYS sent, defaulting to the authenticated
PMG user when omitted — an empty result means "none for that user," not "none globally." Use
pmg_quarantine_blocklist_add/pmg_quarantine_blocklist_remove to manage entries.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `pmail` | string (nullable) | no | Scope the blocklist read to this user's mailbox; defaults to the authenticated PMG user. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_blocklist_remove`

MUTATION (LOW): remove an address from the quarantine blocklist. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

pmail: optional per-user scope (defaults to authenticated user). No UNDO primitive; re-add
with pmg_quarantine_blocklist_add if needed. Dry-run returns a PLAN; confirm=True executes
and returns {"status": "ok", "result": ...}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `address` | string | yes | Email address to remove from the quarantine blocklist. |
| `pmail` | string (nullable) | no | Scope the blocklist removal to this user's mailbox; defaults to the authenticated PMG user. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_spam`

READ-ONLY: list PMG quarantined spam messages. Needs PROXIMO_PMG_* config.

Returns a list of dicts, one per quarantined message. For virus quarantine use
pmg_quarantine_virus; for attachment quarantine use pmg_quarantine_attachment. To act on
quarantined messages (deliver/delete/mark-seen/blocklist/welcomelist) use pmg_quarantine_action.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_spamstatus`

READ-ONLY: get spam quarantine status summary. Needs PROXIMO_PMG_* config.

Returns a dict of summary counts. For the individual quarantined messages use
pmg_quarantine_spam instead.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_spamusers`

READ-ONLY: list users with quarantined mail entries. Needs PROXIMO_PMG_* config.

Returns a list of per-user dicts. quarantine_type: spam|virus|attachment (default spam) —
sent to the PMG API as 'quarantine-type'. To list one user's messages use pmg_quarantine_spam
(pmail scope) or the matching virus/attachment tool.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | integer (nullable) | no | Unix epoch start of the window; omit for no lower bound. (default: `null`) |
| `end` | integer (nullable) | no | Unix epoch end of the window; omit for no upper bound. (default: `null`) |
| `quarantine_type` | string | no | Quarantine type to list users for: spam\|virus\|attachment (default spam). (default: `"spam"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_virus`

READ-ONLY: list virus quarantine entries. Needs PROXIMO_PMG_* config.

Returns a list of dicts, one per quarantined virus message. pmail defaults to the
authenticated user when omitted. For spam quarantine use pmg_quarantine_spam; to act on
entries use pmg_quarantine_action.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `pmail` | string (nullable) | no | Scope the virus quarantine read to this user's mailbox; defaults to the authenticated PMG user. (default: `null`) |
| `start` | integer (nullable) | no | Unix epoch start of the window; omit for no lower bound. (default: `null`) |
| `end` | integer (nullable) | no | Unix epoch end of the window; omit for no upper bound. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_virusstatus`

READ-ONLY: get virus quarantine status summary. Needs PROXIMO_PMG_* config.

Returns a dict of summary counts. For the individual quarantined messages use
pmg_quarantine_virus instead.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_welcomelist_add`

MUTATION (LOW): add an address to the quarantine welcomelist. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

pmail: optional per-user scope (defaults to authenticated user). Additive — reverse with
pmg_quarantine_welcomelist_remove. Dry-run returns a PLAN; confirm=True executes and returns
{"status": "ok", "result": ...}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `address` | string | yes | Email address to add to the quarantine welcomelist. |
| `pmail` | string (nullable) | no | Scope the welcomelist entry to this user's mailbox; defaults to the authenticated PMG user. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_welcomelist_list`

READ-ONLY: list PMG quarantine welcomelist entries. Optional pmail to scope to one user.
Needs PROXIMO_PMG_* config.

Returns a list of welcomelist-entry dicts; pmail defaults to the authenticated user when
omitted. For the blocklist use pmg_quarantine_blocklist_list. Use
pmg_quarantine_welcomelist_add/pmg_quarantine_welcomelist_remove to manage entries.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `pmail` | string (nullable) | no | Scope the welcomelist read to this user's mailbox; defaults to the authenticated PMG user. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_quarantine_welcomelist_remove`

MUTATION (LOW): remove an address from the quarantine welcomelist. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

pmail: optional per-user scope (defaults to authenticated user). No UNDO primitive; re-add
with pmg_quarantine_welcomelist_add if needed. Dry-run returns a PLAN; confirm=True executes
and returns {"status": "ok", "result": ...}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `address` | string | yes | Email address to remove from the quarantine welcomelist. |
| `pmail` | string (nullable) | no | Scope the welcomelist removal to this user's mailbox; defaults to the authenticated PMG user. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_relay_config`

READ-ONLY: get PMG SMTP relay/smarthost configuration. Needs PROXIMO_PMG_* config.

Returns the full mail config section as a dict, including relay host, relay port, and other
SMTP delivery settings. Lives at /config/mail — there is no separate /config/relay endpoint.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_digest`

READ-ONLY: get the PMG RuleDB digest (change-detection hash). Needs PROXIMO_PMG_* config.

Returns a dict with the current hash. The digest changes whenever any ruledb configuration is
modified — poll it to detect drift cheaply instead of re-fetching pmg_ruledb_rules_list.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_action_attach`

MUTATION (MEDIUM): attach an action group to a PMG RuleDB rule. Dry-run by default.

ogroup comes from pmg_action_objects_list (the integer part before '_' in a compound ID like
'13_26'); list a rule's current actions with pmg_ruledb_rule_actions_list. Additive — only
affects mail flow once the rule is active. confirm=True executes and returns {"status": "ok",
"result": <PMG's raw API response>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Rule ID to attach the action group to. |
| `ogroup` | string | yes | Numeric action group ID from pmg_action_objects_list to attach to the rule. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_action_detach`

MUTATION (MEDIUM): detach an action group from a PMG RuleDB rule. Dry-run by default.

Only removes the binding — the action object itself is untouched (delete it separately with
pmg_action_delete if desired). List current actions with pmg_ruledb_rule_actions_list.
confirm=True executes and returns {"status": "ok", "result": <PMG's raw API response>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Rule ID to detach the action group from. |
| `ogroup` | string | yes | Numeric action group ID currently attached to the rule to detach. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_actions_list`

READ-ONLY: list the 'actions' objects attached to a PMG RuleDB rule. Needs PROXIMO_PMG_* config.

Returns a list of action-object dicts, extracted from the same config pmg_ruledb_rule_get
returns — the dedicated .../actions endpoint 501s on PMG 9.1, so this reads /config instead.
id_: rule ID (e.g. '100') from pmg_ruledb_rules_list.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | RuleDB rule ID (positive integer string, e.g. '100'). |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_create`

MUTATION (MEDIUM): create a PMG RuleDB rule. Dry-run by default.

Creates the rule shell only — attach condition/action groups afterward with
pmg_ruledb_rule_from_attach and its sibling attach tools; list existing rules with
pmg_ruledb_rules_list. active defaults False (live mail is affected only once active).
confirm=True executes and returns {"status": "ok", "result": <new rule ID assigned by PMG>}.

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

Irreversible — permanently removes the rule and all its group bindings (the who/what/when/
action groups themselves survive). List rules first with pmg_ruledb_rules_list.
confirm=True executes and returns {"status": "ok", "result": <PMG's raw API response>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Rule ID (positive integer string, e.g. '100'). |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_from_attach`

MUTATION (MEDIUM): attach a 'from' (sender/who) group to a PMG RuleDB rule. Dry-run by default.

ogroup comes from pmg_who_groups_list; list a rule's current 'from' groups with
pmg_ruledb_rule_from_list. Additive — only affects mail flow once the rule is active.
confirm=True executes and returns {"status": "ok", "result": <PMG's raw API response>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Rule ID to attach the group to. |
| `ogroup` | string | yes | Numeric 'who' group ID from pmg_who_groups_list to attach as the 'from' condition. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_from_detach`

MUTATION (MEDIUM): detach a 'from' (sender/who) group from a PMG RuleDB rule. Dry-run by default.

Only removes the binding — the who-group itself is untouched (delete it separately with
pmg_who_group_delete if desired). List current bindings with pmg_ruledb_rule_from_list.
confirm=True executes and returns {"status": "ok", "result": <PMG's raw API response>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Rule ID to detach the group from. |
| `ogroup` | string | yes | Numeric 'who' group ID currently attached as the 'from' condition to detach. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_from_list`

READ-ONLY: list the 'from' objects attached to a PMG RuleDB rule. Needs PROXIMO_PMG_* config.

Returns a list of object dicts. id_: rule ID (e.g. '100') from pmg_ruledb_rules_list. Use
pmg_ruledb_rule_to_list for the 'to' side, and the what/when/actions counterparts for the rest.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | RuleDB rule ID (positive integer string, e.g. '100'). |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_get`

READ-ONLY: get a PMG RuleDB rule's configuration. Needs PROXIMO_PMG_* config.

Returns a dict of the rule's config. id_: rule ID (e.g. '100') from pmg_ruledb_rules_list.
For the rule's individual from/to/what/when object lists use pmg_ruledb_rule_from_list and
its to/what/when/actions siblings.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | RuleDB rule ID (positive integer string, e.g. '100'). |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_to_attach`

MUTATION (MEDIUM): attach a 'to' (recipient/who) group to a PMG RuleDB rule. Dry-run by default.

ogroup comes from pmg_who_groups_list; list a rule's current 'to' groups with
pmg_ruledb_rule_to_list. Additive — only affects mail flow once the rule is active.
confirm=True executes and returns {"status": "ok", "result": <PMG's raw API response>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Rule ID to attach the group to. |
| `ogroup` | string | yes | Numeric 'who' group ID from pmg_who_groups_list to attach as the 'to' condition. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_to_detach`

MUTATION (MEDIUM): detach a 'to' (recipient/who) group from a PMG RuleDB rule. Dry-run by default.

Only removes the binding — the who-group itself is untouched (delete it separately with
pmg_who_group_delete if desired). List current bindings with pmg_ruledb_rule_to_list.
confirm=True executes and returns {"status": "ok", "result": <PMG's raw API response>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Rule ID to detach the group from. |
| `ogroup` | string | yes | Numeric 'who' group ID currently attached as the 'to' condition to detach. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_to_list`

READ-ONLY: list the 'to' objects attached to a PMG RuleDB rule. Needs PROXIMO_PMG_* config.

Returns a list of object dicts. id_: rule ID (e.g. '100') from pmg_ruledb_rules_list. Use
pmg_ruledb_rule_from_list for the 'from' side, and the what/when/actions counterparts for the rest.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | RuleDB rule ID (positive integer string, e.g. '100'). |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_update`

MUTATION (MEDIUM): update a PMG RuleDB rule configuration. Dry-run by default.

Changes rule-level fields only (name/priority/active/direction/AND-invert flags) — to
attach or detach condition/action groups use pmg_ruledb_rule_from_attach and its sibling
attach/detach tools. Only non-None fields are sent. confirm=True executes and returns
{"status": "ok", "result": <PMG's raw API response>}.

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

ogroup comes from pmg_what_groups_list; list a rule's current 'what' groups with
pmg_ruledb_rule_what_list. Additive — only affects mail flow once the rule is active.
confirm=True executes and returns {"status": "ok", "result": <PMG's raw API response>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Rule ID to attach the group to. |
| `ogroup` | string | yes | Numeric 'what' group ID from pmg_what_groups_list to attach as a content condition. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_what_detach`

MUTATION (MEDIUM): detach a 'what' (content) group from a PMG RuleDB rule. Dry-run by default.

Only removes the binding — the what-group itself is untouched (delete it separately with
pmg_what_group_delete if desired). List current bindings with pmg_ruledb_rule_what_list.
confirm=True executes and returns {"status": "ok", "result": <PMG's raw API response>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Rule ID to detach the group from. |
| `ogroup` | string | yes | Numeric 'what' group ID currently attached as a content condition to detach. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_what_list`

READ-ONLY: list the 'what' objects attached to a PMG RuleDB rule. Needs PROXIMO_PMG_* config.

Returns a list of object dicts. id_: rule ID (e.g. '100') from pmg_ruledb_rules_list. Use
pmg_ruledb_rule_when_list for the 'when' side, and the from/to/actions counterparts for the rest.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | RuleDB rule ID (positive integer string, e.g. '100'). |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_when_attach`

MUTATION (MEDIUM): attach a 'when' (timeframe) group to a PMG RuleDB rule. Dry-run by default.

ogroup comes from pmg_when_groups_list; list a rule's current 'when' groups with
pmg_ruledb_rule_when_list. Additive — only affects mail flow once the rule is active.
confirm=True executes and returns {"status": "ok", "result": <PMG's raw API response>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Rule ID to attach the group to. |
| `ogroup` | string | yes | Numeric 'when' group ID from pmg_when_groups_list to attach as a timeframe condition. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_when_detach`

MUTATION (MEDIUM): detach a 'when' (timeframe) group from a PMG RuleDB rule. Dry-run by default.

Only removes the binding — the when-group itself is untouched (delete it separately with
pmg_when_group_delete if desired). List current bindings with pmg_ruledb_rule_when_list.
confirm=True executes and returns {"status": "ok", "result": <PMG's raw API response>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Rule ID to detach the group from. |
| `ogroup` | string | yes | Numeric 'when' group ID currently attached as a timeframe condition to detach. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rule_when_list`

READ-ONLY: list the 'when' objects attached to a PMG RuleDB rule. Needs PROXIMO_PMG_* config.

Returns a list of object dicts. id_: rule ID (e.g. '100') from pmg_ruledb_rules_list. Use
pmg_ruledb_rule_what_list for the 'what' side, and the from/to/actions counterparts for the rest.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | RuleDB rule ID (positive integer string, e.g. '100'). |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_ruledb_rules_list`

READ-ONLY: list all PMG RuleDB rules (hydrated rule list). Needs PROXIMO_PMG_* config.

Returns the full hydrated rule list as dicts, including from/to/what/when/actions for each
rule. For one rule use pmg_ruledb_rule_get; to detect drift without the full fetch use
pmg_ruledb_digest.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_service_control`

MUTATION (MEDIUM): start, stop, restart, or reload a PMG service. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

WARNING: stop on postfix/pmgproxy/pmgdaemon interrupts mail delivery until manually restarted.
Check current state first with pmg_service_status. Dry-run returns a PLAN; confirm=True
executes and returns {"status": "ok", "result": ...}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `service` | string | yes | PMG service name, e.g. postfix, pmgproxy, pmgdaemon, clamav, spamassassin. |
| `action` | string | yes | Control action: start\|stop\|restart\|reload. |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_service_status`

READ-ONLY: get the status of a PMG system service. Needs PROXIMO_PMG_* config.

Returns a dict with the service's state. service: e.g. 'postfix', 'pmgproxy', 'pmgdaemon',
'clamav', 'spamassassin' — no hardcoded enum, unknown names return a PMG 404. Use
pmg_service_control to start/stop/restart/reload the service.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `service` | string | yes | PMG service name, e.g. postfix, pmgproxy, pmgdaemon, pmgmirror, pmgtunnel, pmg-smtp-filter, clamav, spamassassin. |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_spam_config`

READ-ONLY: get PMG spam filter configuration. Needs PROXIMO_PMG_* config.

Returns a dict of the current spam-filter settings (score thresholds, Bayes/AWL/Razor/RBL
toggles, etc). Use pmg_spam_config_update to change them.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_spam_config_update`

MUTATION (MEDIUM): update PMG spam filter configuration. Dry-run by default.
confirm=True to execute. Needs PROXIMO_PMG_* config.

Only non-None fields are sent — omitted fields keep their current PMG value; delete resets
named fields to defaults, effective immediately on new inbound mail. Read current values with
pmg_spam_config. Dry-run returns a PLAN; confirm=True executes and returns {"status": "ok",
"result": ...}.

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

READ-ONLY: get PMG per-domain mail statistics. Optional Unix epoch start/end timespan.
Needs PROXIMO_PMG_* config.

Returns a list of per-domain stat dicts. For overall totals use pmg_statistics_mail; for
time-bucketed counts use pmg_statistics_mailcount. start/end map to starttime/endtime.

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

READ-ONLY: get per-bucket mail count statistics. Needs PROXIMO_PMG_* config.

Returns a list of time-bucketed count dicts (bucket size set by timespan, default 1 hour).
For today's single aggregate total use pmg_statistics_mail instead.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | integer (nullable) | no | Unix epoch start of the window; omit for no lower bound. (default: `null`) |
| `end` | integer (nullable) | no | Unix epoch end of the window; omit for no upper bound. (default: `null`) |
| `timespan` | integer | no | Histogram bucket size in seconds, 3600-31622400 (default 3600 = 1 hour). (default: `3600`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_statistics_receiver`

READ-ONLY: get per-recipient mail statistics. Needs PROXIMO_PMG_* config.

Returns a list of per-recipient stat dicts. orderby is a raw sort-spec passthrough here
(unlike pmg_statistics_sender, which ignores it). For per-sender stats use
pmg_statistics_sender.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | integer (nullable) | no | Unix epoch start of the window; omit for no lower bound. (default: `null`) |
| `end` | integer (nullable) | no | Unix epoch end of the window; omit for no upper bound. (default: `null`) |
| `filter_` | string (nullable) | no | Optional search string to filter recipients. (default: `null`) |
| `orderby` | string (nullable) | no | Raw sort spec passed through to the PMG API. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_statistics_recent`

READ-ONLY: get PMG recent mail statistics. hours: 1-24 window. Needs PROXIMO_PMG_* config.

Returns a list of dicts covering only the last `hours`. For today's full aggregate totals use
pmg_statistics_mail instead.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `hours` | integer | no | Lookback window in hours, 1-24 (default 1). (default: `1`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_statistics_sender`

READ-ONLY: get per-sender mail statistics. Needs PROXIMO_PMG_* config.

Returns a list of per-sender stat dicts. orderby is accepted for compatibility but IGNORED —
PMG rejects it here (HTTP 400) unlike pmg_statistics_receiver, which does honor it. For
per-recipient stats use pmg_statistics_receiver.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | integer (nullable) | no | Unix epoch start of the window; omit for no lower bound. (default: `null`) |
| `end` | integer (nullable) | no | Unix epoch end of the window; omit for no upper bound. (default: `null`) |
| `filter_` | string (nullable) | no | Optional search string to filter senders. (default: `null`) |
| `orderby` | string (nullable) | no | Accepted for compatibility but ignored — PMG 9.1 rejects orderby on this endpoint. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_statistics_spamscores`

READ-ONLY: get PMG spam score distribution statistics. Optional Unix epoch start/end timespan.
Needs PROXIMO_PMG_* config.

Returns a list of dicts bucketing message counts by spam score. For the raw quarantined spam
messages use pmg_quarantine_spam instead. start/end map to starttime/endtime.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | integer (nullable) | no | Unix epoch start of the stats window; omit for no lower bound. (default: `null`) |
| `end` | integer (nullable) | no | Unix epoch end of the stats window; omit for no upper bound. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_statistics_virus`

READ-ONLY: get PMG virus statistics. Optional Unix epoch start/end timespan.
Needs PROXIMO_PMG_* config.

Returns a list of dicts with virus-detection counts over the window. For per-message virus
quarantine entries use pmg_quarantine_virus instead. start/end map to starttime/endtime.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `start` | integer (nullable) | no | Unix epoch start of the stats window; omit for no lower bound. (default: `null`) |
| `end` | integer (nullable) | no | Unix epoch end of the stats window; omit for no upper bound. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_tasks_list`

READ-ONLY: list PMG tasks on a node. Needs PROXIMO_PMG_* config.

Returns a list of task dicts. errors=True returns only failed tasks. For a PVE hypervisor
node's tasks use pve_tasks_list instead.

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

READ-ONLY: get tracking detail for a specific mail ID. Needs PROXIMO_PMG_* config.

Returns a list of delivery-hop dicts for that message. Get id_ from pmg_tracker_list first;
it is validated path-segment-safe (rejects '..', '/', control/whitespace chars).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `id_` | string | yes | Mail/queue tracker ID to fetch detail for. |
| `node` | string (nullable) | no | PMG node name; defaults to the configured node. (default: `null`) |
| `start` | integer (nullable) | no | Unix epoch start of the tracker window; omit for no lower bound. (default: `null`) |
| `end` | integer (nullable) | no | Unix epoch end of the tracker window; omit for no upper bound. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_tracker_list`

READ-ONLY: list mail tracking entries. Needs PROXIMO_PMG_* config.

Returns a list of dicts, one per tracked message (up to `limit`, default 2000). Use
pmg_tracker_detail for the full delivery trace of one message ID from this list.

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

Dry-run returns a PLAN; confirm=True executes and returns {"status": "ok", "result": ...}.
Additive — reverse with pmg_transport_delete. Overrides MX-based routing for the given domain.

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

Mail for the domain falls back to default PMG routing (MX lookup) afterward. No UNDO
primitive; recreate with pmg_transport_create if needed. Dry-run returns a PLAN; confirm=True
executes and returns {"status": "ok", "result": ...}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `domain` | string | yes | Destination domain whose transport rule should be deleted. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_what_group_create`

MUTATION (LOW): create a PMG RuleDB 'what' object group. Dry-run by default.

Creates an empty group — add match objects with pmg_what_object_add; list existing groups with
pmg_what_groups_list. Needs PROXIMO_PMG_* config. confirm=True executes and returns
{"status": "ok", "result": <new ogroup ID assigned by PMG>}.

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

Irreversible — also removes every object within the group. List groups first with
pmg_what_groups_list; to remove just one object instead use pmg_what_object_delete.
confirm=True executes and returns {"status": "ok", "result": <PMG's raw API response>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | Numeric 'what' object group ID (e.g. '8') from pmg_what_groups_list. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_what_group_get`

READ-ONLY: get a PMG RuleDB 'what' object group's configuration. Needs PROXIMO_PMG_* config.

Returns a dict of the group's config. ogroup: numeric ID (e.g. '2') from pmg_what_groups_list —
NOT the group name. Use pmg_what_group_objects to list the objects inside the group.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | 'what' object group numeric ID (e.g. '2') from pmg_what_groups_list — not the group name. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_what_group_objects`

READ-ONLY: list the objects in a PMG RuleDB 'what' object group. Needs PROXIMO_PMG_* config.

Returns a list of object dicts. ogroup: numeric ID (e.g. '2') from pmg_what_groups_list — NOT
the group name. Use pmg_what_group_get for the group's own config (not its member objects).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | 'what' object group numeric ID (e.g. '2') from pmg_what_groups_list — not the group name. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_what_group_update`

MUTATION (MEDIUM): update a PMG RuleDB 'what' object group config. Dry-run by default.

Renames or reconfigures the group itself; to change its match objects use
pmg_what_object_add/pmg_what_object_update/pmg_what_object_delete. Only non-None fields are
sent, others keep their current value. confirm=True executes and returns {"status": "ok",
"result": <PMG's raw API response>}.

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

READ-ONLY: list all PMG RuleDB 'what' object groups. Needs PROXIMO_PMG_* config.

Returns a list of group dicts (id/name/comment). For 'who' or 'when' groups use
pmg_who_groups_list / pmg_when_groups_list. Use pmg_what_group_get for one group's config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_what_object_add`

MUTATION (LOW): add an object to a PMG RuleDB 'what' object group. Dry-run by default.

To create the group first use pmg_what_group_create; list its objects with
pmg_what_group_objects. If the group is already attached to a rule, the new object affects
mail matching immediately. confirm=True executes and returns {"status": "ok",
"result": <PMG's raw API response>}.

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

Irreversible. id_ comes from pmg_what_group_objects; to delete the whole group instead use
pmg_what_group_delete. confirm=True executes and returns {"status": "ok",
"result": <PMG's raw API response>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | Numeric 'what' object group ID (e.g. '8') from pmg_what_groups_list. |
| `id_` | string | yes | Object ID (numeric string) from pmg_what_group_objects. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_what_object_update`

MUTATION (MEDIUM): update an object in a PMG RuleDB 'what' object group. Dry-run by default.

id_ comes from pmg_what_group_objects; type_ must match the object's existing type. Only
non-None fields are sent, others keep their current value. confirm=True executes and returns
{"status": "ok", "result": <PMG's raw API response>}.

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

Creates an empty group — add timeframe objects with pmg_when_object_add; list existing groups
with pmg_when_groups_list. Needs PROXIMO_PMG_* config. confirm=True executes and returns
{"status": "ok", "result": <new ogroup ID assigned by PMG>}.

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

Irreversible — also removes every timeframe within the group. List groups first with
pmg_when_groups_list; to remove just one timeframe instead use pmg_when_object_delete.
confirm=True executes and returns {"status": "ok", "result": <PMG's raw API response>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | Numeric 'when' object group ID (e.g. '4') from pmg_when_groups_list. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_when_group_get`

READ-ONLY: get a PMG RuleDB 'when' object group's configuration. Needs PROXIMO_PMG_* config.

Returns a dict of the group's config. ogroup: numeric ID (e.g. '2') from pmg_when_groups_list —
NOT the group name. Use pmg_when_group_objects to list the objects inside the group.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | 'when' object group numeric ID (e.g. '2') from pmg_when_groups_list — not the group name. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_when_group_objects`

READ-ONLY: list the objects in a PMG RuleDB 'when' object group. Needs PROXIMO_PMG_* config.

Returns a list of object dicts. ogroup: numeric ID (e.g. '2') from pmg_when_groups_list — NOT
the group name. Use pmg_when_group_get for the group's own config (not its member objects).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | 'when' object group numeric ID (e.g. '2') from pmg_when_groups_list — not the group name. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_when_group_update`

MUTATION (MEDIUM): update a PMG RuleDB 'when' object group config. Dry-run by default.

Renames or reconfigures the group itself; to change its timeframes use
pmg_when_object_add/pmg_when_object_update/pmg_when_object_delete. Only non-None fields are
sent, others keep their current value. confirm=True executes and returns {"status": "ok",
"result": <PMG's raw API response>}.

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

READ-ONLY: list all PMG RuleDB 'when' object groups. Needs PROXIMO_PMG_* config.

Returns a list of group dicts (id/name/comment). For 'who' or 'what' groups use
pmg_who_groups_list / pmg_what_groups_list. Use pmg_when_group_get for one group's config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_when_object_add`

MUTATION (LOW): add a timeframe object to a PMG RuleDB 'when' object group. Dry-run by default.

To create the group first use pmg_when_group_create; list its objects with
pmg_when_group_objects. confirm=True executes and returns {"status": "ok",
"result": <PMG's raw API response>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | Numeric 'when' object group ID (e.g. '4') from pmg_when_groups_list. |
| `start` | string | yes | Timeframe start time in H:i format (e.g. '08:00'). |
| `end` | string | yes | Timeframe end time in H:i format (e.g. '17:00'). |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_when_object_delete`

MUTATION (MEDIUM): delete a timeframe object from a PMG RuleDB 'when' object group. Dry-run by default.

Irreversible. id_ comes from pmg_when_group_objects; to delete the whole group instead use
pmg_when_group_delete. confirm=True executes and returns {"status": "ok",
"result": <PMG's raw API response>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | Numeric 'when' object group ID (e.g. '4') from pmg_when_groups_list. |
| `id_` | string | yes | Object ID (numeric string) from pmg_when_group_objects. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_when_object_update`

MUTATION (MEDIUM): update a timeframe object in a PMG RuleDB 'when' object group. Dry-run by default.

id_ comes from pmg_when_group_objects; to add a new timeframe instead use
pmg_when_object_add. confirm=True executes and returns {"status": "ok",
"result": <PMG's raw API response>}.

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

Creates an empty group — add match objects with pmg_who_object_add; list existing groups with
pmg_who_groups_list. Needs PROXIMO_PMG_* config. confirm=True executes and returns
{"status": "ok", "result": <new ogroup ID assigned by PMG>}.

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

Irreversible — also removes every object within the group. List groups first with
pmg_who_groups_list; to remove just one object instead use pmg_who_object_delete.
confirm=True executes and returns {"status": "ok", "result": <PMG's raw API response>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | Numeric 'who' object group ID (e.g. '2') from pmg_who_groups_list. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_who_group_get`

READ-ONLY: get a PMG RuleDB 'who' object group's configuration. Needs PROXIMO_PMG_* config.

Returns a dict of the group's config. ogroup: numeric ID (e.g. '2') from pmg_who_groups_list —
NOT the group name. Use pmg_who_group_objects to list the objects inside the group.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | 'who' object group numeric ID (e.g. '2') from pmg_who_groups_list — not the group name. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_who_group_objects`

READ-ONLY: list the objects in a PMG RuleDB 'who' object group. Needs PROXIMO_PMG_* config.

Returns a list of object dicts. ogroup: numeric ID (e.g. '2') from pmg_who_groups_list — NOT
the group name. Use pmg_who_group_get for the group's own config (not its member objects).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | 'who' object group numeric ID (e.g. '2') from pmg_who_groups_list — not the group name. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_who_group_update`

MUTATION (MEDIUM): update a PMG RuleDB 'who' object group config. Dry-run by default.

Renames or reconfigures the group itself; to change its match objects use
pmg_who_object_add/pmg_who_object_update/pmg_who_object_delete. Only non-None fields are
sent, others keep their current value. confirm=True executes and returns {"status": "ok",
"result": <PMG's raw API response>}.

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

READ-ONLY: list all PMG RuleDB 'who' object groups. Needs PROXIMO_PMG_* config.

Returns a list of group dicts (id/name/comment). For 'what' or 'when' groups use
pmg_what_groups_list / pmg_when_groups_list. Use pmg_who_group_get for one group's config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_who_object_add`

MUTATION (LOW): add an object to a PMG RuleDB 'who' object group. Dry-run by default.

To create the group first use pmg_who_group_create; list its objects with
pmg_who_group_objects. If the group is already attached to a rule, the new object affects
mail matching immediately. confirm=True executes and returns {"status": "ok",
"result": <PMG's raw API response>}.

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

Irreversible. id_ comes from pmg_who_group_objects; to delete the whole group instead use
pmg_who_group_delete. confirm=True executes and returns {"status": "ok",
"result": <PMG's raw API response>}.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `ogroup` | string | yes | Numeric 'who' object group ID (e.g. '2') from pmg_who_groups_list. |
| `id_` | string | yes | Object ID (numeric string) from pmg_who_group_objects. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN; True executes the mutation. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pmg_who_object_update`

MUTATION (MEDIUM): update an object in a PMG RuleDB 'who' object group. Dry-run by default.

id_ comes from pmg_who_group_objects; type_ must match the object's existing type. Only
non-None fields are sent, others keep their current value. confirm=True executes and returns
{"status": "ok", "result": <PMG's raw API response>}.

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

READ-ONLY: list PDM's own access control entries (who can use PDM, not a managed remote's ACL).

No state change. Returns a list of ACL entry dicts. exact=True restricts to the given path
instead of including sub-paths. For a managed PVE cluster's ACL instead of PDM's own, use
pve_acl_list. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `path` | string (nullable) | no | Optional ACL path filter, e.g. '/'; omit to list all entries. (default: `null`) |
| `exact` | boolean | no | If true, match the given path exactly rather than including sub-paths. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_node_status`

READ-ONLY: get resource stats for the PDM appliance's own node (not a managed remote's node).

No state change. Returns a dict shaped like PVE node status; live-prove-pending (not yet
confirmed live). Defaults to node='localhost' since PDM is single-node. For a managed PVE
node's status instead, use pve_node_status. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `node` | string | no | PDM node name; PDM is single-node so this defaults to 'localhost'. (default: `"localhost"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pbs_datastores_list`

READ-ONLY: list datastores on a PDM-registered PBS remote, proxied through PDM.

No state change. Returns [{"name", "path"}, ...] (live-verified, PDM 1.1 -> PBS 4.2). For
snapshots within a datastore use pdm_pbs_snapshots_list; to query PBS directly without PDM,
use pbs_datastores_list. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered PBS remote name, from pdm_remotes_list. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pbs_remote_status`

READ-ONLY: get node status (cpu/memory/uptime, etc.) for a PDM-registered PBS remote,
proxied through PDM.

No state change. Returns a dict (live-verified, PDM 1.1 -> PBS 4.2). For the remote's
datastores, use pdm_pbs_datastores_list. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered PBS remote name, from pdm_remotes_list. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pbs_snapshots_list`

READ-ONLY: list backup snapshots in one datastore on a PDM-registered PBS remote, proxied
through PDM.

No state change. Returns a list of snapshot dicts (empty list if the datastore has none);
live-verified (PDM 1.1 -> PBS 4.2). ns optionally filters by namespace. To query PBS
directly without PDM, use pbs_snapshots_list. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered PBS remote name, from pdm_remotes_list. |
| `datastore` | string | yes | PBS datastore name on the remote to list snapshots from. |
| `ns` | string (nullable) | no | Optional PBS namespace filter; omit to use the default namespace. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_ping`

READ-ONLY: health check the PDM appliance.

No state change. Returns the string 'pong' on success; raises on connection/auth failure.
For version details instead of a bare health check, use pdm_version. Needs PROXIMO_PDM_*
config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_cluster_status`

READ-ONLY: get cluster status for ONE PDM-registered PVE remote, proxied through PDM.

No state change. Returns a list of dicts shaped like PVE's cluster/status (live-proven
2026-06-27). To query the cluster directly without PDM, use pve_cluster_status. Needs
PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered PVE remote name, from pdm_remotes_list. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_config`

READ-ONLY: get an LXC container's config from a PDM-registered PVE remote, proxied through PDM.

No state change. Returns a dict (live-proven 2026-06-27). state defaults to "active" and is
REQUIRED by PDM's API (it 400s if omitted); node/snapshot are optional. To query the cluster
directly without PDM, use pve_guest_config_get. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered PVE remote name, from pdm_remotes_list. |
| `vmid` | string | yes | Numeric CT ID on the remote. |
| `node` | string (nullable) | no | Optional PVE node name; not required for PDM to resolve the container. (default: `null`) |
| `snapshot` | string (nullable) | no | Optional snapshot name to read config from instead of the live config. (default: `null`) |
| `state` | string | no | PDM config-state selector, required by the PDM API; 'active' returns the current config. (default: `"active"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_list`

READ-ONLY: list LXC containers across a PDM-registered PVE remote (cluster-wide), proxied
through PDM.

No state change. Returns a list of dicts shaped like PVE's lxc list (live-proven 2026-06-27);
node optionally filters to one PVE node. For one container's config use pdm_pve_lxc_config;
to query the cluster directly without PDM, use pve_list_guests. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered PVE remote name, from pdm_remotes_list. |
| `node` | string (nullable) | no | Optional PVE node name to restrict the listing to; omit to list cluster-wide. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_migrate`

MUTATION: relocate a container to another node within the same cluster, through PDM.

For a move to a *different* PDM remote/datacenter use pdm_pve_lxc_remote_migrate; to drive a
cluster directly without PDM use pve_guest_migrate. The container is moved, not copied — the
source node stops hosting it (there is no separate source to delete). LXC has no live migration:
online=True does a stop-move-start restart-migration (real downtime); the default (False) requires
it already be stopped. Dry-run by default (returns a PLAN); confirm=True submits and returns a PDM
task reference — track it with pdm_tasks_list (pve_task_status cannot poll a PDM UPID). Requires the
wired PDM remote's token to permit migration (VM.Migrate).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered remote (Proxmox cluster) hosting the container. |
| `vmid` | string | yes | Numeric CTID of the container to migrate, as a string. |
| `target` | string | yes | Destination node name within the same remote's cluster. |
| `online` | boolean | no | True attempts online (restart) migration — real downtime for LXC; else the container must be stopped. (default: `false`) |
| `confirm` | boolean | no | False (default) returns a PLAN only; True submits it. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_power`

MUTATION: start/stop/shutdown a container on a PDM-registered remote (through PDM).

For a VM use pdm_pve_qemu_power; to drive a cluster directly without PDM use
pve_guest_power. Dry-run by default (PLAN); confirm=True to submit. Task-backed → 'submitted'.

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

For a VM use pdm_pve_qemu_remote_migrate; for a same-cluster move use pdm_pve_lxc_migrate.
target_bridge and target_storage mappings are required (e.g. 'vmbr0:vmbr0', 'local-lvm:local-lvm').
delete=True removes the source after a successful move (irreversible). Dry-run by default
(PLAN); confirm=True submits and returns a PDM task reference — track it with pdm_tasks_list (pve_task_status cannot poll a PDM UPID).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered remote (Proxmox cluster) hosting the container. |
| `vmid` | string | yes | Numeric CTID of the container to migrate, as a string. |
| `target_remote` | string | yes | Destination PDM-registered remote (a different datacenter). |
| `target_bridge` | string | yes | Source-to-target network bridge mapping, e.g. 'vmbr0:vmbr0'. |
| `target_storage` | string | yes | Source-to-target storage mapping, e.g. 'local-lvm:local-lvm'. |
| `target_vmid` | string (nullable) | no | CTID on the destination; omit to keep same CTID. (default: `null`) |
| `online` | boolean | no | True attempts online (restart) migration — real downtime for LXC; else the container must be stopped. (default: `false`) |
| `delete` | boolean | no | True deletes container after successful move (destructive). (default: `false`) |
| `confirm` | boolean | no | False (default) returns a PLAN only; True submits it. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_snapshot_create`

MUTATION: snapshot a container on a PDM-registered remote (through PDM).

For a VM use pdm_pve_qemu_snapshot_create. Containers have no RAM state, so there is no
vmstate option. Additive (LOW risk) — creates a restore point, touches no existing state.
Dry-run by default (PLAN); confirm=True creates it and returns the Proxmox task UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered remote (Proxmox cluster) hosting the container. |
| `vmid` | string | yes | Numeric CTID of the target container, as a string. |
| `snapname` | string | yes | Name to give the new snapshot. |
| `description` | string (nullable) | no | Optional free-text note stored with the snapshot. (default: `null`) |
| `confirm` | boolean | no | False (default) returns a PLAN only; True creates it. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_snapshot_delete`

MUTATION: delete a named container snapshot on a PDM-registered remote, through PDM.

Removes only the snapshot's saved state, not the container. Irreversible — there is no UNDO.
For a VM snapshot use pdm_pve_qemu_snapshot_delete; to create rather than delete a snapshot use
pdm_pve_lxc_snapshot_create. Dry-run by default (returns a PLAN); confirm=True executes and
returns a PDM task reference (track with pdm_tasks_list; pve_task_status cannot poll a PDM UPID).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered remote (Proxmox cluster) hosting the container. |
| `vmid` | string | yes | Numeric CTID of the target container, as a string. |
| `snapname` | string | yes | Name of the snapshot to delete. |
| `confirm` | boolean | no | False (default) returns a PLAN only; True deletes it. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_lxc_snapshot_rollback`

MUTATION: roll a container back to a snapshot on a PDM-registered remote (through PDM).

For a VM use pdm_pve_qemu_snapshot_rollback; to roll back without PDM use pve_rollback.
DESTRUCTIVE (discards current state). Takes an auto safety-snapshot first (fail-closed: no
snapshot, no rollback) and returns its name as safety_snapshot — the handle to undo this
rollback. Dry-run by default (PLAN); confirm=True submits and returns the Proxmox task UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered remote (Proxmox cluster) hosting the container. |
| `vmid` | string | yes | Numeric CTID of the target container, as a string. |
| `snapname` | string | yes | Name of the snapshot to roll back to. |
| `confirm` | boolean | no | False (default) returns a PLAN only; True runs it. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_node_list`

READ-ONLY: list PVE nodes in a PDM-registered remote's cluster, proxied through PDM.

No state change. Returns a list of dicts shaped like PVE's /nodes endpoint (live-proven
2026-06-27). Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered PVE remote name, from pdm_remotes_list. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_qemu_config`

READ-ONLY: get a VM's config from a PDM-registered PVE remote, proxied through PDM.

No state change. Returns a dict (live-proven 2026-06-27). state defaults to "active" and is
REQUIRED by PDM's API (it 400s if omitted); node/snapshot are optional. To query the cluster
directly without PDM, use pve_guest_config_get. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered PVE remote name, from pdm_remotes_list. |
| `vmid` | string | yes | Numeric VM ID on the remote. |
| `node` | string (nullable) | no | Optional PVE node name; not required for PDM to resolve the VM. (default: `null`) |
| `snapshot` | string (nullable) | no | Optional snapshot name to read config from instead of the live config. (default: `null`) |
| `state` | string | no | PDM config-state selector, required by the PDM API; 'active' returns the current config. (default: `"active"`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_qemu_list`

READ-ONLY: list VMs across a PDM-registered PVE remote (cluster-wide), proxied through PDM.

No state change. Returns a list of dicts shaped like PVE's qemu list (live-proven
2026-06-27); node optionally filters to one PVE node. For one VM's config use
pdm_pve_qemu_config; to query the cluster directly without PDM, use pve_list_guests. Needs
PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered PVE remote name, from pdm_remotes_list. |
| `node` | string (nullable) | no | Optional PVE node name to restrict the listing to; omit to list cluster-wide. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_qemu_migrate`

MUTATION: migrate a VM to another node within the remote's cluster (through PDM).

For a container use pdm_pve_lxc_migrate; for a different remote/datacenter use
pdm_pve_qemu_remote_migrate; to drive a cluster directly without PDM use pve_guest_migrate.
online=True migrates it running; the default requires it stopped first. Dry-run by default
(PLAN); confirm=True submits and returns a PDM task reference — track it with pdm_tasks_list (pve_task_status cannot poll a PDM UPID).

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

For a container use pdm_pve_lxc_power; to drive a cluster directly without PDM use
pve_guest_power. Dry-run by default: returns a PLAN (live state, blast radius, risk)
recorded to the ledger. Re-call with confirm=True to submit. Task-backed → status='submitted'.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered remote (Proxmox cluster) hosting the VM. |
| `vmid` | string | yes | Numeric VMID of the target VM, as a string. |
| `action` | string | yes | Power action: 'start', 'stop', 'shutdown', or 'resume'. |
| `confirm` | boolean | no | False (default) returns a dry-run PLAN only; True executes. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_qemu_remote_migrate`

MUTATION: migrate a VM to a DIFFERENT PDM-registered remote (datacenter-to-datacenter).

For a container use pdm_pve_lxc_remote_migrate; for a same-cluster move use pdm_pve_qemu_migrate.
target_bridge and target_storage mappings are required (e.g. 'vmbr0:vmbr0', 'local-lvm:local-lvm').
delete=True removes the source VM after a successful move (irreversible). Dry-run by default
(PLAN); confirm=True submits and returns a PDM task reference — track it with pdm_tasks_list (pve_task_status cannot poll a PDM UPID).

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

For a container use pdm_pve_lxc_snapshot_create. vmstate=True includes the VM's RAM state
(larger, slower). Additive (LOW risk) — creates a restore point, touches no existing state.
Dry-run by default (PLAN); confirm=True creates it and returns the Proxmox task UPID.

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

MUTATION: delete a named VM snapshot on a PDM-registered remote, through PDM.

Removes only the snapshot's saved state, not the VM. Irreversible — there is no UNDO. For a
container snapshot use pdm_pve_lxc_snapshot_delete; to create rather than delete a snapshot use
pdm_pve_qemu_snapshot_create. Dry-run by default (returns a PLAN); confirm=True executes and
returns a PDM task reference (track with pdm_tasks_list; pve_task_status cannot poll a PDM UPID).

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered remote (Proxmox cluster) hosting the VM. |
| `vmid` | string | yes | Numeric VMID of the target VM, as a string. |
| `snapname` | string | yes | Name of the snapshot to delete. |
| `confirm` | boolean | no | False (default) returns a PLAN only; True deletes it. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_qemu_snapshot_rollback`

MUTATION: roll a VM back to a snapshot on a PDM-registered remote (through PDM).

For a container use pdm_pve_lxc_snapshot_rollback; to roll back without PDM use pve_rollback.
DESTRUCTIVE (discards current state). Takes an auto safety-snapshot first (fail-closed: no
snapshot, no rollback) and returns its name as safety_snapshot — the handle to undo this
rollback. Dry-run by default (PLAN); confirm=True submits and returns the Proxmox task UPID.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered remote (Proxmox cluster) hosting the VM. |
| `vmid` | string | yes | Numeric VMID of the target VM, as a string. |
| `snapname` | string | yes | Name of the snapshot to roll back to. |
| `confirm` | boolean | no | False (default) returns a PLAN only; True runs it. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_pve_resources`

READ-ONLY: list resources on ONE PDM-registered PVE remote, proxied through PDM.

No state change. Returns a list of dicts shaped like PVE's cluster/resources (live-proven
2026-06-27); kind optionally filters by type (vm, storage, node, sdn, ...). To query the
cluster directly without PDM, use pve_cluster_resources. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote` | string | yes | PDM-registered PVE remote name, from pdm_remotes_list. |
| `kind` | string (nullable) | no | Optional resource-type filter, e.g. 'vm', 'storage', 'node', 'sdn'. (default: `null`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_remote_config_get`

READ-ONLY: get configuration for one PDM-registered remote.

No state change. Returns a dict; credential-shaped keys (token/password/secret) are stripped
before returning. To see all registered remotes first, use pdm_remotes_list. Needs
PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote_id` | string | yes | Remote name as shown in pdm_remotes_list. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_remote_version`

READ-ONLY: get version info for one PDM-registered remote, proxied through PDM.

No state change. Returns a dict (the remote's own /version response). To see all registered
remotes first, use pdm_remotes_list. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `remote_id` | string | yes | Remote name as shown in pdm_remotes_list. |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_remotes_list`

READ-ONLY: list all PVE/PBS remotes registered in PDM (the datacenters/backup targets it manages).

No state change. Returns a list of remote dicts; credential-shaped keys (token/password/secret)
are stripped before returning. For one remote's version or config use pdm_remote_version /
pdm_remote_config_get. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_resources_list`

READ-ONLY: list every fleet resource (VMs, LXCs, storage, etc.) across ALL PDM-registered remotes.

No state change. Returns a flat list of resource dicts. For counters instead of the full
list, use pdm_resources_status; to scope to one remote, use pdm_pve_resources. Needs
PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_resources_status`

READ-ONLY: aggregated fleet status counters (running VMs, LXCs, failed remotes, etc.)
across all PDM-registered remotes.

No state change. Returns a dict of counters. For the underlying per-resource list, use
pdm_resources_list. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_roles_list`

READ-ONLY: list PDM's own roles and their privileges (not a managed remote's roles).

No state change. Returns a list of role dicts. For a managed PVE cluster's roles instead of
PDM's own, use pve_roles_list. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_tasks_list`

READ-ONLY: list recent PDM tasks (queued/running/finished operations) across all
registered remotes.

No state change. Returns a list of task dicts. For a target remote's own task list directly
(without going through PDM), use pve_tasks_list. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_users_list`

READ-ONLY: list PDM's own user accounts (not a managed remote's users).

No state change. Returns a list of user dicts; credential-shaped keys are stripped before
returning. include_tokens=True also includes API token entries. For a managed PVE cluster's
users instead of PDM's own, use pve_users_list. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `include_tokens` | boolean | no | If true, include API token entries alongside user accounts. (default: `false`) |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

#### `pdm_version`

READ-ONLY: get the PDM appliance's own version info.

No state change. Returns a dict with release, repoid, and version. For a lightweight health
check instead, use pdm_ping. Needs PROXIMO_PDM_* config.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `proximo_target` | string (nullable) | no | Which configured Proxmox target to run this call against — a target name from your multi-target config (a specific PVE/PBS/PMG/PDM box). Omit to use the single/default target from the environment; the selection applies only to this call. (default: `null`) |

## Container exec (opt-in)

#### `ct_diagnose`

READ-ONLY: gather 'what's broken' evidence for a container — API status + a fixed read-only
in-container battery (failed units, disk, recent errors, memory, listening ports) + advisory flags.

No mutation, no confirm. Returns a dict with the gathered sections and a flags list. The
in-container probes need PROXIMO_ENABLE_EXEC and the CTID allowlist (same as ct_logs); with
exec off it returns the API-only part and discloses the skipped probes. For node-level
evidence use pve_diagnose.

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

READ-ONLY: tail journalctl for a systemd unit inside a container. Returns the command's
returncode, stdout, and stderr. Gated by the CTID allowlist when PROXIMO_ENABLE_EXEC is set;
fails closed (returns a disclosed blocked status, not an exception) if exec is disabled or the
CTID isn't allowed. For a fixed evidence battery instead of one unit's logs use ct_diagnose;
for an arbitrary in-container command use ct_exec.

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
