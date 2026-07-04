# Proximo

<!-- mcp-name: io.github.john-broadway/proximo-proxmox -->

[![CI](https://github.com/john-broadway/proximo/actions/workflows/ci.yml/badge.svg)](https://github.com/john-broadway/proximo/actions/workflows/ci.yml)
[![CodeQL](https://github.com/john-broadway/proximo/actions/workflows/codeql.yml/badge.svg)](https://github.com/john-broadway/proximo/actions/workflows/codeql.yml)
[![Release](https://img.shields.io/github/v/release/john-broadway/proximo)](https://github.com/john-broadway/proximo/releases)
[![PyPI](https://img.shields.io/pypi/v/proximo-proxmox)](https://pypi.org/project/proximo-proxmox/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](./pyproject.toml)

> **The Proxmox MCP you can hand the keys.**
>
> The others make you choose: a read-only inspector that's safe because it can't touch anything — or a loaded gun aimed at a cluster you care about. Proximo refuses the trade. Every dangerous move is **planned** (see the blast radius first) and **proven** (a tamper-evident record of every move), and **undoable wherever the platform can snapshot** (it snapshots *before* it acts) — trust built into the substrate, not bolted on after. **Hand an AI agent the keys; keep the receipts.**

---

<p align="center">
  <img src="https://raw.githubusercontent.com/john-broadway/proximo/main/docs/demo/demo.svg" alt="Proximo demo: doctor preflight, a destructive delete returning a PLAN with blast radius instead of acting, and the tamper-evident audit ledger verifying clean" width="860">
</p>

<p align="center"><sub>Recorded live against a real PVE 9.2 host with a <b>read-only token</b> — real output, nothing staged, nothing touched.
Reproduce it yourself: <a href="./scripts/demo/demo.py"><code>scripts/demo/demo.py</code></a>.</sub></p>

## What it does

Ask, in plain English, *"why is ct 105 thrashing?"* — and an AI agent pulls node and guest status, tails the logs, and runs a diagnostic *inside* the container to find out. If there's a fix, it shows you the plan before it touches anything, snapshots first, applies, and hands you a signed receipt of exactly what changed.

That's the product: **a hypervisor an AI can operate without being able to wreck it.** Read-only by default. No mutation without a plan first, and the plan refuses destructive ops. It snapshots before any state change, wherever the platform can snapshot. A tamper-evident receipt for every change. The comparison isn't Proximo vs. the GUI — it's **Proximo vs. handing an LLM your root token and hoping.**

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

**Few build the principled one** — both halves, on one clean surface, least-privilege, audited, *trustworthy enough to point at a hypervisor you care about.* That's the bar Proximo aims at. Proximo's specific bet is trust **by construction** across the whole control plane.

There is **no official Proxmox MCP** (and likely won't be soon — Proxmox ships the API+CLI and leaves integrations to the community, the same way there's no official Terraform provider). Proximo is a community project, standing on its own.

## Four surfaces — one control plane

| Surface | Backend | For |
|---|---|---|
| **Proxmox VE** | REST API + scoped token | node/guest lifecycle, storage, SDN, identity, HA, firewall |
| **Proxmox Backup Server** | REST API + scoped token | datastores, namespaces, snapshots, sync jobs, GC, verify |
| **Proxmox Mail Gateway** | Ticket auth (PMGAuthCookie) | mail flow, quarantine, filtering rules, domains, services |
| **Proxmox Datacenter Manager** | API token (PDMAPIToken) | **read-only** federated fleet — remotes, aggregate resources, tasks/access, per-remote PVE/PBS reads |
| **Container exec** | `ssh` → `pct exec` | run-command-in-container, `psql` convenience, log tailing — the things the API structurally can't do |

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

Live-proven against real Proxmox infrastructure: **PVE 9.2** (3-node cluster — offline guest migration, HA lifecycle, governance plane), **PBS 4.2** (datastores, snapshots, GC, namespaces, prune/verify, sync), **PMG 9.1** (auth, read shapes, CRUD cycles, service control, RuleDB, quarantine), and **PDM** (read-only federated fleet — remotes, aggregate resources, tasks/access, per-remote PVE/PBS reads — against a Datacenter Manager federating 3 PVE remotes + 1 PBS) — every step recorded and verified through PROVE.

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

> 📦 **`0.14.1`** — on [PyPI](https://pypi.org/project/proximo-proxmox/), [GitHub](https://github.com/john-broadway/proximo/releases/tag/v0.14.1), and [GHCR](https://github.com/john-broadway/proximo/pkgs/container/proximo) (signed multi-arch image).
>
> **New in 0.14.1 — the trim + harden patch.** Plans and the ledger now show the actual
> field values a mutation will change. Secrets stay out of both: cloud-init passwords,
> ACME DNS credentials, exec argv. The doctor gained its **spine report**.
>
> **0.14.0** added **scoped registration**: `PROXIMO_SURFACES=pve,exec` loads only the
> planes you use. **0.13.0** added the **zero-trust arc** — six opt-in controls
> (CONTAIN · CONSENT · SCOPE · LEASE · ENVELOPE · TAINT), all off until configured.
> [SECURITY.md](SECURITY.md) says which controls are on by default and what each honestly holds.

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

**Docker (GHCR):** `docker run -i --rm … ghcr.io/john-broadway/proximo:latest` runs the stdio MCP server on demand — no daemon, no open port. Multi-arch (amd64 + arm64), shipped with an SBOM and a sigstore-signed build-provenance attestation (`gh attestation verify oci://ghcr.io/john-broadway/proximo --owner john-broadway`).

> **Safe by default:** Proximo is **API-only** out of the box. The near-root edges are **opt-in** and say so plainly: the LXC exec edge (`PROXIMO_ENABLE_EXEC=1`) grants near-root on the host, and the VM qemu-guest-agent edge (`PROXIMO_ENABLE_AGENT=1`) grants near-root inside a guest.
>
> **Big surface, scoped context:** 352 tools is the whole estate — you don't have to load it.
> `PROXIMO_SURFACES=pve,exec` registers **only those planes** (e.g. that pair = 194 tools; `pbs,exec` = 38) —
> unpicked planes are removed from the registry before serving, so they never touch your context window.
> `audit_verify` always stays; a typo'd surface name refuses startup instead of silently serving the wrong set.
>
> The default path never touches the hypervisor host — management goes over the Proxmox **API** (scoped token). The two opt-in edges are the exceptions: exec uses your existing **ssh** to PVE to run `pct exec` as root on the host; the qemu-agent edge runs in-guest ops via the API. Both are off by default, each scoped by its own fail-closed allowlist (`PROXIMO_CT_ALLOWLIST` / `PROXIMO_AGENT_ALLOWLIST`), and say so loudly.
>
> *(A Debian package is deferred/optional — the MCP world installs via `uvx`/pip/Docker, not `apt`.
> Status: `debian/` is a packaging **scaffold, not yet installable** — `dpkg-buildpackage` won't
> produce a working `.deb` until the bundled-venv step is finished; see `debian/README.Debian`.)*

## Multiple targets (one Proximo, many boxes)

By default one Proximo talks to one box (the `PROXIMO_*` env). To reach **several** Proxmox
remotes — internal *and* external, any of the four planes — register them in a TOML file and
point `PROXIMO_TARGETS` at it (see `packaging/targets.example.toml`):

```toml
[targets.edge-pve]
kind       = "pve"
base_url   = "https://edge.example.com:8006/api2/json"
node       = "edge"
token_path = "/etc/proximo/edge-pve.token"   # secret BY REFERENCE — never inlined
```

Then aim any tool at a named remote with **`proximo_target`**:

```
pve_guest_power(vmid=131, action="reboot", proximo_target="edge-pve")
```

- **Omit `proximo_target`** (the default) and behavior is exactly as today — the env box, unchanged.
- The target travels **with the call**, so PLAN and EXECUTE always hit the same box, and the PROVE
  ledger records **which box** (`remote`) every op touched.
- **Kind-checked:** a `pbs_*` tool given a `pve` target errors — no silent cross-plane call.
- **Secrets stay by reference** (`token_path` / `password_path`); the registry holds no secret values.
- **Arming is per-target and out-of-band** (your hand): it swaps the operator token at that target's
  `token_path`. Proximo's code only ever reads whatever token is there.
- **In-container exec (`ct_exec`/`ct_psql`/`ct_logs`/`ct_diagnose`) is target-aware too**, but it runs
  `pct exec` over SSH — so a targeted call needs that target SSH-reachable with `enable_exec` + an
  `ssh_target` set in its registry entry. An external, API-only box won't serve `pct exec`.

## Status — the arena record

- 🩸 **0.14.1** — the **trim + harden patch**. Plans and the ledger now show the actual field
  changes, and carry no secrets. 57 verified fixes, +74 tests, plus the doctor **spine report**.
- 🩸 **0.14.0** — **scoped registration**: `PROXIMO_SURFACES` loads only the planes you use.
  A structural registry gate, not a runtime refusal. Plus the demo-led README.
- 🩸 **0.13.0** — the **zero-trust arc**: CONTAIN · CONSENT · SCOPE · LEASE · ENVELOPE · TAINT,
  all opt-in and fail-closed. Plus the off-box PROVE anchor and `pve_acl_prune` (351 → 352 tools).
- 🩸 **0.12.0** — `proximo doctor --target` brings the CLI preflight onto the multi-target
  registry. Plus a PMG login-concurrency fix. A drop-in over 0.11.0.
- 🩸 **0.11.0** — **native multi-target**: one instance reaches many PVE/PBS/PMG/PDM remotes via
  `proximo_target=`. Plus the ACME cert-order plane (347 → 351 tools). Redteamed and live-proven
  against two real boxes. _(0.1.1 "Spaniard" was the first public cut, 2026-06-10.)_

The four on-by-default controls (PLAN · PROVE · UNDO · DIAGNOSE) are built and redteamed. The
opt-in six (CONSENT · CONTAIN · LEASE · SCOPE · ENVELOPE · TAINT — see [SECURITY.md](SECURITY.md))
ship off until configured.

**The numbers, honestly:** 352 MCP tools. 5,000+ tests, ruff + pyright clean — but those tests
are **mock/in-process**: they prove the *shapes*, not live behavior. The real-Proxmox proofs
below are a separate, by-hand live-smoke harness — not in that count, not in CI.

The **blast-radius engine** carries the destructive surface. Across eleven op-classes it names
the specific guests, nodes, ACL principals, or disks a dangerous op would harm — nothing falls
back to a bare confirm.

**Proven against real Proxmox** (not mocks):
- The trust spine end-to-end, the core provisioning/config mutate cycle, and PBS read shapes.
- The **governance/dangerous plane** — identity (roles/groups/users/ACLs), storage, **SDN pending
  objects** (zone/vnet/subnet create→read→delete), realm create (LDAP/AD/OpenID via an `options`
  dict) — full create→read→delete cycles against a real **PVE 9.2** API, PROVE ledger verified
  throughout. **(SDN/network *apply* — the host-network reload — is deliberately never fired live;
  it carries unrecoverable risk.)**
- The **object planes** — firewall objects (aliases/IP-sets/security-groups/options), HA
  **rules** (the PVE 9 replacement for HA groups), and SDN zones/VNets/subnets (pending, pre-apply) —
  create→read→delete live-proven against a real **PVE 9.2** node; TFA admin reads proven (TFA
  mutation is ticket-gated by PVE, not token-accessible).
- **Offline guest migration** (including local-disk) and the **HA-config** lifecycle on a 3-node PVE 9.2 test cluster.
- **PBS 4.2** — datastores, namespaces, snapshot list/delete/notes/protect, GC, prune, verify,
  sync jobs, and traffic control — live-proven against the test PBS instance.
- **PMG 9.1** — auth (ticket + CSRF flow), node status/syslog/RRD, mail statistics, quarantine
  (spam/virus/attachment list, deliver/delete/blocklist/welcomelist via `pmg_quarantine_action`), domain/transport/mynetworks/spam-config CRUD,
  service status + restart cycle, RuleDB paths (groups/objects/rules/ordering) — W1–W5 live-smoke
  rounds, including safe mutations with full create→verify→clean-up cycles.
- Both protocol faces driven by real clients end-to-end: MCP over stdio, and A2A by the official a2a-sdk.

**Not yet proven — said plainly:** the remaining 352-tool surface runs against mocks for shapes
the live smokes don't reach: real HA *fencing* (needs a hardware watchdog), *online*
live-migration (needs shared storage), and behavior at production scale.

**The A2A face (experimental, opt-in):** `pip install 'proximo-proxmox[a2a]'`, then `proximo-a2a` — a curated
16-skill slice over Agent2Agent that **routes through the same trust core** (PLAN/PROVE/UNDO inherited;
there is no second code path to bypass). Fail-closed perimeter: non-localhost binds are refused without a
bearer token (`PROXIMO_A2A_TOKEN_FILE`); Host-header allowlist defends against DNS rebinding. Ledger note:
the ledger is **keyed (HMAC-SHA256) by default** (`PROXIMO_AUDIT_KEYED`, opt out with `off`) —
tamper-*evident*, not tamper-*proof* — and an off-box `head()` anchor (`PROXIMO_AUDIT_EXPECTED_HEAD`) is the strong guarantee for tail attacks.
`ct_psql` records the SQL body and `ct_exec` the command argv it runs (the operator's own input) for a
complete audit trail; set `PROXIMO_LEDGER_REDACT=1` to record a fingerprint (sha256 + kind + length)
instead, when the SQL/command may carry secrets/PII. The PVE API token is never written to the ledger.

### What's next
- [ ] HA fencing + online migration once the hardware exists
- [ ] PBS certificate-fingerprint wire-enforcement
- [ ] _(optional)_ Debian package for the Debian-native crowd

The full build history — every pillar, every redteam, every fix — lives in [`CHANGELOG.md`](./CHANGELOG.md).

## License

Apache-2.0 — chosen for the patent grant that suits infrastructure tooling. Full text in [`LICENSE`](./LICENSE).

## Credits

*Named for Proximo, the lanista of* Gladiator *— the man who armed the fighter with exactly what he needed, never more, and answered for every move in the arena. That is the whole design: give the operator — human or agent — the reach to act, never the run of the house, accountable for all of it.*

> *"Win the crowd and you will win your freedom."*

Built by **John Broadway** with **Claude** and **Maude** — a human–AI partnership, and the first thing we made on this box to give away to the world.

Claude's contribution spans eras, credited honestly: **Claude Opus 4.8** built the trust pillars and the
original tool surface (June 2026) and has carried the work since — the Backup Server, Mail Gateway, and
Datacenter Manager planes, native multi-target, and the security hardening; **Claude Fable 5** ran the
101-agent release audit and the first publish. Every commit carries its co-author trailer.

---

*"Are you not entertained?"* — stars, issues, and sparring partners welcome. **Strength and honor.** ⚔️
