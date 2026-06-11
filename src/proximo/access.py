"""ACCESS GOVERNANCE pillar — ACL, roles, users, and API tokens.

The trust-layer differentiator: Proxmox ACL semantics are non-obvious in one
critical way — a specific-path ACL entry REPLACES any inherited (propagated) grant
from an ancestor path; it does NOT union with it. Granting can silently narrow
access; revoking a specific entry can silently widen it. plan_acl_modify surfaces
both the SHADOW (loss of inherited privileges) and WIDEN effects BEFORE any
mutation is made — the gotcha that cost a real production cycle.

Hard rules mirrored from the codebase:
- Validators fire on every path/id component before it enters a URL.
- Plans are HONEST — HIGH is maintained even when the op would fail; no false-safety claims.
- The absence of a HIGH flag is NOT a safety signal (curated, not exhaustive).
- No self-gating: the server layer adds confirm-gating + audit; these functions are pure ops.
- Secrets: token values are NEVER written to any plan or ledger detail dict.
  A created token's value surfaces ONCE in the create result and nowhere else.
- UNDO: token_revoke is irreversible; snapshot-based undo does NOT apply to ACL/token ops.
  Never claim undo capability that the platform cannot deliver.
- ACL modify (both grant and revoke) uses PUT /access/acl — there is no per-entry
  DELETE endpoint in Proxmox. Revoke sets delete=1 in the PUT body.
- These ops are SYNCHRONOUS — no UPID; outcome is "ok", not "submitted".

Endpoint shape note:
  ApiBackend exposes _get/_post/_delete/_put. acl_modify uses api._put() for
  the PUT /access/acl call. Confirm the PUT path and body params at live smoke
  (see docstring on acl_modify).
"""

from __future__ import annotations

import re

from .backends import ProximoError
from .planning import RISK_HIGH, RISK_MEDIUM, Plan

# ---------------------------------------------------------------------------
# Validators (module-local)
# ---------------------------------------------------------------------------

# userid: "user@realm" or just "user" (realm is optional for some forms).
# Characters: alnum, dot, underscore, hyphen. No traversal, no newlines.
# \Z anchors past any trailing newline.
_USERID_RE = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+\Z")

# tokenid: alphanumeric + hyphen/underscore (PVE's own naming rule for tokens).
_TOKENID_RE = re.compile(r"^[A-Za-z0-9._-]+\Z")

# roleid: e.g. "PVEVMAdmin", "Administrator", custom names.
_ROLEID_RE = re.compile(r"^[A-Za-z0-9._-]+\Z")

# ACL path: "/"  or  "/" + slash-separated segments (no "..", no trailing slash, no spaces).
# An ACL path of "/" alone is the root (highest blast — all resources).
_ACL_PATH_RE = re.compile(r"^/([A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*)?\Z")


def _check_userid(userid: str) -> str:
    s = str(userid).strip()
    if not _USERID_RE.match(s):
        raise ProximoError(
            f"invalid userid: {userid!r} — expected user@realm "
            "(letters/digits/._- only; no path separators or whitespace)"
        )
    return s


def _check_tokenid(tokenid: str) -> str:
    s = str(tokenid).strip()
    if not _TOKENID_RE.match(s):
        raise ProximoError(
            f"invalid tokenid: {tokenid!r} — expected letters/digits/._- only"
        )
    return s


def _check_roleid(roleid: str) -> str:
    s = str(roleid).strip()
    if not _ROLEID_RE.match(s):
        raise ProximoError(
            f"invalid roleid: {roleid!r} — expected letters/digits/._- only"
        )
    return s


def _check_roles(roles: str) -> str:
    """Validate a comma-separated role list (at least one valid roleid)."""
    s = str(roles).strip()
    if not s:
        raise ProximoError("roles must not be empty")
    for r in s.split(","):
        _check_roleid(r.strip())
    return s


def _check_acl_path(path: str) -> str:
    s = str(path).strip()
    if ".." in s:
        raise ProximoError(f"invalid ACL path: {path!r} (path traversal rejected)")
    if not _ACL_PATH_RE.match(s):
        raise ProximoError(
            f"invalid ACL path: {path!r} — expected '/' or '/segment/…/segment' "
            "(letters/digits/._- only; no trailing slash; no spaces)"
        )
    return s


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_root_or_broad(acl_path: str) -> bool:
    """True for the two highest-blast ACL scopes: / (root) and /storage (all datastores)."""
    return acl_path in ("/", "/storage")


