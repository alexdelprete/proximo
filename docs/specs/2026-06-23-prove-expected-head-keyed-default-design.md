# PROVE: `expected_head` head-pinning + keyed-by-default — Design Spec

**Date:** 2026-06-23
**Status:** Approved — pending spec review
**Authors:** John Broadway, Claude (Anthropic)
**Applies to:** proximo (the PROVE pillar — `audit.py`, `audit_verify` tool, A2A skill)

---

## Plain-language summary (read this part)

Proximo's audit ledger is **tamper-evident**: it hash-chains every entry, so if
someone alters, inserts, reorders, or deletes an entry *in the middle*, verification
points to the exact break. But a forward walk alone is blind to **tail attacks** —
deleting the last few entries, appending a forged one, or wiping the whole file.
Today, `audit_verify()` returns `ok=True` after any of those. The defense already
exists in the library (`verify(expected_head=...)` and `head()`), but the **tool
never exposed it**, so in practice nobody can use it.

This spec ships two things:

1. **Head-pinning on `audit_verify`** — you pin the ledger's `head()` somewhere
   off-box (a secrets store, a read-only mount, your MCP-client env), and every
   verify checks the live chain against it. Now tail-truncation, forged-append, and
   full-wipe are all caught. You pin it once via `PROXIMO_AUDIT_EXPECTED_HEAD`;
   you can still override per call.

2. **Keyed PROVE by default** — the ledger upgrades from bare SHA-256 to
   HMAC-SHA256 (keyed) chaining out of the box, so an attacker who can write the log
   but can't read the key can't forge a valid forward rewrite. Existing unkeyed logs
   are **not broken**: on first run Proximo *seals* the old log (writes a final
   marker, archives it untouched-as-a-chain) and starts a fresh keyed log that
   records where the old one ended — a clean, auditable seam. You can opt out with
   `PROXIMO_AUDIT_KEYED=off`.

**Honest framing (unchanged):** keying is *marginal* hardening — a same-user attacker
who can write the 0600 log can usually read the 0600 key too. The **off-box
`expected_head` anchor is the strong guarantee.** Use both; don't oversell keying.

