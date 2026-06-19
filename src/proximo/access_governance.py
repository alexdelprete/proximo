"""ROLES & REALMS GOVERNANCE pillar — PVE role definitions, realm (domain) management, TFA reads.

This is the permissions-safety moat: mutating roles or realms changes WHO CAN LOG IN and
WHAT THEY CAN DO across the entire cluster.  Plans preview who/what is affected BEFORE any
mutation fires.

Key structural notes:
- Roles:   /access/roles  — define privilege sets; ACL entries reference them.
- Realms:  /access/domains — authentication sources (pam, pve, ldap, ad, openid).
- TFA:     /access/tfa  — per-user second factor entries.  get (read) + delete (mutation,
           RISK_HIGH — removes a second factor) exposed 2026-06-14; ENROLLMENT is NOT exposed
           (interactive TOTP/WebAuthn challenge — deliberately out of scope).
- All ops are SYNCHRONOUS — no UPID returned; outcome is the response or None.
- Built-in role guard: `Administrator`, `NoAccess`, `PVEAdmin`, `PVEAuditor`,
  `PVEDatastoreAdmin`, `PVEDatastoreUser`, `PVEMappingAdmin`, `PVEMappingUser`,
  `PVEPoolAdmin`, `PVEPoolUser`, `PVESDNAdmin`, `PVESDNUser`, `PVESysAdmin`,
  `PVETemplateUser`, `PVEUserAdmin`, `PVEVMAdmin`, `PVEVMUser`
  — PVE will reject DELETE on built-ins; mutations are RISK_HIGH and warned.
- Built-in realm guard: `pam`, `pve` — deleting or misconfig risks total lockout.

Smoke-confirm notes are embedded at each endpoint where the exact PVE API shape is
unverified from live smoke.

Hard rules mirrored from the codebase:
- Validators fire on every id/name before it enters a URL.
- Plans are HONEST — HIGH is maintained even when the op would fail; no false-safety claims.
- Affected-set reads (ACL counts, user counts) mirror plan_migrate honesty:
  read failure → disclose uncertainty + maintain RISK_HIGH; 404 → disclose plainly.
- The absence of a HIGH flag is NOT a safety signal.
- No self-gating: the server layer adds confirm-gating + audit; these functions are pure ops.
- These ops are SYNCHRONOUS — no UPID; outcome is the response, not "submitted".
"""

from __future__ import annotations

import re

# Smoke-confirm / follow-up: _check_roleid (in access.py) blocks '/' but permits '..';
# worst-case path is /access/roles/.. (harmless), but asymmetry should be addressed in a
# dedicated access.py hardening pass.
from .access import _check_roleid, _check_userid, _is_administrator_role
from .backends import ProximoError
from .planning import RISK_HIGH, RISK_MEDIUM, Plan

# ---------------------------------------------------------------------------
# Local validators
# ---------------------------------------------------------------------------

# realmid: letters/digits/_/-/., must start with alnum (letter or digit), no slash, no newline.
# \Z (not $) blocks embedded-newline bypass.
_REALMID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def _check_realmid(realm: str) -> str:
    """Validate a Proxmox realm (authentication domain) name.

    Accepted: letters/digits/underscore/hyphen/dot; must start with alphanumeric; no slash
    or newline (path-traversal rejection).  \\Z anchors past any trailing newline.
    """
    s = str(realm).strip()
    if not _REALMID_RE.match(s):
        raise ProximoError(
            f"invalid realm id: {realm!r} — expected letters/digits/._- "
            "starting with alnum (no slash, no whitespace)"
        )
    return s


# ---------------------------------------------------------------------------
# Constants — built-in roles and realms
# ---------------------------------------------------------------------------

# Well-known PVE built-in roles.  PVE refuses DELETE on these.
# Smoke-confirm: authoritative set is GET /access/roles filtered by `special: 1`; this list
# reflects PVE 8.x and may grow across PVE versions — re-verify at live smoke on upgrade.
_BUILTIN_ROLES = frozenset({
    "Administrator",
    "NoAccess",
    "PVEAdmin",
    "PVEAuditor",
    "PVEDatastoreAdmin",
    "PVEDatastoreUser",
    "PVEMappingAdmin",
    "PVEMappingUser",
    "PVEPoolAdmin",
    "PVEPoolUser",
    "PVESDNAdmin",
    "PVESDNUser",
    "PVESysAdmin",
    "PVETemplateUser",
    "PVEUserAdmin",
    "PVEVMAdmin",
    "PVEVMUser",
})

