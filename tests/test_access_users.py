"""USERS & GROUPS governance pillar tests — fully mocked, no live Proxmox.

Mirrors test_access.py / test_cluster_ops.py style:
- _api() records _get / _post / _put / _delete calls.
- _UserApi / _GroupApi supply per-path responses for plan_* affected-set reads.
- Raise-on-get fake and 404 fake mirror _StatusApi from test_cluster_ops for the
  read-failure-honesty branches.
- Validator-rejection tests use pytest.raises(ProximoError).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from proximo.access_users import (
    _check_freetext,
    _check_groupid,
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
from proximo.backends import ProximoError
from proximo.planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM

# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------

def _api(node: str = "pve") -> SimpleNamespace:
    """Fake api recording _get / _post / _put / _delete calls."""
    seen: dict = {}

    def fake_get(path):
        seen["method"] = "GET"
        seen["path"] = path
        return []

    def fake_post(path, data=None):
        seen["method"] = "POST"
        seen["path"] = path
        seen["data"] = data or {}
        return None

    def fake_put(path, data=None):
        seen["method"] = "PUT"
        seen["path"] = path
        seen["data"] = data or {}
        return None

    def fake_delete(path, params=None):
        seen["method"] = "DELETE"
        seen["path"] = path
        seen["params"] = params
        return None

    return SimpleNamespace(
        config=SimpleNamespace(node=node),
        _get=fake_get,
        _post=fake_post,
        _put=fake_put,
        _delete=fake_delete,
        seen=seen,
    )


class _UserApi:
    """Fake for plan_user_delete: supplies per-path _get responses.

    user_response: dict returned for GET /access/users/{userid} (or None for 404)
    acl_response:  list returned for GET /access/acl (or None to raise)
    raise_on_user: if True, raises a generic (non-404) error on user_get
    raise_on_acl:  if True, raises a generic (non-404) error on acl list
    """

    def __init__(
        self,
        user_response: dict | None = None,
        acl_response: list | None = None,
        raise_on_user: bool = False,
        raise_on_acl: bool = False,
        node: str = "pve",
    ):
        self._user = user_response
        self._acl = acl_response if acl_response is not None else []
        self._raise_user = raise_on_user
        self._raise_acl = raise_on_acl
        self.config = SimpleNamespace(node=node)

    def _get(self, path: str):
        if "/access/users/" in path:
            if self._raise_user:
                raise RuntimeError("transient user API error")
            if self._user is None:
                err = RuntimeError("not found")
                err.response = SimpleNamespace(status_code=404)
                raise err
            return self._user
        if path == "/access/acl":
            if self._raise_acl:
                raise RuntimeError("transient ACL API error")
            return list(self._acl)
        return []


class _GroupApi:
    """Fake for plan_group_delete: supplies per-path _get responses.

    group_response: dict returned for GET /access/groups/{groupid} (or None for 404)
    raise_on_get:   if True, raises a generic (non-404) error
    """

    def __init__(
        self,
        group_response: dict | None = None,
        raise_on_get: bool = False,
        node: str = "pve",
    ):
        self._group = group_response
        self._raise = raise_on_get
        self.config = SimpleNamespace(node=node)

    def _get(self, path: str):
        if self._raise:
            raise RuntimeError("transient group API error")
        if self._group is None:
            err = RuntimeError("not found")
            err.response = SimpleNamespace(status_code=404)
            raise err
        return self._group


# ---------------------------------------------------------------------------
# _check_groupid — validator unit tests
# ---------------------------------------------------------------------------

def test_check_groupid_accepts_simple_name():
    assert _check_groupid("admins") == "admins"


def test_check_groupid_accepts_alphanumeric():
    assert _check_groupid("group123") == "group123"


def test_check_groupid_accepts_with_hyphen():
    assert _check_groupid("my-group") == "my-group"


def test_check_groupid_accepts_with_underscore():
    assert _check_groupid("ops_team") == "ops_team"


def test_check_groupid_rejects_empty():
    with pytest.raises(ProximoError):
        _check_groupid("")


def test_check_groupid_rejects_leading_hyphen():
    with pytest.raises(ProximoError):
        _check_groupid("-badgroup")


def test_check_groupid_rejects_at_sign():
    """Proves it is NOT a userid validator — '@' is rejected."""
    with pytest.raises(ProximoError):
        _check_groupid("foo@bar")


def test_check_groupid_rejects_slash():
    with pytest.raises(ProximoError):
        _check_groupid("group/evil")


def test_check_groupid_rejects_embedded_newline():
    """The \\Z anchor (not $) blocks mid-string newline bypass.

    strip() handles trailing whitespace; \\Z ensures an embedded '\\n'
    (i.e. inside the string, not at the tail) is still rejected.
    """
    with pytest.raises(ProximoError):
        _check_groupid("adm\nins")


def test_check_groupid_rejects_space():
    with pytest.raises(ProximoError):
        _check_groupid("my group")


def test_check_groupid_strips_surrounding_whitespace():
    # strip() is applied before match — "  admins  " should be valid after strip
    assert _check_groupid("  admins  ") == "admins"


# ---------------------------------------------------------------------------
# user_get
# ---------------------------------------------------------------------------

def test_user_get_calls_correct_path():
    api = _api()
    api._get = lambda path: (setattr(api, "seen_path", path) or {})  # type: ignore[arg-type]
    user_get(api, "admin@pam")
    assert api.seen_path == "/access/users/admin@pam"


def test_user_get_returns_dict():
    api = _api()
    result = user_get(api, "admin@pam")
    assert isinstance(result, dict)


def test_user_get_rejects_invalid_userid():
    api = _api()
    with pytest.raises(ProximoError):
        user_get(api, "norealmuser")


def test_user_get_rejects_traversal():
    api = _api()
    with pytest.raises(ProximoError):
        user_get(api, "admin@pam/../evil")


def test_user_get_returns_empty_dict_on_none_response():
    api = _api()
    api._get = lambda path: None  # type: ignore[assignment]
    result = user_get(api, "admin@pam")
    assert result == {}


# ---------------------------------------------------------------------------
# groups_list
# ---------------------------------------------------------------------------

def test_groups_list_calls_correct_path():
    api = _api()
    groups_list(api)
    assert api.seen["path"] == "/access/groups"
    assert api.seen["method"] == "GET"


def test_groups_list_returns_list():
    api = _api()
    result = groups_list(api)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# group_get
# ---------------------------------------------------------------------------

def test_group_get_calls_correct_path():
    api = _api()
    api._get = lambda path: (setattr(api, "seen_path", path) or {})  # type: ignore[arg-type]
    group_get(api, "admins")
    assert api.seen_path == "/access/groups/admins"


def test_group_get_returns_dict():
    api = _api()
    result = group_get(api, "admins")
    assert isinstance(result, dict)


def test_group_get_rejects_invalid_groupid():
    api = _api()
    with pytest.raises(ProximoError):
        group_get(api, "-badgroup")


def test_group_get_rejects_at_sign_in_groupid():
    api = _api()
    with pytest.raises(ProximoError):
        group_get(api, "foo@bar")


# ---------------------------------------------------------------------------
# user_create — URL shape and body params
# ---------------------------------------------------------------------------

def test_user_create_posts_to_access_users():
    api = _api()
    user_create(api, "newuser@pam")
    assert api.seen["path"] == "/access/users"
    assert api.seen["method"] == "POST"


def test_user_create_sends_userid_in_body():
    api = _api()
    user_create(api, "newuser@pam")
    assert api.seen["data"]["userid"] == "newuser@pam"


def test_user_create_sends_comment_when_provided():
    api = _api()
    user_create(api, "newuser@pam", comment="automation user")
    assert api.seen["data"]["comment"] == "automation user"


def test_user_create_omits_comment_when_not_provided():
    api = _api()
    user_create(api, "newuser@pam")
    assert "comment" not in api.seen["data"]


def test_user_create_sends_email_when_provided():
    api = _api()
    user_create(api, "newuser@pam", email="user@example.com")
    assert api.seen["data"]["email"] == "user@example.com"


def test_user_create_sends_enable_false_as_0():
    """enable=False must send 0, not be silently dropped."""
    api = _api()
    user_create(api, "newuser@pam", enable=False)
    assert api.seen["data"]["enable"] == 0


def test_user_create_sends_enable_true_as_1():
    api = _api()
    user_create(api, "newuser@pam", enable=True)
    assert api.seen["data"]["enable"] == 1


def test_user_create_omits_enable_when_not_provided():
    api = _api()
    user_create(api, "newuser@pam")
    assert "enable" not in api.seen["data"]


def test_user_create_sends_expire_when_provided():
    api = _api()
    user_create(api, "newuser@pam", expire=1893456000)
    assert api.seen["data"]["expire"] == 1893456000


def test_user_create_omits_expire_when_not_provided():
    api = _api()
    user_create(api, "newuser@pam")
    assert "expire" not in api.seen["data"]


def test_user_create_sends_groups_when_provided():
    api = _api()
    user_create(api, "newuser@pam", groups="admins")
    assert api.seen["data"]["groups"] == "admins"


def test_user_create_omits_groups_when_not_provided():
    api = _api()
    user_create(api, "newuser@pam")
    assert "groups" not in api.seen["data"]


def test_user_create_sends_firstname_lastname():
    api = _api()
    user_create(api, "newuser@pam", firstname="John", lastname="Doe")
    assert api.seen["data"]["firstname"] == "John"
    assert api.seen["data"]["lastname"] == "Doe"


def test_user_create_rejects_invalid_userid():
    api = _api()
    with pytest.raises(ProximoError):
        user_create(api, "norealmuser")


def test_user_create_rejects_invalid_group_in_groups():
    api = _api()
    with pytest.raises(ProximoError):
        user_create(api, "newuser@pam", groups="valid,bad@group")


# ---------------------------------------------------------------------------
# user_update — URL shape and body params
# ---------------------------------------------------------------------------

def test_user_update_puts_to_correct_path():
    api = _api()
    user_update(api, "admin@pam")
    assert api.seen["path"] == "/access/users/admin@pam"
    assert api.seen["method"] == "PUT"


def test_user_update_does_not_send_userid_in_body():
    """userid goes in the PATH for update (not POST body)."""
    api = _api()
    user_update(api, "admin@pam", comment="updated")
    assert "userid" not in api.seen["data"]


def test_user_update_sends_enable_false_as_0():
    """enable=False must send 0 — never silently dropped (boolean trap)."""
    api = _api()
    user_update(api, "admin@pam", enable=False)
    assert api.seen["data"]["enable"] == 0


def test_user_update_sends_enable_true_as_1():
    api = _api()
    user_update(api, "admin@pam", enable=True)
    assert api.seen["data"]["enable"] == 1


def test_user_update_omits_enable_when_not_provided():
    api = _api()
    user_update(api, "admin@pam", comment="x")
    assert "enable" not in api.seen["data"]


def test_user_update_sends_append_false_as_0():
    """append=False must send 0 — same boolean-trap guard as enable."""
    api = _api()
    user_update(api, "admin@pam", groups="admins", append=False)
    assert api.seen["data"]["append"] == 0


def test_user_update_sends_append_true_as_1():
    api = _api()
    user_update(api, "admin@pam", groups="admins", append=True)
    assert api.seen["data"]["append"] == 1


def test_user_update_omits_append_when_not_provided():
    api = _api()
    user_update(api, "admin@pam", groups="admins")
    assert "append" not in api.seen["data"]


def test_user_update_sends_groups_when_provided():
    api = _api()
    user_update(api, "admin@pam", groups="admins,ops")
    assert api.seen["data"]["groups"] == "admins,ops"


def test_user_update_sends_empty_body_when_no_optional_params():
    api = _api()
    user_update(api, "admin@pam")
    assert api.seen["data"] == {}


def test_user_update_rejects_invalid_userid():
    api = _api()
    with pytest.raises(ProximoError):
        user_update(api, "norealmuser")


def test_user_update_rejects_invalid_group_in_groups():
    api = _api()
    with pytest.raises(ProximoError):
        user_update(api, "admin@pam", groups="-badgroup")


# ---------------------------------------------------------------------------
# user_delete — URL shape
# ---------------------------------------------------------------------------

def test_user_delete_deletes_correct_path():
    api = _api()
    user_delete(api, "admin@pam")
    assert api.seen["path"] == "/access/users/admin@pam"
    assert api.seen["method"] == "DELETE"


def test_user_delete_rejects_invalid_userid():
    api = _api()
    with pytest.raises(ProximoError):
        user_delete(api, "norealmuser")


# ---------------------------------------------------------------------------
# group_create — URL shape and body params
# ---------------------------------------------------------------------------

def test_group_create_posts_to_access_groups():
    api = _api()
    group_create(api, "admins")
    assert api.seen["path"] == "/access/groups"
    assert api.seen["method"] == "POST"


def test_group_create_sends_groupid_in_body():
    api = _api()
    group_create(api, "admins")
    assert api.seen["data"]["groupid"] == "admins"


def test_group_create_sends_comment_when_provided():
    api = _api()
    group_create(api, "admins", comment="Admin users")
    assert api.seen["data"]["comment"] == "Admin users"


def test_group_create_omits_comment_when_not_provided():
    api = _api()
    group_create(api, "admins")
    assert "comment" not in api.seen["data"]


def test_group_create_rejects_invalid_groupid():
    api = _api()
    with pytest.raises(ProximoError):
        group_create(api, "-badgroup")


def test_group_create_rejects_at_sign():
    api = _api()
    with pytest.raises(ProximoError):
        group_create(api, "foo@bar")


# ---------------------------------------------------------------------------
# group_update — URL shape and body params
# ---------------------------------------------------------------------------

def test_group_update_puts_to_correct_path():
    api = _api()
    group_update(api, "admins")
    assert api.seen["path"] == "/access/groups/admins"
    assert api.seen["method"] == "PUT"


def test_group_update_does_not_send_groupid_in_body():
    """groupid goes in the PATH for update."""
    api = _api()
    group_update(api, "admins", comment="updated")
    assert "groupid" not in api.seen["data"]


def test_group_update_sends_comment_when_provided():
    api = _api()
    group_update(api, "admins", comment="new comment")
    assert api.seen["data"]["comment"] == "new comment"


def test_group_update_sends_empty_body_when_no_params():
    api = _api()
    group_update(api, "admins")
    assert api.seen["data"] == {}


def test_group_update_rejects_invalid_groupid():
    api = _api()
    with pytest.raises(ProximoError):
        group_update(api, "bad/group")


# ---------------------------------------------------------------------------
# group_delete — URL shape
# ---------------------------------------------------------------------------

def test_group_delete_deletes_correct_path():
    api = _api()
    group_delete(api, "admins")
    assert api.seen["path"] == "/access/groups/admins"
    assert api.seen["method"] == "DELETE"


def test_group_delete_rejects_invalid_groupid():
    api = _api()
    with pytest.raises(ProximoError):
        group_delete(api, "-badgroup")


# ---------------------------------------------------------------------------
# plan_user_create
# ---------------------------------------------------------------------------

def test_plan_user_create_is_medium_risk():
    p = plan_user_create("newuser@pam")
    assert p.risk == RISK_MEDIUM


def test_plan_user_create_action_string():
    p = plan_user_create("newuser@pam")
    assert p.action == "pve_user_create"


def test_plan_user_create_target_includes_userid():
    p = plan_user_create("newuser@pam")
    assert "newuser@pam" in p.target


def test_plan_user_create_blast_mentions_password_not_set():
    p = plan_user_create("newuser@pam")
    text = " ".join(p.blast_radius).lower()
    assert "password" in text or "passwd" in text or "login" in text


def test_plan_user_create_with_groups_mentions_group_access():
    p = plan_user_create("newuser@pam", groups="admins")
    text = " ".join(p.blast_radius).lower()
    assert "admins" in text or "group" in text


def test_plan_user_create_enable_false_noted_in_blast():
    p = plan_user_create("newuser@pam", enable=False)
    text = " ".join(p.blast_radius).lower()
    assert "disabled" in text or "cannot log in" in text or "enable" in text


def test_plan_user_create_rejects_invalid_userid():
    with pytest.raises(ProximoError):
        plan_user_create("norealmuser")


def test_plan_user_create_rejects_invalid_group():
    with pytest.raises(ProximoError):
        plan_user_create("newuser@pam", groups="-badgroup")


def test_plan_user_create_change_string_mentions_create():
    p = plan_user_create("newuser@pam")
    assert "create" in p.change.lower()


# ---------------------------------------------------------------------------
# plan_user_update
# ---------------------------------------------------------------------------

def test_plan_user_update_is_medium_risk():
    p = plan_user_update("admin@pam")
    assert p.risk == RISK_MEDIUM


def test_plan_user_update_action_string():
    p = plan_user_update("admin@pam")
    assert p.action == "pve_user_update"


def test_plan_user_update_enable_false_warns_no_login():
    p = plan_user_update("admin@pam", enable=False)
    text = " ".join(p.blast_radius).lower()
    assert "log in" in text or "login" in text or "blocked" in text or "disabled" in text


def test_plan_user_update_enable_false_warns_even_when_other_params():
    p = plan_user_update("admin@pam", enable=False, comment="x")
    text = " ".join(p.blast_radius).lower()
    assert "log in" in text or "login" in text or "blocked" in text or "disabled" in text


def test_plan_user_update_groups_replace_warns_may_remove_access():
    """Groups without append (replace mode) warns about potential access loss."""
    p = plan_user_update("admin@pam", groups="admins")
    text = " ".join(p.blast_radius).lower()
    assert "replace" in text or "replaces" in text or "remove" in text or "lose" in text


def test_plan_user_update_groups_append_notes_expansion():
    """Groups with append=True notes access may expand."""
    p = plan_user_update("admin@pam", groups="admins", append=True)
    text = " ".join(p.blast_radius).lower()
    assert "append" in text or "add" in text or "expand" in text or "widen" in text


def test_plan_user_update_rejects_invalid_userid():
    with pytest.raises(ProximoError):
        plan_user_update("norealmuser")


def test_plan_user_update_rejects_invalid_group():
    with pytest.raises(ProximoError):
        plan_user_update("admin@pam", groups="bad@group")


def test_plan_user_update_target_includes_userid():
    p = plan_user_update("admin@pam")
    assert "admin@pam" in p.target


# ---------------------------------------------------------------------------
# plan_user_delete — risk, blast, affected-set reads
# ---------------------------------------------------------------------------

def test_plan_user_delete_is_always_high_risk():
    api = _UserApi(user_response={"email": "a@b.com", "enable": 1}, acl_response=[])
    p = plan_user_delete(api, "admin@pam")
    assert p.risk == RISK_HIGH


def test_plan_user_delete_action_string():
    api = _UserApi(user_response={"enable": 1}, acl_response=[])
    p = plan_user_delete(api, "admin@pam")
    assert p.action == "pve_user_delete"


def test_plan_user_delete_target_includes_userid():
    api = _UserApi(user_response={"enable": 1}, acl_response=[])
    p = plan_user_delete(api, "admin@pam")
    assert "admin@pam" in p.target


def test_plan_user_delete_blast_mentions_irreversible():
    api = _UserApi(user_response={"enable": 1}, acl_response=[])
    p = plan_user_delete(api, "admin@pam")
    text = " ".join(p.blast_radius).lower()
    assert "irreversible" in text or "permanently" in text or "no undo" in text


def test_plan_user_delete_blast_mentions_no_undo():
    api = _UserApi(user_response={"enable": 1}, acl_response=[])
    p = plan_user_delete(api, "admin@pam")
    text = " ".join(p.blast_radius + p.risk_reasons).lower()
    assert "undo" in text or "cannot" in text or "no way" in text


def test_plan_user_delete_with_tokens_mentions_token_revoke():
    api = _UserApi(
        user_response={"enable": 1, "tokens": [{"tokenid": "tok1"}, {"tokenid": "tok2"}]},
        acl_response=[],
    )
    p = plan_user_delete(api, "admin@pam")
    text = " ".join(p.blast_radius).lower()
    assert "token" in text
    assert "2" in text or "two" in text


def test_plan_user_delete_with_acl_entries_names_orphaned_paths():
    acl_entries = [
        {"ugid": "admin@pam", "path": "/vms/100", "roleid": "PVEVMAdmin", "type": "user"},
        {"ugid": "admin@pam", "path": "/storage", "roleid": "PVEDatastoreAdmin", "type": "user"},
    ]
    api = _UserApi(user_response={"enable": 1}, acl_response=acl_entries)
    p = plan_user_delete(api, "admin@pam")
    text = " ".join(p.blast_radius)
    assert "/vms/100" in text or "/storage" in text


def test_plan_user_delete_with_administrator_acl_warns_lockout():
    acl_entries = [
        {"ugid": "admin@pam", "path": "/", "roleid": "Administrator", "type": "user"},
    ]
    api = _UserApi(user_response={"enable": 1}, acl_response=acl_entries)
    p = plan_user_delete(api, "admin@pam")
    text = " ".join(p.blast_radius).lower()
    assert "lockout" in text or "admin" in text


def test_plan_user_delete_not_found_stays_high_risk():
    """User 404 → stays RISK_HIGH, says will no-op/fail."""
    api = _UserApi(user_response=None)  # triggers 404
    p = plan_user_delete(api, "admin@pam")
    assert p.risk == RISK_HIGH


def test_plan_user_delete_not_found_says_will_fail():
    api = _UserApi(user_response=None)
    p = plan_user_delete(api, "admin@pam")
    text = " ".join(p.blast_radius).lower()
    assert "not found" in text or "will fail" in text or "no-op" in text


def test_plan_user_delete_user_read_failure_stays_high_risk():
    """Transient user_get error → stays RISK_HIGH + discloses uncertainty."""
    api = _UserApi(raise_on_user=True)
    p = plan_user_delete(api, "admin@pam")
    assert p.risk == RISK_HIGH


def test_plan_user_delete_user_read_failure_discloses_uncertainty():
    api = _UserApi(raise_on_user=True)
    p = plan_user_delete(api, "admin@pam")
    text = " ".join(p.blast_radius).lower()
    assert "could not" in text or "unconfirmed" in text or "uncertain" in text


def test_plan_user_delete_user_read_failure_safety_signal_disclaimer():
    """Absence of warning must NOT be treated as a safety signal when read failed."""
    api = _UserApi(raise_on_user=True)
    p = plan_user_delete(api, "admin@pam")
    text = " ".join(p.blast_radius + p.risk_reasons).lower()
    assert "not a safety signal" in text or "absence" in text


def test_plan_user_delete_acl_read_failure_stays_high_risk():
    """ACL read failing is a separate concern — risk stays HIGH even if user read succeeds."""
    api = _UserApi(user_response={"enable": 1}, raise_on_acl=True)
    p = plan_user_delete(api, "admin@pam")
    assert p.risk == RISK_HIGH


def test_plan_user_delete_acl_read_failure_discloses_acl_uncertainty():
    api = _UserApi(user_response={"enable": 1}, raise_on_acl=True)
    p = plan_user_delete(api, "admin@pam")
    text = " ".join(p.blast_radius).lower()
    assert "acl" in text or "could not" in text


def test_plan_user_delete_acl_read_failure_safety_signal_disclaimer():
    """ACL read failure: absence of ACL warning must not claim safety."""
    api = _UserApi(user_response={"enable": 1}, raise_on_acl=True)
    p = plan_user_delete(api, "admin@pam")
    text = " ".join(p.blast_radius + p.risk_reasons).lower()
    assert "not a safety signal" in text or "absence" in text


def test_plan_user_delete_rejects_invalid_userid():
    api = _UserApi(user_response={})
    with pytest.raises(ProximoError):
        plan_user_delete(api, "norealmuser")


def test_plan_user_delete_current_populated_when_user_found():
    api = _UserApi(
        user_response={"email": "a@b.com", "enable": 1, "expire": 0},
        acl_response=[],
    )
    p = plan_user_delete(api, "admin@pam")
    assert p.current  # not empty


def test_plan_user_delete_current_empty_when_not_found():
    api = _UserApi(user_response=None)
    p = plan_user_delete(api, "admin@pam")
    assert p.current == {}


# ---------------------------------------------------------------------------
# plan_group_create
# ---------------------------------------------------------------------------

def test_plan_group_create_is_low_risk():
    p = plan_group_create("admins")
    assert p.risk == RISK_LOW


def test_plan_group_create_action_string():
    p = plan_group_create("admins")
    assert p.action == "pve_group_create"


def test_plan_group_create_target_includes_groupid():
    p = plan_group_create("admins")
    assert "admins" in p.target


def test_plan_group_create_blast_says_empty_group():
    p = plan_group_create("admins")
    text = " ".join(p.blast_radius).lower()
    assert "empty" in text or "additive" in text or "no members" in text


def test_plan_group_create_blast_says_additive():
    p = plan_group_create("admins")
    text = " ".join(p.blast_radius).lower()
    assert "additive" in text or "no existing" in text


def test_plan_group_create_rejects_invalid_groupid():
    with pytest.raises(ProximoError):
        plan_group_create("-badgroup")


def test_plan_group_create_rejects_at_sign():
    with pytest.raises(ProximoError):
        plan_group_create("foo@bar")


def test_plan_group_create_change_string_mentions_create():
    p = plan_group_create("admins")
    assert "create" in p.change.lower()


# ---------------------------------------------------------------------------
# plan_group_update
# ---------------------------------------------------------------------------

def test_plan_group_update_is_low_risk():
    p = plan_group_update("admins")
    assert p.risk == RISK_LOW


def test_plan_group_update_action_string():
    p = plan_group_update("admins")
    assert p.action == "pve_group_update"


def test_plan_group_update_target_includes_groupid():
    p = plan_group_update("admins")
    assert "admins" in p.target


def test_plan_group_update_blast_says_no_membership_change():
    p = plan_group_update("admins")
    text = " ".join(p.blast_radius).lower()
    assert "member" in text or "acl" in text or "metadata" in text


def test_plan_group_update_rejects_invalid_groupid():
    with pytest.raises(ProximoError):
        plan_group_update("-badgroup")


# ---------------------------------------------------------------------------
# plan_group_delete — risk, blast, affected-set reads
# ---------------------------------------------------------------------------

def test_plan_group_delete_is_always_high_risk():
    api = _GroupApi(group_response={"members": ["admin@pam"]})
    p = plan_group_delete(api, "admins")
    assert p.risk == RISK_HIGH


def test_plan_group_delete_action_string():
    api = _GroupApi(group_response={"members": []})
    p = plan_group_delete(api, "admins")
    assert p.action == "pve_group_delete"


def test_plan_group_delete_target_includes_groupid():
    api = _GroupApi(group_response={"members": []})
    p = plan_group_delete(api, "admins")
    assert "admins" in p.target


def test_plan_group_delete_blast_mentions_irreversible():
    api = _GroupApi(group_response={"members": []})
    p = plan_group_delete(api, "admins")
    text = " ".join(p.blast_radius).lower()
    assert "irreversible" in text or "permanently" in text or "no undo" in text


def test_plan_group_delete_blast_mentions_acl_orphan():
    """ACL orphan note is ALWAYS present regardless of member count."""
    api = _GroupApi(group_response={"members": []})
    p = plan_group_delete(api, "admins")
    text = " ".join(p.blast_radius).lower()
    assert "acl" in text or "orphan" in text or "grant" in text


def test_plan_group_delete_with_members_names_member_count():
    api = _GroupApi(group_response={"members": ["user1@pam", "user2@pam", "user3@pam"]})
    p = plan_group_delete(api, "admins")
    text = " ".join(p.blast_radius)
    assert "3" in text or "user1@pam" in text


def test_plan_group_delete_with_members_says_lose_access():
    api = _GroupApi(group_response={"members": ["user1@pam"]})
    p = plan_group_delete(api, "admins")
    text = " ".join(p.blast_radius).lower()
    assert "lose" in text or "access" in text or "derived" in text


def test_plan_group_delete_not_found_stays_high_risk():
    api = _GroupApi(group_response=None)  # triggers 404
    p = plan_group_delete(api, "admins")
    assert p.risk == RISK_HIGH


def test_plan_group_delete_not_found_says_will_fail():
    api = _GroupApi(group_response=None)
    p = plan_group_delete(api, "admins")
    text = " ".join(p.blast_radius).lower()
    assert "not found" in text or "will fail" in text or "no-op" in text


def test_plan_group_delete_read_failure_stays_high_risk():
    """Transient group_get error → stays RISK_HIGH + discloses uncertainty."""
    api = _GroupApi(raise_on_get=True)
    p = plan_group_delete(api, "admins")
    assert p.risk == RISK_HIGH


def test_plan_group_delete_read_failure_discloses_uncertainty():
    api = _GroupApi(raise_on_get=True)
    p = plan_group_delete(api, "admins")
    text = " ".join(p.blast_radius).lower()
    assert "could not" in text or "unconfirmed" in text or "uncertain" in text


def test_plan_group_delete_read_failure_safety_signal_disclaimer():
    """Read failure: absence of member warning must not imply safety."""
    api = _GroupApi(raise_on_get=True)
    p = plan_group_delete(api, "admins")
    text = " ".join(p.blast_radius + p.risk_reasons).lower()
    assert "not a safety signal" in text or "absence" in text


def test_plan_group_delete_rejects_invalid_groupid():
    api = _GroupApi(group_response={})
    with pytest.raises(ProximoError):
        plan_group_delete(api, "-badgroup")


def test_plan_group_delete_rejects_at_sign():
    api = _GroupApi(group_response={})
    with pytest.raises(ProximoError):
        plan_group_delete(api, "foo@bar")


def test_plan_group_delete_current_populated_when_group_found():
    api = _GroupApi(group_response={"comment": "admin group", "members": []})
    p = plan_group_delete(api, "admins")
    assert p.current  # not empty


def test_plan_group_delete_current_empty_when_not_found():
    api = _GroupApi(group_response=None)
    p = plan_group_delete(api, "admins")
    assert p.current == {}


def test_plan_group_delete_not_found_still_high_risk_despite_harmless_outcome():
    """The spec: not-found is maintained at HIGH — not-found ≠ safe."""
    api = _GroupApi(group_response=None)
    p = plan_group_delete(api, "admins")
    assert p.risk == RISK_HIGH


def test_plan_group_delete_acl_orphan_note_present_even_with_read_failure():
    """Static ACL-orphan note is ALWAYS present — it doesn't need a read."""
    api = _GroupApi(raise_on_get=True)
    p = plan_group_delete(api, "admins")
    text = " ".join(p.blast_radius).lower()
    assert "acl" in text or "orphan" in text or "grant" in text


