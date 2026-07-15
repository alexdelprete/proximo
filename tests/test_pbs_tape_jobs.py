"""TDD tests for the PBS tape media CATALOG + tape-backup JOBS + backup/restore plane (Wave 4d,
full-surface campaign) — fully mocked, no live PBS. CLOSES Wave 4 (PBS tape).

Mirrors test_pbs_tape_config.py's/test_pbs_tape_media.py's/test_pbs_tape_ops.py's style: a
recording fake PBS API, validator rejection tests (\\Z-anchored), backend-function
path/verb/payload tests, and plan-factory risk/blast-radius/purity tests.

Covers: validators (media uuid, digest, backup-id/type, media status, notification-mode,
notify-user, owner, max-depth, worker-threads, group-filter, namespace mapping, snapshot spec,
store mapping, media_set ref); backend functions for all 15 ops (6 read, 9 mutation); plan
factories (RISK_LOW job-create, RISK_MEDIUM most mutations, RISK_HIGH media_destroy/restore —
see module docstring's RISK RATING section); the "at least one of label_text/uuid" rail on
destroy/move; the GET-verb-but-gated-as-mutation shape of media_destroy; the null-return schema
quirks (job-run, media-status-get); module structure.
"""

from __future__ import annotations

import pytest

from proximo.backends import ProximoError
from proximo.pbs_tape_jobs import (
    _check_backup_id_filter,
    _check_backup_type,
    _check_digest,
    _check_group_filter_list,
    _check_max_depth,
    _check_media_set_ref,
    _check_media_status,
    _check_media_uuid,
    _check_namespace_mapping_list,
    _check_notification_mode,
    _check_notify_user,
    _check_owner,
    _check_snapshot_list,
    _check_store_mapping,
    _check_worker_threads,
    plan_tape_backup,
    plan_tape_backup_job_create,
    plan_tape_backup_job_delete,
    plan_tape_backup_job_run,
    plan_tape_backup_job_update,
    plan_tape_media_destroy,
    plan_tape_media_move,
    plan_tape_media_status_set,
    plan_tape_restore,
    tape_backup,
    tape_backup_job_create,
    tape_backup_job_delete,
    tape_backup_job_get,
    tape_backup_job_list,
    tape_backup_job_run,
    tape_backup_job_update,
    tape_media_content,
    tape_media_destroy,
    tape_media_list,
    tape_media_move,
    tape_media_sets,
    tape_media_status_get,
    tape_media_status_set,
    tape_restore,
)
from proximo.planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM

_UUID = "12345678-1234-1234-1234-123456789abc"
_UUID2 = "87654321-4321-4321-4321-cba987654321"
_UPID = "UPID:node1:00000001:00000000:00000000:tapebackup:store1:root@pam:"

# ---------------------------------------------------------------------------
# Recording fake
# ---------------------------------------------------------------------------

class _Api:
    """Recording fake for PbsBackend (HTTP verb tracking, no live network)."""

    def __init__(self, get_return=None, post_return=None):
        self._get_return = get_return
        self._post_return = post_return
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
        return None

    def _delete(self, path: str, params=None):
        self.dels.append((path, params))
        return None


# ---------------------------------------------------------------------------
# Module structure
# ---------------------------------------------------------------------------

def test_module_docstring_names_schema_facts():
    import proximo.pbs_tape_jobs as m
    doc = m.__doc__ or ""
    assert "destroy" in doc.lower()
    assert "upid" in doc.lower()
    assert "adversarial" in doc.lower()
    assert "namespace" in doc.lower()


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

class TestCheckMediaUuid:
    def test_valid(self):
        assert _check_media_uuid(_UUID) == _UUID

    def test_uppercase_rejected(self):
        with pytest.raises(ProximoError):
            _check_media_uuid(_UUID.upper())

    def test_wrong_shape_rejected(self):
        with pytest.raises(ProximoError):
            _check_media_uuid("not-a-uuid")

    def test_trailing_newline_rejected(self):
        with pytest.raises(ProximoError):
            _check_media_uuid(_UUID + "\n")


class TestCheckDigest:
    def test_valid(self):
        d = "a" * 64
        assert _check_digest(d) == d

    def test_wrong_length_rejected(self):
        with pytest.raises(ProximoError):
            _check_digest("a" * 63)

    def test_uppercase_rejected(self):
        with pytest.raises(ProximoError):
            _check_digest("A" * 64)


