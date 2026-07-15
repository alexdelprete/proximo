"""TDD tests for the PVE APT plane (Wave 1a, 2026-07-15 full-surface campaign).

Covers:
- Validators: _check_apt_package_name, _check_apt_repo_path, _check_apt_index,
  _check_apt_handle, _check_apt_digest
- Plan factories: correct action/target/risk/blast wording for all 3 mutation plans
- CAPTURE-or-declare: repository_set/repository_add capture current state; complete=False only
  when the read itself raises (a successful-but-empty read degrades to current={}, not failure)
- Mutation gating: plan-by-default (no confirm -> status=="plan"); confirm=True executes
- Read tools: updates_list, changelog, repositories_get, versions return the expected shape
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.apt import (
    plan_apt_repository_add,
    plan_apt_repository_set,
    plan_apt_update_refresh,
)
from proximo.audit import AuditLedger
from proximo.backends import ProximoError
from proximo.config import ProximoConfig

# ─── Helpers ───────────────────────────────────────────────────────────────────


def _make_cfg(log_path: str | None = None) -> ProximoConfig:
    return ProximoConfig(
        api_base_url="https://fake:8006/api2/json",
        node="pve",
        token_path="/dev/null",
        enable_agent=False,
        agent_allowlist=frozenset(),
        enable_exec=False,
        ct_allowlist=frozenset(),
        audit_log_path=log_path or "/dev/null",
        redact_ledger=False,
    )


class _FakeAptApi:
    """Fake ApiBackend that records apt-plane calls and returns canned responses."""

    def __init__(
        self,
        *,
        updates_result=None,
        changelog_result="changelog text",
        repos_result=None,
        versions_result=None,
        raise_repos=False,
    ):
        self.config = SimpleNamespace(node="pve")
        self.update_refreshes: list = []
        self.repository_sets: list = []
        self.repository_adds: list = []
        self._updates_result = updates_result or [{"Package": "pve-manager"}]
        self._changelog_result = changelog_result
        self._repos_result = repos_result if repos_result is not None else {
            "files": [{"path": "/etc/apt/sources.list", "digest": "d1",
                       "repositories": [{"Enabled": 1}]}],
            "standard-repos": [{"handle": "no-subscription", "status": True}],
            "digest": "top-digest",
        }
        self._versions_result = versions_result or [{"Package": "pve-manager", "Version": "9.0"}]
        self._raise_repos = raise_repos

    # --- reads ---
    def apt_updates_list(self, node=None):
        return list(self._updates_result)

    def apt_changelog(self, name, node=None, version=None):
        return self._changelog_result

    def apt_repositories_get(self, node=None):
        if self._raise_repos:
            raise RuntimeError("cannot read repositories")
        return dict(self._repos_result)

    def apt_versions(self, node=None):
        return list(self._versions_result)

    # --- mutations ---
    def apt_update_refresh(self, node=None, notify=None, quiet=None):
        self.update_refreshes.append((node, notify, quiet))
        return "UPID:apt-update"

    def apt_repository_set(self, path, index, node=None, enabled=None, digest=None):
        self.repository_sets.append((path, index, node, enabled, digest))

    def apt_repository_add(self, handle, node=None, digest=None):
        self.repository_adds.append((handle, node, digest))


class _FakeExec:
    pass


def _wire_apt(tmp_path, monkeypatch, *, api=None, **api_kw):
    log = str(tmp_path / "audit.log")
    cfg = _make_cfg(log_path=log)
    apt_api = api if api is not None else _FakeAptApi(**api_kw)
    exec_ = _FakeExec()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, apt_api, exec_, ledger))
    return cfg, apt_api, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ─── Validators ────────────────────────────────────────────────────────────────


class TestCheckAptPackageName:
    def test_valid_names(self):
        from proximo.backends import _check_apt_package_name
        assert _check_apt_package_name("pve-manager") == "pve-manager"
        assert _check_apt_package_name("libc6") == "libc6"

    def test_rejects_uppercase(self):
        from proximo.backends import _check_apt_package_name
        with pytest.raises(ProximoError, match="invalid package name"):
            _check_apt_package_name("PveManager")

    def test_rejects_single_char(self):
        from proximo.backends import _check_apt_package_name
        with pytest.raises(ProximoError, match="invalid package name"):
            _check_apt_package_name("a")

    def test_rejects_trailing_newline(self):
        from proximo.backends import _check_apt_package_name
        with pytest.raises(ProximoError, match="invalid package name"):
            _check_apt_package_name("pve-manager\n")


class TestCheckAptRepoPath:
    def test_valid_path(self):
        from proximo.backends import _check_apt_repo_path
        assert _check_apt_repo_path("/etc/apt/sources.list") == "/etc/apt/sources.list"

    def test_rejects_relative_path(self):
        from proximo.backends import _check_apt_repo_path
        with pytest.raises(ProximoError, match="invalid repository file path"):
            _check_apt_repo_path("etc/apt/sources.list")

    def test_rejects_traversal(self):
        from proximo.backends import _check_apt_repo_path
        with pytest.raises(ProximoError, match="path traversal"):
            _check_apt_repo_path("/etc/apt/../shadow")

    def test_rejects_control_chars(self):
        from proximo.backends import _check_apt_repo_path
        with pytest.raises(ProximoError, match="invalid repository file path"):
            _check_apt_repo_path("/etc/apt/sources.list\n")


class TestCheckAptIndex:
    def test_valid_index(self):
        from proximo.backends import _check_apt_index
        assert _check_apt_index(0) == 0
        assert _check_apt_index(5) == 5

    def test_rejects_negative(self):
        from proximo.backends import _check_apt_index
        with pytest.raises(ProximoError, match="invalid repository index"):
            _check_apt_index(-1)

    def test_rejects_non_int(self):
        from proximo.backends import _check_apt_index
        with pytest.raises(ProximoError, match="invalid repository index"):
            _check_apt_index("0")

    def test_rejects_bool(self):
        # bool is a subclass of int in Python — must be explicitly rejected.
        from proximo.backends import _check_apt_index
        with pytest.raises(ProximoError, match="invalid repository index"):
            _check_apt_index(True)


class TestCheckAptHandle:
    def test_valid_handle(self):
        from proximo.backends import _check_apt_handle
        assert _check_apt_handle("no-subscription") == "no-subscription"

    def test_rejects_leading_hyphen(self):
        from proximo.backends import _check_apt_handle
        with pytest.raises(ProximoError, match="invalid repository handle"):
            _check_apt_handle("-no-subscription")

    def test_rejects_underscore(self):
        from proximo.backends import _check_apt_handle
        with pytest.raises(ProximoError, match="invalid repository handle"):
            _check_apt_handle("no_subscription")


class TestCheckAptDigest:
    def test_none_passes_through(self):
        from proximo.backends import _check_apt_digest
        assert _check_apt_digest(None) is None

    def test_valid_hex(self):
        from proximo.backends import _check_apt_digest
        assert _check_apt_digest("abc123") == "abc123"

    def test_rejects_non_hex(self):
        from proximo.backends import _check_apt_digest
        with pytest.raises(ProximoError, match="invalid digest"):
            _check_apt_digest("not-hex!")

    def test_rejects_too_long(self):
        from proximo.backends import _check_apt_digest
        with pytest.raises(ProximoError, match="invalid digest"):
            _check_apt_digest("a" * 81)


# ─── Plan factories ─────────────────────────────────────────────────────────────


class TestUpdateRefreshPlan:
    def test_risk_low(self):
        p = plan_apt_update_refresh()
        assert p.risk == "low"

    def test_action(self):
        p = plan_apt_update_refresh()
        assert p.action == "pve_apt_update_refresh"

    def test_no_upgrade_execution_honesty(self):
        p = plan_apt_update_refresh()
        combined = " ".join(p.blast_radius) + p.change
        assert "does not" in combined.lower() or "does not" in p.blast_radius[0].lower()
        assert "console" in combined.lower()

    def test_idempotent_in_note(self):
        p = plan_apt_update_refresh()
        assert "idempotent" in p.note.lower() or "re-run" in p.note.lower()


class TestRepositorySetPlan:
    def test_risk_medium(self):
        api = _FakeAptApi()
        p = plan_apt_repository_set(api, "/etc/apt/sources.list", 0)
        assert p.risk == "medium"

    def test_captures_current_entry(self):
        api = _FakeAptApi()
        p = plan_apt_repository_set(api, "/etc/apt/sources.list", 0)
        assert p.complete is True
        assert p.current.get("entry") == {"Enabled": 1}

    def test_no_match_degrades_to_empty_not_failure(self):
        """A successful read that finds no matching path/index is NOT a capture failure."""
        api = _FakeAptApi()
        p = plan_apt_repository_set(api, "/etc/apt/sources.list.d/other.list", 3)
        assert p.complete is True
        assert p.current == {}

    def test_complete_false_when_read_raises(self):
        api = _FakeAptApi(raise_repos=True)
        p = plan_apt_repository_set(api, "/etc/apt/sources.list", 0)
        assert p.complete is False
        assert "could not capture" in p.note.lower()

    def test_path_and_index_in_target(self):
        api = _FakeAptApi()
        p = plan_apt_repository_set(api, "/etc/apt/sources.list", 2)
        assert "/etc/apt/sources.list" in p.target
        assert "2" in p.target

    def test_invalid_path_raises(self):
        api = _FakeAptApi()
        with pytest.raises(ProximoError):
            plan_apt_repository_set(api, "relative/path", 0)

    def test_invalid_digest_raises(self):
        api = _FakeAptApi()
        with pytest.raises(ProximoError):
            plan_apt_repository_set(api, "/etc/apt/sources.list", 0, digest="not-hex!")


class TestRepositoryAddPlan:
    def test_risk_medium(self):
        api = _FakeAptApi()
        p = plan_apt_repository_add(api, "no-subscription")
        assert p.risk == "medium"

    def test_captures_current_status(self):
        api = _FakeAptApi()
        p = plan_apt_repository_add(api, "no-subscription")
        assert p.complete is True
        assert p.current.get("handle") == "no-subscription"

    def test_no_match_degrades_to_empty_not_failure(self):
        api = _FakeAptApi()
        p = plan_apt_repository_add(api, "brand-new-handle")
        assert p.complete is True
        assert p.current == {}

    def test_complete_false_when_read_raises(self):
        api = _FakeAptApi(raise_repos=True)
        p = plan_apt_repository_add(api, "no-subscription")
        assert p.complete is False
        assert "could not capture" in p.note.lower()

    def test_handle_in_target(self):
        api = _FakeAptApi()
        p = plan_apt_repository_add(api, "no-subscription")
        assert "no-subscription" in p.target

    def test_no_automatic_revert_in_note(self):
        api = _FakeAptApi()
        p = plan_apt_repository_add(api, "no-subscription")
        assert "no automatic revert" in p.note.lower()

    def test_invalid_handle_raises(self):
        api = _FakeAptApi()
        with pytest.raises(ProximoError):
            plan_apt_repository_add(api, "bad handle!")


# ─── Mutation gating ──────────────────────────────────────────────────────────


class TestMutationGating:
    def test_update_refresh_plan_by_default(self, tmp_path, monkeypatch):
        _, api, log = _wire_apt(tmp_path, monkeypatch)
        out = server.pve_apt_update_refresh()
        assert out["status"] == "plan"
        assert api.update_refreshes == []
        assert any(e["outcome"] == "planned" for e in _entries(log))

    def test_update_refresh_confirm_executes(self, tmp_path, monkeypatch):
        _, api, log = _wire_apt(tmp_path, monkeypatch)
        out = server.pve_apt_update_refresh(confirm=True)
        assert out["status"] == "submitted"
        assert len(api.update_refreshes) == 1
        outcomes = {e["outcome"] for e in _entries(log) if e["action"] == "pve_apt_update_refresh"}
        assert {"planned", "submitted"} <= outcomes

    def test_update_refresh_sync_reports_ok(self, tmp_path, monkeypatch):
        _, api, _ = _wire_apt(tmp_path, monkeypatch)
        monkeypatch.setattr(api, "apt_update_refresh", lambda node=None, notify=None, quiet=None: None)
        out = server.pve_apt_update_refresh(confirm=True)
        assert out["status"] == "ok"
        assert out["result"] is None

    def test_repository_set_plan_by_default(self, tmp_path, monkeypatch):
        _, api, _ = _wire_apt(tmp_path, monkeypatch)
        out = server.pve_apt_repository_set("/etc/apt/sources.list", 0)
        assert out["status"] == "plan"
        assert api.repository_sets == []

    def test_repository_set_confirm_executes(self, tmp_path, monkeypatch):
        _, api, log = _wire_apt(tmp_path, monkeypatch)
        out = server.pve_apt_repository_set("/etc/apt/sources.list", 0, enabled=False, confirm=True)
        assert out["status"] == "ok"
        assert api.repository_sets == [("/etc/apt/sources.list", 0, None, False, None)]
        entry = [e for e in _entries(log) if e["action"] == "pve_apt_repository_set"
                 and e["outcome"] == "ok"][0]
        assert entry["mutation"] is True
        assert entry["detail"]["confirmed"] is True

    def test_repository_add_plan_by_default(self, tmp_path, monkeypatch):
        _, api, _ = _wire_apt(tmp_path, monkeypatch)
        out = server.pve_apt_repository_add("no-subscription")
        assert out["status"] == "plan"
        assert api.repository_adds == []

    def test_repository_add_confirm_executes(self, tmp_path, monkeypatch):
        _, api, log = _wire_apt(tmp_path, monkeypatch)
        out = server.pve_apt_repository_add("no-subscription", confirm=True)
        assert out["status"] == "ok"
        assert api.repository_adds == [("no-subscription", None, None)]
        entry = [e for e in _entries(log) if e["action"] == "pve_apt_repository_add"
                 and e["outcome"] == "ok"][0]
        assert entry["mutation"] is True
        assert entry["detail"]["confirmed"] is True


def test_one_shot_confirm_records_plan_before_executing(tmp_path, monkeypatch):
    _, api, log = _wire_apt(tmp_path, monkeypatch)
    server.pve_apt_repository_add("no-subscription", confirm=True)
    outcomes = {e["outcome"] for e in _entries(log) if e["action"] == "pve_apt_repository_add"}
    assert "planned" in outcomes, "one-shot confirm must record a plan entry before executing"
    assert "ok" in outcomes


# ─── Read tools ───────────────────────────────────────────────────────────────


class TestReadTools:
    def test_updates_list_returns_list(self, tmp_path, monkeypatch):
        _wire_apt(tmp_path, monkeypatch)
        result = server.pve_apt_updates_list()
        assert isinstance(result, list)

    def test_changelog_returns_str(self, tmp_path, monkeypatch):
        _wire_apt(tmp_path, monkeypatch)
        result = server.pve_apt_changelog("pve-manager")
        assert isinstance(result, str)

    def test_repositories_get_returns_dict(self, tmp_path, monkeypatch):
        _wire_apt(tmp_path, monkeypatch)
        result = server.pve_apt_repositories_get()
        assert isinstance(result, dict)

    def test_versions_returns_list(self, tmp_path, monkeypatch):
        _wire_apt(tmp_path, monkeypatch)
        result = server.pve_apt_versions()
        assert isinstance(result, list)