def _is_administrator_role(roles: str) -> bool:
    """True if the comma-separated roles list includes 'Administrator' (PVE's super-role)."""
    return "Administrator" in {r.strip() for r in roles.split(",")}


# ---------------------------------------------------------------------------
# Read operations — audited but not confirm-gated
# ---------------------------------------------------------------------------

def access_users_list(api) -> list[dict]:
    """List all Proxmox users.

    GET /access/users

    Returns a list of user objects (userid, comment, email, enable, expire, groups, …).
    Audited at the server layer.
    """
    return api._get("/access/users") or []


def access_roles_list(api) -> list[dict]:
    """List all Proxmox roles and their privileges.

    GET /access/roles

    Returns a list of role objects (roleid, privs map, …).
    Audited at the server layer.
    """
    return api._get("/access/roles") or []


def access_acl_list(api) -> list[dict]:
    """List all ACL entries on the Proxmox cluster.

    GET /access/acl

    Returns a list of ACL entry objects (path, roleid, ugid (user/group/token),
    type (user|group|token), propagate).
    Audited at the server layer.
    """
    return api._get("/access/acl") or []


def access_tokens_list(api, userid: str) -> list[dict]:
    """List API tokens for a specific user.

    GET /access/users/{userid}/token

    Returns a list of token objects (tokenid, comment, expire, privsep).
    NOTE: the token secret (value) is never returned by this endpoint — it is
    shown ONLY once at token creation time.

    Shape note: {userid} is URL-encoded by PVE on its side; we validate the
    userid here (character set + realm format) but do NOT additionally URL-encode
    it before inserting into the path — Proxmox's own implementation uses the
    raw user@realm string in the path. Confirm at live smoke.
    """
    userid = _check_userid(userid)
    return api._get(f"/access/users/{userid}/token") or []


# ---------------------------------------------------------------------------
# Diagnostic: over-broad grants
# ---------------------------------------------------------------------------

def access_overbroad_grants(api) -> list[dict]:
    """Surface over-broad ACL grants as a first-class diagnostic.

    An 'over-broad' grant is one where:
      - The roleid is 'Administrator' (the PVE super-role with all privileges), OR
      - The ACL path is '/' (root — affects every resource on the cluster).

    These are not necessarily wrong, but they warrant explicit review.

    READ — no mutation, no confirm required. Audited at the server layer.

    Returns a list of dicts with keys: path, ugid, roleid, type, propagate,
    reason (why it's flagged).
    """
    acl_entries = access_acl_list(api)
    flagged = []
    for entry in acl_entries:
        path = entry.get("path", "")
        roleid = entry.get("roleid", "")
        reasons = []
        if roleid == "Administrator":
            reasons.append(
                "Administrator role grants ALL privileges (super-role); "
                "prefer a least-privilege role scoped to the specific task"
            )
        if path == "/":
            reasons.append(
                "ACL at '/' affects EVERY resource on the cluster — widest possible scope"
            )
        if reasons:
            flagged.append({
                "path": path,
                "ugid": entry.get("ugid", ""),
                "roleid": roleid,
                "type": entry.get("type", ""),
                "propagate": entry.get("propagate", True),
                "reasons": reasons,
            })
    return flagged


# ---------------------------------------------------------------------------
# Mutation operations — validate params, build exact PVE URL, return result.
# These do NOT self-gate. The server layer adds confirm-gating + audit.
# ---------------------------------------------------------------------------