class TestCheckBackupIdFilter:
    def test_valid_alnum(self):
        assert _check_backup_id_filter("guest1") == "guest1"

    def test_leading_underscore_allowed(self):
        """Fresh shape, deliberately different from pbs.py's own _check_backup_id (module
        docstring: no length cap, leading underscore allowed)."""
        assert _check_backup_id_filter("_guest1") == "_guest1"

    def test_slash_rejected(self):
        with pytest.raises(ProximoError):
            _check_backup_id_filter("a/b")

    def test_trailing_newline_rejected(self):
        with pytest.raises(ProximoError):
            _check_backup_id_filter("guest1\n")


class TestCheckBackupType:
    @pytest.mark.parametrize("bt", ["vm", "ct", "host"])
    def test_valid(self, bt):
        assert _check_backup_type(bt) == bt

    def test_invalid_rejected(self):
        with pytest.raises(ProximoError):
            _check_backup_type("container")


class TestCheckMediaStatus:
    @pytest.mark.parametrize("s", ["full", "damaged", "retired"])
    def test_valid(self, s):
        assert _check_media_status(s) == s

    def test_writable_rejected(self):
        """Module docstring fact #6: PBS's own prose forbids 'writable' even though it's in the
        raw schema enum."""
        with pytest.raises(ProximoError):
            _check_media_status("writable")

    def test_unknown_rejected(self):
        with pytest.raises(ProximoError):
            _check_media_status("unknown")

    def test_garbage_rejected(self):
        with pytest.raises(ProximoError):
            _check_media_status("broken")


class TestCheckNotificationMode:
    @pytest.mark.parametrize("m", ["legacy-sendmail", "notification-system"])
    def test_valid(self, m):
        assert _check_notification_mode(m) == m

    def test_invalid_rejected(self):
        with pytest.raises(ProximoError):
            _check_notification_mode("email")


class TestCheckNotifyUser:
    def test_valid(self):
        assert _check_notify_user("root@pam") == "root@pam"

    def test_too_short_rejected(self):
        with pytest.raises(ProximoError):
            _check_notify_user("a@")

    def test_no_realm_rejected(self):
        with pytest.raises(ProximoError):
            _check_notify_user("rootonly")

    def test_control_char_rejected(self):
        with pytest.raises(ProximoError):
            _check_notify_user("ro\x00ot@pam")


class TestCheckOwner:
    def test_valid_bare_userid(self):
        assert _check_owner("root@pam") == "root@pam"

    def test_valid_with_token(self):
        assert _check_owner("root@pam!mytoken") == "root@pam!mytoken"

    def test_no_realm_rejected(self):
        with pytest.raises(ProximoError):
            _check_owner("rootonly")


class TestCheckMaxDepth:
    def test_valid_bounds(self):
        assert _check_max_depth(0) == 0
        assert _check_max_depth(7) == 7

    def test_out_of_range_rejected(self):
        with pytest.raises(ProximoError):
            _check_max_depth(8)
        with pytest.raises(ProximoError):
            _check_max_depth(-1)

    def test_non_int_rejected(self):
        with pytest.raises(ProximoError):
            _check_max_depth("abc")


class TestCheckWorkerThreads:
    def test_valid_bounds(self):
        assert _check_worker_threads(1) == 1
        assert _check_worker_threads(32) == 32

    def test_out_of_range_rejected(self):
        with pytest.raises(ProximoError):
            _check_worker_threads(0)
        with pytest.raises(ProximoError):
            _check_worker_threads(33)


class TestCheckGroupFilterList:
    def test_valid(self):
        assert _check_group_filter_list(["type:vm", "exclude:group:g1"]) == ["type:vm", "exclude:group:g1"]

    def test_empty_entry_rejected(self):
        with pytest.raises(ProximoError):
            _check_group_filter_list([""])

    def test_control_char_rejected(self):
        with pytest.raises(ProximoError):
            _check_group_filter_list(["type:vm\x00"])


class TestCheckNamespaceMappingList:
    def test_valid(self):
        assert _check_namespace_mapping_list(["store=ds1,source=a,target=b"]) == ["store=ds1,source=a,target=b"]

    def test_missing_store_prefix_rejected(self):
        with pytest.raises(ProximoError):
            _check_namespace_mapping_list(["source=a"])

    def test_control_char_rejected(self):
        with pytest.raises(ProximoError):
            _check_namespace_mapping_list(["store=ds1\x00"])