# Well-known PVE built-in realms.  pam = local PAM (primary admin login);
# pve = PVE local user DB.  Deleting either is a lockout event.
# Smoke-confirm: verify PVE actually rejects DELETE /access/domains/pam at live smoke.
_BUILTIN_REALMS = frozenset({"pam", "pve"})

# Valid realm_type values.
# Smoke-confirm: verify the full accepted set against live PVE API viewer
# (e.g. openid may require a newer PVE version; confirm 'ad' vs 'activedirectory').
_VALID_REALM_TYPES = frozenset({"pam", "pve", "ldap", "ad", "openid"})


def _is_builtin_role(roleid: str) -> bool:
    """True if roleid is one of the well-known PVE built-in roles."""
    return roleid in _BUILTIN_ROLES


def _is_builtin_realm(realm: str) -> bool:
    """True if realm is one of the well-known PVE built-in realms (pam / pve)."""
    return realm in _BUILTIN_REALMS


# ---------------------------------------------------------------------------
# READ operations — audited but not confirm-gated
# ---------------------------------------------------------------------------

def realms_list(api) -> list[dict]:
    """List all authentication realms (domains) configured in Proxmox.

    GET /access/domains

    Returns a list of realm objects.  Expected fields: realm, type, comment, tfa, default.
    Smoke-confirm: verify exact field names against a live PVE; 'realm' vs 'domain' vs 'name'
    may vary by PVE version.

    Audited at the server layer.
    """
    return api._get("/access/domains") or []


def realm_get(api, realm: str) -> dict:
    """Get the configuration of a specific authentication realm.

    GET /access/domains/{realm}

    Returns a single realm config dict.
    Smoke-confirm: verify the response shape — expected {realm, type, comment, tfa, ...};
    type-specific fields (server, base_dn, bind_dn, etc.) present only for ldap/ad/openid.
    Smoke-confirm: verify 404 behavior when the realm does not exist
    (raises vs returns None vs empty dict).

    Audited at the server layer.
    """
    realm = _check_realmid(realm)
    return api._get(f"/access/domains/{realm}") or {}


def tfa_list(api) -> list[dict]:
    """List all per-user TFA (two-factor authentication) entries across the cluster.

    GET /access/tfa

    Returns a list of TFA entry objects.
    Smoke-confirm: verify the response shape — expected [{userid, entries: [{type, id, ...}]}]
    or a flat list by PVE version.  The exact per-entry structure varies by TFA type
    (totp, recovery, webauthn, yubico).
    Smoke-confirm: verify that GET /access/tfa requires Administrator or Sys.Audit privilege.

    READ ONLY — TFA mutations are deferred (too sensitive / unverifiable without live smoke).
    Audited at the server layer.
    """
    return api._get("/access/tfa") or []


# ---------------------------------------------------------------------------
# MUTATION operations — validate params, build exact PVE URL, return result.
# These do NOT self-gate.  The server layer adds confirm-gating + audit.
# ---------------------------------------------------------------------------

def role_create(api, roleid: str, privs: str | None = None) -> object:
    """Create a new Proxmox role with an optional set of privileges.

    POST /access/roles
    Body: {roleid, privs?}

    privs: comma-separated privilege names (e.g. 'VM.PowerMgmt,VM.Config.Disk').
    Smoke-confirm: verify the exact format PVE accepts for the 'privs' param
    (comma-separated strings, no spaces around commas; verify full privilege name list
    via GET /access/roles on a live instance).
    Smoke-confirm: verify whether omitting 'privs' creates a role with zero privileges
    (expected behavior, but confirm at live smoke).

    Returns the PVE response (typically None — synchronous write, no UPID).

    MUTATION — confirm-gated + audited at the server layer.
    """
    roleid = _check_roleid(roleid)
    data: dict = {"roleid": roleid}
    if privs is not None:
        data["privs"] = str(privs)
    return api._post("/access/roles", data)


def role_update(api, roleid: str, privs: str | None = None, append: bool | None = None) -> object:
    """Update (replace or append to) the privilege set of an existing role.

    PUT /access/roles/{roleid}
    Body: {privs?, append?}

    privs: comma-separated privilege names.
    append: if True (sends append=1), the given privs are ADDED to the role's existing set.
            If False/omitted (default), the privs REPLACE the entire set.
    Smoke-confirm: verify append=1 vs append=True semantics at live smoke — specifically,
    confirm whether omitting 'append' means replace (not union) and whether append=0 is
    needed to force replace when the param is present.

    Returns the PVE response (typically None — synchronous write, no UPID).

    MUTATION — confirm-gated + audited at the server layer.
    """
    roleid = _check_roleid(roleid)
    data: dict = {}
    if privs is not None:
        data["privs"] = str(privs)
    if append is not None:
        data["append"] = int(append)
    return api._put(f"/access/roles/{roleid}", data)


