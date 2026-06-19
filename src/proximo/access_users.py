"""USERS & GROUPS governance pillar — PVE /access/users and /access/groups CRUD.

Dogfoods Proximo's trust thesis: every mutating operation has a plan_ factory that
surfaces the blast radius BEFORE any mutation fires.  The two high-stakes delete plans
(plan_user_delete, plan_group_delete) do safe reads to compute the affected set, and
mirror plan_migrate's read-failure honesty contract exactly:
  - If the read raises (unknown error): disclose uncertainty, keep RISK_HIGH, never
    imply safety from an absent warning.
  - If the read gives 404 (not found): say the delete will no-op/fail.

Hard rules carried from the codebase:
- Validators fire on every id before it enters a URL.
- Plans are HONEST — HIGH is maintained even when the op would fail; no false-safety claims.
- The absence of a HIGH flag is NOT a safety signal (curated, not exhaustive).
- No self-gating: the server layer adds confirm-gating + audit; these functions are pure ops.
- These ops are SYNCHRONOUS — no UPID; outcome is "ok", not "submitted".
- Do NOT edit access.py: _check_userid is imported from there.

Endpoint shape notes (confirm at live smoke):
  user_get:   GET /access/users/{userid}  → {userid, comment, email, enable, expire,
              groups (list or comma-sep), tokens (list), firstname, lastname, keys, ...}
              Smoke-confirm: exact field names and types (groups as list vs string).
  group_get:  GET /access/groups/{groupid} → {groupid, comment, members (list of userid)}
              Smoke-confirm: 'members' field name and whether it is always present.
  user_create / user_update:
              password is NOT set here — there is a separate /access/users/{userid}/passwd
              endpoint.  Creating a user without setting a password means they cannot log in
              via PAM/native auth until a password is set.
  user_update append param:
              Smoke-confirm: 'append' controls whether 'groups' is REPLACED or appended-to.
              append=1: add to existing group membership.  append=0 (default): replace.
  userid in path:
              userid contains '@' which is safe in URL path segments per RFC 3986.  We insert
              it raw (no URL-encoding) consistent with access.py's token endpoints.
              Smoke-confirm: verify PVE handles raw '@' in /access/users/{userid} path.
"""

from __future__ import annotations

import re

from .access import _check_userid
from .backends import ProximoError
from .planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM, Plan

# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

# groupid: letters/digits/underscore/hyphen; must START with alnum; no slash, no newline.
# Mirrors _HA_GROUP_RE in cluster_ops.py.
# \Z anchors past any trailing newline — never use $ for this purpose.
_GROUPID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}\Z")

# Freetext fields (comment, email, firstname, lastname) are stored in PVE's line-based
# config files.  A newline or other control character in one of these fields can corrupt
# that config.  Reject any control character (U+0000–U+001F, U+007F) without stripping
# first — the raw value is the injection surface.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _check_freetext(value: str, field: str) -> str:
    """Reject control characters in a freetext field (no .strip() — raw value is checked).

    Raises ProximoError if the value contains any control character (U+0000-U+001F or
    U+007F), which would corrupt PVE's line-based config if stored.

    Returns the value unchanged (as a str) when accepted.
    """
    s = str(value)
    if _CONTROL_RE.search(s):
        raise ProximoError(
            f"invalid {field}: {value!r} — control characters and newlines are not allowed"
        )
    return s


def _check_groupid(groupid: str) -> str:
    g = str(groupid).strip()
    if not _GROUPID_RE.match(g):
        raise ProximoError(
            f"invalid groupid: {groupid!r} — expected letters/digits/_/- only, "
            "starting with a letter or digit, no whitespace or special characters"
        )
    return g


def _check_groups_list(groups: str) -> str:
    """Validate a comma-separated list of group ids (at least one valid groupid)."""
    s = str(groups).strip()
    if not s:
        raise ProximoError("groups must not be empty")
    for g in s.split(","):
        _check_groupid(g.strip())
    return s


# ---------------------------------------------------------------------------
# READ operations — audited but not confirm-gated
# ---------------------------------------------------------------------------