# ---------------------------------------------------------------------------
# Item 1 — no-undo disclosure on ALL branches of plan_user_delete
# ---------------------------------------------------------------------------

def test_plan_user_delete_read_failure_blast_has_no_undo():
    """Regression: read-failure branch must include a no-undo disclosure in blast."""
    api = _UserApi(raise_on_user=True)
    p = plan_user_delete(api, "admin@pam")
    text = " ".join(p.blast_radius).lower()
    assert "no undo" in text or "irreversible" in text or "permanent" in text


def test_plan_user_delete_not_found_blast_has_no_undo():
    """Regression: 404/not-found branch must include a no-undo disclosure in blast."""
    api = _UserApi(user_response=None)
    p = plan_user_delete(api, "admin@pam")
    text = " ".join(p.blast_radius).lower()
    assert "no undo" in text or "irreversible" in text or "permanent" in text


def test_plan_user_delete_not_found_risk_reasons_has_no_undo():
    """404 branch: risk_reasons must also carry the no-undo note."""
    api = _UserApi(user_response=None)
    p = plan_user_delete(api, "admin@pam")
    reasons_text = " ".join(p.risk_reasons).lower()
    assert "no undo" in reasons_text or "permanent" in reasons_text


def test_plan_user_delete_both_reads_fail_high_risk_with_uncertainty():
    """Item 5a: user_get AND ACL read both raise → RISK_HIGH, both uncertainty disclosures."""
    api = _UserApi(raise_on_user=True, raise_on_acl=True)
    p = plan_user_delete(api, "admin@pam")
    assert p.risk == RISK_HIGH
    combined = " ".join(p.blast_radius + p.risk_reasons).lower()
    # user uncertainty disclosed
    assert "could not" in combined or "unconfirmed" in combined
    # acl uncertainty disclosed
    assert "acl" in combined


