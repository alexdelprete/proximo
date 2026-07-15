"""TDD tests for the PMG APT plane (Wave 1b, 2026-07-15 full-surface campaign).

Mirrors tests/test_apt.py's scope for PVE, adjusted per plane:
- pmg.py's ops are module-level functions taking `api` first and `node` as a REQUIRED param
  (not `node: str | None = None`) and call the generic `api._get/_post/_put` verbs — mirrors
  the rest of pmg.py (node_status, postfix_flush, ...). Node defaulting ("node or cfg.node")
  happens at the server-wrapper level only, same as every other pmg_* tool.
- PMG's apt validators mirror PVE's exactly (permissive digest/handle) — unlike PBS's stricter
  sha256-digest / lowercase-handle patterns.

Covers:
- Validators: _check_pmg_apt_package_name, _check_pmg_apt_repo_path, _check_pmg_apt_index,
  _check_pmg_apt_handle, _check_pmg_apt_digest
- Op functions: URL/param shape via a recording fake
- Plan factories: correct action/target/risk/blast wording for all 3 mutation plans
- CAPTURE-or-declare: repository_set/repository_add capture current state; complete=False only
  when the read itself raises (a successful-but-empty read degrades to current={}, not failure)
- Server-wrapper mutation gating (via server._pmg / server._svc monkeypatch, mirroring
  tests/test_server_pmg_wiring.py's `_wire()` idiom): plan-by-default; confirm=True executes
- Read tools: updates_list, changelog, repositories_get, versions return the expected shape
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.backends import ProximoError
from proximo.config import ProximoConfig
from proximo.pmg import (
    _check_pmg_apt_digest,
    _check_pmg_apt_handle,
    _check_pmg_apt_index,
    _check_pmg_apt_package_name,
    _check_pmg_apt_repo_path,
    apt_changelog,
    apt_repositories_get,
    apt_repository_add,
    apt_repository_set,
    apt_update_refresh,
    apt_updates_list,
    apt_versions,
    plan_apt_repository_add,
    plan_apt_repository_set,
    plan_apt_update_refresh,
)

# ─── _api() — recording fake ───────────────────────────────────────────────────


def _api() -> SimpleNamespace:
    seen: dict = {}

    def fake_get(path, params=None):
        seen["method"] = "GET"
        seen["path"] = path
        seen["params"] = params or {}
        return []

    def fake_post(path, data=None):
        seen["method"] = "POST"
        seen["path"] = path
        seen["data"] = data or {}
        return "task-id-sentinel"

    def fake_put(path, data=None):
        seen["method"] = "PUT"
        seen["path"] = path
        seen["data"] = data or {}
        return None

    return SimpleNamespace(_get=fake_get, _post=fake_post, _put=fake_put, seen=seen)


class _FakeAptApi:
    """Fake PmgBackend returning canned apt-repositories data for CAPTURE tests."""

    def __init__(self, *, repos_result=None, raise_repos=False):
        self._repos_result = repos_result if repos_result is not None else {
            "files": [{"path": "/etc/apt/sources.list", "digest": "d1",
                       "repositories": [{"Enabled": True}]}],
            "standard-repos": [{"handle": "no-subscription", "status": True}],
        }
        self._raise_repos = raise_repos
        self.gets: list = []
        self.posts: list = []
        self.puts: list = []

    def _get(self, path, params=None):
        self.gets.append((path, params))
        if self._raise_repos:
            raise RuntimeError("cannot read repositories")
        return dict(self._repos_result)

    def _post(self, path, data=None):
        self.posts.append((path, data))
        return "task-id-sentinel"

    def _put(self, path, data=None):
        self.puts.append((path, data))
        return None


# ─── Validators ────────────────────────────────────────────────────────────────


class TestCheckPmgAptPackageName:
    def test_valid_names(self):
        assert _check_pmg_apt_package_name("pve-manager") == "pve-manager"
        assert _check_pmg_apt_package_name("libc6") == "libc6"

    def test_rejects_uppercase(self):
        with pytest.raises(ProximoError, match="invalid package name"):
            _check_pmg_apt_package_name("PveManager")

    def test_rejects_single_char(self):
        with pytest.raises(ProximoError, match="invalid package name"):
            _check_pmg_apt_package_name("a")

    def test_rejects_trailing_newline(self):
        with pytest.raises(ProximoError, match="invalid package name"):
            _check_pmg_apt_package_name("pve-manager\n")


class TestCheckPmgAptRepoPath:
    def test_valid_path(self):
        assert _check_pmg_apt_repo_path("/etc/apt/sources.list") == "/etc/apt/sources.list"

    def test_rejects_relative_path(self):
        with pytest.raises(ProximoError, match="invalid repository file path"):
            _check_pmg_apt_repo_path("etc/apt/sources.list")

    def test_rejects_traversal(self):
        with pytest.raises(ProximoError, match="path traversal"):
            _check_pmg_apt_repo_path("/etc/apt/../shadow")

    def test_rejects_control_chars(self):
        with pytest.raises(ProximoError, match="invalid repository file path"):
            _check_pmg_apt_repo_path("/etc/apt/sources.list\n")


class TestCheckPmgAptIndex:
    def test_valid_index(self):
        assert _check_pmg_apt_index(0) == 0
        assert _check_pmg_apt_index(5) == 5

    def test_rejects_negative(self):
        with pytest.raises(ProximoError, match="invalid repository index"):
            _check_pmg_apt_index(-1)

    def test_rejects_non_int(self):
        with pytest.raises(ProximoError, match="invalid repository index"):
            _check_pmg_apt_index("0")

    def test_rejects_bool(self):
        with pytest.raises(ProximoError, match="invalid repository index"):
            _check_pmg_apt_index(True)


class TestCheckPmgAptHandle:
    def test_valid_handle(self):
        assert _check_pmg_apt_handle("no-subscription") == "no-subscription"

    def test_rejects_leading_hyphen(self):
        with pytest.raises(ProximoError, match="invalid repository handle"):
            _check_pmg_apt_handle("-no-subscription")

    def test_rejects_underscore(self):
        with pytest.raises(ProximoError, match="invalid repository handle"):
            _check_pmg_apt_handle("no_subscription")


class TestCheckPmgAptDigest:
    def test_none_passes_through(self):
        assert _check_pmg_apt_digest(None) is None

    def test_valid_hex(self):
        assert _check_pmg_apt_digest("abc123") == "abc123"

    def test_rejects_non_hex(self):
        with pytest.raises(ProximoError, match="invalid digest"):
            _check_pmg_apt_digest("not-hex!")

    def test_rejects_too_long(self):
        with pytest.raises(ProximoError, match="invalid digest"):
            _check_pmg_apt_digest("a" * 81)


# ─── Op functions — URL/param shape ────────────────────────────────────────────


class TestAptUpdatesList:
    def test_path(self):
        api = _api()
        apt_updates_list(api, node="pmg1")
        assert api.seen["path"] == "/nodes/pmg1/apt/update"
        assert api.seen["method"] == "GET"

    def test_returns_list(self):
        api = _api()
        result = apt_updates_list(api, "pmg1")
        assert isinstance(result, list)


class TestAptChangelog:
    def test_params_include_name(self):
        api = _api()
        apt_changelog(api, "pve-manager", "pmg1")
        assert api.seen["path"] == "/nodes/pmg1/apt/changelog"
        assert api.seen["params"]["name"] == "pve-manager"
        assert "version" not in api.seen["params"]

    def test_version_forwarded_when_given(self):
        api = _api()
        apt_changelog(api, "pve-manager", "pmg1", version="8.0-1")
        assert api.seen["params"]["version"] == "8.0-1"

    def test_returns_str(self):
        api = _api()
        api._get = lambda path, params=None: "changelog text"
        result = apt_changelog(api, "pve-manager", "pmg1")
        assert result == "changelog text"

    def test_invalid_name_raises(self):
        api = _api()
        with pytest.raises(ProximoError):
            apt_changelog(api, "BadName", "pmg1")


class TestAptRepositoriesGet:
    def test_uses_correct_path(self):
        api = _api()
        apt_repositories_get(api, "pmg1")
        assert api.seen["path"] == "/nodes/pmg1/apt/repositories"
        assert api.seen["method"] == "GET"

    def test_returns_dict(self):
        api = _api()
        api._get = lambda path, params=None: {}
        result = apt_repositories_get(api, "pmg1")
        assert isinstance(result, dict)


class TestAptVersions:
    def test_uses_correct_path(self):
        api = _api()
        apt_versions(api, "pmg1")
        assert api.seen["path"] == "/nodes/pmg1/apt/versions"

    def test_returns_list(self):
        api = _api()
        result = apt_versions(api, "pmg1")
        assert isinstance(result, list)


class TestAptUpdateRefresh:
    def test_post_path(self):
        api = _api()
        apt_update_refresh(api, "pmg1")
        assert api.seen["path"] == "/nodes/pmg1/apt/update"
        assert api.seen["method"] == "POST"

    def test_notify_quiet_forwarded(self):
        api = _api()
        apt_update_refresh(api, "pmg1", notify=True, quiet=False)
        assert api.seen["data"] == {"notify": True, "quiet": False}

    def test_omits_unset_params(self):
        api = _api()
        apt_update_refresh(api, "pmg1")
        assert api.seen["data"] == {}


class TestAptRepositorySet:
    def test_post_path_and_body(self):
        api = _api()
        apt_repository_set(api, "/etc/apt/sources.list", 0, "pmg1", enabled=False, digest="ab" * 20)
        assert api.seen["path"] == "/nodes/pmg1/apt/repositories"
        assert api.seen["method"] == "POST"
        assert api.seen["data"] == {
            "path": "/etc/apt/sources.list", "index": 0, "enabled": False, "digest": "ab" * 20,
        }

    def test_omits_unset_optional_fields(self):
        api = _api()
        apt_repository_set(api, "/etc/apt/sources.list", 0, "pmg1")
        assert api.seen["data"] == {"path": "/etc/apt/sources.list", "index": 0}

    def test_invalid_digest_raises(self):
        api = _api()
        with pytest.raises(ProximoError):
            apt_repository_set(api, "/etc/apt/sources.list", 0, "pmg1", digest="not-hex!")


class TestAptRepositoryAdd:
    def test_put_path_and_body(self):
        api = _api()
        apt_repository_add(api, "no-subscription", "pmg1", digest="cd" * 20)
        assert api.seen["path"] == "/nodes/pmg1/apt/repositories"
        assert api.seen["method"] == "PUT"
        assert api.seen["data"] == {"handle": "no-subscription", "digest": "cd" * 20}

    def test_omits_unset_digest(self):
        api = _api()
        apt_repository_add(api, "no-subscription", "pmg1")
        assert api.seen["data"] == {"handle": "no-subscription"}

    def test_invalid_handle_raises(self):
        api = _api()
        with pytest.raises(ProximoError):
            apt_repository_add(api, "bad handle!", "pmg1")


# ─── Plan factories ─────────────────────────────────────────────────────────────


class TestUpdateRefreshPlan:
    def test_risk_low(self):
        p = plan_apt_update_refresh("pmg1")
        assert p.risk == "low"

    def test_action(self):
        p = plan_apt_update_refresh("pmg1")
        assert p.action == "pmg_apt_update_refresh"

    def test_no_upgrade_execution_honesty(self):
        p = plan_apt_update_refresh("pmg1")
        combined = " ".join(p.blast_radius) + p.change
        assert "does not" in combined.lower()
        assert "console" in combined.lower()

    def test_idempotent_in_note(self):
        p = plan_apt_update_refresh("pmg1")
        assert "idempotent" in p.note.lower() or "re-run" in p.note.lower()


class TestRepositorySetPlan:
    def test_risk_medium(self):
        api = _FakeAptApi()
        p = plan_apt_repository_set(api, "/etc/apt/sources.list", 0, "pmg1")
        assert p.risk == "medium"

    def test_captures_current_entry(self):
        api = _FakeAptApi()
        p = plan_apt_repository_set(api, "/etc/apt/sources.list", 0, "pmg1")
        assert p.complete is True
        assert p.current.get("entry") == {"Enabled": True}

    def test_no_match_degrades_to_empty_not_failure(self):
        api = _FakeAptApi()
        p = plan_apt_repository_set(api, "/etc/apt/sources.list.d/other.list", 3, "pmg1")
        assert p.complete is True
        assert p.current == {}

    def test_complete_false_when_read_raises(self):
        api = _FakeAptApi(raise_repos=True)
        p = plan_apt_repository_set(api, "/etc/apt/sources.list", 0, "pmg1")
        assert p.complete is False
        assert "could not capture" in p.note.lower()

    def test_path_and_index_in_target(self):
        api = _FakeAptApi()
        p = plan_apt_repository_set(api, "/etc/apt/sources.list", 2, "pmg1")
        assert "/etc/apt/sources.list" in p.target
        assert "2" in p.target

    def test_invalid_path_raises(self):
        api = _FakeAptApi()
        with pytest.raises(ProximoError):
            plan_apt_repository_set(api, "relative/path", 0, "pmg1")

    def test_invalid_digest_raises(self):
        api = _FakeAptApi()
        with pytest.raises(ProximoError):
            plan_apt_repository_set(api, "/etc/apt/sources.list", 0, "pmg1", digest="not-hex!")


class TestRepositoryAddPlan:
    def test_risk_medium(self):
        api = _FakeAptApi()
        p = plan_apt_repository_add(api, "no-subscription", "pmg1")
        assert p.risk == "medium"

    def test_captures_current_status(self):
        api = _FakeAptApi()
        p = plan_apt_repository_add(api, "no-subscription", "pmg1")
        assert p.complete is True
        assert p.current.get("handle") == "no-subscription"

    def test_no_match_degrades_to_empty_not_failure(self):
        api = _FakeAptApi()
        p = plan_apt_repository_add(api, "brand-new-handle", "pmg1")
        assert p.complete is True
        assert p.current == {}

    def test_complete_false_when_read_raises(self):
        api = _FakeAptApi(raise_repos=True)
        p = plan_apt_repository_add(api, "no-subscription", "pmg1")
        assert p.complete is False
        assert "could not capture" in p.note.lower()

    def test_handle_in_target(self):
        api = _FakeAptApi()
        p = plan_apt_repository_add(api, "no-subscription", "pmg1")
        assert "no-subscription" in p.target

    def test_no_automatic_revert_in_note(self):
        api = _FakeAptApi()
        p = plan_apt_repository_add(api, "no-subscription", "pmg1")
        assert "no automatic revert" in p.note.lower()

    def test_invalid_handle_raises(self):
        api = _FakeAptApi()
        with pytest.raises(ProximoError):
            plan_apt_repository_add(api, "bad handle!", "pmg1")


# ─── Server-wrapper mutation gating (mirrors test_server_pmg_wiring.py's `_wire()` idiom) ─────


def _wire(tmp_path, monkeypatch):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log,
    )
    api = SimpleNamespace(config=SimpleNamespace(node="pve"))
    pmg = _FakeAptApi()
    exec_ = SimpleNamespace()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, exec_, ledger))
    monkeypatch.setattr(server, "_pmg", lambda: (SimpleNamespace(node="pmg"), pmg))
    return cfg, pmg, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class TestMutationGating:
    def test_update_refresh_plan_by_default(self, tmp_path, monkeypatch):
        _, pmg, _, log = _wire(tmp_path, monkeypatch)
        out = server.pmg_apt_update_refresh()
        assert out["status"] == "plan"
        assert pmg.posts == []
        assert any(e["outcome"] == "planned" for e in _entries(log))

    def test_update_refresh_confirm_executes(self, tmp_path, monkeypatch):
        _, pmg, _, log = _wire(tmp_path, monkeypatch)
        out = server.pmg_apt_update_refresh(confirm=True)
        assert out["status"] == "submitted"
        assert len(pmg.posts) == 1
        outcomes = {e["outcome"] for e in _entries(log) if e["action"] == "pmg_apt_update_refresh"}
        assert {"planned", "submitted"} <= outcomes

    def test_update_refresh_sync_reports_ok(self, tmp_path, monkeypatch):
        _, pmg, _, _ = _wire(tmp_path, monkeypatch)
        monkeypatch.setattr(pmg, "_post", lambda path, data=None: None)
        out = server.pmg_apt_update_refresh(confirm=True)
        assert out["status"] == "ok"
        assert out["result"] is None

    def test_repository_set_plan_by_default(self, tmp_path, monkeypatch):
        _, pmg, _, _ = _wire(tmp_path, monkeypatch)
        out = server.pmg_apt_repository_set("/etc/apt/sources.list", 0)
        assert out["status"] == "plan"
        assert pmg.posts == []

    def test_repository_set_confirm_executes(self, tmp_path, monkeypatch):
        _, pmg, _, log = _wire(tmp_path, monkeypatch)
        out = server.pmg_apt_repository_set(
            "/etc/apt/sources.list", 0, enabled=False, confirm=True,
        )
        assert out["status"] == "ok"
        assert pmg.posts[-1] == (
            "/nodes/pmg/apt/repositories",
            {"path": "/etc/apt/sources.list", "index": 0, "enabled": False},
        )
        entry = [e for e in _entries(log) if e["action"] == "pmg_apt_repository_set"
                 and e["outcome"] == "ok"][0]
        assert entry["mutation"] is True
        assert entry["detail"]["confirmed"] is True

    def test_repository_add_plan_by_default(self, tmp_path, monkeypatch):
        _, pmg, _, _ = _wire(tmp_path, monkeypatch)
        out = server.pmg_apt_repository_add("no-subscription")
        assert out["status"] == "plan"
        assert pmg.puts == []

    def test_repository_add_confirm_executes(self, tmp_path, monkeypatch):
        _, pmg, _, log = _wire(tmp_path, monkeypatch)
        out = server.pmg_apt_repository_add("no-subscription", confirm=True)
        assert out["status"] == "ok"
        assert pmg.puts[-1] == ("/nodes/pmg/apt/repositories", {"handle": "no-subscription"})
        entry = [e for e in _entries(log) if e["action"] == "pmg_apt_repository_add"
                 and e["outcome"] == "ok"][0]
        assert entry["mutation"] is True
        assert entry["detail"]["confirmed"] is True

    def test_node_override_forwards(self, tmp_path, monkeypatch):
        """node=None defaults to cfg.node ("pmg"); an explicit node overrides it."""
        _, pmg, _, _ = _wire(tmp_path, monkeypatch)
        server.pmg_apt_repository_add("no-subscription", node="other-node", confirm=True)
        assert pmg.puts[-1][0] == "/nodes/other-node/apt/repositories"


def test_one_shot_confirm_records_plan_before_executing(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(tmp_path, monkeypatch)
    server.pmg_apt_repository_add("no-subscription", confirm=True)
    outcomes = {e["outcome"] for e in _entries(log) if e["action"] == "pmg_apt_repository_add"}
    assert "planned" in outcomes, "one-shot confirm must record a plan entry before executing"
    assert "ok" in outcomes


class TestReadTools:
    def test_updates_list_returns_list(self, tmp_path, monkeypatch):
        _, pmg, _, _ = _wire(tmp_path, monkeypatch)
        monkeypatch.setattr(pmg, "_get", lambda path, params=None: [])
        result = server.pmg_apt_updates_list()
        assert isinstance(result, list)

    def test_changelog_returns_str(self, tmp_path, monkeypatch):
        _, pmg, _, _ = _wire(tmp_path, monkeypatch)
        monkeypatch.setattr(pmg, "_get", lambda path, params=None: "changelog text")
        result = server.pmg_apt_changelog("pve-manager")
        assert isinstance(result, str)

    def test_repositories_get_returns_dict(self, tmp_path, monkeypatch):
        _wire(tmp_path, monkeypatch)
        result = server.pmg_apt_repositories_get()
        assert isinstance(result, dict)

    def test_versions_returns_list(self, tmp_path, monkeypatch):
        _, pmg, _, _ = _wire(tmp_path, monkeypatch)
        monkeypatch.setattr(pmg, "_get", lambda path, params=None: [])
        result = server.pmg_apt_versions()
        assert isinstance(result, list)
