# `proximo mint` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `proximo mint` — a print-only token-onboarding recipe builder (sibling to `proximo doctor`) that prints the exact 5-step runbook (create → write → grant → wire → verify) for a least-privilege credential per Proxmox product.

**Architecture:** A pure, host-free recipe-builder module `src/proximo/mint.py` (`build_recipe(...) -> Recipe`, one small builder per product, dispatch by product) plus a `mint` subcommand branch in `server.py main()` next to the `doctor` branch. No API calls, no credential handling, no MCP tool, no network — deliberate non-goals from the approved spec `docs/plans/2026-07-06-mint-helper-design.md`.

**Tech Stack:** Python (stdlib only — `typing.TypedDict`, `argparse`, `json`), pytest. Runs inside proximo's own uv venv.

## Global Constraints

- **Spec is approved and locked** (`docs/plans/2026-07-06-mint-helper-design.md`, commit `78e1c14`) — do not re-litigate design. Two additive deviations are sanctioned by this plan (verified against the code this session): (a) PBS/PDM/PMG verify steps lead with a direct credential auth-smoke because the `proximo doctor` CLI probes **PVE only** (`doctor.py` has no pbs/pmg/pdm path) — doctor is still referenced in every verify step, preserving the mint→doctor arc; (b) PMG's wire step exports `PROXIMO_PMG_USERNAME` because its default is `root@pam` (`pmg.py:203`).
- **This repo is PUBLIC.** No internal IPs, hostnames, org names, or `/root/...` paths in any tracked file. Recipes use `<pve-host>` / `<pbs-host>` / `<pmg-host>` / `<pdm-host>` placeholders. Test sentinels must be low-entropy (all-lowercase, hyphenated).
- **Token-file formats are load-bearing** (the exact bug that motivated the helper): PVE `user@realm!name=SECRET` (`=`), PBS `user@realm!name:SECRET` (`:`), PDM `user@realm!name:SECRET` (`:`, header space-separated), PMG plain password (no token exists). Sources: `backends.py:275`, `pbs.py:243`, `pdm.py:278`, `pmg.py:202`.
- **Roles:** read-only default / `--write` swap — PVE `PVEAuditor`→`PVEVMAdmin`; PBS `Audit`→`DatastoreAdmin`; PDM `Auditor`→`Administrator`; PMG `audit`→`admin`.
- **Two baked-in gotchas:** PDM tokens are ALWAYS privilege-separated (effective = user ∩ token → grant the USER too); PVE `--privsep 1` tokens need their own ACL (grant the token's auth-id directly).
- Commands: `uv run python -m pytest tests/test_mint.py -q` (fast loop), `uv run python -m pytest -q` (full suite, expect 5,269+ green), `uv run ruff check src tests`, `uv run pyright`.
- Work on branch **`feat/pdm-fleet-control`** (the mint spec already lives there). Commit per task. **Never push** — public push/merge is John's `!` hand.
- **No version bump** — feature rides the next deliberate release. CHANGELOG gets an Unreleased entry only.
- No new MCP tool → the 364 tool count and the LobeHub manifest are untouched.

## File Structure

- `src/proximo/mint.py` (create) — `Step`/`Recipe` TypedDicts, `PRODUCTS`, role tables, `_step()` helper, four product builders (`_pve_steps`, `_pbs_steps`, `_pdm_steps`, `_pmg_steps`), `build_recipe()` dispatch, `render_text()`. Pure: no I/O, no env, no host.
- `src/proximo/server.py` (modify, `main()` ~line 936) — the `mint` subcommand branch, directly after the `doctor` branch, before `print(BANNER, ...)`.
- `tests/test_mint.py` (create) — builder + renderer unit tests.
- `tests/test_main_module.py` (modify) — CLI subcommand tests (mirrors the existing doctor CLI test at line 14).
- `README.md`, `SETUP.md`, `CHANGELOG.md` (modify) — one-pointer ripple.

---

### Task 1: mint.py skeleton + PVE builder

**Files:**
- Create: `src/proximo/mint.py`
- Test: `tests/test_mint.py`

**Interfaces:**
- Produces: `build_recipe(product: str = "pve", user: str | None = None, token_name: str = "mcp", token_file: str | None = None, write: bool = False) -> Recipe`; `Recipe` TypedDict with keys `product, user, token_name, token_file, write, steps`; `Step` TypedDict with keys `key, title, commands, notes`; `PRODUCTS = ("pve", "pbs", "pmg", "pdm")`. Step keys are always exactly `["create", "write", "grant", "wire", "verify"]` in order.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mint.py`:

```python
"""MINT — the print-only onboarding recipe builder (see docs/plans/2026-07-06-mint-helper-design.md).

Pure-unit: no live host, no env, no I/O. The file-format separator assertions (= / : / password)
are the regression guard for the exact bug that motivated the helper — a wrong separator
yields a bare 401 with no hint.
"""

import pytest

from proximo.mint import PRODUCTS, build_recipe

STEP_KEYS = ["create", "write", "grant", "wire", "verify"]


def _step(recipe, key):
    return next(s for s in recipe["steps"] if s["key"] == key)


def _commands(recipe, key):
    return "\n".join(_step(recipe, key)["commands"])


def _notes(recipe, key):
    return "\n".join(_step(recipe, key)["notes"])


# ---------------------------------------------------------------- shape

def test_recipe_shape_and_step_order():
    r = build_recipe("pve")
    assert r["product"] == "pve"
    assert r["user"] == "proximo@pve"
    assert r["token_name"] == "mcp"
    assert r["token_file"] == "~/.config/proximo/pve.token"
    assert r["write"] is False
    assert [s["key"] for s in r["steps"]] == STEP_KEYS


def test_unknown_product_errors_listing_valid_set():
    with pytest.raises(ValueError, match="unknown product"):
        build_recipe("esx")
    with pytest.raises(ValueError, match="pve, pbs, pmg, pdm"):
        build_recipe("esx")


def test_custom_args_propagate():
    r = build_recipe("pve", user="ops@pam", token_name="agent",
                     token_file="/etc/proximo/edge.token")
    assert r["user"] == "ops@pam"
    assert "ops@pam!agent" in _commands(r, "create")
    assert "/etc/proximo/edge.token" in _commands(r, "create")


# ---------------------------------------------------------------- pve

def test_pve_create_leads_with_pvesh_json_capture():
    c = _commands(build_recipe("pve"), "create")
    assert "pvesh create /access/users/proximo@pve/token/mcp --privsep 1 --output-format json" in c
    assert "> ~/.config/proximo/pve.token" in c        # secret straight to the file
    assert "umask 177" in c
    # pveum token add prints-once (the reviewer's trap) — mint must NOT lead with it
    assert "pveum user token add" not in c


def test_pve_file_format_is_equals_separator():
    r = build_recipe("pve")
    assert "proximo@pve!mcp=" in _commands(r, "create")   # the capture writes authid=SECRET
    assert "proximo@pve!mcp=SECRET" in _notes(r, "write")  # the format is stated for hand-minters
    assert "chmod 600" in _commands(r, "write")


def test_pve_grant_defaults_read_only_token_acl():
    c = _commands(build_recipe("pve"), "grant")
    assert "pveum acl modify / --tokens 'proximo@pve!mcp' --roles PVEAuditor" in c
    # privsep gotcha: the token's OWN acl, said out loud
    assert "own acl" in _notes(build_recipe("pve"), "grant").lower()


def test_pve_write_flag_swaps_grant():
    r = build_recipe("pve", write=True)
    c = _commands(r, "grant")
    assert "PVEVMAdmin" in c
    assert "PVEAuditor" not in c
    assert r["write"] is True


def test_pve_wire_env_triple():
    c = _commands(build_recipe("pve"), "wire")
    assert "PROXIMO_API_BASE_URL" in c
    assert "PROXIMO_NODE" in c
    assert "PROXIMO_TOKEN_PATH=~/.config/proximo/pve.token" in c
    assert 'kind = "pve"' in c                          # the targets-registry alternative


def test_pve_verify_is_doctor():
    c = _commands(build_recipe("pve"), "verify")
    assert "proximo doctor" in c
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_mint.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'proximo.mint'`

- [ ] **Step 3: Write the implementation**

Create `src/proximo/mint.py`:

```python
"""MINT — print-only token-onboarding recipes: the exact runbook from zero to a scoped credential.

`proximo mint` prints the five steps (create → write → grant → wire → verify) that take an
operator from a bare Proxmox product to a least-privilege credential Proximo can read.
Load-bearing non-goals: mint makes NO API call, holds NO credential, and creates NOTHING
itself — the operator runs the privileged act; the secret never touches Proximo. Not an MCP
tool: it runs before Proximo is wired into any client, then hands off to `proximo doctor`.

Per-product credential shapes (authoritative — mirrors the backends; the =/:/password trap):
    PVE  token file  USER@REALM!NAME=SECRET   backends.py → Authorization: PVEAPIToken={file}
    PBS  token file  USER@REALM!NAME:SECRET   pbs.py      → Authorization: PBSAPIToken={file}
    PDM  token file  USER@REALM!NAME:SECRET   pdm.py      → Authorization: PDMAPIToken {file}
    PMG  password    the password, one line   pmg.py      → ticket auth (PMG has no API tokens)

Two gotchas baked into the recipes (both learned against live hosts, 2026-07-06):
    - PDM tokens are ALWAYS privilege-separated: effective perms = user ∩ token — the PDM
      grant step grants the USER the role too, or the token stays capped at the user's role.
    - PVE `--privsep 1` tokens carry their OWN ACL — the grant targets the token's auth-id.
"""

from __future__ import annotations

from typing import TypedDict


class Step(TypedDict):
    key: str            # one of: create, write, grant, wire, verify (stable --json contract)
    title: str
    commands: list[str]  # copy-pasteable; an entry may be a multi-line block
    notes: list[str]


class Recipe(TypedDict):
    product: str
    user: str
    token_name: str
    token_file: str
    write: bool
    steps: list[Step]


PRODUCTS: tuple[str, ...] = ("pve", "pbs", "pmg", "pdm")

# Least-privilege roles: read-only by default; --write swaps in the scoped write grant.
_READ_ROLE = {"pve": "PVEAuditor", "pbs": "Audit", "pdm": "Auditor", "pmg": "audit"}
_WRITE_ROLE = {"pve": "PVEVMAdmin", "pbs": "DatastoreAdmin", "pdm": "Administrator", "pmg": "admin"}

_SEPARATOR_HINT = "Minted by hand and seeing 401? Check the separator: PVE '=', PBS/PDM ':'."


def _step(key: str, title: str, commands: list[str], notes: list[str]) -> Step:
    return {"key": key, "title": title, "commands": commands, "notes": notes}


def _pve_steps(user: str, token_name: str, token_file: str, write: bool) -> list[Step]:
    authid = f"{user}!{token_name}"
    role = _WRITE_ROLE["pve"] if write else _READ_ROLE["pve"]
    acl_path = "/vms" if write else "/"
    grant_notes = [
        "--privsep 1 tokens carry their OWN ACL — grant the token's auth-id directly; "
        "granting only the user does not empower the token.",
    ]
    if write:
        grant_notes.append(
            "Scope the write grant deliberately: /vms/<vmid> for one guest, /vms for all guests."
        )
    create_block = "\n".join([
        f"pveum user add {user} --comment 'Proximo MCP (least-privilege)'"
        "  # skip if the user exists",
        "umask 177",
        f"pvesh create /access/users/{user}/token/{token_name} --privsep 1"
        " --output-format json \\",
        "  | python3 -c 'import json,sys; v=json.load(sys.stdin)[\"value\"]; "
        f"print(\"{authid}=\" + v, end=\"\")' \\",
        f"  > {token_file}",
    ])
    return [
        _step("create", "mint the API token on the PVE host (as root)", [create_block], [
            "pvesh + JSON is the robust capture — `pveum user token add` prints the secret "
            "ONCE to a table and it is gone.",
            "The secret lands straight in the file; it is never echoed to the terminal.",
        ]),
        _step("write", "token-file format (what PROXIMO_TOKEN_PATH must hold)",
              [f"chmod 600 {token_file}"], [
            f"Exactly one line: {authid}=SECRET — PVE uses '=' between token-id and secret.",
            _SEPARATOR_HINT,
        ]),
        _step("grant", f"grant the {'scoped write' if write else 'read-only'} role to the token",
              [f"pveum acl modify {acl_path} --tokens '{authid}' --roles {role}"], grant_notes),
        _step("wire", "point Proximo at the host (env, or the targets registry)", [
            "export PROXIMO_API_BASE_URL=https://<pve-host>:8006/api2/json",
            "export PROXIMO_NODE=<node-name>",
            f"export PROXIMO_TOKEN_PATH={token_file}",
            "\n".join([
                "# or, as a named target in the PROXIMO_TARGETS registry (TOML):",
                "[targets.<name>]",
                'kind = "pve"',
                'base_url = "https://<pve-host>:8006/api2/json"',
                'node = "<node-name>"',
                f'token_path = "{token_file}"',
            ]),
        ], []),
        _step("verify", "prove the boundary before any AI sees it",
              ["proximo doctor        # or: proximo doctor --target <name>"], [
            "doctor prints what this token CAN and CANNOT do, and the exact grant "
            "for each capability still missing.",
        ]),
    ]


_BUILDERS = {
    "pve": _pve_steps,
}


def build_recipe(
    product: str = "pve",
    user: str | None = None,
    token_name: str = "mcp",
    token_file: str | None = None,
    write: bool = False,
) -> Recipe:
    """Build the 5-step onboarding recipe for one product. Pure — no I/O, no env, no host."""
    if product not in PRODUCTS:
        raise ValueError(
            f"unknown product {product!r} — valid: {', '.join(PRODUCTS)}"
        )
    resolved_user = user or f"proximo@{product}"
    resolved_file = token_file or f"~/.config/proximo/{product}.token"
    steps = _BUILDERS[product](resolved_user, token_name, resolved_file, write)
    return {
        "product": product,
        "user": resolved_user,
        "token_name": token_name,
        "token_file": resolved_file,
        "write": write,
        "steps": steps,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_mint.py -q`
Expected: all PASS (9 tests). Note: `build_recipe("pbs")` would KeyError until Task 2 — no test touches it yet; the dispatch fills in over Tasks 2–4.

- [ ] **Step 5: Commit**

```bash
git add src/proximo/mint.py tests/test_mint.py
git commit -m "feat(mint): recipe skeleton + the PVE onboarding builder"
```

---

### Task 2: PBS builder

**Files:**
- Modify: `src/proximo/mint.py` (add `_pbs_steps`, register in `_BUILDERS`)
- Test: `tests/test_mint.py` (append)

**Interfaces:**
- Consumes: `_step()`, `_READ_ROLE`/`_WRITE_ROLE`, `_SEPARATOR_HINT`, `_BUILDERS` from Task 1.
- Produces: `build_recipe("pbs")` works end-to-end.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_mint.py`)

```python
# ---------------------------------------------------------------- pbs

def test_pbs_create_uses_generate_token_json_capture():
    c = _commands(build_recipe("pbs"), "create")
    assert ("proxmox-backup-manager user generate-token proximo@pbs mcp"
            " --output-format json") in c
    assert "proxmox-backup-manager user create proximo@pbs" in c
    assert "> ~/.config/proximo/pbs.token" in c
    assert "umask 177" in c


def test_pbs_file_format_is_colon_separator():
    r = build_recipe("pbs")
    assert "proximo@pbs!mcp:" in _commands(r, "create")
    assert "proximo@pbs!mcp:SECRET" in _notes(r, "write")
    assert "proximo@pbs!mcp=" not in _commands(r, "create")   # the PVE '=' trap must NOT leak in
    assert "chmod 600" in _commands(r, "write")


def test_pbs_grant_defaults_read_only_and_write_swaps():
    ro = _commands(build_recipe("pbs"), "grant")
    assert "proxmox-backup-manager acl update / Audit --auth-id 'proximo@pbs!mcp'" in ro
    rw = _commands(build_recipe("pbs", write=True), "grant")
    assert "DatastoreAdmin" in rw
    assert " Audit " not in rw


def test_pbs_wire_env():
    c = _commands(build_recipe("pbs"), "wire")
    assert "PROXIMO_PBS_BASE_URL=https://<pbs-host>:8007/api2/json" in c
    assert "PROXIMO_PBS_TOKEN_PATH=~/.config/proximo/pbs.token" in c
    assert 'kind = "pbs"' in c


def test_pbs_verify_auth_smoke_then_doctor():
    r = build_recipe("pbs")
    c = _commands(r, "verify")
    assert "PBSAPIToken=$(cat ~/.config/proximo/pbs.token)" in c
    assert "/api2/json/version" in c
    assert "doctor" in (c + _notes(r, "verify"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_mint.py -q -k pbs`
Expected: FAIL — `KeyError: 'pbs'` (builder not registered)

- [ ] **Step 3: Write the implementation** (add to `src/proximo/mint.py` after `_pve_steps`; register in `_BUILDERS`)

```python
def _pbs_steps(user: str, token_name: str, token_file: str, write: bool) -> list[Step]:
    authid = f"{user}!{token_name}"
    role = _WRITE_ROLE["pbs"] if write else _READ_ROLE["pbs"]
    acl_path = "/datastore" if write else "/"
    grant_notes = ["PBS token ACLs are separate from the user's — grant the token's auth-id."]
    if write:
        grant_notes.append(
            "Scope the write grant deliberately: /datastore/<store> for one datastore."
        )
    create_block = "\n".join([
        f"proxmox-backup-manager user create {user}  # skip if the user exists",
        "umask 177",
        f"proxmox-backup-manager user generate-token {user} {token_name}"
        " --output-format json \\",
        "  | python3 -c 'import json,sys; v=json.load(sys.stdin)[\"value\"]; "
        f"print(\"{authid}:\" + v, end=\"\")' \\",
        f"  > {token_file}",
    ])
    return [
        _step("create", "mint the API token on the PBS host (as root)", [create_block], [
            "The secret lands straight in the file; it is never echoed to the terminal.",
        ]),
        _step("write", "token-file format (what PROXIMO_PBS_TOKEN_PATH must hold)",
              [f"chmod 600 {token_file}"], [
            f"Exactly one line: {authid}:SECRET — PBS uses ':' (colon), NOT the PVE '='.",
            _SEPARATOR_HINT,
        ]),
        _step("grant", f"grant the {'scoped write' if write else 'read-only'} role to the token",
              [f"proxmox-backup-manager acl update {acl_path} {role} --auth-id '{authid}'"],
              grant_notes),
        _step("wire", "point Proximo at the host (env, or the targets registry)", [
            "export PROXIMO_PBS_BASE_URL=https://<pbs-host>:8007/api2/json",
            f"export PROXIMO_PBS_TOKEN_PATH={token_file}",
            "\n".join([
                "# or, as a named target in the PROXIMO_TARGETS registry (TOML):",
                "[targets.<name>]",
                'kind = "pbs"',
                'base_url = "https://<pbs-host>:8007/api2/json"',
                f'token_path = "{token_file}"',
            ]),
        ], [
            "Self-signed PBS? Point PROXIMO_PBS_CA_BUNDLE at its CA, or pin the cert with "
            "PROXIMO_PBS_FINGERPRINT — don't disable TLS verification.",
        ]),
        _step("verify", "prove the token authenticates, then hand off to doctor", [
            "curl -sk --fail"
            f" -H \"Authorization: PBSAPIToken=$(cat {token_file})\" \\\n"
            "  https://<pbs-host>:8007/api2/json/version",
        ], [
            "A version JSON back = the token authenticates (-k here is an auth smoke, not a "
            "trust decision — Proximo itself validates or pins TLS via the wire step).",
            "`proximo doctor` verifies the PVE core config; once wired, the pbs_* tools "
            "fail loudly naming any missing PBS env.",
        ]),
    ]
```

And extend the dispatch:

```python
_BUILDERS = {
    "pve": _pve_steps,
    "pbs": _pbs_steps,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_mint.py -q`
Expected: all PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add src/proximo/mint.py tests/test_mint.py
git commit -m "feat(mint): PBS onboarding builder (colon separator, Audit default)"
```

---

### Task 3: PDM builder (REST recipe + the user∩token gotcha)

**Files:**
- Modify: `src/proximo/mint.py` (add `_pdm_steps`, register in `_BUILDERS`)
- Test: `tests/test_mint.py` (append)

**Interfaces:**
- Consumes: same helpers as Task 2.
- Produces: `build_recipe("pdm")` works end-to-end.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_mint.py`)

