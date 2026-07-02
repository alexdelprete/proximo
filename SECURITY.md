# Security Policy

Proximo gives an AI agent a real control plane over Proxmox VE and PBS. Its whole
design premise is that mutations are previewable, reversible, and recorded — so taking
its security seriously is the point, not an afterthought. Reports are genuinely welcome.

## The two-deployment trust model (read this first)

Proximo's protection comes from two layers that do not fail the same way. Don't confuse them.

1. **The hard floor: the Proxmox token you mint.** Proximo cannot exceed the RBAC grants on
   the PVE/PBS/PMG/PDM credential it's given. That's enforced **server-side, by Proxmox
   itself** — not by any line of Proximo's own code — so it survives even a *fully
   compromised* Proximo process: a prompt-injected agent, a poisoned dependency, an attacker
   with a shell in the MCP client. Whatever that credential can't do, nothing running as
   Proximo can do either. Scope the token to read-only, or to exactly the write surface
   you mean to hand over, and this floor holds no matter what happens above it. It's the
   only layer here that assumes Proximo's own process might be hostile.
2. **The in-process gates** — PLAN/PROVE/UNDO/DIAGNOSE plus the opt-in CONSENT/CONTAIN/
   LEASE/SCOPE/ENVELOPE controls (table below). These raise the bar **within** Proximo's
   own trust domain: previews before mutation, a tamper-evident record, rollback where
   Proxmox allows it, and (opt-in) independent authorization, a kill-switch, arm-TTL,
   declared scope, and rate/blast-radius limits. But they're enforced by code running in
   the *same process, same OS user* as the agent they're meant to constrain. If that agent
   (or whatever's hijacked it) can also write to a gate's own state — the CONSENT
   directory, the CONTAIN trip-file path, the SCOPE file, the rate-reservation directory —
   it can potentially clear its own gate. **These become a real boundary, not just a
   speed bump, only when their state directories live outside the agent's write reach** —
   a different OS user, a different filesystem mount, a different host entirely. Point
   every gate's `PROXIMO_*_DIR` / `PROXIMO_*_PATH` somewhere the agent process itself
   cannot write, or treat them as advisory.

Layer 1 is why Proximo is safe to hand to an agent at all. Layer 2 is what makes that
agent *productive* — previews, receipts, budgets — without pretending it's a sandbox.

## Supported versions

Proximo is pre-1.0; security fixes land on the **latest release only**. There is no
back-port branch.

| Version                                       | Supported    |
| ---------------------------------------------- | ------------ |
| latest release (`0.13.0` as of this writing)   | ✅           |
| anything older                                 | ❌ — upgrade |

## Security controls & defaults

Every control below either ships **on** by default or is **fully inert** until its env
var is set — there's no partial-on state. Don't assume a name in this table is protecting
you unless you've configured it.

| Control | Defends against | Default | Turn on with |
|---|---|---|---|
| **PLAN** | A mutation landing with no preview, no blast-radius accounting, no chance to review first | **On**, always | n/a — not optional |
| **PROVE** | An edited, reordered, or silently truncated mutation history | **On** (keyed HMAC-SHA256 ledger) | `PROXIMO_AUDIT_KEYED` (default `true`; `off` downgrades to unkeyed — not recommended). Catching *tail truncation / full wipe* needs an off-box head anchor — that's opt-in: `PROXIMO_AUDIT_EXPECTED_HEAD` / `PROXIMO_AUDIT_ANCHOR_*`. |
| **UNDO** | An unrecoverable mistake on a plane Proxmox can snapshot | **On** for the planes it covers (fail-closed) | n/a — always applied where a rollback primitive exists (guest config, `ct_exec`/`ct_psql`, guest snapshot/rollback). No env var; firewall/SDN/ACL/token have no Proxmox rollback primitive by design, not by configuration. |
| **DIAGNOSE** | Acting on a guest/node with no read-only evidence gathered first | **On**, always | n/a — read-only, always available |
| **CONSENT** | An agent — compromised, confused, or persuaded by injected instructions — confirming its own mutation with no independent, out-of-band grant | **Off** | `PROXIMO_CONSENT_DIR` (+ `PROXIMO_CONSENT_TTL_SECONDS` for grant expiry) |
| **CONTAIN** (kill-switch) | Needing to halt *every* mutation immediately, mid-incident, without a redeploy or restart | **Off** | `PROXIMO_CONTAIN_TRIP_PATH` |
| **LEASE** (arm-TTL) | A write-armed token staying armed indefinitely after the operator meant to hand it back to read-only | **Off** | `PROXIMO_ARM_TTL` (also requires `PROXIMO_TOKEN_PATH` — an unresolvable path fails closed, never "assume fresh") |
| **SCOPE / provenance** | An agent mutating a target outside the box(es) the operator authorized at arm-time | **Off** | `PROXIMO_SCOPE_PATH` |
| **ENVELOPE** (FORBID + RATE) | Blast radius under hijack — unlimited-speed mutation, or an explicitly forbidden action, from an agent that's been compromised or gone off-script | **Off** | `PROXIMO_FORBID` (global floor, always checked once set) + `PROXIMO_RATE_MAX` / `PROXIMO_RATE_WINDOW` (per-box budget) |
| **TAINT** (untrusted-read coupling) | Prompt injection riding in on adversarial read output (guest logs, quarantine mail, free-text config) then steering a mutation the agent confirms for itself | **Off** | `PROXIMO_TAINT_TRACK` (mark + record a sticky taint on an adversarial read) then, once tainted, `PROXIMO_TAINT_FORBID` (actions refused outright — the primary, no consent escape) and/or `PROXIMO_TAINT_REQUIRE_CONSENT` (any mutation now needs an out-of-band grant). `PROXIMO_TAINT_FENCE` adds an advisory content-fence. |

Two more flags widen what Proximo can **do**, rather than protect what it's already
doing — don't confuse them with the gates above: `PROXIMO_ENABLE_EXEC` (near-root
`ssh → pct exec`) and `PROXIMO_ENABLE_AGENT` (qemu-guest-agent in-guest ops). Both are
off by default and, once on, are each bounded by their own fail-closed CTID/VMID
allowlist.

