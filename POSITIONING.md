# Proximo — Positioning & Competitive Reality

> **Created** 2026-06-07 · **Rewritten** 2026-06-09 (reconciled to the corrected field survey in
> [`LANDSCAPE.md`](./LANDSCAPE.md); the earlier "uncontested / 3-0 / only one with trust" framing was
> wrong and has been removed, not annotated). **Refreshed 2026-06-10** (governance/dangerous plane
> live-proven to execute; A2A perimeter parity closed; competitor numbers re-verified).
> **Refreshed 2026-06-19** (field re-verified at source: OWASP **MCP08 "Lack of Audit and Telemetry"** +
> the MCP security-guidance "blast radius" / "irrecoverable data loss on the host" phrasing re-confirmed
> verbatim; **proxxx corrected** — it now ships a *lifecycle-only* 25-tool MCP surface (`src/mcp/tools.rs`),
> its governance/state plane and audit-verify staying in the CLI/TUI, off the agent surface. Competitor
> **star counts are left at the 2026-06-10 survey** — a deliberate number-refresh is a separate pass).
> Competitive claims re-verified **as of 2026-06-19** (prior full survey 2026-06-10), source-read from the repos (not READMEs alone). The MCP
> leaders ship ~weekly — **re-verify every competitive claim before any public Proximo claim.**
> No manufactured foils: where Proximo loses, is unproven, or is merely late, this says so.

## Where Proximo honestly stands

Proximo is a **late entrant** in a contested lane — v0.6.2, public on GitHub since 2026-06-10,
on PyPI as `proximo-proxmox` and on GHCR (signed multi-arch image), zero adoption so far. The trust spine (PLAN/UNDO/PROVE) and the core VM/snapshot/backup lifecycle have been
live-proven against real Proxmox hosts (a single node plus a nested 3-node test cluster — not production scale). The broad *governance* plane has now been **live-proven to execute**
against a real PVE 9.2 API, including on a nested 3-node test cluster: identity (role/group/user/ACL),
storage, SDN apply, network-interface apply, realm create — all exercised through a full create→read→delete
cycle with PROVE ledger verified throughout; plus offline guest migration (including local-disk) and
HA-config (resource add/list/remove) on the test cluster.

Still plainly unproven: real HA **fencing** (hardware watchdog), **online** live-migration (shared
storage), and production scale. A significant portion of the remaining ~145 MCP tools — the non-governance
lifecycle surface — continues to run against mocks only. The proof is materially farther along; it is not
complete.

It is **not first, not the most tools, and not "the only one with trust."** Anyone claiming otherwise
hasn't read the field. What Proximo *is*: an architecture-first bet that trust belongs in the **substrate**,
aimed at the part of Proxmox nobody else hands to an agent.

## The field (as of 2026-06-10 — full per-lane detail in `LANDSCAPE.md`)

The Proxmox-MCP lane is contested, with four distinct archetypes plus two cross-cuts:

| Archetype | Who (2026-06-10) | Posture, source-read |
|---|---|---|
| **Safe inspector** (most-starred) | canvrno/ProxmoxMCP (~261★, ~6 tools) | Read-mostly "safe inspector." Popular *because* it doesn't hold the knives — the market already votes for caution. |
| **Governance leader** (most active) | RekklesNA/ProxmoxMCP-Plus (~241★, ~42 tools, v0.5.8) | Genuine gating: `command_policy`, `approval_token`, TLS, DNS-rebind, job tracking. **But permissive by default** (`high_risk_mode=audit_only`, approval off) and **no dry-run / no auto-rollback / no blast-radius / no firewall·SDN·ACL·HA modules.** |
| **Trust peer** (respect it) | fabriziosalmi/proxxx (~15★, Rust cockpit, v0.8.4) | The real trust peer: pre-flight **risk gate (PLAN-ish)**, **HMAC-keyed, offline-verifiable audit chain** (arguably stronger than Proximo's *default-unkeyed* one), **Telegram HITL**. **But no auto-UNDO** (no auto-snapshot-before-mutate — it doesn't take the snapshot for you). proxxx now ships a **25-tool MCP surface, but it's lifecycle/inventory-only** (`src/mcp/tools.rs`, verified 2026-06-19) — its firewall/SDN/ACL/PBS-writes, GitOps state engine, and audit-verify stay in the **CLI/TUI, off the surface an agent drives.** |
| **Breadth rival** | chajus1/proxmox-mcp-enhanced (~115 tools) | Claims to cover "every aspect." Trust layer unverified/absent — but it **kills any "most complete by count" pitch. Count is not a moat.** |

