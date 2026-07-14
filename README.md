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

<p align="center">
  <a href="#quickstart">Quickstart</a> ·
  <a href="SETUP.md">Setup</a> ·
  <a href="#the-trust-layer--what-makes-proximo-different">Trust layer</a> ·
  <a href="#choose-the-right-tool">Tools</a> ·
  <a href="VERIFY.md">Verify</a> ·
  <a href="SECURITY.md">Security</a> ·
  <a href="#install--run">Install</a> ·
  <a href="#status--the-arena-record">Status</a>
</p>

> *Named for Proximo, the lanista of* Gladiator *— the story is the design.* He armed his fighter with exactly what he needed, never more, and answered for every move in the arena: a lanista, not a jailer. The Spaniard doesn't get his name up front — he **earns** it, by conduct, on the record. Proximo's last act is opening the cages, holding the wooden sword of his own freedom.
>
> **The Proxmox MCP you can hand the keys.**
>
> The others make you choose: a read-only inspector that's safe because it can't touch anything — or a loaded gun aimed at a cluster you care about. Proximo refuses the trade. Every dangerous move is **planned** (see the blast radius first) and **proven** (a tamper-evident record of every move), and **undoable wherever the platform can snapshot** (it snapshots *before* it acts) — trust built into the substrate, not bolted on after. **Hand an AI agent the keys; keep the receipts.**

**Sovereign, governed, agent-agnostic** — your metal, your token, a ledger you own; no cloud, no phone-home, no standing server unless you opt into the A2A or HTTP face (each runs as you, on loopback — no root, no dedicated user); works with any MCP client. Governance-as-code: **autonomy without accountability isn't autonomy, it's negligence.**

**Don't take our word for any of it — [verify it yourself](VERIFY.md).** Every claim here is paired with the command that proves it.

<details>
<summary><b>Verify in 60 seconds</b> — three receipts, no trust required</summary>

```bash
# 1. The tool count is real — ask the server itself, cold (=> 365).
#    (in a clone of this repo, after `uv sync`)
uv run python -c "import asyncio; from proximo import server; \
print(len(asyncio.run(server.mcp.list_tools())))"

# 2. The container image is what the repo built — sigstore provenance (exit 0 = verified):
gh attestation verify oci://ghcr.io/john-broadway/proximo:latest --owner john-broadway

# 3. The security posture is graded by a third party, not by us:
#    https://scorecard.dev/viewer/?uri=github.com/john-broadway/proximo
```

The rest — forge a ledger byte and watch `verify()` refuse, grep the entire outbound
surface for phone-home (there is none), check PyPI publish provenance — is in
[VERIFY.md](VERIFY.md). These checks work on any tool, from any vendor. Demand them everywhere.

</details>

---

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/john-broadway/proximo/main/docs/brand/proximo-architecture-dark.svg">
    <img alt="Proximo architecture: MCP, A2A, and HTTP/OpenAPI clients all enter one governed dispatch, pass the trust spine (PLAN, PROVE, UNDO, DIAGNOSE), sit on the Proxmox-enforced token floor, and reach four products — PVE, PBS, PMG, PDM" src="https://raw.githubusercontent.com/john-broadway/proximo/main/docs/brand/proximo-architecture-light.svg" width="860">
  </picture>
</p>

<p align="center"><sub>The whole design in one picture: every transport — MCP, A2A, HTTP/OpenAPI — enters <b>one governed dispatch</b> and crosses the <b>same trust spine</b> to reach all four Proxmox products. No transport gets its own path, and the token floor beneath it all is enforced by Proxmox itself. Below: what that looks like live.</sub></p>

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