```python
# ---------------------------------------------------------------- pdm

def test_pdm_create_is_a_rest_recipe_with_cookie_jar():
    c = _commands(build_recipe("pdm"), "create")
    assert "https://<pdm-host>:8443/api2/json/access/ticket" in c
    assert "-c /tmp/proximo-pdm.cookie" in c                      # PDM 1.1: ticket = HttpOnly cookie
    assert "CSRFPreventionToken" in c
    assert "/access/users/proximo@pdm/token/mcp" in c
    assert "read -rsp" in c                                       # root password never in argv/history
    assert "pveum" not in c                                       # no CLI verb exists — REST only
    assert "umask 177" in c


def test_pdm_file_format_is_colon_separator():
    r = build_recipe("pdm")
    assert "proximo@pdm!mcp:" in _commands(r, "create")
    assert "proximo@pdm!mcp:SECRET" in _notes(r, "write")
    assert "proximo@pdm!mcp=" not in _commands(r, "create")


def test_pdm_grant_covers_token_AND_user():
    r = build_recipe("pdm")
    c = _commands(r, "grant")
    assert "auth-id=proximo@pdm!mcp" in c        # the token's own ACL
    assert "'auth-id=proximo@pdm'" in c          # AND the user's — privsep intersection
    assert "role=Auditor" in c
    notes = _notes(r, "grant").lower()
    assert "privilege-separated" in notes and "user" in notes


def test_pdm_write_flag_swaps_grant():
    c = _commands(build_recipe("pdm", write=True), "grant")
    assert "role=Administrator" in c
    assert "role=Auditor" not in c


def test_pdm_wire_env():
    c = _commands(build_recipe("pdm"), "wire")
    assert "PROXIMO_PDM_BASE_URL=https://<pdm-host>:8443" in c
    assert "PROXIMO_PDM_TOKEN_PATH=~/.config/proximo/pdm.token" in c
    assert 'kind = "pdm"' in c


def test_pdm_verify_space_separated_header_then_doctor():
    r = build_recipe("pdm")
    c = _commands(r, "verify")
    assert "PDMAPIToken $(cat ~/.config/proximo/pdm.token)" in c   # SPACE header, not '='
    assert "doctor" in (c + _notes(r, "verify"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_mint.py -q -k pdm`
