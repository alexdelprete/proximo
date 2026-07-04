"""PMG (Proxmox Mail Gateway) lane tests — fully mocked, no live PMG.

Mirrors test_pbs.py style:
- _pmg_backend() uses a mock httpx transport to test PmgBackend's HTTP layer.
- _api() is a recording SimpleNamespace for tool/plan function tests.
- Validator-rejection tests use pytest.raises(ProximoError).
- Plan tests verify honest risk ratings and blast radius content.

Auth model: ticket-based (CONFIRMED against PMG 9.1).
- Login: POST /access/ticket → {ticket, CSRFPreventionToken}
- Reads: Cookie: PMGAuthCookie=<ticket>   (no CSRF)
- Mutations: Cookie + CSRFPreventionToken header
- On 401: re-login once, retry; if still 401, raise.
"""

from __future__ import annotations

import pathlib
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

from proximo.backends import ProximoError
from proximo.planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM
from proximo.pmg import (
    PmgBackend,
    PmgConfig,
    _check_action_object_id,
    _check_action_position,
    _check_backup_notify,
    _check_cidr,
    _check_direction,
    _check_domain,
    _check_mail_id,
    _check_node,
    _check_ogroup,
    _check_priority,
    _check_quarantine_type,
    _check_rrddata_cf,
    _check_rrddata_timeframe,
    _check_ruledb_id,
    _check_service,
    _check_service_action,
    _check_transport_protocol,
    _check_what_object_type,
    _check_who_object_type,
    access_permissions,
    action_bcc_create,
    action_bcc_update,
    action_delete,
    action_disclaimer_create,
    action_disclaimer_update,
    action_field_create,
    action_field_update,
    action_notification_create,
    action_notification_update,
    action_objects_list,
    action_removeattachments_create,
    action_removeattachments_update,
    backup_create,
    domain_create,
    domain_delete,
    domains_list,
    mynetworks_add,
    mynetworks_remove,
    node_rrddata,
    node_status,
    node_syslog,
    node_version,
    plan_action_bcc_create,
    plan_action_bcc_update,
    plan_action_delete,
    plan_action_disclaimer_create,
    plan_action_disclaimer_update,
    plan_action_field_create,
    plan_action_field_update,
    plan_action_notification_create,
    plan_action_notification_update,
    plan_action_removeattachments_create,
    plan_action_removeattachments_update,
    plan_backup_create,
    plan_domain_create,
    plan_domain_delete,
    plan_mynetworks_add,
    plan_mynetworks_remove,
    plan_postfix_flush,
    plan_quarantine_action,
    plan_quarantine_blocklist_add,
    plan_quarantine_blocklist_remove,
    plan_quarantine_welcomelist_add,
    plan_quarantine_welcomelist_remove,
    plan_ruledb_rule_action_attach,
    plan_ruledb_rule_action_detach,
    plan_ruledb_rule_create,
    plan_ruledb_rule_delete,
    plan_ruledb_rule_from_attach,
    plan_ruledb_rule_from_detach,
    plan_ruledb_rule_to_attach,
    plan_ruledb_rule_to_detach,
    plan_ruledb_rule_update,
    plan_ruledb_rule_what_attach,
    plan_ruledb_rule_what_detach,
    plan_ruledb_rule_when_attach,
    plan_ruledb_rule_when_detach,
    plan_service_control,
    plan_spam_config_update,
    plan_transport_create,
    plan_transport_delete,
    plan_what_group_create,
    plan_what_group_delete,
    plan_what_group_update,
    plan_what_object_add,
    plan_what_object_delete,
    plan_what_object_update,
    plan_when_group_create,
    plan_when_group_delete,
    plan_when_group_update,
    plan_when_object_add,
    plan_when_object_delete,
    plan_when_object_update,
    plan_who_group_create,
    plan_who_group_delete,
    plan_who_group_update,
    plan_who_object_add,
    plan_who_object_delete,
    plan_who_object_update,
    postfix_flush,
    postfix_qshape,
    quarantine_action,
    quarantine_attachment,
    quarantine_blocklist_add,
    quarantine_blocklist_list,
    quarantine_blocklist_remove,
    quarantine_spam,
    quarantine_spamstatus,
    quarantine_spamusers,
    quarantine_virus,
    quarantine_virusstatus,
    quarantine_welcomelist_add,
    quarantine_welcomelist_list,
    quarantine_welcomelist_remove,
    relay_config,
    ruledb_digest,
    ruledb_rule_action_attach,
    ruledb_rule_action_detach,
    ruledb_rule_actions_list,
    ruledb_rule_create,
    ruledb_rule_delete,
    ruledb_rule_from_attach,
    ruledb_rule_from_detach,
    ruledb_rule_from_list,
    ruledb_rule_get,
    ruledb_rule_to_attach,
    ruledb_rule_to_detach,
    ruledb_rule_to_list,
    ruledb_rule_update,
    ruledb_rule_what_attach,
    ruledb_rule_what_detach,
    ruledb_rule_what_list,
    ruledb_rule_when_attach,
    ruledb_rule_when_detach,
    ruledb_rule_when_list,
    ruledb_rules_list,
    service_control,
    service_status,
    spam_config,
    spam_config_update,
    statistics_domains,
    statistics_mail,
    statistics_mailcount,
    statistics_receiver,
    statistics_recent,
    statistics_sender,
    statistics_spamscores,
    statistics_virus,
    tasks_list,
    tracker_detail,
    tracker_list,
    transport_create,
    transport_delete,
    what_group_create,
    what_group_delete,
    what_group_get,
    what_group_objects,
    what_group_update,
    what_groups_list,
    what_object_add,
    what_object_delete,
    what_object_update,
    when_group_create,
    when_group_delete,
    when_group_get,
    when_group_objects,
    when_group_update,
    when_groups_list,
    when_object_add,
    when_object_delete,
    when_object_update,
    who_group_create,
    who_group_delete,
    who_group_get,
    who_group_objects,
    who_group_update,
    who_groups_list,
    who_object_add,
    who_object_delete,
    who_object_update,
)

# ---------------------------------------------------------------------------
# PmgConfig helpers
# ---------------------------------------------------------------------------

def _cfg(**kw) -> PmgConfig:
    base = dict(
        base_url="https://pmg.example.lan:8006/api2/json",
        password_path="/run/pmg-password",
    )
    base.update(kw)
    return PmgConfig(**base)


# ---------------------------------------------------------------------------
# PmgConfig.from_env
# ---------------------------------------------------------------------------

def test_pmgconfig_from_env_reads_required_vars(monkeypatch):
    monkeypatch.setenv("PROXIMO_PMG_BASE_URL", "https://pmg:8006/api2/json")
    monkeypatch.setenv("PROXIMO_PMG_PASSWORD_PATH", "/run/pmg-pass")
    monkeypatch.delenv("PROXIMO_PMG_USERNAME", raising=False)
    monkeypatch.delenv("PROXIMO_PMG_NODE", raising=False)
    monkeypatch.delenv("PROXIMO_PMG_VERIFY_TLS", raising=False)
    monkeypatch.delenv("PROXIMO_PMG_CA_BUNDLE", raising=False)
    cfg = PmgConfig.from_env()
    assert cfg.base_url == "https://pmg:8006/api2/json"
    assert cfg.password_path == "/run/pmg-pass"
    assert cfg.username == "root@pam"
    assert cfg.node == "pmg"
    assert cfg.verify_tls is True
    assert cfg.ca_bundle is None


def test_pmgconfig_from_env_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("PROXIMO_PMG_BASE_URL", "https://pmg:8006/api2/json/")
    monkeypatch.setenv("PROXIMO_PMG_PASSWORD_PATH", "/run/pmg-pass")
    cfg = PmgConfig.from_env()
    assert not cfg.base_url.endswith("/")


def test_pmgconfig_from_env_optional_vars(monkeypatch):
    monkeypatch.setenv("PROXIMO_PMG_BASE_URL", "https://pmg:8006/api2/json")
    monkeypatch.setenv("PROXIMO_PMG_PASSWORD_PATH", "/run/pmg-pass")
    monkeypatch.setenv("PROXIMO_PMG_USERNAME", "admin@pve")
    monkeypatch.setenv("PROXIMO_PMG_NODE", "mail1")
    monkeypatch.setenv("PROXIMO_PMG_VERIFY_TLS", "false")
    monkeypatch.setenv("PROXIMO_PMG_CA_BUNDLE", "/etc/ssl/ca.pem")
    # ca_bundle IS set — no TLS warning fires
    cfg = PmgConfig.from_env()
    assert cfg.username == "admin@pve"
    assert cfg.node == "mail1"
    assert cfg.verify_tls is False
    assert cfg.ca_bundle == "/etc/ssl/ca.pem"


def test_pmgconfig_from_env_missing_url_raises(monkeypatch):
    monkeypatch.delenv("PROXIMO_PMG_BASE_URL", raising=False)
    monkeypatch.setenv("PROXIMO_PMG_PASSWORD_PATH", "/run/pmg-pass")
    with pytest.raises(RuntimeError, match="PROXIMO_PMG_BASE_URL"):
        PmgConfig.from_env()


def test_pmgconfig_from_env_missing_password_path_raises(monkeypatch):
    monkeypatch.setenv("PROXIMO_PMG_BASE_URL", "https://pmg:8006/api2/json")
    monkeypatch.delenv("PROXIMO_PMG_PASSWORD_PATH", raising=False)
    with pytest.raises(RuntimeError, match="PROXIMO_PMG_PASSWORD_PATH"):
        PmgConfig.from_env()


def test_pmgconfig_from_env_warns_on_no_tls_verify_no_bundle(monkeypatch):
    monkeypatch.setenv("PROXIMO_PMG_BASE_URL", "https://pmg:8006/api2/json")
    monkeypatch.setenv("PROXIMO_PMG_PASSWORD_PATH", "/run/pmg-pass")
    monkeypatch.setenv("PROXIMO_PMG_VERIFY_TLS", "false")
    monkeypatch.delenv("PROXIMO_PMG_CA_BUNDLE", raising=False)
    with pytest.warns(UserWarning, match="without cert validation"):
        PmgConfig.from_env()


# ---------------------------------------------------------------------------
# PmgBackend FAIL-CLOSED
# ---------------------------------------------------------------------------

def test_pmgbackend_fails_closed_on_unverified_tls():
    """A credential-bearing backend must REFUSE to construct over unverified TLS (no ca_bundle)."""
    with pytest.raises(ProximoError):
        PmgBackend(_cfg(verify_tls=False))


def test_pmgbackend_ok_with_ca_bundle_even_when_verify_false():
    """A ca_bundle provides a trust anchor — construction is allowed."""
    backend = PmgBackend(_cfg(verify_tls=False, ca_bundle="/etc/ssl/certs/ca-certificates.crt"))
    assert backend.config.ca_bundle == "/etc/ssl/certs/ca-certificates.crt"


def test_pmgbackend_ok_with_default_verify():
    backend = PmgBackend(_cfg())  # verify_tls defaults True
    assert backend.config.verify_tls is True


# ---------------------------------------------------------------------------
# PmgConfig is frozen / immutable
# ---------------------------------------------------------------------------

def test_pmgconfig_is_frozen():
    from dataclasses import FrozenInstanceError
    cfg = _cfg()
    with pytest.raises(FrozenInstanceError):
        cfg.base_url = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PmgBackend — lazy login (no network call at construction time)
# ---------------------------------------------------------------------------

def test_pmgbackend_no_login_at_construction(tmp_path):
    """PmgBackend constructs without any POST to /access/ticket."""
    pw_file = tmp_path / "password"
    pw_file.write_text("secret\n")

    mock_client = MagicMock()
    backend = PmgBackend(_cfg(password_path=str(pw_file)))
    backend._client = mock_client

    # No network calls at construction
    mock_client.post.assert_not_called()
    mock_client.get.assert_not_called()
    assert backend._ticket is None
    assert backend._csrf is None


# ---------------------------------------------------------------------------
# PmgBackend — login flow
# ---------------------------------------------------------------------------

def _make_login_resp(ticket: str = "PMG:root@pam::ticket", csrf: str = "csrf-tok") -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"data": {"ticket": ticket, "CSRFPreventionToken": csrf,
                                        "username": "root@pam"}}
    resp.raise_for_status = MagicMock()
    return resp


def test_login_posts_to_access_ticket(tmp_path):
    """_login() POSTs to /access/ticket and caches ticket + CSRF."""
    pw_file = tmp_path / "password"
    pw_file.write_text("s3cr3t\n")

    mock_client = MagicMock()
    mock_client.post.return_value = _make_login_resp()

    backend = PmgBackend(_cfg(password_path=str(pw_file)))
    backend._client = mock_client
    backend._login()

    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert "/access/ticket" in call_args[0][0]
    assert backend._ticket == "PMG:root@pam::ticket"
    assert backend._csrf == "csrf-tok"


def test_login_reads_password_from_file(tmp_path):
    """_login() reads the password from the file, not from a cached value."""
    pw_file = tmp_path / "password"
    pw_file.write_text("my-password\n")

    mock_client = MagicMock()
    mock_client.post.return_value = _make_login_resp()

    backend = PmgBackend(_cfg(password_path=str(pw_file), username="root@pam"))
    backend._client = mock_client
    backend._login()

    call_kwargs = mock_client.post.call_args[1]
    form_data = call_kwargs.get("data", {})
    assert form_data.get("username") == "root@pam"
    assert form_data.get("password") == "my-password"


def test_login_password_not_cached_disk(tmp_path):
    """Password is read at login time, not stored in config or backend state."""
    pw_file = tmp_path / "password"
    pw_file.write_text("pass-v1\n")

    mock_client = MagicMock()
    mock_client.post.return_value = _make_login_resp(ticket="t1")

    backend = PmgBackend(_cfg(password_path=str(pw_file)))
    backend._client = mock_client
    backend._login()

    # Change the file — next login reads the new password
    pw_file.write_text("pass-v2\n")
    mock_client.post.return_value = _make_login_resp(ticket="t2")
    backend._ticket = None  # force re-login
    backend._login()

    calls = mock_client.post.call_args_list
    assert calls[0][1]["data"]["password"] == "pass-v1"
    assert calls[1][1]["data"]["password"] == "pass-v2"


def test_ensure_ticket_calls_login_once(tmp_path):
    """_ensure_ticket() calls _login() only when no ticket is cached."""
    pw_file = tmp_path / "password"
    pw_file.write_text("s3cr3t\n")

    mock_client = MagicMock()
    mock_client.post.return_value = _make_login_resp()

    backend = PmgBackend(_cfg(password_path=str(pw_file)))
    backend._client = mock_client

    backend._ensure_ticket()
    backend._ensure_ticket()  # second call — ticket already cached

    assert mock_client.post.call_count == 1


def test_ensure_ticket_concurrent_login_called_once(tmp_path):
    """Two threads racing on _ensure_ticket() must trigger _login() exactly once.

    A Barrier forces both threads to the check point simultaneously; a sleep inside
    the mocked _login widens the race window so the double-login is deterministic
    without the fix (and reliably absent with it).
    """
    pw_file = tmp_path / "password"
    pw_file.write_text("secret\n")

    backend = PmgBackend(_cfg(password_path=str(pw_file)))

    login_call_count = 0
    barrier = threading.Barrier(2)

    def slow_login() -> None:
        nonlocal login_call_count
        login_call_count += 1
        time.sleep(0.05)  # widen the window: second thread sees _ticket is None
        backend._ticket = "PMG:root@pam::ticket"
        backend._csrf = "csrf-tok"

    backend._login = slow_login  # type: ignore[method-assign]

    errors: list[Exception] = []

    def run() -> None:
        try:
            barrier.wait()  # both threads reach _ensure_ticket simultaneously
            backend._ensure_ticket()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=run)
    t2 = threading.Thread(target=run)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert not errors, f"thread error(s): {errors}"
    assert login_call_count == 1, (
        f"_login called {login_call_count} times — expected exactly once (race condition)"
    )


# ---------------------------------------------------------------------------
# PmgBackend — cookie and CSRF headers
# ---------------------------------------------------------------------------

def _mock_backend(response_data, *, status_code: int = 200,
                  password_content: str = "s3cr3t") -> tuple:  # noqa: S107
    """Returns (backend, mock_client) with a pre-seeded ticket (already logged in).

    Login is NOT exercised by this helper — use the login-flow tests for that.
    """
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = {"data": response_data}
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp
    mock_client.post.return_value = mock_resp

    tmp = pathlib.Path(tempfile.mkdtemp()) / "password"
    tmp.write_text(password_content + "\n")

    backend = PmgBackend(_cfg(password_path=str(tmp)))
    backend._client = mock_client
    # Pre-seed ticket so tests don't trigger login (login tested in separate section)
    backend._ticket = "PMG:root@pam::test-ticket"
    backend._csrf = "test-csrf-token"
    return backend, mock_client


def test_get_sends_pmg_auth_cookie():
    """GET sends Cookie: PMGAuthCookie=<ticket> — no CSRF header."""
    backend, mock_client = _mock_backend({})
    backend._get("/nodes/pmg/version")
    call_kwargs = mock_client.get.call_args[1]
    headers = call_kwargs.get("headers", {})
    assert headers.get("Cookie") == "PMGAuthCookie=PMG:root@pam::test-ticket"
    assert "CSRFPreventionToken" not in headers


def test_post_sends_cookie_and_csrf():
    """POST (mutation) sends both PMGAuthCookie and CSRFPreventionToken."""
    backend, mock_client = _mock_backend(None)
    backend._post("/quarantine/mails/abc123/deliver")
    call_kwargs = mock_client.post.call_args[1]
    headers = call_kwargs.get("headers", {})
    assert headers.get("Cookie") == "PMGAuthCookie=PMG:root@pam::test-ticket"
    assert headers.get("CSRFPreventionToken") == "test-csrf-token"


def test_get_does_not_send_csrf():
    """GET must NOT include CSRFPreventionToken — reads don't need CSRF."""
    backend, mock_client = _mock_backend({})
    backend._get("/access/permissions")
    headers = mock_client.get.call_args[1].get("headers", {})
    assert "CSRFPreventionToken" not in headers


def test_post_csrf_different_from_cookie_key():
    """CSRFPreventionToken header key is distinct from the cookie key."""
    backend, mock_client = _mock_backend(None)
    backend._post("/quarantine/mails/abc123/deliver")
    headers = mock_client.post.call_args[1].get("headers", {})
    assert "CSRFPreventionToken" in headers
    assert "PMGAuthCookie" in headers.get("Cookie", "")


