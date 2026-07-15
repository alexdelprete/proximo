"""TDD tests for the PBS tape hardware config plane (Wave 4a, full-surface campaign) — fully
mocked, no live PBS.

Mirrors test_pbs_notifications.py's / test_pbs_acme.py's style: a recording fake PBS API,
validator rejection tests (\\Z-anchored), backend-function path/verb/payload tests, and
plan-factory risk/blast-radius tests.

Covers: validators (tape id, digest, changer-drivenum, export-slots); backend functions for all
12 ops (6 read, 6 mutation); plan factories (RISK_MEDIUM create/update, RISK_LOW delete — see
module docstring's RISK RATING section); module structure.
"""

from __future__ import annotations

import pytest

from proximo.backends import ProximoError
from proximo.pbs_tape_config import (
    _check_changer_drivenum,
    _check_digest,
    _check_export_slots,
    _check_tape_id,
    plan_tape_changer_create,
    plan_tape_changer_delete,
    plan_tape_changer_update,
    plan_tape_drive_create,
    plan_tape_drive_delete,
    plan_tape_drive_update,
    tape_changer_create,
    tape_changer_delete,
    tape_changer_get,
    tape_changer_list,
    tape_changer_update,
    tape_drive_create,
    tape_drive_delete,
    tape_drive_get,
    tape_drive_list,
    tape_drive_update,
    tape_scan_changers,
    tape_scan_drives,
)
from proximo.planning import RISK_LOW, RISK_MEDIUM

# ---------------------------------------------------------------------------
# Recording fake
# ---------------------------------------------------------------------------

class _Api:
    """Recording fake for PbsBackend (HTTP verb tracking, no live network)."""

    def __init__(self, get_return=None):
        self._get_return = get_return
        self.gets: list[str] = []
        self.posts: list[tuple] = []
        self.puts: list[tuple] = []
        self.dels: list[tuple] = []

    def _get(self, path: str, params=None):
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


# ---------------------------------------------------------------------------
# Module structure
# ---------------------------------------------------------------------------

def test_module_docstring_names_schema_facts():
    import proximo.pbs_tape_config as m
    doc = m.__doc__ or ""
    assert "digest" in doc.lower()
    assert "export-slots" in doc.lower() or "export_slots" in doc.lower()


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

class TestCheckTapeId:
    def test_valid_simple(self):
        assert _check_tape_id("drive1") == "drive1"

    def test_valid_with_dot_underscore_hyphen(self):
        assert _check_tape_id("lto-9.a_1") == "lto-9.a_1"

    def test_leading_underscore_accepted(self):
        """Schema pattern allows a leading underscore (module docstring fact #2) — mirrored
        as-is, unlike pbs_notifications.py's stricter alnum-lead-only charset."""
        assert _check_tape_id("_drive1") == "_drive1"

    def test_min_length_three_enforced(self):
        with pytest.raises(ProximoError):
            _check_tape_id("ab")

    def test_min_length_three_accepted(self):
        assert _check_tape_id("abc") == "abc"

    def test_max_length_32_enforced(self):
        with pytest.raises(ProximoError):
            _check_tape_id("a" * 33)

    def test_max_length_32_accepted(self):
        assert _check_tape_id("a" * 32) == "a" * 32

    def test_slash_raises(self):
        with pytest.raises(ProximoError):
            _check_tape_id("name/slash")

    def test_trailing_newline_raises(self):
        with pytest.raises(ProximoError):
            _check_tape_id("drive1\n")

    def test_empty_raises(self):
        with pytest.raises(ProximoError):
            _check_tape_id("")

    def test_control_char_raises(self):
        with pytest.raises(ProximoError):
            _check_tape_id("dr\x00ive1")

    def test_leading_dot_rejected(self):
        with pytest.raises(ProximoError):
            _check_tape_id(".drive1")


class TestCheckDigest:
    def test_valid(self):
        d = "a" * 64
        assert _check_digest(d) == d

    def test_uppercase_hex_rejected(self):
        with pytest.raises(ProximoError):
            _check_digest("A" * 64)

    def test_wrong_length_rejected(self):
        with pytest.raises(ProximoError):
            _check_digest("a" * 63)

    def test_trailing_newline_rejected(self):
        with pytest.raises(ProximoError):
            _check_digest("a" * 64 + "\n")


