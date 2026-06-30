# Native multi-target — Design Spec

**Date:** 2026-06-29
**Status:** Approved — pending spec review
**Authors:** John Broadway, Claude (Anthropic)
**Applies to:** proximo (target resolution — `config.py`, `backends.py`, the `_svc()/_pbs()/_pmg()/_pdm()` resolvers and `@mcp.tool()` surface in `server.py`, the PROVE ledger `audit.py`)

---

## Plain-language summary (read this part)

Today one Proximo instance talks to exactly **one** Proxmox box. Its target is fixed
at startup from `PROXIMO_*` env vars (one base URL, one node, one token). To reach a
second box — say an external PVE — you run a **second Proximo instance** with its own
env. That instance-per-box model is what the external-PVE cert work hit: reaching a remote PVE
forced a whole second MCP server.

This spec makes Proximo **natively multi-target**. You register named remotes —
internal or external, any of the four planes (PVE / PBS / PMG / PDM) — in one registry
file, and every tool gains an optional `target="name"` to pick which box it hits. No
`target` (the default) behaves **exactly as today** — same env, same single box, every
existing test unchanged.

The safety property that makes this trustworthy: the target travels **with each call**.
A `PLAN` and its `EXECUTE` always resolve to the same box, and the PROVE ledger records
**which box** every operation hit. There is no session-global "current box" that could
drift between preview and mutation.

Your touch-points: write a `targets.toml`, point `PROXIMO_TARGETS` at it, and pass
`proximo_target="name"` when you want a non-default box. Everything else is automatic.

## Refinements locked during planning (read this)

Two names changed from the first sketch, both forced by reading the code:

1. **Selector is `proximo_target=`, not `target=`.** PVE already uses a `target` param
   (migration destination node) on 7 tools, and PDM uses `remote` on 10 tools — both
   natural names collide. `proximo_target` is namespaced and collision-proof (no Proxmox
   API field is ever `proximo_*`). It is the verbatim selector name everywhere below.
2. **The ledger `remote` field is omitted on the default path** (not written as a literal
   `"(default)"`). `verify()` rehashes each entry from all non-chain fields, so omitting
   `remote` on env-box ops keeps their entry hashes byte-identical to today — zero impact
   on the existing path and its hash-exact tests. Absence of `remote` *is* the default box.

## Goals

- Register **multiple Proxmox remotes** (PVE/PBS/PMG/PDM), internal RFC1918 *and*
  external public-IP, in a single Proximo instance.
- Direct any of the 352 tools at a named remote via an explicit `target=` parameter.
- **Zero behavior change** when `target` is omitted and/or no registry is configured —
  the env-configured single box, bit-for-bit as today.
- Preserve the trust spine per call: **PLAN and EXECUTE hit the same box**, and PROVE
  records the remote. Wrong-box operations must be **structurally impossible**, not
  merely "audited after the fact."
- Keep **secrets by-reference** (per-target `token_path`), never inlined in the registry.

## Non-goals

- **Not** a session-global "current target." Rejected: it can drift between PLAN and
  EXECUTE, undermining the exact guarantee Proximo exists to provide.
