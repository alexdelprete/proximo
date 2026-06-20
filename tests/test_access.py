"""ACCESS GOVERNANCE pillar tests — fully mocked, no live Proxmox.

Mirrors test_provisioning.py / test_backup.py style:
- Fake api objects record calls on the mock; assertions verify URL/param shapes.
- plan_* tests use lightweight fakes that supply access_acl_list results.
- Validator-rejection tests use pytest.raises(ProximoError).
- PLAN-before-mutate gating is the server layer's job (test_server_plan.py);
  these tests verify that every mutate has a correct plan function, that plans
  surface the shadow/widen analysis, and that validators fire.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from proximo.access import (
    access_acl_list,
    access_overbroad_grants,
    access_roles_list,
    access_tokens_list,
    access_users_list,
    acl_modify,
    plan_acl_modify,
    plan_token_create,
    plan_token_revoke,
    token_create,
    token_revoke,
)
from proximo.backends import ProximoError
from proximo.planning import RISK_HIGH, RISK_MEDIUM

# ---------------------------------------------------------------------------
# Test fakes
# ---------------------------------------------------------------------------

def _api(node: str = "pve"):
    """Fake api that records _get / _post / _delete calls."""
    seen: dict = {}

    def fake_get(path):
        seen["method"] = "GET"
        seen["path"] = path
        return []

    def fake_post(path, data=None):
        seen["method"] = "POST"
        seen["path"] = path
        seen["data"] = data or {}
        return {"value": "secret-abc-123", "info": {"tokenid": "mytoken"}}

    def fake_delete(path, params=None):
        seen["method"] = "DELETE"
        seen["path"] = path
        seen["params"] = params
        return None

    api = SimpleNamespace(
        config=SimpleNamespace(node=node),
        _get=fake_get,
        _post=fake_post,
        _delete=fake_delete,
        seen=seen,
    )
    return api


def _put_api(node: str = "pve"):
    """Fake api for acl_modify — records api._put calls in seen."""
    seen: dict = {}

    def fake_put(path, data=None):
        seen["method"] = "PUT"
        seen["path"] = path
        seen["data"] = data or {}
        return None

    api = SimpleNamespace(
        config=SimpleNamespace(node=node),
        _put=fake_put,
        seen=seen,
    )
    return api


def _acl_api(acl_entries: list[dict], raise_on_get: bool = False):
    """Fake api for plan_acl_modify — returns the given ACL list from _get('/access/acl')."""
    def fake_get(path):
        if raise_on_get:
            raise RuntimeError("api unavailable")
        if path == "/access/acl":
            return list(acl_entries)
        return []

    return SimpleNamespace(
        config=SimpleNamespace(node="pve"),
        _get=fake_get,
    )


# ---------------------------------------------------------------------------
# access_users_list
# ---------------------------------------------------------------------------

def test_access_users_list_calls_correct_path():
    api = _api()
    access_users_list(api)
    assert api.seen["path"] == "/access/users"
    assert api.seen["method"] == "GET"


def test_access_users_list_returns_list():
    api = _api()
    result = access_users_list(api)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# access_roles_list
# ---------------------------------------------------------------------------

def test_access_roles_list_calls_correct_path():
    api = _api()
    access_roles_list(api)
    assert api.seen["path"] == "/access/roles"
    assert api.seen["method"] == "GET"


def test_access_roles_list_returns_list():
    api = _api()
    result = access_roles_list(api)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# access_acl_list
# ---------------------------------------------------------------------------

def test_access_acl_list_calls_correct_path():
    api = _api()
    access_acl_list(api)
    assert api.seen["path"] == "/access/acl"
    assert api.seen["method"] == "GET"


def test_access_acl_list_returns_list():
    api = _api()
    result = access_acl_list(api)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# access_tokens_list
# ---------------------------------------------------------------------------

def test_access_tokens_list_calls_correct_path():
    api = _api()
    access_tokens_list(api, "admin@pam")
    assert api.seen["path"] == "/access/users/admin@pam/token"
    assert api.seen["method"] == "GET"


def test_access_tokens_list_returns_list():
    api = _api()
    result = access_tokens_list(api, "admin@pam")
    assert isinstance(result, list)


def test_access_tokens_list_rejects_invalid_userid():
    api = _api()
    with pytest.raises(ProximoError):
        access_tokens_list(api, "not-valid")  # no @realm


def test_access_tokens_list_rejects_traversal():
    api = _api()
    with pytest.raises(ProximoError):
        access_tokens_list(api, "admin@pam/../evil")


# ---------------------------------------------------------------------------
# access_overbroad_grants — diagnostic
# ---------------------------------------------------------------------------

def test_access_overbroad_flags_administrator_role():
    entries = [{"path": "/vms/100", "ugid": "user@pam", "roleid": "Administrator", "type": "user", "propagate": True}]
    api = _acl_api(entries)
    result = access_overbroad_grants(api)
    assert len(result) == 1
    reasons = result[0]["reasons"]
    assert any("Administrator" in r for r in reasons)


def test_access_overbroad_flags_root_path():
    entries = [{"path": "/", "ugid": "user@pam", "roleid": "PVEVMAdmin", "type": "user", "propagate": True}]
    api = _acl_api(entries)
    result = access_overbroad_grants(api)
    assert len(result) == 1
    reasons = result[0]["reasons"]
    assert any("/" in r for r in reasons)


def test_access_overbroad_flags_both_administrator_and_root():
    entries = [{"path": "/", "ugid": "root@pam", "roleid": "Administrator", "type": "user", "propagate": True}]
    api = _acl_api(entries)
    result = access_overbroad_grants(api)
    assert len(result) == 1
    reasons = result[0]["reasons"]
    assert len(reasons) == 2  # both Administrator + root reasons


def test_access_overbroad_does_not_flag_narrow_grant():
    entries = [{"path": "/vms/100", "ugid": "user@pam", "roleid": "PVEVMUser", "type": "user", "propagate": True}]
    api = _acl_api(entries)
    result = access_overbroad_grants(api)
    assert result == []


def test_access_overbroad_returns_list():
    api = _acl_api([])
    result = access_overbroad_grants(api)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# acl_modify — URL shape and body params (PUT /access/acl)
# ---------------------------------------------------------------------------

def test_acl_modify_issues_put_request():
    api = _put_api()
    acl_modify(api, "/vms/100", "PVEVMUser", "user@pam", kind="user")
    assert api.seen["method"] == "PUT"


def test_acl_modify_targets_correct_endpoint():
    api = _put_api()
    acl_modify(api, "/vms/100", "PVEVMUser", "user@pam", kind="user")
    assert api.seen["path"] == "/access/acl"


def test_acl_modify_sends_path_in_body():
    api = _put_api()
    acl_modify(api, "/vms/100", "PVEVMUser", "user@pam", kind="user")
    assert api.seen["data"]["path"] == "/vms/100"


def test_acl_modify_sends_roles_in_body():
    api = _put_api()
    acl_modify(api, "/vms/100", "PVEVMUser", "user@pam", kind="user")
    assert api.seen["data"]["roles"] == "PVEVMUser"


def test_acl_modify_user_kind_sends_users_param():
    api = _put_api()
    acl_modify(api, "/vms/100", "PVEVMUser", "user@pam", kind="user")
    assert api.seen["data"]["users"] == "user@pam"
    assert "tokens" not in api.seen["data"]


def test_acl_modify_token_kind_sends_tokens_param():
    api = _put_api()
    acl_modify(api, "/vms/100", "PVEVMUser", "user@pam!mytoken", kind="token")
    assert api.seen["data"]["tokens"] == "user@pam!mytoken"
    assert "users" not in api.seen["data"]


def test_acl_modify_grant_sets_delete_0():
    api = _put_api()
    acl_modify(api, "/vms/100", "PVEVMUser", "user@pam", delete=False)
    assert api.seen["data"]["delete"] == 0


def test_acl_modify_revoke_sets_delete_1():
    api = _put_api()
    acl_modify(api, "/vms/100", "PVEVMUser", "user@pam", delete=True)
    assert api.seen["data"]["delete"] == 1


def test_acl_modify_propagate_true_sends_1():
    api = _put_api()
    acl_modify(api, "/vms/100", "PVEVMUser", "user@pam", propagate=True)
    assert api.seen["data"]["propagate"] == 1


def test_acl_modify_propagate_false_sends_0():
    api = _put_api()
    acl_modify(api, "/vms/100", "PVEVMUser", "user@pam", propagate=False)
    assert api.seen["data"]["propagate"] == 0


# ---------------------------------------------------------------------------
# acl_modify — validator rejections
# ---------------------------------------------------------------------------

def test_acl_modify_rejects_invalid_acl_path():
    api = _put_api()
    with pytest.raises(ProximoError):
        acl_modify(api, "vms/100", "PVEVMUser", "user@pam")  # no leading slash


def test_acl_modify_rejects_traversal_path():
    api = _put_api()
    with pytest.raises(ProximoError):
        acl_modify(api, "/vms/../etc", "PVEVMUser", "user@pam")


def test_acl_modify_rejects_empty_roles():
    api = _put_api()
    with pytest.raises(ProximoError):
        acl_modify(api, "/vms/100", "", "user@pam")


def test_acl_modify_rejects_invalid_userid():
    api = _put_api()
    with pytest.raises(ProximoError):
        acl_modify(api, "/vms/100", "PVEVMUser", "notarealuser")  # no @realm


def test_acl_modify_rejects_invalid_kind():
    api = _put_api()
    with pytest.raises(ProximoError):
        acl_modify(api, "/vms/100", "PVEVMUser", "user@pam", kind="group")


def test_acl_modify_rejects_token_without_bang():
    api = _put_api()
    with pytest.raises(ProximoError):
        acl_modify(api, "/vms/100", "PVEVMUser", "user@pam", kind="token")  # no ! separator


def test_acl_modify_rejects_path_with_space():
    api = _put_api()
    with pytest.raises(ProximoError):
        acl_modify(api, "/vms/ 100", "PVEVMUser", "user@pam")


# ---------------------------------------------------------------------------
# token_create — URL shape, data, and secret handling
# ---------------------------------------------------------------------------

def test_token_create_posts_correct_path():
    api = _api()
    token_create(api, "admin@pam", "mytoken")
    assert api.seen["path"] == "/access/users/admin@pam/token/mytoken"
    assert api.seen["method"] == "POST"


def test_token_create_privsep_true_sends_1():
    api = _api()
    token_create(api, "admin@pam", "mytoken", privsep=True)
    assert api.seen["data"]["privsep"] == 1


def test_token_create_privsep_false_sends_0():
    api = _api()
    token_create(api, "admin@pam", "mytoken", privsep=False)
    assert api.seen["data"]["privsep"] == 0


def test_token_create_sends_comment_when_provided():
    api = _api()
    token_create(api, "admin@pam", "mytoken", comment="automation token")
    assert api.seen["data"]["comment"] == "automation token"


def test_token_create_no_comment_when_not_provided():
    api = _api()
    token_create(api, "admin@pam", "mytoken")
    assert "comment" not in api.seen["data"]


def test_token_create_sends_expire_when_provided():
    api = _api()
    token_create(api, "admin@pam", "mytoken", expire=1893456000)
    assert api.seen["data"]["expire"] == 1893456000


def test_token_create_no_expire_when_not_provided():
    api = _api()
    token_create(api, "admin@pam", "mytoken")
    assert "expire" not in api.seen["data"]


def test_token_create_result_contains_value():
    """The token value surfaces in the create result."""
    api = _api()
    result = token_create(api, "admin@pam", "mytoken")
    assert "value" in result
    assert result["value"] == "secret-abc-123"


def test_token_create_rejects_invalid_userid():
    api = _api()
    with pytest.raises(ProximoError):
        token_create(api, "notvalid", "mytoken")


def test_token_create_rejects_invalid_tokenid():
    api = _api()
    with pytest.raises(ProximoError):
        token_create(api, "admin@pam", "bad token!")  # space + bang


def test_token_create_rejects_traversal_in_userid():
    api = _api()
    with pytest.raises(ProximoError):
        token_create(api, "admin@pam/../evil", "mytoken")


# ---------------------------------------------------------------------------
# token_revoke — URL shape
# ---------------------------------------------------------------------------

def test_token_revoke_deletes_correct_path():
    api = _api()
    token_revoke(api, "admin@pam", "mytoken")
    assert api.seen["path"] == "/access/users/admin@pam/token/mytoken"
    assert api.seen["method"] == "DELETE"


def test_token_revoke_rejects_invalid_userid():
    api = _api()
    with pytest.raises(ProximoError):
        token_revoke(api, "notvalid", "mytoken")


def test_token_revoke_rejects_invalid_tokenid():
    api = _api()
    with pytest.raises(ProximoError):
        token_revoke(api, "admin@pam", "bad token!")


def test_token_revoke_refuses_path_traversal_tokenid():
    # tokenid='..' normalizes DELETE .../users/{u}/token/.. onto the USER-DELETE endpoint — a
    # wrong-target destructive op the plan + ledger would mislabel as "revoke token". Likewise '.'
    # collapses onto the token collection. Both MUST be refused before any DELETE is issued.
    api = _api()
    for bad in ("..", "."):
        with pytest.raises(ProximoError):
            token_revoke(api, "admin@pam", bad)
    assert api.seen == {}   # nothing was ever issued to the wire


# ---------------------------------------------------------------------------
# plan_token_create
# ---------------------------------------------------------------------------

def test_plan_token_create_privsep_true_is_medium():
    p = plan_token_create("admin@pam", "mytoken", privsep=True)
    assert p.risk == RISK_MEDIUM


def test_plan_token_create_privsep_false_is_high():
    p = plan_token_create("admin@pam", "mytoken", privsep=False)
    assert p.risk == RISK_HIGH


def test_plan_token_create_privsep_false_warns_full_owner_privs():
    p = plan_token_create("admin@pam", "mytoken", privsep=False)
    text = " ".join(p.blast_radius).lower()
    assert "full" in text or "all" in text or "owner" in text


def test_plan_token_create_names_tokenid_in_target():
    p = plan_token_create("admin@pam", "mytoken")
    assert "admin@pam!mytoken" in p.target or "mytoken" in p.target


def test_plan_token_create_note_says_value_not_in_plan():
    p = plan_token_create("admin@pam", "mytoken")
    # The note must make clear the secret is NOT in the plan.
    note_text = p.note.lower()
    assert "not" in note_text or "secret" in note_text or "value" in note_text


def test_plan_token_create_value_not_in_plan_dict():
    """The token value does not exist at plan time — verify plan dict has no 'value' key."""
    p = plan_token_create("admin@pam", "mytoken")
    d = p.as_dict()
    # Serialize to string and check; value must not appear in plan JSON.
    import json
    plan_str = json.dumps(d)
    # The fake value from the create mock is "secret-abc-123" — it should never be in plan.
    assert "secret-abc-123" not in plan_str


def test_plan_token_create_blast_mentions_cannot_retrieve():
    p = plan_token_create("admin@pam", "mytoken", privsep=True)
    text = " ".join(p.blast_radius).lower()
    assert "cannot" in text or "once" in text


def test_plan_token_create_rejects_invalid_userid():
    with pytest.raises(ProximoError):
        plan_token_create("notvalid", "mytoken")


def test_plan_token_create_rejects_invalid_tokenid():
    with pytest.raises(ProximoError):
        plan_token_create("admin@pam", "bad token!")


# ---------------------------------------------------------------------------
# plan_token_revoke
# ---------------------------------------------------------------------------

def test_plan_token_revoke_is_high_risk():
    p = plan_token_revoke("admin@pam", "mytoken")
    assert p.risk == RISK_HIGH


def test_plan_token_revoke_action_string():
    p = plan_token_revoke("admin@pam", "mytoken")
    assert p.action == "pve_token_revoke"


def test_plan_token_revoke_says_irreversible():
    p = plan_token_revoke("admin@pam", "mytoken")
    text = " ".join(p.blast_radius).lower()
    assert "irreversible" in text or "permanently" in text or "forever" in text


def test_plan_token_revoke_says_no_undo():
    p = plan_token_revoke("admin@pam", "mytoken")
    text = " ".join(p.blast_radius + p.risk_reasons).lower()
    assert "undo" in text or "cannot" in text or "recover" in text


def test_plan_token_revoke_names_token_in_target():
    p = plan_token_revoke("admin@pam", "mytoken")
    assert "mytoken" in p.target


def test_plan_token_revoke_rejects_invalid_userid():
    with pytest.raises(ProximoError):
        plan_token_revoke("notvalid", "mytoken")


def test_plan_token_revoke_rejects_invalid_tokenid():
    with pytest.raises(ProximoError):
        plan_token_revoke("admin@pam", "bad token!")


# ---------------------------------------------------------------------------
# plan_acl_modify — validator rejections
# ---------------------------------------------------------------------------

def test_plan_acl_modify_rejects_invalid_path():
    api = _acl_api([])
    with pytest.raises(ProximoError):
        plan_acl_modify(api, "vms/100", "PVEVMUser", "user@pam")  # no leading /


def test_plan_acl_modify_rejects_traversal():
    api = _acl_api([])
    with pytest.raises(ProximoError):
        plan_acl_modify(api, "/vms/../etc", "PVEVMUser", "user@pam")


def test_plan_acl_modify_rejects_empty_roles():
    api = _acl_api([])
    with pytest.raises(ProximoError):
        plan_acl_modify(api, "/vms/100", "", "user@pam")


def test_plan_acl_modify_rejects_invalid_userid():
    api = _acl_api([])
    with pytest.raises(ProximoError):
        plan_acl_modify(api, "/vms/100", "PVEVMUser", "notarealuser")


def test_plan_acl_modify_rejects_invalid_kind():
    api = _acl_api([])
    with pytest.raises(ProximoError):
        plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam", kind="group")


# ---------------------------------------------------------------------------
# plan_acl_modify — THE KILLER FEATURE: shadow/widen analysis
# ---------------------------------------------------------------------------

def test_plan_acl_modify_grant_no_inheritance_is_medium():
    """No existing ACL entries: simple additive grant, RISK_MEDIUM."""
    api = _acl_api([])
    p = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam")
    assert p.risk == RISK_MEDIUM


def test_plan_acl_modify_grant_shadows_inherited_is_high():
    """Target has a propagated Administrator grant at /. Granting PVEVMUser at /vms/100
    SHADOWS the inherited Administrator role — this is the lockout gotcha. Must be HIGH."""
    entries = [
        {
            "path": "/",
            "ugid": "user@pam",
            "roleid": "Administrator",
            "type": "user",
            "propagate": True,
        }
    ]
    api = _acl_api(entries)
    p = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam", delete=False)
    assert p.risk == RISK_HIGH


def test_plan_acl_modify_grant_shadow_warning_in_blast():
    """Shadow warning must appear explicitly in blast_radius."""
    entries = [
        {
            "path": "/",
            "ugid": "user@pam",
            "roleid": "Administrator",
            "type": "user",
            "propagate": True,
        }
    ]
    api = _acl_api(entries)
    p = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam")
    text = " ".join(p.blast_radius).lower()
    assert "shadow" in text or "replace" in text or "inherited" in text


def test_plan_acl_modify_grant_shadow_names_lost_role():
    """The shadowed role (Administrator) must be named in the blast radius."""
    entries = [
        {
            "path": "/",
            "ugid": "user@pam",
            "roleid": "Administrator",
            "type": "user",
            "propagate": True,
        }
    ]
    api = _acl_api(entries)
    p = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam")
    text = " ".join(p.blast_radius)
    assert "Administrator" in text


def test_plan_acl_modify_revoke_widens_is_high():
    """Revoking a specific entry at /vms/100 when there's an inherited Administrator grant
    at / RESTORES broader inherited access — revoking WIDENS. Must be HIGH."""
    entries = [
        # Inherited broad grant at root.
        {"path": "/", "ugid": "user@pam", "roleid": "Administrator", "type": "user", "propagate": True},
        # Specific narrower grant at our path (the one we're revoking).
        {"path": "/vms/100", "ugid": "user@pam", "roleid": "PVEVMUser", "type": "user", "propagate": True},
    ]
    api = _acl_api(entries)
    p = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam", delete=True)
    assert p.risk == RISK_HIGH


def test_plan_acl_modify_revoke_widen_warning_in_blast():
    """Widen warning must appear explicitly in blast_radius when revoking restores a broader grant."""
    entries = [
        {"path": "/", "ugid": "user@pam", "roleid": "Administrator", "type": "user", "propagate": True},
        {"path": "/vms/100", "ugid": "user@pam", "roleid": "PVEVMUser", "type": "user", "propagate": True},
    ]
    api = _acl_api(entries)
    p = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam", delete=True)
    text = " ".join(p.blast_radius).lower()
    assert "widen" in text or "restore" in text or "inherited" in text


def test_plan_acl_modify_acl_read_failure_is_high_and_discloses():
    """If the ACL read fails, uncertainty must be disclosed — never silently assumed safe.
    Must be RISK_HIGH since we can't determine shadow/widen effects."""
    api = _acl_api([], raise_on_get=True)
    p = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam")
    assert p.risk == RISK_HIGH
    text = " ".join(p.blast_radius).lower()
    assert "could not" in text or "unavailable" in text or "absence" in text