class TestCheckChangerDrivenum:
    def test_valid_zero(self):
        assert _check_changer_drivenum(0) == 0

    def test_valid_max(self):
        assert _check_changer_drivenum(255) == 255

    def test_below_min_rejected(self):
        with pytest.raises(ProximoError):
            _check_changer_drivenum(-1)

    def test_above_max_rejected(self):
        with pytest.raises(ProximoError):
            _check_changer_drivenum(256)

    def test_non_integer_rejected(self):
        with pytest.raises(ProximoError):
            _check_changer_drivenum("not-a-number")


class TestCheckExportSlots:
    def test_valid_single(self):
        assert _check_export_slots("1") == "1"

    def test_valid_multiple(self):
        assert _check_export_slots("1,2,3") == "1,2,3"

    def test_empty_string_rejected(self):
        with pytest.raises(ProximoError):
            _check_export_slots("")

    def test_empty_segment_rejected(self):
        with pytest.raises(ProximoError):
            _check_export_slots("1,,3")

    def test_zero_rejected(self):
        with pytest.raises(ProximoError):
            _check_export_slots("0")

    def test_negative_rejected(self):
        with pytest.raises(ProximoError):
            _check_export_slots("-1")

    def test_non_integer_rejected(self):
        with pytest.raises(ProximoError):
            _check_export_slots("abc")


# ---------------------------------------------------------------------------
# Backend functions — reads
# ---------------------------------------------------------------------------

class TestTapeDriveList:
    def test_calls_correct_path(self):
        api = _Api(get_return=[{"name": "drive1", "path": "/dev/sg0"}])
        result = tape_drive_list(api)
        assert api.gets == ["/config/drive"]
        assert result == [{"name": "drive1", "path": "/dev/sg0"}]

    def test_empty_api_returns_empty_list(self):
        api = _Api(get_return=None)
        assert tape_drive_list(api) == []


class TestTapeDriveGet:
    def test_correct_path(self):
        api = _Api(get_return={"name": "drive1", "path": "/dev/sg0"})
        result = tape_drive_get(api, "drive1")
        assert api.gets == ["/config/drive/drive1"]
        assert result["name"] == "drive1"

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_drive_get(api, "ab")


class TestTapeChangerList:
    def test_calls_correct_path(self):
        api = _Api(get_return=[{"name": "chg1", "path": "/dev/sg4"}])
        result = tape_changer_list(api)
        assert api.gets == ["/config/changer"]
        assert result == [{"name": "chg1", "path": "/dev/sg4"}]

    def test_empty_api_returns_empty_list(self):
        api = _Api(get_return=None)
        assert tape_changer_list(api) == []


class TestTapeChangerGet:
    def test_correct_path(self):
        api = _Api(get_return={"name": "chg1", "path": "/dev/sg4"})
        result = tape_changer_get(api, "chg1")
        assert api.gets == ["/config/changer/chg1"]
        assert result["name"] == "chg1"

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_changer_get(api, "ab")


class TestTapeScanDrives:
    def test_calls_correct_path_no_params(self):
        api = _Api(get_return=[{"kind": "tape", "path": "/dev/sg0", "vendor": "sentinel-vendor-a"}])
        result = tape_scan_drives(api)
        assert api.gets == ["/tape/scan-drives"]
        assert result[0]["vendor"] == "sentinel-vendor-a"

    def test_empty_api_returns_empty_list(self):
        api = _Api(get_return=None)
        assert tape_scan_drives(api) == []


class TestTapeScanChangers:
    def test_calls_correct_path_no_params(self):
        api = _Api(get_return=[{"kind": "changer", "path": "/dev/sg4", "vendor": "sentinel-vendor-b"}])
        result = tape_scan_changers(api)
        assert api.gets == ["/tape/scan-changers"]
        assert result[0]["vendor"] == "sentinel-vendor-b"

    def test_empty_api_returns_empty_list(self):
        api = _Api(get_return=None)
        assert tape_scan_changers(api) == []


# ---------------------------------------------------------------------------
# Backend functions — mutations, Drives
# ---------------------------------------------------------------------------