def role_delete(api, roleid: str) -> object:
    """Delete a Proxmox role.

    DELETE /access/roles/{roleid}

    NOTE: PVE refuses to delete built-in roles (Administrator, PVEAdmin, etc.).
    Calling this on a built-in role will be rejected by PVE.  Use plan_role_delete
    first — the plan will surface the refusal and the blast radius.

    Returns the PVE response (typically None — synchronous write, no UPID).

    MUTATION — confirm-gated + audited at the server layer.
    """
    roleid = _check_roleid(roleid)
    return api._delete(f"/access/roles/{roleid}")


def realm_create(
    api,
    realm: str,
    realm_type: str,
    comment: str | None = None,
    options: dict | None = None,
) -> object:
    """Create a new authentication realm (domain).

    POST /access/domains
    Body: {realm, type, comment?, **options}

    realm_type: must be one of 'pam', 'pve', 'ldap', 'ad', 'openid' (verified live on PVE 9.2).

    `options` carries the type-specific fields (passed verbatim — keys are NOT remapped, so
    use PVE's exact spelling, which is inconsistent: ldap uses underscores `server1`/`base_dn`/
    `user_attr`; ad uses `domain`/`server1`; openid uses hyphens `issuer-url`/`client-id`).
    PVE is authoritative: it returns a clean error for missing/unknown keys. (Live smoke 2026-06-09
    confirmed a typed realm WITHOUT its required fields IS rejected — `500 missing 'server1'` —
    which is why `options` exists rather than deferring per-type config elsewhere.) Core fields
    (realm/type) are set last so `options` can never clobber them.

    Returns the PVE response (typically None — synchronous write, no UPID).

    MUTATION — confirm-gated + audited at the server layer.
    """
    realm = _check_realmid(realm)
    if realm_type not in _VALID_REALM_TYPES:
        raise ProximoError(
            f"invalid realm_type: {realm_type!r} "
            f"(expected one of {sorted(_VALID_REALM_TYPES)})"
        )
    # type-specific fields first, then core fields LAST so a caller's options can never
    # clobber realm/type (resource identity). PVE is authoritative on which fields each
    # type requires — it returns a clean 400/500 for missing/unknown keys.
    data: dict = dict(options or {})
    if comment is not None:
        data["comment"] = str(comment)
    data["realm"] = realm
    data["type"] = realm_type
    return api._post("/access/domains", data)


def realm_update(api, realm: str, comment: str | None = None,
                 options: dict | None = None) -> object:
    """Update fields of an existing authentication realm.

    PUT /access/domains/{realm}
    Body: {comment?, **options}

    `options` carries type-specific fields (server1/base_dn/etc., passed verbatim — see
    realm_create for PVE's exact, inconsistent key spelling). PVE validates them. The explicit
    `comment` param wins over any options['comment']. A core-only update may send just 'comment'.

    Returns the PVE response (typically None — synchronous write, no UPID).

    MUTATION — confirm-gated + audited at the server layer.
    """
    realm = _check_realmid(realm)
    # type-specific fields first; explicit `comment` param wins over any options['comment'].
    data: dict = dict(options or {})
    if comment is not None:
        data["comment"] = str(comment)
    return api._put(f"/access/domains/{realm}", data)


def realm_delete(api, realm: str) -> object:
    """Delete an authentication realm.

    DELETE /access/domains/{realm}

    NOTE: PVE refuses to delete built-in realms ('pam', 'pve').  Deleting 'pam' would
    cause total lockout.  Use plan_realm_delete first — the plan will refuse built-ins
    and surface the blast radius (users who will lose login ability).

    Returns the PVE response (typically None — synchronous write, no UPID).

    MUTATION — confirm-gated + audited at the server layer.
    """
    realm = _check_realmid(realm)
    return api._delete(f"/access/domains/{realm}")


# ---------------------------------------------------------------------------
# PLAN functions — pure analysis; return a Plan the caller can inspect.
# ---------------------------------------------------------------------------

