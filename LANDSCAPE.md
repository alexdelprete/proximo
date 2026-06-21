# Proximo — The Proxmox Automation Landscape

> **Created** 2026-06-08 · **Refreshed** 2026-06-09 (method-corrected sweep; see Method).
> **Refreshed 2026-06-10** (competitor numbers re-verified; Proximo governance plane now live-proven to
> execute; A2A perimeter parity closed; official-Proxmox-MCP threat added).
> An honest, source-verified survey of the Proxmox automation field across four modalities
> (MCP / A2A / AI / API-IaC), with Proximo's own position stated plainly — including where it is late,
> unproven, or simply not first. No manufactured foils.

> **Method.** Competitors are ranked by real popularity (GitHub stars, registry presence). Tool counts
> and safety features were re-read from the repositories on 2026-06-09 — not inferred from READMEs or
> star counts, which miss feature drift. A keyword-only search (`proxmox` + `mcp`/`ai`) misses tools
> whose primary identity is something else — e.g. a multi-backend homelab cockpit that exposes Proxmox
> as one backend among many — so this survey adds an **off-keyword pass** for that class. A survey's
> silence means "not found," never "does not exist"; treat each finding as as-of its date.

---

## TL;DR — the Proxmox field, four lanes

1. **MCP (AI-native) — contested; Proximo is not first.** Two ~250★ leaders (**canvrno** ~261★, read-only
   "safe inspector" with ~6 tools; **RekklesNA/ProxmoxMCP-Plus** ~241★, the active governance leader), a
   long <50★ tail, and one real *trust* peer (**proxxx**). **Raw tool-count is not a moat:**
   `chajus1/proxmox-mcp-enhanced` already claims **115 tools** — now fewer than Proximo's 145, though a
   raw count says nothing about whether the tools are proven (a significant portion of Proximo's lifecycle
   surface still runs against mocks — see *Where Proximo stands*).
2. **A2A (agent-to-agent) — greenfield for Proxmox.** No dedicated open A2A agent-card/server for Proxmox
   found (off-keyword sweep included). Homelabbers run multi-agent systems *on* Proxmox; nobody exposes
   Proxmox *as* an A2A participant. Demand is unverified — flagged, not claimed.
3. **AI (non-MCP automation) — hobby-tier, unconsolidated.** n8n templates, Prox-AI, OpenClaw, Clawdbot,
   Paperclip — real activity, near-zero stars, no serious product. The serious builders are choosing MCP,
   so this lane mostly feeds Lane 1.
4. **API / IaC — the mature base layer (different modality, not a rival).** Terraform (Telmate ~2.9k★, bpg
   ~2k★), Ansible `community.general.proxmox`, proxmoxer ~787★. Proximo doesn't compete here — but its
   PLAN/UNDO maps onto the **plan/apply/destroy** idiom those users already trust.

**The honest summary:** Proximo is a late, unstarred entrant in the contested MCP lane. Its defensible
thesis is **not** "first," "most tools," or "the only one with trust." It is **trust *by construction***
(every mutation carries PLAN + UNDO + PROVE in-band, fail-closed) **× coverage of the dangerous/governance
plane** (firewall/SDN/ACL/roles/realms/PBS) that even the leaders keep off the MCP surface **× auto-UNDO**
(fail-closed snapshot-before-mutate). You can bolt a `--dry-run` flag onto one tool; you cannot retrofit
auto-snapshot + hash-chain + blast-radius across 100+ existing flat tools after the fact.

---

## Lane 1 — MCP servers for Proxmox VE (ranked, stars re-pulled 2026-06-10)