Two cross-cuts decide framing:
- **Multi-backend / homelab-fleet class** (bshandley/homelab-mcp and kin) — "AI runs my *whole* homelab,"
  Proxmox as one backend among Docker/OPNsense/TrueNAS/HA. A *breadth* bet vs Proximo's *depth* bet. This
  is the class that hid proxxx from a keyword search — **watch it**; if "AI runs my homelab" becomes the
  framing, these, not the Proxmox-MCP leaders, are the real threat.
- **MCP gateways / guardrails** (IBM ContextForge 3.8k★, Docker MCP Gateway, Lasso, …) — add
  auth/policy/audit/approval in front of *any* MCP. They are **resource-blind**: they can gate and log a
  tool call, but they cannot snapshot a VM or compute the blast radius of an ACL change, because they don't
  understand the resource. **PLAN and UNDO are domain-specific by necessity** — a generic layer can't do
  them *for* Proxmox.

## The moat — what survives the leader's next release

**Not "four features they lack."** A shallow `--dry-run` flag, or a hash bolted onto an existing audit log,
is **copyable** — and the leader's trajectory is *into* governance. A feature-absence pitch collapses the
week RekklesNA ships a flag. The durable thesis is the part that **cannot be retrofitted or assembled**:

> **Trust by construction × the governance plane on the MCP surface × auto-UNDO.**

1. **By construction.** Every tool inherits PLAN (dry-run + live state + honest blast-radius, by default)
   and PROVE (tamper-evident hash-chained ledger) as *substrate* — not opt-in, not per-tool; mutating
   guest/exec paths add fail-closed auto-UNDO wherever the platform can snapshot. You cannot retrofit auto-snapshot-before-every-mutation + a chain + real blast-radius preview
   onto 40–115 existing flat tools after the fact; it has to be the foundation. Proximo built the
   foundation first, then the tools on top of it.
2. **The governance plane on the MCP surface.** Firewall · SDN/network · cluster-HA/migration ·
   ACL/users/roles/realms · PBS — exposed *to the agent*, every op PLAN+UNDO+PROVE. RekklesNA has no module
   for it; proxxx keeps it in its CLI/TUI, off its lifecycle-only MCP surface; the gateways can't reach it. This is the empty intersection.
   *Honesty:* the identity/storage/SDN/network/realm surface and offline migration + HA-config have been
   **live-proven to execute** against a real PVE 9.2 API (including a nested 3-node test cluster), with PROVE
   verified throughout. Still unproven at live scale: real HA fencing (hardware watchdog), online
   live-migration (shared storage), and production load. A portion of the broader ~145-tool surface still
   runs against mocks. The thesis is sound and the execution is confirmed on the differentiating plane; the
   remaining proof is lifecycle breadth and production scale (see Honest risks).
3. **Auto-UNDO.** Fail-closed snapshot-before-mutate (waited-on) + one-call revert. proxxx *previews* a
   rollback; it does not take the snapshot for you. This is the single piece **no competitor verified above
   has**, and the hardest to bolt onto a flat tool.

For a flat tool, each new operation is new **attack** surface; for Proximo, each new operation is new
**trust** surface — so the moat *widens* as coverage grows, instead of thinning.

**Explicitly NOT the moat** (don't pitch these — they're false or fragile):
- *First* — no. *Most tools* — no (chajus1 ≈ matches Proximo's count).
- *"Only one with trust"* — no; proxxx (risk-gate + keyed chain + HITL) and RekklesNA (command_policy +
  approval-token) both have real trust mechanisms.
- *Cryptographic depth* — Proximo's chain defaults **unkeyed**; an opt-in HMAC-keyed mode exists (matches
  proxxx when enabled), but the real guarantee is the **off-box `head()` anchor**, not the hash. Auto-UNDO
  and blast-radius are the defensible depth, not the cryptography.

**The assemble-from-parts threat, named honestly:** **ContextForge (audit/policy/approval) + RekklesNA
(coverage) = a credible audit + policy + HITL story over Proxmox *today*, with no new code.** That combo
lacks PLAN/UNDO/blast-radius. Proximo wins only on the parts that can't be assembled — so it must lead on
PLAN (live-state + blast-radius), UNDO (auto-snapshot/revert), and governance-plane coverage, **never on
"has an audit log."**

## What the market signals