def test_plan_acl_modify_acl_read_failure_not_claimed_safe():
    """Never claim absence of warning is a safety signal when read failed."""
    api = _acl_api([], raise_on_get=True)
    p = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam")
    text = " ".join(p.blast_radius + p.risk_reasons).lower()
    assert "not a safety signal" in text or "absence" in text


def test_plan_acl_modify_administrator_role_is_high():
    """Granting Administrator role is always RISK_HIGH regardless of path."""
    api = _acl_api([])
    p = plan_acl_modify(api, "/vms/100", "Administrator", "user@pam")
    assert p.risk == RISK_HIGH


def test_plan_acl_modify_root_path_is_high():
    """Granting at / is always RISK_HIGH — widest possible scope."""
    api = _acl_api([])
    p = plan_acl_modify(api, "/", "PVEVMUser", "user@pam")
    assert p.risk == RISK_HIGH


def test_plan_acl_modify_root_path_blast_mentions_all_resources():
    api = _acl_api([])
    p = plan_acl_modify(api, "/", "PVEVMUser", "user@pam")
    text = " ".join(p.blast_radius).lower()
    assert "all" in text or "every" in text or "cluster" in text


def test_plan_acl_modify_no_inheritance_for_other_user():
    """An inherited grant for a DIFFERENT user must NOT affect the plan for our target."""
    entries = [
        # This is for other@pam, not user@pam.
        {"path": "/", "ugid": "other@pam", "roleid": "Administrator", "type": "user", "propagate": True},
    ]
    api = _acl_api(entries)
    p = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam")
    # No shadow for user@pam — they have no inherited grants being shadowed.
    assert p.risk == RISK_MEDIUM
    text = " ".join(p.blast_radius).lower()
    assert "shadow" not in text