def user_get(api, userid: str) -> dict:
    """Get full config for a single Proxmox user.

    GET /access/users/{userid}

    Returns a dict with user config + group membership + API tokens.
    Smoke-confirm: exact response shape (groups as list vs comma-sep string;
    presence/absence of 'tokens', 'firstname', 'lastname', 'keys' fields).
    """
    userid = _check_userid(userid)
    return api._get(f"/access/users/{userid}") or {}


def groups_list(api) -> list[dict]:
    """List all Proxmox groups.

    GET /access/groups

    Returns a list of group objects (groupid, comment, members count, ...).
    """
    return api._get("/access/groups") or []


def group_get(api, groupid: str) -> dict:
    """Get full config for a single Proxmox group, including member list.

    GET /access/groups/{groupid}

    Returns a dict with group config + members.
    Smoke-confirm: 'members' field name and whether it is always present
    (may be absent for empty groups on some PVE versions).
    """
    groupid = _check_groupid(groupid)
    return api._get(f"/access/groups/{groupid}") or {}


# ---------------------------------------------------------------------------
# MUTATION operations — validate params, build exact PVE URL, return result.
# These do NOT self-gate. The server layer adds confirm-gating + audit.
# ---------------------------------------------------------------------------

def user_create(
    api,
    userid: str,
    comment: str | None = None,
    email: str | None = None,
    enable: bool | None = None,
    expire: int | None = None,
    groups: str | None = None,
    firstname: str | None = None,
    lastname: str | None = None,
) -> object:
    """Create a new Proxmox user.

    POST /access/users
    Body: {userid, comment?, email?, enable?, expire?, groups?, firstname?, lastname?}

    groups: comma-separated group ids (e.g. "admins,ops").

    NOTE: password is NOT set by this endpoint.  There is a separate
    /access/users/{userid}/passwd endpoint for that.  A newly created user
    cannot log in via PAM/native auth until a password is set.

    Smoke-confirm: verify accepted body params and whether 'groups' accepts
    comma-separated ids or a list; verify synchronous vs async return.

    MUTATION — confirm-gated + audited at the server layer.
    """
    userid = _check_userid(userid)
    if groups is not None:
        groups = _check_groups_list(groups)
    data: dict = {"userid": userid}
    if comment is not None:
        data["comment"] = _check_freetext(comment, "comment")
    if email is not None:
        data["email"] = _check_freetext(email, "email")
    if enable is not None:
        data["enable"] = int(enable)
    if expire is not None:
        data["expire"] = int(expire)
    if groups is not None:
        data["groups"] = groups
    if firstname is not None:
        data["firstname"] = _check_freetext(firstname, "firstname")
    if lastname is not None:
        data["lastname"] = _check_freetext(lastname, "lastname")
    # MUTATION — confirm-gated + audited at the server layer.
    return api._post("/access/users", data)


def user_update(
    api,
    userid: str,
    comment: str | None = None,
    email: str | None = None,
    enable: bool | None = None,
    expire: int | None = None,
    groups: str | None = None,
    firstname: str | None = None,
    lastname: str | None = None,
    append: bool | None = None,
) -> object:
    """Update an existing Proxmox user.

    PUT /access/users/{userid}
    Body: {comment?, email?, enable?, expire?, groups?, firstname?, lastname?, append?}

    append: if True (1), adds the specified groups to existing membership rather than
    replacing it.  If False (0) or omitted, 'groups' REPLACES current group membership.
    Smoke-confirm: verify 'append' param name and semantics on the live PVE API.

    NOTE: password is NOT updated by this endpoint — see /access/users/{userid}/passwd.

    MUTATION — confirm-gated + audited at the server layer.
    """
    userid = _check_userid(userid)
    if groups is not None:
        groups = _check_groups_list(groups)
    data: dict = {}
    if comment is not None:
        data["comment"] = _check_freetext(comment, "comment")
    if email is not None:
        data["email"] = _check_freetext(email, "email")
    if enable is not None:
        data["enable"] = int(enable)
    if expire is not None:
        data["expire"] = int(expire)
    if groups is not None:
        data["groups"] = groups
    if firstname is not None:
        data["firstname"] = _check_freetext(firstname, "firstname")
    if lastname is not None:
        data["lastname"] = _check_freetext(lastname, "lastname")
    if append is not None:
        data["append"] = int(append)
    # MUTATION — confirm-gated + audited at the server layer.
    return api._put(f"/access/users/{userid}", data)


