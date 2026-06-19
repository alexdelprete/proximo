# Spec: Signed Agent Cards (SIGNET)

- **Date:** 2026-06-19
- **Status:** Implemented (TDD + 3-lens adversarial redteam; all findings fixed).
- **Surface:** A2A face only (`src/proximo/a2a/`).

## Why

A2A v1.0 (March 2026) added **cryptographically signed Agent Cards** (JWS over the card, RFC 7515).
Without it, an A2A client discovers Proximo's card over plain HTTP and *trusts whatever it reads* —
name, skills, and the RPC URL it should send privileged ops to. Nothing proves the card is the one the
operator published; a MITM or a rogue registry entry can swap the RPC URL and harvest the bearer token.

Signing closes that — **for a client that pins the operator's key out-of-band and requires a valid
signature** (see *Client verification*). It is **PROVE applied to the front door**: the operator
presses a cryptographic seal into the card, and a pinning client verifies the seal before trusting it.
This is:

1. **On-brand** — the same trust thesis as the PROVE ledger, extended to discovery.
2. **Ahead of the field** — no comparable Proxmox-MCP server is even on A2A, let alone signing.
3. **On the newest protocol surface** — A2A v1.0 just shipped this; `a2a-sdk` 1.1.0 ships the helpers.

## What gets built

ES256 (ECDSA P-256) JWS signatures over Proximo's Agent Card, **opt-in** via an operator key, with the
public key published as a JWKS so pinning clients can verify.

- **Sign** through the SDK's `a2a.utils.signing.create_agent_card_signer` (so canonicalization, RFC 8785
  JCS, matches every compliant verifier — zero JCS-mismatch risk).
- **Publish** the public key at `GET /.well-known/jwks.json`; the signature's `kid`+`jku` point there.
- **Verify** with a **strict ES256-only allowlist**, pinned to a single trusted key.

## Design decisions

| Fork | Decision | Why |
|---|---|---|
| Algorithm | **ES256** (ECDSA P-256), asymmetric | Spec's primary example; universal JOSE interop; the seal is worthless if clients can't verify it. NOT Ed25519 (less universal in JOSE verifiers). **NEVER HS256** — see footgun. |
| Pubkey distribution | **JWKS at `/.well-known/jwks.json`** + `kid` + `jku` | Standard publication for clients to obtain and pin the key. |
| Trust anchor | Operator pubkey, **pinned out-of-band** (TOFU / SSH-host-key model) | Honest: signing proves *integrity + continuity under a known key*, not *identity from nothing*. A self-served JWKS does NOT authenticate the operator — the pin does. |
| Opt-in | Sign **only if** `PROXIMO_A2A_SIGNING_KEY_FILE` is set; else unsigned card | Backward compatible; mirrors the existing bearer-token opt-in (`secured=`). Fails LOUD if the var is set but the key is bad. |

## The footgun we defend against (load-bearing)

`a2a.utils.signing.create_agent_card_signer` **defaults `alg` to `HS256`** when the protected header
omits it. HS256 is *symmetric* — the "private key" becomes a shared secret. Worse, if a verifier's
algorithm allowlist contains HS256, an attacker who knows the **public** key can sign a forged card
using that public key as the HMAC secret (classic JWT **algorithm-confusion**).

Defenses, both enforced by test:
1. **Signer** always sets `alg='ES256'` explicitly — never relies on the default.
2. **Verifier** allowlist is `['ES256']` **only** — HS256/symmetric (and `alg:none`/`alg:""`) are
   structurally refused before any key handling.

## Client verification (required for the guarantee)

The signature only buys trust if the client does all three:

1. **Pin the operator key out-of-band.** Obtain the operator's public JWK through a trusted channel
   (TOFU on first contact, a pinned thumbprint, a side channel) — **NOT** by following the card's `jku`.
2. **Ignore card-supplied `kid`/`jku` for key selection.** Use `verifier_for_jwk(pinned_jwk)`, which
   binds to the pinned key and ignores whatever `kid`/`jku` a card presents. A MITM who re-signs a
   forged card with their own key (and points `jku` at their own JWKS) is then refused — the foreign
   signature does not verify under the pinned key.
