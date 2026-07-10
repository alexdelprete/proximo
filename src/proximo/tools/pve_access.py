"""PVE access governance: ACLs/roles/tokens (read+mutation), users & groups, and roles/realms/TFA CRUD.

Split out of proximo.server (2026-07-02) — see proximo/server.py's module
docstring for the funnel these wrappers depend on.
"""
from __future__ import annotations

import proximo.server as _proximo_server
from proximo.access import (
    access_acl_list,
    access_overbroad_grants,
    access_roles_list,
    access_tokens_list,
    access_users_list,
    acl_modify,
    acl_prune,
    plan_acl_modify,
    plan_prune_grant,
    plan_token_create,
    plan_token_revoke,
    token_create,
    token_revoke,
)
from proximo.access_governance import (
    plan_realm_create,
    plan_realm_delete,
    plan_realm_update,
    plan_role_create,
    plan_role_delete,
    plan_role_update,
    plan_tfa_delete,
    realm_create,
    realm_delete,
    realm_get,
    realm_update,
    realms_list,
    role_create,
    role_delete,
    role_update,
    tfa_delete,
    tfa_get,
    tfa_list,
)
from proximo.access_users import (
    group_create,
    group_delete,
    group_get,
    group_update,
    groups_list,
    plan_group_create,
    plan_group_delete,
    plan_group_update,
    plan_user_create,
    plan_user_delete,
    plan_user_update,
    user_create,
    user_delete,
    user_get,
    user_update,
)
from proximo.server import (
    _audited,
    _plan,
    tool,
)

# --- Access governance (REST API, read) ---

@tool()
def pve_users_list() -> list[dict]:
    """List all Proxmox users across every realm (read-only). Returns each user's id (user@realm),
    enabled flag, expiry, group membership, email, and comment. Use pve_user_get for one user's
    full config, tokens, and effective ACL."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_users_list", "access/users", lambda: access_users_list(api))


@tool()
def pve_roles_list() -> list[dict]:
    """List all Proxmox roles and their privileges (read-only). Returns each role's id, privilege
    set, and whether it is built-in. Use pve_role_create/update/delete to modify roles; use
    pve_acl_list to see which principals hold which roles at which paths."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_roles_list", "access/roles", lambda: access_roles_list(api))


@tool()
def pve_acl_list() -> list[dict]:
    """List all ACL entries on the Proxmox cluster (read-only). Returns each entry's path (resource
    scope), roleid (privilege set), principal (user/group/token), type, and propagate flag. Use
    pve_acl_modify to grant/revoke; use pve_overbroad_grants to flag Administrator or root-path
    grants."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_acl_list", "access/acl", lambda: access_acl_list(api))


@tool()
def pve_tokens_list(userid: str) -> list[dict]:
    """List API tokens for a specific user (read-only). Returns each token's id, comment, expiry,
    and privsep (privilege separation) flag — NOT the secret (shown only at creation). userid
    format: 'user@realm'. Use pve_token_create/revoke to manage tokens."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_tokens_list", f"access/users/{userid}/token",
                    lambda: access_tokens_list(api, userid))