| # | Repo | ★ | Tools | Lang | What it is / safety posture (source-verified 06-10) |
|---|---|---|---|---|---|
| 1 | **canvrno/ProxmoxMCP** | ~261 | ~6 | Py | Most-starred. Read-mostly "safe inspector," built for Cline. Popular *because* it doesn't hold the knives. |
| 2 | **RekklesNA/ProxmoxMCP-Plus** | ~241 | ~42 | Py | **Active governance leader** (v0.5.8, Jun 7 2026). VMs/CT/snap/backup/ISO/storage/cluster + SSH-exec + job-control (list/get/poll/cancel/retry). Gov = `command_policy` + `approval_token` + TLS + DNS-rebind. **NO dry-run / NO auto-rollback / NO blast-radius / NO firewall·SDN·ACL·HA.** Permissive by default. |
| 3 | **chajus1/proxmox-mcp-enhanced** | ~10 | **115** | Py | ⚠️ **The breadth rival.** Claims 115 tools "covering every aspect." Trust layer **unverified/absent** — but it rules out any "most complete by count" claim. Its dangerous-op coverage should be verified before anyone claims the completeness lane. |
| 4 | **fabriziosalmi/proxxx** | ~15 | **25 (MCP)** | Rust | **The real TRUST peer** (v0.8.4, May 30 2026, 43 releases). MCP surface = VM/LXC lifecycle + snapshots + provisioning + cluster/node read **only** (25-tool compile-time registry, `src/mcp/tools.rs`, **corrected 2026-06-19** — the earlier "PBS browse/restore + GitOps state diff/`--dry-run` + audit-verify on MCP" was wrong; those are CLI/TUI-only, consistent with this row's own closing note and line 63). Has a pre-flight **risk gate (PLAN-ish)** + **HMAC-keyed offline-verifiable audit chain** (PROVE — arguably stronger than Proximo's default-unkeyed ledger) + Telegram **HITL**. **No auto-UNDO** (read-only rollback *preview* only). **Firewall/SDN/ACL/PBS-writes are NOT on the MCP surface** — they live in the human TUI. |
| 5 | gilby125/mcp-proxmox | ~41 | ~55 | JS | Configurable permissions. |
| 6 | Markermav/ProxmoxMCP-advance | ~24 | — | Py | Multi-client (Claude/Goose/Cline). |
| 7 | bsahane/mcp-proxmox | ~18 | — | Py | FastMCP, token auth, monitoring. |
| 8 | mdlmarkham/TailOpsMCP | ~13 | — | Py | Homelab ops over Tailscale (multi-host; see Cross-cut A). |
| 9 | tyxak/remotepower | ~12 | — | Py | Dashboard + CVE/patch + Proxmox MCP. |
| 10 | antonio-mello-ai/mcp-proxmox | ~11 | — | Py | Cluster mgmt via AI. |
| — | mjrestivo16 (35 tools), Samik081 (TS), jmerelnyc, GethosTheWalrus, agentify-sh, husniadil (PyPI), heybearc, ry-ops, plgonzalezrx8 (read-only+confirm), Zaptimist (ssh-exec), rodaddy (forks) | <10 | — | mix | The long tail. Registry-listed (PulseMCP/mcpmarket/Glama). |

**PBS-specific MCPs (PBS is not whitespace):** `szoran53/pbs-mcp-server` (TS), `ahmetem/pbs-mcp` (Py) —
datastore/snapshot/GC/verify/prune. proxxx covers PBS *browse/restore* inside its cockpit.

**Where Proximo differs (Lane 1):** the governance leader (RekklesNA) is permissive-by-default with no
PLAN/UNDO; the trust peer (proxxx) has PLAN+PROVE+HITL but keeps the dangerous plane out of MCP and has no
auto-UNDO; the breadth rival (chajus1) has count but no verified trust. The intersection none of them
holds — *the full firewall/SDN/ACL/roles/realms/PBS plane, exposed to the agent over MCP, every tool
PLAN+UNDO+PROVE by construction, fail-closed by default* — is where Proximo aims. That intersection is
currently empty.

## Lane 2 — A2A (agent-to-agent) for Proxmox — greenfield

