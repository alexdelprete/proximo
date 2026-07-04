"""PBS config + safety plane tests (Wave 5) — fully mocked, no live PBS.

Covers:
- Plan factories: action/target/risk + honest blast wording.
- Conditional risk: datastore_delete (destroy_data), snapshot_protected_set (protected).
- Secret redaction: password NEVER appears in plan dict or ledger; fingerprint is NOT redacted.
- outcome="submitted" for async worker ops (datastore create + delete).
- CAPTURE-or-declare: datastore_update, remote_update, snapshot_notes_set, traffic_control_upsert.
- Mutation gating: plan-by-default, confirm executes, one-shot records plan first.
- Validation: bad store name, bad path, bad backup_type.
- Module structure: EXCLUSION note (PBS access) in module docstring.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.backends import ProximoError
from proximo.config import ProximoConfig
from proximo.pbs_config import (
    _check_datastore_path,
    _remote_password_fingerprint,
    datastore_get,
    plan_datastore_create,
    plan_datastore_delete,
    plan_datastore_update,
    plan_group_change_owner,
    plan_remote_create,
    plan_remote_delete,
    plan_remote_update,
    plan_snapshot_notes_set,
    plan_snapshot_protected_set,
    plan_traffic_control_delete,
    plan_traffic_control_upsert,
    remote_get,
    remotes_list,
    traffic_control_upsert,
    traffic_controls_list,
)
from proximo.planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM

# ---------------------------------------------------------------------------
# Helpers — pure plan tests use a lightweight fake backend for CAPTURE
# ---------------------------------------------------------------------------

class _FakePbs:
    """Fake PBS backend — records calls; returns configurable data for _get."""

    def __init__(self, get_return=None, raise_on_get=None):
        self.gets: list = []
        self.posts: list = []
        self.puts: list = []
        self.dels: list = []
        self._get_return = get_return
        self._raise_on_get = raise_on_get

    def _get(self, path, params=None):
        self.gets.append((path, params))
        if self._raise_on_get is not None:
            raise self._raise_on_get
        return self._get_return

    def _post(self, path, data=None):
        self.posts.append((path, data))
        return "UPID:pbs"

    def _put(self, path, data=None):
        self.puts.append((path, data))
        return None

    def _delete(self, path, params=None):
        self.dels.append((path, params))
        return None


class _FakeApi:
    """Minimal PVE API stub for _svc()."""
    def __init__(self):
        self.config = SimpleNamespace(node="pve")
        self.gets: list = []

    def _get(self, path):
        self.gets.append(path)
        return []


def _wire(tmp_path, monkeypatch, *, get_return=None, raise_on_get=None, redact_ledger=False):
    """Wire the server with a fake PBS backend and a real on-disk ledger."""
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log, redact_ledger=redact_ledger,
    )
    api = _FakeApi()
    pbs = _FakePbs(get_return=get_return, raise_on_get=raise_on_get)
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, SimpleNamespace(), ledger))
    monkeypatch.setattr(server, "_pbs", lambda: (SimpleNamespace(), pbs))
    return cfg, api, pbs, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------------------
# Module-level: structure + exclusion note
# ---------------------------------------------------------------------------

def test_module_docstring_contains_exclusion_note():
    import proximo.pbs_config as m
    doc = m.__doc__ or ""
    assert "EXCLUSION" in doc
    assert "access" in doc.lower()
    # The plane was live-proven against PBS 4.2 — the docstring records that, and that the
    # remaining unverified bits (snapshot ops) still carry Smoke-confirm. (Was "VERIFIED live
    # shapes: None" pre-live-prove; flipped honestly once the shapes were confirmed.)
    assert "VERIFIED live" in doc
    assert "Smoke-confirm" in doc


def test_remote_password_fingerprint_helper():
    fp = _remote_password_fingerprint()
    assert fp == {"password": "[redacted]"}


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

class TestCheckDatastorePath:
    def test_valid_absolute(self):
        assert _check_datastore_path("/mnt/data") == "/mnt/data"

    def test_valid_deep(self):
        assert _check_datastore_path("/srv/pbs/store1") == "/srv/pbs/store1"

    def test_rejects_empty(self):
        with pytest.raises(ProximoError, match="empty"):
            _check_datastore_path("")

    def test_rejects_relative(self):
        with pytest.raises(ProximoError, match="absolute"):
            _check_datastore_path("relative/path")

    def test_rejects_dotdot(self):
        with pytest.raises(ProximoError, match="traversal"):
            _check_datastore_path("/mnt/../etc")

    def test_rejects_control_chars(self):
        with pytest.raises(ProximoError, match="control"):
            _check_datastore_path("/mnt/\x00data")


# ---------------------------------------------------------------------------
# Plan factory: pbs_datastore_create
# ---------------------------------------------------------------------------

class TestPlanDatastoreCreate:
    def test_action_and_risk(self):
        p = plan_datastore_create("mystore", "/mnt/data")
        assert p.action == "pbs_datastore_create"
        assert p.risk == RISK_MEDIUM

    def test_target_contains_name(self):
        p = plan_datastore_create("mystore", "/mnt/data")
        assert "mystore" in p.target

    def test_change_contains_path(self):
        p = plan_datastore_create("mystore", "/srv/backup")
        assert "/srv/backup" in p.change

    def test_blast_radius_mentions_additive(self):
        p = plan_datastore_create("mystore", "/mnt/data")
        blast = " ".join(p.blast_radius)
        assert "additive" in blast.lower() or "create" in blast.lower()

    def test_blast_mentions_no_rollback(self):
        p = plan_datastore_create("mystore", "/mnt/data")
        blast = " ".join(p.blast_radius)
        assert "rollback" in blast.lower() or "undo" in blast.lower()

    def test_note_mentions_submitted(self):
        p = plan_datastore_create("mystore", "/mnt/data")
        assert "submitted" in p.note.lower()

    def test_note_mentions_smoke_confirm(self):
        p = plan_datastore_create("mystore", "/mnt/data")
        assert "smoke-confirm" in p.note.lower() or "smoke_confirm" in p.note.lower()

    def test_invalid_name_rejected(self):
        with pytest.raises(ProximoError):
            plan_datastore_create("-badname", "/mnt/data")

    def test_invalid_path_rejected(self):
        with pytest.raises(ProximoError):
            plan_datastore_create("mystore", "relative/path")

    def test_optional_gc_schedule_in_change(self):
        p = plan_datastore_create("mystore", "/mnt/data", gc_schedule="sun 03:00")
        assert "sun 03:00" in p.change or "gc-schedule" in p.change


# ---------------------------------------------------------------------------
# Plan factory: pbs_datastore_update (CAPTURE-or-declare)
# ---------------------------------------------------------------------------

class TestPlanDatastoreUpdate:
    def test_action_and_risk(self):
        pbs = _FakePbs()
        p = plan_datastore_update(pbs, "mystore")
        assert p.action == "pbs_datastore_update"
        assert p.risk == RISK_MEDIUM

    def test_capture_reads_current_config(self):
        pbs = _FakePbs(get_return={"name": "mystore", "path": "/mnt/data", "gc-schedule": "sun 03:00"})
        p = plan_datastore_update(pbs, "mystore", gc_schedule="daily 02:00")
        assert p.current.get("gc-schedule") == "sun 03:00"
        assert p.complete is True

    def test_capture_failure_marks_incomplete(self):
        pbs = _FakePbs(raise_on_get=RuntimeError("connection refused"))
        p = plan_datastore_update(pbs, "mystore")
        assert p.complete is False
        assert "not" in p.note.lower() or "could not" in p.note.lower()

    def test_changes_in_change_string(self):
        pbs = _FakePbs()
        p = plan_datastore_update(pbs, "mystore", gc_schedule="daily")
        assert "daily" in p.change or "gc-schedule" in p.change

    def test_blast_mentions_retention(self):
        pbs = _FakePbs()
        p = plan_datastore_update(pbs, "mystore", gc_schedule="daily")
        blast = " ".join(p.blast_radius)
        assert "retention" in blast.lower() or "gc" in blast.lower() or "schedule" in blast.lower()

    def test_note_mentions_revert(self):
        pbs = _FakePbs()
        p = plan_datastore_update(pbs, "mystore")
        assert "revert" in p.note.lower() or "re-apply" in p.note.lower()

    def test_strips_password_from_capture_defensively(self):
        """Even if the backend ever returned a password field, we strip it."""
        pbs = _FakePbs(get_return={"name": "mystore", "password": "leaked-secret"})
        p = plan_datastore_update(pbs, "mystore")
        assert "password" not in p.current
        assert "leaked-secret" not in json.dumps(p.as_dict())


# ---------------------------------------------------------------------------
# Plan factory: pbs_datastore_delete — CONDITIONAL RISK (load-bearing)
# ---------------------------------------------------------------------------

class TestPlanDatastoreDelete:
    def test_destroy_data_false_is_medium(self):
        p = plan_datastore_delete("mystore", destroy_data=False)
        assert p.risk == RISK_MEDIUM

    def test_destroy_data_false_blast_mentions_remains_on_disk(self):
        p = plan_datastore_delete("mystore", destroy_data=False)
        blast = " ".join(p.blast_radius)
        assert "remains on disk" in blast.lower() or "remain" in blast.lower()

    def test_destroy_data_false_blast_mentions_re_addable(self):
        p = plan_datastore_delete("mystore", destroy_data=False)
        blast = " ".join(p.blast_radius)
        # Should mention ability to recover/re-add
        assert "re-add" in blast.lower() or "recover" in blast.lower()

    def test_destroy_data_true_is_high(self):
        p = plan_datastore_delete("mystore", destroy_data=True)
        assert p.risk == RISK_HIGH

    def test_destroy_data_true_blast_mentions_permanently_destroyed(self):
        p = plan_datastore_delete("mystore", destroy_data=True)
        blast = " ".join(p.blast_radius)
        assert "permanently" in blast.lower() or "permanent" in blast.lower()
        assert "destroy" in blast.lower() or "destroyed" in blast.lower()

    def test_destroy_data_true_blast_names_the_datastore(self):
        p = plan_datastore_delete("sentinel-store", destroy_data=True)
        blast = " ".join(p.blast_radius)
        assert "sentinel-store" in blast

    def test_destroy_data_true_mentions_no_recovery(self):
        p = plan_datastore_delete("mystore", destroy_data=True)
        blast = " ".join(p.blast_radius)
        assert "no recovery" in blast.lower() or "irreversible" in blast.lower()

    def test_note_mentions_submitted(self):
        p = plan_datastore_delete("mystore")
        assert "submitted" in p.note.lower()

    def test_note_mentions_smoke_confirm(self):
        p = plan_datastore_delete("mystore")
        assert "smoke-confirm" in p.note.lower() or "smoke_confirm" in p.note.lower()

    def test_invalid_name_rejected(self):
        with pytest.raises(ProximoError):
            plan_datastore_delete("/bad/name")


# ---------------------------------------------------------------------------
# Plan factory: pbs_snapshot_protected_set — CONDITIONAL RISK (load-bearing)
# ---------------------------------------------------------------------------

class TestPlanSnapshotProtectedSet:
    def test_protected_true_is_low(self):
        p = plan_snapshot_protected_set("store1", "ct", "100", 1700000000, protected=True)
        assert p.risk == RISK_LOW

    def test_protected_true_blast_is_protective(self):
        p = plan_snapshot_protected_set("store1", "ct", "100", 1700000000, protected=True)
        blast = " ".join(p.blast_radius)
        assert "shield" in blast.lower() or "protect" in blast.lower() or "prune" in blast.lower()

    def test_protected_false_is_high(self):
        p = plan_snapshot_protected_set("store1", "ct", "100", 1700000000, protected=False)
        assert p.risk == RISK_HIGH

    def test_protected_false_blast_mentions_can_now_be_auto_deleted(self):
        p = plan_snapshot_protected_set("store1", "ct", "100", 1700000000, protected=False)
        blast = " ".join(p.blast_radius)
        assert "auto-deleted" in blast.lower() or "auto deleted" in blast.lower() or "auto" in blast.lower()

    def test_protected_false_blast_mentions_prune_or_gc(self):
        p = plan_snapshot_protected_set("store1", "ct", "100", 1700000000, protected=False)
        blast = " ".join(p.blast_radius)
        assert "prune" in blast.lower() or "gc" in blast.lower()

    def test_protected_false_note_mentions_revert(self):
        p = plan_snapshot_protected_set("store1", "ct", "100", 1700000000, protected=False)
        assert "revert" in p.note.lower() or "re-set" in p.note.lower() or "re-apply" in p.note.lower()

    def test_action_name(self):
        p = plan_snapshot_protected_set("store1", "ct", "100", 1700000000, protected=True)
        assert p.action == "pbs_snapshot_protected_set"

    def test_invalid_backup_type_rejected(self):
        with pytest.raises(ProximoError):
            plan_snapshot_protected_set("store1", "invalid", "100", 1700000000, protected=True)

    def test_invalid_backup_time_rejected(self):
        with pytest.raises(ProximoError):
            plan_snapshot_protected_set("store1", "ct", "100", -1, protected=True)

    def test_namespace_included_in_target(self):
        p = plan_snapshot_protected_set("store1", "ct", "100", 1700000000,
                                        protected=False, ns="team/prod")
        # Namespace should appear somewhere (in change or note)
        combined = p.change + p.note
        assert "team/prod" in combined


# ---------------------------------------------------------------------------
# Plan factory: pbs_snapshot_notes_set (CAPTURE)
# ---------------------------------------------------------------------------

class TestPlanSnapshotNotesSet:
    def test_action_and_risk(self):
        pbs = _FakePbs()
        p = plan_snapshot_notes_set(pbs, "store1", "ct", "100", 1700000000, "my notes")
        assert p.action == "pbs_snapshot_notes_set"
        assert p.risk == RISK_LOW

    def test_capture_stores_current_notes(self):
        pbs = _FakePbs(get_return="old notes")
        p = plan_snapshot_notes_set(pbs, "store1", "ct", "100", 1700000000, "new notes")
        assert p.current.get("notes") == "old notes"
        assert p.complete is True

    def test_capture_failure_marks_incomplete(self):
        pbs = _FakePbs(raise_on_get=RuntimeError("read error"))
        p = plan_snapshot_notes_set(pbs, "store1", "ct", "100", 1700000000, "notes")
        assert p.complete is False

    def test_blast_does_not_affect_data(self):
        pbs = _FakePbs()
        p = plan_snapshot_notes_set(pbs, "store1", "ct", "100", 1700000000, "notes")
        blast = " ".join(p.blast_radius)
        assert "annotation" in blast.lower() or "does not affect" in blast.lower()


# ---------------------------------------------------------------------------
# Plan factory: pbs_group_change_owner
# ---------------------------------------------------------------------------

class TestPlanGroupChangeOwner:
    def test_action_and_risk(self):
        p = plan_group_change_owner("store1", "ct", "100", "newuser@pbs")
        assert p.action == "pbs_group_change_owner"
        assert p.risk == RISK_MEDIUM

    def test_blast_mentions_new_owner_controls_prune(self):
        p = plan_group_change_owner("store1", "ct", "100", "newuser@pbs")
        blast = " ".join(p.blast_radius)
        assert "prune" in blast.lower() or "delete" in blast.lower()
        assert "newuser@pbs" in blast

    def test_change_includes_new_owner(self):
        p = plan_group_change_owner("store1", "ct", "100", "alice@pbs")
        assert "alice@pbs" in p.change


# ---------------------------------------------------------------------------
# Plan factory: pbs_remote_create — SECRET REDACTION (load-bearing)
# ---------------------------------------------------------------------------

class TestPlanRemoteCreate:
    def test_action_and_risk(self):
        p = plan_remote_create("mypbs", "pbs2.example.com", "backup@pbs!tok")
        assert p.action == "pbs_remote_create"
        assert p.risk == RISK_MEDIUM

    def test_plan_factory_has_no_password_parameter(self):
        """The plan factory signature must not accept a 'password' param."""
        import inspect
        sig = inspect.signature(plan_remote_create)
        assert "password" not in sig.parameters, (
            "plan_remote_create must NOT have a 'password' parameter — unconditional redaction"
        )

    def test_fingerprint_in_change(self):
        """Fingerprint is PUBLIC — must appear in the plan change string."""
        p = plan_remote_create("mypbs", "pbs2.example.com", "backup@pbs!tok",
                               fingerprint="aa:bb:cc:dd")
        assert "aa:bb:cc:dd" in p.change

    def test_note_mentions_unconditional_redaction(self):
        p = plan_remote_create("mypbs", "pbs2.example.com", "backup@pbs!tok")
        assert "redacted" in p.note.lower()

    def test_note_mentions_fingerprint_not_redacted(self):
        p = plan_remote_create("mypbs", "pbs2.example.com", "backup@pbs!tok")
        assert "fingerprint" in p.note.lower()
        assert "not" in p.note.lower()


# ---------------------------------------------------------------------------
# Plan factory: pbs_remote_update (CAPTURE + REDACTION)
# ---------------------------------------------------------------------------

class TestPlanRemoteUpdate:
    def test_action_and_risk(self):
        pbs = _FakePbs()
        p = plan_remote_update(pbs, "mypbs")
        assert p.action == "pbs_remote_update"
        assert p.risk == RISK_MEDIUM

    def test_plan_factory_has_no_password_parameter(self):
        import inspect
        sig = inspect.signature(plan_remote_update)
        assert "password" not in sig.parameters

    def test_capture_reads_current_config(self):
        pbs = _FakePbs(get_return={"host": "old.pbs.example.com", "auth-id": "backup@pbs!tok"})
        p = plan_remote_update(pbs, "mypbs")
        assert p.current.get("host") == "old.pbs.example.com"
        assert p.complete is True

    def test_capture_strips_password_defensively(self):
        """If PBS ever returns a password in GET, we strip it."""
        pbs = _FakePbs(get_return={"host": "pbs.example.com", "password": "LEAKED-SECRET"})
        p = plan_remote_update(pbs, "mypbs")
        assert "password" not in p.current
        assert "LEAKED-SECRET" not in json.dumps(p.as_dict())

    def test_capture_failure_marks_incomplete(self):
        pbs = _FakePbs(raise_on_get=RuntimeError("network error"))
        p = plan_remote_update(pbs, "mypbs")
        assert p.complete is False

    def test_fingerprint_in_changes(self):
        pbs = _FakePbs()
        p = plan_remote_update(pbs, "mypbs", fingerprint="aa:bb:cc")
        assert "aa:bb:cc" in p.change


# ---------------------------------------------------------------------------
# Plan factory: pbs_remote_delete
# ---------------------------------------------------------------------------

class TestPlanRemoteDelete:
    def test_action_and_risk(self):
        p = plan_remote_delete("mypbs")
        assert p.action == "pbs_remote_delete"
        assert p.risk == RISK_MEDIUM

    def test_blast_mentions_credentials_and_sync_jobs(self):
        p = plan_remote_delete("mypbs")
        blast = " ".join(p.blast_radius)
        assert "credential" in blast.lower() or "password" in blast.lower()
        assert "sync" in blast.lower() or "job" in blast.lower()

    def test_blast_mentions_password_must_be_resupplied(self):
        p = plan_remote_delete("mypbs")
        blast = " ".join(p.blast_radius)
        assert "password" in blast.lower()


# ---------------------------------------------------------------------------
# Plan factory: pbs_traffic_control_upsert (CAPTURE + create/update dispatch)
# ---------------------------------------------------------------------------

class TestPlanTrafficControlUpsert:
    def test_create_path_is_low(self):
        """When no existing rule is found, risk is LOW (additive)."""
        pbs = _FakePbs(get_return=None)  # _get returns None → create path
        p = plan_traffic_control_upsert(pbs, "rule1", rate_in=100)
        assert p.risk == RISK_LOW

    def test_update_path_is_medium(self):
        """When an existing rule is found, risk is MEDIUM."""
        pbs = _FakePbs(get_return={"name": "rule1", "rate-in": 50})
        p = plan_traffic_control_upsert(pbs, "rule1", rate_in=100)
        assert p.risk == RISK_MEDIUM

    def test_update_path_captures_current(self):
        pbs = _FakePbs(get_return={"name": "rule1", "rate-in": 50})
        p = plan_traffic_control_upsert(pbs, "rule1")
        assert p.current.get("rate-in") == 50

    def test_exception_on_get_marks_incomplete(self):
        """A non-404 error marks the plan incomplete and defaults to create path."""
        pbs = _FakePbs(raise_on_get=RuntimeError("connection refused"))
        p = plan_traffic_control_upsert(pbs, "rule1")
        assert p.complete is False

    def test_create_blast_mentions_additive(self):
        pbs = _FakePbs(get_return=None)
        p = plan_traffic_control_upsert(pbs, "rule1")
        blast = " ".join(p.blast_radius)
        assert "additive" in blast.lower()

    def test_update_blast_mentions_throttle(self):
        pbs = _FakePbs(get_return={"name": "rule1"})
        p = plan_traffic_control_upsert(pbs, "rule1", rate_in=1)
        blast = " ".join(p.blast_radius) + p.note
        assert "throttle" in blast.lower() or "crawl" in blast.lower()

    def test_action_name(self):
        pbs = _FakePbs()
        p = plan_traffic_control_upsert(pbs, "rule1")
        assert p.action == "pbs_traffic_control_upsert"


# ---------------------------------------------------------------------------
# Plan factory: pbs_traffic_control_delete
# ---------------------------------------------------------------------------

class TestPlanTrafficControlDelete:
    def test_action_and_risk(self):
        p = plan_traffic_control_delete("rule1")
        assert p.action == "pbs_traffic_control_delete"
        assert p.risk == RISK_MEDIUM  # deleting config IS a state change — not LOW

    def test_blast_mentions_unthrottled(self):
        p = plan_traffic_control_delete("rule1")
        blast = " ".join(p.blast_radius)
        assert "unthrottled" in blast.lower()

    def test_blast_mentions_recoverable(self):
        p = plan_traffic_control_delete("rule1")
        blast = " ".join(p.blast_radius) + p.note
        assert "re-create" in blast.lower() or "recover" in blast.lower()


# ---------------------------------------------------------------------------
# Server-level: mutation gating (PLAN->PROVE weld)
# ---------------------------------------------------------------------------

class TestMutationGating:
    def test_datastore_create_dry_run_returns_plan(self, tmp_path, monkeypatch):
        _, _, pbs, _, _ = _wire(tmp_path, monkeypatch)
        out = server.pbs_datastore_create("newstore", "/mnt/data")
        assert out["status"] == "plan"
        assert out["risk"] == RISK_MEDIUM
        assert pbs.posts == []  # nothing executed on dry-run

    def test_datastore_create_confirm_records_submitted(self, tmp_path, monkeypatch):
        _, _, pbs, _, log = _wire(tmp_path, monkeypatch)
        out = server.pbs_datastore_create("newstore", "/mnt/data", confirm=True)
        assert out["status"] == "submitted"
        assert pbs.posts != []  # executed
        outcomes = {e["outcome"] for e in _entries(log) if e["action"] == "pbs_datastore_create"}
        assert "planned" in outcomes
        assert "submitted" in outcomes
        assert "ok" not in outcomes  # async → never "ok"

    def test_datastore_delete_dry_run_medium_no_destroy(self, tmp_path, monkeypatch):
        _, _, pbs, _, _ = _wire(tmp_path, monkeypatch)
        out = server.pbs_datastore_delete("mystore", destroy_data=False)
        assert out["status"] == "plan"
        assert out["risk"] == RISK_MEDIUM
        assert pbs.dels == []

    def test_datastore_delete_destroy_true_is_high_plan(self, tmp_path, monkeypatch):
        _, _, pbs, _, _ = _wire(tmp_path, monkeypatch)
        out = server.pbs_datastore_delete("mystore", destroy_data=True)
        assert out["status"] == "plan"
        assert out["risk"] == RISK_HIGH

    def test_datastore_delete_confirm_records_submitted_not_ok(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire(tmp_path, monkeypatch)
        out = server.pbs_datastore_delete("mystore", confirm=True)
        assert out["status"] == "submitted"
        outcomes = {e["outcome"] for e in _entries(log) if e["action"] == "pbs_datastore_delete"}
        assert "planned" in outcomes
        assert "submitted" in outcomes
        assert "ok" not in outcomes  # async → never "ok"

    def test_datastore_delete_destroy_true_confirm_submitted(self, tmp_path, monkeypatch):
        # The destructive branch must ALSO be "submitted", never "ok" — guard against a conditional
        # that only set submitted on the recoverable (destroy_data=False) path.
        _, _, _, _, log = _wire(tmp_path, monkeypatch)
        out = server.pbs_datastore_delete("mystore", destroy_data=True, confirm=True)
        assert out["status"] == "submitted"
        outcomes = {e["outcome"] for e in _entries(log) if e["action"] == "pbs_datastore_delete"}
        assert "submitted" in outcomes
        assert "ok" not in outcomes

    def test_snapshot_protected_set_true_is_low_plan(self, tmp_path, monkeypatch):
        _, _, pbs, _, _ = _wire(tmp_path, monkeypatch)
        out = server.pbs_snapshot_protected_set("store1", "ct", "100", 1700000000, protected=True)
        assert out["status"] == "plan"
        assert out["risk"] == RISK_LOW
        assert pbs.puts == []

    def test_snapshot_protected_set_false_is_high_plan(self, tmp_path, monkeypatch):
        _, _, pbs, _, _ = _wire(tmp_path, monkeypatch)
        out = server.pbs_snapshot_protected_set("store1", "ct", "100", 1700000000, protected=False)
        assert out["status"] == "plan"
        assert out["risk"] == RISK_HIGH
        assert pbs.puts == []

    def test_snapshot_protected_set_confirm_executes_put(self, tmp_path, monkeypatch):
        _, _, pbs, _, log = _wire(tmp_path, monkeypatch)
        out = server.pbs_snapshot_protected_set("store1", "ct", "100", 1700000000,
                                                protected=True, confirm=True)
        assert out["status"] == "ok"
        assert pbs.puts != []
        outcomes = {e["outcome"] for e in _entries(log)
                    if e["action"] == "pbs_snapshot_protected_set"}
        assert "planned" in outcomes
        assert "ok" in outcomes  # synchronous op → ok

    def test_snapshot_notes_set_dry_run_low(self, tmp_path, monkeypatch):
        _, _, pbs, _, _ = _wire(tmp_path, monkeypatch)
        out = server.pbs_snapshot_notes_set("store1", "ct", "100", 1700000000, "my notes")
        assert out["status"] == "plan"
        assert out["risk"] == RISK_LOW

    def test_group_change_owner_dry_run_medium(self, tmp_path, monkeypatch):
        _, _, pbs, _, _ = _wire(tmp_path, monkeypatch)
        out = server.pbs_group_change_owner("store1", "ct", "100", "alice@pbs")
        assert out["status"] == "plan"
        assert out["risk"] == RISK_MEDIUM

    def test_remote_delete_dry_run_medium(self, tmp_path, monkeypatch):
        _, _, pbs, _, _ = _wire(tmp_path, monkeypatch)
        out = server.pbs_remote_delete("remote1")
        assert out["status"] == "plan"
        assert out["risk"] == RISK_MEDIUM

    def test_traffic_control_delete_dry_run_medium(self, tmp_path, monkeypatch):
        _, _, pbs, _, _ = _wire(tmp_path, monkeypatch)
        out = server.pbs_traffic_control_delete("rule1")
        assert out["status"] == "plan"
        assert out["risk"] == RISK_MEDIUM

    def test_traffic_control_upsert_create_path_low_plan(self, tmp_path, monkeypatch):
        _, _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=None)
        out = server.pbs_traffic_control_upsert("rule1", rate_in=100)
        assert out["status"] == "plan"
        assert out["risk"] == RISK_LOW

    def test_traffic_control_upsert_update_path_medium_plan(self, tmp_path, monkeypatch):
        _, _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "rule1"})
        out = server.pbs_traffic_control_upsert("rule1", rate_in=200)
        assert out["status"] == "plan"
        assert out["risk"] == RISK_MEDIUM

    def test_one_shot_confirm_records_plan_first(self, tmp_path, monkeypatch):
        """No mutation without a recorded plan — even a one-shot confirm=True call."""
        _, _, _, _, log = _wire(tmp_path, monkeypatch)
        server.pbs_remote_delete("remote1", confirm=True)
        outcomes = [e["outcome"] for e in _entries(log) if e["action"] == "pbs_remote_delete"]
        assert "planned" in outcomes, "one-shot confirm executed with no plan recorded"
        assert "ok" in outcomes


# ---------------------------------------------------------------------------
# Secret redaction (load-bearing) — scan on-disk ledger
# ---------------------------------------------------------------------------

_PASSWORD_SENTINEL = "SENTINEL-PBS-PW-X99"
_FINGERPRINT_SENTINEL = "ab:cd:ef:12:34"


class TestPbsRemoteRedaction:
    """The remote password MUST NOT appear anywhere in plan dict or audit ledger.
    The fingerprint MUST appear (it is public — assert it is NOT redacted).
    """

    def _scan_ledger(self, log: str, sentinel: str) -> list[str]:
        """Return all ledger lines that contain the sentinel."""
        with open(log, encoding="utf-8") as f:
            return [line for line in f if sentinel in line]

    # --- pbs_remote_create: plan path ---

    def test_password_not_in_plan_dict(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire(tmp_path, monkeypatch)
        out = server.pbs_remote_create("remote1", "pbs2.example.com", "backup@pbs!tok",
                                       _PASSWORD_SENTINEL,
                                       fingerprint=_FINGERPRINT_SENTINEL)
        dump = json.dumps(out)
        assert _PASSWORD_SENTINEL not in dump, (
            f"password sentinel leaked into plan dict: {dump[:500]}"
        )

    def test_fingerprint_in_plan_dict(self, tmp_path, monkeypatch):
        """Fingerprint is PUBLIC — must appear in the plan response."""
        _, _, _, _, log = _wire(tmp_path, monkeypatch)
        out = server.pbs_remote_create("remote1", "pbs2.example.com", "backup@pbs!tok",
                                       _PASSWORD_SENTINEL,
                                       fingerprint=_FINGERPRINT_SENTINEL)
        dump = json.dumps(out)
        assert _FINGERPRINT_SENTINEL in dump, (
            f"fingerprint (public) not in plan dict — should NOT be redacted: {dump[:500]}"
        )

    def test_password_not_in_ledger_plan_path(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire(tmp_path, monkeypatch)
        server.pbs_remote_create("remote1", "pbs2.example.com", "backup@pbs!tok",
                                 _PASSWORD_SENTINEL,
                                 fingerprint=_FINGERPRINT_SENTINEL)
        leaks = self._scan_ledger(log, _PASSWORD_SENTINEL)
        assert leaks == [], f"password sentinel found in ledger (plan path): {leaks}"

    def test_fingerprint_in_ledger_plan_path(self, tmp_path, monkeypatch):
        """Fingerprint must appear in ledger (NOT redacted) — it's public data."""
        _, _, _, _, log = _wire(tmp_path, monkeypatch)
        server.pbs_remote_create("remote1", "pbs2.example.com", "backup@pbs!tok",
                                 _PASSWORD_SENTINEL,
                                 fingerprint=_FINGERPRINT_SENTINEL)
        with open(log, encoding="utf-8") as f:
            body = f.read()
        assert _FINGERPRINT_SENTINEL in body, (
            "fingerprint (public) absent from ledger — should NOT be redacted"
        )

    # --- pbs_remote_create: confirm (execute) path ---

    def test_password_not_in_plan_dict_confirm_path(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire(tmp_path, monkeypatch)
        out = server.pbs_remote_create("remote1", "pbs2.example.com", "backup@pbs!tok",
                                       _PASSWORD_SENTINEL,
                                       fingerprint=_FINGERPRINT_SENTINEL,
                                       confirm=True)
        assert out["status"] == "ok"
        dump = json.dumps(out)
        assert _PASSWORD_SENTINEL not in dump, (
            f"password sentinel leaked into confirm result: {dump[:500]}"
        )

    def test_password_not_in_ledger_confirm_path(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire(tmp_path, monkeypatch)
        server.pbs_remote_create("remote1", "pbs2.example.com", "backup@pbs!tok",
                                 _PASSWORD_SENTINEL,
                                 fingerprint=_FINGERPRINT_SENTINEL,
                                 confirm=True)
        leaks = self._scan_ledger(log, _PASSWORD_SENTINEL)
        assert leaks == [], f"password sentinel found in ledger (confirm path): {leaks}"

    def test_fingerprint_in_ledger_confirm_path(self, tmp_path, monkeypatch):
        """Fingerprint still appears in ledger on the confirm path."""
        _, _, _, _, log = _wire(tmp_path, monkeypatch)
        server.pbs_remote_create("remote1", "pbs2.example.com", "backup@pbs!tok",
                                 _PASSWORD_SENTINEL,
                                 fingerprint=_FINGERPRINT_SENTINEL,
                                 confirm=True)
        with open(log, encoding="utf-8") as f:
            body = f.read()
        assert _FINGERPRINT_SENTINEL in body, (
            "fingerprint (public) absent from ledger on confirm path"
        )

    # --- pbs_remote_update: password redaction ---

    def test_remote_update_password_not_in_plan_dict(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire(tmp_path, monkeypatch)
        out = server.pbs_remote_update("remote1", password=_PASSWORD_SENTINEL,
                                       fingerprint=_FINGERPRINT_SENTINEL)
        dump = json.dumps(out)
        assert _PASSWORD_SENTINEL not in dump

    def test_remote_update_password_not_in_ledger(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire(tmp_path, monkeypatch)
        server.pbs_remote_update("remote1", password=_PASSWORD_SENTINEL)
        leaks = self._scan_ledger(log, _PASSWORD_SENTINEL)
        assert leaks == [], f"password sentinel found in remote_update ledger: {leaks}"

    def test_remote_update_fingerprint_in_plan(self, tmp_path, monkeypatch):
        _, _, _, _, log = _wire(tmp_path, monkeypatch)
        out = server.pbs_remote_update("remote1", fingerprint=_FINGERPRINT_SENTINEL)
        dump = json.dumps(out)
        assert _FINGERPRINT_SENTINEL in dump

    def test_remote_update_password_not_in_ledger_confirm_path(self, tmp_path, monkeypatch):
        # The confirm path is code-identical to remote_create but separately tested — a regression
        # that put the password into remote_update's _audited detail would otherwise slip through.
        _, _, _, _, log = _wire(tmp_path, monkeypatch)
        server.pbs_remote_update("remote1", password=_PASSWORD_SENTINEL,
                                 fingerprint=_FINGERPRINT_SENTINEL, confirm=True)
        leaks = self._scan_ledger(log, _PASSWORD_SENTINEL)
        assert leaks == [], f"password sentinel found in remote_update ledger (confirm path): {leaks}"

    def test_remote_update_password_not_in_result_confirm_path(self, tmp_path, monkeypatch):
        # The _audited envelope returns the raw backend response as result — assert no password echo.
        _, _, _, _, _ = _wire(tmp_path, monkeypatch)
        out = server.pbs_remote_update("remote1", password=_PASSWORD_SENTINEL, confirm=True)
        assert _PASSWORD_SENTINEL not in json.dumps(out)


# ---------------------------------------------------------------------------
# Backend function calls: confirm-path HTTP verb checks
# ---------------------------------------------------------------------------

class TestBackendCalls:
    def test_datastore_create_posts_to_config_datastore(self, tmp_path, monkeypatch):
        _, _, pbs, _, _ = _wire(tmp_path, monkeypatch)
        server.pbs_datastore_create("mystore", "/mnt/data", confirm=True)
        assert pbs.posts
        assert pbs.posts[0][0] == "/config/datastore"

    def test_datastore_delete_deletes_config_datastore(self, tmp_path, monkeypatch):
        _, _, pbs, _, _ = _wire(tmp_path, monkeypatch)
        server.pbs_datastore_delete("mystore", confirm=True)
        assert pbs.dels
        assert "/config/datastore/mystore" in pbs.dels[0][0]

    def test_snapshot_protected_set_puts_protected_path(self, tmp_path, monkeypatch):
        _, _, pbs, _, _ = _wire(tmp_path, monkeypatch)
        server.pbs_snapshot_protected_set("store1", "ct", "100", 1700000000,
                                          protected=True, confirm=True)
        assert pbs.puts
        assert "protected" in pbs.puts[0][0]

    def test_remote_create_posts_to_config_remote(self, tmp_path, monkeypatch):
        _, _, pbs, _, _ = _wire(tmp_path, monkeypatch)
        server.pbs_remote_create("r1", "pbs.example.com", "backup@pbs!tok", "secret", confirm=True)
        assert pbs.posts
        assert pbs.posts[0][0] == "/config/remote"

    def test_remote_delete_deletes_config_remote(self, tmp_path, monkeypatch):
        _, _, pbs, _, _ = _wire(tmp_path, monkeypatch)
        server.pbs_remote_delete("r1", confirm=True)
        assert pbs.dels
        assert "/config/remote/r1" in pbs.dels[0][0]

    def test_traffic_control_delete_deletes_correct_path(self, tmp_path, monkeypatch):
        _, _, pbs, _, _ = _wire(tmp_path, monkeypatch)
        server.pbs_traffic_control_delete("rule1", confirm=True)
        assert pbs.dels
        assert "/config/traffic-control/rule1" in pbs.dels[0][0]


# ---------------------------------------------------------------------------
# Backend op tests — new read ops (path correctness + name interpolation)
# ---------------------------------------------------------------------------

class TestRemotesList:
    def test_gets_correct_path(self):
        pbs = _FakePbs(get_return=[{"name": "r1"}, {"name": "r2"}])
        remotes_list(pbs)
        assert pbs.gets[0][0] == "/config/remote"

    def test_returns_list(self):
        pbs = _FakePbs(get_return=[{"name": "r1"}])
        result = remotes_list(pbs)
        assert isinstance(result, list)

    def test_strips_password_defensively(self):
        pbs = _FakePbs(get_return=[{"name": "r1", "host": "pbs2.example.com", "password": "LEAK"}])
        result = remotes_list(pbs)
        assert "password" not in result[0]
        assert result[0]["host"] == "pbs2.example.com"

    def test_empty_list_when_none_returned(self):
        pbs = _FakePbs(get_return=None)
        result = remotes_list(pbs)
        assert result == []

    def test_non_list_response_shape_fails_closed(self):
        """A non-list response (malformed/unexpected PBS shape) must be refused, not returned
        verbatim -- the previous fallback bypassed password redaction entirely for any shape
        other than a list."""
        pbs = _FakePbs(get_return={"name": "r1", "password": "LEAK"})
        with pytest.raises(ProximoError):
            remotes_list(pbs)

    def test_non_dict_entry_shape_fails_closed(self):
        """A non-dict ENTRY inside an otherwise-list response must also be refused --
        redaction can only be verified on dict entries."""
        pbs = _FakePbs(get_return=[{"name": "r1"}, "not-a-dict"])
        with pytest.raises(ProximoError):
            remotes_list(pbs)


class TestTrafficControlsList:
    def test_gets_correct_path(self):
        pbs = _FakePbs(get_return=[{"name": "rule1"}])
        traffic_controls_list(pbs)
        assert pbs.gets[0][0] == "/config/traffic-control"

    def test_returns_list(self):
        pbs = _FakePbs(get_return=[{"name": "rule1", "rate-in": 100}])
        result = traffic_controls_list(pbs)
        assert isinstance(result, list)

    def test_empty_list_when_none_returned(self):
        pbs = _FakePbs(get_return=None)
        result = traffic_controls_list(pbs)
        assert result == []


class TestDatastoreGet:
    def test_gets_correct_path_with_name(self):
        pbs = _FakePbs(get_return={"name": "mystore", "path": "/srv/pbs"})
        datastore_get(pbs, "mystore")
        assert pbs.gets[0][0] == "/config/datastore/mystore"

    def test_name_interpolated_in_path(self):
        pbs = _FakePbs(get_return={})
        datastore_get(pbs, "ds-alpha")
        assert pbs.gets[0][0] == "/config/datastore/ds-alpha"

    def test_rejects_invalid_name(self):
        from proximo.backends import ProximoError as PE
        pbs = _FakePbs()
        with pytest.raises(PE):
            datastore_get(pbs, "bad/name")

    def test_returns_dict(self):
        pbs = _FakePbs(get_return={"name": "mystore", "path": "/srv/pbs"})
        result = datastore_get(pbs, "mystore")
        assert isinstance(result, dict)


class TestRemoteGet:
    def test_gets_correct_path_with_name(self):
        pbs = _FakePbs(get_return={"name": "r1", "host": "pbs2.example.com"})
        remote_get(pbs, "r1")
        assert pbs.gets[0][0] == "/config/remote/r1"

    def test_name_interpolated_in_path(self):
        pbs = _FakePbs(get_return={})
        remote_get(pbs, "remote-prod")
        assert pbs.gets[0][0] == "/config/remote/remote-prod"

    def test_strips_password_defensively(self):
        pbs = _FakePbs(get_return={"name": "r1", "host": "pbs2.example.com", "password": "LEAK"})
        result = remote_get(pbs, "r1")
        assert "password" not in result
        assert result["host"] == "pbs2.example.com"

    def test_rejects_invalid_name(self):
        from proximo.backends import ProximoError as PE
        pbs = _FakePbs()
        with pytest.raises(PE):
            remote_get(pbs, "bad/name")


class TestTrafficControlUpsertDispatchFailsClosed:
    """The create-vs-update existence check must abort on an inconclusive read rather than
    silently assuming absence and dispatching a CREATE against a possibly-existing rule."""

    def test_attributeerror_from_existence_check_propagates(self):
        pbs = _FakePbs(raise_on_get=AttributeError("malformed response"))
        with pytest.raises(AttributeError):
            traffic_control_upsert(pbs, "rule1", rate_in=100)
        assert pbs.posts == []  # must NOT have silently created
        assert pbs.puts == []   # must NOT have silently updated either


# ---------------------------------------------------------------------------
# Server wiring — 6 new read-audited PBS tools
# ---------------------------------------------------------------------------

class TestNewPbsReadToolWiring:
    def test_pbs_remotes_list_is_audited(self, tmp_path, monkeypatch):
        _, _, pbs, _, log = _wire(tmp_path, monkeypatch, get_return=[{"name": "r1"}])
        server.pbs_remotes_list()
        assert pbs.gets and pbs.gets[0][0] == "/config/remote"
        assert any(e["action"] == "pbs_remotes_list" and not e["mutation"]
                   for e in _entries(log))

    def test_pbs_remote_get_is_audited(self, tmp_path, monkeypatch):
        _, _, pbs, _, log = _wire(tmp_path, monkeypatch,
                                  get_return={"name": "r1", "host": "pbs2.example.com"})
        server.pbs_remote_get("r1")
        assert pbs.gets and "/config/remote/r1" in pbs.gets[0][0]
        assert any(e["action"] == "pbs_remote_get" and not e["mutation"]
                   for e in _entries(log))

    def test_pbs_traffic_controls_list_is_audited(self, tmp_path, monkeypatch):
        _, _, pbs, _, log = _wire(tmp_path, monkeypatch, get_return=[{"name": "rule1"}])
        server.pbs_traffic_controls_list()
        assert pbs.gets and pbs.gets[0][0] == "/config/traffic-control"
        assert any(e["action"] == "pbs_traffic_controls_list" and not e["mutation"]
                   for e in _entries(log))

    def test_pbs_jobs_list_is_audited(self, tmp_path, monkeypatch):
        _, _, pbs, _, log = _wire(tmp_path, monkeypatch,
                                  get_return=[{"id": "job1", "store": "ds1"}])
        server.pbs_jobs_list("sync")
        assert pbs.gets and pbs.gets[0][0] == "/config/sync"
        assert any(e["action"] == "pbs_jobs_list" and not e["mutation"]
                   for e in _entries(log))

    def test_pbs_tasks_list_is_audited(self, tmp_path, monkeypatch):
        _, _, pbs, _, log = _wire(tmp_path, monkeypatch,
                                  get_return=[{"id": "UPID:pbs:001"}])
        server.pbs_tasks_list()
        assert pbs.gets and "/nodes/localhost/tasks" in pbs.gets[0][0]
        assert any(e["action"] == "pbs_tasks_list" and not e["mutation"]
                   for e in _entries(log))

    def test_pbs_datastore_get_is_audited(self, tmp_path, monkeypatch):
        _, _, pbs, _, log = _wire(tmp_path, monkeypatch,
                                  get_return={"name": "mystore", "path": "/srv/pbs"})
        server.pbs_datastore_get("mystore")
        assert pbs.gets and "/config/datastore/mystore" in pbs.gets[0][0]
        assert any(e["action"] == "pbs_datastore_get" and not e["mutation"]
                   for e in _entries(log))


def test_pbs_pmg_pdm_from_target_verify_tls_falsy():
    # redteam LOW: non-PVE planes must treat 0/off/no as falsy too (was != 'false')
    from proximo.pbs import PbsConfig
    from proximo.pdm import PdmConfig
    from proximo.pmg import PmgConfig
    for falsy in (0, "0", "off", "no", False):
        assert PbsConfig.from_target({"base_url": "https://192.0.2.7:8007",
                                      "token_path": "/x", "ca_bundle": "/ca",
                                      "verify_tls": falsy}).verify_tls is False
        assert PmgConfig.from_target({"base_url": "https://192.0.2.9:8006",
                                      "password_path": "/x", "ca_bundle": "/ca",
                                      "verify_tls": falsy}).verify_tls is False
        assert PdmConfig.from_target({"base_url": "https://192.0.2.11:8443",
                                      "token_path": "/x", "ca_bundle": "/ca",
                                      "verify_tls": falsy}).verify_tls is False
