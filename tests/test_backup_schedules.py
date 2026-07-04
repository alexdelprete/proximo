"""Tests for backup_schedules.py — validators, operations, and plan factories.

Mirrors test_pbs.py style:
  - _Api / _Pbs: recording fakes for ApiBackend / PbsBackend (no live network).
  - Validator tests: prove \\Z-anchored rejections (trailing newline, slash, bad type).
  - Operation tests: prove correct HTTP verb + path; result passthrough.
  - Plan tests: prove honest risk, correct current capture, no implied undo.
"""

from __future__ import annotations

import pytest

from proximo.backends import ProximoError
from proximo.backup_schedules import (
    _check_job_id,
    _check_pbs_job_id,
    _check_pbs_job_type,
    _check_realm,
    _check_replication_id,
    backup_job_create,
    backup_job_delete,
    backup_job_get,
    backup_job_list,
    backup_job_update,
    pbs_realm_sync,
    pbs_scheduled_job_create,
    pbs_scheduled_job_delete,
    pbs_scheduled_job_get,
    pbs_scheduled_job_run,
    pbs_scheduled_job_update,
    pbs_scheduled_jobs_list,
    plan_backup_job_create,
    plan_backup_job_delete,
    plan_backup_job_update,
    plan_pbs_job_create,
    plan_pbs_job_delete,
    plan_pbs_job_run,
    plan_pbs_job_update,
    plan_pbs_realm_sync,
    plan_replication_create,
    plan_replication_delete,
    plan_replication_update,
    replication_create,
    replication_delete,
    replication_get,
    replication_update,
)
from proximo.planning import RISK_LOW, RISK_MEDIUM

# ---------------------------------------------------------------------------
# Recording fakes
# ---------------------------------------------------------------------------

class _Api:
    """Recording fake for ApiBackend (HTTP verb tracking, no live network)."""

    def __init__(self, get_return=None):
        self._get_return = get_return if get_return is not None else {}
        self.gets: list[str] = []
        self.posts: list[tuple] = []
        self.puts: list[tuple] = []
        self.dels: list[tuple] = []

    def _get(self, path: str):
        self.gets.append(path)
        return self._get_return

    def _post(self, path: str, data=None):
        self.posts.append((path, data))
        return None

    def _put(self, path: str, data=None):
        self.puts.append((path, data))
        return None

    def _delete(self, path: str, params=None):
        self.dels.append((path, params))
        return None


class _Pbs:
    """Recording fake for PbsBackend (no live PBS required)."""

    def __init__(self, get_return=None):
        self._get_return = get_return if get_return is not None else {}
        self.gets: list[str] = []
        self.posts: list[tuple] = []
        self.puts: list[tuple] = []
        self.dels: list[tuple] = []

    def _get(self, path: str, params=None):
        self.gets.append(path)
        return self._get_return

    def _post(self, path: str, data=None):
        self.posts.append((path, data))
        return "UPID:pbs:post"

    def _put(self, path: str, data=None):
        self.puts.append((path, data))
        return None

    def _delete(self, path: str, params=None):
        self.dels.append((path, params))
        return None


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

class TestCheckJobId:
    def test_valid_simple(self):
        assert _check_job_id("daily") == "daily"

    def test_valid_with_hyphen_underscore(self):
        assert _check_job_id("daily-backup_v2") == "daily-backup_v2"

    def test_empty_raises(self):
        with pytest.raises(ProximoError, match="invalid PVE backup job ID"):
            _check_job_id("")

    def test_slash_raises(self):
        with pytest.raises(ProximoError):
            _check_job_id("job/path")

    def test_trailing_newline_raises(self):
        """\\Z anchoring: a trailing newline must not slip through."""
        with pytest.raises(ProximoError):
            _check_job_id("daily\n")

    def test_control_char_raises(self):
        with pytest.raises(ProximoError):
            _check_job_id("daily\x00")