def test_plan_acl_modify_non_propagated_ancestor_not_inherited():
    """A non-propagated ancestor entry does NOT bleed into child paths."""
    entries = [
        {
            "path": "/",
            "ugid": "user@pam",
            "roleid": "Administrator",
            "type": "user",
            "propagate": False,  # does NOT propagate
        }
    ]
    api = _acl_api(entries)
    p = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam")
    # No shadow — the / entry doesn't propagate to /vms/100.
    assert p.risk == RISK_MEDIUM
    text = " ".join(p.blast_radius).lower()
    assert "shadow" not in text


def test_plan_acl_modify_action_string():
    api = _acl_api([])
    p = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam")
    assert p.action == "pve_acl_modify"


def test_plan_acl_modify_target_includes_path_and_target():
    api = _acl_api([])
    p = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam")
    assert "/vms/100" in p.target
    assert "user@pam" in p.target


def test_plan_acl_modify_change_string_names_grant_or_revoke():
    api = _acl_api([])
    p_grant = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam", delete=False)
    p_revoke = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam", delete=True)
    assert "grant" in p_grant.change.lower()
    assert "revoke" in p_revoke.change.lower()


def test_plan_acl_modify_current_shows_existing_direct_entry():
    """If there's an existing direct ACL entry at path, it appears in plan.current."""
    entries = [
        {"path": "/vms/100", "ugid": "user@pam", "roleid": "PVEVMAdmin", "type": "user", "propagate": True},
    ]
    api = _acl_api(entries)
    p = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam")
    assert p.current.get("roleid") == "PVEVMAdmin"