Expected: FAIL — `KeyError: 'pdm'`

- [ ] **Step 3: Write the implementation** (add after `_pbs_steps`; register in `_BUILDERS`)

```python
def _pdm_steps(user: str, token_name: str, token_file: str, write: bool) -> list[Step]:
    authid = f"{user}!{token_name}"
    role = _WRITE_ROLE["pdm"] if write else _READ_ROLE["pdm"]
    api = "https://<pdm-host>:8443/api2/json"
    csrf = '-H "CSRFPreventionToken: $CSRF"'
    cookie = "-b /tmp/proximo-pdm.cookie"
    grant_notes = [
        "PDM tokens are ALWAYS privilege-separated: effective permissions = user ∩ token. "
        "The second command grants the USER the role too — skip it and the token stays "
        "capped at the user's role (the silent-403 trap).",
        "The cookie jar is removed here — the bootstrap ticket is gone after the grant.",
    ]
    if write:
        grant_notes.insert(1,
            "PDM's built-in roles are coarse — Administrator is full fleet control; "
            "treat this credential accordingly.")
    create_block = "\n".join([
        "read -rsp 'PDM root password (one bootstrap call — never stored): ' PDM_PASS && echo",
        "CSRF=$(curl -sk -c /tmp/proximo-pdm.cookie -X POST"
        f" {api}/access/ticket \\",
        "  --data-urlencode 'username=root@pam' --data-urlencode \"password=$PDM_PASS\" \\",
        "  | python3 -c 'import json,sys; "
        "print(json.load(sys.stdin)[\"data\"][\"CSRFPreventionToken\"])')",
        "unset PDM_PASS",
        f"curl -sk {cookie} {csrf} -X POST {api}/access/users \\",
        f"  --data-urlencode 'userid={user}'  # skip if the user exists",
        "umask 177",
        f"curl -sk {cookie} {csrf} -X POST {api}/access/users/{user}/token/{token_name} \\",
        "  | python3 -c 'import json,sys; v=json.load(sys.stdin)[\"data\"][\"value\"]; "
        f"print(\"{authid}:\" + v, end=\"\")' \\",
        f"  > {token_file}",
    ])
    grant_block = "\n".join([
        f"curl -sk {cookie} {csrf} -X PUT {api}/access/acl \\",
        f"  --data-urlencode 'auth-id={authid}' --data-urlencode 'path=/' \\",
        f"  --data-urlencode 'role={role}' --data-urlencode 'propagate=true'",
        f"curl -sk {cookie} {csrf} -X PUT {api}/access/acl \\",
        f"  --data-urlencode 'auth-id={user}' --data-urlencode 'path=/' \\",
        f"  --data-urlencode 'role={role}' --data-urlencode 'propagate=true'",
        "rm -f /tmp/proximo-pdm.cookie; unset CSRF",
    ])
    return [
        _step("create", "mint the API token over REST (PDM has no CLI verb for tokens)",
              [create_block], [
            "PDM 1.1 returns the ticket as an HttpOnly COOKIE (not in the JSON body) — "
            "hence the cookie jar. Keep it until the grant step; it is removed there.",
            "The token secret lands straight in the file; it is never echoed to the terminal.",
        ]),
        _step("write", "token-file format (what PROXIMO_PDM_TOKEN_PATH must hold)",
              [f"chmod 600 {token_file}"], [
            f"Exactly one line: {authid}:SECRET — PDM uses ':' (colon), NOT the PVE '='. "
            "The request header is space-separated: `Authorization: PDMAPIToken <that line>`.",
            _SEPARATOR_HINT,
        ]),
        _step("grant", f"grant the {'write' if write else 'read-only'} role to the token"
              " AND the user", [grant_block], grant_notes),
        _step("wire", "point Proximo at the host (env, or the targets registry)", [
            "export PROXIMO_PDM_BASE_URL=https://<pdm-host>:8443"
            "   # /api2/json is appended automatically",
            f"export PROXIMO_PDM_TOKEN_PATH={token_file}",
            "\n".join([
                "# or, as a named target in the PROXIMO_TARGETS registry (TOML):",
                "[targets.<name>]",
                'kind = "pdm"',
                'base_url = "https://<pdm-host>:8443"',
                f'token_path = "{token_file}"',
            ]),
        ], [
            "Self-signed PDM? Point PROXIMO_PDM_CA_BUNDLE at its CA, or pin the cert with "
            "PROXIMO_PDM_FINGERPRINT — don't disable TLS verification.",
        ]),
        _step("verify", "prove the token authenticates, then hand off to doctor", [
            "curl -sk --fail"
            f" -H \"Authorization: PDMAPIToken $(cat {token_file})\" \\\n"
            f"  {api}/version",
        ], [
            "A version JSON back = the token authenticates. Note the SPACE after "
            "PDMAPIToken — not '='.",
            "`proximo doctor` verifies the PVE core config; once wired, pdm_ping is the "
            "cheapest live check and the pdm_* tools fail loudly naming any missing env.",
        ]),
    ]
```