def plan_role_create(roleid: str, privs: str | None = None) -> Plan:
    """Preview creating a new Proxmox role.

    PURE — no API call needed.

    RISK_MEDIUM: adds a new capability set.  A new role by itself changes nothing until
    it is assigned via an ACL entry, but it expands the privilege vocabulary available
    to operators.

    Validates roleid; privs format is advisory (PVE defines the valid privilege name set).
    """
    roleid = _check_roleid(roleid)
    priv_note = f"privileges: {privs!r}" if privs is not None else "no privileges specified (empty role)"
    return Plan(
        action="pve_role_create",
        target=f"role:{roleid}",
        change=f"create role {roleid!r} ({priv_note})",
        current={},
        blast_radius=[
            f"creates role {roleid!r} — adds a new privilege set to the cluster",
            priv_note,
            "a new role is inert until assigned via an ACL entry",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=["adds a capability set — inert until an ACL entry references it"],
        note=(
            "Smoke-confirm: priv names are free-form strings here; PVE validates them at POST time. "
            "Confirm format 'VM.PowerMgmt,VM.Config.Disk' (comma-separated, no spaces) at live smoke."
        ),
    )


def plan_role_update(api, roleid: str, privs: str | None = None, append: bool | None = None) -> Plan:
    """Preview updating a Proxmox role's privilege set.

    Reads GET /access/acl to show current usage context (informational, not for ACL counting here —
    role_update changes privileges; existing ACL entries referencing this role now carry the new
    privilege set automatically).

    Risk classification:
    - Built-in role (Administrator, PVEVMAdmin, etc.) → RISK_HIGH: PVE may refuse; the plan
      warns that every ACL entry using this role is immediately affected.
    - All other roles → RISK_MEDIUM.

    NOTE: role_update does NOT read the API — the risk escalation for built-ins is
    classifier-driven (no live read needed for the high-risk gate).  PURE for non-built-ins.
    """
    roleid = _check_roleid(roleid)

    is_builtin = _is_builtin_role(roleid)
    is_admin = _is_administrator_role(roleid)  # reuse imported helper

    if privs is not None:
        action_desc = (
            f"{'append' if append else 'replace'} privileges ({privs!r}) on role {roleid!r}"
        )
    else:
        action_desc = f"update role {roleid!r} (no privs specified — no-op body)"

    blast: list[str] = []
    reasons: list[str] = []

    if is_builtin:
        risk = RISK_HIGH
        blast.append(
            f"BUILT-IN ROLE: {roleid!r} is a PVE system role — PVE may refuse modifications; "
            "check PVE version constraints before proceeding"
        )
        blast.append(
            "every ACL entry referencing this role immediately inherits the NEW privilege set "
            "— blast radius spans all principals and resources using this role"
        )
        reasons.append(
            f"{roleid!r} is a built-in PVE role — modifications affect ALL ACL entries "
            "referencing it and PVE may reject the change"
        )
        if is_admin:
            blast.append(
                "Administrator is the PVE super-role — modifying it affects every "
                "administrator-level principal on the cluster"
            )
            reasons.append("Administrator = super-role; modification is cluster-wide")
    else:
        risk = RISK_MEDIUM
        blast.append(
            f"updates role {roleid!r} privilege set — all ACL entries referencing this role "
            "immediately carry the updated privileges"
        )
        reasons.append(
            "role update propagates immediately to all ACL entries that reference this role"
        )

    if append:
        blast.append(
            "append=True: new privileges are ADDED to the existing set (not replaced)"
        )
    elif append is False:
        blast.append(
            "append=False: the entire privilege set is REPLACED — existing privileges not in "
            f"{privs!r} will be removed"
        )

    # Blast radius: read the ACL and NAME the grants this re-privileges (every ACL entry using this
    # role immediately carries the new privilege set). Mirrors plan_role_delete's read-failure honesty.
    affected: list[dict] = []
    complete = True
    try:
        acl_entries = api._get("/access/acl") or []
        matched = [e for e in acl_entries if e.get("roleid") == roleid]
        for e in matched:
            affected.append({
                "principal": str(e.get("ugid", "")), "path": str(e.get("path", "")),
                "roleid": roleid, "change": "re-privileged",
                "severity": "high" if is_builtin else "medium",
            })
        if matched:
            named = ", ".join(sorted(f"{e.get('ugid', '')}@{e.get('path', '')}" for e in matched))
            blast.append(
                f"{len(matched)} ACL grant(s) use role {roleid!r} and immediately carry the new "
                f"privileges: {named}"
            )
        else:
            blast.append(
                f"0 ACL grants currently reference role {roleid!r} — no principal is re-privileged now"
            )
    except Exception as exc:
        complete = False
        check_error = "404" if getattr(getattr(exc, "response", None), "status_code", None) == 404 \
            else type(exc).__name__
        blast.append(
            f"could NOT read the ACL ({check_error}) — cannot name which grants this re-privileges; "
            "absence of a list is NOT a safety signal"
        )
        reasons.append(f"ACL read failed ({check_error}) — affected-grants list unknown")

    return Plan(
        action="pve_role_update",
        target=f"role:{roleid}",
        change=action_desc,
        current={},
        blast_radius=blast,
        risk=risk,
        risk_reasons=reasons,
        affected=affected,
        complete=complete,
        note=(
            "Smoke-confirm: append=1 semantics — verify whether omitting 'append' means replace "
            "(not union) and whether append=0 forces replace explicitly."
        ),
    )


def plan_role_delete(api, roleid: str) -> Plan:
    """Preview deleting a Proxmox role.

    Reads GET /access/acl to count how many ACL entries reference this role (blast radius).
    Mirrors plan_migrate read-failure honesty: read failure → disclose uncertainty + maintain
    RISK_HIGH; 404 → disclose plainly.

    Risk:
    - Built-in role → RISK_HIGH + refuse message (PVE will reject the delete).
    - Any other role → RISK_HIGH (ACL grants will break; blast is the ACL count).
    """
    roleid = _check_roleid(roleid)

    # Built-in guard: refuse before any read.
    if _is_builtin_role(roleid):
        return Plan(
            action="pve_role_delete",
            target=f"role:{roleid}",
            change=f"delete role {roleid!r}",
            current={},
            blast_radius=[
                f"REFUSED: {roleid!r} is a PVE built-in role — PVE will REJECT this deletion",
                "built-in roles are system-defined and cannot be deleted via the API",
                "to proceed, choose a different role or create a custom role instead",
            ],
            risk=RISK_HIGH,
            risk_reasons=[
                f"{roleid!r} is a built-in PVE role; DELETE /access/roles/{roleid} will be rejected by PVE",
            ],
        )

    # One safe read: count ACL entries that reference this role.
    acl_entries: list[dict] = []
    check_error: str | None = None
    acl_count: int | None = None

    try:
        acl_entries = api._get("/access/acl") or []
        acl_count = sum(1 for e in acl_entries if e.get("roleid") == roleid)
    except Exception as exc:
        resp = getattr(exc, "response", None)
        if resp is not None and getattr(resp, "status_code", None) == 404:
            # /access/acl 404 is unexpected (it's a cluster-level endpoint, always present).
            # Treat as a read failure — disclose, do not imply safety.
            check_error = "404"
        else:
            check_error = type(exc).__name__

    blast: list[str] = []
    reasons: list[str] = []

    if check_error is not None:
        blast.append(
            f"could NOT read current ACL ({check_error}) — cannot determine how many ACL grants "
            "reference this role; absence of a count is NOT a safety signal"
        )
        reasons.append(
            f"ACL read failed ({check_error}) — blast radius (ACL grants that will break) unknown; "
            "absence of a warning is not a safety signal"
        )
    else:
        if acl_count and acl_count > 0:
            blast.append(
                f"{acl_count} ACL grant(s) reference role {roleid!r} and will break "
                "(the principal loses the privileges granted by this role at those paths)"
            )
            reasons.append(
                f"{acl_count} ACL entry(ies) reference {roleid!r}; deleting the role breaks those grants"
            )
        else:
            blast.append(
                f"0 ACL grants currently reference role {roleid!r} — deletion has no immediate "
                "access effect (role is unused)"
            )
            reasons.append(f"role {roleid!r} is not referenced by any current ACL entry")

    blast.append(
        f"permanently deletes role {roleid!r} — any future ACL entry referencing it would be invalid"
    )
    reasons.append("role deletion is irreversible without manual re-creation")

    return Plan(
        action="pve_role_delete",
        target=f"role:{roleid}",
        change=f"delete role {roleid!r}",
        current={},
        blast_radius=blast,
        risk=RISK_HIGH,
        risk_reasons=reasons,
    )


def plan_realm_create(
    realm: str,
    realm_type: str,
    comment: str | None = None,
    options: dict | None = None,
) -> Plan:
    """Preview creating a new authentication realm.

    PURE — no API call needed.

    RISK_MEDIUM: adds a new auth source.  A misconfigured realm can let unintended principals
    authenticate.

    Type-specific fields travel in `options` (passed verbatim to PVE). PVE is authoritative on
    which fields each type requires — it returns a clean error for missing ones, so we surface a
    soft, NON-blocking advisory here rather than re-implementing PVE's per-type required-field map.

    Validates realm and realm_type.
    """
    realm = _check_realmid(realm)
    if realm_type not in _VALID_REALM_TYPES:
        raise ProximoError(
            f"invalid realm_type: {realm_type!r} "
            f"(expected one of {sorted(_VALID_REALM_TYPES)})"
        )

    opts = options or {}
    comment_note = f" (comment: {comment!r})" if comment else ""
    opt_note = f" with options {sorted(opts)}" if opts else ""

    blast = [
        f"adds authentication realm {realm!r} (type={realm_type!r}) to the cluster",
        "a misconfigured realm can allow unintended principals to authenticate",
    ]
    reasons = [
        "adds an auth source — misconfiguration can let unintended principals authenticate",
    ]
    # Soft advisory (NON-blocking): name the fields PVE typically requires per type. Verified
    # against PVE 9.2 (2026-06-09). We do NOT pre-reject — PVE validates and reports missing keys.
    typical = {
        "ldap": "server1, base_dn, user_attr",
        "ad": "domain, server1",
        "openid": "issuer-url, client-id",
    }.get(realm_type)
    if typical and not opts:
        blast.append(
            f"NOTE: type {realm_type!r} typically requires {typical} in `options`; "
            "PVE will reject this create if they are missing"
        )
        reasons.append(f"no type-specific options supplied — {realm_type!r} usually needs {typical}")

    return Plan(
        action="pve_realm_create",
        target=f"realm:{realm}",
        change=f"create realm {realm!r} (type={realm_type!r}){comment_note}{opt_note}",
        current={},
        blast_radius=blast,
        risk=RISK_MEDIUM,
        risk_reasons=reasons,
        note=(
            "Type-specific fields travel in `options` (verbatim to PVE). Typical required keys — "
            "ldap: server1/base_dn/user_attr; ad: domain/server1; openid: issuer-url/client-id. "
            "PVE validates them and reports anything missing."
        ),
    )


def plan_realm_update(api, realm: str, comment: str | None = None,
                      options: dict | None = None) -> Plan:
    """Preview updating an authentication realm's fields.

    Risk:
    - Built-in realm (pam / pve) → RISK_HIGH: changing them risks breaking all logins
      via that realm.
    - All other realms → RISK_MEDIUM.

    Type-specific fields travel in `options` (verbatim to PVE). PURE — no API read needed for
    risk classification (built-in check is classifier-driven).
    """
    realm = _check_realmid(realm)

    is_builtin = _is_builtin_realm(realm)
    opts = options or {}
    fields = []
    if comment is not None:
        fields.append(f"comment={comment!r}")
    if opts:
        fields.append(f"options {sorted(opts)}")
    comment_note = ("set " + ", ".join(fields)) if fields else "no fields specified (no-op)"

    if is_builtin:
        risk = RISK_HIGH
        blast = [
            f"BUILT-IN REALM: {realm!r} is a PVE system realm — modifications risk breaking "
            "ALL logins that use this realm",
            "'pam' = local PAM (primary admin login); 'pve' = PVE local user DB — "
            "misconfiguring either can prevent ALL administrative access to the cluster",
            comment_note,
        ]
        reasons = [
            f"{realm!r} is a built-in PVE realm; changes risk breaking all logins via this realm",
            "built-in realm misconfiguration = potential total auth lockout",
        ]
    else:
        risk = RISK_MEDIUM
        blast = [
            f"updates realm {realm!r} ({comment_note})",
            "type-specific fields (server1, base_dn, etc.) update too if supplied in `options`",
        ]
        reasons = [
            "realm update; comment and any type-specific `options` fields are applied",
        ]

    # Blast radius: read the user DB and NAME the users whose login this could break (a realm
    # misconfig can lock out every user@realm). Mirrors plan_realm_delete's read-failure honesty.
    affected: list[dict] = []
    complete = True
    realm_suffix = f"@{realm}"
    try:
        user_entries = api._get("/access/users") or []
        matched = [u for u in user_entries if str(u.get("userid", "")).endswith(realm_suffix)]
        for u in matched:
            affected.append({"userid": str(u.get("userid", "")), "change": "login may break",
                             "severity": "high" if is_builtin else "medium"})
        if matched:
            named = ", ".join(sorted(str(u.get("userid", "")) for u in matched))
            blast.append(
                f"{len(matched)} user(s) authenticate via realm {realm!r} — a misconfig can break their "
                f"login: {named}"
            )
        else:
            blast.append(f"0 users currently authenticate via realm {realm!r}")
    except Exception as exc:
        complete = False
        check_error = "404" if getattr(getattr(exc, "response", None), "status_code", None) == 404 \
            else type(exc).__name__
        blast.append(
            f"could NOT read the user DB ({check_error}) — cannot name which logins this could break; "
            "absence of a list is NOT a safety signal"
        )
        reasons.append(f"user read failed ({check_error}) — affected-users list unknown")

    return Plan(
        action="pve_realm_update",
        target=f"realm:{realm}",
        change=f"update realm {realm!r} ({comment_note})",
        current={},
        blast_radius=blast,
        risk=risk,
        risk_reasons=reasons,
        affected=affected,
        complete=complete,
        note=(
            "Type-specific fields travel in `options` (verbatim to PVE); PVE validates them. "
            "A core-only update may send just 'comment'."
        ),
    )


def plan_realm_delete(api, realm: str) -> Plan:
    """Preview deleting an authentication realm.

    Reads GET /access/users to count users in this realm (userid suffix = @{realm}).
    Mirrors plan_migrate read-failure honesty: read failure → disclose uncertainty + maintain
    RISK_HIGH; 404 → disclose plainly.

    Risk:
    - Built-in realm (pam / pve) → RISK_HIGH + refuse (PVE will reject; pam deletion = lockout).
    - Any other realm → RISK_HIGH (auth-lockout class: users lose login ability).
    """
    realm = _check_realmid(realm)

    # Built-in guard: refuse before any read.
    if _is_builtin_realm(realm):
        lockout_note = (
            "deleting 'pam' = TOTAL LOCKOUT — all local admin access is lost"
            if realm == "pam"
            else "deleting 'pve' removes the PVE local user DB realm — may block local logins"
        )
        return Plan(
            action="pve_realm_delete",
            target=f"realm:{realm}",
            change=f"delete realm {realm!r}",
            current={},
            blast_radius=[
                f"REFUSED: {realm!r} is a PVE built-in realm — PVE will REJECT this deletion",
                lockout_note,
                "built-in realms cannot be deleted; they are required for cluster operation",
            ],
            risk=RISK_HIGH,
            risk_reasons=[
                f"{realm!r} is a built-in PVE realm; DELETE /access/domains/{realm} will be rejected by PVE",
                lockout_note,
            ],
        )

    # One safe read: count users in this realm.
    user_entries: list[dict] = []
    check_error: str | None = None
    user_count: int | None = None
    realm_suffix = f"@{realm}"

    try:
        user_entries = api._get("/access/users") or []
        user_count = sum(
            1 for u in user_entries
            if str(u.get("userid", "")).endswith(realm_suffix)
        )
    except Exception as exc:
        resp = getattr(exc, "response", None)
        if resp is not None and getattr(resp, "status_code", None) == 404:
            # /access/users 404 is unexpected; treat as read failure — disclose.
            check_error = "404"
        else:
            check_error = type(exc).__name__

    blast: list[str] = []
    reasons: list[str] = []

    if check_error is not None:
        blast.append(
            f"could NOT read current user list ({check_error}) — cannot determine how many users "
            f"authenticate via realm {realm!r}; absence of a count is NOT a safety signal"
        )
        reasons.append(
            f"user-list read failed ({check_error}) — user blast radius unknown; "
            "absence of a warning is not a safety signal"
        )
    else:
        if user_count and user_count > 0:
            blast.append(
                f"{user_count} user(s) authenticate via realm {realm!r} and will be UNABLE TO LOG IN "
                "after this realm is deleted"
            )
            reasons.append(
                f"{user_count} user(s) in realm {realm!r} lose login ability on realm deletion"
            )
        else:
            blast.append(
                f"0 users currently in realm {realm!r} — deletion has no immediate login impact "
                "(realm is unused or all users have been migrated)"
            )
            reasons.append(f"realm {realm!r} has no current users; deletion is low-impact")

    blast.append(
        f"permanently deletes realm {realm!r} — authentication via this domain is gone; "
        "recreation requires reconfiguring all type-specific fields"
    )
    reasons.append("realm deletion is irreversible without full manual reconfiguration")

    return Plan(
        action="pve_realm_delete",
        target=f"realm:{realm}",
        change=f"delete realm {realm!r}",
        current={},
        blast_radius=blast,
        risk=RISK_HIGH,
        risk_reasons=reasons,
    )


# ===========================================================================
# TFA — per-user two-factor-authentication get (read) + delete (mutation)
# ---------------------------------------------------------------------------
# Grounded against live PVE 9.1.7 schema (2026-06-14):
#   GET    /access/tfa/{userid}            list a user's TFA entries
#   GET    /access/tfa/{userid}/{id}        fetch one entry
#   DELETE /access/tfa/{userid}/{id}        {password?}   delete a TFA factor
# Enrollment (POST) is intentionally NOT exposed — it is an interactive TOTP/WebAuthn
# challenge-response, not a clean admin one-shot.
#
# Deleting a TFA factor WEAKENS the account's login security (one fewer second factor) and,
# if it is the user's last factor on a TFA-required realm, can lock the user out → RISK_HIGH.
# `password` (the acting user's current password) is a SECRET: it flows to the API but is
# NEVER placed in the plan or the audit detail.
# ===========================================================================

_TFA_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]*\Z")