def acl_modify(
    api,
    path: str,
    roles: str,
    target: str,
    kind: str = "user",
    propagate: bool = True,
    delete: bool = False,
) -> None:
    """Grant or revoke an ACL entry.

    PUT /access/acl
    Body: {path, roles, users|tokens, propagate, delete}

    kind must be 'user' or 'token'.
    delete=False: grant; delete=True: revoke the entry.

    Proxmox uses a single PUT /access/acl for BOTH grant and revoke — there is
    no per-entry DELETE endpoint. Revoke is indicated by delete=1 in the body.

    Returns None (synchronous — no UPID).

    Endpoint shape notes (confirm at live smoke):
    - PUT /access/acl is the documented PVE API endpoint for all ACL writes.
    - The 'users' body param accepts a comma-separated list of user@realm strings.
    - The 'tokens' body param accepts a comma-separated list of user@realm!tokenid strings.
    - 'propagate' applies the entry recursively down the path hierarchy if True.

    MUTATION — confirm-gated + audited at the server layer.
    """
    path = _check_acl_path(path)
    roles = _check_roles(roles)
    if kind not in ("user", "token"):
        raise ProximoError(f"invalid kind: {kind!r} (expected 'user' or 'token')")
    # Validate the target according to kind.
    if kind == "user":
        target = _check_userid(target)
    else:
        # token kind: expected format "user@realm!tokenid"
        if "!" not in target:
            raise ProximoError(
                f"invalid token target: {target!r} — expected 'user@realm!tokenid'"
            )
        user_part, _, token_part = target.partition("!")
        _check_userid(user_part)
        _check_tokenid(token_part)

    data: dict = {
        "path": path,
        "roles": roles,
        "propagate": int(propagate),
        "delete": int(delete),
    }
    if kind == "user":
        data["users"] = target
    else:
        data["tokens"] = target

    # MUTATION — confirm-gated + audited at the server layer.
    return api._put("/access/acl", data)


def token_create(
    api,
    userid: str,
    tokenid: str,
    privsep: bool = True,
    comment: str | None = None,
    expire: int | None = None,
) -> dict:
    """Create an API token for a user.

    POST /access/users/{userid}/token/{tokenid}

    privsep=True (default, SAFER): the token's privileges are limited to the
    roles/ACLs assigned DIRECTLY to it. privsep=False: the token inherits all
    of the owner user's permissions — effectively granting the owner's full privilege set.

    Returns a dict with keys: value (the token secret — shown ONCE), info (metadata).
    Callers must show the 'value' to the user and warn it cannot be retrieved again.
    The value must NEVER be written to the audit ledger.

    Returns result immediately (synchronous — no UPID).

    MUTATION — confirm-gated + audited at the server layer.
    The audit record must NOT include the token value in its detail dict.
    """
    userid = _check_userid(userid)
    tokenid = _check_tokenid(tokenid)
    data: dict = {"privsep": int(privsep)}
    if comment is not None:
        data["comment"] = str(comment)
    if expire is not None:
        data["expire"] = int(expire)
    # POST /access/users/{userid}/token/{tokenid}
    # userid contains '@' which is safe in URL path per RFC 3986; PVE handles it natively.
    result = api._post(f"/access/users/{userid}/token/{tokenid}", data)
    # result is expected to be {"value": "<secret>", "info": {...}}
    return result or {}


def token_revoke(api, userid: str, tokenid: str) -> None:
    """Revoke (permanently delete) an API token.

    DELETE /access/users/{userid}/token/{tokenid}

    IRREVERSIBLE: the token secret is gone forever. There is no undo.
    Do NOT call this with the intent to undo — it cannot be undone.

    Returns None (synchronous — no UPID).

    MUTATION — confirm-gated + audited at the server layer.
    """
    userid = _check_userid(userid)
    tokenid = _check_tokenid(tokenid)
    return api._delete(f"/access/users/{userid}/token/{tokenid}")


# ---------------------------------------------------------------------------
# Plan functions — pure analysis; return a Plan the caller can inspect.
# ---------------------------------------------------------------------------