And extend the dispatch:

```python
_BUILDERS = {
    "pve": _pve_steps,
    "pbs": _pbs_steps,
    "pdm": _pdm_steps,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_mint.py -q`
Expected: all PASS (20 tests)

- [ ] **Step 5: Commit**

```bash
git add src/proximo/mint.py tests/test_mint.py
git commit -m "feat(mint): PDM REST onboarding builder (cookie ticket, user∩token grant)"
```

---

### Task 4: PMG builder (password, not token)

**Files:**
- Modify: `src/proximo/mint.py` (add `_pmg_steps`, register in `_BUILDERS`)
- Test: `tests/test_mint.py` (append)

**Interfaces:**
- Consumes: same helpers as Task 2.
- Produces: `build_recipe("pmg")` works end-to-end; `_BUILDERS` now covers all of `PRODUCTS`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_mint.py`)

```python
# ---------------------------------------------------------------- pmg

def test_pmg_create_is_user_plus_password_not_token():
    r = build_recipe("pmg")
    c = _commands(r, "create")
    assert "openssl rand -base64 30 > ~/.config/proximo/pmg.token" in c
    assert "pmgsh create /config/users --userid proximo@pmg" in c
    assert "--password \"$(cat" in c                 # read from the file, never retyped
    assert "token" not in _step(r, "create")["title"].lower()   # PMG has no API tokens
    assert "generate-token" not in c