def _check_tfa_id(tfa_id: str) -> str:
    """Validate a TFA entry id — it flows into the URL path, so reject traversal/injection."""
    v = str(tfa_id).strip()
    if ".." in v or not _TFA_ID_RE.match(v):
        raise ProximoError(
            f"invalid TFA id: {tfa_id!r} (alphanumeric/:._- only, start with alnum; no path traversal)"
        )
    return v


def tfa_get(api, userid: str, tfa_id: str | None = None) -> object:
    """Read a user's TFA entries, or one entry. Audited at the server layer (read).

    GET /access/tfa/{userid}            (tfa_id=None) -> list of entries
    GET /access/tfa/{userid}/{tfa_id}                  -> a single entry
    """
    userid = _check_userid(userid)
    if tfa_id is None:
        return api._get(f"/access/tfa/{userid}") or []
    tfa_id = _check_tfa_id(tfa_id)
    return api._get(f"/access/tfa/{userid}/{tfa_id}") or {}


def tfa_delete(api, userid: str, tfa_id: str, password: str | None = None) -> object:
    """Delete a user's TFA factor. MUTATION — confirm-gated + audited at the server layer.

    DELETE /access/tfa/{userid}/{tfa_id}  {password?}
    `password` (the acting user's current password) may be required by PVE; it is passed through
    but never logged. No UNDO: the factor must be re-enrolled. Security-WEAKENING (RISK_HIGH).

    LIVE-VERIFIED CAVEAT (PVE 9.1.7, 2026-06-14): PVE forbids API *tokens* from modifying TFA —
    it returns `403 ... not available with API token, need proper ticket`. TFA mutation requires
    a ticket-based login session, which Proximo does not use (it is token-authed by design). So the
    READ tools (tfa_get / tfa_list) work via token, but this DELETE will 403 under token auth. The
    request is shape-correct (it reaches the API and PVE applies its own rule) and would execute
    under ticket auth.
    """
    userid = _check_userid(userid)
    tfa_id = _check_tfa_id(tfa_id)
    params: dict = {}
    if password is not None:
        params["password"] = password
    return api._delete(f"/access/tfa/{userid}/{tfa_id}", params)


