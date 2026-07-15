"""TDD tests for the PBS datastore-admin plane (Wave 5d, full-surface campaign — the ACTUAL
PBS plane closer, built from the Wave 5c adversarial review's Finding 1+2 endpoint list) —
fully mocked, no live PBS.

Mirrors test_pbs_admin.py's style: a recording fake PBS API, validator tests, backend-function
path/verb/payload tests (exact wire payloads pinned BEFORE implementation — test-first), and
plan-factory risk/blast-radius tests. Headline contracts:
  1. `pbs_group_delete` (DELETE /admin/datastore/{store}/groups) — bulk group delete, MORE
     destructive than single-snapshot delete: RISK_HIGH, blast radius names the whole group +
     ALL its snapshots; returns a synchronous stats OBJECT (not a UPID, not null).
  2. `pbs_datastore_prune` (POST .../prune-datastore) — whole-datastore prune, schema-distinct
     from the shipped single-group `pbs_prune`; dry_run defaults True in OUR tool (deliberate
     safe-default flip — the schema's own default is false), mirroring the shipped pbs_prune.
  3. `pbs_namespace_move` — whole-tree relocation with delete-source defaulting TRUE upstream:
     RISK_HIGH, every where-data-lands param disclosed.
"""

from __future__ import annotations

import pytest

from proximo.backends import ProximoError
from proximo.pbs_datastore_admin import (
    datastore_active_operations,
    datastore_mount,
    datastore_prune,
    datastore_rrd,
    datastore_s3_refresh,
    datastore_unmount,
    datastores_usage,
    group_delete,
    group_move,
    group_notes_get,
    group_notes_set,
    groups_list,
    namespace_move,
    plan_datastore_mount,
    plan_datastore_prune,
    plan_datastore_s3_refresh,
    plan_datastore_unmount,
    plan_group_delete,
    plan_group_move,
    plan_group_notes_set,
    plan_namespace_move,
    remote_scan,
    remote_scan_groups,
    remote_scan_namespaces,
    snapshot_protected_get,
)
from proximo.planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM

# ---------------------------------------------------------------------------
# Recording fake
# ---------------------------------------------------------------------------

class _Api:
    """Recording fake for PbsBackend (HTTP verb tracking, no live network)."""

    def __init__(self, get_return=None, post_return=None, put_return=None, delete_return=None):
        self._get_return = get_return
        self._post_return = post_return
        self._put_return = put_return
        self._delete_return = delete_return
        self.gets: list[tuple] = []
        self.posts: list[tuple] = []
        self.puts: list[tuple] = []
        self.dels: list[tuple] = []

    def _get(self, path: str, params=None):
        self.gets.append((path, params))
        return self._get_return

    def _post(self, path: str, data=None):
        self.posts.append((path, data))
        return self._post_return

    def _put(self, path: str, data=None):
        self.puts.append((path, data))
        return self._put_return

    def _delete(self, path: str, params=None):
        self.dels.append((path, params))
        return self._delete_return


# ---------------------------------------------------------------------------
# Module structure
# ---------------------------------------------------------------------------

def test_module_docstring_names_key_facts():
    import proximo.pbs_datastore_admin as m
    doc = m.__doc__ or ""
    assert "prune-datastore" in doc
    assert "move-namespace" in doc
    assert "delete-source" in doc or "delete_source" in doc
    assert "Wave 5c" in doc  # traces its own origin to the review


# ---------------------------------------------------------------------------
# Backend functions — group reads
# ---------------------------------------------------------------------------

class TestGroupsList:
    def test_path_and_params(self):
        api = _Api(get_return=[{"backup-id": "100", "backup-type": "vm"}])
        out = groups_list(api, store="ds1")
        assert out == [{"backup-id": "100", "backup-type": "vm"}]
        assert api.gets[-1] == ("/admin/datastore/ds1/groups", {})

    def test_ns_forwarded(self):
        api = _Api(get_return=[])
        groups_list(api, store="ds1", ns="team/prod")
        assert api.gets[-1] == ("/admin/datastore/ds1/groups", {"ns": "team/prod"})

    def test_bad_store_rejected(self):
        with pytest.raises(ProximoError):
            groups_list(_Api(), store="bad/store")


