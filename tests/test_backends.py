"""Backend tests — fully mocked, no live Proxmox."""

from __future__ import annotations

import subprocess

import pytest

from proximo.backends import ApiBackend, ExecBackend, ProximoError, _check_vmid
from proximo.config import ProximoConfig


def _cfg(**kw) -> ProximoConfig:
    # Tests permit by default ("*"); the allowlist gate is tested explicitly below.
    base = dict(
        api_base_url="https://x:8006/api2/json",
        node="pve",
        token_path="/run/x",
        ct_allowlist=frozenset({"*"}),
        enable_exec=True,  # exec backend is the feature under test here; the opt-in gate is tested separately
    )
    base.update(kw)
    return ProximoConfig(**base)


class _Proc:
    returncode = 0
    stdout = "ok"
    stderr = ""


def _capture(seen: dict):
    def fake_run(argv, **kw):
        seen["argv"] = argv
        return _Proc()

    return fake_run


def test_form_drops_none_and_coerces_bools():
    # L11: None must be omitted (never serialized as "None"); bools coerce to 1/0; other falsy kept
    out = ApiBackend._form({"a": None, "b": True, "c": False, "d": 0, "e": ""})
    assert out == {"b": 1, "c": 0, "d": 0, "e": ""}


def test_access_permissions_encodes_query_path(monkeypatch):
    # L14: a crafted path must not inject extra query params
    api = ApiBackend(_cfg())
    seen: dict = {}
    monkeypatch.setattr(api, "_get", lambda path: seen.update(p=path) or {})
    api.access_permissions("/pool/x&priv=Sys.Modify")
    query = seen["p"].split("?", 1)[1]
    assert "&priv=" not in query   # the injected param is neutralized
    assert "%26" in query          # '&' is percent-encoded


def test_check_vmid_rejects_unicode_digits():
    # str.isdigit() is True for non-ASCII digits (e.g. Arabic-Indic) — reject; PVE vmids are ASCII 0-9.
    with pytest.raises(ProximoError, match="must be numeric"):
        _check_vmid("١٢٣")


def test_check_vmid_accepts_ascii_digits():
    assert _check_vmid("105") == "105"