# ---------------------------------------------------------------------------
# Item 2 — _check_freetext / freetext injection defence
# ---------------------------------------------------------------------------

def test_check_freetext_accepts_normal_comment():
    assert _check_freetext("automation user", "comment") == "automation user"


def test_check_freetext_rejects_newline():
    with pytest.raises(ProximoError, match="comment"):
        _check_freetext("bad\nvalue", "comment")


def test_check_freetext_rejects_carriage_return():
    with pytest.raises(ProximoError, match="email"):
        _check_freetext("a@b.com\r", "email")


def test_check_freetext_rejects_null_byte():
    with pytest.raises(ProximoError):
        _check_freetext("a\x00b", "firstname")


def test_check_freetext_rejects_del():
    with pytest.raises(ProximoError):
        _check_freetext("a\x7fb", "lastname")


def test_check_freetext_does_not_strip_before_check():
    """A trailing newline must be caught — no .strip() pre-pass."""
    with pytest.raises(ProximoError):
        _check_freetext("cleanstart\n", "comment")


def test_check_freetext_error_message_contains_repr():
    """Error message must include repr of the value (codebase convention: {value!r})."""
    bad = "a\nb"
    with pytest.raises(ProximoError) as exc_info:
        _check_freetext(bad, "comment")
    assert repr(bad) in str(exc_info.value)