@tool()
def pve_overbroad_grants() -> list[dict]:
    """Surface over-broad ACL grants (Administrator role or root '/' path) as a diagnostic (read)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_overbroad_grants", "access/acl",
                    lambda: access_overbroad_grants(api))


# --- Access governance (REST API, MUTATION — confirm-gated) ---

@tool()
def pve_acl_modify(
    path: str, roles: str, target: str, kind: str = "user",
    propagate: bool = True, delete: bool = False, confirm: bool = False,
) -> dict:
    """MUTATION: grant or revoke an ACL entry (PUT /access/acl).

    Dry-run by default — the PLAN surfaces the critical Proxmox gotcha: a specific-path ACL
    REPLACES inherited grants (SHADOW) and revoking can RESTORE them (WIDEN). Re-call with
    confirm=True to execute. Synchronous.

    kind='user' (default), 'group', or 'token'. delete=False = grant; delete=True = revoke.
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"acl:{path}:{target}"
    plan = _plan("pve_acl_modify", tgt,
                 lambda: plan_acl_modify(api, path, roles, target, kind, propagate, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_acl_modify", tgt,
                    lambda: acl_modify(api, path, roles, target, kind, propagate, delete),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_acl_prune(
    path: str, target: str, kind: str = "user", roleid: str = "",
    narrow_role: str | None = None, narrow_path: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: prune (remove/narrow) an over-broad ACL grant flagged by pve_overbroad_grants.

    Dry-run by default — the PLAN names every principal losing/gaining what, and flags
    shadow/widen gotchas. Re-call with confirm=True to execute (revoke, then optional
    narrower re-grant). Synchronous. roleid = the over-broad role to remove (from detection).
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"acl:prune:{path}:{target}"
    plan = _plan("pve_acl_prune", tgt,
                 lambda: plan_prune_grant(api, path, target, kind, roleid, narrow_role, narrow_path))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_acl_prune", tgt,
                    lambda: acl_prune(api, path, target, kind, roleid, narrow_role, narrow_path),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "roleid": roleid,
                            "narrow_role": narrow_role, "narrow_path": narrow_path})


@tool()
def pve_token_create(
    userid: str, tokenid: str, privsep: bool = True,
    comment: str | None = None, expire: int | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: create an API token for a user.

    Dry-run by default — the PLAN shows risk (privsep=False is HIGH: token inherits ALL owner perms).
    confirm=True to execute. The token secret (value) is returned ONCE to the caller and is NEVER
    written to the audit ledger. Synchronous.
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"token:{userid}!{tokenid}"
    # L03: pass expire+comment so the PLAN surface reflects what will actually be created
    plan = _plan("pve_token_create", tgt,
                 lambda: plan_token_create(userid, tokenid, privsep, expire=expire, comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    # SECRET HANDLING: return op result directly (carries the token value to caller);
    # detail dict must NEVER contain the secret — only {"confirmed": True} + non-secret params.
    return _audited("pve_token_create", tgt,
                    lambda: token_create(api, userid, tokenid, privsep, comment, expire),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "expire": expire, "privsep": privsep})


@tool()
def pve_token_revoke(userid: str, tokenid: str, confirm: bool = False) -> dict:
    """MUTATION (IRREVERSIBLE): permanently revoke an API token.

    Dry-run by default — the PLAN flags HIGH: revocation is permanent, the secret is gone forever.
    confirm=True to execute. Synchronous.
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"token:{userid}!{tokenid}"
    plan = _plan("pve_token_revoke", tgt, lambda: plan_token_revoke(userid, tokenid))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_token_revoke", tgt,
                    lambda: token_revoke(api, userid, tokenid),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- Access governance: users & groups ---

@tool()
def pve_user_get(userid: str) -> dict:
    """Get a user's full config (read-only). Returns userid, enabled flag, expiry, email, comment,
    group membership, API tokens, and firstname/lastname. Use pve_user_create/update/delete to
    modify the user; use pve_acl_list to see their effective permissions."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_user_get", f"user/{userid}", lambda: user_get(api, userid))


@tool()
def pve_groups_list() -> list[dict]:
    """List all Proxmox groups (read-only). Returns each group's id, comment, and member count.
    Use pve_group_get for full member list; use pve_group_create/update/delete to manage groups."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_groups_list", "access/groups", lambda: groups_list(api))


@tool()
def pve_group_get(groupid: str) -> dict:
    """Get a group's full config (read-only). Returns groupid, comment, and member list (users in
    the group). Use pve_group_create/update/delete to manage the group; use pve_acl_list to see
    ACL entries referencing this group."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_group_get", f"group/{groupid}", lambda: group_get(api, groupid))