class TestCheckReplicationId:
    def test_valid_vmid_slot(self):
        assert _check_replication_id("101/0") == "101/0"

    def test_valid_numeric(self):
        assert _check_replication_id("101") == "101"

    def test_trailing_newline_raises(self):
        with pytest.raises(ProximoError):
            _check_replication_id("101/0\n")

    def test_empty_raises(self):
        with pytest.raises(ProximoError):
            _check_replication_id("")


class TestCheckPbsJobType:
    def test_valid_sync(self):
        assert _check_pbs_job_type("sync") == "sync"

    def test_valid_verify(self):
        assert _check_pbs_job_type("verify") == "verify"

    def test_valid_prune(self):
        assert _check_pbs_job_type("prune") == "prune"

    def test_invalid_raises(self):
        with pytest.raises(ProximoError, match="invalid PBS job type"):
            _check_pbs_job_type("backup")

    def test_empty_raises(self):
        with pytest.raises(ProximoError):
            _check_pbs_job_type("")

    def test_uppercase_raises(self):
        """Type check is case-sensitive (closed frozenset)."""
        with pytest.raises(ProximoError):
            _check_pbs_job_type("Sync")


class TestCheckPbsJobId:
    def test_valid(self):
        assert _check_pbs_job_id("sync1") == "sync1"

    def test_trailing_newline_raises(self):
        with pytest.raises(ProximoError):
            _check_pbs_job_id("sync1\n")

    def test_slash_raises(self):
        with pytest.raises(ProximoError):
            _check_pbs_job_id("sync/slash")


class TestCheckRealm:
    def test_valid_simple(self):
        assert _check_realm("ldap1") == "ldap1"

    def test_valid_with_dot(self):
        assert _check_realm("company.ad") == "company.ad"

    def test_slash_raises(self):
        with pytest.raises(ProximoError, match="invalid PBS realm name"):
            _check_realm("realm/slash")

    def test_trailing_newline_raises(self):
        with pytest.raises(ProximoError):
            _check_realm("realm\n")

    def test_empty_raises(self):
        with pytest.raises(ProximoError):
            _check_realm("")


# ---------------------------------------------------------------------------
# PVE Backup Job operations
# ---------------------------------------------------------------------------

class TestBackupJobList:
    def test_calls_both_endpoints(self):
        api = _Api(get_return=[{"id": "daily"}])
        result = backup_job_list(api)
        assert "/cluster/backup" in api.gets
        assert "/cluster/backup-info/not-backed-up" in api.gets
        assert "jobs" in result and "unprotected_guests" in result

    def test_empty_api_returns_empty_lists(self):
        api = _Api(get_return=None)
        result = backup_job_list(api)
        assert result["jobs"] == []
        assert result["unprotected_guests"] == []


class TestBackupJobGet:
    def test_correct_path(self):
        api = _Api(get_return={"id": "daily", "schedule": "0 2 * * *"})
        result = backup_job_get(api, "daily")
        assert api.gets == ["/cluster/backup/daily"]
        assert result["id"] == "daily"

    def test_invalid_id_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            backup_job_get(api, "bad/id")

    def test_trailing_newline_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            backup_job_get(api, "daily\n")