def test_user_create_rejects_newline_in_comment():
    """Freetext injection guard: newline in comment rejected on user_create."""
    api = _api()
    with pytest.raises(ProximoError):
        user_create(api, "newuser@pam", comment="injected\nnewline")


def test_user_create_rejects_newline_in_email():
    """Freetext injection guard: newline in email rejected on user_create."""
    api = _api()
    with pytest.raises(ProximoError):
        user_create(api, "newuser@pam", email="user@example.com\n")


def test_user_create_rejects_control_in_firstname():
    api = _api()
    with pytest.raises(ProximoError):
        user_create(api, "newuser@pam", firstname="John\x01Doe")


def test_user_create_rejects_control_in_lastname():
    api = _api()
    with pytest.raises(ProximoError):
        user_create(api, "newuser@pam", lastname="Doe\x1f")


def test_user_update_rejects_newline_in_comment():
    """Freetext injection guard: newline in comment rejected on user_update."""
    api = _api()
    with pytest.raises(ProximoError):
        user_update(api, "admin@pam", comment="injected\nnewline")


def test_user_update_rejects_newline_in_email():
    """Freetext injection guard: newline in email rejected on user_update."""
    api = _api()
    with pytest.raises(ProximoError):
        user_update(api, "admin@pam", email="bad@example.com\n")