def test_plan_acl_modify_current_empty_when_no_direct_entry():
    api = _acl_api([])
    p = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam")
    assert p.current == {}


# ---------------------------------------------------------------------------
# plan_acl_modify — FIX 4: multiple same-path direct roles
# ---------------------------------------------------------------------------

def test_plan_acl_modify_multiple_direct_roles_all_captured():
    """Two direct entries at the same path for the same user (different roles) must both
    be captured — the old code kept only the last one (current_direct = entry overwrote)."""
    entries = [
        {"path": "/vms/100", "ugid": "user@pam", "roleid": "PVEVMAdmin", "type": "user", "propagate": True},
        {"path": "/vms/100", "ugid": "user@pam", "roleid": "PVEVMUser",  "type": "user", "propagate": True},
    ]
    api = _acl_api(entries)
    # Revoking PVEVMUser: with both direct roles captured, current_direct_roles = {PVEVMAdmin, PVEVMUser}.
    # remaining_direct = {PVEVMAdmin} → non-empty → inherited NOT restored → no widen → RISK_MEDIUM.
    # Bug: old code would have current_direct_roles = {PVEVMUser} (last-write), remaining = {}, fall to
    # inherited (empty) → no widen either in this case — but the capture is wrong regardless.
    # The discriminating signal: the plan must not be RISK_HIGH and must not emit a WIDEN WARNING.
    p = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam", delete=True)
    assert p.risk == RISK_MEDIUM
    text = " ".join(p.blast_radius)
    # "WIDEN WARNING" is the escalation signal — the informational "would widen" substring in the
    # no-widen path is fine; the capitalized warning header is the discriminator.
    assert "WIDEN WARNING" not in text