class TestBackupJobCreate:
    def test_posts_to_cluster_backup(self):
        api = _Api()
        backup_job_create(api, "daily", "0 2 * * *", "local")
        assert len(api.posts) == 1
        path, data = api.posts[0]
        assert path == "/cluster/backup"
        assert data["id"] == "daily"
        assert data["schedule"] == "0 2 * * *"
        assert data["storage"] == "local"

    def test_none_kwargs_excluded(self):
        api = _Api()
        backup_job_create(api, "daily", "0 2 * * *", "local", mode=None, comment=None)
        _, data = api.posts[0]
        assert "mode" not in data
        assert "comment" not in data

    def test_invalid_id_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            backup_job_create(api, "bad/id", "0 2 * * *", "local")

    def test_pool_selection_passes_through(self):
        api = _Api()
        backup_job_create(api, "p", "0 2 * * *", "local", pool="prod")
        _, data = api.posts[0]
        assert data["pool"] == "prod"

    def test_all_with_exclude_passes_through(self):
        api = _Api()
        backup_job_create(api, "weekly", "0 3 * * 0", "local", all=True, exclude="100,101")
        _, data = api.posts[0]
        assert data["all"] is True
        assert data["exclude"] == "100,101"

    def test_vmid_and_all_mutually_exclusive_raises(self):
        api = _Api()
        with pytest.raises(ProximoError, match="mutually exclusive"):
            backup_job_create(api, "daily", "0 2 * * *", "local", vmid="100", all=True)

    def test_vmid_and_pool_mutually_exclusive_raises(self):
        api = _Api()
        with pytest.raises(ProximoError, match="mutually exclusive"):
            backup_job_create(api, "daily", "0 2 * * *", "local", vmid="100", pool="prod")

    def test_exclude_without_all_raises(self):
        api = _Api()
        with pytest.raises(ProximoError, match="exclude"):
            backup_job_create(api, "daily", "0 2 * * *", "local", vmid="100", exclude="101")


class TestBackupJobUpdate:
    def test_puts_to_correct_path(self):
        api = _Api()
        backup_job_update(api, "daily", schedule="0 3 * * *")
        assert len(api.puts) == 1
        path, data = api.puts[0]
        assert path == "/cluster/backup/daily"
        assert data["schedule"] == "0 3 * * *"

    def test_none_kwargs_excluded(self):
        api = _Api()
        backup_job_update(api, "daily", schedule="0 3 * * *", comment=None)
        _, data = api.puts[0]
        assert "comment" not in data

    def test_invalid_id_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            backup_job_update(api, "bad\n")


class TestBackupJobDelete:
    def test_deletes_correct_path(self):
        api = _Api()
        backup_job_delete(api, "daily")
        assert len(api.dels) == 1
        assert api.dels[0][0] == "/cluster/backup/daily"

    def test_invalid_id_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            backup_job_delete(api, "../etc")

    def test_trailing_newline_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            backup_job_delete(api, "daily\n")


# ---------------------------------------------------------------------------
# PVE Replication operations
# ---------------------------------------------------------------------------

class TestReplicationOps:
    def test_get_correct_path(self):
        api = _Api(get_return={"id": "101/0", "target": "node2"})
        result = replication_get(api, "101/0")
        assert api.gets == ["/cluster/replication/101/0"]
        assert result["id"] == "101/0"

    def test_create_posts_correct_path_and_body(self):
        api = _Api()
        replication_create(api, "101/0", "local", "node2", schedule="*/15")
        path, data = api.posts[0]
        assert path == "/cluster/replication"
        assert data["id"] == "101/0"
        assert data["target"] == "node2"
        assert data["type"] == "local"
        assert data["schedule"] == "*/15"

    def test_update_puts_correct_path(self):
        api = _Api()
        replication_update(api, "101/0", disable=True)
        path, data = api.puts[0]
        assert path == "/cluster/replication/101/0"
        assert data["disable"] is True

    def test_delete_correct_path(self):
        api = _Api()
        replication_delete(api, "101/0")
        assert api.dels[0][0] == "/cluster/replication/101/0"

    def test_invalid_id_raises_on_get(self):
        api = _Api()
        with pytest.raises(ProximoError):
            replication_get(api, "bad\n")


# ---------------------------------------------------------------------------
# PBS Scheduled Job operations
# ---------------------------------------------------------------------------