def user_delete(api, userid: str) -> object:
    """Delete a Proxmox user.

    DELETE /access/users/{userid}

    IRREVERSIBLE: the user, their tokens, and their direct ACL entries are permanently
    removed.  Any ACLs granted to this userid become orphaned.  There is no undo.

    MUTATION — confirm-gated + audited at the server layer.
    """
    userid = _check_userid(userid)
    # MUTATION — confirm-gated + audited at the server layer.
    return api._delete(f"/access/users/{userid}")


def group_create(api, groupid: str, comment: str | None = None) -> object:
    """Create a new Proxmox group.

    POST /access/groups
    Body: {groupid, comment?}

    MUTATION — confirm-gated + audited at the server layer.
    """
    groupid = _check_groupid(groupid)
    data: dict = {"groupid": groupid}
    if comment is not None:
        data["comment"] = str(comment)
    # MUTATION — confirm-gated + audited at the server layer.
    return api._post("/access/groups", data)


def group_update(api, groupid: str, comment: str | None = None) -> object:
    """Update a Proxmox group (currently only comment is updatable via this endpoint).

    PUT /access/groups/{groupid}
    Body: {comment?}

    MUTATION — confirm-gated + audited at the server layer.
    """
    groupid = _check_groupid(groupid)
    data: dict = {}
    if comment is not None:
        data["comment"] = str(comment)
    # MUTATION — confirm-gated + audited at the server layer.
    return api._put(f"/access/groups/{groupid}", data)


def group_delete(api, groupid: str) -> object:
    """Delete a Proxmox group.

    DELETE /access/groups/{groupid}

    IRREVERSIBLE: the group is permanently removed.  Members lose access that was
    derived from this group's ACL grants.  ACLs granted to this group become orphaned.

    MUTATION — confirm-gated + audited at the server layer.
    """
    groupid = _check_groupid(groupid)
    # MUTATION — confirm-gated + audited at the server layer.
    return api._delete(f"/access/groups/{groupid}")


# ---------------------------------------------------------------------------
# PLAN functions — pure factories; no mutation; the PLAN pillar.
# ---------------------------------------------------------------------------

def plan_user_create(
    userid: str,
    comment: str | None = None,
    email: str | None = None,
    enable: bool | None = None,
    expire: int | None = None,
    groups: str | None = None,
    firstname: str | None = None,
    lastname: str | None = None,
) -> Plan:
    """Preview creating a Proxmox user.

    PURE — no API call needed.

    RISK_MEDIUM: creating a user adds a new principal.  If groups are specified, the user
    inherits all ACL grants assigned to those groups — the scope of access granted to the
    user depends on what the specified groups can do.

    NOTE: password is NOT set by user_create — there is a separate /access/users/{userid}/passwd
    endpoint.  A newly created user cannot log in via PAM/native auth until a password is set.
    """
    userid = _check_userid(userid)
    if groups is not None:
        groups = _check_groups_list(groups)

    blast: list[str] = [
        f"creates user {userid!r} — adds a new principal to the Proxmox cluster",
        "NOTE: password is NOT set by this operation — the user cannot log in until a "
        "password is set separately via /access/users/{userid}/passwd",
    ]
    reasons: list[str] = ["creates a new principal — credentials must be set separately before login"]

    if groups:
        blast.append(
            f"user will be added to group(s): {groups!r} — inherits all ACL grants "
            "assigned to those groups; scope of access depends on group permissions"
        )
        reasons.append(
            f"group membership {groups!r} grants group-derived ACL permissions — "
            "verify group permissions before creating"
        )

    if enable is False or enable == 0:
        blast.append("enable=False: user account is DISABLED — they cannot log in until enabled")
        reasons.append("account disabled at creation — must be explicitly enabled before login")

    return Plan(
        action="pve_user_create",
        target=f"user:{userid}",
        change=f"create user {userid!r}"
               + (f" in groups {groups!r}" if groups else "")
               + (" (disabled)" if (enable is False or enable == 0) else ""),
        current={},
        blast_radius=blast,
        risk=RISK_MEDIUM,
        risk_reasons=reasons,
        note=(
            "password must be set separately before the user can log in via PAM/native auth; "
            "Smoke-confirm: verify POST /access/users body param names and 'groups' format "
            "(comma-sep string vs list) on a live PVE instance"
        ),
    )