def test_pmg_write_step_says_password_file():
    r = build_recipe("pmg")
    assert "chmod 600 ~/.config/proximo/pmg.token" in _commands(r, "write")
    notes = _notes(r, "write").lower()
    assert "password" in notes
    assert "no api token" in notes or "no token" in notes


def test_pmg_grant_defaults_audit_and_write_swaps_admin():
    ro = _commands(build_recipe("pmg"), "grant")
    assert "pmgsh set /config/users/proximo@pmg --role audit" in ro
    rw = build_recipe("pmg", write=True)
    assert "--role admin" in _commands(rw, "grant")
    assert "coarse" in _notes(rw, "grant").lower()   # admin = full control, said out loud


def test_pmg_wire_env_includes_username():
    c = _commands(build_recipe("pmg"), "wire")
    assert "PROXIMO_PMG_BASE_URL=https://<pmg-host>:8006/api2/json" in c
    assert "PROXIMO_PMG_PASSWORD_PATH=~/.config/proximo/pmg.token" in c
    assert "PROXIMO_PMG_USERNAME=proximo@pmg" in c   # default is root@pam — must be overridden
    assert 'kind = "pmg"' in c


def test_pmg_verify_ticket_login_then_doctor():
    r = build_recipe("pmg")
    c = _commands(r, "verify")
    assert "/api2/json/access/ticket" in c
    assert "username=proximo@pmg" in c
    assert "doctor" in (c + _notes(r, "verify"))


