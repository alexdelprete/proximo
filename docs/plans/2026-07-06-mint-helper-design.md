# Proximo `mint` — token-onboarding recipe helper (design)

**Date:** 2026-07-06 · **Status:** design, approved by John · **Sibling:** `proximo doctor`

## Problem

The costliest hour of a Proximo install happens *before* Proximo runs: creating a scoped
credential on the Proxmox product and writing it in the exact shape Proximo reads. Three things
make this a wall, and a real production reviewer plus the author both lost time on it:

1. **Every product's create path differs** — and PDM has no CLI verb at all (tokens are API-only).
2. **The token-file format differs per product** — the `=`-vs-`:`-vs-password trap below. Getting it
   wrong yields a `401` with no hint.
3. **PVE 9.2's `pveum` prints the secret once to a table** — capture it wrong and it's gone; the
   reviewer "lost two secrets before we found `pvesh`".

`proximo doctor` already tells you what to fix *after* you connect. Nothing helps you connect the
first time. `mint` fills exactly that gap and hands off to `doctor`.

## Goal / non-goals

**Goal:** `proximo mint` prints an exact, copy-pasteable runbook to (a) create a least-privilege
credential, (b) write it in the format Proximo reads, (c) grant a scoped role, (d) wire it, and
(e) verify with `doctor`.

**Non-goals — load-bearing:** `mint` does **NOT** call any API, hold any credential, or create
anything itself. It is a **print-only recipe builder**. This is deliberate:
- It fits Proximo's own threat model — a tool that mints its own credentials is the thing the tool
  argues against. The operator runs the privileged act; the secret never touches Proximo.
- It dodges the chicken-and-egg ("you need a token to make a token").
- It is not an MCP tool — it runs before Proximo is wired into any client and never hits the API.

## The per-product facts (the payload)

Formats are authoritative — read from the backends, not guessed:

| Product | Credential | Token-file content (what `PROXIMO_TOKEN_PATH` holds) | Source in code |
|---|---|---|---|
| **PVE** | API token | `user@realm!name`**`=`**`SECRET` | `backends.py` → `PVEAPIToken={file}` |
| **PBS** | API token | `user@realm!name`**`:`**`SECRET` | `pbs.py` → `PBSAPIToken={file}` |
| **PDM** | API token | `name`**`:`**`SECRET` (space-separated header) | `pdm.py` → `PDMAPIToken {file}` |
| **PMG** | **password** | plain password (via `PROXIMO_PMG_PASSWORD_PATH`) | `pmg.py` → ticket auth, no token |

Create paths, per product:
- **PVE:** `pvesh create /access/users/<user>/token/<name> --privsep 1 --output-format json` — the
  robust capture (JSON, `.value` piped straight to the file). `pveum user token add` is the
  alternative but prints-once to a table (the reviewer's trap); `mint` leads with the `pvesh` form.
- **PBS:** `proxmox-backup-manager user generate-token <user> <name> --output-format json`.
- **PDM:** **no CLI verb** — a REST recipe: `POST /api2/json/access/users/<user>/token/<name>` with a
  root ticket (cookie auth: `POST /access/ticket` returns the ticket as an HttpOnly cookie in PDM
  1.1). `mint` prints the `curl` recipe capturing `.data.value` to the file.
- **PMG:** no token — create a dedicated PMG user and set its password; write the password to the
  `PROXIMO_PMG_PASSWORD_PATH` file.

Least-privilege roles (read-only default): **PVE** `PVEAuditor`; **PBS** `Audit`; **PDM** `Auditor`;
**PMG** a read role on the needed scope. The `--write` flag prints the scoped write grant instead.

**Two gotchas `mint` must bake in (both learned the hard way):**
- **PDM tokens are always privilege-separated** — effective perms = *user ∩ token*. Granting only the
  token a role leaves it capped at the user's role. `mint`'s PDM recipe grants the **user** the role
  too (and says why).
- **PVE `--privsep 1`** tokens need their own ACL entry; `mint` grants the **token's** auth-id
  directly so the token is independently scoped (least-privilege, multiple tokens per user).

## CLI

```
proximo mint [--product pve|pbs|pmg|pdm] [--user USER@REALM] [--token-name NAME]
             [--token-file PATH] [--write] [--json]
```
Defaults: `--product pve`; `--user` defaults **per product** to `proximo@<realm>` (pve→`proximo@pve`,
pbs→`proximo@pbs`, pmg→`proximo@pmg`, pdm→`proximo@pdm`); `--token-name mcp`;
`--token-file ~/.config/proximo/<product>.token`. Parses in `server.py main()` next to the `doctor`
branch; prints and exits (never starts the server).

## Output contract — the five steps

Each step is emitted as a titled block (text) or an object (`--json`, mirroring `doctor`):
1. **create** — the exact create command, capturing the secret straight into `--token-file` (never
   echoed to a terminal). PDM = the REST recipe; PMG = create-user + password.
2. **write** — the exact file content shape for that product (`=` / `:` / password) + `chmod 600`.
   For the token products the create step already writes the file; this step states the format so an
   operator who minted by hand can fix a wrong separator.
3. **grant** — read-only role ACL command by default; the scoped write grant under `--write`.
   Includes the PDM user-grant and PVE token-grant notes above.
4. **wire** — `export PROXIMO_TOKEN_PATH=<file>` (+ `PROXIMO_API_BASE_URL`/`PROXIMO_NODE`), or the
   equivalent `[targets.<name>]` TOML block.
5. **verify** — `proximo doctor` (or `--target <name>`): the hand-off. Doctor then reports the exact
   ACL grant for each capability still missing — mint (read-only) → doctor (what to grant) is the arc.

## Structure

- `src/proximo/mint.py` — pure recipe-builder: `build_recipe(product, user, token_name, token_file,
  write) -> Recipe` returning ordered steps. No I/O, no host, no env. One product = one small builder;
  a dispatch picks by product. Fully unit-testable.
- `src/proximo/server.py` `main()` — the `mint` subcommand: parse flags → `build_recipe(...)` →
  render (text or `--json`). ~parallels the `doctor` branch.
- No MCP tool, no backend, no network.

## Testing (TDD, no live host)

Per product, assert the built recipe:
- carries the correct **create** command (PDM = REST recipe, PMG = user+password, not a token);
- states the correct **file-format separator** (`=` for PVE, `:` for PBS/PDM, password for PMG) —
  this is the regression guard for the exact bug that motivated the helper;
- defaults to the **read-only role**, and `--write` swaps in the **write grant**;
- includes the **PDM user-grant** note when product=pdm;
- ends with the **`proximo doctor`** verify step;
- `--json` emits the steps as structured data with stable keys.
Plus: unknown `--product` errors listing the valid set; default `--token-file` path per product.

## Security posture (stated straight)

Print-only: no API call, no credential handled by Proximo, nothing created by the tool. The recipe
captures the secret directly into a `600` file (never a terminal echo that lands in scrollback).
Read-only by default; write is an explicit opt-in that pairs with the soak posture. Honest about the
two products that don't fit the token mold (PMG = password, PDM = no CLI). Nothing here weakens the
trust spine; it only shortens the distance to a correctly-scoped credential.