def plan_user_update(
    userid: str,
    comment: str | None = None,
    email: str | None = None,
    enable: bool | None = None,
    expire: int | None = None,
    groups: str | None = None,
    firstname: str | None = None,
    lastname: str | None = None,
    append: bool | None = None,
) -> Plan:
    """Preview updating a Proxmox user.

    PURE — no API call needed.

    RISK_MEDIUM: updating user config may affect login capability or permission scope.
    Key escalations:
    - enable=False: the user can no longer log in.
    - groups changed: the user's ACL/permission scope changes (may gain or lose access).
    - append=False (default) with groups: REPLACES current group membership; may remove access.
    - append=True with groups: ADDS to current membership; may grant additional access.

    Smoke-confirm: verify 'append' param name and semantics on live PVE API.
    """
    userid = _check_userid(userid)
    if groups is not None:
        groups = _check_groups_list(groups)

    blast: list[str] = [f"updates user {userid!r}"]
    reasons: list[str] = ["modifies a user's config — may change login capability or permissions"]

    if enable is not None and (enable is False or enable == 0):
        blast.append(
            f"enable=False: user {userid!r} can NO LONGER LOG IN — "
            "all sessions/tokens still exist but new logins are blocked"
        )
        reasons.append("setting enable=False blocks login for this user immediately")

    if groups is not None:
        if append:
            blast.append(
                f"append=True: ADDS to group membership — user will also belong to {groups!r}; "
                "group-derived ACL scope may expand"
            )
            reasons.append(
                f"adding groups {groups!r} may widen the user's effective permissions via group ACLs"
            )
        else:
            blast.append(
                f"groups={groups!r} (append not set or False): REPLACES current group membership — "
                "user loses access derived from any groups not in the new list; "
                "Smoke-confirm: verify append=0 vs omit-append both replace (not append)"
            )
            reasons.append(
                "replacing group membership may REMOVE group-derived ACL grants for removed groups"
            )

    if not blast[1:]:
        # Only the header line was added; no notable escalations.
        blast.append("no login-blocking or group-membership changes detected in this update")
        reasons[0] = "modifies metadata fields only (comment, email, name) — no access-scope change expected"

    return Plan(
        action="pve_user_update",
        target=f"user:{userid}",
        change=f"update user {userid!r}"
               + (f" enable={enable}" if enable is not None else "")
               + (f" groups={groups!r}" if groups is not None else ""),
        current={},
        blast_radius=blast,
        risk=RISK_MEDIUM,
        risk_reasons=reasons,
        note=(
            "Smoke-confirm: verify 'append' param semantics (append=1 adds vs replace) on live PVE; "
            "verify PUT /access/users/{userid} accepted body params"
        ),
    )