class TestCheckSnapshotList:
    def test_valid_no_namespace(self):
        assert _check_snapshot_list(["ds1:vm/100/2026-07-15T12:00:00Z"]) == ["ds1:vm/100/2026-07-15T12:00:00Z"]

    def test_valid_with_namespace(self):
        spec = "ds1:ns/prod/ns/web/ct/101/2026-07-15T12:00:00Z"
        assert _check_snapshot_list([spec]) == [spec]

    def test_bad_shape_rejected(self):
        with pytest.raises(ProximoError):
            _check_snapshot_list(["not-a-snapshot-spec"])

    def test_bad_type_rejected(self):
        with pytest.raises(ProximoError):
            _check_snapshot_list(["ds1:container/100/2026-07-15T12:00:00Z"])


class TestCheckStoreMapping:
    def test_single_target(self):
        assert _check_store_mapping("ds1") == "ds1"

    def test_mapping_list(self):
        """NOTE: PBS's own schema description uses the example 'a=b,e' — but 'e' is 1 char,
        violating the item schema's own minLength:3 (a genuine schema self-contradiction, see
        pbs_tape_jobs.py module docstring fact #4). This validator enforces the formal 3-65
        bound, so the doc's own literal example would be rejected here — use a bound-respecting
        equivalent instead."""
        assert _check_store_mapping("aaa=bbb,ccc") == "aaa=bbb,ccc"

    def test_documented_example_violates_its_own_minlength(self):
        """PBS's own description example 'a=b,e' is rejected by the formal per-item minLength:3
        the same schema declares — proves this module follows the STRICTER formal constraint,
        not the (self-contradictory) prose example."""
        with pytest.raises(ProximoError):
            _check_store_mapping("a=b,e")

    def test_empty_segment_rejected(self):
        with pytest.raises(ProximoError):
            _check_store_mapping("a=b,,e")

    def test_too_short_entry_rejected(self):
        with pytest.raises(ProximoError):
            _check_store_mapping("ab")

    def test_bad_charset_rejected(self):
        with pytest.raises(ProximoError):
            _check_store_mapping("a/b")


class TestCheckMediaSetRef:
    def test_valid_plain_string(self):
        """Module docstring fact #5: restore's own media-set param has NO uuid pattern — a plain
        string passes, unlike /tape/media/content's media-set FILTER (which is UUID-shaped)."""
        assert _check_media_set_ref("not-a-uuid-but-thats-fine-here") == "not-a-uuid-but-thats-fine-here"

    def test_uuid_also_valid(self):
        assert _check_media_set_ref(_UUID) == _UUID

    def test_empty_rejected(self):
        with pytest.raises(ProximoError):
            _check_media_set_ref("")

    def test_too_long_rejected(self):
        with pytest.raises(ProximoError):
            _check_media_set_ref("a" * 129)

    def test_control_char_rejected(self):
        with pytest.raises(ProximoError):
            _check_media_set_ref("a\x00b")

    def test_esc_rejected(self):
        """Review finding 3 (Wave 4d): the original hand-rolled blocklist covered only
        \\x00-\\x0d — \\x1b (ESC, the ANSI escape-sequence driver) slipped through into
        Plan.target/ledger target. Must use the module's own complete [^\\x00-\\x1f\\x7f]
        class like every sibling validator."""
        with pytest.raises(ProximoError):
            _check_media_set_ref("legit\x1b[31mfake-error\x1b[0m")

    def test_del_rejected(self):
        """Review finding 3: \\x7f (DEL) is a control character too — same completeness fix."""
        with pytest.raises(ProximoError):
            _check_media_set_ref("legit\x7fbad")

    def test_x0e_through_x1f_rejected(self):
        """Review finding 3: the whole \\x0e-\\x1f band the truncated blocklist missed."""
        for c in ("\x0e", "\x14", "\x1f"):
            with pytest.raises(ProximoError):
                _check_media_set_ref(f"legit{c}bad")


# ---------------------------------------------------------------------------
# Backend functions — reads
# ---------------------------------------------------------------------------

class TestTapeMediaList:
    def test_default_update_status_false(self):
        """Module docstring fact #12: Proximo's own default overrides PBS's upstream default
        (true) — bare call must send update-status=false explicitly."""
        api = _Api(get_return=[])
        tape_media_list(api)
        assert api.gets == [("/tape/media/list", {"update-status": False})]

    def test_update_status_true_forwarded(self):
        api = _Api(get_return=[])
        tape_media_list(api, update_status=True)
        assert api.gets[0][1]["update-status"] is True

    def test_pool_filter_forwarded(self):
        api = _Api(get_return=[])
        tape_media_list(api, pool="pool1")
        assert api.gets[0][1]["pool"] == "pool1"

    def test_update_status_changer_forwarded(self):
        api = _Api(get_return=[])
        tape_media_list(api, update_status_changer="changer1")
        assert api.gets[0][1]["update-status-changer"] == "changer1"

    def test_empty_api_returns_empty_list(self):
        api = _Api(get_return=None)
        assert tape_media_list(api) == []