- **Not** per-target arm/disarm *in code*. Arming stays an external, classifier-gated
  script (John's hand) that swaps the token file at a target's `token_path`. This spec
  makes per-target arming *possible* (each target has its own `token_path`); the
  target-aware arm scripts are separate infra work.
- **Not** a per-target audit ledger. PROVE stays **one** tamper-evident chain for the
  instance, with a `remote` field per entry.
- **Not** a config UI / target-discovery / cluster auto-join. Hand-authored registry only.

---

## Architecture

### 1. Target registry

A TOML file referenced by `PROXIMO_TARGETS`, read with stdlib `tomllib` (**no new
dependency**). Each `[targets.<name>]` table declares one remote of one `kind`, with the
same fields that plane reads from env today — just keyed by name instead of by env var.

```toml
# targets.example.toml  — doc-range values only; the real file is runtime config (untracked)
[targets.home-pve]
kind       = "pve"
base_url   = "https://192.0.2.10:8006/api2/json"
node       = "pve"
token_path = "/etc/proximo/home-pve.token"   # secret by reference, never inlined
verify_tls = true
ca_bundle  = "/etc/proximo/home-pve-ca.pem"
ssh_target = "pve"                            # exec half; "local" for on-host

[targets.edge-pve]
kind       = "pve"
base_url   = "https://198.51.100.20:8006/api2/json"   # external public IP
node       = "edge"
token_path = "/etc/proximo/edge-pve.token"
verify_tls = true
ca_bundle  = "/etc/proximo/edge-pve-ca.pem"

[targets.home-pbs]
kind       = "pbs"
base_url   = "https://192.0.2.7:8007"
token_path = "/etc/proximo/home-pbs.token"
verify_tls = true
ca_bundle  = "/etc/proximo/home-pbs-ca.pem"
```

- **Secrets stay by-reference.** A target carries a `token_path` (PVE/PBS/PDM) or
  `password_path` (PMG), never the secret itself — same discipline as the env today.
- The registry **file** is runtime config, like the env: **untracked**. A
  `targets.example.toml` ships in the repo with TEST-NET (`192.0.2.0/24`,
  `198.51.100.0/24`) / `example.com` values only.
- Parsing is **fail-loud**: malformed TOML, unknown `kind`, or a missing required field
  for that kind raises at resolution with a clear message (never a silent guess) — same
  ethos as `from_env()`.

### 2. Resolution via contextvar

A module-level `_active_target: ContextVar[str | None]` (default `None`).

- Each plane resolver gains the active target as its input. `_svc()` becomes:
  resolve `_active_target.get()` → `None` means `ProximoConfig.from_env()`
  (**unchanged**); a name means build a `ProximoConfig` from that registry entry
  (asserting `kind == "pve"`). `_pbs()/_pmg()/_pdm()` mirror this against their config
  classes and their own kinds.
- **Backward-compat rule (locked):** `target=None` resolves to the **env box**, *even
  when a registry is loaded*. The registry is purely additive — a named target is
  reached only by naming it. There is no implicit "registry default" overriding env.
- Because resolution is a single contextvar read, **every** `_svc()` call — including the
  ~15 internal ones in helpers (`_audited`, `_plan`, `_wait_task`, `_auto_undo`, …) —
  auto-resolves to the active box. A multi-step op (mutate → auto-snapshot → wait-task)
  cannot land its snapshot on the wrong box, because there is no per-call target to
  forget to thread. This is the core safety mechanism.

### 3. `target=` exposed per tool; bodies untouched

FastMCP builds each tool's input schema via `inspect.signature(func, eval_str=True)`
(`mcp/server/fastmcp/utilities/func_metadata.py:222`), and `inspect.signature` honors a
function's `__signature__` override. So a single `@target_aware` wrapper can:

1. Inject `target: str | None = None` into the wrapped tool's `__signature__` (with a
   real `str | None` annotation object, not a string, so `eval_str=True` is a no-op for
   it) — FastMCP then advertises `target` on the tool.
2. On each call, `set()` the contextvar from the `target` kwarg and `reset()` it in a
   `finally`.

The 352 tool **bodies and every internal helper stay byte-for-byte unchanged.** The
wrapper is applied once per tool (an explicit, greppable decorator — *not* a runtime
monkeypatch of the third-party `mcp.tool`), so each tool is visibly target-aware in the
diff and the change at every site is identical.

**Opt-out:** genuinely instance-level tools that act on the local Proximo, not a remote
box — e.g. `audit_verify` (verifies *the* ledger chain) — are excluded from the wrapper
via a small explicit set, so they do not advertise a meaningless `target`.

> **Implementation step 0 (spike, before the sweep):** a throwaway test confirming the
> injected `target` round-trips into the live generated JSON schema and reaches the
> contextvar end-to-end. If FastMCP's introspection does *not* honor `__signature__` as
> read, fall back to adding the literal `target` param to each signature (mechanical,
> script-applied) — but **still** drive resolution through the contextvar, so bodies and
> helpers remain untouched and the wrong-box property holds either way.

### 4. Kind safety

A target names a remote of exactly one `kind`. A tool resolving a target of the wrong
kind raises immediately:

```
ProximoError: target 'home-pbs' is kind 'pbs', not usable by a PVE tool
```

No silent cross-plane call. Enforced in each plane resolver (`_svc` asserts pve, `_pbs`
asserts pbs, etc.).

### 5. PROVE: one chain, `remote` field