Start with a **read-only token** — Proximo is useful long before you grant it write. Full token-first
walkthrough (create the least-privilege token, verify, widen deliberately): **[SETUP.md](SETUP.md)**.
More install paths (pip, Docker/GHCR, from source): [Install & run](#install--run).

## Why Proximo exists

Proxmox VE has a full REST API and a terse, powerful CLI — but the MCP landscape around it is split, and neither half is whole:

- **API-based MCP servers** give rich management (nodes, VMs, storage) but **cannot run a command inside an LXC** — that's a structural gap: the Proxmox REST API has *no* container-exec endpoint (it lives in `lxc-attach`, kernel namespaces, no REST surface).
- **SSH-based MCP servers** can exec in containers, but lean on broad shell access with little scoping.

**Few build the principled one** — both halves, on one clean surface, least-privilege, audited, *trustworthy enough to point at a hypervisor you care about.* That's the bar Proximo aims at. Proximo's specific bet is trust **by construction** across the whole control plane:

| | Read-only inspector | Full-access executor | **Proximo** |
|---|---|---|---|
| Can mutate | no — that's the safety | yes | yes — plan recorded first, then `confirm=true` |
| Preview before a change | n/a | rarely | **default** — blast radius + live state, every mutation |
| Record of what happened | no | app logs, editable | **keyed hash-chained ledger, tamper-evident, on by default** |
| Undo | n/a | rare | snapshot-first, wherever the platform can snapshot |
| Command inside an LXC | no | broad SSH | opt-in, fail-closed CTID allowlist |
| Products covered | usually PVE | usually PVE | **PVE + PBS + PMG + PDM** — one audited plane |
| Verify the artifact you run | varies | varies | signed image (sigstore) · PyPI provenance (PEP 740) · SBOM · [Scorecard](https://scorecard.dev/viewer/?uri=github.com/john-broadway/proximo) |

*(The two archetype columns describe the split above — API-readers and SSH-executors — not any specific project.)*

There is **no official Proxmox MCP** (and likely won't be soon — Proxmox ships the API+CLI and leaves integrations to the community, the same way there's no official Terraform provider). Proximo is a community project, standing on its own.

## Four surfaces — one control plane

| Surface | Backend | For |
|---|---|---|
| **Proxmox VE** | REST API + scoped token | node/guest lifecycle, storage, SDN, identity, HA, firewall |
| **Proxmox Backup Server** | REST API + scoped token | datastores, namespaces, snapshots, sync jobs, GC, verify |
| **Proxmox Mail Gateway** | Ticket auth (PMGAuthCookie) | mail flow, quarantine, filtering rules, domains, services |
| **Proxmox Datacenter Manager** | API token (PDMAPIToken) | federated fleet — reads (remotes, aggregate resources, tasks/access, per-remote PVE/PBS) **plus governed fleet control** (power / snapshot / migrate, dry-run-first) |
| **Container exec** | `ssh` → `pct exec` | run-command-in-container, `psql` convenience, log tailing — the things the API structurally can't do |

Those backends are deliberately boring — anyone can call them. **The product is the trust layer over them.**

## Choose the right tool

365 tools is an estate, not a starting point. Where an operator actually starts:

| You want to… | Start with | Worth knowing |
|---|---|---|
| See the whole cluster at once | `pve_cluster_resources`, `pve_list_guests` | one call, every node |
| Find out why a container is sick | `ct_diagnose`, `ct_logs`, `pve_guest_status` | read-only evidence battery |
| Preflight a token / config | `proximo doctor` (CLI) or `pve_doctor`, `pve_overbroad_grants` | run this before wiring an agent |
| Power / lifecycle | `pve_guest_power` | returns a PLAN first — nothing moves without `confirm=true` |
| Snapshot before touching anything | `pve_snapshot_create`, `pve_rollback` | UNDO's foundation |
| Check backups are actually fresh | `pve_backup_freshness`, `pbs_snapshots_list` | walks real archives — "task OK" is never evidence |
| Run a command in a container | `ct_exec` | opt-in (`PROXIMO_ENABLE_EXEC=1`), fail-closed allowlist |
| Trace / release mail | `pmg_tracker_list`, `pmg_quarantine_spam` | full PMG plane behind it |
| Operate the federated fleet | `pdm_resources_list`, `pdm_pve_lxc_list` | governed control, dry-run-first |
| Prove the record wasn't touched | `audit_verify` | registered on every surface, always |

Every tool, grouped by surface, with typed inputs: [`docs/TOOLS.md`](docs/TOOLS.md).

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

Hold any tool to this — including this one: **[The Keys Test](https://john-broadway.github.io/keys-test/)**
— ten questions to ask before you hand an AI agent real infrastructure, with Proximo's own
scorecard published, partials included.

## At scale

One container is the demo. A cluster is the point.

- **The whole cluster in one call.** `pve_cluster_resources` returns every VM, node, storage pool, and SDN object across the cluster — so the agent answers *"what's the state of everything?"* in one breath, not node by node.
- **One tamper-evident record of every change, across every node.** This is what a human at the CLI never walks away with: every mutation Proximo makes — any node, any operator or agent — lands in a single hash-chained PROVE ledger, and `audit_verify` proves it wasn't edited, reordered, or truncated. *"Show me every state-changing action on the cluster this month, and prove the log wasn't touched"* becomes a query you can actually answer.
- **Where the time comes back.** On one node, a senior at the CLI is faster — and that's fine. Across a dozen nodes and hundreds of guests the tedium multiplies and there's no unified record; that's where delegating execution to a *bounded, audited* agent earns its keep.

All of it live-proven against real Proxmox infrastructure — the full inventory of what was driven on real hardware (and what wasn't) is below, under [the numbers](#status--the-arena-record).

> **Honest scope:** The single-cluster view above (`pve_cluster_resources`, one ledger across its nodes) is per-endpoint — "fleet" there means **a cluster and its nodes**. To reach **separate, independent** clusters from one Proximo, use [native multi-target](#multiple-targets-one-proximo-many-boxes): each call names its box, so one process spans many clusters while every call still lands on exactly one.

## Install & run

> 🧭 **New to Proximo?** Start with **[SETUP.md](SETUP.md)** — a beginner-proof, token-first walkthrough:
> create a least-privilege (read-only) token, verify what it can/can't do with `proximo doctor`, then
> grant scoped write only when you're ready. The token is the floor your keys never leave.

> 📦 **`0.21.1`** — on [PyPI](https://pypi.org/project/proximo-proxmox/), [GitHub](https://github.com/john-broadway/proximo/releases/tag/v0.21.1), and [GHCR](https://github.com/john-broadway/proximo/pkgs/container/proximo) (signed multi-arch image).
>
> **New in 0.21.1 — the truth-audit patch.** A full "are we lying anywhere?" pass over every public
> claim: the code came back clean; the docs that had drifted are fixed and now gated so they can't
> drift again. The hardening it forced: the `chmod 600` secret-file floor now covers **every** secret
> referenced by path — PBS/PDM tokens, the PMG password, the network faces' bearer tokens, the A2A
> signing key — so a mis-deployed `0644` credential refuses at load on every plane; and every pip
> install in the CI/release/image builds is **hash-pinned** against lockfiles exported from
> `uv.lock`, with a two-stage image build (no build tooling, no source tree in what ships).
> No tool-count change (still 365).
>
> Recent: **0.21.0** — the HTTP/OpenAPI face; both network faces now serve the full 365-tool governed
> surface through one shared dispatch. See [SECURITY.md](SECURITY.md) for what each control honestly holds.

Proximo runs **on your machine** (wherever your MCP client lives), **on demand** — like every other Proxmox MCP.

> The pip package is **`proximo-proxmox`** (PyPI's bare `proximo` is reserved); the command and import
> stay **`proximo`**. The optional `[a2a]` and `[http]` extras add the `proximo-a2a` and `proximo-http`
> servers.

**Install:**
```
uvx proximo-proxmox          # zero-install run, on demand
# or: pip install proximo-proxmox         (the MCP core — the `proximo` command)
# or: pip install "proximo-proxmox[a2a]"  (also installs the optional A2A face)
# or: pip install "proximo-proxmox[http]" (also installs the optional HTTP/OpenAPI face)
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
> *(Optional: `debian/` builds a working, lintian-clean `.deb` — build-your-own, distributed
> nowhere. See `debian/README.Debian`.)*

## Multiple targets (one Proximo, many boxes)

One Proximo can talk to **several** Proxmox remotes — internal *and* external, any of the four
planes. Register them in a TOML file (secrets **by reference** — `token_path`, never inlined) and
point `PROXIMO_TARGETS` at it, then aim any tool with `proximo_target="edge-pve"`. The target travels
**with the call**, so PLAN and EXECUTE hit the same box and the PROVE ledger records **which** box; a
`pbs_*` tool given a `pve` target errors (no silent cross-plane call). Arming is per-target and
out-of-band (your hand). Config shape and the exec-over-SSH caveat → `packaging/targets.example.toml`.

## Status — the arena record

- 🩸 **0.21.1** — **the truth-audit patch**: every public claim re-verified (the code was clean; the
  doc drift is fixed and now gated); the `chmod 600` secret floor extended to every secret on every
  plane; all pip installs in CI/release/image builds hash-pinned from `uv.lock`; README rebuilt —
  architecture diagram, tool picker, verify-in-60-seconds receipts. No tool-count change (still 365).
- 🩸 **0.21.0** — **an HTTP/OpenAPI face, full surface on every transport**: a new `proximo-http`
  face for no-code / dashboard clients, and the A2A face corrected to match — both network faces now
  expose the full 365-tool governed surface, not a curated slice. A same-day redteam caught a
  loopback-CSRF hole, fixed before ship. No tool-count change (still 365).
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
- _Earlier: `0.18.0` the open door (`AGENTS.md`, print-only
  `proximo hello`); `0.17.0` governed PDM fleet control (+12 tools) + `proximo mint`; `0.16.0` live-proved
  live-migration + softdog HA fencing; `0.15.0` cert-fingerprint pinning on all four surfaces;
  `0.14.x` scoped registration + the trim/harden patch; `0.13.0` the zero-trust arc (the six opt-in
  controls) + native multi-target; `0.1.1` "Spaniard", the first public cut (2026-06-10). The full
  story per release: [`CHANGELOG.md`](./CHANGELOG.md)._

The four on-by-default controls (PLAN · PROVE · UNDO · DIAGNOSE) are built and redteamed. The
opt-in six (CONSENT · CONTAIN · LEASE · SCOPE · ENVELOPE · TAINT — see [SECURITY.md](SECURITY.md))
ship off until configured.

**The numbers, honestly:** 365 MCP tools, proved in two deliberate layers. **5,000+ in-process
tests** (ruff + pyright clean) pin every tool's *shape* and the trust-core logic. Separately, a
**live-smoke harness drives real Proxmox hardware** — a real 3-node PVE 9.2 cluster, real PBS 4.2 /
PMG 9.1 / PDM 1.1.4, a real cross-datacenter move (the proofs below). The two are kept apart on
purpose: passing shape tests never gets to masquerade as "it works on a real host." We don't just test
on the metal — we *run* on it: this workspace administers its own Proxmox estate through Proximo
(dogfood), so the tools are exercised live in daily use. The in-process suite is the floor under that,
not a substitute for it.

The **blast-radius engine** carries the destructive surface. Across eleven op-classes it names
the specific guests, nodes, ACL principals, or disks a dangerous op would harm — nothing falls
back to a bare confirm.

**Proven against real Proxmox** (not mocks): the trust spine end-to-end and the governance/dangerous
plane — identity, storage, SDN pending objects, firewall/HA objects, realms — full create→read→delete
against a real **PVE 9.2** API with the PROVE ledger verified throughout (SDN *apply* deliberately never
fired live — unrecoverable risk); **offline + online live-migration** and the **HA lifecycle** on a
3-node cluster; **PBS 4.2** (datastores, snapshots, GC, prune, verify, sync), **PMG 9.1** (auth,
statistics, quarantine, RuleDB, CRUD cycles), and **PDM 1.1.4** federated control incl. a real
cross-datacenter move. Faces driven by real clients: MCP over stdio, A2A via the official
a2a-sdk. Per-surface detail → [`CHANGELOG.md`](./CHANGELOG.md).

**Not yet proven — said plainly:** what a lab can't give remains unproven: *hardware*-watchdog
fencing (iTCO/IPMI needs physical hardware — **softdog** fencing and zero-downtime online
live-migration ARE live-proven: 2026-07-05, quorate 3-node PVE 9.2 cluster on NFS shared storage,
a running guest moved node→node in ~9s and a corosync-isolated node was fenced with its HA guest
recovered on a survivor in 2m36s — `scripts/live-smoke/migrate-online-smoke.py`) and behavior at
production scale. The unrecoverable destructive ops (SDN *apply*, etc.) are deliberately never
fired live — proven by plan, held back by design, not a gap.

### The network faces (experimental, opt-in)

Two more transports over the same governed core. `pip install 'proximo-proxmox[a2a]'` →
`proximo-a2a` speaks Agent2Agent; `pip install 'proximo-proxmox[http]'` → `proximo-http` serves
plain HTTP with a generated `/openapi.json` for no-code / dashboard clients (Open WebUI and the
like). Both serve the **full tool surface** through the same dispatch an MCP client takes
(`proximo.governed`) — no second code path, PLAN/PROVE/UNDO and the token scope inherited; scope
with `PROXIMO_SURFACES` + the token ACL, exactly like MCP. Shared fail-closed perimeter: each runs
as you on loopback, refuses a non-localhost bind without a bearer token (constant-time compare),
and defends against DNS-rebind and cross-origin (CSRF) forgery. Full trust/ledger notes →
[SECURITY.md](SECURITY.md).

The full build history — every pillar, every redteam, every fix — lives in [`CHANGELOG.md`](./CHANGELOG.md).

## License

Apache-2.0 — chosen for the patent grant that suits infrastructure tooling. Full text in [`LICENSE`](./LICENSE).

## Credits

The Gladiator throughline up top is the design, joint for joint — Proximo the lanista, who armed his fighter with exactly what he needed and answered for every move; the Spaniard who earns his name on the record, not up front; the helmet that comes off (truth said plainly, at cost — the "not yet proven, said plainly" section, and [`AGENTS.md`](./AGENTS.md) leading with Proximo's own sharp edges). His last act opened the cages. *A tool should hope to end that well.*

> *"Win the crowd and you will win your freedom."*

Built by **John Broadway** with **Claude** and **Maude** — a human–AI partnership, and the first thing we made on this box to give away to the world. **Claude Opus 4.8** built the trust pillars and the original tool surface and has carried the work since; **Claude Fable 5** ran the 101-agent release audit and the first publish. Every commit carries its co-author trailer.

---

*"Are you not entertained?"* — stars, issues, and sparring partners welcome. **Strength and honor.** ⚔️