class TestTapeMediaContent:
    def test_no_filters(self):
        api = _Api(get_return=[])
        tape_media_content(api)
        assert api.gets == [("/tape/media/content", {})]

    def test_all_filters_forwarded(self):
        api = _Api(get_return=[])
        tape_media_content(
            api, backup_id="guest1", backup_type="vm", label_text="tape1",
            media=_UUID, media_set=_UUID2, pool="pool1",
        )
        _, params = api.gets[0]
        assert params == {
            "backup-id": "guest1", "backup-type": "vm", "label-text": "tape1",
            "media": _UUID, "media-set": _UUID2, "pool": "pool1",
        }

    def test_invalid_backup_type_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_media_content(api, backup_type="bogus")


class TestTapeMediaSets:
    def test_calls_correct_path(self):
        api = _Api(get_return=[{"pool": "pool1"}])
        result = tape_media_sets(api)
        assert api.gets == [("/tape/media/media-sets", None)]
        assert result == [{"pool": "pool1"}]

    def test_empty_api_returns_empty_list(self):
        api = _Api(get_return=None)
        assert tape_media_sets(api) == []


class TestTapeMediaStatusGet:
    def test_correct_path(self):
        api = _Api(get_return={"status": "writable"})
        result = tape_media_status_get(api, _UUID)
        assert api.gets == [(f"/tape/media/list/{_UUID}/status", None)]
        assert result == {"status": "writable"}

    def test_null_response_falls_back_to_empty_dict(self):
        """Module docstring fact #3: schema declares this returns null — best-effort passthrough."""
        api = _Api(get_return=None)
        assert tape_media_status_get(api, _UUID) == {}

    def test_invalid_uuid_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_media_status_get(api, "not-a-uuid")


class TestTapeBackupJobList:
    def test_calls_correct_path(self):
        api = _Api(get_return=[{"id": "job1"}])
        result = tape_backup_job_list(api)
        assert api.gets == [("/config/tape-backup-job", None)]
        assert result == [{"id": "job1"}]


class TestTapeBackupJobGet:
    def test_correct_path(self):
        api = _Api(get_return={"id": "job1"})
        result = tape_backup_job_get(api, "job1")
        assert api.gets == [("/config/tape-backup-job/job1", None)]
        assert result["id"] == "job1"

    def test_invalid_job_id_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_backup_job_get(api, "ab")  # too short (min 3)


# ---------------------------------------------------------------------------
# Backend functions — mutations, Media catalog
# ---------------------------------------------------------------------------

class TestTapeMediaDestroy:
    def test_get_verb_with_label_text(self):
        """THE HEADLINE WELD: the underlying wire call is a real GET, even though this is a
        gated mutation."""
        api = _Api()
        tape_media_destroy(api, label_text="tape1")
        assert api.gets == [("/tape/media/destroy", {"label-text": "tape1"})]

    def test_get_verb_with_uuid_and_force(self):
        api = _Api()
        tape_media_destroy(api, uuid=_UUID, force=True)
        assert api.gets == [("/tape/media/destroy", {"uuid": _UUID, "force": True})]

    def test_neither_identifier_raises(self):
        """Module docstring fact #7: deliberate stricter-than-schema safety rail."""
        api = _Api()
        with pytest.raises(ProximoError):
            tape_media_destroy(api)
        assert api.gets == []

    def test_invalid_label_text_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_media_destroy(api, label_text="a")  # too short