The ledger stays a **single** tamper-evident hash-chain for the instance. `record()`
gains a **`remote`** field, sourced from the same contextvar, distinct from the existing
`target` field (which keeps meaning *the operation's object* — vmid/resource/label). An
entry then reads, in effect: *action X on object `target` at box `remote`, outcome Y.*
The `remote` field is **omitted** on the default path (the env box) — its *absence* is the
unambiguous default-box marker, which keeps default-path entry bodies (and thus their hashes)
byte-identical to the pre-multi-target format. The hash-chain, keying, and `expected_head`
pinning are otherwise unchanged.

### 6. Arm/disarm — out of code scope (noted)

Per-target privilege escalation stays **John's hand**: an external, classifier-gated
script swaps the operator token into a target's `token_path`, live, no restart — exactly
as the single-box arm works today, just parameterized by target. Proximo's code never
arms; it reads whatever token is at `token_path` at call time. The registry's per-target
`token_path` is the enabling hook; the target-aware arm scripts are separate infra work,
not built here.

---

## Data flow — a targeted call

```
client calls pve_guest_power(vmid=131, action="reboot", proximo_target="edge-pve")
  └─ @target_aware wrapper: _active_target.set("edge-pve")   [finally: reset]
       └─ tool body (unchanged): cfg, api, _, _ = _svc()
            └─ _svc(): _active_target.get() == "edge-pve"
                 → registry lookup → kind=="pve" ✓ → ProximoConfig(edge-pve fields)
                 → ApiBackend bound to https://198.51.100.20:8006, token edge-pve.token
       └─ _plan/_audited (unchanged): also read _svc() → SAME edge-pve backend
            └─ ledger.record(action="pve_guest_power", target="131",
                             remote="edge-pve", mutation=True, ...)
```

Omit `proximo_target` → contextvar stays `None` → `from_env()` → today's behavior; the ledger
entry has **no `remote` field** (absence marks the default box, preserving byte-identical hashes).

## Error handling

- **No registry but `target="x"` given:** fail-loud — "no target registry configured
  (set PROXIMO_TARGETS); cannot resolve target 'x'."
- **Unknown target name:** fail-loud — "unknown target 'x'." (the known-target list is NOT
  enumerated to the caller — defense-in-depth, esp. via the A2A face).
- **Kind mismatch:** §4 error.
- **Malformed registry / missing required field:** fail-loud at parse, naming the field.
- **Token/CA file missing at call time:** the existing backend error path (unchanged).
- **TLS fail-closed unchanged:** a target with `verify_tls=false` and no `ca_bundle` is
  refused by `ApiBackend`/`PbsBackend` exactly as the env path is today.

## Testing

TDD the **new** surface (the existing 4300+ tests prove only that the default path is
unbroken — `target=None` — they say nothing about multi-target):

- Registry parse: valid file; malformed TOML; unknown kind; missing required field.
- Resolution: `None` → env config (assert identical to today); name → registry config;
  unknown name → error; no-registry-but-name → error.
- **Kind mismatch:** a `pbs_*` tool with a pve target → `ProximoError`.
- **PROVE `remote` field:** a targeted op records the right `remote`; a default op has **no**
  `remote` field (absence == env box; default-path hashes unchanged).
- **Wrong-box-undo (the regression guard):** a mutation on target B with auto-snapshot
  resolves the snapshot **on B**, never the default. Asserted directly.
- Schema spike (step 0): `target` appears on a wrapped tool's generated schema and is
  absent on an opted-out tool (`audit_verify`).

**Live validation** against the **proximo-lab PVE VMs** (`pve-test1/2/3` on the sealed
`vmbr1`) — two real PVE targets registered, an op proven to hit the intended one and the
ledger to show it. **Not the live external box** — another session owns it right now, and two
sessions mutating one box is its own hazard. Stop the lab guests (through Proximo) when
done.

## Build order (each step: suite green before the next)

1. **Core:** registry parse + `_active_target` contextvar + the four resolvers'
   `None`-vs-name branch + the `@target_aware` wrapper (+ step-0 spike). Default path
   unchanged.
2. **PROVE:** `remote` field through `record()` / `_audited` / `_plan`.
3. **Enable per plane, verify each:** PVE first (lab-validated), then PBS, PMG, PDM.
4. **Docs + example:** `targets.example.toml`, README target section, `proximo doctor`
   gains an optional per-target reachability check (CAPTURE only).

## Security & leak posture

- Public repo: the committed `targets.example.toml` and **all** fixtures use doc ranges
  only (`192.0.2.0/24`, `198.51.100.0/24`, `example.com`) — no real IPs, nodes, `/root`
  paths, or tokens, from the first keystroke.
- The real registry file is untracked runtime config; `release_leak_audit.py` continues
  to model the publish tree and refuses a leak shape.
- Secrets by-reference only; the registry never holds a token/password value.
- No widening of Proximo's own privilege: arming remains out-of-code and John's hand.