- **No open A2A agent-card / server for Proxmox found** (incl. off-keyword sweep). A2A itself is large
  (Google → Linux Foundation, 50+ partners; JSON-RPC/gRPC/REST + SSE + Agent Cards) — but nobody has
  shipped "Proxmox as a first-class A2A participant."
- Closest: commercial **Mindflow** "Proxmox VE agent"; homelabbers running *multi-agent systems on*
  Proxmox (Paperclip, Clawdbot) — agents-hosted-on-Proxmox, not Proxmox-as-agent.
- **Proximo's position:** an A2A Agent Card for Proxmox ("the Proxmox operator agent; here are its skills")
  would be first in this lane. Demand is unverified — no signal yet that anyone is asking.

## Lane 3 — AI (non-MCP automation) for Proxmox — hobby-tier

| Project | Signal | What it is |
|---|---|---|
| **n8n "Proxmox AI agent" template** | popular no-code path | NL→Proxmox API via n8n + genAI; the most-reached-for non-coder route. |
| **folkvarlabs/Prox-AI** | ~5★, HCL | Terraform-config *generator* via Google Forms + cost-approval. Not an agent. |
| **OpenClaw** | — | Read-only LLM-backed Proxmox interface. |
| **Clawdbot / Paperclip** | — | LLM-with-tools runtimes deployed *in* Proxmox LXCs. |

No serious consolidated product here; the real builders pick MCP (Lane 1). This lane is a feeder, not a
separate front — though a one-command no-code on-ramp (e.g. an n8n node) would reach the non-coder crowd.

## Lane 4 — API / IaC clients — the mature base layer (different modality)

Terraform **bpg** ~2k★ (modern leader, plan/apply/destroy) & **Telmate** ~2.9k★ (legacy) · Ansible
`community.general.proxmox` (huge usage) · **proxmoxer** ~787★ (dominant Py wrapper) · Go (Telmate ~487,
luthermonson ~267) · **Corsinvest cv4pve** suite (admin/autosnap/diag/metrics/botgram) · **CAPMOX** ~447★
(K8s Cluster-API). Proximo doesn't rival these — but their users already trust **plan/apply** semantics, so
Proximo's PLAN/UNDO speaks a dialect they know. Leverage, not competition.

---

## Cross-cut A — the multi-backend / homelab-fleet shape

These never surface under "proxmox mcp"; Proxmox is one backend among several. This is the class a
keyword search misses, and the one to keep watching:
- **bshandley/homelab-mcp** — MCP over Docker + OPNsense (firewall) + TrueNAS + **Proxmox** + Home Assistant;
  read-only→write capability tiers. A unified-homelab play on the "AI runs my whole homelab" pitch.
- **AI-Engineering-at/homelab-mcp-bundle** (~4★) — 8-server homelab bundle incl. Proxmox.
- **mdlmarkham/TailOpsMCP** (~13★) — multi-host homelab ops over Tailscale.
- **shareed2k/Honey** — searches service instances across platforms incl. Proxmox.

**Implication:** Proximo's bet is *depth on one platform with trust*; this class's bet is *breadth across
the homelab*. Different bets — but if "AI runs my homelab" becomes the dominant framing, the breadth
players, not the Proxmox-MCP leaders, are the more direct competition.

## Cross-cut B — generic trust layers: can someone add PLAN/UNDO *for* Proxmox without building it?

The 2026 hot category is **MCP gateways / guardrails** — they sit in front of *any* MCP and add governance:
**IBM ContextForge** (3.8k★, Apache-2.0; proxies MCP **and A2A** and REST), **Docker MCP Gateway**,
**Lasso**, **Bifrost**, **TrueFoundry**, **Portkey**, **MintMCP**, **Obot**, **Traefik Hub**, **AWS Bedrock
AgentCore**. The adjacent AI-SRE market (Hyground, StackGen, NeuBird, Azure SRE Agent, SRE.ai) is
well-funded.

