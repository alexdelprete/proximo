# Proximo Live-Smoke Scripts

These are **live integration smoke tests** for Proximo. They are NOT unit tests — they require a real Proxmox VE host and a scoped API token, and they exercise Proximo's own stack end-to-end against that host.

They live here (not under `tests/`) precisely so that pytest does not auto-collect them.

---

## What each smoke does

| Script | What it exercises | Mutations? |
|---|---|---|
| `readonly-smoke.sh` | `pve_node_status`, `pve_storage_status`, `pve_storage_content`, `pve_backup_list` (on all discovered storages), `audit_verify` | None |
| `phase1-smoke.sh` | Create / clone / backup / restore / delete QEMU VMs in a throwaway pool | Yes — self-cleaning; operates only on the throwaway VMIDs you specify |
| `netplane-smoke.sh` | Firewall rule CRUD (cluster-level, firewall stays DISABLED), pool lifecycle, HA plan (dry-run) | Firewall rules + pool — self-cleaning; firewall never enabled |
| `fwobjects-smoke.sh` | Firewall **objects**: alias CRUD, ip-set create/entry/delete, security-group CRUD, options read + `options_set` PLAN (dry-run, never executed) | Firewall config objects — self-cleaning; passive (no rule references them); firewall never enabled |
| `harules-smoke.py` | **HA rules** full chain: create throwaway VM → HA-manage → `ha_rule` create/read/update/delete → teardown | VM + HA resource + HA rule — self-cleaning (reverse order); VM is empty + HA state=ignored (CRM never starts it). Run via `proximo-ha-liveprove.sh` (reuses the test-cluster token) |
| `sdn-smoke.py` | **SDN** chain: `simple` zone → vnet → subnet create/read/update/delete | PENDING-ONLY — `sdn_apply` is NEVER called, so no live-network effect; self-cleaning (reverse order). Confirms pending objects stage + revert cleanly |
| `tfa-smoke.py` | **TFA** bounded: `tfa_list`/`tfa_get` reads + `tfa_delete` API-reachability (non-existent entry) | No factor touched, no password sent. Live-verifies PVE forbids token-based TFA mutation (`403 need proper ticket`) — reads work, delete is shape-correct but ticket-gated by PVE |
| `fw-reach-smoke.py` | **Firewall/network reach** (blast-radius): PLAN a firewall rule add → prints the per-rule REACH + `affected`; if `PROXIMO_NODE` is set, also PLANs a network apply → prints best-effort mgmt-interface lockout naming | None — pure PLAN for the rule reach; one safe `network_list` read for the apply naming; `confirm` is never passed, nothing is applied |

All mutating smokes clean up after themselves via `try/finally` and print a loud manual-cleanup fallback if cleanup fails.

---

## Prerequisites