def plan_user_delete(api, userid: str) -> Plan:
    """Preview deleting a Proxmox user.  RISK_HIGH.

    Reads TWICE to compute blast radius:
      1. user_get(userid): confirms the user exists; surfaces their API tokens.
      2. access_acl_list: filters for ACL entries where ugid == userid to show orphaned grants.

    Each read has its own try/except and honesty contract (mirroring plan_migrate exactly):
    - Read raises (not a 404): disclose uncertainty — the absence of a warning is NOT a safety
      signal; stay RISK_HIGH.
    - Read gives 404 (user not found): say the delete will no-op/fail; stay RISK_HIGH.

    IRREVERSIBLE: deleting a user permanently removes them, their tokens, and orphans any ACLs
    granted to them.  Anyone relying on this principal loses access.  If this is an admin user,
    that is a lockout risk.  There is no undo — snapshot-based undo does NOT apply to user ops.
    """
    userid = _check_userid(userid)

    blast: list[str] = []
    reasons: list[str] = []
    risk = RISK_HIGH  # HIGH maintained on every branch — no undo, no false-safety

    # ------------------------------------------------------------------
    # READ 1: user_get — existence + tokens
    # Three outcomes: success, 404 (not found), other error (uncertainty)
    # ------------------------------------------------------------------
    user_data: dict = {}
    user_read_failed = False
    user_not_found = False
    try:
        user_data = api._get(f"/access/users/{userid}") or {}
    except Exception as e:
        resp = getattr(e, "response", None)
        if resp is not None and getattr(resp, "status_code", None) == 404:
            user_not_found = True
        else:
            user_read_failed = True

    if user_not_found:
        blast.append(
            f"delete will NO-OP or FAIL — user {userid!r} not found; "
            "nothing would be removed"
        )
        blast.append(
            "user deletion is IRREVERSIBLE — no undo path exists; "
            "in this case the user was not found, so nothing would be removed"
        )
        reasons.append(
            f"user {userid!r} not found — delete will be rejected by PVE; "
            "RISK_HIGH maintained: not-found does not mean safe"
        )
        reasons.append("user deletion is permanent — no undo path exists")
        # Return early — no point reading ACLs for a non-existent user.
        return Plan(
            action="pve_user_delete",
            target=f"user:{userid}",
            change=f"delete user {userid!r}",
            current={},
            blast_radius=blast,
            risk=risk,
            risk_reasons=reasons,
            note="delete will fail — user not found",
        )

    if user_read_failed:
        blast.append(
            f"could NOT confirm state of user {userid!r} — if the user exists, this PERMANENTLY "
            "removes them, their tokens, and orphans their ACL entries; "
            "absence of a token/ACL warning is NOT a safety signal"
        )
        reasons.append(
            f"user_get for {userid!r} failed — token count and existence unconfirmed; "
            "RISK_HIGH maintained: uncertainty is not a safety signal"
        )
    else:
        # Successful user read — surface token count from the response.
        # VERIFIED live (PVE 9.1.7, 2026-06-08): /access/users/{id} returns `tokens` as a
        # DICT keyed by token-id (e.g. {"claude": {...}}), NOT a list — count its keys.
        # (list handled too, defensively, in case a PVE version differs.)
        tokens = user_data.get("tokens") or {}
        token_count = len(tokens) if isinstance(tokens, (list, dict)) else 0
        token_note = (
            f"{token_count} API token(s) will be PERMANENTLY revoked"
            if token_count
            else "no API tokens found"
        )
        blast.append(
            f"PERMANENTLY deletes user {userid!r} — the user principal is gone forever"
        )
        blast.append(token_note)
        if token_count:
            blast.append(
                "any service or integration using those tokens will IMMEDIATELY lose Proxmox API access"
            )
        blast.append(
            "all ACL entries granted TO this user will be orphaned — "
            "anyone relying on this principal's access will lose it"
        )
        if user_data.get("email"):
            blast.append(f"email on file: {user_data['email']!r}")
        reasons.append(
            f"deleting {userid!r} permanently removes the principal and {token_count} token(s)"
        )

    # ------------------------------------------------------------------
    # READ 2: ACL list — orphaned grants (independent read + honesty)
    # ------------------------------------------------------------------
    acl_read_failed = False
    acl_entries: list[dict] = []
    try:
        from .access import access_acl_list
        acl_entries = access_acl_list(api) or []
    except Exception:
        acl_read_failed = True

    if acl_read_failed:
        blast.append(
            "could NOT read ACL list — cannot enumerate which ACL entries would be orphaned; "
            "absence of an ACL-orphan warning is NOT a safety signal"
        )
        reasons.append(
            "ACL read failed — orphaned grants cannot be enumerated; "
            "absence of a warning is not a safety signal"
        )
    else:
        user_acls = [e for e in acl_entries if e.get("ugid") == userid]
        if user_acls:
            paths = sorted({e.get("path", "?") for e in user_acls})
            blast.append(
                f"ACL entries on {len(user_acls)} path(s) will be orphaned: "
                + ", ".join(paths)
            )
            reasons.append(
                f"{len(user_acls)} ACL grant(s) to {userid!r} at "
                + ", ".join(paths)
                + " will be orphaned"
            )
            # Extra lockout warning if any ACL is at root or carries Administrator
            for e in user_acls:
                if e.get("path") == "/" or e.get("roleid") == "Administrator":
                    blast.append(
                        "LOCKOUT RISK: this user holds an Administrator or root-path ACL — "
                        "deleting an admin user may lock out cluster management"
                    )
                    reasons.append(
                        "user holds Administrator or root-scope ACL — lockout risk if sole admin"
                    )
                    break
        else:
            blast.append("no direct ACL entries found for this user in the current ACL list")
            reasons.append("no ACL entries found for this user")

    blast.append(
        "IRREVERSIBLE: snapshot-based undo does NOT apply to user deletion; "
        "there is no way to recover a deleted user or their tokens"
    )
    reasons.append("user deletion is permanent — no undo path exists")

    current: dict = {}
    if user_data:
        current = {k: user_data[k] for k in ("email", "enable", "expire") if k in user_data}

    return Plan(
        action="pve_user_delete",
        target=f"user:{userid}",
        change=f"permanently delete user {userid!r} and all associated tokens/ACL entries",
        current=current,
        blast_radius=blast,
        risk=risk,
        risk_reasons=reasons,
        note=(
            "Smoke-confirm: user_get response shape (tokens field name/type); "
            "user deletion is synchronous — no UPID; there is NO UNDO"
        ),
    )