def test_all_products_have_builders():
    for p in PRODUCTS:
        assert build_recipe(p)["product"] == p
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_mint.py -q -k pmg`
Expected: FAIL — `KeyError: 'pmg'`

- [ ] **Step 3: Write the implementation** (add after `_pdm_steps`; complete `_BUILDERS`)

```python
def _pmg_steps(user: str, token_name: str, token_file: str, write: bool) -> list[Step]:
    # PMG has no API tokens (ticket auth) — the credential IS a user password; token_name unused.
    role = _WRITE_ROLE["pmg"] if write else _READ_ROLE["pmg"]
    grant_notes = [
        "PMG roles are coarse: audit = read-only; admin = FULL control (there is no "
        "scoped-write middle ground). Treat an admin credential accordingly.",
    ]
    create_block = "\n".join([
        "# where Proximo runs — generate the service password (this file IS the credential):",
        "umask 177",
        f"openssl rand -base64 30 > {token_file}",
        "# on the PMG host — create the user with that password"
        " (read from the file, never retyped):",
        f"pmgsh create /config/users --userid {user} --role {role}"
        f" --password \"$(cat {token_file})\"",
    ])
    return [
        _step("create", "create a dedicated PMG service user (PMG has no API tokens)",
              [create_block], [
            "If Proximo and PMG are different machines, move the password file over a "
            "secure channel (scp the 600 file) — never through a chat or transcript.",
        ]),
        _step("write", "password-file format (what PROXIMO_PMG_PASSWORD_PATH must hold)",
              [f"chmod 600 {token_file}"], [
            "Exactly one line: the PMG user's password. PMG has no API token — this file "
            "is wired via PROXIMO_PMG_PASSWORD_PATH, not PROXIMO_TOKEN_PATH.",
        ]),
        _step("grant", f"set the {'write' if write else 'read-only'} role on the user",
              [f"pmgsh set /config/users/{user} --role {role}"], grant_notes),
        _step("wire", "point Proximo at the host (env, or the targets registry)", [
            "export PROXIMO_PMG_BASE_URL=https://<pmg-host>:8006/api2/json",
            f"export PROXIMO_PMG_PASSWORD_PATH={token_file}",
            f"export PROXIMO_PMG_USERNAME={user}"
            "   # the default is root@pam — set this or Proximo logs in as root",
            "\n".join([
                "# or, as a named target in the PROXIMO_TARGETS registry (TOML):",
                "[targets.<name>]",
                'kind = "pmg"',
                'base_url = "https://<pmg-host>:8006/api2/json"',
                f'password_path = "{token_file}"',
                f'username = "{user}"',
            ]),
        ], []),
        _step("verify", "prove the login works, then hand off to doctor", [
            "curl -sk --fail -X POST https://<pmg-host>:8006/api2/json/access/ticket \\\n"
            f"  --data-urlencode 'username={user}'"
            f" --data-urlencode \"password=$(cat {token_file})\"",
        ], [
            "A ticket back = the login works.",
            "`proximo doctor` verifies the PVE core config; once wired, the pmg_doctor "
            "tool runs the full PMG preflight.",
        ]),
    ]
```

And complete the dispatch:

```python
_BUILDERS = {
    "pve": _pve_steps,
    "pbs": _pbs_steps,
    "pdm": _pdm_steps,
    "pmg": _pmg_steps,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_mint.py -q`
Expected: all PASS (26 tests)

- [ ] **Step 5: Commit**

```bash
git add src/proximo/mint.py tests/test_mint.py
git commit -m "feat(mint): PMG onboarding builder (password credential, coarse roles)"
```

---

### Task 5: Cross-product invariants

**Files:**
- Test: `tests/test_mint.py` (append only — implementation exists; these are the spec's contract bullets, asserted across ALL products at once)

**Interfaces:**
- Consumes: `build_recipe`, `PRODUCTS`, `STEP_KEYS` from prior tasks.

- [ ] **Step 1: Write the tests** (append to `tests/test_mint.py`)

```python
# ---------------------------------------------------------------- invariants (all products)

@pytest.mark.parametrize("product", PRODUCTS)
def test_every_recipe_has_the_five_steps_in_order(product):
    r = build_recipe(product)
    assert [s["key"] for s in r["steps"]] == STEP_KEYS
    for s in r["steps"]:
        assert s["title"]
        assert s["commands"]


@pytest.mark.parametrize("product", PRODUCTS)
def test_every_recipe_locks_the_file_to_600(product):
    joined = "\n".join(c for s in build_recipe(product)["steps"] for c in s["commands"])
    assert "chmod 600" in joined or "umask 177" in joined


@pytest.mark.parametrize("product", PRODUCTS)
def test_every_verify_step_hands_off_to_doctor(product):
    s = _step(build_recipe(product), "verify")
    assert "doctor" in "\n".join(s["commands"] + s["notes"])


@pytest.mark.parametrize("product", PRODUCTS)
def test_default_user_and_file_per_product(product):
    r = build_recipe(product)
    assert r["user"] == f"proximo@{product}"
    assert r["token_file"] == f"~/.config/proximo/{product}.token"


@pytest.mark.parametrize("product", PRODUCTS)
def test_no_secret_placeholder_ever_echoes(product):
    """No recipe command prints a captured secret to stdout — capture goes straight to the file."""
    for s in build_recipe(product)["steps"]:
        for c in s["commands"]:
            for line in c.split("\n"):
                if "print(" in line and "value" in line.lower():
                    block = c  # the python -c capture must be piped into a redirect
                    assert "> " in block
```

- [ ] **Step 2: Run tests to verify they pass** (implementation already satisfies them; any failure here is a real Task 1–4 bug — fix the builder, not the test)

Run: `uv run python -m pytest tests/test_mint.py -q`
Expected: all PASS (46 tests)

- [ ] **Step 3: Commit**

```bash
git add tests/test_mint.py
git commit -m "test(mint): cross-product contract invariants (5 steps, 600 file, doctor hand-off)"
```

---

### Task 6: Text renderer

**Files:**
- Modify: `src/proximo/mint.py` (add `render_text`)
- Test: `tests/test_mint.py` (append)

**Interfaces:**
- Produces: `render_text(recipe: Recipe) -> str` — the human output of the CLI's default (non-`--json`) mode.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_mint.py`)

