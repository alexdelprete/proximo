# Proximo

[![CI](https://github.com/john-broadway/proximo/actions/workflows/ci.yml/badge.svg)](https://github.com/john-broadway/proximo/actions/workflows/ci.yml)
[![CodeQL](https://github.com/john-broadway/proximo/actions/workflows/codeql.yml/badge.svg)](https://github.com/john-broadway/proximo/actions/workflows/codeql.yml)
[![Release](https://img.shields.io/github/v/release/john-broadway/proximo)](https://github.com/john-broadway/proximo/releases)
[![PyPI](https://img.shields.io/pypi/v/proximo-proxmox)](https://pypi.org/project/proximo-proxmox/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](./pyproject.toml)

> **The ethical Proxmox MCP.** API management *and* scoped in-container execution — behind clean, native tools: exec off by default, bounded by the token you scope, every action audited.

*Named for Proximo, the lanista in* Gladiator *who equips the fighter and gives him his shot at freedom — Proximo hands the operator the means to act on the machine, no more than needed, accountable for every move.*

> *"Win the crowd and you will win your freedom."* — Proximo

**Strength and honor.** — the creed: solid, strong, accountable.

---

## Why Proximo exists

Proxmox VE has a full REST API and a terse, powerful CLI — but the MCP landscape around it is split, and neither half is whole:

- **API-based MCP servers** give rich management (nodes, VMs, storage) but **cannot run a command inside an LXC** — that's a structural gap: the Proxmox REST API has *no* container-exec endpoint (it lives in `lxc-attach`, kernel namespaces, no REST surface).
- **SSH-based MCP servers** can exec in containers, but lean on broad shell access with little scoping.

**Few build the principled one** — both halves, on one clean surface, least-privilege, audited, *trustworthy enough to point at a hypervisor you care about.* That's the bar Proximo aims at. *(Others work the trust angle too — notably `fabriziosalmi/proxxx`; see `LANDSCAPE.md`. Proximo's specific bet is trust **by construction** across the whole control plane.)*

There is **no official Proxmox MCP** (and likely won't be soon — Proxmox ships the API+CLI and leaves integrations to the community, the same way there's no official Terraform provider). Proximo is a community project, standing on its own.

## What it does

Two backends behind one tool surface:

| Backend | Mechanism | For |
|---|---|---|
| **Management** | Proxmox REST API + scoped token | node status, list/inspect guests, lifecycle (start/stop/reboot) |
| **Exec** | `ssh` → `pct exec` | run-command-in-container, `psql` convenience, log tailing — the things the API structurally can't do |

## Principles (the mantra, baked in — not bolted on)

- **Ethical** — least-privilege posture (exec off by default; bounded by the token you scope), every action audited, mutations confirm-gated, the PVE token read only at call time, never logged or persisted.
- **Solid** — real tests (unit + a live smoke against a throwaway CTID), typed, documented, no silent failures.
- **Strong** — does the hard thing (container exec) cleanly and least-privileged (fail-closed CTID allowlist, opt-in). *(Container exec isn't unique — the field leader has it too; the differentiator is the trust layer below, not the exec.)*
- **Passion + craft** — redteamed and linted before it's called done; shipped proud — docs, license, community-ready.

## Install & run

> 📦 **`0.6.5` — published.** On [PyPI](https://pypi.org/project/proximo-proxmox/) (`proximo-proxmox`),
> [GitHub](https://github.com/john-broadway/proximo/releases/tag/v0.6.5) (CI green), and
> [GHCR](https://github.com/john-broadway/proximo/pkgs/container/proximo) (signed multi-arch image) — all three live.

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

> **Safe by default:** Proximo is **API-only** out of the box. The in-container exec edge is **opt-in** (`PROXIMO_ENABLE_EXEC=1`) and tells you plainly that it grants near-root on the host.
>
> The default path never touches the hypervisor host — management goes over the Proxmox **API** (scoped token). The opt-in exec edge is the one exception: it uses your existing **ssh** to PVE to run `pct exec` as root on the host. That's exactly why it's off by default and says so loudly.
>
> *(A Debian package is deferred/optional — the MCP world installs via `uvx`/pip/Docker, not `apt`.)*

## The trust layer — what makes Proximo different

Safe-exec for Proxmox already exists elsewhere. Proximo's distinct angle is the **trust layer for AI-driven infrastructure** — four pillars (see `POSITIONING.md`):

| Pillar | What it does | Status |
|---|---|---|
| **PLAN** | Dry-run by default: every mutation first returns a preview — the exact change, the guest's live state, blast radius, and an honest (advisory, heuristic) risk rating — recorded to the ledger. A mutation can't run without its plan being built and recorded first. (It's a recorded *preview*, not a separate human approval step: one `confirm=true` call records the plan **and** performs the change — so in an agent loop, review the preview yourself.) | ✅ built + redteamed |
| **PROVE** | Hash-chained audit ledger; plans and confirmations both land in it. `audit_verify` is tamper-**evident** — it catches edits, reordering, and insertion. Catching truncation/wipe/forged-tail needs the opt-in keyed mode + an off-box head anchor (see the honesty note); the default ledger is unkeyed. | ✅ built + redteamed |
| **UNDO** | Heterogeneous by plane, fail-closed where present: opt-in auto-snapshot before a risky `ct_exec`/`ct_psql` (waited-on, fail-closed if storage can't snapshot); config-revert for guest config; `pve_rollback` + full snapshot lifecycle for guests. Not every PVE plane is snapshottable — firewall/SDN/ACL/token have no rollback primitive — so UNDO covers the snapshottable surface, not every mutation. Undo points aren't auto-pruned — delete with `pve_snapshot_delete`. (Snapshot/rollback are async — poll with `pve_task_status`.) | ✅ built + redteamed |
| **DIAGNOSE** | Read-only evidence battery (failed units, disk, errors, memory, listening ports) + node health (storage/tasks) → advisory flags. Flags surface *incompleteness* too, so an empty list never reads as a false clean bill. | ✅ built + redteamed |

> **Honesty note (load-bearing):** PLAN's risk ratings are an *advisory heuristic*, not a sandbox. `LOW` means "does not change state," **not** "safe" — a read can still exfiltrate. The absence of a `HIGH` flag is **not** a safety signal; the destructive-pattern signatures are curated, not exhaustive. Review every change yourself.

## Status — the arena record

🩸 **0.6.5 — published** on [PyPI](https://pypi.org/project/proximo-proxmox/) (`pip install proximo-proxmox`), [GitHub](https://github.com/john-broadway/proximo), and [GHCR](https://github.com/john-broadway/proximo/pkgs/container/proximo) (signed multi-arch image). _(0.1.1 "Spaniard" was the first public cut, 2026-06-10.)_
All four trust pillars (PLAN · PROVE · UNDO · DIAGNOSE) built and redteamed. **145 MCP tools. 2,500+ tests, 0 skipped, ruff + pyright clean** — these are **mock/in-process** (no socket); CI runs them on GitHub's runners. **The real-PVE proofs below are a separate, by-hand live-smoke harness — not in that count, not in CI.** (the computed blast-radius engine covers the destructive tool surface — eleven op-classes that
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
- Both protocol faces driven by real clients end-to-end: MCP over stdio, and A2A by the official a2a-sdk.

**Not yet proven — said plainly:** most of the 145-tool surface still runs against mocks; real HA
*fencing* (needs a hardware watchdog), *online* live-migration (needs shared storage), and behavior at
production scale. The full, unflattering field comparison lives in [`LANDSCAPE.md`](./LANDSCAPE.md).

**The A2A face (experimental, opt-in):** `pip install 'proximo-proxmox[a2a]'`, then `proximo-a2a` — a curated
16-skill slice over Agent2Agent that **routes through the same trust core** (PLAN/PROVE/UNDO inherited;
there is no second code path to bypass). Fail-closed perimeter: non-localhost binds are refused without a
bearer token (`PROXIMO_A2A_TOKEN_FILE`); Host-header allowlist defends against DNS rebinding. Ledger note:
an opt-in HMAC-keyed chain is available (`PROXIMO_AUDIT_KEY_PATH`); the default is unkeyed —
tamper-*evident*, not tamper-*proof* — and an off-box `head()` anchor is the strong guarantee either way.
`ct_psql` records the SQL body and `ct_exec` the command argv it runs (the operator's own input) for a
complete audit trail; set `PROXIMO_LEDGER_REDACT=1` to record a fingerprint (sha256 + kind + length)
instead, when the SQL/command may carry secrets/PII. The PVE API token is never written to the ledger.

### What's next
- [x] **PyPI** — `proximo-proxmox` published 2026-06-10; `uvx proximo-proxmox` works
- [x] **GHCR** — signed multi-arch image (`ghcr.io/john-broadway/proximo:0.6.5` / `latest`) via a release Action
- [x] Firewall objects · HA rules · SDN object CRUD — live-proven on PVE 9.2 (0.2.0)
- [ ] Live smoke of the remaining surface (PBS-mutate); HA fencing + online migration when the hardware exists
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
