# Proximo

[![CI](https://github.com/john-broadway/proximo/actions/workflows/ci.yml/badge.svg)](https://github.com/john-broadway/proximo/actions/workflows/ci.yml)
[![CodeQL](https://github.com/john-broadway/proximo/actions/workflows/codeql.yml/badge.svg)](https://github.com/john-broadway/proximo/actions/workflows/codeql.yml)
[![Release](https://img.shields.io/github/v/release/john-broadway/proximo)](https://github.com/john-broadway/proximo/releases)
[![PyPI](https://img.shields.io/pypi/v/proximo-proxmox)](https://pypi.org/project/proximo-proxmox/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](./pyproject.toml)

> **The Proxmox MCP you can hand the keys.**
>
> The others make you choose: a read-only inspector that's safe because it can't touch anything — or a loaded gun aimed at a cluster you care about. Proximo refuses the trade. Every dangerous move is **planned** (see the blast radius first) and **proven** (a tamper-evident record of every move), and **undoable wherever the platform can snapshot** (it snapshots *before* it acts) — trust built into the substrate, not bolted on after. **Hand an AI agent the keys; keep the receipts.**

*Named for Proximo, the lanista of* Gladiator *— the man who armed the fighter with exactly what he needed, never more, and answered for every move in the arena. That is the whole design: give the operator — human or agent — the reach to act, never the run of the house, accountable for all of it.*

> *"Win the crowd and you will win your freedom."*

---

## Why Proximo exists

Proxmox VE has a full REST API and a terse, powerful CLI — but the MCP landscape around it is split, and neither half is whole:

- **API-based MCP servers** give rich management (nodes, VMs, storage) but **cannot run a command inside an LXC** — that's a structural gap: the Proxmox REST API has *no* container-exec endpoint (it lives in `lxc-attach`, kernel namespaces, no REST surface).
- **SSH-based MCP servers** can exec in containers, but lean on broad shell access with little scoping.

**Few build the principled one** — both halves, on one clean surface, least-privilege, audited, *trustworthy enough to point at a hypervisor you care about.* That's the bar Proximo aims at. Proximo's specific bet is trust **by construction** across the whole control plane.

There is **no official Proxmox MCP** (and likely won't be soon — Proxmox ships the API+CLI and leaves integrations to the community, the same way there's no official Terraform provider). Proximo is a community project, standing on its own.

## What it does

Ask, in plain English, *"why is ct 105 thrashing?"* — and an AI agent pulls node and guest status, tails the logs, and runs a diagnostic *inside* the container to find out. If there's a fix, it shows you the plan before it touches anything, snapshots first, applies, and hands you a signed receipt of exactly what changed.

That's the product: **a hypervisor an AI can operate without being able to wreck it.** Read-only by default. No mutation without a plan first, and the plan refuses destructive ops. It snapshots before any state change, wherever the platform can snapshot. A tamper-evident receipt for every change. The comparison isn't Proximo vs. the GUI — it's **Proximo vs. handing an LLM your root token and hoping.**

Three Proxmox surfaces — one control plane:

| Surface | Backend | For |
|---|---|---|
| **Proxmox VE** | REST API + scoped token | node/guest lifecycle, storage, SDN, identity, HA, firewall |
| **Proxmox Backup Server** | REST API + scoped token | datastores, namespaces, snapshots, sync jobs, GC, verify |
| **Proxmox Mail Gateway** | Ticket auth (PMGAuthCookie) | mail flow, quarantine, filtering rules, domains, services |
| **Container exec** | `ssh` → `pct exec` | run-command-in-container, `psql` convenience, log tailing — the things the API structurally can't do |

Those backends are deliberately boring — anyone can call them. **The product is the trust layer over them.**

## The trust layer — what makes Proximo different

Safe-exec for Proxmox already exists elsewhere. Proximo's distinct angle is the **trust layer for AI-driven infrastructure** — four pillars:

| Pillar | What it does | Status |
|---|---|---|
| **PLAN** | Dry-run by default: every mutation first returns a preview — the exact change, the guest's live state, blast radius, and an honest (advisory, heuristic) risk rating — recorded to the ledger. A mutation can't run without its plan being built and recorded first. (It's a recorded *preview*, not a separate human approval step: one `confirm=true` call records the plan **and** performs the change — so in an agent loop, review the preview yourself.) | ✅ built + redteamed |
| **PROVE** | Hash-chained audit ledger; plans and confirmations both land in it. `audit_verify` is tamper-**evident** — it catches edits, reordering, and insertion. The ledger is **keyed (HMAC-SHA256) by default** (`PROXIMO_AUDIT_KEYED`; opt out with `off`). Catching tail truncation / forged append / full wipe requires an off-box head anchor: pin `audit_verify`'s `"head"` value somewhere the box can't rewrite it and pass it as `expected_head` (or set `PROXIMO_AUDIT_EXPECTED_HEAD`) — that is the strong guarantee. See the honesty note below. | ✅ built + redteamed |
| **UNDO** | Heterogeneous by plane, fail-closed where present: opt-in auto-snapshot before a risky `ct_exec`/`ct_psql` (waited-on, fail-closed if storage can't snapshot); config-revert for guest config; `pve_rollback` + full snapshot lifecycle for guests. Not every PVE plane is snapshottable — firewall/SDN/ACL/token have no rollback primitive — so UNDO covers the snapshottable surface, not every mutation. Undo points aren't auto-pruned — delete with `pve_snapshot_delete`. (Snapshot/rollback are async — poll with `pve_task_status`.) | ✅ built + redteamed |
| **DIAGNOSE** | Read-only evidence battery (failed units, disk, errors, memory, listening ports) + node health (storage/tasks) → advisory flags. Flags surface *incompleteness* too, so an empty list never reads as a false clean bill. | ✅ built + redteamed |

> **Honesty note (load-bearing):** PLAN's risk ratings are an *advisory heuristic*, not a sandbox. `LOW` means "does not change state," **not** "safe" — a read can still exfiltrate. The absence of a `HIGH` flag is **not** a safety signal; the destructive-pattern signatures are curated, not exhaustive. Review every change yourself.

## At scale

One container is the demo. A cluster is the point.

- **The whole cluster in one call.** `pve_cluster_resources` returns every VM, node, storage pool, and SDN object across the cluster — so the agent answers *"what's the state of everything?"* in one breath, not node by node.
- **One tamper-evident record of every change, across every node.** This is what a human at the CLI never walks away with: every mutation Proximo makes — any node, any operator or agent — lands in a single hash-chained PROVE ledger, and `audit_verify` proves it wasn't edited, reordered, or truncated. *"Show me every state-changing action on the cluster this month, and prove the log wasn't touched"* becomes a query you can actually answer.
- **Where the time comes back.** On one node, a senior at the CLI is faster — and that's fine. Across a dozen nodes and hundreds of guests the tedium multiplies and there's no unified record; that's where delegating execution to a *bounded, audited* agent earns its keep.

Live-proven against real Proxmox infrastructure: **PVE 9.2** (3-node cluster — offline guest migration, HA lifecycle, governance plane), **PBS 4.2** (datastores, snapshots, GC, namespaces, prune/verify, sync), and **PMG 9.1** (auth, read shapes, CRUD cycles, service control, RuleDB, quarantine) — every step recorded and verified through PROVE.

> **Honest scope:** Proximo is configured per endpoint, so "fleet" here means **a cluster and its nodes**, not a set of separate, independent clusters driven from one process. Point it at the cluster you operate.

## Principles (the mantra, baked in — not bolted on)

- **Ethical** — least-privilege posture (exec off by default; bounded by the token you scope), every action audited, mutations confirm-gated, the PVE token read only at call time, never logged or persisted.
- **Solid** — real tests (unit + a live smoke against a throwaway CTID), typed, documented, no silent failures.
- **Strong** — does the hard thing (container exec) cleanly and least-privileged (fail-closed CTID allowlist, opt-in). *(Container exec isn't unique — the field leader has it too; the differentiator is the trust layer below, not the exec.)*
- **Passion + craft** — redteamed and linted before it's called done; shipped proud — docs, license, community-ready.

## Install & run

> 🧭 **New to Proximo?** Start with **[SETUP.md](SETUP.md)** — a beginner-proof, token-first walkthrough:
> create a least-privilege (read-only) token, verify what it can/can't do with `proximo doctor`, then
> grant scoped write only when you're ready. The token is the floor your keys never leave.

> 📦 **`0.8.0` — published.** On [PyPI](https://pypi.org/project/proximo-proxmox/) (`proximo-proxmox`),
> [GitHub](https://github.com/john-broadway/proximo/releases/tag/v0.8.0) (CI green), and
> [GHCR](https://github.com/john-broadway/proximo/pkgs/container/proximo) (signed multi-arch image) — all three live.
> New in 0.8.0: **103-tool PMG surface** (Proxmox Mail Gateway — ticket auth, quarantine, RuleDB
> filtering engine, service control, config CRUD, backup) + **+6 PBS gap tools** + bugfix for
> `pbs_group_change_owner` (POST, not PUT). All three Proxmox surfaces now live-proven.
> See the [CHANGELOG](./CHANGELOG.md).

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
> The default path never touches the hypervisor host — management goes over the Proxmox **API** (scoped token). The two opt-in edges are the exceptions: exec uses your existing **ssh** to PVE to run `pct exec` as root on the host; the qemu-agent edge runs in-guest ops via the API. Both are off by default, each scoped by its own fail-closed allowlist (`PROXIMO_CT_ALLOWLIST` / `PROXIMO_AGENT_ALLOWLIST`), and say so loudly.
>
> *(A Debian package is deferred/optional — the MCP world installs via `uvx`/pip/Docker, not `apt`.)*

## Status — the arena record

🩸 **0.8.0 — published** on [PyPI](https://pypi.org/project/proximo-proxmox/) (`pip install proximo-proxmox`), [GitHub](https://github.com/john-broadway/proximo), and [GHCR](https://github.com/john-broadway/proximo/pkgs/container/proximo) (signed multi-arch image). _(0.1.1 "Spaniard" was the first public cut, 2026-06-10.)_
All four trust pillars (PLAN · PROVE · UNDO · DIAGNOSE) built and redteamed. **325 MCP tools. 4,100+ tests, 0 skipped, ruff + pyright clean** — these are **mock/in-process** (no socket); CI runs them on GitHub's runners. **The real-Proxmox proofs below are a separate, by-hand live-smoke harness — not in that count, not in CI.** (the computed blast-radius engine covers the destructive tool surface — eleven op-classes that
name the specific guests, nodes, ACL principals, or disks a dangerous op would harm, so nothing falls back
to a bare confirm. Atop 0.5.0's signed A2A cards + native async-task wait.)

**Proven against real Proxmox** (not mocks):
- The trust spine end-to-end, the core provisioning/config mutate cycle, and PBS read shapes.
- The **governance/dangerous plane** — identity (roles/groups/users/ACLs), storage, **SDN pending
  objects** (zone/vnet/subnet create→read→delete), realm create (LDAP/AD/OpenID via an `options`
  dict) — full create→read→delete cycles against a real **PVE 9.2** API, PROVE ledger verified
  throughout. **(SDN/network *apply* — the host-network reload — is deliberately never fired live;
  it carries unrecoverable risk.)**
- The **0.2.0 object planes** — firewall objects (aliases/IP-sets/security-groups/options), HA
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

**Not yet proven — said plainly:** the remaining 325-tool surface runs against mocks for shapes
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

Built by **John Broadway** with **Claude** and **Maude** — a human–AI partnership, and the first thing we made on this box to give away to the world.

Claude's contribution spans eras, credited honestly: **Claude Opus 4.8** built the trust pillars and the
tool surface (2026-06-07 → 06-09); **Claude Fable 5** ran the 101-agent release audit and the publish
(2026-06-10). Every commit carries its co-author trailer.

---

*"Are you not entertained?"* — stars, issues, and sparring partners welcome. **Strength and honor.** ⚔️