# ---------------------------------------------------------------------------
# Item 3 — group member-count non-list shape
# ---------------------------------------------------------------------------

def test_plan_group_delete_non_list_members_no_false_count():
    """PVE returns members as a comma-sep string → must not char-count as member count."""
    api = _GroupApi(group_response={"members": "user1@pam,user2@pam"})
    p = plan_group_delete(api, "admins")
    text = " ".join(p.blast_radius)
    # "user1@pam,user2@pam" has 17 chars — none of those numbers should appear as member count
    assert "17" not in text and "16" not in text
    # The plan must disclose that the member shape was unconfirmed
    combined = text.lower()
    assert "unconfirmed" in combined or "non-list" in combined or "shape" in combined


def test_plan_group_delete_non_list_members_stays_high_risk():
    """Non-list members shape → RISK_HIGH maintained (not silently treated as empty)."""
    api = _GroupApi(group_response={"members": "user1@pam"})
    p = plan_group_delete(api, "admins")
    assert p.risk == RISK_HIGH


def test_plan_group_delete_non_list_members_reasons_has_unconfirmed_note():
    api = _GroupApi(group_response={"members": "user1@pam,user2@pam"})
    p = plan_group_delete(api, "admins")
    reasons_text = " ".join(p.risk_reasons).lower()
    assert "unconfirmed" in reasons_text or "not a list" in reasons_text or "non-list" in reasons_text