class TestTapeDriveCreate:
    def test_posts_to_correct_path(self):
        api = _Api()
        tape_drive_create(api, "drive1", "/dev/sg0")
        assert len(api.posts) == 1
        path, data = api.posts[0]
        assert path == "/config/drive"
        assert data == {"name": "drive1", "path": "/dev/sg0"}

    def test_changer_and_drivenum_forwarded(self):
        api = _Api()
        tape_drive_create(api, "drive1", "/dev/sg0", changer="chg1", changer_drivenum=2)
        _, data = api.posts[0]
        assert data["changer"] == "chg1"
        assert data["changer-drivenum"] == 2

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_drive_create(api, "ab", "/dev/sg0")

    def test_invalid_changer_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_drive_create(api, "drive1", "/dev/sg0", changer="ab")

    def test_invalid_changer_drivenum_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_drive_create(api, "drive1", "/dev/sg0", changer_drivenum=999)


class TestTapeDriveUpdate:
    def test_puts_to_correct_path(self):
        api = _Api()
        tape_drive_update(api, "drive1", path="/dev/sg1")
        assert len(api.puts) == 1
        path, data = api.puts[0]
        assert path == "/config/drive/drive1"
        assert data == {"path": "/dev/sg1"}

    def test_none_kwargs_excluded(self):
        api = _Api()
        tape_drive_update(api, "drive1")
        _, data = api.puts[0]
        assert data == {}

    def test_digest_forwarded_and_validated(self):
        api = _Api()
        digest = "b" * 64
        tape_drive_update(api, "drive1", digest=digest)
        _, data = api.puts[0]
        assert data["digest"] == digest

    def test_invalid_digest_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_drive_update(api, "drive1", digest="not-hex")

    def test_delete_list_forwarded(self):
        api = _Api()
        tape_drive_update(api, "drive1", delete=["changer", "changer-drivenum"])
        _, data = api.puts[0]
        assert data["delete"] == ["changer", "changer-drivenum"]

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_drive_update(api, "ab")


class TestTapeDriveDelete:
    def test_deletes_correct_path(self):
        api = _Api()
        tape_drive_delete(api, "drive1")
        assert api.dels[0][0] == "/config/drive/drive1"

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_drive_delete(api, "ab")


# ---------------------------------------------------------------------------
# Backend functions — mutations, Changers
# ---------------------------------------------------------------------------

class TestTapeChangerCreate:
    def test_posts_to_correct_path(self):
        api = _Api()
        tape_changer_create(api, "chg1", "/dev/sg4")
        assert len(api.posts) == 1
        path, data = api.posts[0]
        assert path == "/config/changer"
        assert data == {"name": "chg1", "path": "/dev/sg4"}

    def test_eject_and_export_slots_forwarded(self):
        api = _Api()
        tape_changer_create(api, "chg1", "/dev/sg4", eject_before_unload=True, export_slots="1,2")
        _, data = api.posts[0]
        assert data["eject-before-unload"] is True
        assert data["export-slots"] == "1,2"

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_changer_create(api, "ab", "/dev/sg4")

    def test_invalid_export_slots_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_changer_create(api, "chg1", "/dev/sg4", export_slots="abc")


class TestTapeChangerUpdate:
    def test_puts_to_correct_path(self):
        api = _Api()
        tape_changer_update(api, "chg1", path="/dev/sg5")
        assert len(api.puts) == 1
        path, data = api.puts[0]
        assert path == "/config/changer/chg1"
        assert data == {"path": "/dev/sg5"}

    def test_none_kwargs_excluded(self):
        api = _Api()
        tape_changer_update(api, "chg1")
        _, data = api.puts[0]
        assert data == {}

    def test_digest_forwarded_and_validated(self):
        api = _Api()
        digest = "c" * 64
        tape_changer_update(api, "chg1", digest=digest)
        _, data = api.puts[0]
        assert data["digest"] == digest

    def test_invalid_digest_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_changer_update(api, "chg1", digest="not-hex")

    def test_delete_list_forwarded(self):
        api = _Api()
        tape_changer_update(api, "chg1", delete=["export-slots", "eject-before-unload"])
        _, data = api.puts[0]
        assert data["delete"] == ["export-slots", "eject-before-unload"]

    def test_invalid_export_slots_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_changer_update(api, "chg1", export_slots="abc")

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_changer_update(api, "ab")


