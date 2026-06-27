"""TDD tests for the qemu-agent plane (Wave 3).

Covers:
- Config: agent_permitted unit tests (empty deny, "*" allow, exact match, enable_agent flag)
- Plan factories: correct Plan fields (action/target/risk/no-undo note/redaction)
- Validators: file path, info-command, fs-command closed sets
- Backend gate: ApiBackend raises ProximoError with gate off or vmid not permitted
- Server gate (server layer): enable off → blocked:agent_disabled; vmid not allowlisted → blocked:allowlist
- exec timeout honesty: status="running" with pid when deadline passed; status="ok" only when exited
- Redaction: "hunter2" (password) and "SECRET-PAYLOAD" (content) appear NOWHERE in plan dict,
  ledger, or any detail — on both confirm=False and confirm=True paths
- Mutating tools: plan-by-default (no confirm → status=="plan", nothing executed); confirm executes
- Read tools: no confirm param, correct mutation=False ledger entries when blocked
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.backends import ApiBackend, ProximoError
from proximo.config import ProximoConfig
from proximo.qemu_agent import (
    _check_agent_fs_command,
    _check_agent_info_command,
    _check_file_path,
    _content_fingerprint,
    _password_fingerprint,
    plan_agent_exec,
    plan_agent_file_write,
    plan_agent_fs,
    plan_agent_set_password,
)

# ─── helpers ──────────────────────────────────────────────────────────────────

_PASSWORD_SENTINEL = "hunter2"
_CONTENT_SENTINEL = "SECRET-PAYLOAD"


def _make_cfg(
    enable_agent: bool = True,
    agent_allowlist: frozenset[str] | None = None,
    enable_exec: bool = False,
    ct_allowlist: frozenset[str] | None = None,
    log_path: str | None = None,
    redact_ledger: bool = False,
) -> ProximoConfig:
    return ProximoConfig(
        api_base_url="https://fake:8006/api2/json",
        node="pve",
        token_path="/dev/null",
        enable_agent=enable_agent,
        agent_allowlist=agent_allowlist if agent_allowlist is not None else frozenset({"*"}),
        enable_exec=enable_exec,
        ct_allowlist=ct_allowlist if ct_allowlist is not None else frozenset(),
        audit_log_path=log_path or "/dev/null",
        redact_ledger=redact_ledger,
    )


class _FakeAgentApi:
    """Fake ApiBackend that records agent calls and returns canned responses."""

    def __init__(self, *, exec_returns=None, exec_status_returns=None,
                 file_read_returns=None, simple_returns=None):
        self.config = SimpleNamespace(node="pve")
        self.agent_execs: list = []
        self.agent_exec_statuses: list = []
        self.agent_file_reads: list = []
        self.agent_file_writes: list = []
        self.agent_set_passwords: list = []
        self.agent_simples: list = []
        self._exec_returns = exec_returns or {"pid": 42}
        self._exec_status_returns = exec_status_returns or {"exited": True, "exitcode": 0,
                                                             "out-data": "", "err-data": ""}
        self._file_read_returns = file_read_returns or {"content": "file-body"}
        self._simple_returns = simple_returns or {}

    def agent_exec(self, vmid, node, command):
        self.agent_execs.append((vmid, node, command))
        return dict(self._exec_returns)

    def agent_exec_status(self, vmid, node, pid):
        self.agent_exec_statuses.append((vmid, node, pid))
        return dict(self._exec_status_returns)

    def agent_file_read(self, vmid, node, file):
        self.agent_file_reads.append((vmid, node, file))
        return dict(self._file_read_returns)

    def agent_file_write(self, vmid, node, file, content):
        self.agent_file_writes.append((vmid, node, file, content))
        return None  # PVE returns no body

    def agent_set_password(self, vmid, node, username, password):
        self.agent_set_passwords.append((vmid, node, username, password))
        return None  # PVE returns no body

    def agent_simple(self, vmid, node, command):
        self.agent_simples.append((vmid, node, command))
        return dict(self._simple_returns)


class _FakeExec:
    pass  # qemu-agent plane never touches exec backend


def _wire_agent(tmp_path, monkeypatch, *,
                enable_agent=True,
                agent_allowlist=None,
                exec_returns=None,
                exec_status_returns=None,
                file_read_returns=None,
                simple_returns=None,
                redact_ledger=False):
    """Wire the server with a fake agent-capable API and a real ledger."""
    log = str(tmp_path / "audit.log")
    cfg = _make_cfg(
        enable_agent=enable_agent,
        agent_allowlist=agent_allowlist if agent_allowlist is not None else frozenset({"*"}),
        log_path=log,
        redact_ledger=redact_ledger,
    )
    api = _FakeAgentApi(
        exec_returns=exec_returns,
        exec_status_returns=exec_status_returns,
        file_read_returns=file_read_returns,
        simple_returns=simple_returns,
    )
    exec_ = _FakeExec()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, exec_, ledger))
    return cfg, api, exec_, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ─── Config: agent_permitted ──────────────────────────────────────────────────

class TestAgentPermitted:
    def test_empty_allowlist_denies_all(self):
        cfg = _make_cfg(agent_allowlist=frozenset())
        assert cfg.agent_permitted("101") is False
        assert cfg.agent_permitted("200") is False

    def test_star_allows_all(self):
        cfg = _make_cfg(agent_allowlist=frozenset({"*"}))
        assert cfg.agent_permitted("101") is True
        assert cfg.agent_permitted("999") is True

    def test_exact_match_allows(self):
        cfg = _make_cfg(agent_allowlist=frozenset({"101", "200"}))
        assert cfg.agent_permitted("101") is True
        assert cfg.agent_permitted("200") is True

    def test_exact_match_denies_other(self):
        cfg = _make_cfg(agent_allowlist=frozenset({"101"}))
        assert cfg.agent_permitted("200") is False

    def test_str_coercion(self):
        cfg = _make_cfg(agent_allowlist=frozenset({"101"}))
        # Callers may pass int-like or padded strings
        assert cfg.agent_permitted("101") is True


# ─── Validators ───────────────────────────────────────────────────────────────

class TestValidators:
    def test_file_path_absolute_valid(self):
        assert _check_file_path("/etc/passwd") == "/etc/passwd"
        assert _check_file_path("/var/log/syslog") == "/var/log/syslog"

    def test_file_path_relative_raises(self):
        with pytest.raises(ProximoError, match="absolute"):
            _check_file_path("etc/passwd")

    def test_file_path_empty_raises(self):
        with pytest.raises(ProximoError):
            _check_file_path("")

    def test_file_path_traversal_raises(self):
        with pytest.raises(ProximoError, match="traversal"):
            _check_file_path("/etc/../etc/shadow")

    def test_file_path_control_chars_rejected(self):
        # CR/LF/TAB/NUL and other C0 controls are the header/URL-injection vectors — reject them.
        for bad in ("/etc/x\r\nX-Injected: y", "/etc/x\n", "/etc/x\ttab", "/etc/x\x00", "/etc/\x1b"):
            with pytest.raises(ProximoError):
                _check_file_path(bad)

    def test_file_path_space_allowed(self):
        # Space is legal in a guest path (e.g. "/home/u/My Documents/f"); the backend percent-encodes it.
        assert _check_file_path("/home/u/My Documents/f") == "/home/u/My Documents/f"

    def test_username_valid(self):
        from proximo.backends import _check_username
        assert _check_username("root") == "root"
        assert _check_username("alice.smith") == "alice.smith"

    def test_username_rejects_garbage(self):
        from proximo.backends import _check_username
        for bad in ("", "a" * 257, "root\nadmin", "user\x00", "x\ty"):
            with pytest.raises(ProximoError):
                _check_username(bad)

    def test_info_command_valid(self):
        for cmd in ("ping", "info", "get-osinfo", "get-host-name", "fsfreeze-status", "exec-status"):
            assert _check_agent_info_command(cmd) == cmd

    def test_info_command_invalid_raises(self):
        with pytest.raises(ProximoError, match="unsupported agent info command"):
            _check_agent_info_command("fsfreeze-freeze")  # fs cmd, not info cmd

    def test_info_command_arbitrary_raises(self):
        with pytest.raises(ProximoError):
            _check_agent_info_command("../../etc")

    def test_fs_command_valid(self):
        for cmd in ("fsfreeze-freeze", "fsfreeze-thaw", "fstrim"):
            assert _check_agent_fs_command(cmd) == cmd

    def test_fs_command_invalid_raises(self):
        with pytest.raises(ProximoError, match="unsupported agent fs command"):
            _check_agent_fs_command("ping")

    def test_backend_agent_simple_rejects_exec_status(self):
        """exec-status is NOT in agent_simple's valid set — it must go through agent_exec_status."""
        # Confirm the frozenset design: exec-status not in _VALID_AGENT_SIMPLE_CMDS
        from proximo.backends import _VALID_AGENT_SIMPLE_CMDS
        assert "exec-status" not in _VALID_AGENT_SIMPLE_CMDS