class TestGroupNotesGet:
    def test_path_and_params(self):
        api = _Api(get_return="my group notes")
        out = group_notes_get(api, store="ds1", backup_type="vm", backup_id="100")
        assert out == "my group notes"
        assert api.gets[-1] == (
            "/admin/datastore/ds1/group-notes",
            {"backup-type": "vm", "backup-id": "100"},
        )

    def test_ns_forwarded(self):
        api = _Api(get_return="")
        group_notes_get(api, store="ds1", backup_type="ct", backup_id="101", ns="a/b")
        _, params = api.gets[-1]
        assert params == {"backup-type": "ct", "backup-id": "101", "ns": "a/b"}

    def test_bad_backup_type_rejected(self):
        with pytest.raises(ProximoError):
            group_notes_get(_Api(), store="ds1", backup_type="bogus", backup_id="100")


class TestSnapshotProtectedGet:
    def test_path_and_params(self):
        api = _Api(get_return=True)
        out = snapshot_protected_get(
            api, store="ds1", backup_type="vm", backup_id="100", backup_time=1700000000,
        )
        assert out is True
        assert api.gets[-1] == (
            "/admin/datastore/ds1/protected",
            {"backup-type": "vm", "backup-id": "100", "backup-time": 1700000000},
        )

    def test_ns_forwarded(self):
        api = _Api(get_return=False)
        snapshot_protected_get(
            api, store="ds1", backup_type="vm", backup_id="100", backup_time=1700000000,
            ns="team",
        )
        _, params = api.gets[-1]
        assert params["ns"] == "team"

    def test_bad_backup_time_rejected(self):
        with pytest.raises(ProximoError):
            snapshot_protected_get(
                _Api(), store="ds1", backup_type="vm", backup_id="100", backup_time=0,
            )


class TestDatastoreRrd:
    def test_path_and_params(self):
        api = _Api(get_return=None)
        out = datastore_rrd(api, store="ds1", cf="AVERAGE", timeframe="hour")
        assert out == {}
        assert api.gets[-1] == (
            "/admin/datastore/ds1/rrd", {"cf": "AVERAGE", "timeframe": "hour"},
        )

    def test_decade_timeframe_accepted(self):
        api = _Api(get_return=None)
        datastore_rrd(api, store="ds1", cf="MAX", timeframe="decade")
        _, params = api.gets[-1]
        assert params == {"cf": "MAX", "timeframe": "decade"}

    def test_bad_cf_rejected(self):
        with pytest.raises(ProximoError):
            datastore_rrd(_Api(), store="ds1", cf="MIN", timeframe="hour")

    def test_bad_timeframe_rejected(self):
        with pytest.raises(ProximoError):
            datastore_rrd(_Api(), store="ds1", cf="MAX", timeframe="century")


class TestDatastoreActiveOperations:
    def test_path(self):
        api = _Api(get_return=None)
        out = datastore_active_operations(api, store="ds1")
        assert out == {}
        assert api.gets[-1] == ("/admin/datastore/ds1/active-operations", None)


class TestDatastoresUsage:
    def test_path(self):
        api = _Api(get_return=[{"store": "ds1", "avail": 100}])
        out = datastores_usage(api)
        assert out == [{"store": "ds1", "avail": 100}]
        assert api.gets[-1] == ("/status/datastore-usage", None)


class TestRemoteScan:
    def test_scan_path(self):
        api = _Api(get_return=[{"store": "remote-ds"}])
        out = remote_scan(api, name="myremote")
        assert out == [{"store": "remote-ds"}]
        assert api.gets[-1] == ("/config/remote/myremote/scan", None)

    def test_scan_groups_path_and_namespace_param(self):
        """Wire param is `namespace` on this endpoint — NOT `ns` (schema-verified divergence
        from every /admin/datastore sibling)."""
        api = _Api(get_return=[])
        remote_scan_groups(api, name="myremote", store="remote-ds", namespace="a/b")
        assert api.gets[-1] == (
            "/config/remote/myremote/scan/remote-ds/groups", {"namespace": "a/b"},
        )

    def test_scan_groups_no_namespace(self):
        api = _Api(get_return=[])
        remote_scan_groups(api, name="myremote", store="remote-ds")
        assert api.gets[-1] == ("/config/remote/myremote/scan/remote-ds/groups", {})

    def test_scan_namespaces_path(self):
        api = _Api(get_return=[])
        remote_scan_namespaces(api, name="myremote", store="remote-ds")
        assert api.gets[-1] == ("/config/remote/myremote/scan/remote-ds/namespaces", None)

    def test_bad_remote_name_rejected(self):
        with pytest.raises(ProximoError):
            remote_scan(_Api(), name="a")  # < 3 chars