# ---------------------------------------------------------------------------
# Item 4 — plan_user_create blast carries password/login note (not just reasons)
# ---------------------------------------------------------------------------

def test_plan_user_create_blast_contains_passwd_endpoint():
    """The blast must mention the /passwd endpoint, not just reasons."""
    p = plan_user_create("newuser@pam")
    blast_text = " ".join(p.blast_radius).lower()
    assert "passwd" in blast_text or "password" in blast_text


def test_plan_user_create_blast_says_cannot_log_in():
    """The blast must state user cannot log in until password is set."""
    p = plan_user_create("newuser@pam")
    blast_text = " ".join(p.blast_radius).lower()
    assert "cannot log in" in blast_text or "can't log in" in blast_text or "log in" in blast_text


# ---------------------------------------------------------------------------
# Item 5b — _check_groupid boundary: 40 chars accepted, 41 rejected
# ---------------------------------------------------------------------------

def test_check_groupid_accepts_40_chars():
    """Maximum valid length: 1 alnum start + 39 more = 40 total."""
    name = "a" * 40
    assert _check_groupid(name) == name


def test_check_groupid_rejects_41_chars():
    """One over maximum: 41 chars must be rejected."""
    with pytest.raises(ProximoError):
        _check_groupid("a" * 41)


# ---------------------------------------------------------------------------
# Live read-smoke regression (2026-06-08): /access/users/{id} returns `tokens`
# as a DICT keyed by token-id, not a list. plan_user_delete must count the dict.
# ---------------------------------------------------------------------------