# ---------------------------------------------------------------------------
# PmgBackend — 401 retry
# ---------------------------------------------------------------------------

def test_get_on_401_relogins_and_retries(tmp_path):
    """On HTTP 401 from GET: clear ticket, re-login once, retry; succeed on second try."""
    pw_file = tmp_path / "password"
    pw_file.write_text("secret\n")

    login_resp = _make_login_resp(ticket="new-ticket", csrf="new-csrf")

    resp_401 = MagicMock()
    resp_401.status_code = 401

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = {"data": {"version": "9.1"}}
    resp_200.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.get.side_effect = [resp_401, resp_200]
    mock_client.post.return_value = login_resp  # login POST

    backend = PmgBackend(_cfg(password_path=str(pw_file)))
    backend._ticket = "stale-ticket"
    backend._csrf = "stale-csrf"
    backend._client = mock_client

    result = backend._get("/nodes/pmg/version")

    assert result == {"version": "9.1"}
    assert backend._ticket == "new-ticket"
    assert backend._csrf == "new-csrf"
    # GET was called twice (first 401, then retry)
    assert mock_client.get.call_count == 2
    # Login (POST /access/ticket) was called exactly once
    assert mock_client.post.call_count == 1
    assert "/access/ticket" in mock_client.post.call_args[0][0]


def test_get_on_persistent_401_raises(tmp_path):
    """If retry after re-login also returns 401, raise_for_status must raise."""
    pw_file = tmp_path / "password"
    pw_file.write_text("secret\n")

    login_resp = _make_login_resp()

    resp_401 = MagicMock()
    resp_401.status_code = 401

    resp_401_retry = MagicMock()
    resp_401_retry.status_code = 401
    resp_401_retry.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("401", request=MagicMock(), response=MagicMock())
    )

    mock_client = MagicMock()
    mock_client.get.side_effect = [resp_401, resp_401_retry]
    mock_client.post.return_value = login_resp

    backend = PmgBackend(_cfg(password_path=str(pw_file)))
    backend._ticket = "stale-ticket"
    backend._csrf = "stale-csrf"
    backend._client = mock_client

    with pytest.raises(httpx.HTTPStatusError):
        backend._get("/nodes/pmg/version")
    assert mock_client.get.call_count == 2


def test_post_on_401_relogins_and_retries(tmp_path):
    """On HTTP 401 from POST: clear ticket, re-login once, retry; succeed on second try."""
    pw_file = tmp_path / "password"
    pw_file.write_text("secret\n")

    login_resp = _make_login_resp(ticket="new-ticket", csrf="new-csrf")

    resp_401 = MagicMock()
    resp_401.status_code = 401

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = {"data": None}
    resp_200.raise_for_status = MagicMock()

    mock_client = MagicMock()
    # post: first call is the data POST (401), second is login, third is retry data POST
    mock_client.post.side_effect = [resp_401, login_resp, resp_200]

    backend = PmgBackend(_cfg(password_path=str(pw_file)))
    backend._ticket = "stale-ticket"
    backend._csrf = "stale-csrf"
    backend._client = mock_client

    backend._post("/quarantine/mails/abc123/deliver")

    # 3 POST calls: data-401, login, data-retry
    assert mock_client.post.call_count == 3
    assert "/access/ticket" in mock_client.post.call_args_list[1][0][0]


# ---------------------------------------------------------------------------
# PmgBackend HTTP methods — basic call-through
# ---------------------------------------------------------------------------

def test_get_calls_httpx_get():
    backend, mock_client = _mock_backend({"version": "8.0"})
    backend._get("/nodes/pmg/version")
    mock_client.get.assert_called_once()
    call_args = mock_client.get.call_args
    assert call_args[0][0] == "/nodes/pmg/version"


def test_get_with_params_passes_params():
    backend, mock_client = _mock_backend([])
    backend._get("/statistics/mail", params={"start": 1717000000})
    call_kwargs = mock_client.get.call_args[1]
    assert call_kwargs.get("params", {}).get("start") == 1717000000


def test_post_calls_httpx_post():
    backend, mock_client = _mock_backend(None)
    backend._post("/quarantine/mails/abc123/deliver")
    mock_client.post.assert_called_once()


def test_get_raises_for_status():
    """raise_for_status is called on every response."""
    backend, mock_client = _mock_backend({})
    backend._get("/nodes/pmg/version")
    mock_client.get.return_value.raise_for_status.assert_called_once()


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

class TestCheckNode:
    def test_valid_node(self):
        assert _check_node("pmg") == "pmg"

    def test_valid_node_with_hyphen(self):
        assert _check_node("pmg-node1") == "pmg-node1"

    def test_valid_alphanumeric(self):
        assert _check_node("mail1") == "mail1"

    def test_rejects_slash(self):
        with pytest.raises(ProximoError):
            _check_node("pmg/node")

    def test_rejects_newline(self):
        with pytest.raises(ProximoError):
            _check_node("pmg\n")

    def test_rejects_empty(self):
        with pytest.raises(ProximoError):
            _check_node("")

    def test_rejects_leading_hyphen(self):
        with pytest.raises(ProximoError):
            _check_node("-pmg")

    def test_rejects_space(self):
        with pytest.raises(ProximoError):
            _check_node("pmg node")

    def test_rejects_dotdot(self):
        with pytest.raises(ProximoError):
            _check_node("../etc")


class TestCheckMailId:
    def test_valid_alphanumeric(self):
        assert _check_mail_id("abc123") == "abc123"

    def test_valid_with_dots_and_hyphens(self):
        assert _check_mail_id("msg-2024.01.15") == "msg-2024.01.15"

    def test_valid_with_underscore(self):
        assert _check_mail_id("A1_B2") == "A1_B2"

    def test_rejects_slash(self):
        with pytest.raises(ProximoError):
            _check_mail_id("abc/def")

    def test_rejects_newline(self):
        with pytest.raises(ProximoError):
            _check_mail_id("abc\n")

    def test_rejects_empty(self):
        with pytest.raises(ProximoError):
            _check_mail_id("")

    def test_rejects_leading_dot(self):
        with pytest.raises(ProximoError):
            _check_mail_id(".hidden")

    def test_rejects_dotdot_traversal(self):
        with pytest.raises(ProximoError):
            _check_mail_id("../etc")


# ---------------------------------------------------------------------------
# _api() — recording SimpleNamespace for tool/plan tests
# ---------------------------------------------------------------------------

def _api() -> SimpleNamespace:
    """Minimal PMG API fake recording _get / _post / _put / _delete calls.

    Includes a mock config with username="root@pam" to match the real
    PmgBackend — quarantine_blocklist / quarantine_blocklist_add now
    default pmail to api.config.username when none is supplied (PMG 9.1
    live-verified: pmail is required for root@pam).

    W3: added _put and _delete recorders so W3 mutation ops can be tested
    without AttributeError.
    """
    seen: dict = {}

    def fake_get(path, params=None):
        seen["method"] = "GET"
        seen["path"] = path
        seen["params"] = params or {}
        return {}

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
        seen["params"] = params or {}
        return None

    config = SimpleNamespace(username="root@pam")
    return SimpleNamespace(
        _get=fake_get, _post=fake_post, _put=fake_put, _delete=fake_delete,
        seen=seen, config=config,
    )


# ---------------------------------------------------------------------------
# READ operations — URL shapes and duck-typed API
# ---------------------------------------------------------------------------

class TestNodeVersion:
    def test_uses_correct_path(self):
        # PMG 9.1 live-verified: version is global; path is /version (no node segment)
        api = _api()
        node_version(api, "pmg")
        assert api.seen["path"] == "/version"
        assert api.seen["method"] == "GET"

    def test_node_not_in_path(self):
        # The node param is validated but NOT used in the path — PMG version is global
        api = _api()
        node_version(api, "mail1")
        assert api.seen["path"] == "/version"
        assert "mail1" not in api.seen["path"]

    def test_rejects_invalid_node(self):
        api = _api()
        with pytest.raises(ProximoError):
            node_version(api, "bad/node")

    def test_rejects_newline_in_node(self):
        api = _api()
        with pytest.raises(ProximoError):
            node_version(api, "pmg\n")