**Why this matters, source-verified:** every one of these gateways provides **auth + policy + audit +
(some) human-approval** — but **none provide dry-run, auto-rollback, or blast-radius**, because a gateway
is **resource-blind**: it can gate or log a tool call, but it can't snapshot a Proxmox VM or compute the
blast radius of an ACL change, because it doesn't understand the resource. **PLAN and UNDO are
domain-specific by necessity** — a generic layer can't do them *for* Proxmox.

**The honest threat (assemble-from-parts):** ContextForge (audit/policy/approval) + RekklesNA (coverage)
= a credible audit + policy + HITL story over Proxmox *today*, with no new code. That combo lacks
PLAN/UNDO/blast-radius — but if a buyer's bar is "audit + approval," it clears now. The defensible ground
is the part that can't be assembled: PLAN (live-state + blast-radius), UNDO (auto-snapshot/revert), and
coverage of the governance plane — not "has an audit log."

---

## Where Proximo honestly stands (no spin, no shrink)

- **Popularity:** zero (just-published — v0.6.3 on PyPI/GitHub/GHCR, zero public stars). MCP leaders
  ~250★; IaC leaders ~2–3k★.
- **"First":** no. **"Most tools":** no (chajus1 ≈115). **"Only one with trust":** no (proxxx: risk-gate +
  keyed audit chain + HITL; RekklesNA: command_policy + approval-token).
- **Genuinely differentiated, execution now confirmed on the key plane:**
  1. **Trust by construction** — every mutation PLAN+UNDO+PROVE *in-band & fail-closed-by-default*, vs
     proxxx's human-gates-each-act and RekklesNA's opt-in/audit-only.
  2. **The dangerous/governance plane on the MCP surface** — firewall/SDN/ACL/roles/realms/PBS exposed *to
     the agent*. RekklesNA doesn't cover it; proxxx keeps it in the TUI. This is the empty intersection.
     The identity/storage/SDN/network/realm surface and offline migration + HA-config have been
     **live-proven to execute** against a real PVE 9.2 API, including a nested 3-node test cluster, with
     PROVE verified throughout. Still unproven: real HA fencing (hardware watchdog), online live-migration
     (shared storage), and production scale.
  3. **Auto-UNDO** — none of the above takes the snapshot for you; proxxx previews a rollback, it doesn't
     perform one.
- **A2A face perimeter-parity closed:** fail-closed public bind, bearer auth on the control endpoint,
  `PROXIMO_A2A_ALLOWED_HOSTS` Host/DNS-rebind allowlist — previously warn-only. Matches the leader's
  perimeter posture.
- **Maturity, stated straight:** v0.6.3, just-published (PyPI/GitHub/GHCR); a significant portion of the broader ~145-tool
  lifecycle surface still runs against mocks; MCP face is local stdio (no network bind); perimeter
  hardening for MCP becomes required the day a remote transport is added. The differentiation above is now
  execution-confirmed on the governance plane; lifecycle breadth and production scale remain to prove.
- **Emerging threat:** field chatter that Proxmox may ship an **official MCP server**. An official basic
  server would commoditize the VM/LXC/snapshot/backup lifecycle layer. Proximo's durable answer is the
  dangerous/governance plane and trust-by-construction — capabilities an official day-one server is
  unlikely to ship. This risk is real; watch the Proxmox project for announcements.

## Sources
GitHub (stars + repo READMEs re-read 2026-06-10: canvrno, RekklesNA v0.5.8, proxxx v0.8.4, chajus1,
gilby125, bshandley/homelab-mcp); PulseMCP / mcpmarket / Glama registries; IBM/mcp-context-forge (3.8k★,
v1.0.2); Integrate.io & TrueFoundry MCP-gateway roundups; agamm/awesome-ai-sre; a2a-protocol.org;
Mindflow; n8n Proxmox-AI template.