def plan_group_create(groupid: str, comment: str | None = None) -> Plan:
    """Preview creating a Proxmox group.

    PURE — no API call needed.

    RISK_LOW: creating an empty group is purely additive.  The group has no members and
    no ACL grants at creation time — it is harmless until members are added and/or ACLs
    are granted to it.
    """
    groupid = _check_groupid(groupid)

    return Plan(
        action="pve_group_create",
        target=f"group:{groupid}",
        change=f"create group {groupid!r}"
               + (f" comment={comment!r}" if comment is not None else ""),
        current={},
        blast_radius=[
            f"creates group {groupid!r} — an empty group; no members, no ACL grants at creation",
            "additive: no existing access is changed",
        ],
        risk=RISK_LOW,
        risk_reasons=["creates an empty group — purely additive; no members or ACLs until explicitly set"],
    )


def plan_group_update(groupid: str, comment: str | None = None) -> Plan:
    """Preview updating a Proxmox group.

    PURE — no API call needed.

    RISK_LOW/MEDIUM: updating a group comment is low impact.  If future params affect
    membership or ACL grants, risk would increase — for comment-only updates, LOW is accurate.
    """
    groupid = _check_groupid(groupid)

    return Plan(
        action="pve_group_update",
        target=f"group:{groupid}",
        change=f"update group {groupid!r}"
               + (f" comment={comment!r}" if comment is not None else ""),
        current={},
        blast_radius=[
            f"updates group {groupid!r} — modifies metadata only (comment)",
            "member list and ACL grants are NOT changed by this operation",
        ],
        risk=RISK_LOW,
        risk_reasons=["comment-only update — no membership or access-scope change"],
        note=(
            "Smoke-confirm: verify PUT /access/groups/{groupid} accepted params; "
            "if PVE exposes membership-update here, risk may be higher"
        ),
    )