def plan_acl_modify(
    api,
    path: str,
    roles: str,
    target: str,
    kind: str = "user",
    propagate: bool = True,
    delete: bool = False,
) -> Plan:
    """Preview what an ACL change does — the killer feature.

    THE CRITICAL PROXMOX GOTCHA: a specific-path ACL entry REPLACES any
    inherited (propagated) grant from an ancestor path. It does NOT union with it.
    This means:
      - GRANTING can NARROW access: if the target currently has broad inherited
        privileges (e.g. Administrator at /), a new specific entry at /vms/100
        with fewer privileges SHADOWS the inherited grant — the inherited grant no
        longer applies at /vms/100.
      - REVOKING a specific entry can WIDEN access: if you remove a specific entry,
        the target falls back to a broader inherited grant that was being shadowed.

    This plan:
      1. Reads the current ACL (one safe read; errors are disclosed, not swallowed).
      2. Computes SHADOW: inherited privileges that would be LOST at `path` due to
         the new specific entry replacing the inherited grant (grant path).
         For revoke path: inherited grants that would be RESTORED (i.e., WIDENED).
      3. Computes WIDEN: privileges the new entry adds that the target didn't have.
      4. Flags HIGH risk for: Administrator role, root path (/), or any detected shadow.
      5. Flags HIGH risk when revoke widens access (restores a broader inherited grant).

    Validates inputs even on the plan path — same as all other plan functions.
    """
    path = _check_acl_path(path)
    roles = _check_roles(roles)
    if kind not in ("user", "token"):
        raise ProximoError(f"invalid kind: {kind!r} (expected 'user' or 'token')")
    if kind == "user":
        target = _check_userid(target)
    else:
        if "!" not in target:
            raise ProximoError(
                f"invalid token target: {target!r} — expected 'user@realm!tokenid'"
            )
        user_part, _, token_part = target.partition("!")
        _check_userid(user_part)
        _check_tokenid(token_part)

    new_roles = {r.strip() for r in roles.split(",")}
    action_word = "revoke" if delete else "grant"

    # ------------------------------------------------------------------
    # ONE SAFE READ: current ACL state.
    # Three outcomes: success, failure (disclose, don't swallow).
    # ------------------------------------------------------------------
    acl_entries: list[dict] = []
    check_error: str | None = None
    try:
        acl_entries = access_acl_list(api) or []
    except Exception as e:
        check_error = type(e).__name__

    # ------------------------------------------------------------------
    # Analyse what the target currently sees at `path` (inherited + direct).
    # An ACL entry at an ancestor path with propagate=True bleeds down.
    # An existing direct entry at `path` for this target is what we'd replace.
    # ------------------------------------------------------------------
    current_direct_entries: list[dict] = []  # ALL direct entries for target at path
    inherited_entries: list[dict] = []        # ancestor propagated entries for target

    if check_error is None:
        for entry in acl_entries:
            ugid = entry.get("ugid", "")
            entry_path = entry.get("path", "")
            entry_propagate = entry.get("propagate", True)
            # Match this entry to our target (user or token kind check is implicit via ugid).
            if ugid != target:
                continue
            if entry_path == path:
                current_direct_entries.append(entry)
            elif path.startswith(entry_path.rstrip("/") + "/") and entry_propagate:
                # This ancestor entry propagates into our path.
                inherited_entries.append(entry)

    # Inherited roles (those bleeding into our path from ancestors).
    inherited_roles: set[str] = set()
    for e in inherited_entries:
        inherited_roles.add(e.get("roleid", ""))

    # Direct roles at this path (before our change) — accumulate ALL, not just the last.
    current_direct_roles: set[str] = {e.get("roleid", "") for e in current_direct_entries}
    has_direct = bool(current_direct_entries)

    # Effective roles at path BEFORE the change:
    # If there's any direct entry, it ALREADY shadows inherited ones — inherited don't apply.
    # If there's no direct entry, inherited roles apply.
    effective_before: set[str] = (
        current_direct_roles if has_direct else inherited_roles
    )

    # Effective roles AFTER the change:
    if not delete:
        # Grant: PUT /access/acl adds the specified role(s) at path.
        # PVE tracks one entry per (user, path, role) — adding a role does NOT remove OTHER
        # existing same-path roles; each role is a separate ACL record. However, adding a new
        # specific entry at this path DOES shadow any inherited (ancestor) grants that were
        # previously bleeding down (because a direct entry takes precedence over inheritance).
        # Therefore: effective_after = (existing direct roles) ∪ (new roles), minus the
        # inherited roles that are now shadowed by having any direct entry at all.
        # Simplification: we can only accurately predict shadow for the case where there was
        # NO prior direct entry (inherited-only case) — that is the PVE gotcha.
        # If there's already a direct entry, the target already had a direct entry shadowing
        # inherited grants, so adding more roles there doesn't change the shadow status.
        effective_after = new_roles
    else:
        # Revoke: remove the specified role(s) from the direct entries.
        # If OTHER direct roles for this target remain at this path, those roles STILL shadow
        # the inherited grants — inherited access does NOT come back in that case.
        # Only when NO direct roles remain does the target fall back to inherited roles.
        remaining_direct = current_direct_roles - new_roles
        effective_after = remaining_direct if remaining_direct else inherited_roles

    # SHADOW: inherited roles that DISAPPEAR because a new direct entry shadows them.
    # ONLY meaningful when transitioning from inherited-only (no prior direct entry) to a
    # specific-path entry. If there was already a direct entry, inherited were already shadowed.
    shadowed_inherited = inherited_roles - new_roles if not has_direct and not delete else set()
    # SHADOW from same-path replacement is NOT computed — PVE unions same-path roles, not replaces.

    # WIDEN: roles that APPEAR in the effective set at path (newly gained).
    widened = effective_after - effective_before

    # ------------------------------------------------------------------
    # Build blast radius and risk.
    # ------------------------------------------------------------------
    blast: list[str] = []
    reasons: list[str] = []
    risk = RISK_MEDIUM

    if check_error is not None:
        blast.append(
            f"could NOT read current ACL ({check_error}) — cannot determine what privileges "
            "would be shadowed or widened; absence of a shadow/widen warning is NOT a safety signal"
        )
        reasons.append(
            "ACL read failed — shadow/widen analysis unavailable; absence of a warning is not a safety signal"
        )
        risk = RISK_HIGH  # uncertainty on an access-governance op is inherently high-risk
    else:
        # Check for group-type ACL entries at or above path — group membership creates
        # shadow/widen effects this analysis cannot enumerate (group members are not in the
        # ACL list; only the group entry itself is). Emit a disclosure without escalating risk.
        group_entries_present = any(
            e.get("type") == "group" and (
                e.get("path") == path or path.startswith(e.get("path", "").rstrip("/") + "/")
            )
            for e in acl_entries
        )
        if group_entries_present:
            blast.append(
                "UNCERTAINTY: group-type ACL entries exist at or above this path — "
                "group membership grants are NOT visible in the per-user ACL list; "
                "shadow/widen analysis may be INCOMPLETE for users who are group members"
            )
            reasons.append(
                "group-based ACL grants exist at this scope; shadow analysis may miss group-inherited privileges"
            )
        if not delete:
            # Grant path.
            if shadowed_inherited:
                sr = ", ".join(sorted(shadowed_inherited))
                blast.append(
                    f"SHADOW WARNING: granting {roles!r} at {path!r} will REPLACE {target!r}'s "
                    f"INHERITED grants — the following inherited roles will NO LONGER apply at "
                    f"{path!r}: {sr}. (The specific-path entry takes precedence over ancestor "
                    "propagated grants.)"
                )
                reasons.append(
                    "granting a specific-path ACL replaces ancestor inherited (propagated) grants — "
                    f"inherited roles {{{sr}}} are shadowed (lost) at {path!r}"
                )
                risk = RISK_HIGH
            if widened:
                wr = ", ".join(sorted(widened))
                blast.append(
                    f"NEW privileges at {path!r}: {target!r} gains {wr}"
                )
                reasons.append(f"target gains new roles: {wr}")
            if not shadowed_inherited and not widened:
                blast.append(
                    f"grants {roles!r} to {target!r} at {path!r} (propagate={propagate}) — "
                    "no inherited grants detected to shadow; no new privileges detected"
                )
                reasons.append("no inherited grants to shadow; grant is additive at this path")
        else:
            # Revoke path.
            if widened:
                wr = ", ".join(sorted(widened))
                blast.append(
                    f"WIDEN WARNING: revoking the specific entry at {path!r} for {target!r} "
                    f"RESTORES inherited grants — {target!r} will gain back: {wr}"
                )
                reasons.append(
                    "revoking a specific-path ACL restores inherited grants — "
                    f"the following roles become effective again at {path!r}: {wr}"
                )
                risk = RISK_HIGH
            if not widened:
                blast.append(
                    f"revokes {roles!r} from {target!r} at {path!r} — no inherited grants detected "
                    "that would widen access after revoke"
                )
                reasons.append("no inherited grants detected; revoke is straightforward")

    # Additional escalations independent of shadow/widen analysis.
    if _is_administrator_role(roles):
        blast.append(
            "Administrator role grants ALL Proxmox privileges — this is the widest possible role"
        )
        reasons.append("Administrator = super-role with full cluster privileges")
        risk = RISK_HIGH
    if _is_root_or_broad(path):
        blast.append(
            f"ACL at {path!r} affects ALL resources at that scope on the cluster"
        )
        reasons.append(f"path {path!r} is a high-blast scope (root or storage-wide)")
        risk = RISK_HIGH

    if not current_direct_entries:
        current: dict = {}
    else:
        # Show the first direct entry for the current dict (representative when multiple exist).
        first = current_direct_entries[0]
        current = {k: first[k] for k in ("path", "roleid", "ugid", "propagate") if k in first}

    return Plan(
        action="pve_acl_modify",
        target=f"acl:{path}:{target}",
        change=(
            f"{action_word} role(s) {roles!r} {'to' if not delete else 'from'} "
            f"{target!r} at path {path!r} (propagate={propagate})"
        ),
        current=current,
        blast_radius=blast,
        risk=risk,
        risk_reasons=reasons,
    )


