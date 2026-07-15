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

Two gotchas baked into the recipes (both learned against live hosts, 2026-07-06; the PVE one
confirmed against a real adopter dead-token report, issue #24, 2026-07-15):
    - PDM tokens are ALWAYS privilege-separated: effective perms = user ∩ token — the PDM
      grant step grants the USER the role too, or the token stays capped at the user's role.
    - PVE `--privsep 1` tokens are ALSO privilege-separated the same way: effective perms =
      user ∩ token. A freshly-created user has no ACL of its own, so the grant step grants
      BOTH the token's auth-id AND the user — token-only leaves the intersection empty (a
      dead token that authenticates but can do nothing). PBS has no privsep concept (a PBS
      token's ACL stands alone) so its grant step is token-only by design, not by omission.
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
        "--privsep 1 tokens carry their OWN ACL, but a privsep token's EFFECTIVE permissions "
        "are the INTERSECTION of the user's ACL and the token's ACL — grant the role to BOTH "
        "the token's auth-id AND the user, or a freshly-created user (no ACL of its own) leaves "
        "the intersection empty: the token authenticates but can do nothing.",
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
        _step("grant", f"grant the {'scoped write' if write else 'read-only'} role to the token"
              " AND the user", [
            f"pveum acl modify {acl_path} --tokens '{authid}' --roles {role}",
            f"pveum acl modify {acl_path} --users '{user}' --roles {role}",
        ], grant_notes),
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
        _step("create", "create a dedicated PMG service user (PMG has no API keys)",
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


_BUILDERS = {
    "pve": _pve_steps,
    "pbs": _pbs_steps,
    "pdm": _pdm_steps,
    "pmg": _pmg_steps,
}


def build_recipe(
    product: str = "pve",
    user: str | None = None,
    token_name: str = "mcp",  # noqa: S107 — a token NAME (label), not a credential value
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