3. **Require a signature.** Treat an unsigned / signature-stripped card as a failure, not a fallback —
   otherwise a MITM strips the seal and serves a plain card (downgrade). Verifying-if-present is not
   enough; the pinned key must be *required*.

A client that fetches the verification key from the card's own `jku` gains nothing against a MITM (the
attacker controls the card, hence the `jku`). The shipped `verifier_for_jwk` / `make_verifier` are
pinned by construction; the client examples in the tests use the pinned pattern.

## Wire format

- Canonicalization: **RFC 8785 (JCS)** via the SDK — `MessageToDict(card)` → drop `signatures` →
  recursively strip empty str/list/dict → `json.dumps(sort_keys=True, separators=(',',':'))`.
- JWS protected header: `{alg: ES256, typ: JOSE, kid: <thumbprint>, jku: <jwks_url>}`.
- `AgentCard.signatures[]` carries `{protected, signature}` (compact JWS split; payload recomputed from
  the canonical card at verify time, per the SDK).

## Config / provisioning

- `PROXIMO_A2A_SIGNING_KEY_FILE` — path to a PEM EC P-256 **private** key. Absent → unsigned card.
- Operator mints the key (their hand, like the bearer token / PVE token):
  `openssl ecparam -name prime256v1 -genkey -noout -out a2a-signing.pem`
- `kid` = RFC 7638 JWK thumbprint of the public key (stable, derived — no separate config).

## Surfaces

- **NEW** `src/proximo/a2a/signing.py` — `OperatorKey`, `load_operator_key`, `sign_card`, `public_jwk`,
  `jwks`, `make_verifier` (operator self-verify), `verifier_for_jwk` (client-side pinned verify).
- `src/proximo/a2a/card.py` — `build_agent_card(..., signing_key=None, jwks_url=None)`: signs if keyed.
- `src/proximo/a2a/app.py` — `_load_signing_key` (env, fail-loud), `_jwks_url`, a `GET
  /.well-known/jwks.json` route (open, like the card), `signing_key` threaded through `build_app`/`main`.
- `pyproject.toml` — `[a2a]`/`dev` extras use `a2a-sdk[signing]` + `cryptography` (declared, not
  relied-on-transitively).

## Test plan (TDD order)

1. `load_operator_key` reads EC P-256 PEM + derives `kid`; rejects non-P-256 (fail-closed).
2. `sign_card` attaches an ES256/JOSE seal carrying `kid`.
3. Round-trip: sign → verify with operator key → no error.
4. **Tamper:** mutate a top-level field → reject; mutate the nested `supported_interfaces[0].url`
   (the headline threat) → reject.
5. **Alg-confusion:** ES256-only verifier refuses an HS256 seal.
6. Opt-in: no key → `card.signatures` empty.
7. `public_jwk` emits `crv/x/y/kid`, **no private `d`**; `jwks` wraps it.
8. `build_agent_card(signing_key=...)` signs; app serves the JWKS + a sealed card; no key → 404/unsigned.
9. **Key substitution (MITM):** a foreign-key seal (+ attacker `jku`) is refused by a pinned client.
10. **E2E:** a real `a2a-sdk` client resolves the served card and pinned-verifies via the JWKS.

## Non-goals (v1, honest scope)

- No key **rotation** endpoint beyond multi-key JWKS (the format supports multiple `keys[]`; we ship
  single-key, rotation is additive).
- No card signing on the **MCP** face (MCP has no card; stdio is local-trust).
- Proximo is the **signer/server**; client verification is shown in tests + documented, not a shipped
  client library.
- The out-of-band pin is **documented, not automated** — we don't pretend a self-served JWKS proves
  identity.

## Build discipline

spec → TDD (Iron Law: failing test first) → 3-lens adversarial redteam (correctness / security:
alg-confusion + key handling + no private-key leak + key-substitution / leak) → full suite green +
ruff + pyright.