def plan_token_create(userid: str, tokenid: str, privsep: bool = True) -> Plan:
    """Preview creating an API token.

    PURE — no API call needed.

    privsep=True (default): token is privilege-separated — its rights are limited
    to ACLs assigned directly to it. Lower blast.
    privsep=False: token inherits ALL of the owner's permissions. The token
    effectively IS the user — RISK_HIGH, flagged as over-broad.

    NOTE: the token secret value does NOT appear in the plan (it doesn't exist yet).
    The value surfaces once in the token_create result. Plans are safe to log.
    """
    userid = _check_userid(userid)
    tokenid = _check_tokenid(tokenid)

    if not privsep:
        risk = RISK_HIGH
        reasons = [
            "privsep=False: this token inherits ALL of the owner user's permissions — "
            "it is equivalent to the user credential itself; prefer privsep=True and "
            "assign only the permissions the token actually needs"
        ]
        blast = [
            f"creates token {userid}!{tokenid} with privsep=False — "
            "token has FULL owner privileges (not privilege-separated); "
            "a leaked token is as dangerous as a leaked user password"
        ]
    else:
        risk = RISK_MEDIUM
        reasons = ["creates a credential — token secrets cannot be retrieved after creation"]
        blast = [
            f"creates token {userid}!{tokenid} (privsep=True — restricted to token's own ACLs)",
            "the token secret value will be shown ONCE at creation; it cannot be retrieved again",
        ]

    return Plan(
        action="pve_token_create",
        target=f"token:{userid}!{tokenid}",
        change=f"create token {userid}!{tokenid} (privsep={privsep})",
        current={},
        blast_radius=blast,
        risk=risk,
        risk_reasons=reasons,
        note="token secret (value) is NOT in this plan — it surfaces once in the creation result",
    )


def plan_token_revoke(userid: str, tokenid: str) -> Plan:
    """Preview revoking (deleting) an API token.

    PURE — no API call needed.

    RISK_HIGH: revocation is IRREVERSIBLE. The token secret is permanently gone.
    Any systems or integrations using this token will immediately lose access.
    There is no undo — snapshot-based undo does NOT apply to token operations.
    """
    userid = _check_userid(userid)
    tokenid = _check_tokenid(tokenid)
    return Plan(
        action="pve_token_revoke",
        target=f"token:{userid}!{tokenid}",
        change=f"revoke (permanently delete) token {userid}!{tokenid}",
        current={},
        blast_radius=[
            f"PERMANENTLY revokes token {userid}!{tokenid} — the secret is gone forever",
            "any service or integration using this token will immediately lose Proxmox API access",
            "IRREVERSIBLE: snapshot-based undo does NOT apply to token operations",
        ],
        risk=RISK_HIGH,
        risk_reasons=[
            "token revocation is permanent — the secret cannot be recovered or reissued",
            "downstream systems using this token lose access immediately and irrecoverably",
        ],
    )