def plan_tfa_delete(api, userid: str, tfa_id: str) -> Plan:
    """Preview deleting a TFA factor. Reads the user's TFA entries (one safe read) to show how many
    factors remain. RISK_HIGH — removes a second factor; the last one on a TFA-required realm can
    lock the user out. Never references the password."""
    userid = _check_userid(userid)
    tfa_id = _check_tfa_id(tfa_id)
    current: dict = {}
    total: int | None = None
    read_error: str | None = None
    try:
        entries = api._get(f"/access/tfa/{userid}")
        if isinstance(entries, list):
            total = len(entries)
            current = next((e for e in entries if e.get("id") == tfa_id or e.get("type") == tfa_id), {})
    except Exception as exc:
        read_error = type(exc).__name__
    blast = [
        f"removes TFA entry '{tfa_id}' from user '{userid}' — a SECOND FACTOR is deleted",
        "WEAKENS the account's login security (one fewer 2FA factor)",
        f"if this is '{userid}'s last factor and the realm REQUIRES TFA, the user may be UNABLE to log in",
        "no UNDO: the factor must be re-enrolled (TOTP/WebAuthn) to restore it",
    ]
    if total is not None:
        blast.insert(1, f"user currently has {total} TFA entry/entries")
    elif read_error is not None:
        # Module honesty contract (mirrors plan_role_delete / plan_realm_delete): read failure ->
        # disclose uncertainty + maintain RISK_HIGH. Never present a missing count as safe.
        blast.insert(1,
            f"could NOT read current TFA entries ({read_error}) — cannot determine how many "
            "factors remain; absence of a count is NOT a safety signal")
    return Plan(
        action="pve_tfa_delete", target=f"access/tfa/{userid}/{tfa_id}",
        change=f"delete TFA entry '{tfa_id}' for user '{userid}'",
        current=current, blast_radius=blast, risk=RISK_HIGH,
        risk_reasons=[
            "deleting a TFA factor weakens account security and can break login on TFA-required realms",
        ],
    )