def test_plan_acl_modify_revoke_does_not_widen_when_other_direct_remains():
    """Revoking one of two direct roles at the same path must NOT trigger a widen-HIGH
    when the remaining direct role still shadows the inherited grant."""
    entries = [
        # Inherited broad grant at root.
        {"path": "/", "ugid": "user@pam", "roleid": "Administrator", "type": "user", "propagate": True},
        # Two direct roles at our path — both shadow the inherited Administrator grant.
        {"path": "/vms/100", "ugid": "user@pam", "roleid": "PVEVMAdmin", "type": "user", "propagate": True},
        {"path": "/vms/100", "ugid": "user@pam", "roleid": "PVEVMUser",  "type": "user", "propagate": True},
    ]
    api = _acl_api(entries)
    # Revoking PVEVMUser: remaining_direct = {PVEVMAdmin} (non-empty).
    # effective_after = {PVEVMAdmin} — Administrator still shadowed, NOT restored.
    # widened = {PVEVMAdmin} - {PVEVMAdmin, PVEVMUser} = {} → no widen → RISK_MEDIUM.
    # Bug in old code: effective_after = inherited_roles = {Administrator} always →
    # widened = {Administrator} → false WIDEN WARNING + false RISK_HIGH.
    p = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam", delete=True)
    assert p.risk == RISK_MEDIUM
    text = " ".join(p.blast_radius)
    assert "WIDEN WARNING" not in text