class TestPbsScheduledJobOps:
    def test_get_correct_path_sync(self):
        pbs = _Pbs(get_return={"id": "sync1"})
        result = pbs_scheduled_job_get(pbs, "sync", "sync1")
        assert pbs.gets == ["/config/sync/sync1"]
        assert result["id"] == "sync1"

    def test_get_invalid_type_raises(self):
        pbs = _Pbs()
        with pytest.raises(ProximoError, match="invalid PBS job type"):
            pbs_scheduled_job_get(pbs, "badtype", "job1")

    def test_get_trailing_newline_on_id_raises(self):
        pbs = _Pbs()
        with pytest.raises(ProximoError):
            pbs_scheduled_job_get(pbs, "sync", "sync1\n")

    def test_create_posts_to_correct_path(self):
        pbs = _Pbs()
        pbs_scheduled_job_create(pbs, "sync", "sync1", store="datastore1")
        path, data = pbs.posts[0]
        assert path == "/config/sync"
        assert data["id"] == "sync1"
        assert data["store"] == "datastore1"

    def test_create_none_kwargs_excluded(self):
        pbs = _Pbs()
        pbs_scheduled_job_create(pbs, "sync", "sync1", store=None)
        _, data = pbs.posts[0]
        assert "store" not in data

    def test_update_puts_to_correct_path(self):
        pbs = _Pbs()
        pbs_scheduled_job_update(pbs, "verify", "ver1", schedule="0 4 * * *")
        path, data = pbs.puts[0]
        assert path == "/config/verify/ver1"
        assert data["schedule"] == "0 4 * * *"

    def test_delete_correct_path_prune(self):
        pbs = _Pbs()
        pbs_scheduled_job_delete(pbs, "prune", "prune1")
        assert pbs.dels[0][0] == "/config/prune/prune1"

    def test_run_posts_to_admin_path(self):
        pbs = _Pbs()
        result = pbs_scheduled_job_run(pbs, "sync", "sync1")
        assert pbs.posts[0][0] == "/admin/sync/sync1/run"
        assert result == "UPID:pbs:post"

    def test_run_invalid_type_raises(self):
        pbs = _Pbs()
        with pytest.raises(ProximoError):
            pbs_scheduled_job_run(pbs, "backup", "b1")


class TestPbsScheduledJobsList:
    def test_gets_correct_path_sync(self):
        pbs = _Pbs(get_return=[{"id": "sync1", "store": "ds1"}])
        result = pbs_scheduled_jobs_list(pbs, "sync")
        assert pbs.gets[0] == "/config/sync"
        assert isinstance(result, list)

    def test_job_type_interpolated_in_path_verify(self):
        pbs = _Pbs(get_return=[])
        pbs_scheduled_jobs_list(pbs, "verify")
        assert pbs.gets[0] == "/config/verify"

    def test_job_type_interpolated_in_path_prune(self):
        pbs = _Pbs(get_return=[])
        pbs_scheduled_jobs_list(pbs, "prune")
        assert pbs.gets[0] == "/config/prune"

    def test_invalid_job_type_raises_proximo_error(self):
        pbs = _Pbs()
        with pytest.raises(ProximoError, match="invalid PBS job type"):
            pbs_scheduled_jobs_list(pbs, "backup")

    def test_invalid_job_type_schedule_raises(self):
        pbs = _Pbs()
        with pytest.raises(ProximoError):
            pbs_scheduled_jobs_list(pbs, "schedule")

    def test_empty_list_on_none_return(self):
        pbs = _Pbs(get_return=None)
        result = pbs_scheduled_jobs_list(pbs, "sync")
        assert result == []


# ---------------------------------------------------------------------------
# PBS Realm Sync
# ---------------------------------------------------------------------------