1. **A real Proxmox VE host** (tested against PVE 7.x and 8.x).
2. **A scoped API token** — see [Creating a least-privilege token](#creating-a-least-privilege-token) below.
3. **Proximo installed** — either `pip install proximo` or run from the repo root (the wrappers auto-detect both).
4. **`shred`** available on the runner (standard on Linux; `coreutils`).

---

## Required environment variables

Set these before running any smoke. **No infra literal is hardcoded** — the scripts fail fast with a clear error if a required variable is unset.

### All smokes

| Variable | Example | Notes |
|---|---|---|
| `PROXIMO_API_BASE_URL` | `https://pve.example.com:8006/api2/json` | Full URL to your PVE JSON API endpoint |
| `PROXIMO_NODE` | `your-node` | PVE node name (matches `pvesh get /nodes`) |
| `PROXIMO_VERIFY_TLS` | `false` | `true` = verify cert (recommended for production); `false` = accept self-signed |

### Auth (choose one)

| Variable | When to use |
|---|---|
| `PROXIMO_TOKEN_PATH` | Path to a plain file whose only content is the API token string (`user@realm!tokenid=<secret>`). You manage the file's lifecycle. |
| `PROXIMO_TOKEN_FILE` | Path to a shell env file that exports the token (e.g. `PROXMOX_TOKEN=user@realm!tokenid=<secret>`). The wrapper auto-detects the token, writes it to a `mktemp` file under `umask 077`, and shreds it on exit. |

### `phase1-smoke.sh` additional variables

| Variable | Required | Default | Notes |
|---|---|---|---|
| `SMOKE_STORE` | **Yes** | — | Storage ID to use for backups (e.g. `your-backup-storage`) |
| `SMOKE_POOL` | No | `proximo-smoke-throwaway` | Pool to create throwaway VMs in |
| `SMOKE_VMID` | No | `9900` | Base VMID; three consecutive IDs are used (base, base+1, base+2). Choose IDs well above your highest production VMID. |
| `PROXIMO_CT_ALLOWLIST` | No | matches `SMOKE_VMID` range | Proximo's container allowlist; defaults to the three throwaway VMIDs |

### `netplane-smoke.sh` additional variables

| Variable | Required | Default | Notes |
|---|---|---|---|
| `SMOKE_FW_COMMENT` | No | `proximo-smoke-fwtest` | Comment tag applied to throwaway firewall rules |
| `SMOKE_POOL_ID` | No | `proximo-smoke-throwaway-pool` | Throwaway pool ID for the pool-lifecycle test |

### Override the Python interpreter

Set `PYTHON=/path/to/python3` to use a specific interpreter or virtualenv Python. The wrappers default to `python3` on `PATH`.

---

## Quick start

```sh
# Export required variables
export PROXIMO_API_BASE_URL="https://pve.example.com:8006/api2/json"
export PROXIMO_NODE="your-node"
export PROXIMO_VERIFY_TLS="false"   # or "true" if you have a valid cert
export PROXIMO_TOKEN_PATH="/path/to/token-file"   # file contains: user@realm!tokenid=<secret>

# Read-only smoke (safe; no mutations)
bash scripts/live-smoke/readonly-smoke.sh

# Mutate smoke (creates/deletes throwaway VMs)
export SMOKE_STORE="your-backup-storage"
export SMOKE_VMID="9900"   # choose IDs safe for throwaway use
bash scripts/live-smoke/phase1-smoke.sh

# Network/infra-plane smoke (firewall CRUD + pool lifecycle + HA plan)
bash scripts/live-smoke/netplane-smoke.sh
```

---

## Creating a least-privilege token

Proximo is designed around the principle of a **scoped API token** — one that has only the permissions the tool set actually needs. You should NOT use your root@pam password or a full-admin token for these tests.

### Step 1 — Create a dedicated user (optional but recommended)

```sh
pveum user add proximo-smoke@pve --comment "Proximo smoke test user"
```

### Step 2 — Create an API token for that user

```sh
pveum user token add proximo-smoke@pve smoke --comment "Proximo live-smoke token"
```

Save the printed secret — it is shown only once.

### Step 3 — Grant permissions

Minimum for **readonly smoke** (`Datastore.Audit` + `Sys.Audit`):

```sh
pveum acl modify / -user proximo-smoke@pve -token smoke -role PVEAuditor
```

Additional for **phase1 smoke** (VM lifecycle + backup):

```sh
pveum role add ProximoSmoke -privs "VM.Allocate VM.Clone VM.Config.CDROM VM.Config.CPU VM.Config.Disk VM.Config.HWType VM.Config.Memory VM.Config.Network VM.Config.Options VM.PowerMgmt VM.Snapshot Datastore.AllocateSpace Datastore.Audit Pool.Allocate Sys.Audit"
pveum acl modify / -user proximo-smoke@pve -token smoke -role ProximoSmoke
```

Additional for **netplane smoke** (firewall CRUD + pool lifecycle):

```sh
# Add to the role above, or grant additionally:
pveum acl modify / -user proximo-smoke@pve -token smoke -privs "Sys.Modify Pool.Audit"
```

> **Tip:** Start with narrow permissions and expand only when a specific step reports a 403. Proximo will tell you which tool failed.

---

## Security notes

- **Token secrets are never printed.** The wrappers pass the token via a file path, not via command-line arguments or environment variables visible in `ps`.
- **Temp files are shredded on exit.** When `PROXIMO_TOKEN_FILE` is used, the wrapper writes the extracted token to a `mktemp` file under `umask 077` and registers a `trap '... shred -u ...' EXIT` — crucially **without** using `exec` to launch Python, so the bash process resumes after Python exits and the trap fires reliably.
- **Mutations are throwaway-scoped.** All mutating operations target clearly-named throwaway artifacts (`proximo-smoke-*`, VMIDs you choose). No production guests, pools, or firewall rules are touched.
- **Firewall is never enabled.** The netplane smoke tests firewall rule CRUD at the API level but never calls `firewall_set_enabled` — the firewall remains in whatever state your PVE has it.
- **SDN/network changes are never applied.** Operations that would reload host networking (e.g. `sdn_apply`, `network_apply`) are not exercised — they carry unrecoverable risk on a production network.