# ---------------------------------------------------------------------------
# Backend functions — mutations
# ---------------------------------------------------------------------------

class TestGroupDelete:
    def test_path_verb_and_params(self):
        stats = {"removed-groups": 1, "removed-snapshots": 7, "protected-snapshots": 0}
        api = _Api(delete_return=stats)
        out = group_delete(api, store="ds1", backup_type="vm", backup_id="100")
        assert out == stats
        assert api.dels[-1] == (
            "/admin/datastore/ds1/groups",
            {"backup-type": "vm", "backup-id": "100"},
        )

    def test_ns_and_error_on_protected_forwarded(self):
        api = _Api(delete_return={})
        group_delete(
            api, store="ds1", backup_type="vm", backup_id="100", ns="a",
            error_on_protected=False,
        )
        _, params = api.dels[-1]
        assert params == {
            "backup-type": "vm", "backup-id": "100", "ns": "a", "error-on-protected": False,
        }

    def test_backup_id_required_non_none(self):
        with pytest.raises(ProximoError):
            group_delete(_Api(), store="ds1", backup_type="vm", backup_id="bad id\n")


class TestGroupNotesSet:
    def test_path_verb_and_params(self):
        api = _Api()
        group_notes_set(api, store="ds1", backup_type="vm", backup_id="100", notes="line1\nline2")
        assert api.puts[-1] == (
            "/admin/datastore/ds1/group-notes",
            {"backup-type": "vm", "backup-id": "100", "notes": "line1\nline2"},
        )

    def test_ns_forwarded(self):
        api = _Api()
        group_notes_set(api, store="ds1", backup_type="vm", backup_id="100", notes="x", ns="a")
        _, data = api.puts[-1]
        assert data["ns"] == "a"


class TestMountUnmountS3Refresh:
    def test_mount(self):
        api = _Api(post_return="UPID:pbs:1:0:0:0:mount:ds1:root@pam:")
        out = datastore_mount(api, store="ds1")
        assert out.startswith("UPID:")
        assert api.posts[-1] == ("/admin/datastore/ds1/mount", None)

    def test_unmount(self):
        api = _Api(post_return="UPID:pbs:1:0:0:0:unmount:ds1:root@pam:")
        datastore_unmount(api, store="ds1")
        assert api.posts[-1] == ("/admin/datastore/ds1/unmount", None)

    def test_s3_refresh_is_put(self):
        api = _Api(put_return="UPID:pbs:1:0:0:0:s3refresh:ds1:root@pam:")
        datastore_s3_refresh(api, store="ds1")
        assert api.puts[-1] == ("/admin/datastore/ds1/s3-refresh", None)
        assert not api.posts


class TestGroupMove:
    def test_minimal(self):
        api = _Api(post_return="UPID:x")
        group_move(api, store="ds1", backup_type="vm", backup_id="100")
        assert api.posts[-1] == (
            "/admin/datastore/ds1/move-group",
            {"backup-type": "vm", "backup-id": "100"},
        )

    def test_full_field_set(self):
        api = _Api(post_return="UPID:x")
        group_move(
            api, store="ds1", backup_type="vm", backup_id="100", ns="src/a",
            target_ns="dst/b", merge_group=False,
        )
        _, data = api.posts[-1]
        assert data == {
            "backup-type": "vm", "backup-id": "100", "ns": "src/a",
            "target-ns": "dst/b", "merge-group": False,
        }