class TestPbsRealmSync:
    def test_posts_to_correct_path(self):
        pbs = _Pbs()
        result = pbs_realm_sync(pbs, "company-ad")
        assert pbs.posts[0][0] == "/access/domains/company-ad/sync"
        assert result == "UPID:pbs:post"

    def test_kwargs_passed(self):
        pbs = _Pbs()
        pbs_realm_sync(pbs, "ldap1", scope="users", remove_vanished=True)
        _, data = pbs.posts[0]
        assert data["scope"] == "users"
        assert data["remove_vanished"] is True

    def test_none_kwargs_excluded(self):
        pbs = _Pbs()
        pbs_realm_sync(pbs, "ldap1", scope=None)
        _, data = pbs.posts[0]
        assert "scope" not in data

    def test_invalid_realm_raises(self):
        pbs = _Pbs()
        with pytest.raises(ProximoError, match="invalid PBS realm name"):
            pbs_realm_sync(pbs, "realm/slash")

    def test_trailing_newline_on_realm_raises(self):
        pbs = _Pbs()
        with pytest.raises(ProximoError):
            pbs_realm_sync(pbs, "realm\n")


# ---------------------------------------------------------------------------
# Plan factories — PVE Backup Jobs
# ---------------------------------------------------------------------------

class TestPlanBackupJobCreate:
    def test_is_low_risk(self):
        plan = plan_backup_job_create("daily", "0 2 * * *", "local")
        assert plan.risk == RISK_LOW

    def test_current_is_empty(self):
        plan = plan_backup_job_create("daily", "0 2 * * *", "local")
        assert plan.current == {}

    def test_change_includes_id(self):
        plan = plan_backup_job_create("daily", "0 2 * * *", "local")
        assert "daily" in plan.change

    def test_target_correct(self):
        plan = plan_backup_job_create("daily", "0 2 * * *", "local")
        assert plan.target == "cluster/backup/daily"

    def test_invalid_id_raises(self):
        with pytest.raises(ProximoError):
            plan_backup_job_create("bad/id", "0 2 * * *", "local")

    def test_mutually_exclusive_selection_raises(self):
        with pytest.raises(ProximoError, match="mutually exclusive"):
            plan_backup_job_create("daily", "0 2 * * *", "local", vmid="100", all=True)

    def test_exclude_without_all_raises(self):
        with pytest.raises(ProximoError, match="exclude"):
            plan_backup_job_create("daily", "0 2 * * *", "local", exclude="101")


class TestPlanBackupJobUpdate:
    def test_reads_current_from_api(self):
        api = _Api(get_return={"id": "daily", "schedule": "0 2 * * *", "storage": "local"})
        plan = plan_backup_job_update(api, "daily", schedule="0 3 * * *")
        assert plan.risk == RISK_LOW
        assert "id" in plan.current   # captured from the fake API

    def test_no_implied_undo_in_note(self):
        api = _Api(get_return={"id": "daily"})
        plan = plan_backup_job_update(api, "daily")
        # Plan note must acknowledge no snapshot/UNDO primitive exists
        assert "no snapshot" in plan.note.lower() or "no undo" in plan.note.lower()

    def test_invalid_id_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            plan_backup_job_update(api, "bad\n")


class TestPlanBackupJobDelete:
    def test_reads_current_from_api(self):
        api = _Api(get_return={"id": "daily", "schedule": "0 2 * * *"})
        plan = plan_backup_job_delete(api, "daily")
        assert plan.risk == RISK_LOW
        assert "id" in plan.current

    def test_blast_radius_mentions_no_backup_deletion(self):
        api = _Api(get_return={"id": "daily"})
        plan = plan_backup_job_delete(api, "daily")
        blast_text = " ".join(plan.blast_radius).lower()
        assert "not deleted" in blast_text or "no" in blast_text


# ---------------------------------------------------------------------------
# Plan factories — PVE Replication
# ---------------------------------------------------------------------------