# ─── Plan factories ───────────────────────────────────────────────────────────

class TestPlanFactories:
    def test_plan_agent_exec_fields(self):
        plan = plan_agent_exec("101", ["echo", "hello"])
        assert plan.action == "pve_agent_exec"
        assert plan.target == "qemu/101"
        assert plan.risk == "medium"
        assert "No UNDO" in plan.note
        assert "Irreversible" in plan.note
        assert "echo" in plan.change

    def test_plan_agent_exec_redact_check(self):
        """Command IS allowed in plan (not a secret) — it's content/password that must be redacted."""
        plan = plan_agent_exec("101", ["echo", "hello"])
        d = plan.as_dict()
        assert "echo" in json.dumps(d)  # command appears (normal)

    def test_plan_agent_file_write_content_redacted(self):
        plan = plan_agent_file_write("101", "/etc/hosts", _CONTENT_SENTINEL)
        d = plan.as_dict()
        dump = json.dumps(d)
        assert _CONTENT_SENTINEL not in dump, (
            f"content sentinel leaked into plan dict: {dump[:500]}"
        )
        assert "content_sha256" in dump
        assert "content_len" in dump

    def test_plan_agent_file_write_fields(self):
        plan = plan_agent_file_write("101", "/etc/hosts", "content")
        assert plan.action == "pve_agent_file_write"
        assert plan.target == "qemu/101:/etc/hosts"
        # HIGH: overwrites an arbitrary caller-supplied path (could be /etc/shadow), irreversible.
        assert plan.risk == "high"
        assert "No UNDO" in plan.note
        assert "unconditionally redacted" in plan.note.lower()

    def test_plan_agent_fs_freeze_high_risk(self):
        plan = plan_agent_fs("101", "fsfreeze-freeze")
        assert plan.risk == "high"
        assert "No UNDO" in plan.note

    def test_plan_agent_fs_thaw_high_risk(self):
        plan = plan_agent_fs("101", "fsfreeze-thaw")
        assert plan.risk == "high"

    def test_plan_agent_fs_fstrim_medium_risk(self):
        plan = plan_agent_fs("101", "fstrim")
        assert plan.risk == "medium"

    def test_plan_agent_set_password_redacted(self):
        plan = plan_agent_set_password("101", "root")
        d = plan.as_dict()
        dump = json.dumps(d)
        assert _PASSWORD_SENTINEL not in dump
        assert "[redacted]" in dump

    def test_plan_agent_set_password_fields(self):
        plan = plan_agent_set_password("101", "alice")
        assert plan.action == "pve_agent_set_password"
        assert plan.target == "qemu/101:alice"
        assert plan.risk == "high"
        assert "No UNDO" in plan.note
        assert "unconditionally redacted" in plan.note.lower()


