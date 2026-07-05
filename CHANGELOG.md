# Changelog

All notable changes to Proximo. Format loosely follows Keep a Changelog; versions are SemVer.

## [Unreleased]

## [0.16.0] - 2026-07-05

**The last two "unproven by design" claims are now live-proven** — online (zero-downtime) QEMU
migration over shared storage, and HA fencing with the softdog watchdog — on a real 3-node PVE 9.2
cluster with NFS-backed shared storage. Plus the storage bug the proof surfaced, fixed.

- proof(cluster): **ONLINE live-migration live-proven end-to-end through the full stack**
  (`scripts/live-smoke/migrate-online-smoke.py`): a running QEMU guest with its disk on shared
  NFS storage migrated node→node in ~9s and **never stopped** (post-state asserted: guest on the
  target node AND still `running`; an online migration that can't stay live fails — it does not
  silently fall back to offline). The PLAN preview is asserted to disclose source→target and the
  online mode before anything moves; PROVE ledger verified after. Closes the roadmap gap that had
  been "unproven by design until shared storage exists" since 2026-06-10.
- proof(ha): **HA fencing live-proven with the softdog watchdog** on a real quorate 3-node
  cluster: an HA-managed guest's node had corosync cut; its LRM stopped petting the watchdog,
  softdog reset the node ~85s later (boot-time change + the kernel's
  `watchdog: watchdog0: watchdog did not stop!` signature in the prior boot's journal — no reboot
  was ever issued), and the CRM recovered the guest `started` on a survivor node. Fault-to-recovery
  2m36s, every phase observed through Proximo's own read tools. Honest residual: softdog (PVE's
  default watchdog) is proven; a *hardware* watchdog (iTCO/IPMI) still needs real hardware.
- fix(storage): **`pve_storage_create` no longer sends `shared` for network-backed storage types**
  (nfs/cifs/pbs/cephfs/rbd/iscsi). PVE fixes `shared=1` in the plugin for those types and its API
  *rejects* the explicit property (`500 unexpected property 'shared'` — live-found on PVE 9.2 by the
  migration proof, mid-smoke). `shared=True` intent is already satisfied for them, so it is omitted;
  `dir`-style types still send it. `storage_update` can't see the storage's type, so its docstring
  now carries the sharp edge (pass `shared=None` for intrinsically-shared types). The unit test that
  asserted the old behavior encoded the wrong assumption — flipped to the live-proven truth.