@tool()
def pve_user_create(userid: str, comment: str | None = None, email: str | None = None,
                    enable: bool | None = None, expire: int | None = None,
                    groups: str | None = None, firstname: str | None = None,
                    lastname: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create a user. Dry-run by default (note: password is set separately — the user
    cannot log in until then). confirm=True to execute."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"user/{userid}"
    plan = _plan("pve_user_create", tgt,
                 lambda: plan_user_create(userid, comment, email, enable, expire, groups,
                                          firstname, lastname))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_user_create", tgt,
                    lambda: user_create(api, userid, comment, email, enable, expire,
                                       groups, firstname, lastname),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_user_update(userid: str, comment: str | None = None, email: str | None = None,
                    enable: bool | None = None, expire: int | None = None,
                    groups: str | None = None, firstname: str | None = None,
                    lastname: str | None = None, append: bool | None = None,
                    confirm: bool = False) -> dict:
    """MUTATION: update a user (enable=False stops login; group changes re-scope access).
    Dry-run by default. confirm=True to execute."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"user/{userid}"
    plan = _plan("pve_user_update", tgt,
                 lambda: plan_user_update(userid, comment, email, enable, expire, groups,
                                          firstname, lastname, append))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_user_update", tgt,
                    lambda: user_update(api, userid, comment, email, enable, expire,
                                       groups, firstname, lastname, append),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_user_delete(userid: str, confirm: bool = False) -> dict:
    """MUTATION (HIGH): delete a user. Dry-run by default — the PLAN reads the user's ACLs/tokens
    to show what access vanishes (permanent, no undo; admin = lockout risk). confirm=True."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"user/{userid}"
    plan = _plan("pve_user_delete", tgt, lambda: plan_user_delete(api, userid))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_user_delete", tgt,
                    lambda: user_delete(api, userid),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_group_create(groupid: str, comment: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create an (empty) group. Dry-run by default (additive, LOW risk).
    Returns the plan preview; confirm=True to execute. The group is inert until users are
    added or an ACL entry grants it privileges."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"group/{groupid}"
    plan = _plan("pve_group_create", tgt, lambda: plan_group_create(groupid, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_group_create", tgt,
                    lambda: group_create(api, groupid, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_group_update(groupid: str, comment: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: update a group's comment. Dry-run by default (additive, LOW risk).
    Returns the plan preview; confirm=True to execute. Does not modify group membership."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"group/{groupid}"
    plan = _plan("pve_group_update", tgt, lambda: plan_group_update(groupid, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_group_update", tgt,
                    lambda: group_update(api, groupid, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_group_delete(groupid: str, confirm: bool = False) -> dict:
    """MUTATION (HIGH): delete a group. Dry-run by default — the PLAN reads members and warns ACLs
    granted to/on the group are orphaned. confirm=True."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"group/{groupid}"
    plan = _plan("pve_group_delete", tgt, lambda: plan_group_delete(api, groupid))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_group_delete", tgt,
                    lambda: group_delete(api, groupid),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- Access governance: roles, realms, TFA ---

@tool()
def pve_realms_list() -> list[dict]:
    """List authentication realms/domains configured in Proxmox (read-only). Returns each realm's
    type (pam/pve/ldap/ad/openid), comment, TFA setting, and default flag. Use pve_realm_get for
    type-specific config; use pve_realm_create/update/delete to manage realms."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_realms_list", "access/domains", lambda: realms_list(api))


@tool()
def pve_realm_get(realm: str) -> dict:
    """Get a realm's full config (read-only). Returns realm type, comment, TFA requirement, and
    type-specific settings (server/base_dn for ldap; domain/server1 for ad; issuer-url/client-id
    for openid). Use pve_realm_create/update/delete to manage realms."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_realm_get", f"realm/{realm}", lambda: realm_get(api, realm))


@tool()
def pve_tfa_list() -> list[dict]:
    """List all per-user TFA (two-factor) entries across the cluster (read-only). Returns each
    entry's userid, factor type (totp/webauthn/yubico/recovery), factor id, and metadata. Use pve_tfa_get
    for one user's entries; use pve_tfa_delete (confirm=True) to remove a factor (RISK_HIGH)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_tfa_list", "access/tfa", lambda: tfa_list(api))


@tool()
def pve_tfa_get(userid: str, tfa_id: str | None = None) -> object:
    """Read a user's TFA entries (read-only). Returns list of entries if tfa_id is omitted; a
    single entry dict if tfa_id is specified. Each entry includes factor type, id, and metadata.
    Use pve_tfa_delete (confirm=True) to remove a factor (RISK_HIGH — can lock the user out)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_tfa_get", f"access/tfa/{userid}", lambda: tfa_get(api, userid, tfa_id))


@tool()
def pve_tfa_delete(
    userid: str, tfa_id: str, password: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION (HIGH RISK): delete a user's TFA factor. Dry-run by default — the PLAN shows how many
    factors remain and warns this WEAKENS the account (and can lock the user out if it's the last
    factor on a TFA-required realm). `password` (if PVE requires it) is passed through but never
    logged. confirm=True to execute.

    NOTE (live-verified PVE 9.1.7): PVE requires a ticket-based login session — NOT an API token —
    to mutate TFA, returning `403 ... need proper ticket` under token auth. Proximo is token-authed,
    so this delete will 403 on PVE; the read tools (pve_tfa_get/pve_tfa_list) work normally.
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"access/tfa/{userid}/{tfa_id}"
    plan = _plan("pve_tfa_delete", tgt, lambda: plan_tfa_delete(api, userid, tfa_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_tfa_delete", tgt,
                    lambda: tfa_delete(api, userid, tfa_id, password),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_role_create(roleid: str, privs: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create a custom role with an optional privilege set. Dry-run by default (MEDIUM
    risk — inert until an ACL entry references it). Returns the plan preview; confirm=True to
    execute. privs format: comma-separated privilege names (e.g. 'VM.PowerMgmt,VM.Config.Disk')."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"role/{roleid}"
    plan = _plan("pve_role_create", tgt, lambda: plan_role_create(roleid, privs))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_role_create", tgt,
                    lambda: role_create(api, roleid, privs),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_role_update(roleid: str, privs: str | None = None, append: bool | None = None,
                    confirm: bool = False) -> dict:
    """MUTATION: change a role's privileges. Dry-run by default — built-in roles (Administrator,
    PVEAdmin, …) are flagged HIGH (changing them re-scopes every ACL using them). confirm=True."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"role/{roleid}"
    plan = _plan("pve_role_update", tgt, lambda: plan_role_update(api, roleid, privs, append))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_role_update", tgt,
                    lambda: role_update(api, roleid, privs, append),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_role_delete(roleid: str, confirm: bool = False) -> dict:
    """MUTATION (HIGH): delete a role. Dry-run by default — the PLAN reads ACLs to count grants
    that will break, and refuses built-in roles. confirm=True."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"role/{roleid}"
    plan = _plan("pve_role_delete", tgt, lambda: plan_role_delete(api, roleid))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_role_delete", tgt,
                    lambda: role_delete(api, roleid),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_realm_create(realm: str, realm_type: str, comment: str | None = None,
                     options: dict | None = None, confirm: bool = False) -> dict:
    """MUTATION: create an auth realm. Dry-run by default; confirm=True to execute.
    `options` carries the type-specific fields PVE requires (ldap: server1/base_dn/user_attr;
    ad: domain/server1; openid: issuer-url/client-id) — passed verbatim; PVE validates them."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"realm/{realm}"
    plan = _plan("pve_realm_create", tgt,
                 lambda: plan_realm_create(realm, realm_type, comment, options))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_realm_create", tgt,
                    lambda: realm_create(api, realm, realm_type, comment, options),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_realm_update(realm: str, comment: str | None = None,
                     options: dict | None = None, confirm: bool = False) -> dict:
    """MUTATION: update a realm. Dry-run by default — built-in pam/pve realms are flagged HIGH
    (changing them risks breaking logins). confirm=True. `options` carries type-specific fields
    (server1/base_dn/etc.) passed verbatim; PVE validates them."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"realm/{realm}"
    plan = _plan("pve_realm_update", tgt, lambda: plan_realm_update(api, realm, comment, options))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_realm_update", tgt,
                    lambda: realm_update(api, realm, comment, options),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_realm_delete(realm: str, confirm: bool = False) -> dict:
    """MUTATION (HIGH, lockout-class): delete an auth realm. Dry-run by default — the PLAN reads
    users to count who can no longer log in, and refuses built-in pam/pve. confirm=True."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"realm/{realm}"
    plan = _plan("pve_realm_delete", tgt, lambda: plan_realm_delete(api, realm))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_realm_delete", tgt,
                    lambda: realm_delete(api, realm),
                    mutation=True, outcome="ok", detail={"confirmed": True})