class TestAccessPermissions:
    def test_uses_correct_path(self):
        # PMG 9.1 live-verified: no /access/permissions endpoint; user/role info is
        # at /access/users
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(method="GET", path=path, params=params or {}) or []
        )
        access_permissions(api)
        assert api.seen["path"] == "/access/users"
        assert api.seen["method"] == "GET"

    def test_no_path_params(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        access_permissions(api)
        assert api.seen["params"] == {}


class TestNodeStatus:
    def test_uses_correct_path(self):
        api = _api()
        node_status(api, "pmg")
        assert api.seen["path"] == "/nodes/pmg/status"
        assert api.seen["method"] == "GET"

    def test_rejects_invalid_node(self):
        api = _api()
        with pytest.raises(ProximoError):
            node_status(api, "../etc")


class TestRelayConfig:
    def test_uses_correct_path(self):
        # PMG 9.1 live-verified: relay/smarthost settings are in /config/mail
        api = _api()
        relay_config(api)
        assert api.seen["path"] == "/config/mail"
        assert api.seen["method"] == "GET"


class TestDomainsList:
    def test_uses_correct_path(self):
        api = _api()
        # Patch to return a list (fake_get returns {} but domains_list falls back to [])
        api._get = lambda path, params=None: (
            api.seen.update(method="GET", path=path, params=params or {}) or []
        )
        domains_list(api)
        assert api.seen["path"] == "/config/domains"
        assert api.seen["method"] == "GET"

    def test_returns_list(self):
        api = _api()
        api._get = lambda path, params=None: []
        result = domains_list(api)
        assert isinstance(result, list)


class TestMailStatistics:
    def test_uses_correct_path(self):
        api = _api()
        statistics_mail(api)
        assert api.seen["path"] == "/statistics/mail"
        assert api.seen["method"] == "GET"

    def test_no_params_when_none(self):
        api = _api()
        statistics_mail(api)
        assert api.seen["params"] == {}


class TestQuarantineSpam:
    def test_uses_correct_path(self):
        # PMG 9.1 live-verified: spam quarantine list is at /quarantine/spam
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(method="GET", path=path, params=params or {}) or []
        )
        quarantine_spam(api)
        assert api.seen["path"] == "/quarantine/spam"
        assert api.seen["method"] == "GET"

    def test_no_params_when_none(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        quarantine_spam(api)
        assert api.seen["params"] == {}


# ---------------------------------------------------------------------------
# MUTATION operations — URL shapes and methods
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# TLS hardening regression
# ---------------------------------------------------------------------------

def test_pmgbackend_ca_bundle_path_no_httpx_deprecation():
    """PMG backend with a CA-bundle path must not hit httpx's deprecated verify=<str>."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        backend = PmgBackend(_cfg(verify_tls=False, ca_bundle="/etc/ssl/certs/ca-certificates.crt"))
    assert backend._client is not None


# ---------------------------------------------------------------------------
# W2: _check_service validator
# ---------------------------------------------------------------------------

class TestCheckService:
    def test_valid_simple(self):
        assert _check_service("postfix") == "postfix"

    def test_valid_with_hyphen(self):
        assert _check_service("pmg-smtp-filter") == "pmg-smtp-filter"

    def test_valid_alphanumeric(self):
        assert _check_service("clamav") == "clamav"

    def test_valid_spamassassin(self):
        assert _check_service("spamassassin") == "spamassassin"

    def test_rejects_slash(self):
        with pytest.raises(ProximoError):
            _check_service("../../etc/passwd")

    def test_rejects_newline(self):
        with pytest.raises(ProximoError):
            _check_service("postfix\n")

    def test_rejects_empty(self):
        with pytest.raises(ProximoError):
            _check_service("")

    def test_rejects_leading_hyphen(self):
        with pytest.raises(ProximoError):
            _check_service("-postfix")

    def test_rejects_space(self):
        with pytest.raises(ProximoError):
            _check_service("pmg daemon")


# ---------------------------------------------------------------------------
# W2 READ operations — URL shapes and duck-typed API
# ---------------------------------------------------------------------------

class TestStatisticsDomains:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(method="GET", path=path, params=params or {}) or []
        )
        statistics_domains(api)
        assert api.seen["path"] == "/statistics/domains"

    def test_maps_start_to_starttime(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        statistics_domains(api, start=1717000000)
        assert api.seen["params"].get("starttime") == 1717000000
        assert "start" not in api.seen["params"]

    def test_maps_end_to_endtime(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        statistics_domains(api, end=1717099999)
        assert api.seen["params"].get("endtime") == 1717099999
        assert "end" not in api.seen["params"]

    def test_no_params_when_neither_given(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params) or []
        )
        statistics_domains(api)
        # params should be None when no start/end given
        assert api.seen.get("params") is None

    def test_rejects_non_int_start(self):
        api = _api()
        with pytest.raises(ProximoError):
            statistics_domains(api, start="not-a-time")

    def test_rejects_non_int_end(self):
        api = _api()
        with pytest.raises(ProximoError):
            statistics_domains(api, end="not-a-time")


class TestStatisticsVirus:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(method="GET", path=path, params=params or {}) or []
        )
        statistics_virus(api)
        assert api.seen["path"] == "/statistics/virus"

    def test_maps_start_to_starttime(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        statistics_virus(api, start=1717000000)
        assert api.seen["params"].get("starttime") == 1717000000

    def test_rejects_non_int_start(self):
        api = _api()
        with pytest.raises(ProximoError):
            statistics_virus(api, start="bad")


class TestStatisticsSpamscores:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(method="GET", path=path, params=params or {}) or []
        )
        statistics_spamscores(api)
        assert api.seen["path"] == "/statistics/spamscores"

    def test_maps_start_to_starttime(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        statistics_spamscores(api, start=1717000000, end=1717099999)
        assert api.seen["params"].get("starttime") == 1717000000
        assert api.seen["params"].get("endtime") == 1717099999

    def test_rejects_non_int_end(self):
        api = _api()
        with pytest.raises(ProximoError):
            statistics_spamscores(api, end="bad")


class TestStatisticsRecent:
    def test_uses_correct_path(self):
        api = _api()
        statistics_recent(api)
        assert api.seen["path"] == "/statistics/recent"
        assert api.seen["method"] == "GET"

    def test_hours_forwarded_as_param(self):
        api = _api()
        statistics_recent(api, hours=6)
        assert api.seen["params"].get("hours") == 6

    def test_default_hours_is_1(self):
        api = _api()
        statistics_recent(api)
        assert api.seen["params"].get("hours") == 1

    def test_invalid_hours_raises_proximo_error(self):
        api = _api()
        with pytest.raises(ProximoError, match="invalid hours"):
            statistics_recent(api, hours="bad")


class TestQuarantineBlocklistList:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(method="GET", path=path, params=params) or []
        )
        quarantine_blocklist_list(api)
        assert api.seen["path"] == "/quarantine/blocklist"

    def test_pmail_defaults_to_username_when_none(self):
        # PMG 9.1 live-verified: pmail is required for root@pam.
        # When no pmail is given, the function defaults to api.config.username.
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params) or []
        )
        quarantine_blocklist_list(api)
        # No explicit pmail → defaults to api.config.username ("root@pam")
        assert api.seen.get("params") == {"pmail": "root@pam"}

    def test_pmail_included_when_provided(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        quarantine_blocklist_list(api, pmail="user@example.com")
        assert api.seen["params"].get("pmail") == "user@example.com"


class TestPostfixQshape:
    def test_uses_correct_path(self):
        api = _api()
        postfix_qshape(api, "pmg")
        assert api.seen["path"] == "/nodes/pmg/postfix/qshape"
        assert api.seen["method"] == "GET"

    def test_rejects_invalid_node(self):
        api = _api()
        with pytest.raises(ProximoError):
            postfix_qshape(api, "../etc")


class TestSpamConfig:
    def test_uses_correct_path(self):
        api = _api()
        spam_config(api)
        assert api.seen["path"] == "/config/spam"
        assert api.seen["method"] == "GET"


class TestServiceStatus:
    def test_uses_correct_path(self):
        api = _api()
        service_status(api, "postfix", "pmg")
        assert api.seen["path"] == "/nodes/pmg/services/postfix/state"
        assert api.seen["method"] == "GET"

    def test_defaults_node_to_pmg(self):
        api = _api()
        service_status(api, "clamav")
        assert "/nodes/pmg/services/clamav/state" == api.seen["path"]

    def test_rejects_invalid_service(self):
        api = _api()
        with pytest.raises(ProximoError):
            service_status(api, "../../etc/passwd")

    def test_rejects_service_with_newline(self):
        api = _api()
        with pytest.raises(ProximoError):
            service_status(api, "postfix\n")

    def test_rejects_invalid_node(self):
        api = _api()
        with pytest.raises(ProximoError):
            service_status(api, "postfix", "../etc")


# ---------------------------------------------------------------------------
# W2 MUTATION operations — body shapes
# ---------------------------------------------------------------------------

class TestQuarantineBlocklistAdd:
    def test_uses_correct_path_and_method(self):
        api = _api()
        quarantine_blocklist_add(api, "spam@evil.com")
        assert api.seen["path"] == "/quarantine/blocklist"
        assert api.seen["method"] == "POST"

    def test_body_includes_address(self):
        api = _api()
        quarantine_blocklist_add(api, "spam@evil.com")
        assert api.seen["data"].get("address") == "spam@evil.com"

    def test_pmail_included_in_body_when_given(self):
        api = _api()
        quarantine_blocklist_add(api, "spam@evil.com", pmail="user@example.com")
        assert api.seen["data"].get("pmail") == "user@example.com"

    def test_pmail_defaults_to_username_when_none(self):
        # PMG 9.1 live-verified: pmail is required for root@pam.
        # When no pmail is given, defaults to api.config.username.
        api = _api()
        quarantine_blocklist_add(api, "spam@evil.com")
        assert api.seen["data"].get("pmail") == "root@pam"


class TestQuarantineAction:
    def test_uses_correct_path_and_method(self):
        api = _api()
        quarantine_action(api, "deliver", "abc123")
        assert api.seen["path"] == "/quarantine/content"
        assert api.seen["method"] == "POST"

    def test_body_includes_action(self):
        api = _api()
        quarantine_action(api, "delete", "abc123")
        assert api.seen["data"].get("action") == "delete"

    def test_body_includes_id(self):
        api = _api()
        quarantine_action(api, "deliver", "abc123")
        assert api.seen["data"].get("id") == "abc123"

    def test_invalid_action_raises_proximo_error(self):
        api = _api()
        with pytest.raises(ProximoError, match="invalid quarantine action"):
            quarantine_action(api, "explode", "abc123")

    def test_all_valid_actions_accepted(self):
        for action in ("deliver", "delete", "mark-seen", "mark-unseen", "blocklist", "welcomelist"):
            api = _api()
            quarantine_action(api, action, "abc123")  # must not raise
            assert api.seen["data"].get("action") == action


class TestPostfixFlush:
    def test_uses_correct_path_and_method(self):
        api = _api()
        postfix_flush(api, "pmg")
        assert api.seen["path"] == "/nodes/pmg/postfix/flush_queues"
        assert api.seen["method"] == "POST"

    def test_rejects_invalid_node(self):
        api = _api()
        with pytest.raises(ProximoError):
            postfix_flush(api, "../etc")


# ---------------------------------------------------------------------------
# W2 PLAN operations — risk ratings and blast radius
# ---------------------------------------------------------------------------

class TestPlanQuarantineBlocklistAdd:
    def test_risk_is_low(self):
        p = plan_quarantine_blocklist_add("spam@evil.com")
        assert p.risk == RISK_LOW

    def test_action_string(self):
        p = plan_quarantine_blocklist_add("spam@evil.com")
        assert p.action == "pmg_quarantine_blocklist_add"

    def test_blast_radius_non_empty(self):
        p = plan_quarantine_blocklist_add("spam@evil.com")
        assert len(p.blast_radius) > 0

    def test_blast_mentions_additive(self):
        p = plan_quarantine_blocklist_add("spam@evil.com")
        text = " ".join(p.blast_radius).lower()
        assert "additive" in text or "not deleted" in text or "no message" in text

    def test_change_mentions_address(self):
        p = plan_quarantine_blocklist_add("spam@evil.com")
        assert "spam@evil.com" in p.change

    def test_rejects_invalid_mail_id(self):
        # No _check on address (it's POST body, not a URL segment) — just verify plan builds
        p = plan_quarantine_blocklist_add("any-address")
        assert p.action == "pmg_quarantine_blocklist_add"


class TestPlanQuarantineAction:
    def test_risk_is_medium(self):
        p = plan_quarantine_action("deliver", "abc123")
        assert p.risk == RISK_MEDIUM

    def test_delete_is_high(self):
        # permanent, irreversible message deletion must be HIGH, not MEDIUM
        p = plan_quarantine_action("delete", "abc123")
        assert p.risk == RISK_HIGH

    def test_action_string(self):
        p = plan_quarantine_action("delete", "abc123")
        assert p.action == "pmg_quarantine_action"

    def test_blast_radius_mentions_delete_irreversible(self):
        p = plan_quarantine_action("delete", "abc123")
        text = " ".join(p.blast_radius).lower()
        assert "irreversible" in text or "permanent" in text

    def test_blast_radius_mentions_action(self):
        p = plan_quarantine_action("deliver", "abc123")
        text = " ".join(p.blast_radius).lower()
        assert "deliver" in text

    def test_invalid_action_raises_proximo_error(self):
        with pytest.raises(ProximoError, match="invalid quarantine action"):
            plan_quarantine_action("explode", "abc123")

    def test_change_mentions_action_and_ids(self):
        p = plan_quarantine_action("mark-seen", "abc123")
        assert "mark-seen" in p.change
        assert "abc123" in p.change


class TestPlanPostfixFlush:
    def test_risk_is_low(self):
        p = plan_postfix_flush("pmg")
        assert p.risk == RISK_LOW

    def test_action_string(self):
        p = plan_postfix_flush("pmg")
        assert p.action == "pmg_postfix_flush"

    def test_blast_radius_non_empty(self):
        p = plan_postfix_flush("pmg")
        assert len(p.blast_radius) > 0

    def test_blast_mentions_queue_flush(self):
        p = plan_postfix_flush("pmg")
        text = " ".join(p.blast_radius).lower()
        assert "queue" in text or "flush" in text or "deliver" in text

    def test_rejects_invalid_node(self):
        with pytest.raises(ProximoError):
            plan_postfix_flush("../etc")


# ---------------------------------------------------------------------------
# W3: validators
# ---------------------------------------------------------------------------

class TestCheckDomain:
    def test_valid_simple_domain(self):
        assert _check_domain("example.com") == "example.com"

    def test_valid_single_char(self):
        assert _check_domain("a") == "a"

    def test_valid_with_hyphens(self):
        assert _check_domain("my-mail-server.example.com") == "my-mail-server.example.com"

    def test_valid_with_underscores(self):
        assert _check_domain("_dmarc.example.com") == "_dmarc.example.com"

    def test_rejects_slash(self):
        with pytest.raises(ProximoError):
            _check_domain("example/com")

    def test_rejects_dotdot_traversal(self):
        with pytest.raises(ProximoError):
            _check_domain("../etc")

    def test_rejects_newline(self):
        with pytest.raises(ProximoError):
            _check_domain("example.com\n")

    def test_rejects_space(self):
        with pytest.raises(ProximoError):
            _check_domain("example com")

    def test_rejects_empty(self):
        with pytest.raises(ProximoError):
            _check_domain("")

    def test_rejects_leading_hyphen(self):
        with pytest.raises(ProximoError):
            _check_domain("-example.com")


class TestCheckCidr:
    def test_valid_ipv4_cidr(self):
        assert _check_cidr("10.0.0.0/8") == "10.0.0.0/8"

    def test_valid_slash32(self):
        assert _check_cidr("192.168.1.1/32") == "192.168.1.1/32"

    def test_valid_ipv6_cidr(self):
        _check_cidr("2001:db8::/32")  # must not raise

    def test_rejects_invalid_cidr(self):
        with pytest.raises(ProximoError):
            _check_cidr("not-a-cidr")

    def test_rejects_dotdot_traversal(self):
        with pytest.raises(ProximoError):
            _check_cidr("../etc")

    def test_rejects_newline(self):
        with pytest.raises(ProximoError):
            _check_cidr("10.0.0.0/8\n")

    def test_rejects_invalid_octet(self):
        # IPv4 octets must be 0-255; 300 is out of range
        with pytest.raises(ProximoError):
            _check_cidr("300.300.300.300/8")


class TestCheckTransportProtocol:
    def test_valid_smtp(self):
        assert _check_transport_protocol("smtp") == "smtp"

    def test_valid_lmtp(self):
        assert _check_transport_protocol("lmtp") == "lmtp"

    def test_rejects_ftp(self):
        with pytest.raises(ProximoError):
            _check_transport_protocol("ftp")

    def test_rejects_empty(self):
        with pytest.raises(ProximoError):
            _check_transport_protocol("")

    def test_rejects_uppercase(self):
        with pytest.raises(ProximoError):
            _check_transport_protocol("SMTP")

    def test_error_message_lists_valid_values(self):
        with pytest.raises(ProximoError, match="lmtp"):
            _check_transport_protocol("ftp")


class TestCheckServiceAction:
    def test_valid_start(self):
        assert _check_service_action("start") == "start"

    def test_valid_stop(self):
        assert _check_service_action("stop") == "stop"

    def test_valid_restart(self):
        assert _check_service_action("restart") == "restart"

    def test_valid_reload(self):
        assert _check_service_action("reload") == "reload"

    def test_rejects_invalid(self):
        with pytest.raises(ProximoError):
            _check_service_action("explode")

    def test_rejects_empty(self):
        with pytest.raises(ProximoError):
            _check_service_action("")

    def test_error_message_lists_valid_values(self):
        with pytest.raises(ProximoError, match="restart"):
            _check_service_action("kill")


# ---------------------------------------------------------------------------
# W3 READ operations — URL shapes
# ---------------------------------------------------------------------------

class TestQuarantineWelcomelistList:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(method="GET", path=path, params=params) or []
        )
        quarantine_welcomelist_list(api)
        assert api.seen["path"] == "/quarantine/welcomelist"
        assert api.seen["method"] == "GET"

    def test_pmail_defaults_to_username_when_none(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params) or []
        )
        quarantine_welcomelist_list(api)
        assert api.seen.get("params", {}).get("pmail") == "root@pam"

    def test_pmail_passed_when_provided(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        quarantine_welcomelist_list(api, pmail="user@example.com")
        assert api.seen["params"].get("pmail") == "user@example.com"


# ---------------------------------------------------------------------------
# W3 MUTATION operations — body / path shapes
# ---------------------------------------------------------------------------

class TestDomainCreate:
    def test_uses_correct_path_and_method(self):
        api = _api()
        domain_create(api, "example.com")
        assert api.seen["path"] == "/config/domains"
        assert api.seen["method"] == "POST"

    def test_body_includes_domain(self):
        api = _api()
        domain_create(api, "example.com")
        assert api.seen["data"].get("domain") == "example.com"

    def test_comment_included_when_provided(self):
        api = _api()
        domain_create(api, "example.com", comment="primary domain")
        assert api.seen["data"].get("comment") == "primary domain"

    def test_comment_absent_when_not_provided(self):
        api = _api()
        domain_create(api, "example.com")
        assert "comment" not in api.seen["data"]

    def test_rejects_invalid_domain(self):
        api = _api()
        with pytest.raises(ProximoError):
            domain_create(api, "../etc")


class TestDomainDelete:
    def test_uses_correct_path_and_method(self):
        api = _api()
        domain_delete(api, "example.com")
        assert api.seen["path"] == "/config/domains/example.com"
        assert api.seen["method"] == "DELETE"

    def test_rejects_invalid_domain(self):
        api = _api()
        with pytest.raises(ProximoError):
            domain_delete(api, "bad/domain")


class TestTransportCreate:
    def test_uses_correct_path_and_method(self):
        api = _api()
        transport_create(api, "example.com", "relay.example.com")
        assert api.seen["path"] == "/config/transport"
        assert api.seen["method"] == "POST"

    def test_body_includes_required_fields(self):
        api = _api()
        transport_create(api, "example.com", "relay.example.com")
        d = api.seen["data"]
        assert d.get("domain") == "example.com"
        assert d.get("host") == "relay.example.com"
        assert d.get("port") == 25
        assert d.get("protocol") == "smtp"

    def test_custom_port_and_protocol(self):
        api = _api()
        transport_create(api, "example.com", "relay.example.com", port=24, protocol="lmtp")
        assert api.seen["data"]["port"] == 24
        assert api.seen["data"]["protocol"] == "lmtp"

    def test_rejects_invalid_protocol(self):
        api = _api()
        with pytest.raises(ProximoError):
            transport_create(api, "example.com", "relay.example.com", protocol="ftp")

    def test_rejects_invalid_domain(self):
        api = _api()
        with pytest.raises(ProximoError):
            transport_create(api, "../etc", "relay.example.com")

    def test_rejects_port_out_of_range(self):
        api = _api()
        with pytest.raises(ProximoError):
            transport_create(api, "example.com", "relay.example.com", port=0)

    def test_rejects_port_too_large(self):
        api = _api()
        with pytest.raises(ProximoError):
            transport_create(api, "example.com", "relay.example.com", port=65536)


class TestTransportDelete:
    def test_uses_correct_path_and_method(self):
        api = _api()
        transport_delete(api, "example.com")
        assert api.seen["path"] == "/config/transport/example.com"
        assert api.seen["method"] == "DELETE"

    def test_rejects_invalid_domain(self):
        api = _api()
        with pytest.raises(ProximoError):
            transport_delete(api, "bad/domain")


class TestMynetworksAdd:
    def test_uses_correct_path_and_method(self):
        api = _api()
        mynetworks_add(api, "10.0.0.0/8")
        assert api.seen["path"] == "/config/mynetworks"
        assert api.seen["method"] == "POST"

    def test_body_includes_cidr(self):
        api = _api()
        mynetworks_add(api, "10.0.0.0/8")
        assert api.seen["data"].get("cidr") == "10.0.0.0/8"

    def test_rejects_invalid_cidr(self):
        api = _api()
        with pytest.raises(ProximoError):
            mynetworks_add(api, "not-a-cidr")


class TestMynetworksRemove:
    def test_uses_correct_path_and_method(self):
        api = _api()
        mynetworks_remove(api, "10.0.0.0/8")
        assert api.seen["method"] == "DELETE"

    def test_cidr_slash_is_url_encoded_in_path(self):
        api = _api()
        mynetworks_remove(api, "10.0.0.0/8")
        # / → %2F so PMG does not interpret it as a path separator
        assert api.seen["path"] == "/config/mynetworks/10.0.0.0%2F8"

    def test_rejects_invalid_cidr(self):
        api = _api()
        with pytest.raises(ProximoError):
            mynetworks_remove(api, "not-a-cidr")


class TestSpamConfigUpdate:
    def test_uses_correct_path_and_method(self):
        api = _api()
        spam_config_update(api, bounce_score=5)
        assert api.seen["path"] == "/config/spam"
        assert api.seen["method"] == "PUT"

    def test_only_non_none_fields_in_body(self):
        api = _api()
        spam_config_update(api, bounce_score=5, use_bayes=None, use_razor=None)
        data = api.seen["data"]
        assert "bounce_score" in data
        assert "use_bayes" not in data
        assert "use_razor" not in data

    def test_multiple_fields_sent(self):
        api = _api()
        spam_config_update(api, use_bayes=True, maxspamsize=1000)
        data = api.seen["data"]
        assert "use_bayes" in data
        assert "maxspamsize" in data
        assert "bounce_score" not in data

    def test_empty_body_when_all_none(self):
        # When all kwargs are None, the body is empty (no PMG fields overridden)
        api = _api()
        spam_config_update(api)
        assert api.seen["data"] == {}


class TestQuarantineWelcomelistAdd:
    def test_uses_correct_path_and_method(self):
        api = _api()
        quarantine_welcomelist_add(api, "good@example.com")
        assert api.seen["path"] == "/quarantine/welcomelist"
        assert api.seen["method"] == "POST"

    def test_body_includes_address_and_pmail(self):
        api = _api()
        quarantine_welcomelist_add(api, "good@example.com")
        d = api.seen["data"]
        assert d.get("address") == "good@example.com"
        assert d.get("pmail") == "root@pam"  # defaults to api.config.username

    def test_pmail_override(self):
        api = _api()
        quarantine_welcomelist_add(api, "good@example.com", pmail="user@example.com")
        assert api.seen["data"].get("pmail") == "user@example.com"


class TestQuarantineWelcomelistRemove:
    def test_uses_correct_path_and_method(self):
        api = _api()
        quarantine_welcomelist_remove(api, "good@example.com")
        assert api.seen["path"] == "/quarantine/welcomelist"
        assert api.seen["method"] == "DELETE"

    def test_address_and_pmail_as_params(self):
        api = _api()
        quarantine_welcomelist_remove(api, "good@example.com")
        p = api.seen["params"]
        assert p.get("address") == "good@example.com"
        assert p.get("pmail") == "root@pam"

    def test_pmail_override(self):
        api = _api()
        quarantine_welcomelist_remove(api, "good@example.com", pmail="user@example.com")
        assert api.seen["params"].get("pmail") == "user@example.com"


class TestQuarantineBlocklistRemove:
    """Test the W2 executor that the W3 plan function now gates."""

    def test_uses_correct_path_and_method(self):
        api = _api()
        quarantine_blocklist_remove(api, "spam@evil.com")
        assert api.seen["path"] == "/quarantine/blocklist"
        assert api.seen["method"] == "DELETE"

    def test_address_and_pmail_as_params(self):
        api = _api()
        quarantine_blocklist_remove(api, "spam@evil.com")
        p = api.seen["params"]
        assert p.get("address") == "spam@evil.com"
        assert p.get("pmail") == "root@pam"  # defaults to api.config.username

    def test_pmail_override(self):
        api = _api()
        quarantine_blocklist_remove(api, "spam@evil.com", pmail="user@example.com")
        assert api.seen["params"].get("pmail") == "user@example.com"


class TestQuarantineBlocklistRemovePlan:
    """Test the new plan function (executor already existed in W2)."""

    def test_risk_is_low(self):
        p = plan_quarantine_blocklist_remove("spam@evil.com")
        assert p.risk == RISK_LOW

    def test_action_string(self):
        p = plan_quarantine_blocklist_remove("spam@evil.com")
        assert p.action == "pmg_quarantine_blocklist_remove"

    def test_change_mentions_address(self):
        p = plan_quarantine_blocklist_remove("spam@evil.com")
        assert "spam@evil.com" in p.change

    def test_blast_radius_non_empty(self):
        p = plan_quarantine_blocklist_remove("spam@evil.com")
        assert len(p.blast_radius) > 0

    def test_target_is_quarantine_blocklist(self):
        p = plan_quarantine_blocklist_remove("spam@evil.com")
        assert "blocklist" in p.target


class TestServiceControl:
    def test_uses_correct_path_and_method(self):
        api = _api()
        service_control(api, "postfix", "restart", "pmg")
        assert api.seen["path"] == "/nodes/pmg/services/postfix/restart"
        assert api.seen["method"] == "POST"

    def test_defaults_node_to_pmg(self):
        api = _api()
        service_control(api, "clamav", "stop")
        assert api.seen["path"] == "/nodes/pmg/services/clamav/stop"

    def test_rejects_invalid_action(self):
        api = _api()
        with pytest.raises(ProximoError):
            service_control(api, "postfix", "explode")

    def test_rejects_invalid_service(self):
        api = _api()
        with pytest.raises(ProximoError):
            service_control(api, "../../etc/passwd", "start")

    def test_all_valid_actions_accepted(self):
        for action in ("start", "stop", "restart", "reload"):
            api = _api()
            service_control(api, "postfix", action, "pmg")  # must not raise
            assert action in api.seen["path"]


# ---------------------------------------------------------------------------
# W3 PLAN operations — risk ratings and blast radius
# ---------------------------------------------------------------------------

class TestPlanDomainCreate:
    def test_risk_is_low(self):
        p = plan_domain_create("example.com")
        assert p.risk == RISK_LOW

    def test_action_string(self):
        p = plan_domain_create("example.com")
        assert p.action == "pmg_domain_create"

    def test_change_mentions_domain(self):
        p = plan_domain_create("example.com")
        assert "example.com" in p.change

    def test_blast_radius_non_empty(self):
        p = plan_domain_create("example.com")
        assert len(p.blast_radius) > 0

    def test_rejects_invalid_domain(self):
        with pytest.raises(ProximoError):
            plan_domain_create("../etc")


class TestPlanDomainDelete:
    def test_risk_is_medium(self):
        p = plan_domain_delete("example.com")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_domain_delete("example.com")
        assert p.action == "pmg_domain_delete"

    def test_change_mentions_domain(self):
        p = plan_domain_delete("example.com")
        assert "example.com" in p.change

    def test_rejects_invalid_domain(self):
        with pytest.raises(ProximoError):
            plan_domain_delete("bad/domain")


class TestPlanTransportCreate:
    def test_risk_is_low(self):
        p = plan_transport_create("example.com", "relay.example.com")
        assert p.risk == RISK_LOW

    def test_action_string(self):
        p = plan_transport_create("example.com", "relay.example.com")
        assert p.action == "pmg_transport_create"

    def test_change_mentions_domain_and_host(self):
        p = plan_transport_create("example.com", "relay.example.com")
        assert "example.com" in p.change
        assert "relay.example.com" in p.change

    def test_rejects_invalid_protocol(self):
        with pytest.raises(ProximoError):
            plan_transport_create("example.com", "relay.example.com", protocol="ftp")

    def test_rejects_invalid_domain(self):
        with pytest.raises(ProximoError):
            plan_transport_create("bad/domain", "relay.example.com")


class TestPlanTransportDelete:
    def test_risk_is_medium(self):
        p = plan_transport_delete("example.com")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_transport_delete("example.com")
        assert p.action == "pmg_transport_delete"

    def test_rejects_invalid_domain(self):
        with pytest.raises(ProximoError):
            plan_transport_delete("bad/domain")


class TestPlanMynetworksAdd:
    def test_risk_is_low(self):
        p = plan_mynetworks_add("10.0.0.0/8")
        assert p.risk == RISK_LOW

    def test_action_string(self):
        p = plan_mynetworks_add("10.0.0.0/8")
        assert p.action == "pmg_mynetworks_add"

    def test_change_mentions_cidr(self):
        p = plan_mynetworks_add("10.0.0.0/8")
        assert "10.0.0.0/8" in p.change

    def test_rejects_invalid_cidr(self):
        with pytest.raises(ProximoError):
            plan_mynetworks_add("not-a-cidr")


class TestPlanMynetworksRemove:
    def test_risk_is_medium(self):
        p = plan_mynetworks_remove("10.0.0.0/8")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_mynetworks_remove("10.0.0.0/8")
        assert p.action == "pmg_mynetworks_remove"

    def test_rejects_invalid_cidr(self):
        with pytest.raises(ProximoError):
            plan_mynetworks_remove("not-a-cidr")


class TestPlanSpamConfigUpdate:
    def test_risk_is_medium(self):
        p = plan_spam_config_update(bounce_score=5)
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_spam_config_update(use_bayes=True)
        assert p.action == "pmg_spam_config_update"

    def test_change_mentions_field(self):
        p = plan_spam_config_update(bounce_score=5)
        assert "bounce_score" in p.change

    def test_blast_radius_mentions_mail_impact(self):
        p = plan_spam_config_update(bounce_score=5)
        text = " ".join(p.blast_radius).lower()
        assert "mail" in text or "spam" in text or "filter" in text

    def test_raises_when_all_none(self):
        with pytest.raises(ProximoError):
            plan_spam_config_update()


class TestPlanQuarantineWelcomelistAdd:
    def test_risk_is_low(self):
        p = plan_quarantine_welcomelist_add("good@example.com")
        assert p.risk == RISK_LOW

    def test_action_string(self):
        p = plan_quarantine_welcomelist_add("good@example.com")
        assert p.action == "pmg_quarantine_welcomelist_add"

    def test_change_mentions_address(self):
        p = plan_quarantine_welcomelist_add("good@example.com")
        assert "good@example.com" in p.change

    def test_blast_radius_non_empty(self):
        p = plan_quarantine_welcomelist_add("good@example.com")
        assert len(p.blast_radius) > 0


class TestPlanQuarantineWelcomelistRemove:
    def test_risk_is_low(self):
        p = plan_quarantine_welcomelist_remove("good@example.com")
        assert p.risk == RISK_LOW

    def test_action_string(self):
        p = plan_quarantine_welcomelist_remove("good@example.com")
        assert p.action == "pmg_quarantine_welcomelist_remove"


class TestPlanServiceControl:
    def test_risk_is_medium(self):
        p = plan_service_control("postfix", "stop")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_service_control("postfix", "start")
        assert p.action == "pmg_service_control"

    def test_change_mentions_service_and_action(self):
        p = plan_service_control("postfix", "restart")
        assert "postfix" in p.change
        assert "restart" in p.change

    def test_blast_radius_warns_mail_delivery_interruption(self):
        p = plan_service_control("postfix", "stop")
        text = " ".join(p.blast_radius).lower()
        assert "interrupts mail delivery" in text

    def test_blast_radius_warns_manually_restarted(self):
        p = plan_service_control("postfix", "stop")
        text = " ".join(p.blast_radius).lower()
        assert "manually restarted" in text

    def test_invalid_action_raises_proximo_error(self):
        with pytest.raises(ProximoError):
            plan_service_control("postfix", "explode")

    def test_invalid_service_raises_proximo_error(self):
        with pytest.raises(ProximoError):
            plan_service_control("../../etc/passwd", "stop")


# ---------------------------------------------------------------------------
# W4 Validator tests
# ---------------------------------------------------------------------------

class TestCheckRrddataTimeframe:
    def test_valid_values_pass(self):
        for v in ("hour", "day", "week", "month", "year"):
            assert _check_rrddata_timeframe(v) == v

    def test_invalid_value_raises(self):
        with pytest.raises(ProximoError):
            _check_rrddata_timeframe("minute")

    def test_empty_raises(self):
        with pytest.raises(ProximoError):
            _check_rrddata_timeframe("")


class TestCheckRrddataCf:
    def test_valid_values_pass(self):
        assert _check_rrddata_cf("AVERAGE") == "AVERAGE"
        assert _check_rrddata_cf("MAX") == "MAX"

    def test_invalid_value_raises(self):
        with pytest.raises(ProximoError):
            _check_rrddata_cf("MIN")

    def test_lowercase_raises(self):
        with pytest.raises(ProximoError):
            _check_rrddata_cf("average")


class TestCheckBackupNotify:
    def test_valid_values_pass(self):
        for v in ("always", "error", "never"):
            assert _check_backup_notify(v) == v

    def test_invalid_value_raises(self):
        with pytest.raises(ProximoError):
            _check_backup_notify("sometimes")


class TestCheckQuarantineType:
    def test_valid_values_pass(self):
        for v in ("spam", "virus", "attachment"):
            assert _check_quarantine_type(v) == v

    def test_invalid_value_raises(self):
        with pytest.raises(ProximoError):
            _check_quarantine_type("phishing")


# ---------------------------------------------------------------------------
# W4 READ op tests
# ---------------------------------------------------------------------------

class TestTrackerList:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path, params=params or {}) or []
        )
        tracker_list(api, "pmg")
        assert api.seen["path"] == "/nodes/pmg/tracker"

    def test_always_sends_limit(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        tracker_list(api, "pmg")
        assert api.seen["params"].get("limit") == 2000

    def test_maps_start_to_starttime(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        tracker_list(api, "pmg", start=1717000000)
        assert api.seen["params"].get("starttime") == 1717000000
        assert "start" not in api.seen["params"]

    def test_maps_from__to_from_key(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        tracker_list(api, "pmg", from_="sender@example.com")
        assert api.seen["params"].get("from") == "sender@example.com"
        assert "from_" not in api.seen["params"]

    def test_rejects_invalid_node(self):
        api = _api()
        with pytest.raises(ProximoError):
            tracker_list(api, "../../etc")

    def test_rejects_non_int_start(self):
        api = _api()
        with pytest.raises(ProximoError):
            tracker_list(api, "pmg", start="bad")


class TestTrackerDetail:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path) or []
        )
        tracker_detail(api, "pmg", "msg-abc123")
        assert api.seen["path"] == "/nodes/pmg/tracker/msg-abc123"

    def test_id_traversal_rejected(self):
        # id_ is a URL path segment — slash/traversal/injection metachars must be rejected
        api = _api()
        for bad in ("some/id", "../../etc", "id?x=1", "a#b", "id\nlog"):
            with pytest.raises(ProximoError, match="invalid tracker id"):
                tracker_detail(api, "pmg", bad)

    def test_clean_id_with_colon_passes(self):
        # mail-ish chars (e.g. ':') are still allowed — only structural metachars are blocked
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path) or []
        )
        tracker_detail(api, "pmg", "queue:ABC123")
        assert api.seen["path"] == "/nodes/pmg/tracker/queue:ABC123"

    def test_maps_start_to_starttime(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        tracker_detail(api, "pmg", "mid", start=1717000000)
        assert api.seen["params"].get("starttime") == 1717000000

    def test_no_params_when_no_start_end(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params) or []
        )
        tracker_detail(api, "pmg", "mid")
        assert api.seen.get("params") is None


class TestQuarantineVirus:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path) or []
        )
        quarantine_virus(api)
        assert api.seen["path"] == "/quarantine/virus"

    def test_defaults_pmail_to_config_username(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        quarantine_virus(api)
        assert api.seen["params"].get("pmail") == "root@pam"

    def test_explicit_pmail_overrides_default(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        quarantine_virus(api, pmail="user@domain.com")
        assert api.seen["params"].get("pmail") == "user@domain.com"

    def test_maps_start_to_starttime(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        quarantine_virus(api, start=1717000000)
        assert api.seen["params"].get("starttime") == 1717000000


class TestQuarantineAttachment:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path) or []
        )
        quarantine_attachment(api)
        assert api.seen["path"] == "/quarantine/attachment"

    def test_defaults_pmail_to_config_username(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        quarantine_attachment(api)
        assert api.seen["params"].get("pmail") == "root@pam"

    def test_maps_end_to_endtime(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        quarantine_attachment(api, end=1717099999)
        assert api.seen["params"].get("endtime") == 1717099999


class TestQuarantineVirusstatus:
    def test_uses_correct_path(self):
        api = _api()
        quarantine_virusstatus(api)
        assert api.seen["path"] == "/quarantine/virusstatus"
        assert api.seen["method"] == "GET"


class TestQuarantineSpamstatus:
    def test_uses_correct_path(self):
        api = _api()
        quarantine_spamstatus(api)
        assert api.seen["path"] == "/quarantine/spamstatus"
        assert api.seen["method"] == "GET"


class TestQuarantineSpamusers:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path, params=params or {}) or []
        )
        quarantine_spamusers(api)
        assert api.seen["path"] == "/quarantine/spamusers"

    def test_maps_quarantine_type_to_hyphen_key(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        quarantine_spamusers(api, quarantine_type="virus")
        assert api.seen["params"].get("quarantine-type") == "virus"
        assert "quarantine_type" not in api.seen["params"]

    def test_default_quarantine_type_is_spam(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        quarantine_spamusers(api)
        assert api.seen["params"].get("quarantine-type") == "spam"

    def test_invalid_quarantine_type_raises(self):
        api = _api()
        with pytest.raises(ProximoError):
            quarantine_spamusers(api, quarantine_type="phishing")

    def test_maps_start_to_starttime(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        quarantine_spamusers(api, start=1717000000)
        assert api.seen["params"].get("starttime") == 1717000000


class TestStatisticsMailcount:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path, params=params or {}) or []
        )
        statistics_mailcount(api)
        assert api.seen["path"] == "/statistics/mailcount"

    def test_always_sends_timespan(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        statistics_mailcount(api)
        assert api.seen["params"].get("timespan") == 3600

    def test_maps_start_to_starttime(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        statistics_mailcount(api, start=1717000000)
        assert api.seen["params"].get("starttime") == 1717000000

    def test_rejects_non_int_timespan(self):
        api = _api()
        with pytest.raises(ProximoError):
            statistics_mailcount(api, timespan="bad")

    def test_rejects_timespan_below_min(self):
        api = _api()
        with pytest.raises(ProximoError):
            statistics_mailcount(api, timespan=100)

    def test_rejects_timespan_above_max(self):
        api = _api()
        with pytest.raises(ProximoError):
            statistics_mailcount(api, timespan=99999999)


class TestStatisticsSender:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path, params=params) or []
        )
        statistics_sender(api)
        assert api.seen["path"] == "/statistics/sender"

    def test_no_params_when_none_given(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params) or []
        )
        statistics_sender(api)
        assert api.seen.get("params") is None

    def test_orderby_not_sent_to_api(self):
        # PMG 9.1 live-verified: /statistics/sender rejects 'orderby' with HTTP 400.
        # Proximo accepts the param for API compatibility but silently drops it.
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        statistics_sender(api, orderby="count:desc")
        assert "orderby" not in api.seen.get("params", {}), \
            "orderby must NOT be sent to PMG /statistics/sender (causes 400)"

    def test_maps_filter__to_filter_key(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        statistics_sender(api, filter_="example.com")
        assert api.seen["params"].get("filter") == "example.com"
        assert "filter_" not in api.seen["params"]

    def test_maps_start_to_starttime(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        statistics_sender(api, start=1717000000)
        assert api.seen["params"].get("starttime") == 1717000000


class TestStatisticsReceiver:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path, params=params) or []
        )
        statistics_receiver(api)
        assert api.seen["path"] == "/statistics/receiver"

    def test_no_params_when_none_given(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params) or []
        )
        statistics_receiver(api)
        assert api.seen.get("params") is None

    def test_orderby_passed_raw(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        statistics_receiver(api, orderby="bytes:asc")
        assert api.seen["params"].get("orderby") == "bytes:asc"

    def test_maps_filter__to_filter_key(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        statistics_receiver(api, filter_="user@example.com")
        assert api.seen["params"].get("filter") == "user@example.com"

    def test_rejects_non_int_start(self):
        api = _api()
        with pytest.raises(ProximoError):
            statistics_receiver(api, start="bad")


class TestNodeSyslog:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path, params=params) or []
        )
        node_syslog(api, "pmg")
        assert api.seen["path"] == "/nodes/pmg/syslog"

    def test_no_params_when_none_given(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params) or []
        )
        node_syslog(api, "pmg")
        assert api.seen.get("params") is None

    def test_passes_optional_params(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        node_syslog(api, "pmg", limit=100, service="postfix")
        p = api.seen["params"]
        assert p.get("limit") == 100
        assert p.get("service") == "postfix"

    def test_rejects_invalid_node(self):
        api = _api()
        with pytest.raises(ProximoError):
            node_syslog(api, "../../etc")


class TestNodeRrddata:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path, params=params or {}) or []
        )
        node_rrddata(api, "pmg", "day")
        assert api.seen["path"] == "/nodes/pmg/rrddata"

    def test_sends_timeframe_param(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        node_rrddata(api, "pmg", "week")
        assert api.seen["params"].get("timeframe") == "week"

    def test_optional_cf_sent_when_given(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        node_rrddata(api, "pmg", "day", cf="MAX")
        assert api.seen["params"].get("cf") == "MAX"

    def test_cf_absent_when_not_given(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        node_rrddata(api, "pmg", "day")
        assert "cf" not in api.seen["params"]

    def test_invalid_timeframe_raises(self):
        api = _api()
        with pytest.raises(ProximoError):
            node_rrddata(api, "pmg", "minute")

    def test_invalid_cf_raises(self):
        api = _api()
        with pytest.raises(ProximoError):
            node_rrddata(api, "pmg", "day", cf="MIN")


class TestTasksList:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path, params=params) or []
        )
        tasks_list(api, "pmg")
        assert api.seen["path"] == "/nodes/pmg/tasks"

    def test_no_params_when_none_given(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params) or []
        )
        tasks_list(api, "pmg")
        assert api.seen.get("params") is None

    def test_errors_bool_to_int(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(params=params or {}) or []
        )
        tasks_list(api, "pmg", errors=True)
        assert api.seen["params"].get("errors") == 1

    def test_rejects_invalid_node(self):
        api = _api()
        with pytest.raises(ProximoError):
            tasks_list(api, "../../etc")


# ---------------------------------------------------------------------------
# W4 MUTATION op tests
# ---------------------------------------------------------------------------

class TestBackupCreate:
    def test_posts_to_correct_path(self):
        api = _api()
        backup_create(api, "pmg")
        assert api.seen["path"] == "/nodes/pmg/backup"
        assert api.seen["method"] == "POST"

    def test_sends_notify_and_statistic(self):
        api = _api()
        backup_create(api, "pmg", notify="error", statistic=False)
        data = api.seen.get("data", {})
        assert data.get("notify") == "error"
        assert data.get("statistic") is False

    def test_invalid_notify_raises(self):
        api = _api()
        with pytest.raises(ProximoError):
            backup_create(api, "pmg", notify="sometimes")

    def test_invalid_node_raises(self):
        api = _api()
        with pytest.raises(ProximoError):
            backup_create(api, "../../etc")


# ---------------------------------------------------------------------------
# W4 PLAN function tests
# ---------------------------------------------------------------------------

class TestPlanBackupCreate:
    def test_risk_is_low(self):
        p = plan_backup_create("pmg")
        assert p.risk == RISK_LOW

    def test_action_string(self):
        p = plan_backup_create("pmg")
        assert p.action == "pmg_backup_create"

    def test_change_mentions_node(self):
        p = plan_backup_create("pmg")
        assert "pmg" in p.change

    def test_blast_radius_mentions_backup_path(self):
        p = plan_backup_create("pmg")
        text = " ".join(p.blast_radius)
        assert "/var/lib/pmg/backup/" in text

    def test_blast_radius_mentions_additive(self):
        p = plan_backup_create("pmg")
        text = " ".join(p.blast_radius).lower()
        assert "additive" in text

    def test_blast_radius_mentions_notify(self):
        p = plan_backup_create("pmg", notify="always")
        text = " ".join(p.blast_radius)
        assert "always" in text

    def test_invalid_notify_raises(self):
        with pytest.raises(ProximoError):
            plan_backup_create("pmg", notify="bad")

    def test_invalid_node_raises(self):
        with pytest.raises(ProximoError):
            plan_backup_create("../../etc")


# ---------------------------------------------------------------------------
# W5a Validator tests
# ---------------------------------------------------------------------------

class TestCheckRuledbId:
    def test_valid_integer_string(self):
        assert _check_ruledb_id("100") == "100"

    def test_valid_single_digit(self):
        assert _check_ruledb_id("0") == "0"

    def test_valid_large_id(self):
        assert _check_ruledb_id("99999") == "99999"

    def test_rejects_slash(self):
        with pytest.raises(ProximoError):
            _check_ruledb_id("100/200")

    def test_rejects_alpha(self):
        with pytest.raises(ProximoError):
            _check_ruledb_id("abc")

    def test_rejects_empty(self):
        with pytest.raises(ProximoError):
            _check_ruledb_id("")

    def test_rejects_dotdot_traversal(self):
        with pytest.raises(ProximoError):
            _check_ruledb_id("../etc")

    def test_rejects_newline(self):
        with pytest.raises(ProximoError):
            _check_ruledb_id("100\n")

    def test_rejects_space(self):
        with pytest.raises(ProximoError):
            _check_ruledb_id("100 200")


class TestCheckOgroup:
    def test_valid_simple(self):
        assert _check_ogroup("group1") == "group1"

    def test_valid_with_hyphen(self):
        assert _check_ogroup("my-group") == "my-group"

    def test_valid_with_underscore(self):
        assert _check_ogroup("my_group") == "my_group"

    def test_valid_single_char(self):
        assert _check_ogroup("a") == "a"

    def test_valid_mixed(self):
        assert _check_ogroup("Grp1-A_B") == "Grp1-A_B"

    def test_rejects_slash(self):
        with pytest.raises(ProximoError):
            _check_ogroup("group/bad")

    def test_rejects_dotdot_traversal(self):
        with pytest.raises(ProximoError):
            _check_ogroup("../etc")

    def test_rejects_newline(self):
        with pytest.raises(ProximoError):
            _check_ogroup("group\n")

    def test_rejects_empty(self):
        with pytest.raises(ProximoError):
            _check_ogroup("")

    def test_rejects_leading_hyphen(self):
        with pytest.raises(ProximoError):
            _check_ogroup("-group")

    def test_rejects_space(self):
        with pytest.raises(ProximoError):
            _check_ogroup("my group")


# ---------------------------------------------------------------------------
# W5a READ op tests
# ---------------------------------------------------------------------------

class TestRuledbRulesList:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path, method="GET") or []
        )
        ruledb_rules_list(api)
        assert api.seen["path"] == "/config/ruledb/rules"
        assert api.seen["method"] == "GET"

    def test_returns_list(self):
        api = _api()
        api._get = lambda path, params=None: []
        result = ruledb_rules_list(api)
        assert isinstance(result, list)


class TestRuledbRuleGet:
    def test_uses_correct_path(self):
        api = _api()
        ruledb_rule_get(api, "100")
        assert api.seen["path"] == "/config/ruledb/rules/100/config"
        assert api.seen["method"] == "GET"

    def test_id_interpolated_into_path(self):
        api = _api()
        ruledb_rule_get(api, "200")
        assert "200" in api.seen["path"]

    def test_rejects_invalid_id(self):
        api = _api()
        with pytest.raises(ProximoError):
            ruledb_rule_get(api, "bad/id")

    def test_rejects_newline_in_id(self):
        api = _api()
        with pytest.raises(ProximoError):
            ruledb_rule_get(api, "100\n")


class TestRuledbRuleFromList:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path) or []
        )
        ruledb_rule_from_list(api, "100")
        assert api.seen["path"] == "/config/ruledb/rules/100/from"

    def test_id_interpolated(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path) or []
        )
        ruledb_rule_from_list(api, "42")
        assert "42" in api.seen["path"]

    def test_rejects_invalid_id(self):
        api = _api()
        with pytest.raises(ProximoError):
            ruledb_rule_from_list(api, "../etc")


class TestRuledbRuleToList:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path) or []
        )
        ruledb_rule_to_list(api, "100")
        assert api.seen["path"] == "/config/ruledb/rules/100/to"

    def test_rejects_invalid_id(self):
        api = _api()
        with pytest.raises(ProximoError):
            ruledb_rule_to_list(api, "bad")


class TestRuledbRuleWhatList:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path) or []
        )
        ruledb_rule_what_list(api, "100")
        assert api.seen["path"] == "/config/ruledb/rules/100/what"

    def test_rejects_invalid_id(self):
        api = _api()
        with pytest.raises(ProximoError):
            ruledb_rule_what_list(api, "bad")


class TestRuledbRuleWhenList:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path) or []
        )
        ruledb_rule_when_list(api, "100")
        assert api.seen["path"] == "/config/ruledb/rules/100/when"

    def test_rejects_invalid_id(self):
        api = _api()
        with pytest.raises(ProximoError):
            ruledb_rule_when_list(api, "bad")


class TestRuledbRuleActionsList:
    def test_uses_correct_path(self):
        # PMG 9.1 live-verified: /rules/{id}/actions returns 501.
        # Actions are embedded in the rule config under the 'action' key.
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path) or {}
        )
        ruledb_rule_actions_list(api, "100")
        assert api.seen["path"] == "/config/ruledb/rules/100/config"

    def test_extracts_action_list(self):
        # Confirm we return the embedded 'action' list, not the whole config dict.
        api = _api()
        action_data = [{"id": 18, "name": "Block"}]
        api._get = lambda path, params=None: {"action": action_data, "name": "myrule"}
        result = ruledb_rule_actions_list(api, "100")
        assert result == action_data

    def test_id_interpolated(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path) or {}
        )
        ruledb_rule_actions_list(api, "500")
        assert "500" in api.seen["path"]

    def test_rejects_invalid_id(self):
        api = _api()
        with pytest.raises(ProximoError):
            ruledb_rule_actions_list(api, "bad/id")


class TestWhoGroupsList:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path, method="GET") or []
        )
        who_groups_list(api)
        assert api.seen["path"] == "/config/ruledb/who"
        assert api.seen["method"] == "GET"


class TestWhoGroupGet:
    def test_uses_correct_path(self):
        # PMG 9.1 live-verified: ogroup must be numeric ID (e.g. '2'), not a name.
        api = _api()
        who_group_get(api, "2")
        assert api.seen["path"] == "/config/ruledb/who/2/config"
        assert api.seen["method"] == "GET"

    def test_ogroup_interpolated(self):
        api = _api()
        who_group_get(api, "3")
        assert "3" in api.seen["path"]

    def test_rejects_non_numeric_ogroup(self):
        # Names like 'mygroup' are rejected — PMG 9.1 requires numeric IDs.
        api = _api()
        with pytest.raises(ProximoError):
            who_group_get(api, "mygroup")

    def test_rejects_slash_in_ogroup(self):
        api = _api()
        with pytest.raises(ProximoError):
            who_group_get(api, "2/3")

    def test_rejects_newline_in_ogroup(self):
        api = _api()
        with pytest.raises(ProximoError):
            who_group_get(api, "2\n")


class TestWhoGroupObjects:
    def test_uses_correct_path(self):
        # PMG 9.1 live-verified: ogroup must be numeric ID (e.g. '2'), not a name.
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path) or []
        )
        who_group_objects(api, "2")
        assert api.seen["path"] == "/config/ruledb/who/2/objects"

    def test_rejects_non_numeric_ogroup(self):
        api = _api()
        with pytest.raises(ProximoError):
            who_group_objects(api, "mygroup")

    def test_rejects_traversal(self):
        api = _api()
        with pytest.raises(ProximoError):
            who_group_objects(api, "../etc")


class TestWhatGroupsList:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path, method="GET") or []
        )
        what_groups_list(api)
        assert api.seen["path"] == "/config/ruledb/what"
        assert api.seen["method"] == "GET"


class TestWhatGroupGet:
    def test_uses_correct_path(self):
        # PMG 9.1 live-verified: ogroup must be numeric ID (e.g. '8'), not a name.
        api = _api()
        what_group_get(api, "8")
        assert api.seen["path"] == "/config/ruledb/what/8/config"

    def test_rejects_non_numeric_ogroup(self):
        api = _api()
        with pytest.raises(ProximoError):
            what_group_get(api, "mygroup")

    def test_rejects_slash(self):
        api = _api()
        with pytest.raises(ProximoError):
            what_group_get(api, "8/9")


class TestWhatGroupObjects:
    def test_uses_correct_path(self):
        # PMG 9.1 live-verified: ogroup must be numeric ID (e.g. '8'), not a name.
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path) or []
        )
        what_group_objects(api, "8")
        assert api.seen["path"] == "/config/ruledb/what/8/objects"

    def test_rejects_non_numeric_ogroup(self):
        api = _api()
        with pytest.raises(ProximoError):
            what_group_objects(api, "mygroup")

    def test_rejects_traversal(self):
        api = _api()
        with pytest.raises(ProximoError):
            what_group_objects(api, "../etc")


class TestWhenGroupsList:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path, method="GET") or []
        )
        when_groups_list(api)
        assert api.seen["path"] == "/config/ruledb/when"
        assert api.seen["method"] == "GET"


class TestWhenGroupGet:
    def test_uses_correct_path(self):
        # PMG 9.1 live-verified: ogroup must be numeric ID (e.g. '4'), not a name.
        api = _api()
        when_group_get(api, "4")
        assert api.seen["path"] == "/config/ruledb/when/4/config"

    def test_rejects_non_numeric_ogroup(self):
        api = _api()
        with pytest.raises(ProximoError):
            when_group_get(api, "mygroup")

    def test_rejects_slash(self):
        api = _api()
        with pytest.raises(ProximoError):
            when_group_get(api, "4/5")


class TestWhenGroupObjects:
    def test_uses_correct_path(self):
        # PMG 9.1 live-verified: ogroup must be numeric ID (e.g. '4'), not a name.
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path) or []
        )
        when_group_objects(api, "4")
        assert api.seen["path"] == "/config/ruledb/when/4/objects"

    def test_rejects_non_numeric_ogroup(self):
        api = _api()
        with pytest.raises(ProximoError):
            when_group_objects(api, "mygroup")

    def test_rejects_traversal(self):
        api = _api()
        with pytest.raises(ProximoError):
            when_group_objects(api, "../etc")


class TestActionObjectsList:
    def test_uses_correct_path(self):
        api = _api()
        api._get = lambda path, params=None: (
            api.seen.update(path=path, method="GET") or []
        )
        action_objects_list(api)
        assert api.seen["path"] == "/config/ruledb/action/objects"
        assert api.seen["method"] == "GET"

    def test_returns_list(self):
        api = _api()
        api._get = lambda path, params=None: []
        result = action_objects_list(api)
        assert isinstance(result, list)


class TestRuledbDigest:
    def test_uses_correct_path(self):
        api = _api()
        ruledb_digest(api)
        assert api.seen["path"] == "/config/ruledb/digest"
        assert api.seen["method"] == "GET"

    def test_no_params(self):
        api = _api()
        ruledb_digest(api)
        assert api.seen.get("params", {}) == {}


# ---------------------------------------------------------------------------
# W5b Validator
# ---------------------------------------------------------------------------

class TestCheckWhoObjectType:
    def test_accepts_all_valid_types(self):
        for t in ("email", "domain", "regex", "ip", "network", "ldap"):
            assert _check_who_object_type(t) == t

    def test_rejects_invalid_type(self):
        with pytest.raises(ProximoError):
            _check_who_object_type("spf")

    def test_rejects_empty_string(self):
        with pytest.raises(ProximoError):
            _check_who_object_type("")

    def test_rejects_name_with_slashes(self):
        with pytest.raises(ProximoError):
            _check_who_object_type("email/injection")


# ---------------------------------------------------------------------------
# W5b: WHO group CRUD ops
# ---------------------------------------------------------------------------

class TestWhoGroupCreate:
    def test_uses_correct_path_and_method(self):
        api = _api()
        who_group_create(api, "Blocklist")
        assert api.seen["path"] == "/config/ruledb/who"
        assert api.seen["method"] == "POST"

    def test_sends_name_in_body(self):
        api = _api()
        who_group_create(api, "Blocklist")
        assert api.seen["data"].get("name") == "Blocklist"

    def test_sends_optional_info(self):
        api = _api()
        who_group_create(api, "Blocklist", info="My blocklist")
        assert api.seen["data"].get("info") == "My blocklist"

    def test_sends_and_flag(self):
        api = _api()
        who_group_create(api, "Blocklist", and_=True)
        assert api.seen["data"].get("and") is True

    def test_sends_invert_flag(self):
        api = _api()
        who_group_create(api, "Blocklist", invert=True)
        assert api.seen["data"].get("invert") is True

    def test_omits_none_optionals(self):
        api = _api()
        who_group_create(api, "Blocklist")
        assert "info" not in api.seen["data"]
        assert "and" not in api.seen["data"]
        assert "invert" not in api.seen["data"]


class TestWhoGroupUpdate:
    def test_uses_correct_path_and_method(self):
        api = _api()
        who_group_update(api, "2", name="Renamed")
        assert api.seen["path"] == "/config/ruledb/who/2/config"
        assert api.seen["method"] == "PUT"

    def test_sends_name_in_body(self):
        api = _api()
        who_group_update(api, "2", name="Renamed")
        assert api.seen["data"].get("name") == "Renamed"

    def test_sends_and_flag(self):
        api = _api()
        who_group_update(api, "2", and_=False)
        assert api.seen["data"].get("and") is False

    def test_rejects_non_numeric_ogroup(self):
        api = _api()
        with pytest.raises(ProximoError):
            who_group_update(api, "mygroup", name="x")

    def test_omits_none_optionals(self):
        api = _api()
        who_group_update(api, "2")
        assert api.seen["data"] == {}


class TestWhoGroupDelete:
    def test_uses_correct_path_and_method(self):
        api = _api()
        who_group_delete(api, "2")
        assert api.seen["path"] == "/config/ruledb/who/2"
        assert api.seen["method"] == "DELETE"

    def test_rejects_non_numeric_ogroup(self):
        api = _api()
        with pytest.raises(ProximoError):
            who_group_delete(api, "mygroup")


# ---------------------------------------------------------------------------
# W5b: WHAT group CRUD ops
# ---------------------------------------------------------------------------

class TestWhatGroupCreate:
    def test_uses_correct_path_and_method(self):
        api = _api()
        what_group_create(api, "DangerousContent")
        assert api.seen["path"] == "/config/ruledb/what"
        assert api.seen["method"] == "POST"

    def test_sends_name_in_body(self):
        api = _api()
        what_group_create(api, "DangerousContent")
        assert api.seen["data"].get("name") == "DangerousContent"

    def test_omits_none_optionals(self):
        api = _api()
        what_group_create(api, "DangerousContent")
        assert "info" not in api.seen["data"]
        assert "and" not in api.seen["data"]
        assert "invert" not in api.seen["data"]


class TestWhatGroupUpdate:
    def test_uses_correct_path_and_method(self):
        api = _api()
        what_group_update(api, "8", name="Renamed")
        assert api.seen["path"] == "/config/ruledb/what/8/config"
        assert api.seen["method"] == "PUT"

    def test_rejects_non_numeric_ogroup(self):
        api = _api()
        with pytest.raises(ProximoError):
            what_group_update(api, "mygroup", name="x")

    def test_omits_none_optionals(self):
        api = _api()
        what_group_update(api, "8")
        assert api.seen["data"] == {}


class TestWhatGroupDelete:
    def test_uses_correct_path_and_method(self):
        api = _api()
        what_group_delete(api, "8")
        assert api.seen["path"] == "/config/ruledb/what/8"
        assert api.seen["method"] == "DELETE"

    def test_rejects_non_numeric_ogroup(self):
        api = _api()
        with pytest.raises(ProximoError):
            what_group_delete(api, "mygroup")


# ---------------------------------------------------------------------------
# W5b: WHEN group CRUD ops
# ---------------------------------------------------------------------------

class TestWhenGroupCreate:
    def test_uses_correct_path_and_method(self):
        api = _api()
        when_group_create(api, "OfficeHours")
        assert api.seen["path"] == "/config/ruledb/when"
        assert api.seen["method"] == "POST"

    def test_sends_name_in_body(self):
        api = _api()
        when_group_create(api, "OfficeHours")
        assert api.seen["data"].get("name") == "OfficeHours"

    def test_omits_none_optionals(self):
        api = _api()
        when_group_create(api, "OfficeHours")
        assert "info" not in api.seen["data"]
        assert "and" not in api.seen["data"]
        assert "invert" not in api.seen["data"]


class TestWhenGroupUpdate:
    def test_uses_correct_path_and_method(self):
        api = _api()
        when_group_update(api, "4", name="Renamed")
        assert api.seen["path"] == "/config/ruledb/when/4/config"
        assert api.seen["method"] == "PUT"

    def test_rejects_non_numeric_ogroup(self):
        api = _api()
        with pytest.raises(ProximoError):
            when_group_update(api, "mygroup", name="x")

    def test_omits_none_optionals(self):
        api = _api()
        when_group_update(api, "4")
        assert api.seen["data"] == {}


class TestWhenGroupDelete:
    def test_uses_correct_path_and_method(self):
        api = _api()
        when_group_delete(api, "4")
        assert api.seen["path"] == "/config/ruledb/when/4"
        assert api.seen["method"] == "DELETE"

    def test_rejects_non_numeric_ogroup(self):
        api = _api()
        with pytest.raises(ProximoError):
            when_group_delete(api, "mygroup")


# ---------------------------------------------------------------------------
# W5b: WHO object CRUD ops
# ---------------------------------------------------------------------------

class TestWhoObjectAdd:
    def test_email_uses_correct_path(self):
        api = _api()
        who_object_add(api, "2", "email", email="bad@evil.com")
        assert api.seen["path"] == "/config/ruledb/who/2/email"
        assert api.seen["method"] == "POST"

    def test_email_sends_email_field(self):
        api = _api()
        who_object_add(api, "2", "email", email="bad@evil.com")
        assert api.seen["data"].get("email") == "bad@evil.com"

    def test_domain_uses_correct_path(self):
        api = _api()
        who_object_add(api, "2", "domain", domain="evil.com")
        assert api.seen["path"] == "/config/ruledb/who/2/domain"

    def test_domain_sends_domain_field(self):
        api = _api()
        who_object_add(api, "2", "domain", domain="evil.com")
        assert api.seen["data"].get("domain") == "evil.com"

    def test_regex_uses_correct_path(self):
        api = _api()
        who_object_add(api, "2", "regex", regex=r".*@spam\.com")
        assert api.seen["path"] == "/config/ruledb/who/2/regex"

    def test_regex_sends_regex_field(self):
        api = _api()
        who_object_add(api, "2", "regex", regex=r".*@spam\.com")
        assert api.seen["data"].get("regex") == r".*@spam\.com"

    def test_ip_uses_correct_path(self):
        api = _api()
        who_object_add(api, "2", "ip", ip="1.2.3.4")
        assert api.seen["path"] == "/config/ruledb/who/2/ip"

    def test_ip_sends_ip_field(self):
        api = _api()
        who_object_add(api, "2", "ip", ip="1.2.3.4")
        assert api.seen["data"].get("ip") == "1.2.3.4"

    def test_network_uses_correct_path(self):
        api = _api()
        who_object_add(api, "2", "network", cidr="10.0.0.0/8")
        assert api.seen["path"] == "/config/ruledb/who/2/network"

    def test_network_sends_cidr_field(self):
        api = _api()
        who_object_add(api, "2", "network", cidr="10.0.0.0/8")
        assert api.seen["data"].get("cidr") == "10.0.0.0/8"

    def test_ldap_uses_correct_path(self):
        api = _api()
        who_object_add(api, "2", "ldap", mode="group", profile="corp", group="admins")
        assert api.seen["path"] == "/config/ruledb/who/2/ldap"

    def test_ldap_sends_ldap_fields(self):
        api = _api()
        who_object_add(api, "2", "ldap", mode="group", profile="corp", group="admins")
        assert api.seen["data"].get("mode") == "group"
        assert api.seen["data"].get("profile") == "corp"
        assert api.seen["data"].get("group") == "admins"

    def test_rejects_invalid_type(self):
        api = _api()
        with pytest.raises(ProximoError):
            who_object_add(api, "2", "spf", email="x@y.com")

    def test_rejects_non_numeric_ogroup(self):
        api = _api()
        with pytest.raises(ProximoError):
            who_object_add(api, "mygroup", "email", email="x@y.com")


class TestWhoObjectUpdate:
    def test_email_uses_correct_path(self):
        api = _api()
        who_object_update(api, "2", "email", "5", email="new@evil.com")
        assert api.seen["path"] == "/config/ruledb/who/2/email/5"
        assert api.seen["method"] == "PUT"

    def test_email_sends_email_field(self):
        api = _api()
        who_object_update(api, "2", "email", "5", email="new@evil.com")
        assert api.seen["data"].get("email") == "new@evil.com"

    def test_network_uses_correct_path(self):
        api = _api()
        who_object_update(api, "2", "network", "7", cidr="192.168.0.0/16")
        assert api.seen["path"] == "/config/ruledb/who/2/network/7"

    def test_rejects_invalid_type(self):
        api = _api()
        with pytest.raises(ProximoError):
            who_object_update(api, "2", "spf", "5", email="x@y.com")

    def test_rejects_non_numeric_ogroup(self):
        api = _api()
        with pytest.raises(ProximoError):
            who_object_update(api, "mygroup", "email", "5", email="x@y.com")

    def test_rejects_non_numeric_id(self):
        api = _api()
        with pytest.raises(ProximoError):
            who_object_update(api, "2", "email", "obj-abc", email="x@y.com")

    def test_empty_body_when_no_fields(self):
        api = _api()
        who_object_update(api, "2", "email", "5")
        assert api.seen["data"] == {}


class TestWhoObjectDelete:
    def test_uses_correct_path_and_method(self):
        api = _api()
        who_object_delete(api, "2", "5")
        assert api.seen["path"] == "/config/ruledb/who/2/objects/5"
        assert api.seen["method"] == "DELETE"

    def test_rejects_non_numeric_ogroup(self):
        api = _api()
        with pytest.raises(ProximoError):
            who_object_delete(api, "mygroup", "5")

    def test_rejects_non_numeric_id(self):
        api = _api()
        with pytest.raises(ProximoError):
            who_object_delete(api, "2", "abc")


# ---------------------------------------------------------------------------
# W5b: Plan functions
# ---------------------------------------------------------------------------

class TestPlanWhoGroupCreate:
    def test_risk_is_low(self):
        p = plan_who_group_create("Blocklist")
        assert p.risk == RISK_LOW

    def test_action_string(self):
        p = plan_who_group_create("Blocklist")
        assert p.action == "pmg_who_group_create"

    def test_change_mentions_name(self):
        p = plan_who_group_create("Blocklist")
        assert "Blocklist" in p.change

    def test_blast_radius_non_empty(self):
        p = plan_who_group_create("Blocklist")
        assert len(p.blast_radius) > 0

    def test_target_is_who_path(self):
        p = plan_who_group_create("Blocklist")
        assert "config/ruledb/who" in p.target


class TestPlanWhoGroupUpdate:
    def test_risk_is_medium(self):
        p = plan_who_group_update("2", name="Renamed")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_who_group_update("2")
        assert p.action == "pmg_who_group_update"

    def test_target_includes_ogroup(self):
        p = plan_who_group_update("2")
        assert "2" in p.target

    def test_blast_radius_non_empty(self):
        p = plan_who_group_update("2")
        assert len(p.blast_radius) > 0

    def test_rejects_non_numeric_ogroup(self):
        with pytest.raises(ProximoError):
            plan_who_group_update("mygroup")

    def test_blast_radius_discloses_new_name(self):
        p = plan_who_group_update("2", name="Renamed")
        assert any("Renamed" in entry for entry in p.blast_radius)

    def test_no_fields_noted_as_no_op(self):
        p = plan_who_group_update("2")
        assert any("no-op" in entry or "no fields" in entry for entry in p.blast_radius)


class TestPlanWhoGroupDelete:
    def test_risk_is_medium(self):
        p = plan_who_group_delete("2")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_who_group_delete("2")
        assert p.action == "pmg_who_group_delete"

    def test_target_includes_ogroup(self):
        p = plan_who_group_delete("2")
        assert "2" in p.target

    def test_blast_radius_non_empty(self):
        p = plan_who_group_delete("2")
        assert len(p.blast_radius) > 0

    def test_rejects_non_numeric_ogroup(self):
        with pytest.raises(ProximoError):
            plan_who_group_delete("mygroup")


class TestPlanWhatGroupCreate:
    def test_risk_is_low(self):
        p = plan_what_group_create("DangerousContent")
        assert p.risk == RISK_LOW

    def test_action_string(self):
        p = plan_what_group_create("DangerousContent")
        assert p.action == "pmg_what_group_create"

    def test_change_mentions_name(self):
        p = plan_what_group_create("DangerousContent")
        assert "DangerousContent" in p.change

    def test_blast_radius_non_empty(self):
        p = plan_what_group_create("DangerousContent")
        assert len(p.blast_radius) > 0


class TestPlanWhatGroupUpdate:
    def test_risk_is_medium(self):
        p = plan_what_group_update("8")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_what_group_update("8")
        assert p.action == "pmg_what_group_update"

    def test_rejects_non_numeric_ogroup(self):
        with pytest.raises(ProximoError):
            plan_what_group_update("mygroup")

    def test_blast_radius_discloses_new_name(self):
        p = plan_what_group_update("8", name="Renamed")
        assert any("Renamed" in entry for entry in p.blast_radius)


class TestPlanWhatGroupDelete:
    def test_risk_is_medium(self):
        p = plan_what_group_delete("8")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_what_group_delete("8")
        assert p.action == "pmg_what_group_delete"

    def test_rejects_non_numeric_ogroup(self):
        with pytest.raises(ProximoError):
            plan_what_group_delete("mygroup")


class TestPlanWhenGroupCreate:
    def test_risk_is_low(self):
        p = plan_when_group_create("OfficeHours")
        assert p.risk == RISK_LOW

    def test_action_string(self):
        p = plan_when_group_create("OfficeHours")
        assert p.action == "pmg_when_group_create"

    def test_change_mentions_name(self):
        p = plan_when_group_create("OfficeHours")
        assert "OfficeHours" in p.change

    def test_blast_radius_non_empty(self):
        p = plan_when_group_create("OfficeHours")
        assert len(p.blast_radius) > 0


class TestPlanWhenGroupUpdate:
    def test_risk_is_medium(self):
        p = plan_when_group_update("4")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_when_group_update("4")
        assert p.action == "pmg_when_group_update"

    def test_rejects_non_numeric_ogroup(self):
        with pytest.raises(ProximoError):
            plan_when_group_update("mygroup")

    def test_blast_radius_discloses_new_name(self):
        p = plan_when_group_update("4", name="Renamed")
        assert any("Renamed" in entry for entry in p.blast_radius)


class TestPlanWhenGroupDelete:
    def test_risk_is_medium(self):
        p = plan_when_group_delete("4")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_when_group_delete("4")
        assert p.action == "pmg_when_group_delete"

    def test_rejects_non_numeric_ogroup(self):
        with pytest.raises(ProximoError):
            plan_when_group_delete("mygroup")


class TestPlanWhoObjectAdd:
    def test_risk_is_low(self):
        p = plan_who_object_add("2", "email", email="x@y.com")
        assert p.risk == RISK_LOW

    def test_action_string(self):
        p = plan_who_object_add("2", "email")
        assert p.action == "pmg_who_object_add"

    def test_target_includes_type(self):
        p = plan_who_object_add("2", "email")
        assert "email" in p.target

    def test_target_includes_ogroup(self):
        p = plan_who_object_add("2", "email")
        assert "2" in p.target

    def test_blast_radius_non_empty(self):
        p = plan_who_object_add("2", "email")
        assert len(p.blast_radius) > 0

    def test_rejects_invalid_type(self):
        with pytest.raises(ProximoError):
            plan_who_object_add("2", "spf")

    def test_rejects_non_numeric_ogroup(self):
        with pytest.raises(ProximoError):
            plan_who_object_add("mygroup", "email")


class TestPlanWhoObjectUpdate:
    def test_risk_is_medium(self):
        p = plan_who_object_update("2", "email", "5")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_who_object_update("2", "email", "5")
        assert p.action == "pmg_who_object_update"

    def test_target_includes_type_and_id(self):
        p = plan_who_object_update("2", "email", "5")
        assert "email" in p.target
        assert "5" in p.target

    def test_blast_radius_non_empty(self):
        p = plan_who_object_update("2", "email", "5")
        assert len(p.blast_radius) > 0

    def test_rejects_invalid_type(self):
        with pytest.raises(ProximoError):
            plan_who_object_update("2", "spf", "5")

    def test_rejects_non_numeric_ogroup(self):
        with pytest.raises(ProximoError):
            plan_who_object_update("mygroup", "email", "5")

    def test_rejects_non_numeric_id(self):
        with pytest.raises(ProximoError):
            plan_who_object_update("2", "email", "obj-abc")

    def test_blast_radius_discloses_new_value(self):
        p = plan_who_object_update("2", "email", "5", email="attacker@evil.example")
        assert any("attacker@evil.example" in entry for entry in p.blast_radius)


class TestPlanWhoObjectDelete:
    def test_risk_is_medium(self):
        p = plan_who_object_delete("2", "5")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_who_object_delete("2", "5")
        assert p.action == "pmg_who_object_delete"

    def test_target_includes_ogroup_and_id(self):
        p = plan_who_object_delete("2", "5")
        assert "2" in p.target
        assert "5" in p.target

    def test_blast_radius_non_empty(self):
        p = plan_who_object_delete("2", "5")
        assert len(p.blast_radius) > 0

    def test_rejects_non_numeric_ogroup(self):
        with pytest.raises(ProximoError):
            plan_who_object_delete("mygroup", "5")

    def test_rejects_non_numeric_id(self):
        with pytest.raises(ProximoError):
            plan_who_object_delete("2", "abc")


# ---------------------------------------------------------------------------
# W5c: _check_what_object_type validator
# ---------------------------------------------------------------------------

class TestCheckWhatObjectType:
    def test_valid_types_pass(self):
        for t in ("contenttype", "matchfield", "spamfilter", "virusfilter",
                  "filenamefilter", "archivefilter", "archivefilenamefilter"):
            assert _check_what_object_type(t) == t

    def test_invalid_type_raises(self):
        with pytest.raises(ProximoError):
            _check_what_object_type("email")

    def test_empty_string_raises(self):
        with pytest.raises(ProximoError):
            _check_what_object_type("")

    def test_error_lists_valid_types(self):
        with pytest.raises(ProximoError, match="contenttype"):
            _check_what_object_type("bogus")


# ---------------------------------------------------------------------------
# W5c: _check_action_position validator
# ---------------------------------------------------------------------------

class TestCheckActionPosition:
    def test_start_passes(self):
        assert _check_action_position("start") == "start"

    def test_end_passes(self):
        assert _check_action_position("end") == "end"

    def test_invalid_raises(self):
        with pytest.raises(ProximoError):
            _check_action_position("middle")


# ---------------------------------------------------------------------------
# W5c: _check_action_object_id validator
# ---------------------------------------------------------------------------

class TestCheckActionObjectId:
    def test_valid_compound_id(self):
        assert _check_action_object_id("13_26") == "13_26"

    def test_leading_zeros_ok(self):
        assert _check_action_object_id("0_0") == "0_0"

    def test_plain_numeric_rejected(self):
        with pytest.raises(ProximoError):
            _check_action_object_id("26")

    def test_slash_rejected(self):
        with pytest.raises(ProximoError):
            _check_action_object_id("13/26")

    def test_empty_rejected(self):
        with pytest.raises(ProximoError):
            _check_action_object_id("")

    def test_letters_rejected(self):
        with pytest.raises(ProximoError):
            _check_action_object_id("abc_def")


# ---------------------------------------------------------------------------
# W5c: what_object_add op tests
# ---------------------------------------------------------------------------

class TestWhatObjectAdd:
    def test_contenttype_uses_correct_path(self):
        api = _api()
        what_object_add(api, "8", "contenttype", contenttype="text/plain")
        assert api.seen["path"] == "/config/ruledb/what/8/contenttype"
        assert api.seen["method"] == "POST"

    def test_contenttype_body_has_contenttype(self):
        api = _api()
        what_object_add(api, "8", "contenttype", contenttype="text/plain")
        assert api.seen["data"].get("contenttype") == "text/plain"

    def test_contenttype_only_content_hyphen_key(self):
        api = _api()
        what_object_add(api, "8", "contenttype", contenttype="text/html", only_content=True)
        assert api.seen["data"].get("only-content") is True

    def test_matchfield_uses_correct_path(self):
        api = _api()
        what_object_add(api, "8", "matchfield", field="Subject", value="spam")
        assert api.seen["path"] == "/config/ruledb/what/8/matchfield"

    def test_matchfield_body_has_field_and_value(self):
        api = _api()
        what_object_add(api, "8", "matchfield", field="Subject", value="spam")
        assert api.seen["data"].get("field") == "Subject"
        assert api.seen["data"].get("value") == "spam"

    def test_matchfield_top_part_only_hyphen_key(self):
        api = _api()
        what_object_add(api, "8", "matchfield", field="X", value="v", top_part_only=True)
        assert api.seen["data"].get("top-part-only") is True

    def test_spamfilter_uses_correct_path(self):
        api = _api()
        what_object_add(api, "8", "spamfilter", spamlevel=5)
        assert api.seen["path"] == "/config/ruledb/what/8/spamfilter"

    def test_spamfilter_body_has_spamlevel(self):
        api = _api()
        what_object_add(api, "8", "spamfilter", spamlevel=5)
        assert api.seen["data"].get("spamlevel") == 5

    def test_virusfilter_uses_correct_path(self):
        api = _api()
        what_object_add(api, "8", "virusfilter")
        assert api.seen["path"] == "/config/ruledb/what/8/virusfilter"

    def test_virusfilter_sends_empty_body(self):
        api = _api()
        what_object_add(api, "8", "virusfilter")
        assert api.seen["data"] == {}

    def test_filenamefilter_uses_correct_path(self):
        api = _api()
        what_object_add(api, "8", "filenamefilter", filename="*.exe")
        assert api.seen["path"] == "/config/ruledb/what/8/filenamefilter"

    def test_filenamefilter_body_has_filename(self):
        api = _api()
        what_object_add(api, "8", "filenamefilter", filename="*.exe")
        assert api.seen["data"].get("filename") == "*.exe"

    def test_archivefilter_uses_correct_path(self):
        api = _api()
        what_object_add(api, "8", "archivefilter", contenttype="application/zip")
        assert api.seen["path"] == "/config/ruledb/what/8/archivefilter"

    def test_archivefilter_body_has_contenttype(self):
        api = _api()
        what_object_add(api, "8", "archivefilter", contenttype="application/zip")
        assert api.seen["data"].get("contenttype") == "application/zip"

    def test_archivefilter_only_content_hyphen_key(self):
        api = _api()
        what_object_add(api, "8", "archivefilter", contenttype="application/zip",
                        only_content=False)
        assert "only-content" in api.seen["data"]

    def test_archivefilenamefilter_uses_correct_path(self):
        api = _api()
        what_object_add(api, "8", "archivefilenamefilter", filename="*.bat")
        assert api.seen["path"] == "/config/ruledb/what/8/archivefilenamefilter"

    def test_archivefilenamefilter_body_has_filename(self):
        api = _api()
        what_object_add(api, "8", "archivefilenamefilter", filename="*.bat")
        assert api.seen["data"].get("filename") == "*.bat"

    def test_invalid_type_raises(self):
        api = _api()
        with pytest.raises(ProximoError):
            what_object_add(api, "8", "email")

    def test_rejects_non_numeric_ogroup(self):
        api = _api()
        with pytest.raises(ProximoError):
            what_object_add(api, "mygroup", "virusfilter")


# ---------------------------------------------------------------------------
# W5c: what_object_update op tests
# ---------------------------------------------------------------------------

class TestWhatObjectUpdate:
    def test_contenttype_uses_correct_path(self):
        api = _api()
        what_object_update(api, "8", "contenttype", "5", contenttype="text/plain")
        assert api.seen["path"] == "/config/ruledb/what/8/contenttype/5"
        assert api.seen["method"] == "PUT"

    def test_matchfield_uses_correct_path(self):
        api = _api()
        what_object_update(api, "8", "matchfield", "3", field="From", value="spammer")
        assert api.seen["path"] == "/config/ruledb/what/8/matchfield/3"

    def test_only_none_fields_not_sent(self):
        api = _api()
        what_object_update(api, "8", "matchfield", "3", field="From")
        assert "value" not in api.seen["data"]

    def test_top_part_only_hyphen_key_on_update(self):
        api = _api()
        what_object_update(api, "8", "matchfield", "3", top_part_only=True)
        assert api.seen["data"].get("top-part-only") is True

    def test_rejects_non_numeric_id(self):
        api = _api()
        with pytest.raises(ProximoError):
            what_object_update(api, "8", "contenttype", "abc")

    def test_invalid_type_raises(self):
        api = _api()
        with pytest.raises(ProximoError):
            what_object_update(api, "8", "bogustype", "5")


# ---------------------------------------------------------------------------
# W5c: what_object_delete op tests
# ---------------------------------------------------------------------------

class TestWhatObjectDelete:
    def test_uses_objects_sub_path(self):
        api = _api()
        what_object_delete(api, "8", "5")
        assert api.seen["path"] == "/config/ruledb/what/8/objects/5"
        assert api.seen["method"] == "DELETE"

    def test_rejects_non_numeric_ogroup(self):
        api = _api()
        with pytest.raises(ProximoError):
            what_object_delete(api, "mygroup", "5")

    def test_rejects_non_numeric_id(self):
        api = _api()
        with pytest.raises(ProximoError):
            what_object_delete(api, "8", "abc")


# ---------------------------------------------------------------------------
# W5c: when_object_add op tests
# ---------------------------------------------------------------------------

class TestWhenObjectAdd:
    def test_uses_correct_path(self):
        api = _api()
        when_object_add(api, "4", start="08:00", end="17:00")
        assert api.seen["path"] == "/config/ruledb/when/4/timeframe"
        assert api.seen["method"] == "POST"

    def test_body_has_start_and_end(self):
        api = _api()
        when_object_add(api, "4", start="08:00", end="17:00")
        assert api.seen["data"].get("start") == "08:00"
        assert api.seen["data"].get("end") == "17:00"

    def test_rejects_non_numeric_ogroup(self):
        api = _api()
        with pytest.raises(ProximoError):
            when_object_add(api, "mygroup", start="08:00", end="17:00")


# ---------------------------------------------------------------------------
# W5c: when_object_update op tests
# ---------------------------------------------------------------------------

class TestWhenObjectUpdate:
    def test_uses_correct_path(self):
        api = _api()
        when_object_update(api, "4", "7", start="09:00", end="17:00")
        assert api.seen["path"] == "/config/ruledb/when/4/timeframe/7"
        assert api.seen["method"] == "PUT"

    def test_both_start_and_end_in_body(self):
        # PMG 9.1 timeframe PUT requires both start and end;
        # a partial body (start only) returns 400 — live-proven 2026-06-26.
        api = _api()
        when_object_update(api, "4", "7", start="09:00", end="17:00")
        assert api.seen["data"].get("start") == "09:00"
        assert api.seen["data"].get("end") == "17:00"

    def test_rejects_non_numeric_id(self):
        api = _api()
        with pytest.raises(ProximoError):
            when_object_update(api, "4", "abc", start="09:00", end="17:00")


# ---------------------------------------------------------------------------
# W5c: when_object_delete op tests
# ---------------------------------------------------------------------------

class TestWhenObjectDelete:
    def test_uses_objects_sub_path(self):
        api = _api()
        when_object_delete(api, "4", "7")
        assert api.seen["path"] == "/config/ruledb/when/4/objects/7"
        assert api.seen["method"] == "DELETE"

    def test_rejects_non_numeric_ogroup(self):
        api = _api()
        with pytest.raises(ProximoError):
            when_object_delete(api, "mygroup", "7")


# ---------------------------------------------------------------------------
# W5c: action_bcc_create op tests
# ---------------------------------------------------------------------------

class TestActionBccCreate:
    def test_uses_correct_path(self):
        api = _api()
        action_bcc_create(api, name="copy-admin", target="admin@example.com")
        assert api.seen["path"] == "/config/ruledb/action/bcc"
        assert api.seen["method"] == "POST"

    def test_body_has_required_fields(self):
        api = _api()
        action_bcc_create(api, name="copy-admin", target="admin@example.com")
        assert api.seen["data"].get("name") == "copy-admin"
        assert api.seen["data"].get("target") == "admin@example.com"

    def test_optional_original_sent_when_provided(self):
        api = _api()
        action_bcc_create(api, name="n", target="t@t.com", original=True)
        assert api.seen["data"].get("original") is True

    def test_optional_info_sent_when_provided(self):
        api = _api()
        action_bcc_create(api, name="n", target="t@t.com", info="desc")
        assert api.seen["data"].get("info") == "desc"


# ---------------------------------------------------------------------------
# W5c: action_bcc_update op tests
# ---------------------------------------------------------------------------

class TestActionBccUpdate:
    def test_uses_correct_path(self):
        api = _api()
        action_bcc_update(api, "13_26", target="new@example.com")
        assert api.seen["path"] == "/config/ruledb/action/bcc/13_26"
        assert api.seen["method"] == "PUT"

    def test_only_non_none_sent(self):
        api = _api()
        action_bcc_update(api, "13_26", target="new@example.com")
        assert "name" not in api.seen["data"]

    def test_rejects_non_compound_id(self):
        api = _api()
        with pytest.raises(ProximoError):
            action_bcc_update(api, "26", target="x@x.com")


# ---------------------------------------------------------------------------
# W5c: action_field_create op tests
# ---------------------------------------------------------------------------

class TestActionFieldCreate:
    def test_uses_correct_path(self):
        api = _api()
        action_field_create(api, name="add-tag", field="X-Spam", value="yes")
        assert api.seen["path"] == "/config/ruledb/action/field"
        assert api.seen["method"] == "POST"

    def test_body_has_required_fields(self):
        api = _api()
        action_field_create(api, name="add-tag", field="X-Spam", value="yes")
        assert api.seen["data"].get("name") == "add-tag"
        assert api.seen["data"].get("field") == "X-Spam"
        assert api.seen["data"].get("value") == "yes"


# ---------------------------------------------------------------------------
# W5c: action_field_update op tests
# ---------------------------------------------------------------------------

class TestActionFieldUpdate:
    def test_uses_correct_path(self):
        api = _api()
        action_field_update(api, "5_10", name="tag", field="X-Spam", value="no")
        assert api.seen["path"] == "/config/ruledb/action/field/5_10"
        assert api.seen["method"] == "PUT"

    def test_required_fields_all_in_body(self):
        # PMG 9.1 field action PUT requires name+field+value;
        # a partial body (value only) returns 400 — live-proven 2026-06-26.
        api = _api()
        action_field_update(api, "5_10", name="tag", field="X-Spam", value="no")
        assert api.seen["data"].get("name") == "tag"
        assert api.seen["data"].get("field") == "X-Spam"
        assert api.seen["data"].get("value") == "no"

    def test_rejects_non_compound_id(self):
        api = _api()
        with pytest.raises(ProximoError):
            action_field_update(api, "10", name="tag", field="X-Spam", value="no")


# ---------------------------------------------------------------------------
# W5c: action_notification_create op tests
# ---------------------------------------------------------------------------

class TestActionNotificationCreate:
    def test_uses_correct_path(self):
        api = _api()
        action_notification_create(api, name="notify-admin", to="admin@example.com",
                                   subject="Alert", body_text="Mail matched.")
        assert api.seen["path"] == "/config/ruledb/action/notification"
        assert api.seen["method"] == "POST"

    def test_body_has_required_fields(self):
        api = _api()
        action_notification_create(api, name="notify-admin", to="admin@example.com",
                                   subject="Alert", body_text="Mail matched.")
        assert api.seen["data"].get("name") == "notify-admin"
        assert api.seen["data"].get("to") == "admin@example.com"
        assert api.seen["data"].get("subject") == "Alert"
        assert api.seen["data"].get("body") == "Mail matched."

    def test_body_text_maps_to_body_key(self):
        api = _api()
        action_notification_create(api, name="n", to="t@t.com",
                                   subject="s", body_text="content")
        assert "body_text" not in api.seen["data"]
        assert api.seen["data"].get("body") == "content"

    def test_attach_sent_when_provided(self):
        api = _api()
        action_notification_create(api, name="n", to="t@t.com",
                                   subject="s", body_text="b", attach=True)
        assert api.seen["data"].get("attach") is True


# ---------------------------------------------------------------------------
# W5c: action_notification_update op tests
# ---------------------------------------------------------------------------

class TestActionNotificationUpdate:
    def test_uses_correct_path(self):
        api = _api()
        action_notification_update(
            api, "7_14", name="n", to="a@a.com", subject="New subject", body_text="b"
        )
        assert api.seen["path"] == "/config/ruledb/action/notification/7_14"
        assert api.seen["method"] == "PUT"

    def test_body_text_maps_to_body_key_on_update(self):
        # PMG 9.1 notification PUT requires name+to+subject+body_text;
        # a partial body (subject only) returns 400 — live-proven 2026-06-26.
        # body_text maps to API param 'body'.
        api = _api()
        action_notification_update(
            api, "7_14", name="n", to="a@a.com", subject="s", body_text="updated"
        )
        assert api.seen["data"].get("body") == "updated"
        assert "body_text" not in api.seen["data"]

    def test_rejects_non_compound_id(self):
        api = _api()
        with pytest.raises(ProximoError):
            action_notification_update(
                api, "14", name="n", to="a@a.com", subject="x", body_text="b"
            )


# ---------------------------------------------------------------------------
# W5c: action_disclaimer_create op tests
# ---------------------------------------------------------------------------

class TestActionDisclaimerCreate:
    def test_uses_correct_path(self):
        api = _api()
        action_disclaimer_create(api, name="footer", disclaimer="Confidential")
        assert api.seen["path"] == "/config/ruledb/action/disclaimer"
        assert api.seen["method"] == "POST"

    def test_body_has_required_fields(self):
        api = _api()
        action_disclaimer_create(api, name="footer", disclaimer="Confidential")
        assert api.seen["data"].get("name") == "footer"
        assert api.seen["data"].get("disclaimer") == "Confidential"

    def test_add_separator_hyphen_key(self):
        api = _api()
        action_disclaimer_create(api, name="footer", disclaimer="text",
                                 add_separator=True)
        assert api.seen["data"].get("add-separator") is True
        assert "add_separator" not in api.seen["data"]

    def test_position_validated(self):
        api = _api()
        with pytest.raises(ProximoError):
            action_disclaimer_create(api, name="footer", disclaimer="text",
                                     position="middle")

    def test_position_start_accepted(self):
        api = _api()
        action_disclaimer_create(api, name="footer", disclaimer="text", position="start")
        assert api.seen["data"].get("position") == "start"


# ---------------------------------------------------------------------------
# W5c: action_disclaimer_update op tests
# ---------------------------------------------------------------------------

class TestActionDisclaimerUpdate:
    def test_uses_correct_path(self):
        api = _api()
        action_disclaimer_update(api, "2_9", disclaimer="New text")
        assert api.seen["path"] == "/config/ruledb/action/disclaimer/2_9"
        assert api.seen["method"] == "PUT"

    def test_add_separator_hyphen_key_on_update(self):
        api = _api()
        action_disclaimer_update(api, "2_9", add_separator=False)
        assert "add-separator" in api.seen["data"]
        assert "add_separator" not in api.seen["data"]

    def test_rejects_non_compound_id(self):
        api = _api()
        with pytest.raises(ProximoError):
            action_disclaimer_update(api, "9", disclaimer="x")


# ---------------------------------------------------------------------------
# W5c: action_removeattachments_create op tests
# ---------------------------------------------------------------------------

class TestActionRemoveattachmentsCreate:
    def test_uses_correct_path(self):
        api = _api()
        action_removeattachments_create(api, name="strip-attach", text="[removed]")
        assert api.seen["path"] == "/config/ruledb/action/removeattachments"
        assert api.seen["method"] == "POST"

    def test_body_has_required_fields(self):
        api = _api()
        action_removeattachments_create(api, name="strip-attach", text="[removed]")
        assert api.seen["data"].get("name") == "strip-attach"
        assert api.seen["data"].get("text") == "[removed]"

    def test_all_maps_to_all_key_not_all_underscore(self):
        api = _api()
        action_removeattachments_create(api, name="n", text="t", all_=True)
        assert api.seen["data"].get("all") is True
        assert "all_" not in api.seen["data"]

    def test_quarantine_sent_when_provided(self):
        api = _api()
        action_removeattachments_create(api, name="n", text="t", quarantine=True)
        assert api.seen["data"].get("quarantine") is True


# ---------------------------------------------------------------------------
# W5c: action_removeattachments_update op tests
# ---------------------------------------------------------------------------

class TestActionRemoveattachmentsUpdate:
    def test_uses_correct_path(self):
        api = _api()
        action_removeattachments_update(api, "3_5", text="[stripped]")
        assert api.seen["path"] == "/config/ruledb/action/removeattachments/3_5"
        assert api.seen["method"] == "PUT"

    def test_all_maps_to_all_key_on_update(self):
        api = _api()
        action_removeattachments_update(api, "3_5", all_=False)
        assert "all" in api.seen["data"]
        assert "all_" not in api.seen["data"]

    def test_rejects_non_compound_id(self):
        api = _api()
        with pytest.raises(ProximoError):
            action_removeattachments_update(api, "5", text="x")


# ---------------------------------------------------------------------------
# W5c: action_delete op tests
# ---------------------------------------------------------------------------

class TestActionDelete:
    def test_uses_objects_sub_path(self):
        api = _api()
        action_delete(api, "13_26")
        assert api.seen["path"] == "/config/ruledb/action/objects/13_26"
        assert api.seen["method"] == "DELETE"

    def test_rejects_plain_numeric_id(self):
        api = _api()
        with pytest.raises(ProximoError):
            action_delete(api, "26")

    def test_rejects_slash_in_id(self):
        api = _api()
        with pytest.raises(ProximoError):
            action_delete(api, "13/26")


# ---------------------------------------------------------------------------
# W5c: plan_what_object_* tests
# ---------------------------------------------------------------------------

class TestPlanWhatObjectAdd:
    def test_risk_is_low(self):
        p = plan_what_object_add("8", "filenamefilter")
        assert p.risk == RISK_LOW

    def test_action_string(self):
        p = plan_what_object_add("8", "virusfilter")
        assert p.action == "pmg_what_object_add"

    def test_target_includes_ogroup_and_type(self):
        p = plan_what_object_add("8", "spamfilter")
        assert "8" in p.target
        assert "spamfilter" in p.target

    def test_blast_radius_non_empty(self):
        p = plan_what_object_add("8", "virusfilter")
        assert len(p.blast_radius) > 0

    def test_rejects_non_numeric_ogroup(self):
        with pytest.raises(ProximoError):
            plan_what_object_add("mygroup", "virusfilter")

    def test_rejects_invalid_type(self):
        with pytest.raises(ProximoError):
            plan_what_object_add("8", "bogus")


class TestPlanWhatObjectUpdate:
    def test_risk_is_medium(self):
        p = plan_what_object_update("8", "contenttype", "5")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_what_object_update("8", "matchfield", "3")
        assert p.action == "pmg_what_object_update"

    def test_target_includes_ogroup_type_and_id(self):
        p = plan_what_object_update("8", "spamfilter", "3")
        assert "8" in p.target
        assert "spamfilter" in p.target
        assert "3" in p.target

    def test_rejects_non_numeric_id(self):
        with pytest.raises(ProximoError):
            plan_what_object_update("8", "contenttype", "abc")

    def test_blast_radius_discloses_new_value(self):
        p = plan_what_object_update("8", "matchfield", "3", field="Subject", value="malicious")
        assert any("malicious" in entry for entry in p.blast_radius)


class TestPlanWhatObjectDelete:
    def test_risk_is_medium(self):
        p = plan_what_object_delete("8", "5")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_what_object_delete("8", "5")
        assert p.action == "pmg_what_object_delete"

    def test_target_includes_ogroup_and_id(self):
        p = plan_what_object_delete("8", "5")
        assert "8" in p.target
        assert "5" in p.target

    def test_blast_radius_non_empty(self):
        p = plan_what_object_delete("8", "5")
        assert len(p.blast_radius) > 0


# ---------------------------------------------------------------------------
# W5c: plan_when_object_* tests
# ---------------------------------------------------------------------------

class TestPlanWhenObjectAdd:
    def test_risk_is_low(self):
        p = plan_when_object_add("4", start="08:00", end="17:00")
        assert p.risk == RISK_LOW

    def test_action_string(self):
        p = plan_when_object_add("4", start="08:00", end="17:00")
        assert p.action == "pmg_when_object_add"

    def test_target_includes_ogroup(self):
        p = plan_when_object_add("4", start="08:00", end="17:00")
        assert "4" in p.target

    def test_blast_radius_non_empty(self):
        p = plan_when_object_add("4", start="08:00", end="17:00")
        assert len(p.blast_radius) > 0

    def test_rejects_non_numeric_ogroup(self):
        with pytest.raises(ProximoError):
            plan_when_object_add("mygroup", start="08:00", end="17:00")


class TestPlanWhenObjectUpdate:
    def test_risk_is_medium(self):
        p = plan_when_object_update("4", "7")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_when_object_update("4", "7")
        assert p.action == "pmg_when_object_update"

    def test_target_includes_ogroup_and_id(self):
        p = plan_when_object_update("4", "7")
        assert "4" in p.target
        assert "7" in p.target

    def test_rejects_non_numeric_id(self):
        with pytest.raises(ProximoError):
            plan_when_object_update("4", "abc")

    def test_blast_radius_discloses_new_value(self):
        p = plan_when_object_update("4", "7", start="03:00", end="04:00")
        assert any("03:00" in entry for entry in p.blast_radius)


class TestPlanWhenObjectDelete:
    def test_risk_is_medium(self):
        p = plan_when_object_delete("4", "7")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_when_object_delete("4", "7")
        assert p.action == "pmg_when_object_delete"

    def test_target_includes_ogroup_and_id(self):
        p = plan_when_object_delete("4", "7")
        assert "4" in p.target
        assert "7" in p.target

    def test_blast_radius_non_empty(self):
        p = plan_when_object_delete("4", "7")
        assert len(p.blast_radius) > 0


# ---------------------------------------------------------------------------
# W5c: plan_action_* tests
# ---------------------------------------------------------------------------

class TestPlanActionBccCreate:
    def test_risk_is_low(self):
        p = plan_action_bcc_create("copy-admin", "admin@example.com")
        assert p.risk == RISK_LOW

    def test_action_string(self):
        p = plan_action_bcc_create("n", "t@t.com")
        assert p.action == "pmg_action_bcc_create"

    def test_blast_radius_non_empty(self):
        p = plan_action_bcc_create("n", "t@t.com")
        assert len(p.blast_radius) > 0


class TestPlanActionBccUpdate:
    def test_risk_is_medium(self):
        p = plan_action_bcc_update("13_26")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_action_bcc_update("13_26")
        assert p.action == "pmg_action_bcc_update"

    def test_target_includes_id(self):
        p = plan_action_bcc_update("13_26")
        assert "13_26" in p.target

    def test_rejects_non_compound_id(self):
        with pytest.raises(ProximoError):
            plan_action_bcc_update("26")

    def test_blast_radius_discloses_new_target(self):
        p = plan_action_bcc_update("13_26", target="attacker@evil.example")
        assert any("attacker@evil.example" in entry for entry in p.blast_radius)


class TestPlanActionFieldCreate:
    def test_risk_is_low(self):
        p = plan_action_field_create("tag", "X-Spam", "yes")
        assert p.risk == RISK_LOW

    def test_action_string(self):
        p = plan_action_field_create("tag", "X-Spam", "yes")
        assert p.action == "pmg_action_field_create"


class TestPlanActionFieldUpdate:
    def test_risk_is_medium(self):
        p = plan_action_field_update("5_10")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_action_field_update("5_10")
        assert p.action == "pmg_action_field_update"

    def test_blast_radius_discloses_new_value(self):
        p = plan_action_field_update("5_10", name="tag", field="X-Spam", value="evil-payload")
        assert any("evil-payload" in entry for entry in p.blast_radius)

    def test_rejects_non_compound_id(self):
        with pytest.raises(ProximoError):
            plan_action_field_update("10")


class TestPlanActionNotificationCreate:
    def test_risk_is_low(self):
        p = plan_action_notification_create("n", "t@t.com")
        assert p.risk == RISK_LOW

    def test_action_string(self):
        p = plan_action_notification_create("n", "t@t.com")
        assert p.action == "pmg_action_notification_create"


class TestPlanActionNotificationUpdate:
    def test_risk_is_medium(self):
        p = plan_action_notification_update("7_14")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_action_notification_update("7_14")
        assert p.action == "pmg_action_notification_update"

    def test_blast_radius_discloses_new_value(self):
        p = plan_action_notification_update("7_14", to="attacker@evil.example")
        assert any("attacker@evil.example" in entry for entry in p.blast_radius)

    def test_rejects_non_compound_id(self):
        with pytest.raises(ProximoError):
            plan_action_notification_update("14")


class TestPlanActionDisclaimerCreate:
    def test_risk_is_low(self):
        p = plan_action_disclaimer_create("footer")
        assert p.risk == RISK_LOW

    def test_action_string(self):
        p = plan_action_disclaimer_create("footer")
        assert p.action == "pmg_action_disclaimer_create"


class TestPlanActionDisclaimerUpdate:
    def test_risk_is_medium(self):
        p = plan_action_disclaimer_update("2_9")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_action_disclaimer_update("2_9")
        assert p.action == "pmg_action_disclaimer_update"

    def test_blast_radius_discloses_new_value(self):
        p = plan_action_disclaimer_update("2_9", disclaimer="malicious text")
        assert any("malicious text" in entry for entry in p.blast_radius)

    def test_rejects_non_compound_id(self):
        with pytest.raises(ProximoError):
            plan_action_disclaimer_update("9")


class TestPlanActionRemoveattachmentsCreate:
    def test_risk_is_low(self):
        p = plan_action_removeattachments_create("strip")
        assert p.risk == RISK_LOW

    def test_action_string(self):
        p = plan_action_removeattachments_create("strip")
        assert p.action == "pmg_action_removeattachments_create"


class TestPlanActionRemoveattachmentsUpdate:
    def test_risk_is_medium(self):
        p = plan_action_removeattachments_update("3_5")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_action_removeattachments_update("3_5")
        assert p.action == "pmg_action_removeattachments_update"

    def test_blast_radius_discloses_new_value(self):
        p = plan_action_removeattachments_update("3_5", text="stripped-notice")
        assert any("stripped-notice" in entry for entry in p.blast_radius)

    def test_rejects_non_compound_id(self):
        with pytest.raises(ProximoError):
            plan_action_removeattachments_update("5")


class TestPlanActionDelete:
    def test_risk_is_medium(self):
        p = plan_action_delete("13_26")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_action_delete("13_26")
        assert p.action == "pmg_action_delete"

    def test_target_includes_id(self):
        p = plan_action_delete("13_26")
        assert "13_26" in p.target

    def test_blast_radius_non_empty(self):
        p = plan_action_delete("13_26")
        assert len(p.blast_radius) > 0

    def test_rejects_non_compound_id(self):
        with pytest.raises(ProximoError):
            plan_action_delete("26")


# ---------------------------------------------------------------------------
# W5d Validators
# ---------------------------------------------------------------------------


class TestCheckDirection:
    def test_accepts_zero(self):
        assert _check_direction(0) == 0

    def test_accepts_one(self):
        assert _check_direction(1) == 1

    def test_accepts_two(self):
        assert _check_direction(2) == 2

    def test_rejects_three(self):
        with pytest.raises(ProximoError):
            _check_direction(3)

    def test_rejects_negative(self):
        with pytest.raises(ProximoError):
            _check_direction(-1)

    def test_rejects_non_int(self):
        with pytest.raises(ProximoError):
            _check_direction("both")


class TestCheckPriority:
    def test_accepts_zero(self):
        assert _check_priority(0) == 0

    def test_accepts_hundred(self):
        assert _check_priority(100) == 100

    def test_accepts_fifty(self):
        assert _check_priority(50) == 50

    def test_rejects_negative(self):
        with pytest.raises(ProximoError):
            _check_priority(-1)

    def test_rejects_over_hundred(self):
        with pytest.raises(ProximoError):
            _check_priority(101)

    def test_rejects_non_int(self):
        with pytest.raises(ProximoError):
            _check_priority("high")


# ---------------------------------------------------------------------------
# W5d: ruledb_rule_create op tests
# ---------------------------------------------------------------------------


class TestRuledbRuleCreate:
    def test_uses_correct_path(self):
        api = _api()
        ruledb_rule_create(api, "my-rule", 50)
        assert api.seen["path"] == "/config/ruledb/rules"
        assert api.seen["method"] == "POST"

    def test_body_has_required_fields(self):
        api = _api()
        ruledb_rule_create(api, "my-rule", 50)
        assert api.seen["data"].get("name") == "my-rule"
        assert api.seen["data"].get("priority") == 50

    def test_active_defaults_false(self):
        api = _api()
        ruledb_rule_create(api, "my-rule", 50)
        assert api.seen["data"].get("active") is False

    def test_active_can_be_set_true(self):
        api = _api()
        ruledb_rule_create(api, "my-rule", 50, active=True)
        assert api.seen["data"].get("active") is True

    def test_hyphen_params_sent_with_hyphen_keys(self):
        api = _api()
        ruledb_rule_create(api, "r", 10, from_and=True, from_invert=False,
                           to_and=True, to_invert=False,
                           what_and=True, what_invert=False,
                           when_and=True, when_invert=False)
        assert api.seen["data"].get("from-and") is True
        assert api.seen["data"].get("from-invert") is False
        assert api.seen["data"].get("to-and") is True
        assert api.seen["data"].get("what-and") is True
        assert api.seen["data"].get("when-and") is True
        # underscore form must NOT appear in the API body
        assert "from_and" not in api.seen["data"]

    def test_direction_sent_when_provided(self):
        api = _api()
        ruledb_rule_create(api, "r", 10, direction=2)
        assert api.seen["data"].get("direction") == 2

    def test_rejects_invalid_priority(self):
        api = _api()
        with pytest.raises(ProximoError):
            ruledb_rule_create(api, "r", 200)

    def test_rejects_invalid_direction(self):
        api = _api()
        with pytest.raises(ProximoError):
            ruledb_rule_create(api, "r", 10, direction=5)


# ---------------------------------------------------------------------------
# W5d: ruledb_rule_update op tests
# ---------------------------------------------------------------------------


class TestRuledbRuleUpdate:
    def test_uses_correct_path(self):
        api = _api()
        ruledb_rule_update(api, "100", name="renamed")
        assert api.seen["path"] == "/config/ruledb/rules/100/config"
        assert api.seen["method"] == "PUT"

    def test_only_non_none_fields_sent(self):
        api = _api()
        ruledb_rule_update(api, "100", name="renamed")
        assert "priority" not in api.seen["data"]
        assert "active" not in api.seen["data"]

    def test_hyphen_params_sent_with_hyphen_keys(self):
        api = _api()
        ruledb_rule_update(api, "100", from_and=True, what_invert=True)
        assert api.seen["data"].get("from-and") is True
        assert api.seen["data"].get("what-invert") is True
        assert "from_and" not in api.seen["data"]

    def test_rejects_invalid_rule_id(self):
        api = _api()
        with pytest.raises(ProximoError):
            ruledb_rule_update(api, "abc", name="x")

    def test_rejects_invalid_priority(self):
        api = _api()
        with pytest.raises(ProximoError):
            ruledb_rule_update(api, "100", priority=999)


# ---------------------------------------------------------------------------
# W5d: ruledb_rule_delete op tests
# ---------------------------------------------------------------------------


class TestRuledbRuleDelete:
    def test_uses_correct_path(self):
        api = _api()
        ruledb_rule_delete(api, "100")
        assert api.seen["path"] == "/config/ruledb/rules/100"
        assert api.seen["method"] == "DELETE"

    def test_rejects_invalid_id(self):
        api = _api()
        with pytest.raises(ProximoError):
            ruledb_rule_delete(api, "abc")


# ---------------------------------------------------------------------------
# W5d: attach op tests (5 attach verbs)
# ---------------------------------------------------------------------------


class TestRuledbRuleFromAttach:
    def test_uses_correct_path(self):
        api = _api()
        ruledb_rule_from_attach(api, "100", "2")
        assert api.seen["path"] == "/config/ruledb/rules/100/from"
        assert api.seen["method"] == "POST"

    def test_ogroup_in_body(self):
        api = _api()
        ruledb_rule_from_attach(api, "100", "2")
        assert api.seen["data"].get("ogroup") == "2"


class TestRuledbRuleToAttach:
    def test_uses_correct_path(self):
        api = _api()
        ruledb_rule_to_attach(api, "100", "3")
        assert api.seen["path"] == "/config/ruledb/rules/100/to"
        assert api.seen["method"] == "POST"

    def test_ogroup_in_body(self):
        api = _api()
        ruledb_rule_to_attach(api, "100", "3")
        assert api.seen["data"].get("ogroup") == "3"


class TestRuledbRuleWhatAttach:
    def test_uses_correct_path(self):
        api = _api()
        ruledb_rule_what_attach(api, "100", "8")
        assert api.seen["path"] == "/config/ruledb/rules/100/what"
        assert api.seen["method"] == "POST"

    def test_ogroup_in_body(self):
        api = _api()
        ruledb_rule_what_attach(api, "100", "8")
        assert api.seen["data"].get("ogroup") == "8"


class TestRuledbRuleWhenAttach:
    def test_uses_correct_path(self):
        api = _api()
        ruledb_rule_when_attach(api, "100", "4")
        assert api.seen["path"] == "/config/ruledb/rules/100/when"
        assert api.seen["method"] == "POST"

    def test_ogroup_in_body(self):
        api = _api()
        ruledb_rule_when_attach(api, "100", "4")
        assert api.seen["data"].get("ogroup") == "4"


class TestRuledbRuleActionAttach:
    def test_uses_correct_path(self):
        api = _api()
        ruledb_rule_action_attach(api, "100", "13")
        # PMG 9.1 live-verified: singular /action (not /actions — that path returns 501)
        assert api.seen["path"] == "/config/ruledb/rules/100/action"
        assert api.seen["method"] == "POST"

    def test_ogroup_in_body(self):
        api = _api()
        ruledb_rule_action_attach(api, "100", "13")
        assert api.seen["data"].get("ogroup") == "13"


# ---------------------------------------------------------------------------
# W5d: detach op tests (5 detach verbs — ogroup in the DELETE path)
# ---------------------------------------------------------------------------


class TestRuledbRuleFromDetach:
    def test_uses_correct_path(self):
        api = _api()
        ruledb_rule_from_detach(api, "100", "2")
        assert api.seen["path"] == "/config/ruledb/rules/100/from/2"
        assert api.seen["method"] == "DELETE"


class TestRuledbRuleToDetach:
    def test_uses_correct_path(self):
        api = _api()
        ruledb_rule_to_detach(api, "100", "3")
        assert api.seen["path"] == "/config/ruledb/rules/100/to/3"
        assert api.seen["method"] == "DELETE"


class TestRuledbRuleWhatDetach:
    def test_uses_correct_path(self):
        api = _api()
        ruledb_rule_what_detach(api, "100", "8")
        assert api.seen["path"] == "/config/ruledb/rules/100/what/8"
        assert api.seen["method"] == "DELETE"


class TestRuledbRuleWhenDetach:
    def test_uses_correct_path(self):
        api = _api()
        ruledb_rule_when_detach(api, "100", "4")
        assert api.seen["path"] == "/config/ruledb/rules/100/when/4"
        assert api.seen["method"] == "DELETE"


class TestRuledbRuleActionDetach:
    def test_uses_correct_path(self):
        api = _api()
        ruledb_rule_action_detach(api, "100", "13")
        # PMG 9.1 live-verified: singular /action (not /actions — that path returns 501)
        assert api.seen["path"] == "/config/ruledb/rules/100/action/13"
        assert api.seen["method"] == "DELETE"


# ---------------------------------------------------------------------------
# W5d: plan_ruledb_rule_create tests
# ---------------------------------------------------------------------------


class TestPlanRuledbRuleCreate:
    def test_risk_is_medium(self):
        p = plan_ruledb_rule_create("r", 50)
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_ruledb_rule_create("r", 50)
        assert p.action == "pmg_ruledb_rule_create"

    def test_active_defaults_false_in_signature(self):
        # active must default to False to satisfy the safety requirement
        p = plan_ruledb_rule_create("r", 50)
        assert "active=False" in p.change or "active=False" in str(p.blast_radius)

    def test_mail_flow_warning_in_blast_radius(self):
        p = plan_ruledb_rule_create("r", 50)
        combined = " ".join(p.blast_radius)
        assert "live mail processing" in combined

    def test_rejects_invalid_priority(self):
        with pytest.raises(ProximoError):
            plan_ruledb_rule_create("r", 999)

    def test_rejects_invalid_direction(self):
        with pytest.raises(ProximoError):
            plan_ruledb_rule_create("r", 50, direction=5)


# ---------------------------------------------------------------------------
# W5d: plan_ruledb_rule_update tests
# ---------------------------------------------------------------------------


class TestPlanRuledbRuleUpdate:
    def test_risk_is_medium(self):
        p = plan_ruledb_rule_update("100")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_ruledb_rule_update("100")
        assert p.action == "pmg_ruledb_rule_update"

    def test_mail_flow_warning_in_blast_radius(self):
        p = plan_ruledb_rule_update("100")
        combined = " ".join(p.blast_radius)
        assert "live mail processing" in combined

    def test_active_true_note_present(self):
        p = plan_ruledb_rule_update("100", active=True)
        combined = " ".join(p.blast_radius)
        assert "activates" in combined or "active" in combined

    def test_rejects_invalid_rule_id(self):
        with pytest.raises(ProximoError):
            plan_ruledb_rule_update("abc")

    def test_rejects_invalid_priority(self):
        with pytest.raises(ProximoError):
            plan_ruledb_rule_update("100", priority=200)

    def test_blast_radius_discloses_new_name(self):
        p = plan_ruledb_rule_update("100", name="Renamed-Rule")
        assert any("Renamed-Rule" in entry for entry in p.blast_radius)


# ---------------------------------------------------------------------------
# W5d: plan_ruledb_rule_delete tests
# ---------------------------------------------------------------------------


class TestPlanRuledbRuleDelete:
    def test_risk_is_medium(self):
        p = plan_ruledb_rule_delete("100")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_ruledb_rule_delete("100")
        assert p.action == "pmg_ruledb_rule_delete"

    def test_target_includes_id(self):
        p = plan_ruledb_rule_delete("100")
        assert "100" in p.target

    def test_rejects_invalid_rule_id(self):
        with pytest.raises(ProximoError):
            plan_ruledb_rule_delete("abc")


# ---------------------------------------------------------------------------
# W5d: attach/detach plan tests
# ---------------------------------------------------------------------------


class TestPlanRuledbRuleFromAttach:
    def test_risk_is_medium(self):
        p = plan_ruledb_rule_from_attach("100", "2")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_ruledb_rule_from_attach("100", "2")
        assert p.action == "pmg_ruledb_rule_from_attach"

    def test_mail_flow_note_in_blast_radius(self):
        p = plan_ruledb_rule_from_attach("100", "2")
        combined = " ".join(p.blast_radius)
        assert "only affects flow if the rule is active" in combined


class TestPlanRuledbRuleFromDetach:
    def test_risk_is_medium(self):
        p = plan_ruledb_rule_from_detach("100", "2")
        assert p.risk == RISK_MEDIUM

    def test_action_string(self):
        p = plan_ruledb_rule_from_detach("100", "2")
        assert p.action == "pmg_ruledb_rule_from_detach"


class TestPlanRuledbRuleToAttach:
    def test_risk_is_medium(self):
        p = plan_ruledb_rule_to_attach("100", "3")
        assert p.risk == RISK_MEDIUM

    def test_mail_flow_note_in_blast_radius(self):
        p = plan_ruledb_rule_to_attach("100", "3")
        combined = " ".join(p.blast_radius)
        assert "only affects flow if the rule is active" in combined


class TestPlanRuledbRuleToDetach:
    def test_risk_is_medium(self):
        p = plan_ruledb_rule_to_detach("100", "3")
        assert p.risk == RISK_MEDIUM


class TestPlanRuledbRuleWhatAttach:
    def test_risk_is_medium(self):
        p = plan_ruledb_rule_what_attach("100", "8")
        assert p.risk == RISK_MEDIUM

    def test_mail_flow_note_in_blast_radius(self):
        p = plan_ruledb_rule_what_attach("100", "8")
        combined = " ".join(p.blast_radius)
        assert "only affects flow if the rule is active" in combined


class TestPlanRuledbRuleWhatDetach:
    def test_risk_is_medium(self):
        p = plan_ruledb_rule_what_detach("100", "8")
        assert p.risk == RISK_MEDIUM


class TestPlanRuledbRuleWhenAttach:
    def test_risk_is_medium(self):
        p = plan_ruledb_rule_when_attach("100", "4")
        assert p.risk == RISK_MEDIUM

    def test_mail_flow_note_in_blast_radius(self):
        p = plan_ruledb_rule_when_attach("100", "4")
        combined = " ".join(p.blast_radius)
        assert "only affects flow if the rule is active" in combined


class TestPlanRuledbRuleWhenDetach:
    def test_risk_is_medium(self):
        p = plan_ruledb_rule_when_detach("100", "4")
        assert p.risk == RISK_MEDIUM


class TestPlanRuledbRuleActionAttach:
    def test_risk_is_medium(self):
        p = plan_ruledb_rule_action_attach("100", "13")
        assert p.risk == RISK_MEDIUM

    def test_mail_flow_note_in_blast_radius(self):
        p = plan_ruledb_rule_action_attach("100", "13")
        combined = " ".join(p.blast_radius)
        assert "only affects flow if the rule is active" in combined


class TestPlanRuledbRuleActionDetach:
    def test_risk_is_medium(self):
        p = plan_ruledb_rule_action_detach("100", "13")
        assert p.risk == RISK_MEDIUM