def plan_group_delete(api, groupid: str) -> Plan:
    """Preview deleting a Proxmox group.  RISK_HIGH.

    Reads group_get to enumerate current members.  Mirrors plan_migrate's read-failure
    honesty contract exactly:
    - Read raises (not a 404): disclose uncertainty, keep RISK_HIGH.
    - Read gives 404 (group not found): say delete will no-op/fail, keep RISK_HIGH.
    - Static note (no read needed): ACLs granted ON or TO this group become orphaned;
      all members lose the access they derived from group-level grants.

    IRREVERSIBLE: the group is permanently removed.  There is no undo.
    """
    groupid = _check_groupid(groupid)

    blast: list[str] = []
    reasons: list[str] = []
    risk = RISK_HIGH  # HIGH on every branch

    # ------------------------------------------------------------------
    # ONE SAFE READ: group_get — members + existence
    # Three outcomes: success, 404 (not found), other error (uncertainty)
    # ------------------------------------------------------------------
    group_data: dict = {}
    read_failed = False
    not_found = False
    try:
        group_data = api._get(f"/access/groups/{groupid}") or {}
    except Exception as e:
        resp = getattr(e, "response", None)
        if resp is not None and getattr(resp, "status_code", None) == 404:
            not_found = True
        else:
            read_failed = True

    if not_found:
        blast.append(
            f"delete will NO-OP or FAIL — group {groupid!r} not found; "
            "nothing would be removed"
        )
        reasons.append(
            f"group {groupid!r} not found — delete will be rejected by PVE; "
            "RISK_HIGH maintained: not-found does not mean safe"
        )
        return Plan(
            action="pve_group_delete",
            target=f"group:{groupid}",
            change=f"delete group {groupid!r}",
            current={},
            blast_radius=blast,
            risk=risk,
            risk_reasons=reasons,
            note="delete will fail — group not found",
        )

    if read_failed:
        blast.append(
            f"could NOT confirm state of group {groupid!r} — if the group exists, this "
            "PERMANENTLY removes it; member count and ACL impact are unconfirmed; "
            "absence of a member/ACL warning is NOT a safety signal"
        )
        reasons.append(
            f"group_get for {groupid!r} failed — member list unconfirmed; "
            "RISK_HIGH maintained: uncertainty is not a safety signal"
        )
    else:
        members = group_data.get("members") or []
        members_is_list = isinstance(members, list)
        member_count = len(members) if members_is_list else 0
        blast.append(
            f"PERMANENTLY deletes group {groupid!r} — the group is gone forever"
        )
        if not members_is_list:
            blast.append(
                "member shape was unconfirmed (PVE returned a non-list value for 'members') — "
                "member count may be unavailable; this does NOT mean the group is empty; "
                "Smoke-confirm: 'members' field type on live PVE"
            )
            reasons.append(
                "members field was not a list — member count unconfirmed; "
                "RISK_HIGH maintained: unconfirmed shape is not a safety signal"
            )
        elif member_count:
            blast.append(
                f"{member_count} member(s) ({', '.join(str(m) for m in members[:5])}"
                + (" ..." if member_count > 5 else "")
                + ") will LOSE all access derived from this group's ACL grants"
            )
            reasons.append(
                f"{member_count} group member(s) lose group-derived ACL grants immediately"
            )
        else:
            blast.append(
                "no members found in group (Smoke-confirm: 'members' field name/presence "
                "for empty groups)"
            )
            reasons.append("group appears empty — no members found")

    # Blast radius: read the ACL and NAME the group-level grants that orphan (the access members lose).
    affected: list[dict] = []
    complete = True
    try:
        acl_entries = api._get("/access/acl") or []
        grants = [e for e in acl_entries if e.get("type") == "group" and e.get("ugid") == groupid]
        for e in grants:
            affected.append({"principal": f"group {groupid}", "path": str(e.get("path", "")),
                             "roleid": str(e.get("roleid", "")), "change": "orphaned", "severity": "high"})
        if grants:
            named = ", ".join(sorted(f"{e.get('roleid', '')}@{e.get('path', '')}" for e in grants))
            blast.append(
                f"{len(grants)} ACL grant(s) to group {groupid!r} ORPHAN on deletion — members lose: {named}"
            )
        else:
            blast.append(
                f"0 ACL grants currently target group {groupid!r} — members lose no group-derived access"
            )
    except Exception as exc:
        complete = False
        check_error = "404" if getattr(getattr(exc, "response", None), "status_code", None) == 404 \
            else type(exc).__name__
        blast.append(
            f"could NOT read the ACL ({check_error}) — cannot name the group grants that orphan; "
            "absence of a list is NOT a safety signal"
        )
        reasons.append(f"ACL read failed ({check_error}) — orphaned-grants list unknown")

    # Static analysis — always true regardless of read result
    blast.append(
        f"ACL entries granted ON /access/groups/{groupid} or TO this group will be ORPHANED — "
        "any access previously derived from these grants is immediately lost"
    )
    reasons.append(
        "group-level ACL grants are orphaned on deletion — affected members lose group-derived access"
    )
    blast.append(
        "IRREVERSIBLE: snapshot-based undo does NOT apply to group deletion; "
        "there is no way to recover a deleted group"
    )
    reasons.append("group deletion is permanent — no undo path exists")

    current: dict = {}
    if group_data:
        current = {k: group_data[k] for k in ("comment",) if k in group_data}

    return Plan(
        action="pve_group_delete",
        target=f"group:{groupid}",
        change=f"permanently delete group {groupid!r} and orphan its ACL grants",
        current=current,
        blast_radius=blast,
        risk=risk,
        risk_reasons=reasons,
        affected=affected,
        complete=complete,
        note=(
            "Smoke-confirm: group_get response shape ('members' field name and whether "
            "it is present for empty groups); "
            "group deletion is synchronous — no UPID; there is NO UNDO"
        ),
    )