class TestTapeChangerDelete:
    def test_deletes_correct_path(self):
        api = _Api()
        tape_changer_delete(api, "chg1")
        assert api.dels[0][0] == "/config/changer/chg1"

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_changer_delete(api, "ab")


# ---------------------------------------------------------------------------
# Plan factories — Drives
# ---------------------------------------------------------------------------

class TestPlanTapeDriveCreate:
    def test_is_medium_risk(self):
        plan = plan_tape_drive_create("drive1", "/dev/sg0")
        assert plan.risk == RISK_MEDIUM

    def test_current_is_empty(self):
        plan = plan_tape_drive_create("drive1", "/dev/sg0")
        assert plan.current == {}

    def test_target_correct(self):
        plan = plan_tape_drive_create("drive1", "/dev/sg0")
        assert plan.target == "pbs/config/drive/drive1"

    def test_change_includes_name_and_path(self):
        plan = plan_tape_drive_create("drive1", "/dev/sg0")
        assert "drive1" in plan.change and "/dev/sg0" in plan.change

    def test_no_undo_primitive_implied(self):
        plan = plan_tape_drive_create("drive1", "/dev/sg0")
        assert "no snapshot" in plan.note.lower()

    def test_invalid_name_raises(self):
        with pytest.raises(ProximoError):
            plan_tape_drive_create("ab", "/dev/sg0")

    def test_invalid_changer_drivenum_raises(self):
        with pytest.raises(ProximoError):
            plan_tape_drive_create("drive1", "/dev/sg0", changer_drivenum=999)


class TestPlanTapeDriveUpdate:
    def test_reads_current_from_api(self):
        api = _Api(get_return={"name": "drive1", "path": "/dev/sg0"})
        plan = plan_tape_drive_update(api, "drive1", path="/dev/sg1")
        assert plan.risk == RISK_MEDIUM
        assert plan.current == {"name": "drive1", "path": "/dev/sg0"}

    def test_change_includes_new_path(self):
        api = _Api(get_return={"name": "drive1"})
        plan = plan_tape_drive_update(api, "drive1", path="/dev/sg9")
        assert "/dev/sg9" in plan.change

    def test_no_fields_changed_message(self):
        api = _Api(get_return={"name": "drive1"})
        plan = plan_tape_drive_update(api, "drive1")
        assert "no fields changed" in plan.change

    def test_empty_delete_list_rejected(self):
        """Wave 5b review finding 1 corrects the Wave 4a claim above: delete=[] is REJECTED, not
        disclosed. httpx's form encoding drops an empty-list value entirely, so a disclosed
        "delete=[]" never matched what confirm=True actually sent — a PLAN/PROVE parity gap.
        `is not None` (not truthiness) is still the contract; the empty case now raises loudly."""
        api = _Api(get_return={"name": "drive1"})
        with pytest.raises(ProximoError):
            plan_tape_drive_update(api, "drive1", delete=[])

    def test_bad_digest_rejected_at_plan_time(self):
        api = _Api(get_return={"name": "drive1"})
        with pytest.raises(ProximoError, match="digest"):
            plan_tape_drive_update(api, "drive1", digest="not-a-sha256")

    def test_no_implied_undo_in_note(self):
        api = _Api(get_return={"name": "drive1"})
        plan = plan_tape_drive_update(api, "drive1")
        assert "no snapshot" in plan.note.lower()

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            plan_tape_drive_update(api, "ab")


class TestPlanTapeDriveDelete:
    def test_is_low_risk(self):
        api = _Api(get_return={"name": "drive1"})
        plan = plan_tape_drive_delete(api, "drive1")
        assert plan.risk == RISK_LOW

    def test_reads_current_from_api(self):
        api = _Api(get_return={"name": "drive1", "path": "/dev/sg0"})
        plan = plan_tape_drive_delete(api, "drive1")
        assert plan.current == {"name": "drive1", "path": "/dev/sg0"}

    def test_re_creatable_in_note(self):
        api = _Api(get_return={"name": "drive1"})
        plan = plan_tape_drive_delete(api, "drive1")
        assert "re-creat" in plan.note.lower()

    def test_warn_about_job_failure(self):
        api = _Api(get_return={"name": "drive1"})
        plan = plan_tape_drive_delete(api, "drive1")
        assert "WARN" in plan.note.upper()

    def test_does_not_touch_hardware_or_media(self):
        api = _Api(get_return={"name": "drive1"})
        plan = plan_tape_drive_delete(api, "drive1")
        haystack = " ".join(plan.blast_radius).lower()
        assert "untouched" in haystack

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            plan_tape_drive_delete(api, "ab")