*Status note: CONSENT/CONTAIN/LEASE/SCOPE/ENVELOPE are present in this repository's
current source. Check `CHANGELOG.md` against the version you actually installed — a
published package can lag the tree you're reading; these gates land in a release only
when their changelog entry says so.*

## Prompt injection / untrusted tool output

Several of Proximo's read tools pull text off the Proxmox stack straight into an
agent's context — and some of that text is written by whoever controls the guest, the
mail traffic, or the log line, not by the operator. That's a prompt-injection channel:
**no exploit needed, just a persuasive string placed somewhere Proximo will read it
back to the agent.**

Tools worth attention because they can carry attacker- or guest-controlled text:

- **Node/CT syslog and journal** — `pve_node_syslog`, `pve_node_journal`,
  `pmg_node_syslog`: anything that can write to the journal (a process inside a guest, a
  crafted service/unit name) can place text here.
- **`ct_logs`** — tails a systemd unit's log inside a container; the container's own
  workload controls that content.
- **Task logs** — `pve_task_log`: mostly Proxmox's own output, but can echo
  user-supplied strings from the operation that produced it.
- **Guest names, notes, and descriptions** — `pve_list_guests`, `pve_guest_config_get`,
  `pve_cluster_resources`, and free-text `description=` fields on mappings/objects:
  anyone with guest create/edit rights can set these.
- **The PMG quarantine tools, especially** — `pmg_quarantine_spam`,
  `pmg_quarantine_virus`, `pmg_quarantine_attachment`, `pmg_tracker_list` /
  `pmg_tracker_detail`: these exist specifically to surface **attacker-authored
  spam/phishing content** — subject lines, sender strings, message bodies written by
  whoever sent the mail. Handing that straight to an agent's context is, by design,
  handing it adversarial input.

**This is a real frontier — not solved, but no longer unmitigated.** An opt-in **TAINT**
control (`taint.py`, off by default) turns "an untrusted read happened" into something the
server can act on by construction:

- **Classification by channel.** Every tool whose return carries guest- or externally-authored
  bytes is classified adversarial — the logs and quarantine tools above, *and* the exec-output
  tools (`ct_exec`, `ct_psql`, `pve_agent_exec`) and in-guest `pve_agent_file_read`, even though
  those mutate. A completeness test fails CI if a new tool ships unclassified, so the set can't
  silently fall behind the surface.
- **Track (by construction).** With `PROXIMO_TAINT_TRACK` (or either coupling below) set, reading
  adversarial content writes a **sticky** taint marker beside the ledger and stamps `untrusted:true`
  on the ledger entry — so DIAGNOSE/audit can see a mutation that *followed* adversarial input. The
  marker clears **only out-of-band** (no tool clears it; a consumed CONSENT grant does **not** clear
  it — otherwise a hijacked agent could get a sacrificial benign action approved to launder the
  taint). It survives a process restart.
- **Forbid (the primary enforcement).** Once tainted, `PROXIMO_TAINT_FORBID` actions are refused
  outright (`blocked:taint_forbidden`) — **no consent escape**, a hard wall before consent at every
  seam. Point it at the cross-domain infra actions (firewall/network/access/token/exec/guest-power):
  "a session that has read quarantine mail cannot then reconfigure the firewall" is enforced by the
  envelope the operator declared once, not by a human approving each call.
- **Consent (the in-domain residue).** `PROXIMO_TAINT_REQUIRE_CONSENT` makes CONSENT mandatory for
  any tainted mutation the forbid set doesn't cover — the case where the legitimate workflow and the
  attack are the *same* call (read quarantine → act on quarantine). Fail-closed if the consent dir
  isn't configured.
- **Fence (advisory).** `PROXIMO_TAINT_FENCE` wraps adversarial output in a labeled envelope. It
  helps a cooperating agent and the human reading the transcript; a hijacked agent can ignore it.
  **Advisory only — never a guarantee.**

