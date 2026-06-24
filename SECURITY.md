# Security Policy

Proximo gives an AI agent a real control plane over Proxmox VE and PBS. Its whole
design premise is that mutations are previewable, reversible, and recorded — so taking
its security seriously is the point, not an afterthought. Reports are genuinely welcome.

## Supported versions

Proximo is pre-1.0; security fixes land on the **latest release only**. There is no
back-port branch.

| Version          | Supported |
| ---------------- | --------- |
| latest `0.7.x`   | ✅        |
| anything older   | ❌ — upgrade |

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
- **The trust boundary is the token you mint.** Proximo cannot exceed the RBAC grants on
  the PVE token it's given, and it defaults to a read-only role. Running it with a
  broadly-scoped or root-equivalent token against that guidance is operator
  misconfiguration, not a Proximo vulnerability — though reports of Proximo *encouraging*
  such a configuration are welcome.
- **UNDO is not universal.** Some planes can't be snapshotted by Proxmox (firewall /
  SDN / ACL / token), so they have no rollback primitive by design. That's documented
  scope, not a missing feature.

## Verifying authenticity

- **Container image (GHCR):** every published image carries a sigstore-signed
  build-provenance attestation and an SPDX SBOM. Verify before trusting a pull:
  `gh attestation verify oci://ghcr.io/john-broadway/proximo:<tag> --owner john-broadway`
- **PyPI (`proximo-proxmox`):** published via GitHub Actions OIDC Trusted Publishing —
  no long-lived API token sits in the release path.

If a downloaded artifact fails verification, treat it as untrusted and report it here.