class TestNamespaceMove:
    def test_required_fields(self):
        api = _Api(post_return="UPID:x")
        namespace_move(api, store="ds1", ns="src", target_ns="dst")
        assert api.posts[-1] == (
            "/admin/datastore/ds1/move-namespace", {"ns": "src", "target-ns": "dst"},
        )

    def test_full_field_set(self):
        api = _Api(post_return="UPID:x")
        namespace_move(
            api, store="ds1", ns="src", target_ns="", delete_source=False, max_depth=2,
            merge_groups=False,
        )
        _, data = api.posts[-1]
        assert data == {
            "ns": "src", "target-ns": "", "delete-source": False, "max-depth": 2,
            "merge-groups": False,
        }

    def test_empty_source_ns_rejected(self):
        """Stricter-than-schema rail mirroring plan_namespace_delete: the ROOT namespace cannot
        be relocated (the schema's own ns pattern technically allows '', but a root-move is
        meaningless)."""
        with pytest.raises(ProximoError):
            namespace_move(_Api(), store="ds1", ns="", target_ns="dst")

    def test_max_depth_bounds(self):
        with pytest.raises(ProximoError):
            namespace_move(_Api(), store="ds1", ns="src", target_ns="dst", max_depth=8)


class TestDatastorePrune:
    def test_dry_run_default_true_ours_not_schemas(self):
        """The schema's own dry-run default is FALSE; this tool deliberately flips the default
        to True — the same safe-default flip the shipped pbs_prune (single-group) made."""
        api = _Api(post_return="UPID:x")
        datastore_prune(api, store="ds1", keep_last=3)
        _, data = api.posts[-1]
        assert data["dry-run"] is True

    def test_path_and_full_field_set(self):
        api = _Api(post_return="UPID:x")
        datastore_prune(
            api, store="ds1", keep_last=1, keep_hourly=2, keep_daily=3, keep_weekly=4,
            keep_monthly=5, keep_yearly=6, ns="a", max_depth=2, dry_run=False,
        )
        path, data = api.posts[-1]
        assert path == "/admin/datastore/ds1/prune-datastore"
        assert data == {
            "keep-last": 1, "keep-hourly": 2, "keep-daily": 3, "keep-weekly": 4,
            "keep-monthly": 5, "keep-yearly": 6, "ns": "a", "max-depth": 2,
        }  # dry-run OMITTED when False (schema default) — no misleading dry-run=0 on the wire

    def test_keep_hourly_exists_unlike_group_prune(self):
        """prune-datastore accepts keep-hourly — the shipped single-group pbs_prune does not
        expose it; schema-distinct surfaces."""
        api = _Api(post_return="UPID:x")
        datastore_prune(api, store="ds1", keep_hourly=4, dry_run=False)
        _, data = api.posts[-1]
        assert data == {"keep-hourly": 4}


# ---------------------------------------------------------------------------
# Plan factories
# ---------------------------------------------------------------------------

class TestPlanGroupDelete:
    def test_risk_high(self):
        plan = plan_group_delete(store="ds1", backup_type="vm", backup_id="100")
        assert plan.risk == RISK_HIGH

    def test_blast_radius_names_whole_group_and_all_snapshots(self):
        plan = plan_group_delete(store="ds1", backup_type="vm", backup_id="100", ns="a")
        joined = " ".join(plan.blast_radius)
        assert "ALL" in joined and "snapshot" in joined.lower()
        assert "vm/100" in joined or ("vm" in joined and "100" in joined)
        assert "ds1" in plan.target + joined
        assert "'a'" in joined or "a" in plan.target

    def test_more_destructive_than_snapshot_delete_stated(self):
        plan = plan_group_delete(store="ds1", backup_type="vm", backup_id="100")
        text = plan.change + " ".join(plan.blast_radius) + plan.note
        assert "pbs_snapshot_delete" in text  # names the narrower alternative

    def test_error_on_protected_false_disclosed(self):
        plan = plan_group_delete(
            store="ds1", backup_type="vm", backup_id="100", error_on_protected=False,
        )
        joined = " ".join(plan.blast_radius)
        assert "protected" in joined.lower()

    def test_is_pure(self):
        assert plan_group_delete(store="ds1", backup_type="vm", backup_id="100").current == {}


class TestPlanGroupNotesSet:
    def test_risk_low_and_captures(self):
        api = _Api(get_return="old notes")
        plan = plan_group_notes_set(api, store="ds1", backup_type="vm", backup_id="100", notes="new")
        assert plan.risk == RISK_LOW
        assert plan.current == {"notes": "old notes"}
        assert plan.complete is True

    def test_capture_failure_declares(self):
        class _Broken(_Api):
            def _get(self, path, params=None):
                raise RuntimeError("down")
        plan = plan_group_notes_set(_Broken(), store="ds1", backup_type="vm", backup_id="100", notes="new")
        assert plan.complete is False