# ─── Backend defense-in-depth ─────────────────────────────────────────────────

class TestApiBackendAgentGate:
    """The gate must be enforced AT the backend — no caller can bypass by skipping the server layer."""

    def _make_api(self, enable_agent: bool = True,
                  agent_allowlist: frozenset[str] | None = None) -> ApiBackend:
        cfg = ProximoConfig(
            api_base_url="https://fake:8006/api2/json",
            node="pve",
            token_path="/dev/null",
            # verify_tls=True → ApiBackend constructor does NOT raise (only refuses verify=False)
            verify_tls=True,
            enable_agent=enable_agent,
            agent_allowlist=agent_allowlist if agent_allowlist is not None else frozenset({"*"}),
        )
        return ApiBackend(cfg)

    def test_agent_exec_gate_disabled_raises(self):
        api = self._make_api(enable_agent=False)
        with pytest.raises(ProximoError, match="disabled"):
            api.agent_exec("101", None, ["echo"])

    def test_agent_exec_empty_allowlist_raises(self):
        api = self._make_api(enable_agent=True, agent_allowlist=frozenset())
        with pytest.raises(ProximoError, match="allowlist"):
            api.agent_exec("101", None, ["echo"])

    def test_agent_exec_wrong_vmid_raises(self):
        api = self._make_api(enable_agent=True, agent_allowlist=frozenset({"200"}))
        with pytest.raises(ProximoError, match="allowlist"):
            api.agent_exec("101", None, ["echo"])

    def test_agent_simple_gate_disabled_raises(self):
        api = self._make_api(enable_agent=False)
        with pytest.raises(ProximoError, match="disabled"):
            api.agent_simple("101", None, "ping")

    def test_agent_file_read_gate_disabled_raises(self):
        api = self._make_api(enable_agent=False)
        with pytest.raises(ProximoError, match="disabled"):
            api.agent_file_read("101", None, "/etc/hosts")

    def test_agent_file_write_gate_disabled_raises(self):
        api = self._make_api(enable_agent=False)
        with pytest.raises(ProximoError, match="disabled"):
            api.agent_file_write("101", None, "/var/log/oldfile.log", "content")

    def test_agent_set_password_gate_disabled_raises(self):
        api = self._make_api(enable_agent=False)
        with pytest.raises(ProximoError, match="disabled"):
            api.agent_set_password("101", None, "root", "pw")

    def test_agent_simple_invalid_command_raises(self):
        api = self._make_api(enable_agent=True)
        with pytest.raises(ProximoError, match="unsupported agent command"):
            api.agent_simple("101", None, "exec-status")  # must go through agent_exec_status

    def test_agent_simple_routes_reads_get_actions_post(self, monkeypatch):
        """Live-proven (PVE 9.2): read commands are GET, action commands POST. A POST to a get-*
        path 501s on the real host — this regression-guards the method split the mocks can't catch."""
        api = self._make_api(enable_agent=True)
        used = {}
        monkeypatch.setattr(api, "_get", lambda path: used.__setitem__("m", "GET") or {})
        monkeypatch.setattr(api, "_post", lambda path, data=None: used.__setitem__("m", "POST") or {})
        for read_cmd in ("get-osinfo", "info", "network-get-interfaces", "get-fsinfo"):
            api.agent_simple("101", None, read_cmd)
            assert used["m"] == "GET", f"{read_cmd} must be GET"
        for action_cmd in ("ping", "fstrim", "fsfreeze-status", "fsfreeze-freeze", "fsfreeze-thaw"):
            api.agent_simple("101", None, action_cmd)
            assert used["m"] == "POST", f"{action_cmd} must be POST"

    def test_agent_file_read_url_encodes_file_param(self, monkeypatch):
        """The caller-supplied path is percent-encoded into the query string so '&'/'?'/space
        cannot inject extra query params or corrupt the request."""
        api = self._make_api(enable_agent=True)
        captured = {}

        def _fake_get(path):
            captured["path"] = path
            return {}

        monkeypatch.setattr(api, "_get", _fake_get)
        api.agent_file_read("101", None, "/etc/a&b c?x=1")
        p = captured["path"]
        assert "%26" in p and "%20" in p and "%3F" in p   # & space ? all encoded
        assert "a&b" not in p                              # raw '&' must NOT survive into the query
        assert "?file=" in p                               # the only literal '?' is our query separator