class TestPlanReplication:
    def test_create_is_low_risk_with_empty_current(self):
        plan = plan_replication_create("101/0", "local", "node2")
        assert plan.risk == RISK_LOW
        assert plan.current == {}

    def test_create_change_discloses_schedule_and_rate(self):
        # schedule/rate/disable/comment are the actual fields being written — the PLAN
        # preview (and the PROVE ledger entry built from it) must show them, not just
        # the id/type/target, mirroring plan_pbs_job_create's `{kw}` disclosure.
        plan = plan_replication_create(
            "101/0", "local", "node2", schedule="*/30", rate=10.0, disable=False, comment="nightly"
        )
        assert "*/30" in plan.change
        assert "10.0" in plan.change
        assert "nightly" in plan.change

    def test_update_reads_current(self):
        api = _Api(get_return={"id": "101/0", "target": "node2"})
        plan = plan_replication_update(api, "101/0", schedule="*/15")
        assert plan.risk == RISK_LOW
        assert "id" in plan.current

    def test_delete_reads_current(self):
        api = _Api(get_return={"id": "101/0", "target": "node2"})
        plan = plan_replication_delete(api, "101/0")
        assert plan.risk == RISK_LOW
        assert "id" in plan.current

    def test_delete_blast_radius_mentions_data_not_removed(self):
        api = _Api(get_return={"id": "101/0"})
        plan = plan_replication_delete(api, "101/0")
        blast_text = " ".join(plan.blast_radius).lower()
        assert "not" in blast_text


# ---------------------------------------------------------------------------
# Plan factories — PBS Scheduled Jobs
# ---------------------------------------------------------------------------

class TestPlanPbsJobs:
    def test_create_is_low_risk_empty_current(self):
        plan = plan_pbs_job_create("sync", "sync1")
        assert plan.risk == RISK_LOW
        assert plan.current == {}

    def test_create_target_correct(self):
        plan = plan_pbs_job_create("verify", "ver1")
        assert plan.target == "pbs/config/verify/ver1"

    def test_create_invalid_type_raises(self):
        with pytest.raises(ProximoError):
            plan_pbs_job_create("backup", "b1")

    def test_update_reads_current(self):
        pbs = _Pbs(get_return={"id": "sync1", "schedule": "0 1 * * *"})
        plan = plan_pbs_job_update(pbs, "sync", "sync1", schedule="0 2 * * *")
        assert plan.risk == RISK_LOW
        assert "id" in plan.current

    def test_delete_reads_current(self):
        pbs = _Pbs(get_return={"id": "prune1"})
        plan = plan_pbs_job_delete(pbs, "prune", "prune1")
        assert plan.risk == RISK_LOW
        assert "id" in plan.current

    def test_run_is_low_risk(self):
        plan = plan_pbs_job_run("prune", "prune1")
        assert plan.risk == RISK_LOW
        assert "prune" in plan.change

    def test_run_mentions_prune_may_delete(self):
        plan = plan_pbs_job_run("prune", "prune1")
        blast_text = " ".join(plan.blast_radius).lower()
        assert "prune" in blast_text or "delete" in blast_text or "snapshot" in blast_text

    def test_run_invalid_type_raises(self):
        with pytest.raises(ProximoError):
            plan_pbs_job_run("bad-type", "job1")


# ---------------------------------------------------------------------------
# Plan factory — PBS Realm Sync
# ---------------------------------------------------------------------------

class TestPlanPbsRealmSync:
    def test_is_low_risk(self):
        plan = plan_pbs_realm_sync("ldap1")
        assert plan.risk == RISK_LOW

    def test_remove_vanished_is_medium(self):
        # remove-vanished deletes directory-absent PBS users — a destructive sync, MEDIUM not LOW
        plan = plan_pbs_realm_sync("ldap1", remove_vanished=True)
        assert plan.risk == RISK_MEDIUM
        assert "remove-vanished" in plan.change.lower()

    def test_current_is_empty(self):
        plan = plan_pbs_realm_sync("ldap1")
        assert plan.current == {}

    def test_note_mentions_smoke_confirm(self):
        plan = plan_pbs_realm_sync("ldap1")
        assert "smoke-confirm" in plan.note.lower()

    def test_invalid_realm_raises(self):
        with pytest.raises(ProximoError):
            plan_pbs_realm_sync("realm/slash")