class TestTapeMediaStatusSet:
    def test_status_forwarded(self):
        api = _Api()
        tape_media_status_set(api, _UUID, status="retired")
        assert api.posts == [(f"/tape/media/list/{_UUID}/status", {"status": "retired"})]

    def test_status_none_sends_empty_body(self):
        """Omitting status is PBS's documented way to CLEAR the override."""
        api = _Api()
        tape_media_status_set(api, _UUID)
        assert api.posts == [(f"/tape/media/list/{_UUID}/status", {})]

    def test_writable_rejected(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_media_status_set(api, _UUID, status="writable")


class TestTapeMediaMove:
    def test_vault_name_forwarded(self):
        api = _Api()
        tape_media_move(api, uuid=_UUID, vault_name="offsite1")
        assert api.posts == [("/tape/media/move", {"uuid": _UUID, "vault-name": "offsite1"})]

    def test_omitted_vault_sends_no_vault_field(self):
        """Module docstring RISK RATING: omitting vault_name sets OFFLINE, not a no-op — but the
        wire payload simply omits the field (PBS applies its own offline default)."""
        api = _Api()
        tape_media_move(api, label_text="tape1")
        assert api.posts == [("/tape/media/move", {"label-text": "tape1"})]

    def test_neither_identifier_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_media_move(api, vault_name="offsite1")
        assert api.posts == []


# ---------------------------------------------------------------------------
# Backend functions — mutations, Tape backup jobs
# ---------------------------------------------------------------------------

class TestTapeBackupJobCreate:
    def test_minimal_required_fields(self):
        api = _Api()
        tape_backup_job_create(api, "job1", "drive1", "pool1", "store1")
        assert api.posts == [(
            "/config/tape-backup-job",
            {"id": "job1", "drive": "drive1", "pool": "pool1", "store": "store1"},
        )]

    def test_all_optional_fields_forwarded(self):
        api = _Api()
        tape_backup_job_create(
            api, "job1", "drive1", "pool1", "store1",
            comment="c1", eject_media=True, export_media_set=False,
            group_filter=["type:vm"], latest_only=True, max_depth=3,
            notification_mode="legacy-sendmail", notify_user="root@pam", ns="prod",
            schedule="daily", worker_threads=4,
        )
        _, data = api.posts[0]
        assert data == {
            "id": "job1", "drive": "drive1", "pool": "pool1", "store": "store1",
            "comment": "c1", "eject-media": True, "export-media-set": False,
            "group-filter": ["type:vm"], "latest-only": True, "max-depth": 3,
            "notification-mode": "legacy-sendmail", "notify-user": "root@pam", "ns": "prod",
            "schedule": "daily", "worker-threads": 4,
        }

    def test_invalid_job_id_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_backup_job_create(api, "ab", "drive1", "pool1", "store1")

    # -- Review finding 2 (Wave 4d): comment/ns were forwarded via bare str() with zero
    # validation despite the schema's own maxLength/pattern constraints (comment: maxLength 128,
    # no control chars; ns: maxLength 256, /-separated identifier components, <=8 levels). --

    def test_oversize_comment_rejected(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_backup_job_create(api, "job1", "drive1", "pool1", "store1", comment="x" * 129)
        assert api.posts == []

    def test_control_char_comment_rejected(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_backup_job_create(api, "job1", "drive1", "pool1", "store1",
                                   comment="ok\n\x01injected")
        assert api.posts == []

    def test_oversize_ns_rejected(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_backup_job_create(api, "job1", "drive1", "pool1", "store1", ns="y" * 257)
        assert api.posts == []

    def test_traversal_ns_rejected(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_backup_job_create(api, "job1", "drive1", "pool1", "store1",
                                   ns="/../etc/passwd")
        assert api.posts == []

    def test_too_deep_ns_rejected(self):
        """The tape ns schema caps at 8 /-separated components ({0,7} + final)."""
        api = _Api()
        with pytest.raises(ProximoError):
            tape_backup_job_create(api, "job1", "drive1", "pool1", "store1",
                                   ns="/".join(["x"] * 9))
        assert api.posts == []

    def test_valid_nested_ns_accepted(self):
        api = _Api()
        tape_backup_job_create(api, "job1", "drive1", "pool1", "store1", ns="prod/vms")
        assert api.posts[0][1]["ns"] == "prod/vms"


class TestTapeBackupJobUpdate:
    def test_puts_partial_fields(self):
        api = _Api()
        tape_backup_job_update(api, "job1", schedule="weekly")
        assert api.puts == [("/config/tape-backup-job/job1", {"schedule": "weekly"})]

    def test_none_kwargs_excluded(self):
        api = _Api()
        tape_backup_job_update(api, "job1")
        assert api.puts[0][1] == {}

    def test_delete_list_forwarded(self):
        api = _Api()
        tape_backup_job_update(api, "job1", delete=["comment", "schedule"])
        assert api.puts[0][1]["delete"] == ["comment", "schedule"]

    def test_digest_forwarded(self):
        api = _Api()
        tape_backup_job_update(api, "job1", digest="d" * 64)
        assert api.puts[0][1]["digest"] == "d" * 64

    def test_oversize_comment_rejected(self):
        """Review finding 2 (Wave 4d) — same shared-helper path as create, proven on update too."""
        api = _Api()
        with pytest.raises(ProximoError):
            tape_backup_job_update(api, "job1", comment="x" * 129)
        assert api.puts == []

    def test_control_char_ns_rejected(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_backup_job_update(api, "job1", ns="prod\x1bvms")
        assert api.puts == []


class TestTapeBackupJobDelete:
    def test_deletes_correct_path(self):
        api = _Api()
        tape_backup_job_delete(api, "job1")
        assert api.dels == [("/config/tape-backup-job/job1", {})]

    def test_digest_forwarded(self):
        api = _Api()
        tape_backup_job_delete(api, "job1", digest="c" * 64)
        assert api.dels[0][1] == {"digest": "c" * 64}


class TestTapeBackupJobRun:
    def test_posts_to_correct_path_no_body(self):
        api = _Api(post_return=None)
        tape_backup_job_run(api, "job1")
        assert api.posts == [("/tape/backup/job1", {})]

    def test_invalid_job_id_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_backup_job_run(api, "ab")


# ---------------------------------------------------------------------------
# Backend functions — mutations, One-off backup + restore
# ---------------------------------------------------------------------------

class TestTapeBackup:
    def test_minimal_required_fields(self):
        api = _Api(post_return=_UPID)
        result = tape_backup(api, "drive1", "pool1", "store1")
        assert api.posts == [("/tape/backup", {"drive": "drive1", "pool": "pool1", "store": "store1"})]
        assert result == _UPID

    def test_all_optional_fields_forwarded(self):
        api = _Api(post_return=_UPID)
        tape_backup(
            api, "drive1", "pool1", "store1",
            eject_media=True, export_media_set=True, force_media_set=True,
            group_filter=["type:ct"], latest_only=True, max_depth=2,
            notification_mode="notification-system", notify_user="root@pam", ns="prod",
            worker_threads=8,
        )
        _, data = api.posts[0]
        assert data == {
            "drive": "drive1", "pool": "pool1", "store": "store1",
            "eject-media": True, "export-media-set": True, "force-media-set": True,
            "group-filter": ["type:ct"], "latest-only": True, "max-depth": 2,
            "notification-mode": "notification-system", "notify-user": "root@pam", "ns": "prod",
            "worker-threads": 8,
        }

    def test_no_schedule_or_id_param_exists(self):
        import inspect
        sig = inspect.signature(tape_backup)
        assert "schedule" not in sig.parameters
        assert "job_id" not in sig.parameters
        assert "id" not in sig.parameters

    def test_oversize_ns_rejected(self):
        """Review finding 2 (Wave 4d): the one-off backup's own inline ns handling had the same
        bare-str() gap as _job_extra_fields'."""
        api = _Api()
        with pytest.raises(ProximoError):
            tape_backup(api, "drive1", "pool1", "store1", ns="y" * 257)
        assert api.posts == []

    def test_control_char_ns_rejected(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_backup(api, "drive1", "pool1", "store1", ns="prod\x00vms")
        assert api.posts == []


class TestTapeRestore:
    def test_minimal_required_fields(self):
        api = _Api(post_return=_UPID)
        result = tape_restore(api, "drive1", _UUID, "store1")
        assert api.posts == [("/tape/restore", {"drive": "drive1", "media-set": _UUID, "store": "store1"})]
        assert result == _UPID

    def test_store_mapping_forwarded(self):
        api = _Api(post_return=_UPID)
        tape_restore(api, "drive1", _UUID, "aaa=bbb,ccc")
        assert api.posts[0][1]["store"] == "aaa=bbb,ccc"

    def test_all_optional_fields_forwarded(self):
        api = _Api(post_return=_UPID)
        tape_restore(
            api, "drive1", _UUID, "store1",
            namespaces=["store=ds1,target=prod"],
            notification_mode="legacy-sendmail", notify_user="root@pam", owner="root@pam!tok",
            snapshots=["ds1:vm/100/2026-07-15T12:00:00Z"],
        )
        _, data = api.posts[0]
        assert data == {
            "drive": "drive1", "media-set": _UUID, "store": "store1",
            "namespaces": ["store=ds1,target=prod"],
            "notification-mode": "legacy-sendmail", "notify-user": "root@pam",
            "owner": "root@pam!tok", "snapshots": ["ds1:vm/100/2026-07-15T12:00:00Z"],
        }

    def test_invalid_snapshot_spec_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_restore(api, "drive1", _UUID, "store1", snapshots=["garbage"])


# ---------------------------------------------------------------------------
# Plan factories — Media catalog
# ---------------------------------------------------------------------------

class TestPlanTapeMediaDestroy:
    def test_is_high_risk(self):
        plan = plan_tape_media_destroy(label_text="tape1")
        assert plan.risk == RISK_HIGH

    def test_current_is_empty_pure_plan(self):
        plan = plan_tape_media_destroy(uuid=_UUID)
        assert plan.current == {}

    def test_no_undo_note(self):
        plan = plan_tape_media_destroy(label_text="tape1")
        assert "no undo" in plan.note.lower()

    def test_neither_identifier_raises(self):
        with pytest.raises(ProximoError):
            plan_tape_media_destroy()


class TestPlanTapeMediaStatusSet:
    def test_is_medium_risk(self):
        plan = plan_tape_media_status_set(_UUID, status="damaged")
        assert plan.risk == RISK_MEDIUM

    def test_clear_message(self):
        plan = plan_tape_media_status_set(_UUID)
        assert "clear" in plan.change.lower()

    def test_invalid_status_raises(self):
        with pytest.raises(ProximoError):
            plan_tape_media_status_set(_UUID, status="unknown")


class TestPlanTapeMediaMove:
    def test_is_medium_risk(self):
        plan = plan_tape_media_move(uuid=_UUID, vault_name="offsite1")
        assert plan.risk == RISK_MEDIUM

    def test_offline_message_when_vault_omitted(self):
        plan = plan_tape_media_move(label_text="tape1")
        assert "offline" in plan.change.lower()

    def test_neither_identifier_raises(self):
        with pytest.raises(ProximoError):
            plan_tape_media_move(vault_name="offsite1")


# ---------------------------------------------------------------------------
# Plan factories — Tape backup jobs
# ---------------------------------------------------------------------------

class TestPlanTapeBackupJobCreate:
    def test_is_low_risk(self):
        plan = plan_tape_backup_job_create("job1", "drive1", "pool1", "store1")
        assert plan.risk == RISK_LOW

    def test_current_is_empty(self):
        plan = plan_tape_backup_job_create("job1", "drive1", "pool1", "store1")
        assert plan.current == {}

    def test_change_includes_identifiers(self):
        plan = plan_tape_backup_job_create("job1", "drive1", "pool1", "store1")
        assert "job1" in plan.change and "drive1" in plan.change

    def test_invalid_job_id_raises(self):
        with pytest.raises(ProximoError):
            plan_tape_backup_job_create("ab", "drive1", "pool1", "store1")

    def test_oversize_comment_rejected_at_plan_time(self):
        """Review finding 2 (Wave 4d) — plan-time validation parity: a bad comment must be caught
        at PLAN time, not only at execution."""
        with pytest.raises(ProximoError):
            plan_tape_backup_job_create("job1", "drive1", "pool1", "store1", comment="x" * 129)

    def test_bad_ns_rejected_at_plan_time(self):
        with pytest.raises(ProximoError):
            plan_tape_backup_job_create("job1", "drive1", "pool1", "store1", ns="/../bad")


class TestPlanTapeBackupJobUpdate:
    def test_reads_current_from_api(self):
        api = _Api(get_return={"id": "job1", "drive": "drive1"})
        plan = plan_tape_backup_job_update(api, "job1", schedule="weekly")
        assert plan.risk == RISK_MEDIUM
        assert plan.current == {"id": "job1", "drive": "drive1"}

    def test_no_fields_changed_message(self):
        api = _Api(get_return={"id": "job1"})
        plan = plan_tape_backup_job_update(api, "job1")
        assert "no fields changed" in plan.change

    def test_delete_empty_list_rejected(self):
        """Wave 5b review finding 1: `is not None`, not truthiness — but delete=[] is REJECTED,
        not disclosed. httpx's form encoding drops an empty-list value entirely, so a disclosed
        "delete=[]" never matched what confirm=True actually sent."""
        api = _Api(get_return={"id": "job1"})
        with pytest.raises(ProximoError):
            plan_tape_backup_job_update(api, "job1", delete=[])


class TestPlanTapeBackupJobDelete:
    def test_is_medium_risk(self):
        api = _Api(get_return={"id": "job1"})
        plan = plan_tape_backup_job_delete(api, "job1")
        assert plan.risk == RISK_MEDIUM

    def test_silent_stop_language(self):
        api = _Api(get_return={"id": "job1"})
        plan = plan_tape_backup_job_delete(api, "job1")
        assert "silently" in " ".join(plan.blast_radius).lower()


class TestPlanTapeBackupJobRun:
    def test_is_medium_risk(self):
        plan = plan_tape_backup_job_run("job1")
        assert plan.risk == RISK_MEDIUM

    def test_current_is_empty_pure_plan(self):
        plan = plan_tape_backup_job_run("job1")
        assert plan.current == {}

    def test_schema_quirk_noted(self):
        plan = plan_tape_backup_job_run("job1")
        assert "null" in plan.note.lower()


# ---------------------------------------------------------------------------
# Plan factories — One-off backup + restore
# ---------------------------------------------------------------------------

class TestPlanTapeBackup:
    def test_is_medium_risk(self):
        plan = plan_tape_backup("drive1", "pool1", "store1")
        assert plan.risk == RISK_MEDIUM

    def test_current_is_empty_pure_plan(self):
        plan = plan_tape_backup("drive1", "pool1", "store1")
        assert plan.current == {}

    def test_upid_undo_note(self):
        plan = plan_tape_backup("drive1", "pool1", "store1")
        assert "upid" in plan.note.lower()

    def test_bad_ns_rejected_at_plan_time(self):
        """Review finding 2 (Wave 4d) — plan-time validation parity for the one-off backup's ns."""
        with pytest.raises(ProximoError):
            plan_tape_backup("drive1", "pool1", "store1", ns="y" * 257)


class TestPlanTapeRestore:
    def test_is_high_risk(self):
        plan = plan_tape_restore("drive1", _UUID, "store1")
        assert plan.risk == RISK_HIGH

    def test_current_is_empty_pure_plan(self):
        plan = plan_tape_restore("drive1", _UUID, "store1")
        assert plan.current == {}

    def test_whole_media_set_scope_by_default(self):
        plan = plan_tape_restore("drive1", _UUID, "store1")
        assert "whole media-set" in plan.change.lower()

    def test_selective_scope_when_snapshots_given(self):
        plan = plan_tape_restore(
            "drive1", _UUID, "store1", snapshots=["ds1:vm/100/2026-07-15T12:00:00Z"],
        )
        assert "snapshots=" in plan.change

    def test_overwrite_semantics_smoke_confirm_language(self):
        plan = plan_tape_restore("drive1", _UUID, "store1")
        assert "smoke-confirm" in " ".join(plan.blast_radius).lower()

    def test_invalid_store_mapping_raises(self):
        with pytest.raises(ProximoError):
            plan_tape_restore("drive1", _UUID, "a/b")

    # -- Review finding 1 (Wave 4d, HIGH): the dry-run PLAN for the wave's own RISK_HIGH tool
    # silently dropped namespaces/owner/notify_user/notification_mode after validating them — a
    # namespace remap or ownership reassignment was invisible to a caller reviewing the plan
    # before confirm=True. Every optional param must be surfaced in `change`; namespaces and
    # owner must ALSO appear in blast_radius (where restored data lands + who owns it). --

    def test_namespaces_surfaced_in_change_and_blast_radius(self):
        ns_map = "store=backup2,source=prod/vms,target=quarantine/vms"
        plan = plan_tape_restore("drive1", _UUID, "store1", namespaces=[ns_map])
        assert ns_map in plan.change, "namespace remapping must be visible in the plan change text"
        blast = " ".join(plan.blast_radius)
        assert ns_map in blast, "namespace remapping must be called out in blast_radius (WHERE the data lands)"

    def test_owner_surfaced_in_change_and_blast_radius(self):
        plan = plan_tape_restore("drive1", _UUID, "store1", owner="someuser@pve!some-token")
        assert "someuser@pve!some-token" in plan.change, "owner reassignment must be visible in the change text"
        blast = " ".join(plan.blast_radius)
        assert "someuser@pve!some-token" in blast, (
            "owner must be called out in blast_radius (WHO owns the restored data)"
        )

    def test_notify_user_surfaced_in_change(self):
        plan = plan_tape_restore("drive1", _UUID, "store1", notify_user="admin@pbs")
        assert "admin@pbs" in plan.change

    def test_notification_mode_surfaced_in_change(self):
        plan = plan_tape_restore("drive1", _UUID, "store1", notification_mode="legacy-sendmail")
        assert "legacy-sendmail" in plan.change

    def test_default_namespaces_and_owner_language_when_omitted(self):
        """When namespaces/owner are omitted the plan must not be silent either — the defaults
        (source-mirroring namespaces auto-created; PBS's own default ownership) are part of
        where-and-who too."""
        plan = plan_tape_restore("drive1", _UUID, "store1")
        blast = " ".join(plan.blast_radius).lower()
        assert "auto-created" in blast