def test_exec_remote_builds_ssh_argv(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(subprocess, "run", _capture(seen))
    ExecBackend(_cfg(ssh_target="pve")).run("105", ["echo", "hi"])
    assert seen["argv"][0:2] == ["ssh", "pve"]
    assert "pct exec 105 -- echo hi" in seen["argv"][2]


def test_exec_local_builds_direct_pct_argv(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(subprocess, "run", _capture(seen))
    ExecBackend(_cfg(ssh_target="local")).run("105", ["echo", "hi"])
    assert seen["argv"] == ["pct", "exec", "105", "--", "echo", "hi"]


def test_exec_allowlist_fails_closed_when_empty():
    with pytest.raises(ProximoError, match="allowlist"):
        ExecBackend(_cfg(ct_allowlist=frozenset())).run("105", ["true"])


def test_exec_enforces_allowlist():
    with pytest.raises(ProximoError, match="allowlist"):
        ExecBackend(_cfg(ct_allowlist=frozenset({"100"}))).run("999", ["true"])


def test_exec_disabled_raises_even_with_allowlist(monkeypatch):
    # Defense-in-depth (M-3): ExecBackend.run() must enforce the PROXIMO_ENABLE_EXEC opt-in
    # itself — a permissive allowlist does NOT grant exec when the gate is off.
    monkeypatch.setattr(subprocess, "run", _capture({}))
    with pytest.raises(ProximoError, match="exec is disabled"):
        ExecBackend(_cfg(enable_exec=False, ct_allowlist=frozenset({"*"}))).run("105", ["true"])


def test_apibackend_refuses_unverified_tls(monkeypatch, tmp_path):
    # H-2: the PVE token must never cross an unverified channel. Mirrors PbsBackend's rule.
    tok = tmp_path / "t"
    tok.write_text("u@pam!t=secret")
    with pytest.raises(ProximoError, match="unverified TLS"):
        ApiBackend(_cfg(token_path=str(tok), verify_tls=False, ca_bundle=None))


def test_apibackend_ok_with_verified_tls(tmp_path):
    # The happy path still constructs: default verify_tls=True needs no CA bundle to build the client.
    tok = tmp_path / "t"
    tok.write_text("u@pam!t=secret")
    ApiBackend(_cfg(token_path=str(tok), verify_tls=True))  # no raise


def test_auth_header_format(tmp_path):
    tok = tmp_path / "token"
    tok.write_text("root@pam!proximo=secret-uuid\n")
    header = ApiBackend(_cfg(token_path=str(tok)))._auth_header()
    assert header["Authorization"] == "PVEAPIToken=root@pam!proximo=secret-uuid"


def test_guest_power_rejects_unknown_action():
    with pytest.raises(ProximoError):
        ApiBackend(_cfg()).guest_power("105", "explode")


def test_guest_status_rejects_bad_kind():
    with pytest.raises(ProximoError):
        ApiBackend(_cfg()).guest_status("105", kind="lxc/../cluster")


def test_guest_status_rejects_nonnumeric_vmid():
    with pytest.raises(ProximoError):
        ApiBackend(_cfg()).guest_status("105; reboot")


# --- UNDO pillar: snapshot backend ---

def test_snapshot_list_path(monkeypatch):
    api = ApiBackend(_cfg())
    monkeypatch.setattr(api, "_get",
                        lambda path: [{"name": "current"}] if path == "/nodes/pve/lxc/105/snapshot" else None)
    assert api.snapshot_list("105") == [{"name": "current"}]


def test_snapshot_create_builds_path_and_data(monkeypatch):
    api = ApiBackend(_cfg())
    seen: dict = {}
    monkeypatch.setattr(api, "_post", lambda path, data=None: seen.update(path=path, data=data) or "UPID:x")
    upid = api.snapshot_create("105", "before_x", description="d")
    assert seen["path"] == "/nodes/pve/lxc/105/snapshot"
    assert seen["data"] == {"snapname": "before_x", "description": "d"}
    assert upid == "UPID:x"


def test_snapshot_rollback_path(monkeypatch):
    api = ApiBackend(_cfg())
    seen: dict = {}
    monkeypatch.setattr(api, "_post", lambda path, data=None: seen.update(path=path) or "U")
    api.snapshot_rollback("105", "snap1")
    assert seen["path"] == "/nodes/pve/lxc/105/snapshot/snap1/rollback"


def test_snapshot_delete_path_and_force(monkeypatch):
    api = ApiBackend(_cfg())
    seen: dict = {}
    monkeypatch.setattr(api, "_delete", lambda path, params=None: seen.update(path=path, params=params) or "U")
    api.snapshot_delete("105", "snap1", force=True)
    assert seen["path"] == "/nodes/pve/lxc/105/snapshot/snap1"
    assert seen["params"] == {"force": 1}


def test_task_status_path(monkeypatch):
    api = ApiBackend(_cfg())
    seen: dict = {}
    monkeypatch.setattr(api, "_get",
                        lambda path: seen.update(path=path) or {"status": "stopped", "exitstatus": "OK"})
    api.task_status("UPID:pve:00001:0:0:0:vzsnapshot:105:root@pam:")
    assert seen["path"].startswith("/nodes/pve/tasks/")


def test_snapshot_create_rejects_bad_snapname():
    for bad in ["../etc", "1leadingdigit", "a/b", "has space", "semi;colon"]:
        with pytest.raises(ProximoError):
            ApiBackend(_cfg()).snapshot_create("105", bad)


def test_snapshot_rollback_rejects_path_traversal_snapname():
    with pytest.raises(ProximoError):
        ApiBackend(_cfg()).snapshot_rollback("105", "../../etc/passwd")


def test_task_status_rejects_bad_upid():
    with pytest.raises(ProximoError):
        ApiBackend(_cfg()).task_status("../../etc/passwd")


# --- redteam hardening (2026-06-07) ---

def test_snapname_rejects_trailing_newline():
    # Python $ matches before a trailing \n — must use \Z so "valid\n" doesn't slip through.
    with pytest.raises(ProximoError):
        ApiBackend(_cfg()).snapshot_create("105", "validname\n")


def test_upid_rejects_trailing_newline():
    with pytest.raises(ProximoError):
        ApiBackend(_cfg()).task_status("UPID:pve:1:0:0:0:t:105:root@pam:\n")


def test_node_rejects_trailing_newline():
    with pytest.raises(ProximoError):
        ApiBackend(_cfg()).snapshot_list("105", node="pve\n")


def test_upid_rejects_overlong():
    with pytest.raises(ProximoError):
        ApiBackend(_cfg()).task_status("UPID:pve:" + "a" * 500 + ":root@pam:")


def test_snapname_rejects_reserved_current():
    # PVE reserves "current" (the live state) — reject client-side for a clean error.
    with pytest.raises(ProximoError):
        ApiBackend(_cfg()).snapshot_create("105", "current")


# --- DIAGNOSE pillar: node read endpoints ---

def test_node_storage_path(monkeypatch):
    api = ApiBackend(_cfg())
    seen: dict = {}
    monkeypatch.setattr(api, "_get", lambda path: seen.update(path=path) or [{"storage": "local"}])
    assert api.node_storage() == [{"storage": "local"}]
    assert seen["path"] == "/nodes/pve/storage"


def test_node_tasks_path(monkeypatch):
    api = ApiBackend(_cfg())
    seen: dict = {}
    monkeypatch.setattr(api, "_get", lambda path: seen.update(path=path) or [])
    api.node_tasks(limit=50)
    assert seen["path"] == "/nodes/pve/tasks?limit=50"


def test_node_tasks_rejects_noninteger_limit():
    # limit goes into the query string; a non-int must fail loud, never inject.
    with pytest.raises((ValueError, ProximoError)):
        ApiBackend(_cfg()).node_tasks(limit="50; rm -rf")


def test_node_tasks_clamps_nonpositive_limit(monkeypatch):
    api = ApiBackend(_cfg())
    seen: dict = {}
    monkeypatch.setattr(api, "_get", lambda path: seen.update(path=path) or [])
    api.node_tasks(limit=0)
    assert "limit=0" not in seen["path"]  # non-positive limit must not pass through


def test_exec_run_validates_vmid_even_with_wildcard_allowlist():
    # Defense-in-depth: ExecBackend must reject a non-numeric ctid like ApiBackend does,
    # not lean solely on shlex.quote + pct.
    with pytest.raises(ProximoError):
        ExecBackend(_cfg(ct_allowlist=frozenset({"*"}))).run("105; rm -rf", ["true"])


# --- FIX 2: hardened _NODE_RE (leading-alnum required) ---

def test_node_rejects_dotdot_path_traversal():
    """'..' must be rejected — old regex allowed a leading dot."""
    with pytest.raises(ProximoError):
        ApiBackend(_cfg()).snapshot_list("105", node="..")


def test_node_rejects_leading_dot():
    """A node name beginning with '.' must be rejected by the hardened regex."""
    with pytest.raises(ProximoError):
        ApiBackend(_cfg()).snapshot_list("105", node=".hidden")


def test_node_accepts_valid_names():
    """Regression: host01, pve-01, node.2 (all used in practice) must still be accepted."""
    api = ApiBackend(_cfg())
    for name in ("host01", "pve-01", "node2", "pve.host"):
        # snapshot_list calls _check_node; test that no ProximoError is raised for valid names.
        # (The actual _get will fail since no HTTP stub, but the validator must not fire first.)
        try:
            api.snapshot_list("105", node=name)
        except ProximoError as exc:
            raise AssertionError(f"valid node {name!r} was rejected: {exc}") from exc
        except Exception:  # noqa: S110
            pass  # HTTP error from the real backend is expected; validator passed


# --- FIX 1: ApiBackend._put exists and mirrors _delete ---

def test_apibackend_has_put_method():
    """ApiBackend must expose _put — firewall.py and access.py call it."""
    api = ApiBackend(_cfg())
    assert hasattr(api, "_put"), "ApiBackend must have a _put method"
    assert callable(api._put)


def test_apibackend_put_uses_put_verb(monkeypatch):
    """ApiBackend._put must issue an HTTP PUT (not GET/POST/DELETE)."""
    from unittest.mock import MagicMock
    api = ApiBackend(_cfg())
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": "result"}
    mock_client = MagicMock()
    mock_client.request.return_value = mock_resp
    api._client = mock_client
    api._auth_header = lambda: {}
    api._put("/some/path", {"k": "v"})
    verb = mock_client.request.call_args[0][0]
    assert verb == "PUT"


# ---------------------------------------------------------------------------
# httpx verify=<str> deprecation regression (see proximo._tls)
# ---------------------------------------------------------------------------

def test_apibackend_ca_bundle_path_no_httpx_deprecation():
    """A CA-bundle *path* must not trigger httpx's deprecated verify=<str> form.

    httpx deprecated passing a str path to verify=; the backend now hands httpx
    an ssl.SSLContext instead. Promote DeprecationWarning to error so a regression
    fails loudly rather than warning silently.
    """
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        api = ApiBackend(_cfg(ca_bundle="/etc/ssl/certs/ca-certificates.crt"))
    # bool path stays a bool (no context built) — unchanged behavior.
    assert api._client is not None


def test_apibackend_verify_bool_passes_through():
    import ssl

    from proximo._tls import httpx_verify

    assert httpx_verify(True) is True
    assert httpx_verify(False) is False
    assert isinstance(httpx_verify("/etc/ssl/certs/ca-certificates.crt"), ssl.SSLContext)


# ---------------------------------------------------------------------------
# L09: backend-layer file path validation for agent_file_read/write
# These tests exercise the BACKEND guard directly (no server layer involved).
# The MCP path is already safe; the backend guard closes the gap for direct
# backend callers (integration tests, future A2A paths, library consumers).
# ---------------------------------------------------------------------------

def _agent_cfg(**kw) -> ProximoConfig:
    """Config with agent gate enabled and wildcard allowlist for path-validation tests."""
    base = dict(
        api_base_url="https://x:8006/api2/json",
        node="pve",
        token_path="/run/x",
        ct_allowlist=frozenset({"*"}),
        enable_exec=True,
        enable_agent=True,
        agent_allowlist=frozenset({"*"}),
    )
    base.update(kw)
    return ProximoConfig(**base)


# -- _check_file_path unit tests --

def test_check_file_path_rejects_relative_path():
    from proximo.backends import _check_file_path
    with pytest.raises(ProximoError, match="absolute path"):
        _check_file_path("relative/path")


def test_check_file_path_rejects_dotdot_traversal():
    from proximo.backends import _check_file_path
    with pytest.raises(ProximoError, match="traversal"):
        _check_file_path("/etc/../etc/passwd")


def test_check_file_path_rejects_null_byte():
    from proximo.backends import _check_file_path
    with pytest.raises(ProximoError, match="absolute path"):
        _check_file_path("/etc/hosts\x00injected")


def test_check_file_path_rejects_newline_in_path():
    from proximo.backends import _check_file_path
    with pytest.raises(ProximoError, match="absolute path"):
        _check_file_path("/etc/hosts\nX-Injected: header")


def test_check_file_path_accepts_valid_absolute_path():
    from proximo.backends import _check_file_path
    assert _check_file_path("/etc/hosts") == "/etc/hosts"


def test_check_file_path_accepts_path_with_spaces_and_specials():
    """Spaces and printable specials are allowed in guest paths (percent-encoded at wire layer)."""
    from proximo.backends import _check_file_path
    assert _check_file_path("/etc/a&b c?x=1") == "/etc/a&b c?x=1"


# -- agent_file_read backend-layer enforcement --

def test_agent_file_read_rejects_relative_path():
    """agent_file_read must reject a non-absolute path at the backend layer (defense-in-depth)."""
    api = ApiBackend(_agent_cfg())
    with pytest.raises(ProximoError, match="absolute path"):
        api.agent_file_read("101", None, "relative/path")


def test_agent_file_read_rejects_dotdot_traversal():
    """agent_file_read must block path traversal at the backend layer."""
    api = ApiBackend(_agent_cfg())
    with pytest.raises(ProximoError, match="traversal"):
        api.agent_file_read("101", None, "/etc/../etc/passwd")


def test_agent_file_read_rejects_control_char():
    """agent_file_read must reject paths containing C0 control characters."""
    api = ApiBackend(_agent_cfg())
    with pytest.raises(ProximoError, match="absolute path"):
        api.agent_file_read("101", None, "/etc/hosts\x0apayload")


def test_agent_file_read_accepts_valid_path(monkeypatch):
    """A valid absolute path clears backend validation and reaches the HTTP layer."""
    api = ApiBackend(_agent_cfg())
    monkeypatch.setattr(api, "_get", lambda path: {"content": "data", "bytes-read": 4})
    result = api.agent_file_read("101", None, "/etc/hosts")
    assert result == {"content": "data", "bytes-read": 4}


# -- agent_file_write backend-layer enforcement --

def test_agent_file_write_rejects_relative_path():
    """agent_file_write must reject a non-absolute path at the backend layer (defense-in-depth)."""
    api = ApiBackend(_agent_cfg())
    with pytest.raises(ProximoError, match="absolute path"):
        api.agent_file_write("101", None, "relative/path", "content")


def test_agent_file_write_rejects_dotdot_traversal():
    """agent_file_write must block path traversal at the backend layer."""
    api = ApiBackend(_agent_cfg())
    with pytest.raises(ProximoError, match="traversal"):
        api.agent_file_write("101", None, "/var/log/../../../etc/shadow", "content")


def test_agent_file_write_rejects_control_char():
    """agent_file_write must reject paths containing C0 control characters."""
    api = ApiBackend(_agent_cfg())
    with pytest.raises(ProximoError, match="absolute path"):
        api.agent_file_write("101", None, "/var/log/file\x00injected", "content")


def test_agent_file_write_accepts_valid_path(monkeypatch):
    """A valid absolute path clears backend validation and reaches the HTTP layer."""
    api = ApiBackend(_agent_cfg())
    monkeypatch.setattr(api, "_post", lambda path, data=None: None)
    api.agent_file_write("101", None, "/var/log/probe.txt", "content")  # must not raise