Your touch-points: optionally set `PROXIMO_AUDIT_EXPECTED_HEAD` (and `…_KEYED=off`
if you don't want keying). Everything else is automatic.

---

## Goals

- Expose `expected_head` head-pinning through the `audit_verify` MCP tool **and** the
  A2A skill, with a configured default so it's actually used, not forgotten.
- Make **keyed (HMAC-SHA256) PROVE the default**, while guaranteeing **zero breakage**
  for users with an existing unkeyed ledger (auto seal-and-rotate).
- Keep the spine's ethos: **fail-closed, no silent downgrade**, loud about anything
  surprising, honest about the threat model.
- Fix the documentation overclaim the 2026-06-22 audit flagged: the README's PROVE
  scorecard can now honestly state head-pinning ships.

## Non-goals

- **Not** tamper-*proof*. Detection remains the guarantee, not prevention — anyone with
  write access (and, keyed, the key) can rewrite the chain forward; the off-box anchor
  is what catches it.
- **Not** an off-box anchor *service* (no remote attestation, no head-publishing daemon).
  Proximo surfaces `head()`; pinning it off-box is the operator's job.
- **Not** key rotation / re-keying of an in-flight keyed ledger. The only mode
  transition supported is unkeyed → keyed via seal-and-rotate.
- **Not** changing the interior-tamper detection that already works.

---

## Architecture — one ledger-lifecycle factory

All mode/lifecycle decisions move into a single factory in `audit.py`:

```python
def open_ledger(cfg) -> AuditLedger
```

It encapsulates: resolve the effective mode (keyed default vs. opt-out vs. explicit
key path) → load/generate the key → inspect the existing log's mode → seal-and-rotate
if a keyed ledger is wanted but the on-disk log is unkeyed → return a ready
`AuditLedger`. `server._svc()` calls `open_ledger(cfg)` instead of today's inline
`load_or_create_key(...)` + `AuditLedger(...)`.

**Rejected alternatives:** inlining rotation in `_svc()` (scatters crypto lifecycle
into the server, untestable in isolation); a separate `audit_migrate.py` (overkill for
the code size). Keeping it in `audit.py` makes the whole lifecycle unit-testable behind
one seam and keeps the crypto in the module that owns it.

---

## Feature A — `expected_head` on `audit_verify`

### Config

New field on `ProximoConfig`:

```python
expected_head: str | None = None   # PROXIMO_AUDIT_EXPECTED_HEAD — off-box-pinned head
```

Parsed in `from_env()`: `os.environ.get("PROXIMO_AUDIT_EXPECTED_HEAD") or None`.
Validation: if set, it must be a 64-char lowercase hex string (matches `GENESIS_HASH`
shape / a SHA-256 / HMAC-SHA256 hexdigest); otherwise fail loud at load
(`RuntimeError`) — a malformed pin is an operator error we surface, never ignore.

### Tool

```python
@mcp.tool()
def audit_verify(expected_head: str | None = None) -> dict:
    cfg, _, _, audit = _svc()
    pin = expected_head if expected_head is not None else cfg.expected_head
    v = audit.verify(expected_head=pin)
    return {
        "ok": v.ok,
        "entries": v.entries,
        "broken_at_line": v.broken_at,
        "reason": v.reason,
        "head": audit.head(),          # the live/actual head
        "expected_head": pin,          # what was checked against (None = not pinned)
        "keyed": audit.keyed,
    }
```

- Explicit param wins over the config default; `None` + no config default = today's
  behavior (forward walk only), but the response now makes the *absence* of a pin
  visible (`expected_head: null`) so a caller can see they're unprotected against tail
  attacks.
- On mismatch the library already returns `ok=False` with
  `"head mismatch (tail truncated/appended or file replaced)"`; the response carries
  both `head` and `expected_head` so the discrepancy is legible.
- `audit_verify` stays read-only (no `confirm=`), so the registry-completeness gate
  (it's in the read-only allow-set) is unaffected.

### A2A skill

`a2a/skills.py:154` registers `audit_verify` with empty args `()`. Thread the single
optional `expected_head: str | None` through so the A2A face has identical
capability — same trust core, no second mutate/verify path. (Adjust the skill's
parameter wiring to pass the arg; verification stays `mutating=False`.)

---

## Feature B — keyed-by-default + auto seal-and-rotate

### Config

```python
audit_keyed: bool = True                 # PROXIMO_AUDIT_KEYED (default on); "off"/"0"/"false" disables
audit_key_path: str | None = None        # PROXIMO_AUDIT_KEY_PATH — explicit override still wins
```

Effective mode resolution (in `open_ledger`):

- `audit_keyed` is **on** by default; `PROXIMO_AUDIT_KEYED` in `("0","false","off","no")`
  turns it off (unkeyed SHA-256 — today's default behavior, now opt-in).
- Key path: explicit `PROXIMO_AUDIT_KEY_PATH` if set, else the **derived default**
  `<dirname(audit_log_path)>/audit.key`.
- If keyed is off → `AuditLedger(path)` (unkeyed). Done.
- If keyed is on → `load_or_create_key(key_path)`, then inspect the log (below).

### Existing-log inspection

A helper reads the log's on-disk mode without trusting per-entry claims blindly — it
peeks the **last** non-empty entry's `alg`:

- file absent/empty → start keyed (the new genesis is keyed). No rotation.
- last entry is keyed (`alg == "hmac-sha256"`) → use as-is (already keyed).
- last entry is unkeyed (no `alg`) → **seal-and-rotate**.

(We trust the file's own `alg` for the *migration* decision only — an attacker who
rewrote the log to strip `alg` could force a needless rotation, but that's within the
already-disclosed same-user-write threat model and is caught by `expected_head`. The
*verification* path keeps its existing rule: the ledger's key is authoritative, never
the entry's `alg`.)

### Seal-and-rotate (atomic, lock-guarded)

Serialized by an exclusive `flock` on a **stable sidecar lock file**
(`<audit_log_path>.lock`) — *not* on the log itself, which gets renamed mid-rotation
(a lock on the log's inode wouldn't serialize a concurrent start that re-opens the
path). After acquiring the sidecar lock, **re-check** the unkeyed condition by
re-opening the log path (double-rotate guard: a racing process that already rotated
leaves a keyed log, so the loser sees keyed and does nothing):

1. Append a terminal `audit_rotate` entry to the **old** (unkeyed) log — chains
   validly as a normal unkeyed entry; `detail={"reason": "keyed-default upgrade",
   "sealed": true}`. Capture the resulting head `H`.
2. **Rename** the old log → `audit.log.unkeyed-<UTC:YYYYMMDDTHHMMSSZ>-<H[:8]>`
   (archive — **never delete**; the old chain stays independently verifiable as an
   unkeyed ledger).
3. Start the new keyed log; its first recorded action is an `audit_rotate` genesis
   entry with `detail={"prev_log": <archive_basename>, "prev_head": H,
   "prev_alg": "sha256"}` — a cryptographic chain-of-custody seam linking new→old.
4. `warn()` loudly (same channel as the other honest startup warnings) naming the
   archive path and `H`.

The archive lands beside the active log. Idempotent: a second start sees a keyed log
and does nothing.

### Fail-closed on key-gen failure

If keyed is on (default) and the key can't be created/loaded (e.g. read-only FS,
permission error), `open_ledger` **raises** with the exact remedy:
`"cannot create audit key at <path>: <err>; set PROXIMO_AUDIT_KEYED=off to run an
unkeyed ledger"`. We never silently fall back to unkeyed — a silent downgrade of the
PROVE pillar is precisely the failure mode the spine exists to prevent.

---

## Data flow

```
server._svc()
  └─ open_ledger(cfg)
       ├─ keyed off?  → AuditLedger(log)                    [unkeyed]
       └─ keyed on
            ├─ key = load_or_create_key(key_path)           [fail-loud on error]
            ├─ inspect(log).mode
            │    ├─ empty/keyed → AuditLedger(log, key=key)
            │    └─ unkeyed     → seal_and_rotate(log, key) ; AuditLedger(log, key=key)
            └─ return ledger
  └─ audit_verify(expected_head?) → verify(pin) → {ok, head, expected_head, …}
```

## Error handling summary

| Condition | Behavior |
|---|---|
| `PROXIMO_AUDIT_EXPECTED_HEAD` malformed (not 64-hex) | fail loud at config load |
| `expected_head` mismatch at verify | `ok=False`, reason + both heads (result, not exception) |
| key-gen/load failure while keyed-on | raise with `…=off` remedy (no silent downgrade) |
| existing keyed log, key missing | existing fail-closed behavior (verify rejects; load raises) |
| concurrent first-run rotation | sidecar-lockfile flock + post-lock re-check → exactly one rotation |

---

## Testing (all TDD — watch each fail first)

**`audit.py` factory + rotation:**
- mode resolution: keyed-default-on; `…_KEYED=off`; explicit `…_KEY_PATH`; derived
  default key path; empty log → keyed genesis; existing keyed → kept; existing unkeyed
  → rotates.
- seal-and-rotate: old log gets the terminal `sealed` entry and still `verify()`s as a
  valid unkeyed chain; archive filename shape (`unkeyed-<stamp>-<H8>`); new keyed log's
  genesis records `prev_log`/`prev_head=H`; new log `verify()`s keyed.
- idempotency: second `open_ledger` on a keyed log does nothing; double-rotate guard
  (simulate the post-lock re-check).
- fail-closed: unwritable key path while keyed-on raises with the `=off` remedy.

**Tool / A2A:**
- `audit_verify(expected_head=X)` match → `ok=True`; mismatch → `ok=False` + reason +
  `head`≠`expected_head`.
- config default used when param omitted; explicit param overrides config default.
- response shape includes `expected_head`; `expected_head: null` when unpinned.
- A2A skill passes the arg through and stays `mutating=False`.

**Security (the point of the feature):**
- tail-truncate a verified log → caught **only** when `expected_head` is pinned.
- forged-append + full-wipe → caught with `expected_head`.
- stripped-`alg` downgrade of a keyed log → verification still fails (key authoritative)
  and/or caught by `expected_head`.

**Regression:** unkeyed behavior intact under `…_KEYED=off`; registry-completeness gate
still passes (`audit_verify` read-only); full suite stays green (2,500+).

---

## Docs to update (part of the work, not after)

- `audit.py` module docstring — keyed is now the default; document seal-and-rotate and
  the archive naming.
- `CLAUDE.md` trust-spine note — PROVE now keyed-by-default + head-pinning available.
- `packaging/proximo.env.example` — `PROXIMO_AUDIT_KEYED`, `PROXIMO_AUDIT_EXPECTED_HEAD`
  (with the "pin off-box" note).
- `README` — correct the PROVE scorecard to match reality (head-pinning ships; keyed
  default) while keeping the "tamper-evident, not tamper-proof / off-box anchor is the
  strong guarantee" honesty.
- `CHANGELOG.md` — feature entry under the next version.

## Out of scope / future

- An off-box head-publishing helper (push `head()` to a remote on each mutation).
- Keyed-ledger key rotation.
- A `pve_doctor` line surfacing PROVE mode + whether a head is pinned (nice follow-up).