# ---------------------------------------------------------------------------
# Plan factories — Changers
# ---------------------------------------------------------------------------

class TestPlanTapeChangerCreate:
    def test_is_medium_risk(self):
        plan = plan_tape_changer_create("chg1", "/dev/sg4")
        assert plan.risk == RISK_MEDIUM

    def test_current_is_empty(self):
        plan = plan_tape_changer_create("chg1", "/dev/sg4")
        assert plan.current == {}

    def test_target_correct(self):
        plan = plan_tape_changer_create("chg1", "/dev/sg4")
        assert plan.target == "pbs/config/changer/chg1"

    def test_change_includes_name_and_path(self):
        plan = plan_tape_changer_create("chg1", "/dev/sg4")
        assert "chg1" in plan.change and "/dev/sg4" in plan.change

    def test_invalid_name_raises(self):
        with pytest.raises(ProximoError):
            plan_tape_changer_create("ab", "/dev/sg4")

    def test_invalid_export_slots_raises(self):
        with pytest.raises(ProximoError):
            plan_tape_changer_create("chg1", "/dev/sg4", export_slots="abc")


class TestPlanTapeChangerUpdate:
    def test_reads_current_from_api(self):
        api = _Api(get_return={"name": "chg1", "path": "/dev/sg4"})
        plan = plan_tape_changer_update(api, "chg1", path="/dev/sg5")
        assert plan.risk == RISK_MEDIUM
        assert plan.current == {"name": "chg1", "path": "/dev/sg4"}

    def test_change_includes_new_path(self):
        api = _Api(get_return={"name": "chg1"})
        plan = plan_tape_changer_update(api, "chg1", path="/dev/sg9")
        assert "/dev/sg9" in plan.change

    def test_bad_digest_rejected_at_plan_time(self):
        api = _Api(get_return={"name": "chg1"})
        with pytest.raises(ProximoError, match="digest"):
            plan_tape_changer_update(api, "chg1", digest="not-a-sha256")

    def test_bad_export_slots_rejected_at_plan_time(self):
        api = _Api(get_return={"name": "chg1"})
        with pytest.raises(ProximoError):
            plan_tape_changer_update(api, "chg1", export_slots="abc")

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            plan_tape_changer_update(api, "ab")

    def test_no_fields_changed_message(self):
        api = _Api(get_return={"name": "chg1"})
        plan = plan_tape_changer_update(api, "chg1")
        assert "no fields changed" in plan.change

    def test_empty_delete_list_rejected(self):
        """Wave 5b review finding 1 — changer mirror of the drive-side rejection fix."""
        api = _Api(get_return={"name": "chg1"})
        with pytest.raises(ProximoError):
            plan_tape_changer_update(api, "chg1", delete=[])

    def test_no_implied_undo_in_note(self):
        api = _Api(get_return={"name": "chg1"})
        plan = plan_tape_changer_update(api, "chg1", path="/dev/sg5")
        note_lower = plan.note.lower()
        assert "no snapshot" in note_lower or "no undo" in note_lower or "re-apply" in note_lower


class TestPlanTapeChangerDelete:
    def test_is_low_risk(self):
        api = _Api(get_return={"name": "chg1"})
        plan = plan_tape_changer_delete(api, "chg1")
        assert plan.risk == RISK_LOW

    def test_reads_current_from_api(self):
        api = _Api(get_return={"name": "chg1", "path": "/dev/sg4"})
        plan = plan_tape_changer_delete(api, "chg1")
        assert plan.current == {"name": "chg1", "path": "/dev/sg4"}

    def test_re_creatable_in_note(self):
        api = _Api(get_return={"name": "chg1"})
        plan = plan_tape_changer_delete(api, "chg1")
        assert "re-creat" in plan.note.lower()

    def test_warn_about_drive_failure(self):
        api = _Api(get_return={"name": "chg1"})
        plan = plan_tape_changer_delete(api, "chg1")
        assert "WARN" in plan.note.upper()

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            plan_tape_changer_delete(api, "ab")