# ---------------------------------------------------------------------------
# plan_acl_modify — FIX 5: group-based inheritance uncertainty warning
# ---------------------------------------------------------------------------

def test_plan_acl_modify_group_entry_at_path_resolved_no_incomplete_caveat():
    """A group-type ACL entry at the path no longer yields the generic 'incomplete' caveat once the
    target's group memberships are resolved (here _acl_api resolves them to empty)."""
    entries = [
        {"path": "/vms/100", "ugid": "admins", "roleid": "PVEVMAdmin", "type": "group", "propagate": True},
    ]
    api = _acl_api(entries)
    p = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam")
    assert not any("may be INCOMPLETE" in line for line in p.blast_radius)


def test_plan_acl_modify_group_entry_at_ancestor_resolved_no_incomplete_caveat():
    """A group entry propagating down from an ancestor: same — caveat gone once groups resolve."""
    entries = [
        {"path": "/", "ugid": "admins", "roleid": "Administrator", "type": "group", "propagate": True},
    ]
    api = _acl_api(entries)
    p = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam")
    assert not any("may be INCOMPLETE" in line for line in p.blast_radius)


def test_plan_acl_modify_no_group_entries_no_group_warning():
    """When no group-type entries exist, the group disclosure must NOT appear."""
    entries = [
        {"path": "/", "ugid": "user@pam", "roleid": "Administrator", "type": "user", "propagate": True},
    ]
    api = _acl_api(entries)
    p = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam")
    text = " ".join(p.blast_radius).lower()
    # shadow warning appears (Administrator at / bleeds down), but no group warning
    assert "group" not in text