The **most-starred** Proxmox MCP in the field is the **read-mostly** one (canvrno, ~261★, ~6 tools).
People star the *safe* inspector over the feature-rich mutator. The market is already wary of handing an
MCP the knives — which is precisely the fear an in-substrate trust layer answers.

## The tailwind — recognized and growing (2026), told straight

- **OWASP MCP Top 10** names **MCP08 "Lack of Audit and Telemetry"** → recommends *"immutable audit
  trails"*. That is **PROVE, codified as a top-10 risk** (plus MCP02 privilege/scope creep, MCP05 command
  injection). ([owasp.org/www-project-mcp-top-10](https://owasp.org/www-project-mcp-top-10/))
- **Official MCP security best practices** center auth/SSRF/consent and explicitly name **"blast radius,"**
  least-privilege, *"irrecoverable data loss on the host machine,"* and consent-before-dangerous-commands —
  but say nothing about mutation **preview** or **undo**. The spec defines what is *possible*, not what is
  *safe* to mutate. ([modelcontextprotocol.io](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices))
- **2026 discourse** (Microsoft, Strata, CSA, StackGen): *"adoption has outpaced governance"*; ~30 CVEs in
  60 days, ~200k vulnerable instances; consensus that **destructive ops need a human checkpoint** + **audit
  retained in your own environment.**
- **Honest nuance:** the frameworks loudly bless **audit (PROVE)** and **least-privilege / human-approval**.
  **Dry-run preview (PLAN)** and **auto-undo (UNDO)** are still *ahead* of what OWASP and the MCP spec have
  codified — Proximo's innovation beyond the recognized need, **not** yet externally blessed. State it as a
  strength, not as borrowed authority.

## Table-stakes Proximo must match (the floor)

- The leader's ~42-tool VM/LXC lifecycle + snapshots + backup + ISO + storage + discovery + job tracking.
- The leader's emerging gating bar: command policy, approval gating, transport hardening.
- Coverage is the **floor**, not the pitch — under-covering the dangerous ops undermines the thesis (you
  can only preview/undo/prove what you expose).

## Perimeter parity — MCP local, A2A closed

The **MCP face** remains local stdio — no network bind, secrets-by-path, fail-closed allowlist, opt-in
exec. That is the smallest attack surface in the field (smaller than the leader's multi-transport/OpenAPI
surface). **The day Proximo adds a remote MCP transport, it inherits the leader's perimeter to-do list**
(enforce-auth, bind hardening, per-command approval, DNS-rebind protection). A best-in-class trust layer
behind a weak door is a contradiction — the trust story must not excuse the perimeter. Belt-and-suspenders.

The **A2A face** has reached perimeter parity: fail-closed public bind (requests refused without a token),
bearer auth on the control endpoint, and `PROXIMO_A2A_ALLOWED_HOSTS` Host/DNS-rebind allowlist enforcement
— previously the A2A face only warned. This matches the leader's auth/bind/DNS-rebind hardening posture.

## Honest risks

- **Proof gap narrowed, not closed.** The governance/dangerous plane (identity/storage/SDN/network/realm,
  offline migration, HA-config) is now **live-proven to execute** against a real PVE 9.2 API. But real HA
  **fencing** (hardware watchdog), **online** live-migration (shared storage), and production-scale load
  remain unproven. A portion of the broader lifecycle surface still runs against mocks. "Most complete
  trust-instrumented control plane" is still a goal, not yet a fully proven claim.
- **Official Proxmox MCP.** Field chatter suggests Proxmox may ship an official MCP server. An official
  basic server would commoditize the lifecycle layer (VM/LXC/snapshot/backup), removing it as
  differentiator. Proximo's durable answer is the **dangerous/governance plane + trust-by-construction**
  that an official day-one server is unlikely to carry — but this risk is real and should not be dismissed.
- **Time-sensitivity.** Every competitive finding here is 2026-06-10; the leaders ship ~weekly. Re-verify
  before any public statement.
- **Bolt-on risk.** A shallow trust feature from the leader is plausible; the defense is depth + coverage +
  by-construction (the moat above), never feature-novelty.
- **Still v0.6.2, brand-new public, zero adoption.** On GitHub + PyPI (`proximo-proxmox`) + GHCR (signed image) — all three live. No
  "the only one" / "the best" claims until they are true *and* live.

## The one-liner

*Everyone secures the door. Proximo builds the safety net into the substrate — every mutation carries a
preview, a fail-closed undo, and a tamper-evident record by construction, across a control plane built to
reach the governance ops no one else exposes to an agent.*
