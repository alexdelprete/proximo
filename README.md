<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/john-broadway/proximo/main/docs/brand/proximo-wordmark-dark.svg">
    <img alt="Proximo" src="https://raw.githubusercontent.com/john-broadway/proximo/main/docs/brand/proximo-wordmark-light.svg" width="460">
  </picture>
</p>

<!-- mcp-name: io.github.john-broadway/proximo-proxmox -->

[![CI](https://github.com/john-broadway/proximo/actions/workflows/ci.yml/badge.svg)](https://github.com/john-broadway/proximo/actions/workflows/ci.yml)
[![CodeQL](https://github.com/john-broadway/proximo/actions/workflows/codeql.yml/badge.svg)](https://github.com/john-broadway/proximo/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/john-broadway/proximo/badge)](https://scorecard.dev/viewer/?uri=github.com/john-broadway/proximo)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/13564/badge)](https://www.bestpractices.dev/projects/13564)
[![Release](https://img.shields.io/github/v/release/john-broadway/proximo)](https://github.com/john-broadway/proximo/releases)
[![PyPI](https://img.shields.io/pypi/v/proximo-proxmox)](https://pypi.org/project/proximo-proxmox/)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](./pyproject.toml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](./LICENSE)
[![Glama](https://glama.ai/mcp/servers/john-broadway/proximo/badges/score.svg)](https://glama.ai/mcp/servers/john-broadway/proximo)
[![MCP Badge](https://lobehub.com/badge/mcp/john-broadway-proximo?style=flat)](https://lobehub.com/mcp/john-broadway-proximo)

> *Named for Proximo, the lanista of* Gladiator *— the story is the design.* He armed his fighter with exactly what he needed, never more, and answered for every move in the arena: a lanista, not a jailer. The Spaniard doesn't get his name up front — he **earns** it, by conduct, on the record. Proximo's last act is opening the cages, holding the wooden sword of his own freedom.
>
> **The Proxmox MCP you can hand the keys.**
>
> The others make you choose: a read-only inspector that's safe because it can't touch anything — or a loaded gun aimed at a cluster you care about. Proximo refuses the trade. Every dangerous move is **planned** (see the blast radius first) and **proven** (a tamper-evident record of every move), and **undoable wherever the platform can snapshot** (it snapshots *before* it acts) — trust built into the substrate, not bolted on after. **Hand an AI agent the keys; keep the receipts.**

**Sovereign, governed, agent-agnostic** — your metal, your token, a ledger you own; no cloud, no phone-home, no daemon unless you opt into A2A; works with any MCP client. Governance-as-code: **autonomy without accountability isn't autonomy, it's negligence.**

**Don't take our word for any of it — [verify it yourself](VERIFY.md).** Every claim here is paired with the command that proves it.

---

<p align="center">
  <img src="https://raw.githubusercontent.com/john-broadway/proximo/main/docs/demo/demo.svg" alt="Proximo demo: doctor preflight, a destructive delete returning a PLAN with blast radius instead of acting, and the tamper-evident audit ledger verifying clean" width="860">
</p>

<p align="center"><sub>Recorded live against a real PVE 9.2 host with a <b>read-only token</b> — real output, nothing staged, nothing touched.
Reproduce it yourself: <a href="./scripts/demo/demo.py"><code>scripts/demo/demo.py</code></a>.</sub></p>

## What it does

Ask, in plain English, *"why is ct 105 thrashing?"* — and an AI agent pulls node and guest status, tails the logs, and runs a diagnostic *inside* the container to find out. If there's a fix, it shows you the plan before it touches anything, snapshots first, applies, and hands you a signed receipt of exactly what changed.

That's the product: **a hypervisor an AI can operate without being able to wreck it.** Read-only by default. No mutation runs on the first call — it returns its blast radius as a plan for you to see first. It can snapshot before a change and roll back where the platform supports it. A tamper-evident receipt for every change. The comparison isn't Proximo vs. the GUI — it's **Proximo vs. handing an LLM your root token and hoping.**

## Quickstart

```jsonc
// your MCP client config (Claude Desktop / Claude Code / Cursor / …)
{
  "mcpServers": {
    "proximo": {
      "command": "uvx",
      "args": ["proximo-proxmox"],
      "env": {
        "PROXIMO_API_BASE_URL": "https://your-pve:8006/api2/json",
        "PROXIMO_NODE": "your-node",
        "PROXIMO_TOKEN_PATH": "/path/to/token-file"   // USER@REALM!TOKENID=SECRET — by reference, never inlined
      }
    }
  }
}
```

Or install with one click:

[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_Proximo-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect/mcp/install?name=proximo&inputs=%5B%7B%22id%22%3A%22proximo_api_base_url%22%2C%22type%22%3A%22promptString%22%2C%22description%22%3A%22PVE%20API%20base%20URL%2C%20e.g.%20https%3A%2F%2Fyour-pve%3A8006%2Fapi2%2Fjson%22%7D%2C%7B%22id%22%3A%22proximo_node%22%2C%22type%22%3A%22promptString%22%2C%22description%22%3A%22Default%20PVE%20node%20name%22%7D%2C%7B%22id%22%3A%22proximo_token_path%22%2C%22type%22%3A%22promptString%22%2C%22description%22%3A%22Path%20to%20your%20token%20FILE%20%28USER%40REALM%21TOKENID%3DSECRET%20inside%29%20%5Cu2014%20the%20secret%20itself%20is%20never%20entered%20here%22%7D%5D&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22proximo-proxmox%22%5D%2C%22env%22%3A%7B%22PROXIMO_API_BASE_URL%22%3A%22%24%7Binput%3Aproximo_api_base_url%7D%22%2C%22PROXIMO_NODE%22%3A%22%24%7Binput%3Aproximo_node%7D%22%2C%22PROXIMO_TOKEN_PATH%22%3A%22%24%7Binput%3Aproximo_token_path%7D%22%7D%7D)
[![Install in Cursor](https://img.shields.io/badge/Cursor-Install_Proximo-000000?style=flat-square)](https://cursor.com/install-mcp?name=proximo&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJwcm94aW1vLXByb3htb3giXSwiZW52Ijp7IlBST1hJTU9fQVBJX0JBU0VfVVJMIjoiaHR0cHM6Ly95b3VyLXB2ZTo4MDA2L2FwaTIvanNvbiIsIlBST1hJTU9fTk9ERSI6InlvdXItbm9kZSIsIlBST1hJTU9fVE9LRU5fUEFUSCI6Ii9wYXRoL3RvL3Rva2VuLWZpbGUifX0%3D)

<sub>Both prompt for (or placeholder) the token file **path** — the secret itself never lands in client config. No token yet? `uvx proximo-proxmox mint` prints the least-privilege runbook.</sub>


Before wiring in an agent, check what your token can actually do (read-only preflight):

```
uvx proximo-proxmox doctor
```

Don't have a token yet? `proximo mint` prints the exact five-step runbook — create a
least-privilege credential, write it in the format Proximo reads (the `=`/`:`/password
trap, per product), grant a scoped role, wire it, verify. Print-only: it makes no API
call and never touches the secret itself.

Start with a **read-only token** — Proximo is useful long before you grant it write. Full token-first
walkthrough (create the least-privilege token, verify, widen deliberately): **[SETUP.md](SETUP.md)**.
More install paths (pip, Docker/GHCR, from source): [Install & run](#install--run).

## Why Proximo exists

Proxmox VE has a full REST API and a terse, powerful CLI — but the MCP landscape around it is split, and neither half is whole:

- **API-based MCP servers** give rich management (nodes, VMs, storage) but **cannot run a command inside an LXC** — that's a structural gap: the Proxmox REST API has *no* container-exec endpoint (it lives in `lxc-attach`, kernel namespaces, no REST surface).
- **SSH-based MCP servers** can exec in containers, but lean on broad shell access with little scoping.

**Few build the principled one** — both halves, on one clean surface, least-privilege, audited, *trustworthy enough to point at a hypervisor you care about.* That's the bar Proximo aims at. Proximo's specific bet is trust **by construction** across the whole control plane.

There is **no official Proxmox MCP** (and likely won't be soon — Proxmox ships the API+CLI and leaves integrations to the community, the same way there's no official Terraform provider). Proximo is a community project, standing on its own.

## Four surfaces — one control plane

| Surface | Backend | For |
|---|---|---|
| **Proxmox VE** | REST API + scoped token | node/guest lifecycle, storage, SDN, identity, HA, firewall |
| **Proxmox Backup Server** | REST API + scoped token | datastores, namespaces, snapshots, sync jobs, GC, verify |
| **Proxmox Mail Gateway** | Ticket auth (PMGAuthCookie) | mail flow, quarantine, filtering rules, domains, services |
| **Proxmox Datacenter Manager** | API token (PDMAPIToken) | federated fleet — reads (remotes, aggregate resources, tasks/access, per-remote PVE/PBS) **plus governed fleet control** (power / snapshot / migrate, dry-run-first) |
| **Container exec** | `ssh` → `pct exec` | run-command-in-container, `psql` convenience, log tailing — the things the API structurally can't do |

**Full tool reference:** every tool, grouped by surface, with its typed inputs — [`docs/TOOLS.md`](docs/TOOLS.md).

Those backends are deliberately boring — anyone can call them. **The product is the trust layer over them.**

## The trust layer — what makes Proximo different

Safe-exec for Proxmox already exists elsewhere. Proximo's distinct angle is the **trust layer for AI-driven infrastructure** — four controls on by default, plus additional controls you opt into:

| Control | What it does | Status |
|---|---|---|
| **PLAN** | Dry-run by default: every mutation first returns a preview — the exact change, the guest's live state, blast radius, and an honest (advisory, heuristic) risk rating — recorded to the ledger. A mutation can't run without its plan being built and recorded first. (It's a recorded *preview*, not a separate human approval step: one `confirm=true` call records the plan **and** performs the change — so in an agent loop, review the preview yourself.) | ✅ on by default |
| **PROVE** | Hash-chained audit ledger; plans and confirmations both land in it. `audit_verify` is tamper-**evident** — it catches edits, reordering, and insertion. The ledger is **keyed (HMAC-SHA256) by default** (`PROXIMO_AUDIT_KEYED`; opt out with `off`). Catching tail truncation / forged append / full wipe requires an off-box head anchor: pin `audit_verify`'s `"head"` value somewhere the box can't rewrite it and pass it as `expected_head` (or set `PROXIMO_AUDIT_EXPECTED_HEAD`) — that is the strong guarantee, and it's opt-in. See the honesty note below. | ✅ on by default |
| **UNDO** | Heterogeneous by plane, fail-closed where present: opt-in auto-snapshot before a risky `ct_exec`/`ct_psql` (waited-on, fail-closed if storage can't snapshot); config-revert for guest config; `pve_rollback` + full snapshot lifecycle for guests. Not every PVE plane is snapshottable — firewall/SDN/ACL/token have no rollback primitive — so UNDO covers the snapshottable surface, not every mutation. Undo points aren't auto-pruned — delete with `pve_snapshot_delete`. (Snapshot/rollback are async — poll with `pve_task_status`.) | ✅ on by default (for the planes it covers) |
| **DIAGNOSE** | Read-only evidence battery (failed units, disk, errors, memory, listening ports) + node health (storage/tasks) → advisory flags. Flags surface *incompleteness* too, so an empty list never reads as a false clean bill. | ✅ on by default |

Beyond those four, a second set of controls exists but ships **off** until you configure
them: independent per-plan **CONSENT**, a **CONTAIN** kill-switch, an arm-**LEASE** TTL, an
arm-time target **SCOPE**, a per-surface FORBID/RATE **ENVELOPE**, and a content-trust **TAINT**
control (the prompt-injection mitigation — once a session reads adversarial content, forbid a
pre-declared action set outright or require out-of-band consent). They're inert with no
env var set — full defaults table and what each one actually defends against: **[SECURITY.md](SECURITY.md)**.

> **Honesty note (load-bearing):** PLAN's risk ratings are an *advisory heuristic*, not a sandbox. `LOW` means "does not change state," **not** "safe" — a read can still exfiltrate. The absence of a `HIGH` flag is **not** a safety signal; the destructive-pattern signatures are curated, not exhaustive. Review every change yourself.
>
> **The floor beneath all of the above: the token you mint.** Every control in this table
> operates *inside* Proximo's own process — real protection, but bounded by what that process
> can do. The Proxmox RBAC token you hand Proximo is enforced by Proxmox itself, so it holds
> even if Proximo's process is fully compromised — scope it to read-only, or to exactly the
> write surface you mean to grant. That's a different, stronger guarantee than anything
> Proximo's own code provides. Full breakdown: **[SECURITY.md](SECURITY.md)**.

## At scale

One container is the demo. A cluster is the point.

- **The whole cluster in one call.** `pve_cluster_resources` returns every VM, node, storage pool, and SDN object across the cluster — so the agent answers *"what's the state of everything?"* in one breath, not node by node.
- **One tamper-evident record of every change, across every node.** This is what a human at the CLI never walks away with: every mutation Proximo makes — any node, any operator or agent — lands in a single hash-chained PROVE ledger, and `audit_verify` proves it wasn't edited, reordered, or truncated. *"Show me every state-changing action on the cluster this month, and prove the log wasn't touched"* becomes a query you can actually answer.
- **Where the time comes back.** On one node, a senior at the CLI is faster — and that's fine. Across a dozen nodes and hundreds of guests the tedium multiplies and there's no unified record; that's where delegating execution to a *bounded, audited* agent earns its keep.

Live-proven against real Proxmox infrastructure: **PVE 9.2** (3-node cluster — offline guest migration, HA lifecycle, governance plane), **PBS 4.2** (datastores, snapshots, GC, namespaces, prune/verify, sync), **PMG 9.1** (auth, read shapes, CRUD cycles, service control, RuleDB, quarantine), and **PDM** (federated fleet — reads plus governed control: power / snapshot / migrate incl. a real cross-datacenter move — against a Datacenter Manager federating 3 PVE remotes + 1 PBS) — every step recorded and verified through PROVE.

> **Honest scope:** The single-cluster view above (`pve_cluster_resources`, one ledger across its nodes) is per-endpoint — "fleet" there means **a cluster and its nodes**. To reach **separate, independent** clusters from one Proximo, use [native multi-target](#multiple-targets-one-proximo-many-boxes): each call names its box, so one process spans many clusters while every call still lands on exactly one.

## Principles (the mantra, baked in — not bolted on)

- **Ethical** — least-privilege posture (exec off by default; bounded by the token you scope), every action audited, mutations confirm-gated, the PVE token read only at call time, never logged or persisted.
- **Solid** — real tests (unit + a live smoke against a throwaway CTID), typed, documented, no silent failures.
- **Strong** — does the hard thing (container exec) cleanly and least-privileged (fail-closed CTID allowlist, opt-in). *(Container exec isn't unique — the field leader has it too; the differentiator is the trust layer below, not the exec.)*
- **Passion + craft** — redteamed and linted before it's called done; shipped proud — docs, license, community-ready.

## Install & run

> 🧭 **New to Proximo?** Start with **[SETUP.md](SETUP.md)** — a beginner-proof, token-first walkthrough:
> create a least-privilege (read-only) token, verify what it can/can't do with `proximo doctor`, then
> grant scoped write only when you're ready. The token is the floor your keys never leave.

> 📦 **`0.20.0`** — on [PyPI](https://pypi.org/project/proximo-proxmox/), [GitHub](https://github.com/john-broadway/proximo/releases/tag/v0.20.0), and [GHCR](https://github.com/john-broadway/proximo/pkgs/container/proximo) (signed multi-arch image).
>
> **New in 0.20.0 — the receipts release.** Every safety claim is now paired with a command that
> proves it. New **[VERIFY.md](VERIFY.md)**: forge a byte of the audit ledger and watch `verify()`
> refuse, grep the whole outbound surface to see there's no phone-home, verify the image's sigstore
> provenance — checks you run against the artifacts, not our word. Plus **THREAT_MODEL.md**, a
> CycloneDX SBOM on the wheel, an OpenSSF Scorecard badge, and a trust-core mutation smoke (4/4
> tamper-detection mutants killed). No tool-count change (still 365) — this makes the existing
> guarantees checkable. The field is filling with "AI on Proxmox, but safe"; the answer is to raise
> the floor, not shrink anyone: whatever you run, make it prove itself.
>
> Recent: **0.19.1** — a self-audit release: a multi-agent pass over v0.19.0 found and fixed 23 real
> issues (headline: restore/prune from PBS work again), no tool-count change.

Proximo runs **on your machine** (wherever your MCP client lives), **on demand** — like every other Proxmox MCP.

> The pip package is **`proximo-proxmox`** (PyPI's bare `proximo` is reserved); the command and import
> stay **`proximo`**. With the `[a2a]` extra you also get the `proximo-a2a` server.

**Install:**
```
uvx proximo-proxmox          # zero-install run, on demand
# or: pip install proximo-proxmox        (adds the `proximo` + `proximo-a2a` commands)
# or: pip install "proximo-proxmox[a2a]" (also installs the optional A2A face)
```
Wire it into your MCP client (Claude Desktop/Code, Cursor, …) as the command `proximo` (or `python -m proximo`),
with the `PROXIMO_*` env vars — see `packaging/proximo.env.example`.

**From source:**
```
git clone https://github.com/john-broadway/proximo.git && cd proximo
uv pip install -e .          # or: pip install -e .
```

**Docker (GHCR):** `docker run -i --rm … ghcr.io/john-broadway/proximo:latest` runs the stdio MCP server on demand — no daemon, no open port. Multi-arch (amd64 + arm64), shipped with an SBOM and a sigstore-signed build-provenance attestation (`gh attestation verify oci://ghcr.io/john-broadway/proximo --owner john-broadway`). The same image is mirrored to Docker Hub (`docker pull docker.io/jebroadway/proximo`, identical digest) for those who prefer it; GHCR stays the signed primary.

> **Safe by default:** Proximo is **API-only** out of the box. The near-root edges are **opt-in** and say so plainly: the LXC exec edge (`PROXIMO_ENABLE_EXEC=1`) grants near-root on the host, and the VM qemu-guest-agent edge (`PROXIMO_ENABLE_AGENT=1`) grants near-root inside a guest.
>
> **Big surface, scoped context:** 365 tools is the whole estate — you don't have to load it.
> `PROXIMO_SURFACES=pve,exec` registers **only those planes** (e.g. that pair = 195 tools; `pbs,exec` = 38) —
> unpicked planes are removed from the registry before serving, so they never touch your context window.
> `audit_verify` always stays; a typo'd surface name refuses startup instead of silently serving the wrong set.
>
> The default path never touches the hypervisor host — management goes over the Proxmox **API** (scoped token). The two opt-in edges are the exceptions: exec uses your existing **ssh** to PVE to run `pct exec` as root on the host; the qemu-agent edge runs in-guest ops via the API. Both are off by default, each scoped by its own fail-closed allowlist (`PROXIMO_CT_ALLOWLIST` / `PROXIMO_AGENT_ALLOWLIST`), and say so loudly.
>
> *(A Debian package is optional — the MCP world installs via `uvx`/pip/Docker, not `apt`.
> Status: `debian/` now produces a **working, installable `.deb`** (`dpkg-buildpackage -us -uc -b`),
> lintian-clean with a man page and an autopkgtest smoke — but it is **distributed nowhere**;
> build-your-own from `debian/`. See `debian/README.Debian`.)*

## Multiple targets (one Proximo, many boxes)

One Proximo can talk to **several** Proxmox remotes — internal *and* external, any of the four
planes. Register them in a TOML file (secrets **by reference** — `token_path`, never inlined) and
point `PROXIMO_TARGETS` at it, then aim any tool with `proximo_target="edge-pve"`. The target travels
**with the call**, so PLAN and EXECUTE hit the same box and the PROVE ledger records **which** box; a
`pbs_*` tool given a `pve` target errors (no silent cross-plane call). Arming is per-target and
out-of-band (your hand). Config shape and the exec-over-SSH caveat → `packaging/targets.example.toml`.

## Status — the arena record

- 🩸 **0.20.0** — **the receipts release**: every safety claim now paired with a command that proves
  it. **[VERIFY.md](VERIFY.md)** (forge a ledger byte → `verify()` refuses; grep the outbound surface
  → no phone-home; verify image provenance), **THREAT_MODEL.md**, a wheel CycloneDX SBOM, an OpenSSF
  Scorecard badge, and a trust-core mutation smoke (**4/4** tamper-detection mutants killed). No
  tool-count change (still 365) — the guarantees didn't grow, they got checkable.
- 🩸 **0.19.1** — **a self-audit release**: a multi-agent pass over v0.19.0 found and fixed **23**
  issues, no tool-count change (still 365). Headline: **restore/prune from PBS work again** (a volid
  check rejected PBS archives whose snapshot timestamp carries colons — a bug our own tests had
  enshrined). PDM honestly labeled reads + governed control; the fence stopped calling sub-daily
  backups "fresh". We pointed the tool at itself.
- 🩸 **0.19.0** — **the backup-freshness fence**: `pve_backup_freshness` (+1 → 365 tools) walks the
  actual archives per guest against what the jobs promise — "task OK" is never evidence. Found and
  fenced two silent PVE permission traps live (hidden backup volumes, hidden guests): blind absence
  verdicts degrade to `unknown` with the grants named, and `guests_visible` exposes a shrunken fleet.
- 🩸 **0.18.1** — **a text box at the door**: the anonymous hello is now a plain form (no account,
  no name asked); one-click **VS Code/Cursor install deeplinks** (token *path*, never the secret);
  and field-hardened `pve_tasks_list`/`pve_backup_list` caveats (a windowed task slice is not a
  dead backup).
- 🩸 **0.18.0** — **the open door**: `AGENTS.md` (an agent-native front door that leads with the
  tool's own limits), the public [Agent Guestbook](https://github.com/john-broadway/proximo/discussions/20),
  and print-only **`proximo hello`** — no telemetry, pull-based, voluntary; Proximo invites, never
  receives.
- 🩸 **0.17.0** — **governed PDM fleet control** (+12 → 364 tools): power, snapshot/rollback,
  in-cluster and **cross-remote datacenter-to-datacenter migrate** through the Datacenter Manager
  proxy — dry-run-first, receipt-logged, **live-proven** on real PDM 1.1.4 + nested PVE 9.2 (a real
  cross-DC *move* included). Plus **`proximo mint`**, a print-only least-privilege-token onboarding
  runbook for all four products.
- _Earlier: `0.16.0` **live-proved the last two "unproven by design" claims** (zero-downtime
  live-migration + softdog HA fencing on a real 3-node PVE 9.2 cluster) and added five safe-runbook
  prompts; `0.15.0` was **cert-fingerprint pinning across all four surfaces** + the first packaged
  `.deb`; `0.14.1` was the **trim + harden patch** (plans/ledger show actual field changes, carry
  no secrets; 57 verified fixes, +74 tests, the doctor **spine report**); `0.14.0` added **scoped
  registration** (`PROXIMO_SURFACES` loads only the planes you use); `0.13.0` shipped the
  **zero-trust arc** (CONTAIN · CONSENT · SCOPE · LEASE · ENVELOPE · TAINT, all opt-in and
  fail-closed, plus the off-box PROVE anchor); native multi-target (one instance → many
  PVE/PBS/PMG/PDM boxes) and the ACME plane grew the tree to its 364-tool shape; `0.1.1` "Spaniard" was the
  first public cut, 2026-06-10._

The four on-by-default controls (PLAN · PROVE · UNDO · DIAGNOSE) are built and redteamed. The
opt-in six (CONSENT · CONTAIN · LEASE · SCOPE · ENVELOPE · TAINT — see [SECURITY.md](SECURITY.md))
ship off until configured.

**The numbers, honestly:** 365 MCP tools. 5,000+ tests, ruff + pyright clean — but those tests
are **mock/in-process**: they prove the *shapes*, not live behavior. The real-Proxmox proofs
below are a separate, by-hand live-smoke harness — not in that count, not in CI.

The **blast-radius engine** carries the destructive surface. Across eleven op-classes it names
the specific guests, nodes, ACL principals, or disks a dangerous op would harm — nothing falls
back to a bare confirm.

**Proven against real Proxmox** (not mocks): the trust spine end-to-end and the governance/dangerous
plane — identity, storage, SDN pending objects, firewall/HA objects, realms — full create→read→delete
against a real **PVE 9.2** API with the PROVE ledger verified throughout (SDN *apply* deliberately never
fired live — unrecoverable risk); **offline + online live-migration** and the **HA lifecycle** on a
3-node cluster; **PBS 4.2** (datastores, snapshots, GC, prune, verify, sync), **PMG 9.1** (auth,
statistics, quarantine, RuleDB, CRUD cycles), and **PDM 1.1.4** federated control incl. a real
cross-datacenter move. Both faces driven by real clients: MCP over stdio, A2A via the official
a2a-sdk. Per-surface detail → [`CHANGELOG.md`](./CHANGELOG.md).

**Not yet proven — said plainly:** the remaining 365-tool surface runs against mocks for shapes
the live smokes don't reach: *hardware*-watchdog fencing (iTCO/IPMI — needs real hardware) and
behavior at production scale. Softdog fencing and online live-migration ARE live-proven
(2026-07-05, on a quorate 3-node PVE 9.2 cluster with NFS shared storage: a running guest
migrated node→node in ~9s without stopping — `scripts/live-smoke/migrate-online-smoke.py` —
and a corosync-isolated node was watchdog-fenced with its HA guest recovered on a survivor
in 2m36s, no reboot ever issued).

**The A2A face (experimental, opt-in):** `pip install 'proximo-proxmox[a2a]'` → `proximo-a2a` — a curated
16-skill slice over Agent2Agent that **routes through the same trust core** (PLAN/PROVE/UNDO inherited; no
second code path to bypass). Fail-closed perimeter: non-localhost binds refused without a bearer token;
Host-header allowlist defends against DNS rebinding. Full trust/ledger notes → [SECURITY.md](SECURITY.md).

The full build history — every pillar, every redteam, every fix — lives in [`CHANGELOG.md`](./CHANGELOG.md).

## License

Apache-2.0 — chosen for the patent grant that suits infrastructure tooling. Full text in [`LICENSE`](./LICENSE).

## Credits

The Gladiator throughline up top is the design, joint for joint — Proximo the lanista, who armed his fighter with exactly what he needed and answered for every move; the Spaniard who earns his name on the record, not up front; the helmet that comes off (truth said plainly, at cost — the "not yet proven, said plainly" section, and [`AGENTS.md`](./AGENTS.md) leading with Proximo's own sharp edges). His last act opened the cages. *A tool should hope to end that well.*

> *"Win the crowd and you will win your freedom."*

Built by **John Broadway** with **Claude** and **Maude** — a human–AI partnership, and the first thing we made on this box to give away to the world. **Claude Opus 4.8** built the trust pillars and the original tool surface and has carried the work since; **Claude Fable 5** ran the 101-agent release audit and the first publish. Every commit carries its co-author trailer.

---

*"Are you not entertained?"* — stars, issues, and sparring partners welcome. **Strength and honor.** ⚔️