class TestPlanMountUnmountS3Refresh:
    def test_mount_medium(self):
        plan = plan_datastore_mount(store="ds1")
        assert plan.risk == RISK_MEDIUM
        assert "ds1" in plan.target + plan.change

    def test_unmount_medium_and_names_interruption(self):
        plan = plan_datastore_unmount(store="ds1")
        assert plan.risk == RISK_MEDIUM
        joined = " ".join(plan.blast_radius)
        assert "unavailable" in joined.lower() or "abort" in joined.lower() or "fail" in joined.lower()

    def test_s3_refresh_medium(self):
        plan = plan_datastore_s3_refresh(store="ds1")
        assert plan.risk == RISK_MEDIUM
        joined = " ".join(plan.blast_radius)
        assert "cache" in joined.lower()


class TestPlanGroupMove:
    def test_risk_medium(self):
        plan = plan_group_move(store="ds1", backup_type="vm", backup_id="100", target_ns="dst")
        assert plan.risk == RISK_MEDIUM

    def test_discloses_source_and_target_ns(self):
        plan = plan_group_move(
            store="ds1", backup_type="vm", backup_id="100", ns="src/a", target_ns="dst/b",
        )
        text = plan.change + " ".join(plan.blast_radius)
        assert "src/a" in text
        assert "dst/b" in text

    def test_merge_group_default_disclosed(self):
        """merge-group defaults TRUE upstream — the plan must say what the default does even
        when the caller didn't set it."""
        plan = plan_group_move(store="ds1", backup_type="vm", backup_id="100", target_ns="dst")
        text = plan.change + " ".join(plan.blast_radius) + plan.note
        assert "merge" in text.lower()


class TestPlanNamespaceMove:
    def test_risk_high(self):
        plan = plan_namespace_move(store="ds1", ns="src", target_ns="dst")
        assert plan.risk == RISK_HIGH

    def test_discloses_delete_source_default_true(self):
        """delete-source defaults TRUE upstream — the plan must disclose the source namespace
        is removed even when the caller never set the param."""
        plan = plan_namespace_move(store="ds1", ns="src", target_ns="dst")
        text = plan.change + " ".join(plan.blast_radius)
        assert "delete" in text.lower() or "remov" in text.lower()
        assert "src" in text and "dst" in text

    def test_delete_source_false_disclosed(self):
        plan = plan_namespace_move(store="ds1", ns="src", target_ns="dst", delete_source=False)
        text = " ".join(plan.blast_radius)
        assert "kept" in text.lower() or "not removed" in text.lower() or "delete_source=False" in text

    def test_names_broken_job_references(self):
        plan = plan_namespace_move(store="ds1", ns="src", target_ns="dst")
        joined = " ".join(plan.blast_radius)
        assert "job" in joined.lower()


class TestPlanDatastorePrune:
    def test_dry_run_true_is_low(self):
        plan = plan_datastore_prune(store="ds1", keep_last=3, dry_run=True)
        assert plan.risk == RISK_LOW

    def test_dry_run_false_is_high(self):
        plan = plan_datastore_prune(store="ds1", keep_last=3, dry_run=False)
        assert plan.risk == RISK_HIGH

    def test_no_keep_policy_disclosed(self):
        plan = plan_datastore_prune(store="ds1", dry_run=False)
        text = plan.change + " ".join(plan.blast_radius)
        assert "no keep policy" in text.lower() or "all may be pruned" in text.lower()

    def test_whole_datastore_scope_disclosed(self):
        """The plan must distinguish this from the single-group pbs_prune — namespace scope +
        recursion, not one group."""
        plan = plan_datastore_prune(store="ds1", keep_last=1, ns="a", max_depth=3, dry_run=False)
        text = plan.change + " ".join(plan.blast_radius) + plan.note
        assert "'a'" in text or "ns" in text
        assert "max" in text.lower() or "recursion" in text.lower() or "depth" in text.lower()