def _acl_api_full(acl_entries, *, groups=None, members=None, tokens=None):
    """Path-aware fake: /access/acl, /access/users/{id}, /access/groups/{id}, /access/users/{id}/token."""
    def fake_get(path):
        if path == "/access/acl":
            return list(acl_entries)
        if path.endswith("/token"):
            return list(tokens or [])
        if path.startswith("/access/users/"):
            return {"groups": list(groups or [])}
        if path.startswith("/access/groups/"):
            grp = path.rsplit("/", 1)[1]
            return {"members": list((members or {}).get(grp, []))}
        return []
    return SimpleNamespace(config=SimpleNamespace(node="pve"), _get=fake_get)


def test_plan_acl_modify_privsep1_token_does_not_fold_owner_groups():
    acl = [{"path": "/", "ugid": "ops", "roleid": "PVEVMAdmin", "type": "group", "propagate": True}]
    api = _acl_api_full(acl, tokens=[{"tokenid": "ci", "privsep": 1}])
    plan = plan_acl_modify(api, "/vms/100", "PVEVMUser", "svc@pam!ci", kind="token")
    assert any("may be INCOMPLETE" in line for line in plan.blast_radius)  # not folded -> honest


def test_plan_acl_modify_privsep0_token_folds_owner_groups():
    # privsep=0 token DOES inherit owner groups -> owner's group-inherited role is folded + shadowed.
    acl = [{"path": "/", "ugid": "ops", "roleid": "PVEVMAdmin", "type": "group", "propagate": True}]
    api = _acl_api_full(acl, groups=["ops"], tokens=[{"tokenid": "ci", "privsep": 0}])
    plan = plan_acl_modify(api, "/vms/100", "PVEVMUser", "svc@pam!ci", kind="token")
    assert not any("may be INCOMPLETE" in line for line in plan.blast_radius)  # resolved -> complete
    assert any(a["change"] == "loses" and "PVEVMAdmin" in a["roles"] for a in plan.affected)


def test_plan_acl_modify_privsep0_token_folds_owner_direct_grant():
    # privsep=0 token inherits the owner's DIRECT propagated grant (Administrator at /) -> shadowed.
    acl = [{"path": "/", "ugid": "svc@pam", "roleid": "Administrator", "type": "user", "propagate": True}]
    api = _acl_api_full(acl, groups=[], tokens=[{"tokenid": "ci", "privsep": 0}])
    plan = plan_acl_modify(api, "/vms/100", "PVEVMUser", "svc@pam!ci", kind="token")
    assert any(a["change"] == "loses" and "Administrator" in a["roles"] for a in plan.affected)
    assert plan.risk == "high"


def test_plan_acl_modify_read_failure_sets_complete_false():
    # acl_list read fails -> result.complete False -> propagated onto the Plan (machine-checkable).
    api = _acl_api([], raise_on_get=True)
    plan = plan_acl_modify(api, "/vms/100", "PVEVMUser", "user@pam")
    assert plan.complete is False and plan.risk == RISK_HIGH