**Honest limits (do not over-read this):** TAINT's forbid/consent walls are a real boundary only
when the marker dir and consent dir sit **outside the agent's own write reach** — the same
two-deployment condition every gate here carries. Co-located (agent shares the filesystem), a
compromised agent can `rm` the marker; then it is a speed-bump plus an observability signal, and
CONTAIN's out-of-band kill is the real backstop. Classification is a curated set — a channel that's
mis-classified as trusted is a residual gap the module can't self-detect (bias: classify adversarial
when unsure). And TAINT only guards mutations *after* the untrusted read — which is the whole
injection vector, but state it plainly.

**The strongest control is deployment shape, not a runtime gate.** Split the work across **two
agent contexts**: a read-only "inbox/log reader" (a read-only Proxmox token, mutation tools not on
its surface) and a mutator (the untrusted-read tools not on its surface). The injection channel and
the mutation capability never meet in one context, and this survives even a fully compromised Proximo
process (the Layer-1 token floor). Its load-bearing half — that the two surfaces reach *different*
agent contexts — is the deployer's to arrange; Proximo can't enforce it server-side. Prefer this for
any PMG-facing workflow; use the TAINT gate to protect the deployments that won't split. A
plan-pinning form (only mutations planned *before* the taint event may run) is a stronger future
direction, not yet built.

## Reporting a vulnerability

**Please do not open a public issue for a security report.**

Use GitHub's private vulnerability reporting:

1. Go to the repository's **Security** tab → **Report a vulnerability**.
2. Describe the issue, the affected version/commit, and a reproduction if you have one.

That opens a private advisory thread visible only to you and the maintainer.

This is a small, independently-maintained project — expect a best-effort response, not
a contractual SLA. Reports are acknowledged as quickly as is practical, and disclosure
is coordinated with you: a fix and an advisory go out together, with credit unless you
ask otherwise.

## What's most worth your attention

The highest-value areas to probe, because they're where the trust model lives or where
access is broadest:

- **Trust-spine bypass.** Any path that mutates state *without* a PLAN, that escapes a
  fail-closed UNDO where one is expected, or that writes the PROVE ledger without
  extending the hash chain. The ledger's strong guarantee is the off-box `head()`
  anchor (head-pinning via `audit_verify(expected_head=…)`); a way to advance the head
  undetected, or to forge a verifying chain, is in scope.
- **Independent-gate bypass.** A way for a mutation to proceed while a configured
  CONSENT/CONTAIN/LEASE/SCOPE/ENVELOPE gate would have blocked it — especially by
  writing to the gate's own state (its trip file, scope file, consent grant, or rate
  reservation) from within the agent's own reach — is in scope, and is exactly the
  Layer-2 failure mode described above.
- **The in-container exec edge.** `PROXIMO_ENABLE_EXEC=1` enables `ssh → pct exec`,
  which is near-root on the host. It's opt-in and fail-closed behind a CTID allowlist —
  any allowlist bypass, or a way to reach exec without the flag, is high severity.
- **The A2A network face.** The optional A2A server (`proximo-a2a`) must refuse
  non-localhost binds without a bearer token and enforce the `PROXIMO_A2A_ALLOWED_HOSTS`
  Host/DNS-rebind allowlist. Auth bypass, header smuggling, or rebind escape are in scope.
- **Secret handling.** Proximo takes its PVE token by path/env, never as a literal in a
  shell line. A path where a token, key, or other secret is logged, echoed into the
  audit ledger, or otherwise persisted in cleartext is in scope.

## Honest scope notes

- **Risk ratings are an advisory heuristic, not a sandbox.** A tool rated `LOW` means
  "no state change," **not** "safe." Proximo previews, undoes, and proves — it does not
  sandbox the Proxmox API. A report that boils down to "a HIGH-risk op did the dangerous
  thing it said it would do, with a plan and an audit record" is working as designed.
- **The token you mint is the hard floor** — see "The two-deployment trust model" above.
  Running Proximo with a broadly-scoped or root-equivalent token against that guidance is
  operator misconfiguration, not a Proximo vulnerability — though reports of Proximo
  *encouraging* such a configuration are welcome.
- **UNDO is not universal.** Some planes can't be snapshotted by Proxmox (firewall /
  SDN / ACL / token), so they have no rollback primitive by design. That's documented
  scope, not a missing feature.
- **The opt-in gates (CONSENT/CONTAIN/LEASE/SCOPE/ENVELOPE) are inert until configured**
  — see "Security controls & defaults" above. A report that one of them "didn't stop"
  an action when its env var was never set is expected behavior, not a finding.

## Verifying authenticity

- **Container image (GHCR):** every published image carries a sigstore-signed
  build-provenance attestation and an SPDX SBOM. Verify before trusting a pull:
  `gh attestation verify oci://ghcr.io/john-broadway/proximo:<tag> --owner john-broadway`
- **PyPI (`proximo-proxmox`):** published via GitHub Actions OIDC Trusted Publishing —
  no long-lived API token sits in the release path.

If a downloaded artifact fails verification, treat it as untrusted and report it here.