```python
# ---------------------------------------------------------------- renderer

from proximo.mint import render_text  # noqa: E402  (keep imports grouped at top in the real file)


def test_render_text_header_and_numbered_steps():
    out = render_text(build_recipe("pve"))
    assert out.startswith("proximo mint — pve onboarding (read-only)")
    assert "[1/5] create — " in out
    assert "[5/5] verify — " in out


def test_render_text_write_mode_in_header():
    assert "(write)" in render_text(build_recipe("pve", write=True)).splitlines()[0]


def test_render_text_indents_commands_and_prefixes_notes():
    out = render_text(build_recipe("pbs"))
    assert "\n    proxmox-backup-manager user create proximo@pbs" in out
    assert "\n  note: " in out


def test_render_text_indents_every_line_of_multiline_blocks():
    out = render_text(build_recipe("pdm"))
    for line in out.splitlines():
        if "curl -sk" in line:
            assert line.startswith("    ")
```

(Move the `from proximo.mint import render_text` up into the existing import line at the top of the file: `from proximo.mint import PRODUCTS, build_recipe, render_text`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_mint.py -q -k render`
Expected: FAIL — `ImportError: cannot import name 'render_text'`

- [ ] **Step 3: Write the implementation** (add at the bottom of `src/proximo/mint.py`)

```python
def render_text(recipe: Recipe) -> str:
    """Render a recipe as the numbered, copy-pasteable text runbook (the CLI default)."""
    mode = "write" if recipe["write"] else "read-only"
    lines = [
        f"proximo mint — {recipe['product']} onboarding ({mode})",
        f"# user={recipe['user']}  token={recipe['token_name']}  file={recipe['token_file']}",
        "",
    ]
    total = len(recipe["steps"])
    for i, step in enumerate(recipe["steps"], 1):
        lines.append(f"[{i}/{total}] {step['key']} — {step['title']}")
        for command in step["commands"]:
            lines.extend(f"    {line}" for line in command.split("\n"))
        lines.extend(f"  note: {note}" for note in step["notes"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_mint.py -q`
Expected: all PASS (50 tests)

- [ ] **Step 5: Commit**

```bash
git add src/proximo/mint.py tests/test_mint.py
git commit -m "feat(mint): text renderer for the five-step runbook"
```

---

### Task 7: the `mint` CLI subcommand

**Files:**
- Modify: `src/proximo/server.py` — `main()`, insert directly after the `doctor` branch's `return` (line ~935), before `print(BANNER, file=sys.stderr)`
- Test: `tests/test_main_module.py` (append)

**Interfaces:**
- Consumes: `build_recipe`, `render_text`, `PRODUCTS` from `proximo.mint`.
- Produces: `proximo mint [--product ...] [--user ...] [--token-name ...] [--token-file ...] [--write] [--json]` — prints and exits; never starts the server; unknown product → exit code 2 with the valid set on stderr.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_main_module.py`; mirror the doctor CLI test's monkeypatch style at line 14)

```python
def test_main_mint_subcommand_prints_runbook_and_skips_server(monkeypatch, capsys):
    import proximo.server as srv
    ran = {}
    monkeypatch.setattr(srv.sys, "argv", ["proximo", "mint"])
    monkeypatch.setattr(srv.mcp, "run", lambda *a, **k: ran.__setitem__("server", True))
    srv.main()
    out = capsys.readouterr().out
    assert out.startswith("proximo mint — pve onboarding (read-only)")
    assert "[1/5] create — " in out
    assert "server" not in ran            # mint prints and exits — never starts the server


def test_main_mint_json_emits_structured_recipe(monkeypatch, capsys):
    import json

    import proximo.server as srv
    monkeypatch.setattr(srv.sys, "argv",
                        ["proximo", "mint", "--product", "pbs", "--write", "--json"])
    monkeypatch.setattr(srv.mcp, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    srv.main()
    recipe = json.loads(capsys.readouterr().out)   # stdout must be ONLY the JSON
    assert recipe["product"] == "pbs"
    assert recipe["write"] is True
    assert [s["key"] for s in recipe["steps"]] == ["create", "write", "grant", "wire", "verify"]


def test_main_mint_unknown_product_exits_2_with_valid_set(monkeypatch, capsys):
    import pytest

    import proximo.server as srv
    monkeypatch.setattr(srv.sys, "argv", ["proximo", "mint", "--product", "esx"])
    with pytest.raises(SystemExit) as exc:
        srv.main()
    assert exc.value.code == 2
    assert "pve, pbs, pmg, pdm" in capsys.readouterr().err
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_main_module.py -q`
Expected: the 3 new tests FAIL (mint argv falls through to `mcp.run()` → first test's `ran` gets set / second raises AssertionError); the 2 existing tests still PASS.

- [ ] **Step 3: Write the implementation** (insert in `src/proximo/server.py` `main()`, immediately after the doctor branch's `return`)

```python
    # `proximo mint` — print-only onboarding recipe: create → write → grant → wire → verify.
    # Prints the exact runbook for a least-privilege credential per product; makes NO API call,
    # never handles a secret, and never starts the server. Hands off to `proximo doctor`.
    if len(sys.argv) > 1 and sys.argv[1] == "mint":
        import argparse
        import json

        from proximo.mint import PRODUCTS, build_recipe, render_text
        parser = argparse.ArgumentParser(prog="proximo mint")
        parser.add_argument("--product", default="pve",
                            help=f"one of: {', '.join(PRODUCTS)} (default: pve)")
        parser.add_argument("--user", default=None,
                            help="service user (default: proximo@<product-realm>)")
        parser.add_argument("--token-name", default="mcp",
                            help="token name (default: mcp; unused for pmg)")
        parser.add_argument("--token-file", default=None,
                            help="credential file (default: ~/.config/proximo/<product>.token)")
        parser.add_argument("--write", action="store_true",
                            help="print the scoped WRITE grant instead of the read-only default")
        parser.add_argument("--json", action="store_true",
                            help="emit the recipe as structured JSON (mirrors doctor)")
        args = parser.parse_args(sys.argv[2:])
        try:
            recipe = build_recipe(product=args.product, user=args.user,
                                  token_name=args.token_name, token_file=args.token_file,
                                  write=args.write)
        except ValueError as e:
            print(f"proximo mint: {e}", file=sys.stderr)
            raise SystemExit(2) from None
        print(json.dumps(recipe, indent=2) if args.json else render_text(recipe))
        return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_main_module.py tests/test_mint.py -q`
Expected: all PASS

- [ ] **Step 5: Sanity-run the real CLI (run-it-like-an-enduser)**

```bash
uv run proximo mint | head -30
uv run proximo mint --product pdm --write | head -40
uv run proximo mint --product pmg --json | head -20
uv run proximo mint --product esx; echo "exit=$?"
```
Expected: readable runbooks; the last prints `proximo mint: unknown product 'esx' — valid: pve, pbs, pmg, pdm` to stderr with `exit=2`.

- [ ] **Step 6: Commit**

```bash
git add src/proximo/server.py tests/test_main_module.py
git commit -m "feat(cli): proximo mint subcommand — print-only onboarding runbook"
```

---

### Task 8: Docs ripple + full gates

**Files:**
- Modify: `README.md` (the doctor mention around lines 51–58), `SETUP.md` (Step 2 intro), `CHANGELOG.md` (Unreleased)

**Interfaces:**
- Consumes: the shipped CLI from Task 7. No code changes in this task.

- [ ] **Step 1: README pointer** — in the block that introduces `proximo doctor` (around line 51), add the mint line so the arc reads mint → doctor:

```markdown
Don't have a token yet? `proximo mint` prints the exact five-step runbook — create a
least-privilege credential, write it in the format Proximo reads (the `=`/`:`/password
trap, per product), grant a scoped role, wire it, verify. Print-only: it makes no API
call and never touches the secret itself.
```

- [ ] **Step 2: SETUP.md pointer** — at the top of "Step 2 — Create a least-privilege token in Proxmox", add:

```markdown
> Shortcut: `proximo mint` prints this whole step (and the next three) as an exact,
> copy-pasteable runbook for your product — `--product pve|pbs|pmg|pdm`, read-only by
> default, `--write` for the scoped write grant.
```

- [ ] **Step 3: CHANGELOG entry** — match the file's existing heading style (read its head first); under Unreleased, Added:

```markdown
- `proximo mint` — print-only token-onboarding runbook (sibling to `proximo doctor`):
  the exact create → write → grant → wire → verify steps per product (PVE/PBS/PMG/PDM),
  least-privilege by default (`--write` opt-in), `--json` for structured output. Bakes in
  the per-product credential formats (`=` vs `:` vs password) and the two hard-won grant
  gotchas (PDM user∩token intersection; PVE privsep token ACLs). Makes no API call and
  never handles a secret.
```

- [ ] **Step 4: Full gates**

```bash
uv run python -m pytest -q          # expect 5,269 prior + ~53 new, all green (3 by-design skips)
uv run ruff check src tests
uv run pyright
```
Expected: all green/clean. Fix anything that isn't before committing.

- [ ] **Step 5: Commit**

```bash
git add README.md SETUP.md CHANGELOG.md
git commit -m "docs(mint): README/SETUP pointers + changelog for the onboarding runbook"
```

---

## Self-review (done at planning time)

- **Spec coverage:** problem/goal → Tasks 1–4 (recipes) + 7 (CLI); non-goals (print-only, no MCP tool) → enforced by structure (no network imports, no `@mcp.tool`) and the never-starts-server CLI test; per-product facts table → separator tests per product; create paths incl. PDM REST + pvesh-first → Tasks 1–4; roles + `--write` → per-product grant tests; both gotchas → PDM dual-grant test + PVE own-ACL note test; CLI flags/defaults → Tasks 1 (defaults) + 7 (flags); five-step output contract → shape + invariants tests; `--json` mirror → Task 7; testing section bullets → all present; security posture → 600/umask invariant test, no-echo invariant test, read-only default tests.
- **Known deviations from spec (additive, verified against code):** non-PVE verify steps lead with a credential auth-smoke because the doctor CLI is PVE-only (doctor still referenced — the test `test_every_verify_step_hands_off_to_doctor` keeps the spec's arc); user-create lines added to create steps (fresh-host copy-paste success); PMG wire exports `PROXIMO_PMG_USERNAME` (default is root@pam). Flag these to John at review.
- **Type consistency:** `build_recipe` signature identical in Tasks 1 and 7; `Step`/`Recipe` keys consistent across builders, renderer, CLI, and tests; `_BUILDERS` grows monotonically over Tasks 1→4.