- feat(prompts): **five safe-runbook MCP prompts** (`src/proximo/prompts.py`) — user-invoked front
  doors that encode the guarded path for common operations: `safe_migration`, `provision_container`,
  and `safe_backup` (each plan-first → verify-after), `diagnose_cluster` (read-only DIAGNOSE sweep),
  and `review_receipts` (verify the PROVE ledger's integrity — entries are read off-box). Prompts are
  templates, not tool-callers — they add no new authority; they lower the "where do I start" barrier
  and point at the sequence the trust spine already enforces. Registered on the shared FastMCP
  instance, surfaced over `prompts/list`/`prompts/get`, and declared in the LobeHub manifest by the
  extended `scripts/gen_lobehub_manifest.py`. Pinned by `tests/test_prompts.py`.

## [0.15.0] - 2026-07-04

**Cert-fingerprint pinning across all four Proxmox surfaces, and a distributable Debian package.**
Pin any Proxmox backend Proximo talks to — PVE · PBS · PMG · PDM — by its exact certificate,
the self-signed operator's answer to shipping a cluster CA. Every pin is wire-enforced and
live-proven against real hardware. Plus the first packaged `.deb`. New capabilities, no breaking
changes; suite 5,193 green, ruff + pyright clean.

- feat(pmg,pdm): **cert-fingerprint pinning now covers all four surfaces.** `PROXIMO_PMG_FINGERPRINT`
  and `PROXIMO_PDM_FINGERPRINT` complete what PBS and PVE started — every Proxmox backend Proximo
  talks to (PVE · PBS · PMG · PDM) can now be verified by an exact-cert SHA-256 pin instead of a
  shipped CA. Same guarantee across the board: the pin replaces CA/hostname validation, a mismatch
  closes the socket before any credential or token is sent, a pin alone suffices, a garbled pin
  refuses loudly at startup. Available via env or the target registry (`fingerprint` field).
  **Live-proven against the real self-signed lab PMG 9.1 and PDM.**
- feat(pve): **`PROXIMO_FINGERPRINT` — wire-enforced cert pinning for the PVE backend.**
  Extends the PBS pin to Proxmox VE: a stock PVE node serves a cert signed by the per-cluster
  "PVE Cluster Manager CA" that no public root trusts, so an operator can now pin the node
  cert's SHA-256 instead of shipping the cluster CA. Same guarantee as PBS — exact-cert match
  checked on the handshake, socket closed on mismatch before the `PVEAPIToken` header is sent;
  a pin alone is sufficient verification; a garbled pin refuses loudly at startup. Available
  via `PROXIMO_FINGERPRINT` (env) or `fingerprint` (target registry). **Live-proven against a
  real self-signed PVE 9.2 node** (matching pin connects, wrong pin refuses), in addition to
  the synthetic-TLS unit tests.
- feat(pbs): **`PROXIMO_PBS_FINGERPRINT` is now wire-enforced.** When set, the PBS server
  certificate's SHA-256 must match the pin exactly — checked on the TLS handshake itself,
  and a mismatch closes the socket before the token header is ever sent. The pin replaces
  CA/hostname validation (the `proxmox-backup-client --fingerprint` idiom), so a pin alone
  is now sufficient verification for a self-signed PBS box, while a garbled fingerprint
  refuses loudly at startup. Accepts the colon-separated form the PBS GUI displays.
  Proven in tests against a real TLS handshake (self-signed cert + live socket), not mocks —
  and **live-proven against a real self-signed PBS 4.2 datastore** (matching pin reads, wrong
  pin refuses). Closes the long-standing "stored; not yet wire-enforced" honesty note.
- packaging(debian): **a buildable, tested `.deb`** — dh-virtualenv, self-contained venv under
  `/opt/venvs/proximo`, `/usr/bin/proximo` entry point, a hand-written `man proximo`, and a
  passing autopkgtest smoke check. `lintian` clean (three unfixable pre-stripped-wheel tags on
  the debug package aside). Built with `dpkg-buildpackage`, verified end-user (install →
  `proximo doctor` → clean purge, zero files left). Not distributed anywhere yet — build your
  own from `debian/`; remaining rough edges are listed honestly in `debian/README.Debian`.

## [0.14.1] - 2026-07-04

**The trim + harden patch: PLAN previews and the PROVE ledger now tell the whole truth — and
keep secrets out of both.** Plus the doctor's spine report, and a leaner tree with ~35
duplication sites collapsed. No new tools, no new env vars, no breaking changes.

**Trim + harden campaign (2026-07-04).** A 10-cluster agent-team sweep over the whole tree —
57 verified findings applied (every one re-verified against the code before touching it), +74
new pinning tests. Suite 5,153 green (3 by-design skips), ruff + pyright clean.

Hardened — PLAN/PROVE tell the whole truth, secrets stay out of both:
- **Secret redaction in PLAN previews:** guest-config plans (`pve_guest_config_set`/`revert`)
  now mask cloud-init secrets (e.g. `cipassword`) before they reach the plan response or the
  ledger; ACME DNS-plugin update/delete plans no longer capture the provider's credential
  `data` field; notification-endpoint create/update plans disclose/redact the fields actually
  applied instead of embedding raw payloads.
- **`pve_tfa_delete` password-leak seam closed:** the acting user's password no longer rides
  the URL query string, where a guaranteed PVE error echo (httpx's URL-bearing exception text)
  could leak it into error messages and the ledger.
- **PLAN disclosure gaps closed across four planes:** all 12 PMG RuleDB `*_update` tools (who/
  what/when groups + objects, action bcc/field/notification/disclaimer/removeattachments, rule
  update) now render the actual field values being changed into the dry-run preview AND the
  executed-mutation ledger detail — an operator approving a plan (or auditing afterward) can
  now see e.g. a BCC target being redirected, not just an object id. Same class of fix for
  `pve_network_iface_create` (staged interface fields), SDN zone/vnet/subnet create/update
  (actual option key=values), storage-backend create (per-backend params) and delete (plans now
  say plainly when `cleanup=True` will wipe the underlying disks), and
  `pve_replication_create` (schedule/rate/comment params previously silently dropped).
- **PROVE ledger symlink guard now re-checks on every append/read** (record/head/verify), not
  just at construction — a mid-session directory swap under the long-lived ledger instance is
  refused, mirroring the envelope reservation-dir guard.
- **Startup warning when `PROXIMO_LEDGER_REDACT` is off** (the default records full exec
  argv/SQL into the ledger, which can carry secrets) — parity with every other
  permissive-by-default warning.
- **Envelope RATE cap now ranks candidates by effective sustained rate** (count/window), so a
  short-window sanity ceiling can no longer outrank a stricter long-window budget for the same
  box; envelope-resolution failures are now recorded to the ledger and refuse fail-closed
  instead of raising unaudited.
- **Fail-closed shape checks:** PBS `remotes_list` refuses non-list responses and non-dict
  entries rather than returning anything unverified password-free; PBS
  `traffic_control_upsert` aborts on an unexpected existence-check error instead of silently
  assuming create; backup storage names reject `.`/`..` (path-traversal guard parity with the
  storage plane); `role_create`/`role_update` (privs), `realm_*`/`group_*` (comment) reject
  control characters, matching the existing user-plane guard; blast disk-move dependents now
  read guest configs through the validated accessor instead of a raw API path.
- **A2A/PDM boundary:** a non-string `skill` in an inbound A2A call is a clean audited
  rejection (was an uncaught TypeError bypassing the ledger); PDM secret-key redaction widened
  to compound names (`client_secret`, `api_key`, `auth_token`, `private_key`, …).

Trimmed — ~35 verified-identical duplication sites collapsed into shared helpers (PMG epoch
params ×11, who/what-object body builders, blast severity ladder + sentinels, firewall rule
lookup/digest re-reads, backends node-check ×26, qemu-agent gate ×6, PDM config/url
normalization, envelope candidate parsing, and dead code removed: `_check_ha_sid`,
`_is_root_or_broad`). Zero behavior change; every trim pinned by the existing suite.

- feat(doctor): the **spine report** — `proximo doctor` now shows the trust spine: the four
  structural pillars (PLAN·PROVE·UNDO·DIAGNOSE, standing in every configuration) and the two
  sockets only the operator can fill (CONSENT · CONTAIN), each with the exact out-of-band
  recipe to erect it. Configured state is reported yes/no only — the doctor never echoes the
  configured paths (a hijacked session must not learn where the operator placed the consent
  drop or the kill-switch). Doctrine stated in SECURITY.md: four ship standing, two are yours
  to erect — a pillar Proximo raised for you would be a pillar the agent could lower for itself.

## [0.14.0] - 2026-07-03

**Scoped registration (`PROXIMO_SURFACES`) + the demo-led README.** Load only the planes you
use: `PROXIMO_SURFACES=pve,exec` registers just those surfaces' tools (that pair = 194 of 352;
`pbs,exec` = 38) — unpicked planes are pruned from the MCP registry before serving, so they
never reach the client's context window. Structural gate, not a runtime refusal; applied after
the env file loads (the CONSENT-footgun lesson); `audit_verify` is never scopeable away; an
unknown surface name refuses startup loudly instead of silently serving the wrong set. Unset =
all 352, zero behavior change — the house opt-in contract. A completeness test fails CI if a
future tool falls outside every surface. Default tool count unchanged (352). Full suite
**5,079 green** (3 by-design skips), ruff + pyright clean.

- feat(surfaces): `PROXIMO_SURFACES` registration scoping — `pve` / `pbs` / `pmg` / `pdm` /
  `exec`, comma-separated, case-insensitive; live-verified end-user (scoped registry + typo
  refusal, exit 1). Documented in README ("Big surface, scoped context") and SECURITY.md
  (explicitly framed as context hygiene / surface reduction, **not** an authorization control —
  the token's ACL remains the real boundary).
- docs(readme): restructure for the arriving reader — live demo recording up top
  (`docs/demo/demo.svg`, recorded against a real PVE 9.2 host with a read-only token via
  `scripts/demo/demo.py`, reproducible), "What it does" + a Quickstart (MCP client config +
  `doctor`) above the fold; the lanista naming note moved to Credits. No claims changed.
- test(doctor): pin the no-secret-material invariant on the `proximo doctor` report — sentinel
  secrets planted on every secret-bearing seam must never appear in the printed report (regression
  guard for CodeQL alert #75, assessed a false positive: object-level taint from the backend that
  read the token; the report itself carries only booleans, paths, and privilege names).
- deps: raise floors to the versions the suite actually tests against — `starlette>=1.3.1`,
  `cryptography>=49.0.0` (a2a + dev extras), `pytest-asyncio>=1.4.0` (dev); bump
  `actions/attest-build-provenance` pin to v4.1.1 (dependabot #17, #15, #13, #12).

## [0.13.0] - 2026-07-02

**Zero-trust arc — a CONTAIN kill-switch and its siblings, a prompt-injection TAINT control, plus an
automated PROVE anchor.** Six new opt-in, out-of-band controls (a **CONTAIN** kill-switch, independent
**CONSENT**, an arm-time **SCOPE** gate, an arm-**LEASE** TTL, a two-commit per-surface **ENVELOPE**,
and a content-trust **TAINT** control), each wired at the 5 mutation seams with the same fail-closed,
out-of-band discipline. Also automates the off-box PROVE head-pin, closes a config-loading footgun
that could leave CONSENT silently inert, adds one enforcement tool, and (review follow-ups) hardens
the PROVE ledger against symlink redirection, reorders the rate wall after consent, and truth-sizes
the security docs. **+1 tool (351 → 352).** Full suite 5068 green (3 skipped),
ruff + pyright clean. Every new gate is **opt-in and inert until its env var is set** — these are
independent controls, not a bundled "pillar" system; see `SECURITY.md` "The two-deployment trust
model" and its controls-and-defaults table for what each one honestly holds.

### Added
- **TAINT control — prompt-injection mitigation** (`taint.py`; `PROXIMO_TAINT_TRACK` /
  `PROXIMO_TAINT_FORBID` / `PROXIMO_TAINT_REQUIRE_CONSENT` / `PROXIMO_TAINT_FENCE`) — opt-in, off by
  default, a **minor** capability when released. Classifies every tool whose return carries
  guest/external-authored bytes (`ADVERSARIAL_TOOLS` — logs, quarantine/tracker, config free-text, and
  the exec-output tools `ct_exec`/`ct_psql`/`pve_agent_exec` + in-guest `pve_agent_file_read`), pinned
  by a completeness test that fails CI on an unclassified new tool. Reading adversarial content sets a
  **sticky, file-backed** taint marker beside the ledger (fail-closed, fresh-stat, out-of-band clear
  only; survives restart; a consumed CONSENT grant never clears it) and stamps `untrusted:true` on the
  ledger entry. Once tainted, `PROXIMO_TAINT_FORBID` refuses a pre-declared action set outright
  (`blocked:taint_forbidden`, the primary — no consent escape, before consent at every seam) and
  `PROXIMO_TAINT_REQUIRE_CONSENT` makes CONSENT mandatory for the in-domain residue (fail-closed as
  `blocked:taint_consent_unconfigured` if the consent dir is unset). A marker-write failure fails
  closed (`blocked:taint_mark_failed`) rather than serving untracked output. `PROXIMO_TAINT_FENCE` adds
  an advisory content-fence (result-field only; never a guarantee). Inert until an env var is set —
  zero behavior change by default. `SECURITY.md` "Prompt injection" rewritten with the tiered mitigation
  + the two-instance-split headline recommendation + honest limits; 3-lens redteam (self + correctness
  + injection), all findings closed. No tool-count change (352). ~180 tests.
- **CONTAIN kill-switch** (`contain.py`; `PROXIMO_CONTAIN_TRIP_PATH`) — the out-of-band emergency stop
  the rest of the arc is built around: while the trip file exists, every mutation is refused before the
  backend call and audited (outcome `contained`), checked FIRST at all 5 mutation seams so it overrides
  every other gate. The trip is read FRESH each call; fail-closed on a perm/garbled trip path (an
  unreadable trip denies rather than assuming clear); reads and dry-run PLAN stay ungated so DIAGNOSE
  still works while contained. The operator's real velocity backstop against a hijacked agent — the
  lever that still holds even though the rate wall is not tamper-evident. Opt-in, inert when unset. 10 tests.
- **Off-box PROVE anchor** (`audit_anchor.py`) — automates the "pin the ledger head off-box" strong
  guarantee: a `FileSink` pins `head()` to a file (an NFS/object-store path the box can write but not
  rewrite), auto-pinned at startup and exportable on-demand from `audit_verify`. Anti-poisoning
  invariant: the on-demand export advances the pin only on first run or an unchanged head — it never
  re-pins to a moved head, so a verify run that *detects* a truncation can't overwrite the good pin
  with the tampered one; a moved head instead surfaces as a directional `anchor_hint`. Fail-closed: an
  unreachable/corrupt sink refuses the call rather than pass a stale pin off as clean. 25 tests
  including the RED-proven invariant "never re-pins to a head other than the previously-pinned one."
- **Independent CONSENT** (`consent.py`; `PROXIMO_CONSENT_DIR` / `PROXIMO_CONSENT_TTL_SECONDS`) —
  closes two trust holes: self-asserted authorization (`confirm=` is only the agent's own bool) and
  session-not-per-request trust (an armed session otherwise opens an unlimited mutation window). A
  mutation now proceeds only if an unexpired grant file for *this exact plan* exists in the consent
  dir, placed by a human out-of-band — never an MCP tool — and consuming it is single-use
  (`consent_id` hashes the plan's stable decision-relevant fields, not volatile telemetry). Wired
  beside CONTAIN at all 5 mutation seams; opt-in, inert when unset. **Known limit**
  (`docs/known-issues.md`): this only closes the gap if the agent's own shell cannot write the grant
  dir. 19 tests, including 4 exec-family bypass proofs and interleaved-context isolation.
- **`pve_acl_prune`** (gap #6) — the enforcement counterpart to `pve_overbroad_grants`, which detected
  accreting Administrator/root grants but never removed them. Revokes a flagged over-broad grant and
  optionally re-grants a narrower one, routed through the full spine: dual blast-radius (revoke leg +
  re-grant leg, merged, risk never lowered), PROVE, confirm-gated, per-grant — no bulk-prune.
  `pve_acl_modify` / `plan_acl_modify` gain `kind="group"` support. **Tool count 351 → 352.** 30 tests
  + a 3-lens adversarial redteam (gating / disclosure-merge / secret-validation) that caught and fixed
  one HIGH: the re-grant leg used a stale revoke-path shadow context, under-reporting risk for
  `privsep=0` tokens.
- **Arm-time target-scope gate** (`provenance.py`; `PROXIMO_SCOPE_PATH`) — an out-of-band JSON scope
  file (`{"targets": [...]}`) declares which guests/targets an armed session may mutate; an
  instruction targeting a guest outside the declared scope is refused before the backend call and
  audited (`blocked:out_of_scope`), and a garbled/unreadable/empty scope file refuses all mutations
  (`blocked:scope_unreadable`). Guest-identity targets normalize (`lxc/N:action` → `lxc/N`) but never
  cross kind or plane; the gate takes no caller-supplied parameter — scope is file-only, closing the
  self-authorization path. **Honest ceiling:** an in-scope action is still unauthenticated as-to-intent
  (max-risk ceiling, scope expiry, and a signed task-token are deferred fast-follows). 46 tests + a
  3-lens redteam (coverage / matching-rule / fail-closed) that caught one Med-High (a snapshot-plan
  false-authorize).
- **Auto-expiring arm TTL** (`lease.py`; `PROXIMO_ARM_TTL` + `PROXIMO_TOKEN_PATH`) — closes
  fail-open-over-time: armed write-authority previously survived session-end/crash/reboot indefinitely,
  reverting only on a manual `disarm`. Authority now auto-expires N seconds after the arm token's
  mtime (the arm step stamps it via `install -m 600`). Fail-closed on a garbled/non-positive TTL, an
  unset/missing token path, a non-regular-file path, or a future mtime (clock skew — never "assume
  fresh"). Reads and dry-run PLAN stay ungated, so an expired lease auto-downgrades arm to read-only.
  16 tests, including 2 redteam regressions (future-mtime and directory-token-path fail-opens).
- **Per-surface autonomy envelope — FORBID + RATE/BUDGET walls** (`envelope.py`; `PROXIMO_FORBID` /
  `PROXIMO_RATE_MAX` / `PROXIMO_RATE_WINDOW`, shipped as two commits). The operator declares limits
  once per surface; the agent runs autonomously inside them; the system enforces by construction; the
  human is on-exception — not a per-action human-in-the-loop lever.
  - **FORBID** (commit 1/2) — a deterministic per-target/per-action denylist, resolved
    kind-agnostically so it gates every plane uniformly. Composite matching (action + target +
    `detail["action"]`, not tool name) closes sub-action holes in `pve_guest_power`,
    `node_service_control`, and `pmg_quarantine_action`; a global floor (`PROXIMO_FORBID`) applies to
    every mutation regardless of target and cannot be escaped; an unregistered active target fails
    closed rather than going silently inert. 18 tests.
  - **RATE/BUDGET** (commit 2/2) — a per-box, `flock`-guarded, sliding-window mutation-rate limiter,
    the answer to velocity-under-hijack: an atomic reservation file (temp + `os.replace`, crash-safe)
    keyed by `base_url` (physical box identity), capped at the *tightest* limit across every
    name/env config for that box so a caller can't dodge it by omitting or swapping
    `proximo_target`. Per-operation de-dup so a multi-seam mutation reserves exactly one slot.
    Replaces a naive whole-ledger-count design from the WIP, refuted by a 3-lens redteam for
    concurrency races and per-instance undercounting. That same redteam found and fixed 7 further
    hardening gaps: `rate_window<=0` fail-open, NaN/±inf slot values slipping the fail-closed branch,
    an unaudited reservation-read crash, a followable lock-sidecar symlink, a window-blind tie-break,
    and unbounded reservation-file growth. **Honest limit** (stated in the module docstring): the
    reservation file is **not tamper-evident** — a co-located agent with write access to the
    reservation dir can reset its own budget; CONTAIN's out-of-band kill is the real velocity
    backstop. 18 more tests (39 total in `test_envelope.py`); a 20-thread concurrency barrier
    confirmed exactly-k (3) reservations and per-box isolation.

### Security
- **`proximo.env` now actually loads at startup**, closing a footgun that left the new gates above
  silently inert. Under stdio the server previously saw only the MCP client's inline env block, so a
  `PROXIMO_*` var set in the documented `~/.config/proximo/proximo.env` was ignored without warning —
  **fail-dangerous for CONSENT**: `PROXIMO_CONSENT_DIR` set there left the gate silently off while the
  operator believed every mutation needed sign-off. `load_env_file()` now sources the file first thing
  in `server.main()` / `proximo-a2a`, filling only unset `PROXIMO_*` keys (real/inline env always
  wins), touching only that namespace (no `PATH`/`LD_*` injection); a missing file is a no-op, and a
  loaded file announces itself on stderr. Also fixes the identical pre-existing gap for
  `PROXIMO_ENABLE_EXEC` and its siblings. 8 tests, including namespace isolation and an
  env-wins-over-file precedence check.
- **PROVE ledger hardened against symlink redirection** — the audit append and both rotation
  sidecar-lock opens now use `O_NOFOLLOW`, and the ledger/key **directories** refuse a symlinked path
  (`islink` guard) before `makedirs`. Closes a co-located-writer escape on the flagship pillar: a
  planted symlink at the ledger path — or its parent dir — could previously redirect tamper-evident
  appends onto an arbitrary target the service can write. Brings PROVE to parity with the ENVELOPE
  rate-lock's existing guard. 7 symlink/concurrency tests, including real-`flock` barrier proofs the
  ledger had lacked.
- **Rate wall now evaluated AFTER consent** — the per-surface RATE reservation was split out of the
  envelope check and moved below `enforce_consent` at all 5 seams, so a consent-refused mutation no
  longer spends a slot from the box's budget. Closes an operator-DoS lever: a looping/hijacked agent
  could otherwise burn the whole window's budget on attempts consent would refuse, denying the human's
  own approved mutations. FORBID stays an early hard wall (spends nothing); fail-closed semantics and
  the one-slot-per-operation de-dup are unchanged.

### Changed
- **Docs truth-sized to shipped defaults.** `SECURITY.md` gains a "two-deployment trust model" (the
  Proxmox token is the hard floor, enforced by server-side RBAC; the in-process gates are a boundary
  only when their state paths sit outside the agent's reach), a controls-and-defaults table (which
  gates are on-by-default vs opt-in, with their env vars), and a prompt-injection / untrusted-tool-
  output section. `README.md` and the dev docs reframed off "four pillars" → "four on by default +
  opt-in controls" (explicitly not marketed as a bundled "pillar" system).
- **Release / CI hygiene.** `server.json`'s version fields are now covered by the version-consistency
  gate (`scripts/version_tools.py` check/set/release); the Trivy image scan and the internal-mirror
  CI's `pip-audit` are now blocking (both verified clean first). PMG who/what/when group CRUD collapsed to shared generics
  (public API unchanged); `blast.py`'s two largest functions decomposed and an mccabe complexity gate
  added; a CONTAIN/envelope live-smoke script added (FORBID + concurrent RATE barrier vs a real host).

### Fixed
- **`pve_acme_plugin_create` / `pve_acme_plugin_update` crashed whenever `dns_api` was set.** The
  wrappers map `dns_api` onto PVE's `api` body field via `kw["api"]`, but the acme_certs.py helpers'
  own first positional parameter (the backend) was also named `api`, so `**kw` collided
  (`TypeError: got multiple values for argument 'api'`). Because `dns_api` (the DNS provider) is the
  primary real use of these tools, both were unusable — update crashed on dry-run *and* execute,
  create on execute. Renamed the backend param to `backend`. Surfaced by the new per-wrapper
  request-shape sweep; regression-tested on the confirm=True executor path the sweep can't reach.

## [0.12.0] — 2026-06-30

**The `doctor` preflight goes multi-target-aware, plus a PMG login-concurrency fix. No new tools
(still 351 across PVE/PBS/PMG/PDM); no behavior change at the default.** A small, deliberate minor:
0.11.0 made the MCP tools target-aware but left the `doctor` *CLI* pinned to the env-configured box;
this closes that gap. Drop-in over 0.11.0 — nothing to read before upgrading.

### Added
- **`proximo doctor --target <name>`** — the `doctor` CLI preflight can now target a named remote from
  the `PROXIMO_TARGETS` registry (the `pve_doctor` MCP tool was already target-aware; this wires the
  CLI flag). Omit `--target` and behavior is byte-identical (the env-configured box).

### Fixed
- **PMG ticket-refresh race** — `PmgBackend` now serializes login under a lock (double-checked in
  `_ensure_ticket`; the 401 re-login is locked, with the HTTP retry left *outside* the lock to avoid a
  deadlock). Latent under the single-threaded stdio transport, but a real correctness gap if the
  backend is ever driven from multiple threads/async tasks.

## [0.11.0] — 2026-06-30

**Native multi-target + the ACME cert-order plane (347 → 351 tools).** One Proximo instance now
reaches many Proxmox remotes (internal *and* external) via an explicit per-tool `proximo_target=`;
omit it and behavior is byte-identical to before. Also closes the ACME gap (certs could be configured
but never *issued* through Proximo). **Read "Changed" before upgrading** — the PBS/PMG/PDM `verify_tls`
fix is fail-closed. Multi-target was adversarially redteamed (6 dimensions) and live-proven against two
distinct real boxes (PVE + PBS).

### Added
- **ACME certificate *order* plane — closes the gap where Proxmox certs could be half-configured
  but never issued through Proximo.** Account + DNS-challenge plugin tools already existed; nothing
  set the node-side ACME config or triggered an order. Four new tools (**347 → 351**):
  - `pve_node_acme_domains_set` — set a node's ACME `account=` + domains (`PUT /nodes/{node}/config`),
    DNS-01 (`acmedomainN=domain=…,plugin=…`) or standalone http-01. REPLACE semantics: stale
    `acmedomainN` indices are removed, not merged. Strict FQDN validation blocks config-property
    injection through the `,`/`=` delimiters. MEDIUM — config only, no cert issued.
  - `pve_acme_cert_order` — order a new cert (`POST …/certificates/acme/certificate`, async UPID).
    MEDIUM, **not** HIGH like `pve_node_cert_upload`: CA-validated, installed only on a successful
    challenge (a failure can't lock you out); reloads pveproxy on success.
  - `pve_acme_cert_renew` — renew the existing cert (`PUT …`, `force`=renew even if >30d to expiry).
  - `pve_acme_cert_revoke` — revoke at the CA (`DELETE …`). HIGH/irreversible; use
    `pve_node_cert_delete` to fall back to self-signed *without* revoking.
  - Endpoint shapes pinned against a live PVE 9.2.3 `pvesh usage` schema; carry `Smoke-confirm:`
    until live-fired.
- **Native multi-target — one Proximo instance can address many Proxmox remotes** (internal *and*
  external; any of PVE/PBS/PMG/PDM), replacing the one-instance-per-box model.
  - A TOML **target registry** (`PROXIMO_TARGETS`) of named remotes; each carries its connection
    fields with the **secret by reference** (`token_path`/`password_path`), never inlined.
  - Every tool gains an optional **`proximo_target="name"`** parameter. Omit it (the default) and
    behavior is **byte-identical to before** — the env-configured box, every existing test unchanged.
  - The target rides a per-call `ContextVar`, so **PLAN and EXECUTE always hit the same box**; PROVE
    records a **`remote`** field per entry (one chain; omitted on the default path so default-box
    entry hashes are unchanged). **Kind-checked:** a `pbs_*` tool given a `pve` target errors — no
    silent cross-plane call, and a `pve_*` tool aimed at a non-pve target errors rather than silently
    hitting the env box.
  - **No new tools** — `proximo_target` is a parameter on the existing surface. Per-target arming
    stays out-of-band (swaps the operator token at that target's `token_path`).
  - In-container exec (`ct_exec`/`ct_psql`/`ct_logs`/`ct_diagnose`) is target-aware too, but runs
    `pct exec` over SSH — a targeted call needs that box SSH-reachable (`enable_exec` + `ssh_target`);
    an external API-only remote won't serve it.
  - **Adversarially redteamed** (6-dimension review): the core invariants — contextvar isolation,
    kind-safety, secret-by-reference, one-chain PROVE, default-path hash-stability — were confirmed
    sound; the one real finding (the `ct_*` exec tools were not yet target-aware) is fixed above. A
    structural test asserts every remote-acting tool advertises `proximo_target` (only `audit_verify`,
    which verifies *this* instance's ledger, is exempt).
  - See `packaging/targets.example.toml` and the README "Multiple targets" section.

### Changed (review before upgrading)
- **`PROXIMO_PBS_VERIFY_TLS` / `PROXIMO_PMG_VERIFY_TLS` / `PROXIMO_PDM_VERIFY_TLS` now honor the full
  falsy set (`0`/`false`/`off`/`no`) like PVE — and the backend then refuses to start without a CA
  bundle (fail-closed).** Previously only the literal `false` disabled TLS; `0`/`off`/`no` were
  silently ignored and TLS stayed on. If you set one of these to `0`/`off`/`no` and relied on it
  being ignored, **that plane will now fail to start** — remove it (TLS on) or set the matching
  `…_CA_BUNDLE`. (Extends the 0.10.0 PVE `PROXIMO_VERIFY_TLS` fail-closed fix to the other planes.)

## [0.10.0] — 2026-06-29

Security-hardening release. An adversarial multi-agent redteam of the full surface produced 32
confirmed findings (2 high, 8 medium, 22 low); 30 are fixed and 2 are documented-as-inherent. Also
includes three live-proven loose-end fixes. **No new tools** (still 347 across PVE/PBS/PMG/PDM).
**Read "Changed" before upgrading — several fixes are fail-closed and can affect an existing deployment.**

### Changed (review before upgrading)
- **`PROXIMO_VERIFY_TLS=0`/`no`/`off` now actually disables TLS verification as written — and the
  backend then REFUSES to start without a CA bundle (fail-closed).** Previously these values were
  silently ignored and TLS stayed on. If you set `PROXIMO_VERIFY_TLS=0` and relied on it being
  ignored, **the server will now fail to start** — remove it (TLS on) or set `PROXIMO_CA_BUNDLE`.
- **Stricter input validation rejects malformed values that were previously accepted:** non-numeric
  CTIDs (`ct_exec`/`ct_psql`/`ct_logs`/`ct_diagnose`), PBS node names and PMG tracker IDs containing
  path/query metacharacters, and a non-string `raidlevel`. Well-formed input is unaffected.
- **`PROXIMO_SSH_TARGET` is charset-validated at startup** (rejects option-injection shapes such as a
  leading `-`); a normal host / alias / `user@host` is unaffected.
- **Risk labels corrected (some ops now plan at a higher tier):** PMG quarantine `action=delete` →
  HIGH (irreversible); PBS `realm_sync remove_vanished=true`, PVE `node_dns_set`, and PBS
  `traffic_control_delete` → MEDIUM. If you gate approvals on risk tier, these now need the higher gate.

### Security
- **No credential reaches the PROVE ledger or a plan response.** ACME DNS-plugin `data` (Cloudflare/AWS
  provider keys) and create-time `password` options are now redacted in plan output; PDM
  secret-stripping is case-insensitive and recursive.
- **Path-traversal / query-injection seams closed** in PMG `tracker_detail`, PBS `tasks_list`, and
  `access_permissions` (URL-encoded / charset-guarded path segments).
- **A2A DNS-rebind Host guard is always on** (was token-only); IPv6 `::1` loopback bind fixed.
- **PROVE ledger hardened:** a crafted log line can no longer brick the append path (a non-string
  `entry_hash` is rejected); a keyed→unkeyed downgrade now seals + rotates the keyed chain (custody
  seam) instead of silently appending unverifiable bare-SHA entries; `PROXIMO_AUDIT_KEYED=off` warns.

### Fixed
- **Plan/execute honesty (the trust spine):** `pve_create_container`/`pve_create_vm` surface the create
  `options` in the plan (a privileged LXC plans at HIGH); `pve_clone` surfaces name/pool;
  `pve_ha_resource_add` surfaces `max_restart`/`max_relocate` (0 warns it disables CRM action);
  `pve_token_create` surfaces expire/comment.
- **`pve_backup_job_create` guest selection:** `all_guests`/`pool`/`exclude` exposed with
  mutually-exclusive validation (was vmid-only). _Live-proven against real PVE._
- **`pve_network_iface_update`** auto-injects the interface's current `type` so an address-only change
  applies (PVE requires `type`) while a type *change* stays impossible by construction. _PVE-schema-confirmed._
- **Config writes** route through the shared form-coercion so a native bool reaches PVE as `1`/`0`
  (was `True`/`False` → HTTP 400); backend-layer file-path validation added to qemu-agent file ops.
- **`pdm-smoke`** routes its version probe to a PVE remote (PBS remotes return 400 on it). _Live-proven._

### Notes
- Two findings are inherent and documented rather than patched: credentials necessarily travel as MCP
  tool parameters (server-side redaction is complete; the parameter itself lives at the client/LLM
  boundary), and a process-death window in the synchronous audit ledger (fsync plus the Proxmox task
  log are the compensating controls).

## [0.9.0] — 2026-06-27

### Added
- **PDM surface — 22 tools (Proxmox Datacenter Manager).** A fourth surface behind a dedicated
  `PdmBackend` (API-token auth, `PDMAPIToken` scheme), covering the PDM read API: datacenter
  self/topology (ping, version, node status, remotes), fleet aggregate (resources, status),
  tasks + access (tasks, ACL, roles, users), and per-remote proxied reads — PVE
  (`pdm_pve_resources` / `cluster_status` / `node_list` / `qemu_list` / `qemu_config` /
  `lxc_list` / `lxc_config`) and PBS (`pdm_pbs_*`: status, datastores, snapshots). **Read-only
  (DIAGNOSE) throughout — no PDM mutation path.** Brings the surface to **347 tools across 4
  surfaces** (PVE / PBS / PMG / PDM).

### Fixed
- **PDM group-C `state` param.** `pdm_pve_qemu_config` / `pdm_pve_lxc_config` treated the `state`
  query param as optional, but PDM requires it — so a plain call returned `400`. They now default
  `state="active"` (the current-config enum value) and always send it.

## [0.8.1] — 2026-06-27

### Added
- **Official MCP Registry support.** Added `server.json` (2025-12-11 schema) plus a PyPI
  package-ownership token in the README, so Proximo can be published to
  `registry.modelcontextprotocol.io` — which in turn feeds downstream directories
  (Glama, PulseMCP).

### Fixed
- **Docs:** PMG surface count is now correct on the published package (103 net tools; one tool
  was removed in 0.8.0, so the gross "104 new" netted to 103).

Packaging + docs only — no functional/code changes from 0.8.0.

## [0.8.0] — 2026-06-26

### Added
- **PMG surface — 104 new tools (Proxmox Mail Gateway).** Full coverage of the PMG 9.1 API
  behind a dedicated `PmgBackend` (ticket-based auth: `POST /access/ticket` → PMGAuthCookie +
  CSRFPreventionToken; TLS-strict, fail-closed, credential never logged or cached on disk):
  - **Observability:** node status, mail statistics, per-sender/domain/virus/spamscore statistics,
    quarantine spam/virus/attachment status, syslog, RRD node performance data.
  - **Quarantine:** spam/virus/attachment list, per-user spam scores, blocklist and welcomelist CRUD
    (add/remove), `pmg_quarantine_action` (confirm-gated: deliver/delete/mark-seen/blocklist/welcomelist).
  - **Config CRUD:** managed domains (list/create/delete), transport maps (list/create/delete),
    `mynetworks` CIDR entries (list/add/remove), spam config read + confirm-gated update,
    mail relay/smarthost config, TLS/ACME/subscription read.
  - **Service control:** service status and `pmg_service_control` (confirm-gated restart/stop/start
    per `pmg-smtp-filter`, `postfix`, `pmgproxy`, `pmgdaemon`).
  - **RuleDB filtering engine:** full rule/action/object-group management — groups (list/create/
    delete/update), object types (`who`/`what`/`when`/`action`/`timeframe`), rules (list/create/
    delete/update), object assignment (`add_to`/`remove_from`), and rule ordering
    (`pmg_ruledb_apply` confirm-gated).
  - **Backup:** `pmg_backup_run` (confirm-gated scheduled-backup trigger).
  - **Postfix:** queue shape (`pmg_postfix_qshape`) and `pmg_postfix_flush` (confirm-gated queue
    flush).
  - **Doctor:** `pmg_doctor` reads version, access permissions, and node status to verify
    connectivity and token scope — same startup-verify pattern as `pve_doctor`.
- **PMG quarantine tool surface cleanup (breaking, pre-release).** The deliver path previously had
  its own dedicated tool (`pmg_quarantine_deliver`); it was a strict subset of
  `pmg_quarantine_action(action="deliver")` — already live-proven — and was removed to keep one
  consistent action surface. The `pmg_quarantine_list` tool (spam quarantine only) is renamed
  `pmg_quarantine_spam` for symmetry with `pmg_quarantine_virus` / `pmg_quarantine_attachment`. The
  read-collection tools `pmg_quarantine_blocklist` and `pmg_quarantine_welcomelist` gain the `_list`
  suffix (`pmg_quarantine_blocklist_list`, `pmg_quarantine_welcomelist_list`) matching every other
  read-collection tool (`pmg_domains_list`, `pbs_*_list`, etc.). The mutators
  (`pmg_quarantine_blocklist_add` / `_remove`, `pmg_quarantine_welcomelist_add` / `_remove`) are
  unchanged. Tool count: 326 → 325 (PMG 104 → 103).
- **+6 PBS coverage tools** — fills gaps in the PBS surface: `pbs_remotes_list`,
  `pbs_remote_get`, `pbs_datastores_list` (all-datastore view), `pbs_datastore_status` (per-
  datastore detail), `pbs_traffic_control_list`, `pbs_sync_jobs_list`.

### Fixed
- **`pbs_group_change_owner`** now issues `POST /admin/datastore/{ds}/change-owner` (was `PUT`,
  which PBS 4.2 rejects with HTTP 404). Caught by live-smoke against the test PBS instance —
  a case where mocks passed but the wire failed.

### Changed
- Tool count **145 → 325** (PVE 184 + PBS 33 + PMG 103 + `ct_*` 4 + `audit` 1).
- All three Proxmox surfaces (VE · Backup Server · Mail Gateway) are now **live-proven** against
  real Proxmox instances. PMG W1–W5 smoke confirmed: auth, read shapes, safe CRUD cycles (domain/
  transport/mynetworks/spam-config/welcomelist/blocklist), service restart + polling, RuleDB
  paths, and PLAN-path honesty on confirm-gated ops.
- `pyproject.toml` description and keywords updated to reflect the three-surface control plane
  (`pmg`, `mail-gateway` added to keywords).

## [0.7.4] — 2026-06-24

### Added
- **`pip-audit` is now a blocking CI gate** (was a warn-only on-ramp). The resolved dependency
  set is clean — verified by replicating CI's `pip install -e ".[dev]"` resolution, which lands on
  `cryptography` 49.0.0 / `starlette` 1.3.1 / `pydantic-settings` 2.14.2 with no known advisories.
  A new CVE in a resolved dependency now reds CI until it's patched.
- **Trivy image vulnerability scanning** (`.github/workflows/trivy.yml`) — continuous scanning
  of the container image's OS-package + library layers (the `python:3.13-slim` base + apt layer),
  which `pip-audit` (Python deps) and CodeQL (source) don't cover. Findings upload to the Security
  tab. Report-first on-ramp; flips to blocking once a green run confirms the baseline.
- **OpenSSF Scorecard** (`.github/workflows/scorecard.yml`) — supply-chain posture scoring,
  published to the public dashboard.
- **`SECURITY.md`** — security policy + a private vulnerability-reporting path (GitHub private
  advisories), with honest scope notes (risk ratings are advisory, not a sandbox; the PVE token
  is the trust boundary) and image/PyPI authenticity-verification guidance.
- **Scoped CodeQL to the shipped package (`src/`)** via `.github/codeql/codeql-config.yml`,
  matching the existing pyright scope. The dev/demo scripts under `scripts/` print connection
  metadata (node, API base URL) and operation output — which CodeQL's taint tracker flagged as
  `py/clear-text-logging-sensitive-data`, though the token secret is never logged — producing 32
  false positives with no shipped impact. SAST now analyzes exactly what ships.

### Security
- **`ApiBackend` now refuses to construct over unverified TLS** — `PROXIMO_VERIFY_TLS=false` with no
  CA bundle raises `ProximoError` instead of warning, matching the rule `PbsBackend` already enforces
  (every request carries the PVE token; a read-only token is still a credential). **Breaking** if you
  ran with `verify_tls=false`: set `PROXIMO_CA_BUNDLE` to the PVE CA cert (preferred) or
  `PROXIMO_VERIFY_TLS=true`. (audit H-2)

### Fixed
*From an internal adversarial audit (8 dimensions, each finding independently verified):*
- **PLAN integrity on multi-node clusters (C-1):** `plan_config_set` / `plan_config_revert` read live
  config from the *configured default* node, ignoring the `node` the mutation targets — so the PROVE
  plan snapshot could be from the wrong node. Both now resolve `node or config.node`, matching the
  execute path.
- **Audit-ledger crash on a corrupt tail line (H-1):** `_last_hash` didn't guard a valid-JSON
  *non-dict* line, raising `TypeError` — which could crash `record()` mid-mutation (entry unrecorded)
  or DoS `audit_verify`/`head()`. Now guarded the same way `verify()` already was.
- **Exec opt-in is enforced at the backend (M-3):** `ExecBackend.run()` now checks
  `PROXIMO_ENABLE_EXEC` itself, not only at the server layer — defense-in-depth against a future
  direct caller.
- **cloud-init UNDO honesty (M-1, M-2):** an undo-capture failure no longer degrades silently — it is
  surfaced in the result status and the PROVE ledger (`ok:undo_unavailable`); and the undo record now
  discloses that a revert does not delete keys the change added.

### Changed (docs honesty)
- **Honest UNDO scope in README/SETUP (H-3):** the tagline no longer claims *every* dangerous move is
  undoable — now "undoable wherever the platform can snapshot" (delete / template-convert /
  token-revoke and firewall/SDN/ACL ops are irreversible by design, as the body already said).
- Corrected a stale tool count in an A2A docstring (116 → 145, L-3).
- **README/landing copy restructured** — leads with *what it does* + the trust layer, before the backend plumbing (so a reader scanning for the value hits the safety model first, not the API table); the roadmap section trimmed to forward-looking items.

## [0.7.3] — 2026-06-24

### Added
- **`proximo doctor` CLI** — runs the read-only preflight (`pve_doctor`) from the shell and prints its
  JSON, so a user can verify their token/config and see exactly what it CAN and CANNOT do **before**
  wiring Proximo into any AI client. Exits non-zero with a plain message on a config/connectivity error.
- **`SETUP.md`** — a beginner-proof, token-first setup guide (GUI + CLI): create a least-privilege
  (read-only) token, point Proximo at your server, verify the boundary with `proximo doctor`, then
  grant scoped write only when ready. Ships in the sdist.

### Changed
- **Rollback PLAN now warns that PVE excludes `description`/`tags` from snapshots** — so a rollback does
  not revert those fields (use `pve_guest_config_set` / `pve_guest_config_revert` to change them). Surfaced
  by dogfooding against a live cluster, where a set description survived a rollback. No API change.
- **The PBS "not configured" error now points at the PVE-path fallback** — when `PROXIMO_PBS_*` is unset,
  the error suggests `pve_backup_list` against a pbs-type storage, which needs no PBS config (it uses the
  PVE token already in hand). No API change.

## [0.7.2] — 2026-06-23

### Packaging / Security
- **Both publish paths now ship only the user-facing set (deny-by-default).** The github mirror already
  curated its tree; the **sdist did not** — hatchling bundled the whole repo root, so internal dev/strategy
  docs rode along in the published source distribution. Now `[tool.hatch.build.targets.sdist]` ships an
  explicit allowlist (src + README + CHANGELOG + LICENSE), and the mirror's deny list adds
  `POSITIONING.md` / `LANDSCAPE.md` / `ROADMAP.md` alongside `CLAUDE.md`. Internal strategy + dev-memory +
  `.gitea/` + `.remember/` no longer publish on either path. (The wheel was always clean — `packages =
  src/proximo`.) No code or API change.

## [0.7.1] — 2026-06-23

**PROVE robustness — 0.7.0 harden pass.** Crash-consistency, concurrency, and upgrade-UX hardening
around the keyed PROVE ledger. The crypto guarantees themselves (chain integrity, downgrade-rejection,
no-key forgery, tail-pin detection) were re-verified under adversarial testing as **holding** — these
are robustness fixes around them, not crypto changes.

### Fixed
- **`verify()` no longer crashes on a non-string `entry_hash`.** A tampered entry whose `entry_hash`
  was a truthy non-string (a number, list, …) raised `TypeError` instead of reporting tamper — a
  writer-with-access DoS on the verify pillar. It now fails the check cleanly.
- **A crash-torn last line can no longer corrupt the next append.** If a crash left the final line
  without its trailing newline, `record()` now starts the new entry on a fresh line instead of
  gluing two JSON objects onto one physical line (which the forward walk read as a single unparseable
  line, silently re-anchoring the chain at GENESIS).
- **Keyed-default migration is now race-safe.** `seal_and_rotate` claims the new keyed log path
  atomically (temp file + `os.replace`); a concurrent writer that creates the log in the rotate
  window is clobbered rather than landing an unkeyed entry at line 1 (which would have made the live
  keyed ledger fail `verify()` permanently). A concurrent-start "loser" no longer emits a migration
  warning with an empty archive path.

### Changed
- **A pinned head is normalized before validation** (`PROXIMO_AUDIT_EXPECTED_HEAD` and the
  `audit_verify(expected_head=)` param): a hexdigest is case-insensitive and a copy-paste often
  carries a trailing newline or spaces, so an uppercased/whitespaced head is now accepted instead of
  raising. Previously a fat-fingered pin raised in config — which is read on *every* tool call, so it
  broke all tools, not just `audit_verify`. Genuinely malformed pins still raise; a blank value is
  treated as unpinned. `PROXIMO_AUDIT_KEYED` likewise tolerates surrounding whitespace (`" off "`).
- **`audit_verify` returns a `rotation_hint`** when a head mismatch coincides with a sibling
  migration archive — telling the operator whether the mismatch is the expected keyed-default upgrade
  rotation (re-pin) or a genuine tail attack, since the migration's stderr warning is often swallowed
  by MCP stdio clients.
- **Setting `PROXIMO_AUDIT_KEY_PATH` with `PROXIMO_AUDIT_KEYED=off` now warns** that the explicit key
  path takes precedence (the ledger is keyed), instead of silently keying.

### Security
- **The release leak-audit denies `CLAUDE.md` by basename** in BOTH the `audit` report and the
  `build-tree` publisher — they now share one `partition_paths` rule, so `CLAUDE.md` (including a
  nested `docs/CLAUDE.md`) is stripped from the published tree, not merely flagged. Previously a
  basename deny was honored by `audit` but invisible to the prefix-only tree builder (the two could
  drift — audit "clean" while the tree publishes the file).

### Upgrade
- The race-safe migration fix covers the in-process rename window. A ledger is still **all-keyed or
  all-unkeyed for its whole life**, so during a *rolling* upgrade **quiesce or upgrade all writers of
  a given ledger together** — a mixed keyed/unkeyed fleet writing the same ledger across the cutover
  will land a downgraded entry and fail `verify()`. Single-process deployments are unaffected.

## [0.7.0] — 2026-06-23

**PROVE hardening.** Keyed (HMAC) PROVE by default, off-box head-pinning to catch tail attacks,
and a stripped-down public mirror. The keyed default **auto-migrates** an existing unkeyed ledger
on first run — see Upgrade below.

### Added
- PROVE head-pinning: `audit_verify(expected_head=...)` and `PROXIMO_AUDIT_EXPECTED_HEAD`
  catch tail truncation / forged append / full wipe (the off-box anchor is the strong guarantee).
  A malformed pin is rejected as a clear caller error (one 64-hex shape rule guards both the
  per-call `expected_head` and the env default), so a typo never masquerades as a tamper alarm.
  When no head is pinned, `audit_verify` returns a one-line `hint` nudging the operator to anchor
  the head off-box — so the guarantee isn't silently left unused.

### Changed
- PROVE ledger is now **keyed (HMAC-SHA256) by default** (`PROXIMO_AUDIT_KEYED`, opt out with `off`).
  An existing unkeyed ledger is sealed and archived (never deleted), and a fresh keyed log is
  started recording the prior head as a custody seam. Key-gen failure fails closed (no silent downgrade).

### Upgrade
- **Keyed PROVE is now the default — and existing ledgers auto-migrate.** On first run after
  upgrading, an existing *unkeyed* ledger is sealed and archived (`audit.log.unkeyed-<stamp>-<head8>`,
  never deleted) and a fresh *keyed* log is started. A loud warning prints the new head; if you pin
  `PROXIMO_AUDIT_EXPECTED_HEAD`, **re-pin it to that new head**. To stay unkeyed, set
  `PROXIMO_AUDIT_KEYED=off` before upgrading.

## [0.6.5] — 2026-06-22

**Security & live-integration CI.** Closes an A2A bind auth-bypass, hardens identifier validation,
fixes a plan-honesty gap, and lands a substantial live-integration smoke harness that exercises the
trust spine against a real cluster. No new tools (145).

**Released 2026-06-22** — published on PyPI (`proximo-proxmox`), GitHub (Release `v0.6.5`), and GHCR
(signed multi-arch image).

### Security
- **A2A auth-bypass: an empty bind host bound every interface *without* auth.** `_is_public` treated
  an empty/whitespace host as non-public (`bool("")` is `False`), so `PROXIMO_A2A_HOST=""` bound
  `0.0.0.0` — all interfaces — while skipping the bearer-token requirement a non-loopback bind is
  meant to force. An empty, `None`, or whitespace-only host is now classified public: the A2A control
  endpoint refuses to start on it without a bearer token, fail-closed like any other public bind.
- **Identifier validation hardened.** `vmid` is validated as ASCII digits (was `str.isdigit()`, which
  accepts non-ASCII Unicode digits); `realmid` rejects `.`/`..` dot-segments (the path-traversal class
  closed across the other identifiers in 0.6.2/0.6.3); firewall alias CIDRs are validated; and the
  TLS-verify default is pinned fail-closed by test.

### Fixed
- **Plan honesty: `pve_network_iface_update` preview was blind to staged `options`.** The dry-run did
  not disclose every field it would stage, and a reserved `type` key could be passed through. The plan
  now discloses the staged fields and rejects the reserved key.

### Added
- **Public-tree leak-gate catches bare internal hostnames.** The release leak-audit previously matched
  only dotted internal TLDs (`.lan`/`.internal`/`.intranet`); it now also refuses bare internal
  hostnames via an internal-only denylist (itself stripped from the public tree).
- **Registry-completeness gate (CI).** A test pins the read-only tool set and asserts every *other*
  registered tool takes a `confirm=` parameter, so a new mutating tool cannot ship un-gated. (It proves
  a mutator *has* the confirm gate, not that `confirm=False` no-ops.)
- **Live-integration smoke harness.** A phase-tagged orchestrator (`scripts/live-smoke/run-all.py`:
  read → plan → mutate → destroy, escalating by blast radius) plus planes for the mutate slice,
  access-CRUD, storage-admin, and PBS (namespace / snapshot-delete / prune / gc / verify). Each plane
  is guarded by an independent default-deny allowlist (`safety.py`) — a VMID/storage/PBS-host not named
  as a test target is refused *before* any API call, a second safety layer beneath the scoped token —
  is self-seeding and self-cleaning, and SKIPs when its scoped env is unset. The PBS `verify` smoke
  asserts *real, scoped* verification (the target snapshot's `verification.state == 'ok'` and a decoy
  snapshot left untouched). It is wired to a nightly advisory CI job (non-blocking); the read+plan
  slice runs with only a read token and is proven end-to-end against a real cluster.
- **Characterization fixtures pin the blast engine to real PVE response shapes**
  (`tests/test_live_shapes.py`), locking the backup-job selection-mode serialization the
  `guest_destroy` resolver depends on against ground truth — real PVE omits unset `pool`/`vmid` keys
  rather than sending `null`, serializes `all` as an int and `exclude` as a comma-string, and always
  carries a synthetic `current` snapshot entry. Shape-only and credential-free, so they run in the
  fast suite.

### Docs
- **Overclaim corrections.** Fixed a self-contradicting "the hypervisor is never touched" line, the
  PROVE "verifiable" framing, and the PLAN "gate" wording; replaced hardcoded test counts with
  drift-resistant phrasing.

## [0.6.4] — 2026-06-21

**Honesty, UX & defense-in-depth.** Small fixes surfaced by a fresh-eyes multi-agent audit whose
headline finding was that the trust spine holds under five independent adversarial reads. No new
tools (145).

### Security
- **Defense-in-depth: `_check_userid` now rejects `.`/`..` dot-segments**, matching its sibling
  validators (`_check_tokenid` / `_check_roleid`). A userid was safe only by side-effect of its no-`/`
  charset; the explicit guard keeps path-traversal closed if that charset is ever loosened.

### Fixed
- **A2A install hint named a nonexistent distribution.** `pip install 'proximo[a2a]'` (in the runtime
  error message, README, `a2a/__init__.py`, and `pyproject.toml`) hard-failed — the PyPI project is
  `proximo-proxmox`. All four now say `proximo-proxmox[a2a]`.
- **Honesty: "the PVE token never read or logged" was inaccurate.** The token IS read from its file at
  call time (it just isn't logged or persisted). The README and package docstring now say so, matching
  the code's own comment.

### Docs
- **UNDO pillar reframed to its real coverage.** It was presented as a symmetric peer pillar
  ("auto-snapshot + rollback"); in reality auto-snapshot is opt-in and exec-only, guests use
  config-revert / `pve_rollback`, and the firewall/SDN/ACL/token planes aren't PVE-snapshottable at all.
  README + CLAUDE.md now state UNDO covers the snapshottable surface, not every mutation.
- **Blast-radius op-class count corrected** in the README (ten → eleven `compute_*` functions).
- **Two stale security comments corrected** (`storage_admin.py`, `access_governance.py`) that described
  path-traversal gaps the validators actually close.

## [0.6.3] — 2026-06-21

**Defense-in-depth & plan honesty.** Two non-destructive fixes from the post-0.6.2 codebase sweep: a
`pve_clone` dry-run that mislabeled the default *linked* clone as a "new independent guest" now reflects
`full`, and two more path-traversal dot-segments — siblings of the 0.6.2 `pve_token_revoke` fix — are
rejected in the network-interface and storage validators. No new tools (145).

### Fixed
- **Plan honesty: `pve_clone` dry-run mislabeled a linked clone as "independent".** `plan_clone` was
  blind to `full` (the tool never forwarded it), so the dry-run unconditionally said *"new independent
  guest"* — true only for `full=True`, while the default `full=False` is a **linked** clone (copy-on-write,
  template-dependent). It also previewed a storage-targeted clone as viable even though the op refuses
  `storage` without `full=True`. The plan now reflects `full`: linked-vs-full wording, the template
  precondition for a linked clone, and a "will be REFUSED" note for `storage` without `full`. (Same class
  as the firewall rule-precedence fix — the preview describing the wrong behavior. Non-destructive: every
  divergent path already fails closed.)
- **Security (defense-in-depth): two more path-traversal dot-segments closed.** Following the 0.6.2
  `pve_token_revoke` fix, a codebase-wide sweep of path-interpolated identifiers found two siblings
  whose validator permitted a `.`/`..` segment the HTTP client normalizes onto a different endpoint:
  - `_check_iface` rejected `..` but **not a lone `.`** — `pve_network_iface_update(iface=".")`
    collapsed `PUT /nodes/{n}/network/.` onto `PUT /nodes/{n}/network`, the network-config **apply**
    endpoint (a disruptive wrong-target op the plan mislabeled as an interface update).
  - `_check_storage` had no dot-segment guard (storage `.`/`..` collapsed to non-destructive
    endpoints — lower severity, same class).
  Both now reject `.`/`..`. Legit VLAN interfaces (`eth0.100`) and dotted storage ids are unaffected.
  (The other path-interpolated validators were verified to already guard this — start-with-alphanumeric
  anchors, explicit `..` rejects, or `@`/numeric structure.)

## [0.6.2] — 2026-06-20

**Security & correctness.** A path-traversal that could delete a user via `pve_token_revoke`, a
firewall rule-precedence honesty fix, two PROVE/blast-radius corrections, and opt-in ledger redaction
for `ct_psql`/`ct_exec`. No new tools (145); the trust spine was independently re-reviewed and verified.

### Added
- **Clone target storage.** `pve_clone` accepts a `storage` parameter to place a full clone's disks
  on a chosen storage (e.g. to keep the clone off the source storage). Refused for linked clones —
  PVE only honors a storage override on a full copy, so the plan rejects it up front rather than
  send a request PVE will reject. The clone plan also now discloses the `SDN.Use`-on-bridge
  permission the cloned NIC requires on PVE 8+.
- **Release leak-audit guard.** `scripts/release_leak_audit.py` models the curated GitHub publish
  tree (which gitleaks and the pre-push hook never see, because it's a synthetic `git commit-tree`):
  it strips internal-only paths (`.gitea/`) and refuses to publish if the public surface carries a
  leak shape — RFC1918 IP, internal-TLD hostname, `/root` path, or credential token. Wired into the
  `release.sh` gate; `build-tree` emits the clean, audited tree SHA for `git commit-tree`.
- **Opt-in ledger redaction.** `PROXIMO_LEDGER_REDACT=1` makes `ct_psql` and `ct_exec` record a
  fingerprint (sha256 + kind + length) of the SQL / command instead of the body, for operators whose
  SQL or command args may carry secrets/PII (e.g. `--password ...`). Both the ledger `detail` and the
  persisted plan are covered. Default unchanged — the body is recorded for a complete audit trail.

### Fixed
- **Security: path-traversal in `pve_token_revoke` could delete the entire user.** `_check_tokenid`
  (and `_check_roleid`) accepted an all-dots identifier. `pve_token_revoke(userid=u, tokenid="..")`
  built `DELETE /access/users/{u}/token/..`, which the HTTP client normalizes (RFC 3986 dot-segments)
  to `DELETE /access/users/{u}` — deleting the **user** and all their tokens/ACLs, while the dry-run
  plan and the tamper-evident audit ledger both recorded a harmless *"revoke token"*. A wrong-target
  destructive mutation that bypassed both PLAN and PROVE. Now rejects `.`/`..`-class segments (the
  same guard `_check_acl_path` / `_check_tfa_id` already applied). MCP-path only — `pve_token_revoke`
  is excluded from the A2A slice. (Verified empirically against the project's httpx.)
- **Honesty/safety: firewall rule-add disclosed the WRONG rule precedence.** `pve_firewall_rule_add`'s
  docstring and plan claimed the new rule is *"appended — positions of existing rules are not shifted."*
  PVE actually inserts a created rule at the **TOP (position 0)** — `pos` is ignored on create — shifting
  existing rules down, so the new rule takes **precedence** (matching is first-match, top-down). The plan
  told operators the opposite of the truth: a DROP they believed was lowest-precedence lands at the top
  and can shadow an existing SSH/8006 ACCEPT — the exact lockout the tool exists to prevent. Corrected to
  disclose top-insertion and the precedence/lockout implication. (Verified against the PVE API docs +
  the "pos ignored on create" forum report.)
- **PROVE: `pve_guest_power` recorded `outcome="ok"` for an async task.** Guest power
  (start/stop/reboot/shutdown) is task-backed — the `POST .../status/{action}` returns a UPID, like
  every other async op (and the identical-shape `node_service_control`). The ledger now records
  `"submitted"`, never `"ok"`: it must not claim the guest started/stopped when only the task was
  accepted. (The lone async op that asserted completion.)
- **Blast-radius: ACL incomplete group-resolution under-reported risk.** When a group-type ACL entry
  exists in scope but the target's group membership couldn't be resolved (e.g. a failed `user_get`),
  a shadowed inherited grant could be hidden — the engine disclosed this in prose but left the
  structured risk at MEDIUM. It now forces HIGH, matching the honesty contract every sibling engine
  upholds (incomplete enumeration that could hide harm escalates; over-flag is acceptable).
- **Honesty: audit-ledger docstring overclaim.** `audit.py` said *"Secrets are never written here"*
  while `ct_psql` records the SQL body; corrected to state the PVE token is never written and that
  `ct_psql`/`ct_exec` record the SQL/command (redactable via `PROXIMO_LEDGER_REDACT`).
- **Blast-radius: boot-disk under-report.** When a guest's boot disk was indeterminate (legacy
  `boot: c`/`cdn` or no boot line) and it lost a disk on the target storage, the engine reported a
  survivable `degraded`/MEDIUM loss with the false note *"boot disk is elsewhere"* — even though a
  lost disk could itself be the boot disk. It now over-flags as `may NOT boot`/HIGH and never claims
  the boot disk is elsewhere when it cannot see where it is (over-flag, never under-flag).
- **Honesty: package docstring overclaim.** `proximo.__doc__` said *"Least-privilege by default …
  secrets never read or logged"*; corrected to match the README — *"bounded by the token you scope …
  the PVE token never read or logged"* (the API plane has no built-in scoping; `ct_psql` SQL is
  recorded in the ledger).

## [0.6.1] — 2026-06-20

**Release-process & CI hardening.** No functional changes to the shipped package — the
`proximo` runtime code is identical to 0.6.0; this release brings the repository's release
and security tooling up to standard (and is the first release published via the new
tokenless pipeline).

### Added
- **Drift-proof releases.** `scripts/version_tools.py` (single source of truth for the
  version) + `scripts/release.sh` (one-command bump + local gate), plus a
  `version-consistency` CI check that fails the build if `pyproject.toml`,
  `src/proximo/__init__.py`, the git tag, and the CHANGELOG ever disagree.
- **Security CI.** gitleaks (secret scanning), pip-audit (dependency CVEs), CodeQL code
  scanning, and Dependabot (GitHub Actions + pip + security updates).
- **Tokenless PyPI publishing** via OIDC Trusted Publishing, gated behind a manual-approval
  environment — no API token in the release path.

### Changed
- Hardened the MCP tool-count guard (145) against silently-shadowed tools.

## [0.6.0] — 2026-06-19

**Blast-radius coverage push.** Extends the computed blast-radius engine across the destructive tool
surface so no dangerous operation falls back to a bare confirm: ten op-classes (#6–15) now read live
cluster state at plan time and NAME the specific cross-resource consequences (the guests an action
strands, the nodes a firewall change locks out, the principals an ACL deletion orphans, the disk a
volume delete destroys). Each was built test-first and adversarially redteamed — every redteam pass
caught a real under-flag, all fixed. No new tools (still 145); **+86 tests (2308 → 2394)**, ruff +
pyright clean. Backward-compatible (additive). Verified against a real Proxmox: PLAN-checks on live
cluster data, plus a bounded allocate→delete→verify on an isolated test sandbox.

### Added
- **In-use-disk blast for `pve_storage_content_delete` (op-class #14, rank 9).** Deleting a storage volume
  now scans guest configs cluster-wide and, if the volid is an ACTIVE guest disk, names the owning guest
  and escalates to HIGH (won't-boot if it's the boot disk / only copy / EFI-TPM). Exact volid match (so
  `vm-101-disk-0` is not confused with `vm-101-disk-00`); a mounted-ISO (`media=cdrom`) reference is not
  mislabeled as a data disk. Incomplete enumeration is forced HIGH, never read as "not in use".
- **Last-copy blast for `pve_backup_delete` (op-class #15, rank 8).** Deleting a backup archive now reads
  the storage's backup list and reports whether OTHER recovery points of the same guest remain — deleting
  the LAST backup leaves no recovery point (named in `Plan.affected`). Read failure or unparseable guest id
  is disclosed (`complete=False`), never read as "other copies exist". Risk stays HIGH throughout.
- **Attachment blast for `pve_network_iface_update` (op-class #13, rank 4).** Editing a bridge now reads
  the cluster guests and NAMES every guest with a NIC on that bridge — they have their networking
  disrupted when the staged change is applied (token-level bridge match, so editing `vmbr1` does not
  false-match a guest on `vmbr10`). Risk stays MEDIUM (the edit is staged/reversible; `network_apply`
  carries the HIGH mgmt-lockout via the existing apply-lockout engine); the value is naming the
  affected guests in `Plan.affected`. Incomplete guest enumeration is disclosed, never read as safe.
- **Access-plane blast-radius coverage (op-classes #9–12, ranks 5–7).** Four mutating access tools that
  silently orphaned permissions now read the ACL / user DB and NAME exactly who loses access:
  `pve_pool_delete` (was pure/no-reads — now names the principals whose grants on `/pool/<id>` orphan;
  escalates MEDIUM→HIGH when real grants break or a read fails), `pve_group_delete` (now names the
  group-level ACL grants its members lose, not just the member list), `pve_role_update` (names every ACL
  grant the new privilege set re-privileges), and `pve_realm_update` (names every user whose login the
  change could break). Each populates `Plan.affected`/`complete` and follows the read-failure honesty
  contract (a failed read → disclosed + never read as safe). Mirrors the already-covered delete siblings.
- **Disk-residency blast for `pve_guest_migrate` (op-class #8).** `plan_migrate` warned generically
  "requires shared storage"; it now reads the guest's disks + cluster storage.cfg and names exactly which
  disks block a clean migration to the target: a disk on LOCAL/non-shared storage (must be copied with
  `with-local-disks`, or the migrate fails — and a live migration is impossible), a disk on storage that
  is `nodes`-restricted off the target (cannot place at all), a RAW/passthrough device (cannot follow the
  guest to another node), or storage whose config is unreadable (assessed conservatively, never assumed
  migratable). Escalates a live-qemu MEDIUM migrate to HIGH when a disk makes it impossible; risk is never
  lowered. Clean only when every disk is provably shared and available on the target. Closes rank 3.
- **Computed blast-radius for the firewall lockout pair (op-class #7).** `pve_firewall_set_enabled`
  (enable) and `pve_firewall_options_set` (`policy_in=DROP`, `enable`, or unset-`policy_in`) now read the
  firewall ruleset at plan time and **name the nodes that would lose management access** under the
  resulting default-DROP policy: a node is flagged LOCKOUT if its (datacenter ∪ node) ruleset has no
  ENABLED inbound ACCEPT for SSH(22)/PVE(8006), CONDITIONAL if the only such ACCEPT is source-restricted
  to a specific host/range/set (locks out any admin outside it), and disclosed-but-not-flagged if it is
  open or internal/private-restricted. A disabled / outbound / udp / wrong-port rule is never counted as
  protection (no under-flagged lockout); unreadable rules or unenumerable nodes force HIGH and are never
  read as safe. Cluster/node scope only (a guest firewall is self-scoped). The op stays RISK_HIGH
  throughout — the engine names the at-risk nodes, it never lowers risk. Closes rank 2 of the coverage audit.
- **Computed blast-radius for `pve_disk_move` (op-class #6).** Moving a disk onto a target storage now
  reads the target at plan time and names the cross-resource impact: a fit check using the disk's
  PROVISIONED size (worst case) flags a move that **won't fit / fills the target** (HIGH), an
  absolute-free floor plus a percent-of-total threshold flags a **TIGHT** target (MEDIUM), and either
  case names the **co-tenant guests** that share the target and would face allocation pressure. Capacity
  that cannot be read (size or free space unreadable, or incomplete cluster enumeration) is forced HIGH
  and never reported as safe; when the disk fits comfortably, co-tenants are **not** flagged (no
  cry-wolf). The engine only escalates a plan's risk, never lowers it. Hardened `_parse_size_bytes` to
  fail-closed on non-positive/blank input (no wrong-small int can slip past a capacity check). Closes the
  highest-severity gap from the 2026-06-19 blast-radius coverage audit.

### Known gaps (logged, not silently dropped)
- `pbs_prune` and `pbs_namespace_delete` (PBS-server side) are already RISK_HIGH with honest "destroys
  ALL recovery points / no undo" warnings — they do not fall back to a bare confirm. The remaining
  enhancement is *itemizing* which snapshots/groups would be removed (PBS prune `--dry-run` /
  per-namespace group enumeration), which needs the PBS datastore API surface; deferred as a quality
  (not safety) improvement.

## [0.5.0] — 2026-06-19

Three additive features — A2A **signed agent cards** (SIGNET), a native **async-task wait** tool, and a
fifth computed blast-radius op-class (**storage nodes-restrict**). Backward-compatible. Tool surface
**144 → 145** (one new read tool); each built test-first and adversarially redteamed.

**Released 2026-06-19** — published on PyPI (`proximo-proxmox`), GitHub (Release `v0.5.0`), and GHCR
(signed multi-arch image).

### Added
- **Signed A2A agent cards (SIGNET).** Opt-in ES256/JWS signatures over the A2A AgentCard (via the
  a2a-sdk signing helpers, RFC 8785 canonicalization), with the operator public key published as a JWKS
  at `GET /.well-known/jwks.json` (`kid` = RFC 7638 thumbprint; `jku` set). `alg` is pinned to ES256 on
  both signer and verifier — the HS256 algorithm-confusion class is structurally refused. Enable with
  `PROXIMO_A2A_SIGNING_KEY_FILE` (EC P-256 PEM); absent → unsigned card (backward-compatible). Ships
  `verifier_for_jwk`, the client-side pinned verifier — it binds to an out-of-band-pinned key and
  ignores card-supplied `kid`/`jku`, so a MITM cannot substitute their own key. Adds `a2a-sdk[signing]`
  + `cryptography` to the `[a2a]` extra.
- **`pve_task_wait`** — block until an async Proxmox task (migrate / backup / restore / clone /
  rollback / snapshot + guest create) reaches a terminal state or a timeout, returning a structured
  `{upid, finished, succeeded, status, exitstatus, timed_out, polls}` (read-only; `succeeded` is fail-closed
  = stopped AND `exitstatus == "OK"`; timeout clamped 1–600 s, interval 1–60 s). Saves clients
  hand-rolling a `pve_task_status` poll loop. (Proximo's native UPID model — NOT the MCP Tasks protocol,
  which was removed from the spec.)
- **Blast-radius op-class #5 — storage nodes-restrict.** `pve_storage_update` with a restricted `nodes`
  list now NAMES the guests it would strand (those on an excluded node with a disk on the storage —
  won't-boot / degraded / live-crash), mirroring the storage-delete class and reusing its honesty
  contract (incomplete enumeration → loud, HIGH, never "safe"). `nodes=""` is correctly read as PVE's
  "clear restriction → all nodes" widening (strands nobody), not maximal stranding. Enriches the
  existing dry-run preview; adds no tool.

## [0.4.0] — 2026-06-16

A fourth computed blast-radius op-class — **guest-destroy** — on `pve_delete_guest`. Additive and
backward-compatible; tool surface stays **144** (it enriches the existing dry-run preview, adds no
tool). Built test-first, adversarially redteamed, and live read-only-smoked against a real cluster.

**Released 2026-06-16** — published on PyPI (`proximo-proxmox`), GitHub (Release `v0.4.0`), and GHCR
(signed multi-arch image, attestation verified). First public release since 0.2.0; rolls up the 0.3.0
blast classes + `pve_doctor` in the same version.

### Added
- **Blast-radius op-class #4 — guest-destroy.** `pve_delete_guest` dry-run now computes, at PLAN
  time, what destroying a guest actually does, conditional on the call's `purge`/`force`:
  - **What PVE will REFUSE** (`force` does not override the first two): `protection=1`, a template
    with linked clones (names the clones; detection is config-based — LVM-thin/ZFS/RBD — and carries
    an explicit caveat that directory/qcow2 backing chains are not visible in config), and a running
    guest without `force`. An indeterminate run-state with `force=false` is reported as incomplete,
    never as a clean "go."
  - **References, conditional on `purge`:** HA resource, replication jobs, and explicit backup-job
    vmid lists — phrased as "left dangling" when `purge=false` and "removed by purge" when `purge=true`
    (never the opposite). Pool membership is resolved live via `pool_get`.
  - **Intrinsic removals:** disks + their storages, real snapshots (PVE's synthetic `current`
    live-state row is excluded), and pool membership.
  - **Honesty contract:** every edge is read fail-closed; a failed read flags `complete=False` and
    is never reported as "nothing found"; backup coverage is resolved per mode — `all=1` (covered
    unless excluded), `pool=X` (covered iff target is in that pool, incomplete only if pool data
    unreadable), explicit `vmid` list (direct); only a truly unrecognizable selection stays
    incomplete. The common real-cluster `all=1, exclude=…` config no longer cries "incomplete" on
    every destroy plan. (`compute_guest_destroy_blast` / `gather_guest_dependents`.)

## [0.3.0] — 2026-06-16

The blast-radius engine across all op-classes (storage · access/ACL · firewall/network) + a new
onboarding preflight (`pve_doctor`). All additive and backward-compatible; tool surface 143 → **144**.

### Added
- **Computed blast-radius (storage/disk class).** `pve_storage_delete` and `pve_storage_update`
  (disable) now read the cluster at PLAN time and **name the actual guests** that lose disks —
  cluster-wide — distinguishing *"will not boot"* (boot disk / only copy on the storage) from
  *"degraded"* (a non-boot disk lost). Surfaced as `blast_radius` strings **and** a new structured
  `affected: list[dict]` field (additive, non-breaking), and recorded to the PROVE ledger.
  Fail-closed: an incomplete enumeration renders a loud `⚠ INCOMPLETE` marker, never lowers risk,
  and is never read as "nothing affected = safe". New pure engine `proximo.blast` (the graph
  reasoning is unit-tested with zero API). First op-class of the broader blast-radius thesis —
  access/ACL and firewall/network follow the same seam.
  (Spec: `docs/specs/2026-06-15-blast-radius-engine.md`.)
- **Computed blast-radius (access/ACL class).** `pve_acl_modify` now extracts its shadow/widen
  reasoning into the pure `proximo.blast.compute_acl_blast`, populates the structured `affected`
  field, **completes** the target's shadow by resolving their own group-inherited grants (#1), and
  lists who-else-can-reach the path as explicit **UNCHANGED** context (#2). Honest per-principal
  model: only the target gains/loses; group members are never reported as gaining/losing. privsep=1
  tokens do not fold owner groups. Fail-closed throughout (caveat retained when a read fails; risk
  never lowered). (Spec: `docs/specs/2026-06-15-acl-blast-radius.md`.)
- **Computed blast-radius (firewall reach — Part A).** `pve_firewall_rule_add` / `rule_remove` /
  `rule_update` now classify the **per-rule REACH** — *"this rule permits SSH (22/tcp) from
  0.0.0.0/0"* — via the new pure `proximo.blast.compute_firewall_reach`, surfaced as `blast_radius`
  lines **and** the structured `affected` field, recorded to the PROVE ledger. Honest framing:
  reach is a property of **the rule** (what it permits/blocks *if* it is the deciding match in an
  enforced, default-DROP firewall), never an assertion that *"the cluster is exposed"* as fact.
  Missing field → **maximal, never benign**: empty `dport` → ALL ports, empty `source` → anywhere,
  an ipset/alias reference (`+name`/`dc/name`) → unknown-conservative (never "low"). `enable=0` →
  *"staged, not active"*. Removing an ACCEPT names what it **closes**; removing a DROP/REJECT names
  what it **re-permits**; an update classifies the **post-update** rule. Risk is only ever raised,
  never below the MEDIUM floor. (Spec: `docs/specs/2026-06-15-firewall-network-blast-radius.md`.)
- **Computed blast-radius (network-apply lockout — Part B).** `pve_network_apply` now best-effort
  **names the management interface** a network apply would touch: it parses the management host from
  the configured API base URL and, via the pure `proximo.blast.compute_apply_lockout`, names the
  pending interface that carries it (*"this apply changes `vmbr0`, which holds the management host —
  you will lose SSH/API"*), surfaced as `blast_radius` lines + the structured `affected` field.
  This sits on top of the **unconditional `RISK_HIGH`** that network apply already carries — naming
  the interface can only add specificity, never lower risk. Honest by construction: a hostname
  management host, an addressless interface read, a non-pending match, or a read failure all yield
  *"could not identify the management interface — HIGH stands; assume lockout risk"*, **never** "no
  lockout". `pve_sdn_apply` gains a light note that the management path is normally on a plain
  bridge, not an SDN vnet. (Spec: `docs/specs/2026-06-15-firewall-network-blast-radius.md`.)
- **`pve_doctor` — onboarding preflight (read-only).** Checks API reachability + reads the calling
  token's *effective* permissions, then reports what the token CAN / CANNOT do — with the privilege
  + role to grant for each gap. Turns raw `403`s into an actionable checklist; run it first after
  install to verify config/token before wiring Proximo into an MCP client. Routed through the PROVE
  ledger as a read; same advisory posture as DIAGNOSE. Per-capability match-mode prevents overclaim
  (rollback is its own capability — `VM.Snapshot` without `VM.Snapshot.Rollback` is reported as
  create-only, never "UNDO works"). Adds `ApiBackend.version()` + `access_permissions()`. Brings the
  tool surface to **144** — the prior 0.2.0 docs' "144" was an off-by-one (the shipped artifact
  served 143); with `pve_doctor` the documented count is now accurate.

## [0.2.0] — 2026-06-15

Complete the four **half-built planes** to total CRUD coverage. **26 new MCP tools**
(surface now 144), each wearing the PLAN + PROVE trust substrate by construction, built
test-first, adversarially redteamed, and — where the operation is a reversible config-object
edit — **live-proven on a real PVE 9.2 node**.

### Added
- **Firewall objects plane (11 tools)** — aliases (`list`/`create`/`update`/`delete`),
  IP-sets (`create`/`delete` + entry `add`/`remove`), security groups (`create`/`delete`),
  and firewall `options_set`. Scope-aware (cluster/node/guest) via `_fw_base`.
- **HA rules plane (3 tools)** — `ha_rule_create`/`update`/`delete`, the PVE 9 replacement
  for the deprecated HA groups. Auto-detects the groups→rules migration and surfaces it
  honestly rather than 500-ing.
- **SDN plane (10 tools)** — zones (`create`/`update`/`delete`), VNets
  (`create`/`update`/`delete`), subnets (`list`/`create`/`update`/`delete`). New objects stay
  *pending* until `sdn_apply`, so create→delete reverts cleanly with no effect on the
  production network. (`sdn_apply` is unchanged — not re-added here.)
- **TFA admin (2 tools)** — `tfa_get`, `tfa_delete`. PVE gates TFA *mutation* behind a
  ticket-based login session, not an API token: `tfa_delete` is shape-correct and reaches the
  API but is ticket-gated (403 with a token); reads work via token. TFA enrollment remains out
  of scope (interactive challenge→confirm).

### Changed
- `pyright` is scoped to `src/` (`[tool.pyright] include = ["src"]`) so the default run
  reflects the shipped package; structural test-double type noise no longer pollutes the clean
  signal. Tests stay inspectable on demand (`pyright tests/`).

---

## [0.1.2] — 2026-06-14

Distribution + supply-chain hardening. No changes to the MCP/A2A surface or behavior.

### Added
- **GHCR container image** — a release workflow builds and publishes a multi-arch
  (`linux/amd64` + `linux/arm64`) image to `ghcr.io/john-broadway/proximo` on each GitHub
  Release. `docker run -i --rm … ghcr.io/john-broadway/proximo` runs the stdio MCP server on
  demand — no daemon, no open port. Images ship with an SBOM and a sigstore-signed
  build-provenance attestation (`gh attestation verify oci://… --owner john-broadway`).

### Security
- **CI / supply-chain hardening** (independent 3-lens review): workflows default to
  `permissions: contents: read`; the publish and signing actions are pinned by commit SHA
  with a Dependabot keeper; the Docker build uses an allow-list `COPY` so a local build
  can't bake stray secrets into the image.

---

## [0.1.1] — 2026-06-10 — "Spaniard"

Hardening + release-readiness pass driven by an independent multi-team audit (3 cold reviewers,
40 doc claims source-verified, full-history leak audit, adversarial verification of every finding).

### Added
- **Realm options dict** (`8d2dac0`): `pve_realm_create` and `pve_realm_update` now accept a
  type-specific `options` dict — LDAP (`server1`/`base_dn`/`user_attr`), AD (`domain`/`server1`),
  OpenID (`issuer-url`/`client-id`). Previously, creating any LDAP/AD/OpenID realm was impossible
  through the tool. Live-proven against a real PVE 9.2 API.
- **Governance/dangerous plane — live-proven to execute** (milestone): the governance and dangerous
  plane (identity role/group/user/ACL; storage; SDN apply; network apply; realm create) that was
  previously built+redteamed but MOCKED-only is now **proven to execute create→read→delete against
  a real PVE 9.2 API on a nested test cluster**. Also proven on a nested 3-node test cluster:
  offline guest migration (including local-disk) and HA-config operations (resource add/list/remove)
  execute. PROVE ledger verified throughout. **Honest scope:** "nested test cluster" — not
  production scale; HA **fencing** (hardware watchdog) and **online** live-migration (shared storage)
  remain unproven.
- **CI**: GitHub Actions workflow — ruff + the full pytest suite on Python 3.12 and 3.13.

### Security
- **A2A perimeter hardening** (`a8ce10b`, `0d952a6`): fail-closed by design — non-localhost bind
  is **refused** unless `PROXIMO_A2A_TOKEN_FILE` is set; bearer auth (constant-time comparison) on
  the JSON-RPC control endpoint when a token is set; Host-header allowlist + DNS-rebind defense
  (`PROXIMO_A2A_ALLOWED_HOSTS`); `'*'` in the allowlist warns rather than silently disabling. The
  agent card declares the bearer scheme. localhost-default dev behavior unchanged; A2A stays opt-in.
- **Audit ledger file permissions:** the ledger is now created `0600` (owner-only) instead of the
  umask default — entries can carry command/SQL detail and were world-readable on typical umasks.
  Applies at creation; an existing file keeps the mode its operator set.

### Fixed
- Realm create/update no longer silently ignores type-specific options (LDAP/AD/OpenID realms
  were uncreatable before this fix).
- **Audit-integrity:** `ct_logs` now enforces the CTID allowlist at the server layer like its
  siblings — a forbidden CTID ledgers as `blocked:allowlist` instead of surfacing as a backend error,
  so allowlist denials are uniformly traceable in the PROVE ledger. Blocked entries for read-only
  tools (`ct_logs`, `ct_diagnose`) now ledger `mutation: false`, matching the tool's true class.
- **Packaging:** `proximo-a2a` without the `[a2a]` extra now prints a one-line
  `pip install "proximo[a2a]"` hint (exit 2) instead of a raw `ModuleNotFoundError` traceback —
  including when only `uvicorn` is missing; a missing *submodule* of an installed dependency still
  tracebacks (that is a real environment bug, not a missing extra).

### Notes
- **117 MCP tools; 1964 tests passing (0 skipped); ruff clean.** Published 2026-06-10 — GitHub + PyPI (`proximo-proxmox`); GHCR pending.
- Docs: public-readiness scrub of ROADMAP/CHANGELOG/POSITIONING; README install command made
  copy-pasteable; claim wording tightened to carry its own scope. Lint: 3 leftover warnings in the
  live-smoke scripts cleaned.

## [0.1.0] — 2026-06-09 — "Spaniard"

First blood — the foundation of the ethical Proxmox MCP. _Tagged `v0.1.0`; not yet published to
PyPI/GHCR (local/private). Honest scope: 117 MCP tools, most exercised against mocks only; the trust
spine + core lifecycle are live-proven, the governance plane is built/redteamed but not yet live-fired._

### Added
- **MCP stdio transport, proven end-to-end:** `python -m proximo` entry point; the `initialize` handshake
  advertises Proximo's own version (not the MCP SDK's); covered by a real-client integration test
  (`test_mcp_stdio_e2e.py`: client → stdio → FastMCP dispatch → tool → back).
- Two backends: **REST API management** (scoped token) + **`ssh`→`pct` in-container exec** (local or remote).
- **MCP tool surface** (FastMCP): `pve_node_status`, `pve_list_guests`, `pve_guest_status`,
  `pve_guest_power`, `ct_exec`, `ct_psql`, `ct_logs`.
- **Ethical spine:** append-only audit log (records real outcomes), confirm-gates on every mutating tool,
  fail-closed CTID allowlist, input validation on API path components (vmid/kind/node).
- Tests (13) + ruff lint config. Clean run.

### Security
- Security redteam (2026-06-07): **5 findings, all fixed** —
  `ct_exec`/`ct_psql` now confirm-gated; allowlist now fails **closed**; audit records real outcomes
  (errors included); `vmid`/`kind`/`node` validated against injection; TLS-disabled now warns.
- Verified solid: command injection (shlex-correct on local + ssh + psql paths); the API token is never
  logged, never enters the audit log, subprocess argv, or error messages.

### PROVE pillar — tamper-evident ledger (2026-06-07)
- The audit log is now a **hash-chained, tamper-evident ledger**: `entry_hash = sha256(prev_hash + body)`,
  flock-guarded, fsync'd. `verify()` and the `audit_verify` MCP tool detect any altered / deleted /
  inserted / reordered entry and pinpoint the break; `head()` is anchorable off-box. Tamper-**evident**,
  not tamper-proof (honestly scoped). +6 tamper-detection tests. Redteam: 2 findings fixed.
- This is one of the four trust-layer pillars (PLAN · UNDO · **PROVE** · DIAGNOSE).

### PLAN pillar — dry-run by default (2026-06-07)
- New `proximo.planning` module: **every mutating tool now previews before it acts.** Called without
  `confirm=True`, `pve_guest_power` / `ct_exec` / `ct_psql` return a **plan** — the exact change, the
  guest's live state (power), blast radius, and an **advisory, heuristic risk rating** — instead of
  executing. `confirm=True` then executes. You structurally cannot mutate without a plan first existing.
- **PLAN ⊗ PROVE:** the previewed plan (including the live state it was based on) is written to the
  tamper-evident ledger with `outcome="planned"`; a confirmed execution records `confirmed=true`. The
  approval trail — *what preview was shown before the action* — is now verifiable, not just *that* it ran.
- **Honest by design (guard every path to LOW):** `LOW` means "does not change state," not "safe";
  the absence of a `HIGH` flag is not a safety signal; destructive signatures are curated, not exhaustive.
- Adversarial review: confirmed bypasses fixed — whitelist audit (`find -delete`, `ip route add`,
  `mount <dev>` no longer rate "read-only"); SQL `SELECT pg_terminate_backend()/lo_import()`,
  `COPY ... PROGRAM` (RCE) now escalate; failed dry-runs are audited; `current` state recorded; latent
  `_max_risk`/`_fmt_uptime` edge crashes fixed. Every confirmed bypass became a regression test.
- Tests: **81 total** (was 21), ruff clean.
- **Guarantee enforced:** the plan is recorded on BOTH paths — even a one-shot `confirm=True` records
  its `planned` entry before mutating (no plan, no mutation). The PLAN→PROVE triplet
  (`planned → ok/confirmed`) is uniform; a one-shot confirm can't bypass the recorded preview.

### UNDO pillar — auto-snapshot before mutating + one-call revert (2026-06-07)
- **Snapshot backend + tools:** `pve_snapshot_list` (read), `pve_snapshot_create`, `pve_rollback`
  (DESTRUCTIVE — discards changes since the snapshot), `pve_snapshot_delete` (all PLAN-gated), and
  `pve_task_status` to poll the async task UPIDs these return. Endpoints verified against PVE docs.
- **The headline — auto-undo before exec:** `ct_exec`/`ct_psql` gain `snapshot=True`. With `confirm=True`
  it takes a `proximo_undo_<ts>` snapshot **and waits for the task to finish** before running the
  mutation, records the undo point, and returns it. **Fail-closed:** if the snapshot can't be created
  or doesn't finish OK (e.g. storage doesn't support snapshots), the command is **NOT run**.
- **Honest:** snapshots are storage-dependent (ZFS/BTRFS/LVM-thin; not directory/raw) — surfaced in the
  plan, never assumed. Rollback's PLAN spells out the blast radius. Async ops record `outcome="submitted"`
  (not "ok") so the ledger never claims an in-flight task is done.
- Adversarial review: confirmed fixes, each a regression test — regex anchors `$`→`\Z` (newline bypass),
  UPID length cap + reserved-name (`current`) guard, microsecond-unique undo names, strict task-exit
  (fail-closed on missing `exitstatus`), server-layer allowlist gate (no orphaned snapshot for a
  forbidden CTID), non-contradictory rollback preview when the snapshot is missing.
- Tests: **116 total**, ruff clean.

### DIAGNOSE pillar — read-first "what's broken" (2026-06-07)
- New `proximo.diagnose` module + tools: `ct_diagnose` (API guest status + a FIXED read-only
  in-container battery — failed units, disk, recent errors, memory, listening ports) and
  `pve_diagnose` (node status + storage usage + recent failed tasks). Both strictly READ-ONLY
  (no confirm, no mutation), audited. Backend reads: `node_storage`, `node_tasks`.
- **Honest by design:** advisory flags, never causation ("signal present", not "the cause is X").
  Flags also surface **incompleteness** — partial mode (exec off → API-only + a skipped-probes flag),
  a failed read, or a failed probe all flag, so an empty `flags` list can never read as a false clean
  bill of health. Inactive/offline storage is reported as offline, not as "full" (no stale-data alarm).
- Adversarial review — read-only guarantee held (no injection, gates correct); the task-list `status`
  field was **verified against the live PVE API**. Fixes, each a regression test: incompleteness flags,
  inactive-storage handling, removed dead `--no-legend` guard, `_frac` inf/overflow guard, transient/
  WARNINGS tasks no longer counted as failed, `node_tasks` limit clamp, `ExecBackend` vmid validation.
- Tests: **141 total**, ruff clean. **All four trust-layer pillars (PLAN · UNDO · PROVE · DIAGNOSE) now built.**

### Coverage expansion — phases 1–7 (2026-05 → 2026-06)
- Grew the MCP surface from the 7 foundation tools to **117** `@mcp.tool()` tools, every mutating one
  wearing PLAN+UNDO+PROVE by construction: provisioning/backup/restore, config/disk/cloud-init mutation, the
  four "dangerous plane" domains (**firewall · network/SDN · cluster HA/migration · ACL/users/roles/realms**),
  observability, task/pool control, storage admin, and **PBS-native** deep tools (GC/verify/prune/snapshots/
  namespaces; separate `:8007` backend, TLS fail-closed).
- **Live-proven** against a real PVE: the core provisioning/config mutate cycle (create→config→revert→
  clone→backup→restore→delete, ledger verified) + read shapes across node/storage/observability + a
  PBS datastore. **Honest scope:** the bulk of the 117-tool surface — *including the dangerous plane* —
  is **MOCKED-only** (unit-tested against fakes, not fired against real Proxmox). A broad live smoke needs a
  wider scoped token.

### A2A (Agent2Agent) face — experimental (2026-06-09)
- Optional second protocol head (`pip install 'proximo[a2a]'` → `proximo-a2a`): a curated **16-skill slice**
  exposed over A2A, routing to the same server tools so PLAN/PROVE/UNDO/fail-closed are inherited. Serves an
  agent card at `/.well-known/agent-card.json`; localhost by default (no built-in auth — warns on
  non-localhost). Built + redteamed (PLAN-bypass + slice-boundary: **0 findings**); +47 tests. **Proven
  end-to-end against a real a2a-sdk client** — agent-card resolve over HTTP + a real `message/send` invoking a
  skill → completed task with a `result` artifact (real-socket proof + an in-process integration test,
  `test_a2a_e2e.py`).

### PROVE — opt-in HMAC-keyed audit chain (2026-06-09)
- The audit ledger now supports an **opt-in keyed mode**: set `PROXIMO_AUDIT_KEY_PATH` to chain entries
  with **HMAC-SHA256** instead of bare SHA-256 (key auto-generated at 0600 via an atomic temp+link, hex
  stored, fail-closed on empty/non-hex/<32-byte). The **ledger's key is authoritative** — a downgrade
  (strip the HMAC, recompute as SHA-256 without the key) is rejected; a keyed log must be all-keyed. Default
  stays **unkeyed and byte-identical** (existing logs + tests unaffected); `audit_verify` reports `keyed`.
  Adversarial review (forge / key-handling / verify lenses): no exploitable forgery; +12 tests incl. the downgrade
  attack. **Honest scope:** keying resists forward-rewrite by an attacker *without* the key, but a same-user
  attacker who can write the 0600 log can often read the 0600 key — the **off-box `head()` anchor remains
  the strong guarantee.** Not a "cryptographic depth" moat.

### Honesty note (2026-06-09)
- The PBS cert fingerprint is stored but **not yet wire-enforced**.

### Notes (as of 0.1.0 — historical; since superseded)
- At 0.1.0 this was **pre-alpha and not yet released**; Apache-2.0 LICENSE added. Then-pending: broad
  live smoke of the mocked surface (needs a properly-scoped token) and publish (PyPI/GHCR + CI) so the
  install commands work — **all since done.** Proximo is publicly released; see `[0.4.0]` above
  (published on PyPI · GitHub · GHCR).

_Strength and honor._