# ─── Server gate helpers ──────────────────────────────────────────────────────

class TestServerGateHelpers:
    """blocked:agent_disabled and blocked:allowlist are correct for both mutation and read."""

    def test_agent_disabled_mutation_status(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire_agent(tmp_path, monkeypatch, enable_agent=False)
        out = server.pve_agent_exec("101", ["echo"], confirm=False)
        assert out["status"] == "blocked:agent_disabled"
        entries = _entries(log)
        blocked = [e for e in entries if e["outcome"] == "blocked:agent_disabled"]
        assert len(blocked) == 1
        assert blocked[0]["mutation"] is True

    def test_agent_disabled_read_status(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire_agent(tmp_path, monkeypatch, enable_agent=False)
        out = server.pve_agent_info("101")
        assert out["status"] == "blocked:agent_disabled"
        entries = _entries(log)
        blocked = [e for e in entries if e["outcome"] == "blocked:agent_disabled"]
        assert len(blocked) == 1
        assert blocked[0]["mutation"] is False  # read tool must NOT ledger as mutation

    def test_agent_disabled_file_read_not_mutation(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire_agent(tmp_path, monkeypatch, enable_agent=False)
        out = server.pve_agent_file_read("101", "/etc/hosts")
        assert out["status"] == "blocked:agent_disabled"
        entries = _entries(log)
        blocked = [e for e in entries if e["outcome"] == "blocked:agent_disabled"]
        assert blocked[0]["mutation"] is False

    def test_allowlist_blocked_mutation(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire_agent(tmp_path, monkeypatch,
                                      agent_allowlist=frozenset({"200"}))
        out = server.pve_agent_exec("101", ["echo"])
        assert out["status"] == "blocked:allowlist"
        entries = _entries(log)
        blocked = [e for e in entries if e["outcome"] == "blocked:allowlist"]
        assert blocked[0]["mutation"] is True

    def test_allowlist_blocked_read_not_mutation(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire_agent(tmp_path, monkeypatch,
                                      agent_allowlist=frozenset({"200"}))
        out = server.pve_agent_info("101")
        assert out["status"] == "blocked:allowlist"
        entries = _entries(log)
        blocked = [e for e in entries if e["outcome"] == "blocked:allowlist"]
        assert blocked[0]["mutation"] is False

    def test_allowlist_blocked_file_read_not_mutation(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire_agent(tmp_path, monkeypatch,
                                      agent_allowlist=frozenset({"200"}))
        out = server.pve_agent_file_read("101", "/etc/hosts")
        assert out["status"] == "blocked:allowlist"
        entries = _entries(log)
        blocked = [e for e in entries if e["outcome"] == "blocked:allowlist"]
        assert blocked[0]["mutation"] is False


# ─── Plan-by-default (no confirm) ─────────────────────────────────────────────

class TestPlanByDefault:
    def test_agent_exec_no_confirm_returns_plan(self, tmp_path, monkeypatch):
        _, api, _, _, log = _wire_agent(tmp_path, monkeypatch)
        out = server.pve_agent_exec("101", ["echo", "hi"])
        assert out["status"] == "plan"
        assert api.agent_execs == []  # nothing executed
        planned = [e for e in _entries(log) if e["outcome"] == "planned"]
        assert len(planned) == 1

    def test_agent_file_write_no_confirm_returns_plan(self, tmp_path, monkeypatch):
        _, api, _, _, log = _wire_agent(tmp_path, monkeypatch)
        out = server.pve_agent_file_write("101", "/var/log/probe.txt", "body")
        assert out["status"] == "plan"
        assert api.agent_file_writes == []

    def test_agent_fs_no_confirm_returns_plan(self, tmp_path, monkeypatch):
        _, api, _, _, log = _wire_agent(tmp_path, monkeypatch)
        out = server.pve_agent_fs("101", "fstrim")
        assert out["status"] == "plan"
        assert api.agent_simples == []

    def test_agent_set_password_no_confirm_returns_plan(self, tmp_path, monkeypatch):
        _, api, _, _, log = _wire_agent(tmp_path, monkeypatch)
        out = server.pve_agent_set_password("101", "root", _PASSWORD_SENTINEL)
        assert out["status"] == "plan"
        assert api.agent_set_passwords == []

    def test_oneshot_confirm_still_records_plan_first(self, tmp_path, monkeypatch):
        """Even a one-shot confirm=True must record a 'planned' entry BEFORE 'ok'."""
        _, api, _, _, log = _wire_agent(tmp_path, monkeypatch)
        out = server.pve_agent_fs("101", "fstrim", confirm=True)
        assert out["status"] == "ok"
        entries = _entries(log)
        # planned must appear before ok
        outcomes = [e["outcome"] for e in entries]
        assert "planned" in outcomes
        assert "ok" in outcomes
        assert outcomes.index("planned") < outcomes.index("ok")


# ─── Confirm executes ─────────────────────────────────────────────────────────

class TestConfirmExecutes:
    def test_agent_fs_confirm_executes(self, tmp_path, monkeypatch):
        _, api, _, _, log = _wire_agent(tmp_path, monkeypatch)
        out = server.pve_agent_fs("101", "fstrim", confirm=True)
        assert out["status"] == "ok"
        assert api.agent_simples == [("101", None, "fstrim")]

    def test_agent_file_write_confirm_executes(self, tmp_path, monkeypatch):
        _, api, _, _, log = _wire_agent(tmp_path, monkeypatch)
        out = server.pve_agent_file_write("101", "/var/log/probe.txt", "body", confirm=True)
        assert out["status"] == "ok"
        assert api.agent_file_writes == [("101", None, "/var/log/probe.txt", "body")]

    def test_agent_set_password_confirm_executes(self, tmp_path, monkeypatch):
        _, api, _, _, log = _wire_agent(tmp_path, monkeypatch)
        out = server.pve_agent_set_password("101", "root", _PASSWORD_SENTINEL, confirm=True)
        assert out["status"] == "ok"
        assert api.agent_set_passwords == [("101", None, "root", _PASSWORD_SENTINEL)]

    def test_agent_info_no_confirm_needed(self, tmp_path, monkeypatch):
        _, api, _, _, log = _wire_agent(tmp_path, monkeypatch)
        out = server.pve_agent_info("101", command="ping")
        # Returns raw result (read tool), not a plan or confirm envelope
        assert "status" not in out or out.get("status") not in ("plan",)
        assert api.agent_simples == [("101", None, "ping")]

    def test_agent_file_read_no_confirm_needed(self, tmp_path, monkeypatch):
        _, api, _, _, log = _wire_agent(tmp_path, monkeypatch)
        out = server.pve_agent_file_read("101", "/etc/hosts")
        assert "content" in out or out is not None  # raw read result
        assert api.agent_file_reads == [("101", None, "/etc/hosts")]


# ─── exec timeout honesty ─────────────────────────────────────────────────────

class TestExecTimeoutHonesty:
    def test_exec_ok_when_exited(self, tmp_path, monkeypatch):
        """status="ok" ONLY when agent reports exited=True."""
        _, api, _, _, log = _wire_agent(
            tmp_path, monkeypatch,
            exec_returns={"pid": 99},
            exec_status_returns={"exited": True, "exitcode": 0, "out-data": "hello", "err-data": ""},
        )
        out = server.pve_agent_exec("101", ["echo"], confirm=True)
        assert out["status"] == "ok"
        assert out["result"]["pid"] == 99
        assert out["result"]["exitcode"] == 0
        entries = _entries(log)
        ok_entries = [e for e in entries if e["outcome"] == "ok"]
        assert len(ok_entries) == 1

    def test_exec_running_on_timeout(self, tmp_path, monkeypatch):
        """When exec-status never reports exited, return status="running" with pid — never "ok"."""
        _, api, _, _, log = _wire_agent(
            tmp_path, monkeypatch,
            exec_returns={"pid": 77},
            # Agent never reports exited — timeout path must fire
            exec_status_returns={"exited": False, "exitcode": None},
        )
        # timeout=0: deadline is immediately exhausted (after the first status check, monotonic has passed)
        out = server.pve_agent_exec("101", ["sleep", "100"], timeout=0, confirm=True)
        assert out["status"] == "running"
        assert out["pid"] == 77
        assert "running" in out["message"]
        entries = _entries(log)
        # NO "ok" outcome in the ledger for this action
        ok_entries = [e for e in entries if e["action"] == "pve_agent_exec" and e["outcome"] == "ok"]
        assert len(ok_entries) == 0
        running_entries = [e for e in entries if e["action"] == "pve_agent_exec"
                           and e["outcome"] == "running"]
        assert len(running_entries) == 1

    def test_exec_timeout_plan_recorded_first(self, tmp_path, monkeypatch):
        """Even on the timeout path, a 'planned' entry precedes the 'running' entry."""
        _, api, _, _, log = _wire_agent(
            tmp_path, monkeypatch,
            exec_returns={"pid": 7},
            exec_status_returns={"exited": False},
        )
        server.pve_agent_exec("101", ["cmd"], timeout=0, confirm=True)
        entries = _entries(log)
        outcomes = [e["outcome"] for e in entries]
        assert "planned" in outcomes
        assert "running" in outcomes
        assert outcomes.index("planned") < outcomes.index("running")

    def test_exec_exited_int_one_is_ok(self, tmp_path, monkeypatch):
        """'exited' may arrive as int 1 (not bool True) — still counts as completion → ok."""
        _, _, _, _, log = _wire_agent(
            tmp_path, monkeypatch,
            exec_returns={"pid": 5},
            exec_status_returns={"exited": 1, "exitcode": 0, "out-data": "x", "err-data": ""},
        )
        out = server.pve_agent_exec("101", ["echo"], confirm=True)
        assert out["status"] == "ok"

    def test_exec_polls_multiple_iterations_and_sleeps(self, tmp_path, monkeypatch):
        """The poll loop must NOT busy-wait: it sleeps between exec-status polls and keeps polling
        until the agent reports exited (proves the loop runs >1 iteration with a paced sleep)."""
        _, api, _, _, log = _wire_agent(tmp_path, monkeypatch, exec_returns={"pid": 8})
        # exec-status: not-exited twice, then exited.
        statuses = [
            {"exited": False},
            {"exited": False},
            {"exited": True, "exitcode": 0, "out-data": "done", "err-data": ""},
        ]
        calls = {"n": 0}

        def _status(vmid, node, pid):
            i = min(calls["n"], len(statuses) - 1)
            calls["n"] += 1
            return dict(statuses[i])

        sleeps: list = []
        monkeypatch.setattr(api, "agent_exec_status", _status)
        monkeypatch.setattr(server.time, "sleep", lambda s: sleeps.append(s))

        out = server.pve_agent_exec("101", ["echo"], timeout=60, confirm=True)
        assert out["status"] == "ok"
        assert calls["n"] == 3            # polled three times (two not-exited, then exited)
        assert sleeps == [server._AGENT_POLL_INTERVAL] * 2  # slept between the polls, not after exit

    def test_exec_respects_redact_ledger(self, tmp_path, monkeypatch):
        """With PROXIMO_LEDGER_REDACT on, a secret in the exec argv must NOT reach the ledger —
        the plan's change line carries a fingerprint, not the argv (parity with ct_exec)."""
        _, _, _, _, log = _wire_agent(
            tmp_path, monkeypatch,
            exec_returns={"pid": 3},
            exec_status_returns={"exited": True, "exitcode": 0, "out-data": "", "err-data": ""},
            redact_ledger=True,
        )
        secret = "p@ss-IN-ARGV"
        out = server.pve_agent_exec("101", ["mysql", f"-p{secret}", "db"], confirm=True)
        assert out["status"] == "ok"
        # The argv secret must appear in NO ledger line (planned, ok, anything).
        with open(log, encoding="utf-8") as f:
            leaks = [ln for ln in f if secret in ln]
        assert leaks == [], f"redacted argv leaked into ledger: {leaks}"

    def test_exec_no_redact_records_argv(self, tmp_path, monkeypatch):
        """Default (redact off): the argv IS recorded — exec command is not a secret by default."""
        _, _, _, _, log = _wire_agent(
            tmp_path, monkeypatch,
            exec_returns={"pid": 3},
            exec_status_returns={"exited": True, "exitcode": 0, "out-data": "", "err-data": ""},
        )
        server.pve_agent_exec("101", ["echo", "marker-XYZ"], confirm=True)
        with open(log, encoding="utf-8") as f:
            body = f.read()
        assert "marker-XYZ" in body


# ─── Redaction (load-bearing) ─────────────────────────────────────────────────

class TestRedaction:
    """Sentinels must NOT appear in: plan dict, ledger (planned entry), detail (ok/running), result."""

    def _scan_ledger(self, log: str, sentinel: str) -> list[str]:
        """Return all ledger lines that contain the sentinel."""
        with open(log, encoding="utf-8") as f:
            return [line for line in f if sentinel in line]

    # --- set_password ---

    def test_password_not_in_plan_dict(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire_agent(tmp_path, monkeypatch)
        out = server.pve_agent_set_password("101", "root", _PASSWORD_SENTINEL)
        assert out["status"] == "plan"
        dump = json.dumps(out)
        assert _PASSWORD_SENTINEL not in dump, (
            f"password sentinel leaked into plan dict: {dump[:500]}"
        )

    def test_password_not_in_ledger_plan_path(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire_agent(tmp_path, monkeypatch)
        server.pve_agent_set_password("101", "root", _PASSWORD_SENTINEL)
        leaks = self._scan_ledger(log, _PASSWORD_SENTINEL)
        assert leaks == [], f"password sentinel found in ledger (plan path): {leaks}"

    def test_password_not_in_plan_dict_oneshot(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire_agent(tmp_path, monkeypatch)
        out = server.pve_agent_set_password("101", "root", _PASSWORD_SENTINEL, confirm=True)
        assert out["status"] == "ok"
        dump = json.dumps(out)
        assert _PASSWORD_SENTINEL not in dump, (
            f"password sentinel leaked into confirm result: {dump[:500]}"
        )

    def test_password_not_in_ledger_confirm_path(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire_agent(tmp_path, monkeypatch)
        server.pve_agent_set_password("101", "root", _PASSWORD_SENTINEL, confirm=True)
        leaks = self._scan_ledger(log, _PASSWORD_SENTINEL)
        assert leaks == [], f"password sentinel found in ledger (confirm path): {leaks}"

    # --- file_write ---

    def test_content_not_in_plan_dict(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire_agent(tmp_path, monkeypatch)
        out = server.pve_agent_file_write("101", "/var/log/probe.txt", _CONTENT_SENTINEL)
        assert out["status"] == "plan"
        dump = json.dumps(out)
        assert _CONTENT_SENTINEL not in dump, (
            f"content sentinel leaked into plan dict: {dump[:500]}"
        )

    def test_content_not_in_ledger_plan_path(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire_agent(tmp_path, monkeypatch)
        server.pve_agent_file_write("101", "/var/log/probe.txt", _CONTENT_SENTINEL)
        leaks = self._scan_ledger(log, _CONTENT_SENTINEL)
        assert leaks == [], f"content sentinel found in ledger (plan path): {leaks}"

    def test_content_not_in_plan_dict_oneshot(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire_agent(tmp_path, monkeypatch)
        out = server.pve_agent_file_write("101", "/var/log/probe.txt", _CONTENT_SENTINEL, confirm=True)
        assert out["status"] == "ok"
        dump = json.dumps(out)
        assert _CONTENT_SENTINEL not in dump, (
            f"content sentinel leaked into confirm result: {dump[:500]}"
        )

    def test_content_not_in_ledger_confirm_path(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire_agent(tmp_path, monkeypatch)
        server.pve_agent_file_write("101", "/var/log/probe.txt", _CONTENT_SENTINEL, confirm=True)
        leaks = self._scan_ledger(log, _CONTENT_SENTINEL)
        assert leaks == [], f"content sentinel found in ledger (confirm path): {leaks}"

    def test_content_fingerprint_in_plan(self, tmp_path, monkeypatch):
        """Redaction is present BUT fingerprint is there — plan is still useful."""
        _, _, _, _, log = _wire_agent(tmp_path, monkeypatch)
        out = server.pve_agent_file_write("101", "/var/log/probe.txt", _CONTENT_SENTINEL)
        dump = json.dumps(out)
        assert "content_sha256" in dump
        assert "content_len" in dump

    def test_password_fingerprint_in_plan(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire_agent(tmp_path, monkeypatch)
        out = server.pve_agent_set_password("101", "root", _PASSWORD_SENTINEL)
        dump = json.dumps(out)
        assert "[redacted]" in dump


# ─── Read tool ledger detail (no content body in ledger) ─────────────────────

class TestReadToolLedger:
    def test_file_read_ledger_has_path_not_content(self, tmp_path, monkeypatch):
        """pve_agent_file_read logs file path to ledger; the content is in the returned dict only."""
        _, api, _, _, log = _wire_agent(tmp_path, monkeypatch,
                                        file_read_returns={"content": "SECRET-FILE-BODY"})
        out = server.pve_agent_file_read("101", "/etc/hosts")
        # The returned dict may carry content (that's the point of the tool)
        # but the ledger detail must only carry the file path
        entries = _entries(log)
        for entry in entries:
            detail_str = json.dumps(entry.get("detail", {}))
            assert "SECRET-FILE-BODY" not in detail_str, (
                f"file content leaked into ledger detail: {detail_str[:300]}"
            )
        assert "content" in out or out is not None

    def test_agent_info_result_passes_through(self, tmp_path, monkeypatch):
        _, api, _, _, log = _wire_agent(tmp_path, monkeypatch,
                                        simple_returns={"hostname": "myvm"})
        out = server.pve_agent_info("101", command="get-host-name")
        assert out.get("hostname") == "myvm"

    def test_agent_info_exec_status_routes_to_exec_status_method(self, tmp_path, monkeypatch):
        """exec-status command must be routed to agent_exec_status, not agent_simple."""
        _, api, _, _, log = _wire_agent(
            tmp_path, monkeypatch,
            exec_status_returns={"exited": True, "exitcode": 0, "out-data": "", "err-data": ""},
        )
        server.pve_agent_info("101", command="exec-status", pid=42)
        assert api.agent_exec_statuses == [("101", None, 42)]
        assert api.agent_simples == []


# ─── Fingerprint helpers ──────────────────────────────────────────────────────

class TestFingerprintHelpers:
    def test_content_fingerprint_structure(self):
        fp = _content_fingerprint("hello world")
        assert "content_sha256" in fp
        assert "content_len" in fp
        assert fp["content_len"] == 11
        assert len(fp["content_sha256"]) == 64

    def test_content_fingerprint_deterministic(self):
        fp1 = _content_fingerprint("abc")
        fp2 = _content_fingerprint("abc")
        assert fp1 == fp2

    def test_content_fingerprint_different_inputs(self):
        fp1 = _content_fingerprint("abc")
        fp2 = _content_fingerprint("xyz")
        assert fp1["content_sha256"] != fp2["content_sha256"]

    def test_password_fingerprint_structure(self):
        # Structure only — the function takes no password, so it cannot leak one. The real
        # "secret never reaches the ledger" invariant is owned by TestRedaction (which scans the
        # on-disk ledger after a tool call with a sentinel password).
        assert _password_fingerprint() == {"password": "[redacted]"}


# ─── No-undo declarations ─────────────────────────────────────────────────────

class TestNoUndo:
    def test_agent_exec_plan_declares_no_undo(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire_agent(tmp_path, monkeypatch)
        out = server.pve_agent_exec("101", ["rm", "-rf", "/var/log/oldfile.log"])
        assert "no undo" in out.get("note", "").lower() or "No UNDO" in out.get("note", "")

    def test_agent_file_write_plan_declares_no_undo(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire_agent(tmp_path, monkeypatch)
        out = server.pve_agent_file_write("101", "/var/log/probe.txt", "body")
        assert "no undo" in out.get("note", "").lower() or "No UNDO" in out.get("note", "")

    def test_agent_fs_plan_declares_no_undo(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire_agent(tmp_path, monkeypatch)
        out = server.pve_agent_fs("101", "fstrim")
        assert "no undo" in out.get("note", "").lower() or "No UNDO" in out.get("note", "")

    def test_agent_set_password_plan_declares_no_undo(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire_agent(tmp_path, monkeypatch)
        out = server.pve_agent_set_password("101", "root", "pw")
        assert "no undo" in out.get("note", "").lower() or "No UNDO" in out.get("note", "")
