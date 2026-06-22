#!/usr/bin/env python3
"""Live access-CRUD smoke: user / role / token create+delete + the token_revoke path-traversal fix.

  1. role_create -> assert listed -> (kept until cleanup)
  2. user_create -> assert listed
  3. token_create -> assert the token exists; token_revoke -> assert it is GONE
  4. SECURITY (live): token_revoke(userid, "..") MUST be REFUSED (the path-traversal fix) AND the user
     MUST still exist afterward — proving the malicious tokenid did NOT normalize onto user-delete
  5. cleanup: user_delete + role_delete -> assert both gone

SAFETY: access-mgmt privileges CANNOT be ACL-scoped to "test identities only" in PVE, so the SOLE guard
is the in-smoke identity allowlist (assert_test_identity, default-deny). This MUST refuse any prod user/
role before any create/delete. Configure with test-only identities + PROXIMO_SMOKE_IDENTITY_PREFIXES.
Needs a token with access-management privileges (Realm.AllocateUser/User.Modify/Permissions.Modify/
Sys.Modify) — provisioned by John. Run with the PVE env + the identity allowlist.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from safety import assert_test_identity, load_identity_allowlist  # noqa: E402  (sibling live-smoke module)

from proximo.access import token_create, token_revoke  # noqa: E402
from proximo.access_governance import role_create, role_delete  # noqa: E402
from proximo.access_users import user_create, user_delete  # noqa: E402
from proximo.backends import ProximoError  # noqa: E402
from proximo.server import _svc  # noqa: E402

USER = os.environ.get("SMOKE_CRUD_USER", "proximo-cismoke@pve").strip()
ROLE = os.environ.get("SMOKE_CRUD_ROLE", "ProximoCISmoke").strip()
TOKEN = os.environ.get("SMOKE_CRUD_TOKEN", "cismoke").strip()

# SOLE safety layer: refuse any non-test identity BEFORE any access mutation (default-deny).
_PREFIXES = load_identity_allowlist(os.environ)
assert_test_identity(USER, _PREFIXES, "user")
assert_test_identity(ROLE, _PREFIXES, "role")

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str) -> None:
    _results.append((name, ok))
    print(f"{'✅' if ok else '❌'} {name}: {detail}")


def _roles(api) -> set[str]:
    return {r.get("roleid") for r in (api._get("/access/roles") or [])}


def _users(api) -> set[str]:
    return {u.get("userid") for u in (api._get("/access/users") or [])}


def _tokens(api) -> set[str]:
    return {t.get("tokenid") for t in (api._get(f"/access/users/{USER}/token") or [])}


def main() -> int:
    _, api, _, _ = _svc()
    # idempotent clean start (guard already proved these are test identities)
    if USER in _users(api):
        user_delete(api, USER)
    if ROLE in _roles(api):
        role_delete(api, ROLE)
    try:
        role_create(api, ROLE, privs="VM.Audit")
        check("role_created", ROLE in _roles(api), f"role={ROLE}")

        user_create(api, USER, comment="proximo live-CI access-crud smoke")
        check("user_created", USER in _users(api), f"user={USER}")

        token_create(api, USER, TOKEN)
        check("token_created", TOKEN in _tokens(api), f"token={TOKEN}")
        token_revoke(api, USER, TOKEN)
        check("token_revoked", TOKEN not in _tokens(api), f"gone={TOKEN not in _tokens(api)}")

        # SECURITY (live): a '..' tokenid must be REFUSED, and the user must survive it.
        refused = False
        try:
            token_revoke(api, USER, "..")
        except ProximoError:
            refused = True
        check("token_revoke_rejects_path_traversal", refused and USER in _users(api),
              f"refused={refused} user_intact={USER in _users(api)}")

        user_delete(api, USER)
        check("user_deleted", USER not in _users(api), f"gone={USER not in _users(api)}")
        role_delete(api, ROLE)
        check("role_deleted", ROLE not in _roles(api), f"gone={ROLE not in _roles(api)}")
    finally:
        if USER in _users(api):
            user_delete(api, USER)
        if ROLE in _roles(api):
            role_delete(api, ROLE)

    passed = sum(1 for _, ok in _results if ok)
    ok = passed == len(_results)
    label = "access-CRUD live-verify (user/role/token + token_revoke fix)"
    print(f"\n{label}: {'PASS' if ok else 'FAIL'}  {passed}/{len(_results)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