def test_plan_user_delete_counts_dict_shaped_tokens():
    # VERIFIED live: tokens come back as {"claude": {...}, "other": {...}} (a dict).
    api = _UserApi(user_response={"tokens": {"claude": {"privsep": 1}, "ci": {"privsep": 1}}},
                   acl_response=[])
    plan = plan_user_delete(api, "admin@pam")
    blast = " ".join(plan.blast_radius)
    assert "2 API token(s)" in blast          # both tokens counted, not 0
    assert plan.risk == RISK_HIGH


# ---------------------------------------------------------------------------
# Blast-radius coverage (rank 6): group_delete names the group-level ACL grants
# its members lose (not just the member list).
# ---------------------------------------------------------------------------

def test_plan_group_delete_names_orphaned_acl_grants():
    from types import SimpleNamespace

    from proximo.access_users import plan_group_delete

    def _get(path):
        if path == "/access/groups/devs":
            return {"members": ["alice@pve", "bob@pve"], "comment": "x"}
        if path == "/access/acl":
            return [{"type": "group", "ugid": "devs", "path": "/vms/100", "roleid": "PVEVMUser"},
                    {"type": "user", "ugid": "carol@pve", "path": "/", "roleid": "X"}]
        return {}

    api = SimpleNamespace(config=SimpleNamespace(node="pve"), _get=_get)
    p = plan_group_delete(api, "devs")
    assert any(a["path"] == "/vms/100" and a["roleid"] == "PVEVMUser" for a in p.affected)
    # discriminating guard: only group-principal grants appear (a leaked user grant has a different principal)
    assert all(a["principal"] == "group devs" for a in p.affected)
    assert p.complete is True


def test_plan_group_delete_acl_read_failure_is_incomplete():
    from types import SimpleNamespace

    from proximo.access_users import plan_group_delete

    def _get(path):
        if path == "/access/groups/devs":
            return {"members": ["alice@pve"]}
        if path == "/access/acl":
            raise RuntimeError("acl unavailable")
        return {}

    api = SimpleNamespace(config=SimpleNamespace(node="pve"), _get=_get)
    p = plan_group_delete(api, "devs")
    assert p.complete is False
