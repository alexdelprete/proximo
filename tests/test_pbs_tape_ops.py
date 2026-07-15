"""TDD tests for the PBS tape drive + changer OPERATIONS plane (Wave 4c, full-surface campaign)
— fully mocked, no live PBS.

Mirrors test_pbs_tape_config.py's / test_pbs_tape_media.py's style: a recording fake PBS API,
validator rejection tests (\\Z-anchored), backend-function path/verb/payload tests, and
plan-factory risk/blast-radius tests. Adds the returns-are-not-uniform proof (module docstring
fact #2 — load-slot/restore-key/transfer return null while every other mutation returns a UPID)
and the SECRET CONTRACT test for restore-key's `password` (mirrors 4b's key tests).

Covers: validators (label-text, slot, redact-secrets); backend functions for all 19 ops (6 read,
13 mutation); plan factories (RISK_LOW rewind/transfer, RISK_MEDIUM the rest of the physical
ops, RISK_HIGH label-media/barcode-label-media/format-media — see module docstring's RISK RATING
section); module structure.
"""

from __future__ import annotations

import pytest

from proximo.backends import ProximoError
from proximo.pbs_tape_ops import (
    _check_label_text,
    _check_slot,
    _redact_secrets,
    plan_tape_changer_transfer,
    plan_tape_drive_barcode_label_media,
    plan_tape_drive_catalog,
    plan_tape_drive_clean,
    plan_tape_drive_eject,
    plan_tape_drive_format,
    plan_tape_drive_inventory_update,
    plan_tape_drive_label_media,
    plan_tape_drive_load_media,
    plan_tape_drive_load_slot,
    plan_tape_drive_restore_key,
    plan_tape_drive_rewind,
    plan_tape_drive_unload,
    tape_changer_status,
    tape_changer_transfer,
    tape_drive_barcode_label_media,
    tape_drive_cartridge_memory,
    tape_drive_catalog,
    tape_drive_clean,
    tape_drive_eject,
    tape_drive_format,
    tape_drive_inventory,
    tape_drive_inventory_update,
    tape_drive_label_media,
    tape_drive_load_media,
    tape_drive_load_slot,
    tape_drive_read_label,
    tape_drive_restore_key,
    tape_drive_rewind,
    tape_drive_status,
    tape_drive_unload,
    tape_drive_volume_statistics,
)
from proximo.planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM

_UPID = "UPID:node1:00000001:00000000:00000000:tapeop:drive1:root@pam:"

# ---------------------------------------------------------------------------
# Recording fake
# ---------------------------------------------------------------------------

class _Api:
    """Recording fake for PbsBackend (HTTP verb tracking, no live network). `_post`/`_put` return
    `_upid_return` when set (simulating a UPID-returning op) else None (simulating a
    synchronous/null-returning op)."""

    def __init__(self, get_return=None, upid_return=None):
        self._get_return = get_return
        self._upid_return = upid_return
        self.gets: list[tuple] = []
        self.posts: list[tuple] = []
        self.puts: list[tuple] = []
        self.dels: list[tuple] = []

    def _get(self, path: str, params=None):
        self.gets.append((path, params))
        return self._get_return

    def _post(self, path: str, data=None):
        self.posts.append((path, data))
        return self._upid_return

    def _put(self, path: str, data=None):
        self.puts.append((path, data))
        return self._upid_return

    def _delete(self, path: str, params=None):
        self.dels.append((path, params))
        return None


# ---------------------------------------------------------------------------
# Module structure
# ---------------------------------------------------------------------------

def test_module_docstring_names_schema_facts():
    import proximo.pbs_tape_ops as m
    doc = m.__doc__ or ""
    assert "upid" in doc.lower()
    assert "label-text" in doc.lower() or "label_text" in doc.lower()
    assert "adversarial" in doc.lower()


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

class TestCheckLabelText:
    def test_valid_simple(self):
        assert _check_label_text("scratch01") == "scratch01"

    def test_valid_with_dot_underscore_hyphen(self):
        assert _check_label_text("lto-9.a_1") == "lto-9.a_1"

    def test_min_length_two_enforced(self):
        with pytest.raises(ProximoError):
            _check_label_text("a")

    def test_min_length_two_accepted(self):
        assert _check_label_text("ab") == "ab"

    def test_max_length_32_enforced(self):
        with pytest.raises(ProximoError):
            _check_label_text("a" * 33)

    def test_max_length_32_accepted(self):
        assert _check_label_text("a" * 32) == "a" * 32

    def test_slash_raises(self):
        with pytest.raises(ProximoError):
            _check_label_text("name/slash")

    def test_trailing_newline_raises(self):
        with pytest.raises(ProximoError):
            _check_label_text("scratch01\n")

    def test_empty_raises(self):
        with pytest.raises(ProximoError):
            _check_label_text("")

    def test_control_char_raises(self):
        with pytest.raises(ProximoError):
            _check_label_text("sc\x00ratch")

    def test_leading_dot_rejected(self):
        with pytest.raises(ProximoError):
            _check_label_text(".scratch01")


class TestCheckSlot:
    def test_valid_min(self):
        assert _check_slot(1, "source-slot") == 1

    def test_valid_typical(self):
        assert _check_slot(42, "source-slot") == 42

    def test_zero_rejected(self):
        with pytest.raises(ProximoError):
            _check_slot(0, "source-slot")

    def test_negative_rejected(self):
        with pytest.raises(ProximoError):
            _check_slot(-1, "source-slot")

    def test_non_integer_rejected(self):
        with pytest.raises(ProximoError):
            _check_slot("not-a-number", "source-slot")

    def test_string_digit_coerced(self):
        # int("5") succeeds — mirrors the rest of this codebase's permissive int() coercion.
        assert _check_slot("5", "source-slot") == 5

    def test_error_message_names_field(self):
        with pytest.raises(ProximoError, match="target-slot"):
            _check_slot(0, "target-slot")


class TestRedactSecrets:
    def test_password_redacted(self):
        out = _redact_secrets({"password": "hunter2", "drive": "drive1"})
        assert out["password"] == "[redacted]"
        assert out["drive"] == "drive1"

    def test_no_secret_keys_passthrough(self):
        out = _redact_secrets({"drive": "drive1", "label-text": "scratch01"})
        assert out == {"drive": "drive1", "label-text": "scratch01"}


# ---------------------------------------------------------------------------
# Backend functions — reads
# ---------------------------------------------------------------------------

class TestReads:
    def test_drive_status(self):
        api = _Api(get_return={"blocksize": 0, "compression": True, "product": "ULT3580-HH9",
                                "vendor": "IBM", "revision": "1", "buffer-mode": 1})
        out = tape_drive_status(api, "drive1")
        assert api.gets[-1] == ("/tape/drive/drive1/status", None)
        assert out["product"] == "ULT3580-HH9"

    def test_drive_status_null_returns_empty_dict(self):
        api = _Api(get_return=None)
        assert tape_drive_status(api, "drive1") == {}

    def test_drive_read_label(self):
        api = _Api(get_return={"label-text": "scratch01", "uuid": "u1", "ctime": 1700000000})
        out = tape_drive_read_label(api, "drive1")
        assert api.gets[-1] == ("/tape/drive/drive1/read-label", {})
        assert out["label-text"] == "scratch01"

    def test_drive_read_label_inventorize_forwarded(self):
        api = _Api(get_return={})
        tape_drive_read_label(api, "drive1", inventorize=True)
        assert api.gets[-1] == ("/tape/drive/drive1/read-label", {"inventorize": True})

    def test_drive_read_label_inventorize_omitted_when_none(self):
        api = _Api(get_return={})
        tape_drive_read_label(api, "drive1", inventorize=None)
        assert api.gets[-1] == ("/tape/drive/drive1/read-label", {})

    def test_drive_cartridge_memory(self):
        api = _Api(get_return=[{"id": 1, "name": "Barcode", "value": "SCRATCH01"}])
        out = tape_drive_cartridge_memory(api, "drive1")
        assert api.gets[-1] == ("/tape/drive/drive1/cartridge-memory", None)
        assert out[0]["name"] == "Barcode"

    def test_drive_cartridge_memory_null_returns_empty_list(self):
        api = _Api(get_return=None)
        assert tape_drive_cartridge_memory(api, "drive1") == []

    def test_drive_volume_statistics(self):
        api = _Api(get_return={"serial": "SN123", "lifetime-bytes-read": 0})
        out = tape_drive_volume_statistics(api, "drive1")
        assert api.gets[-1] == ("/tape/drive/drive1/volume-statistics", None)
        assert out["serial"] == "SN123"

    def test_drive_inventory(self):
        api = _Api(get_return=[{"label-text": "scratch01", "uuid": "u1"}])
        out = tape_drive_inventory(api, "drive1")
        assert api.gets[-1] == ("/tape/drive/drive1/inventory", None)
        assert out[0]["label-text"] == "scratch01"

    def test_drive_inventory_null_returns_empty_list(self):
        api = _Api(get_return=None)
        assert tape_drive_inventory(api, "drive1") == []

    def test_changer_status(self):
        api = _Api(get_return=[{"entry-id": 0, "entry-kind": "drive"}])
        out = tape_changer_status(api, "changer1")
        assert api.gets[-1] == ("/tape/changer/changer1/status", {})
        assert out[0]["entry-kind"] == "drive"

    def test_changer_status_cache_forwarded(self):
        api = _Api(get_return=[])
        tape_changer_status(api, "changer1", cache=False)
        assert api.gets[-1] == ("/tape/changer/changer1/status", {"cache": False})

    def test_read_drive_id_validated(self):
        with pytest.raises(ProximoError):
            tape_drive_status(_Api(), "a")  # too short

    def test_read_changer_id_validated(self):
        with pytest.raises(ProximoError):
            tape_changer_status(_Api(), "a")  # too short


# ---------------------------------------------------------------------------
# Backend functions — mutations, Drive
# ---------------------------------------------------------------------------

class TestDriveMutations:
    def test_load_media_upid(self):
        api = _Api(upid_return=_UPID)
        out = tape_drive_load_media(api, "drive1", "scratch01")
        assert api.posts[-1] == ("/tape/drive/drive1/load-media", {"label-text": "scratch01"})
        assert out == _UPID

    def test_load_media_validates_label(self):
        with pytest.raises(ProximoError):
            tape_drive_load_media(_Api(), "drive1", "a")  # too short

    def test_load_slot_returns_null_not_upid(self):
        """module docstring fact #2 — the one exception on this plane."""
        api = _Api(upid_return=_UPID)  # even if the fake WOULD return a upid-shaped string...
        out = tape_drive_load_slot(api, "drive1", 3)
        assert api.posts[-1] == ("/tape/drive/drive1/load-slot", {"source-slot": 3})
        assert out is None  # ...the backend function's own return type is None (no return stmt)

    def test_load_slot_validates_slot(self):
        with pytest.raises(ProximoError):
            tape_drive_load_slot(_Api(), "drive1", 0)

    def test_unload_upid_with_target_slot(self):
        api = _Api(upid_return=_UPID)
        out = tape_drive_unload(api, "drive1", target_slot=5)
        assert api.posts[-1] == ("/tape/drive/drive1/unload", {"target-slot": 5})
        assert out == _UPID

    def test_unload_omits_target_slot_when_none(self):
        api = _Api(upid_return=_UPID)
        tape_drive_unload(api, "drive1", target_slot=None)
        assert api.posts[-1] == ("/tape/drive/drive1/unload", {})

    def test_eject_upid(self):
        api = _Api(upid_return=_UPID)
        out = tape_drive_eject(api, "drive1")
        assert api.posts[-1] == ("/tape/drive/drive1/eject-media", {})
        assert out == _UPID

    def test_rewind_upid(self):
        api = _Api(upid_return=_UPID)
        out = tape_drive_rewind(api, "drive1")
        assert api.posts[-1] == ("/tape/drive/drive1/rewind", {})
        assert out == _UPID

    def test_clean_upid_uses_put(self):
        api = _Api(upid_return=_UPID)
        out = tape_drive_clean(api, "drive1")
        assert api.puts[-1] == ("/tape/drive/drive1/clean", {})
        assert not api.posts
        assert out == _UPID

    def test_inventory_update_upid_uses_put(self):
        api = _Api(upid_return=_UPID)
        out = tape_drive_inventory_update(api, "drive1", catalog=True, read_all_labels=False)
        assert api.puts[-1] == (
            "/tape/drive/drive1/inventory", {"catalog": True, "read-all-labels": False},
        )
        assert out == _UPID

    def test_inventory_update_omits_unset_fields(self):
        api = _Api(upid_return=_UPID)
        tape_drive_inventory_update(api, "drive1")
        assert api.puts[-1] == ("/tape/drive/drive1/inventory", {})

    def test_label_media_upid(self):
        api = _Api(upid_return=_UPID)
        out = tape_drive_label_media(api, "drive1", "newlabel01", pool="pool1")
        assert api.posts[-1] == (
            "/tape/drive/drive1/label-media", {"label-text": "newlabel01", "pool": "pool1"},
        )
        assert out == _UPID

    def test_label_media_omits_pool_when_none(self):
        api = _Api(upid_return=_UPID)
        tape_drive_label_media(api, "drive1", "newlabel01")
        assert api.posts[-1] == ("/tape/drive/drive1/label-media", {"label-text": "newlabel01"})

    def test_barcode_label_media_upid(self):
        api = _Api(upid_return=_UPID)
        out = tape_drive_barcode_label_media(api, "drive1", pool="pool1")
        assert api.posts[-1] == ("/tape/drive/drive1/barcode-label-media", {"pool": "pool1"})
        assert out == _UPID

    def test_barcode_label_media_no_params(self):
        api = _Api(upid_return=_UPID)
        tape_drive_barcode_label_media(api, "drive1")
        assert api.posts[-1] == ("/tape/drive/drive1/barcode-label-media", {})

    def test_format_upid_all_fields(self):
        api = _Api(upid_return=_UPID)
        out = tape_drive_format(
            api, "drive1", fast=False, label_text="scratch01", load_barcode="scratch02",
        )
        assert api.posts[-1] == (
            "/tape/drive/drive1/format-media",
            {"fast": False, "label-text": "scratch01", "load-barcode": "scratch02"},
        )
        assert out == _UPID

    def test_format_no_params(self):
        api = _Api(upid_return=_UPID)
        tape_drive_format(api, "drive1")
        assert api.posts[-1] == ("/tape/drive/drive1/format-media", {})

    def test_catalog_upid_all_fields(self):
        api = _Api(upid_return=_UPID)
        out = tape_drive_catalog(api, "drive1", force=True, scan=True, verbose=False)
        assert api.posts[-1] == (
            "/tape/drive/drive1/catalog", {"force": True, "scan": True, "verbose": False},
        )
        assert out == _UPID

    def test_catalog_no_params(self):
        api = _Api(upid_return=_UPID)
        tape_drive_catalog(api, "drive1")
        assert api.posts[-1] == ("/tape/drive/drive1/catalog", {})

    def test_restore_key_returns_none(self):
        api = _Api(upid_return=_UPID)  # even a upid-shaped fake return is discarded (no return)
        out = tape_drive_restore_key(api, "drive1", "hunter2-password")
        assert api.posts[-1] == ("/tape/drive/drive1/restore-key", {"password": "hunter2-password"})
        assert out is None

    def test_restore_key_no_length_constraint(self):
        """module docstring fact #9 — restore-key's password has no minLength, unlike
        pbs_tape_media.py's key create/update passwords."""
        api = _Api()
        tape_drive_restore_key(api, "drive1", "x")  # 1 char — must not raise
        assert api.posts[-1] == ("/tape/drive/drive1/restore-key", {"password": "x"})


# ---------------------------------------------------------------------------
# Backend functions — mutations, Changer
# ---------------------------------------------------------------------------

class TestChangerMutations:
    def test_transfer_returns_none(self):
        api = _Api(upid_return=_UPID)  # even a upid-shaped fake return is discarded (no return)
        out = tape_changer_transfer(api, "changer1", 1, 5)
        assert api.posts[-1] == ("/tape/changer/changer1/transfer", {"from": 1, "to": 5})
        assert out is None

    def test_transfer_validates_slots(self):
        with pytest.raises(ProximoError):
            tape_changer_transfer(_Api(), "changer1", 0, 5)
        with pytest.raises(ProximoError):
            tape_changer_transfer(_Api(), "changer1", 1, 0)

    def test_transfer_validates_changer_id(self):
        with pytest.raises(ProximoError):
            tape_changer_transfer(_Api(), "a", 1, 5)  # too short


# ---------------------------------------------------------------------------
# Plan factories — risk levels
# ---------------------------------------------------------------------------

class TestPlanRiskLevels:
    def test_load_media_medium(self):
        assert plan_tape_drive_load_media("drive1", "scratch01").risk == RISK_MEDIUM

    def test_load_slot_medium(self):
        assert plan_tape_drive_load_slot("drive1", 3).risk == RISK_MEDIUM

    def test_unload_medium(self):
        assert plan_tape_drive_unload("drive1").risk == RISK_MEDIUM

    def test_eject_medium(self):
        assert plan_tape_drive_eject("drive1").risk == RISK_MEDIUM

    def test_rewind_low(self):
        assert plan_tape_drive_rewind("drive1").risk == RISK_LOW

    def test_clean_medium(self):
        assert plan_tape_drive_clean("drive1").risk == RISK_MEDIUM

    def test_inventory_update_medium(self):
        assert plan_tape_drive_inventory_update("drive1").risk == RISK_MEDIUM

    def test_label_media_high(self):
        assert plan_tape_drive_label_media("drive1", "newlabel01").risk == RISK_HIGH

    def test_barcode_label_media_high(self):
        assert plan_tape_drive_barcode_label_media("drive1").risk == RISK_HIGH

    def test_format_high(self):
        assert plan_tape_drive_format("drive1").risk == RISK_HIGH

    def test_catalog_medium(self):
        assert plan_tape_drive_catalog("drive1").risk == RISK_MEDIUM

    def test_restore_key_medium(self):
        assert plan_tape_drive_restore_key("drive1", "hunter2").risk == RISK_MEDIUM

    def test_transfer_low(self):
        assert plan_tape_changer_transfer("changer1", 1, 5).risk == RISK_LOW


# ---------------------------------------------------------------------------
# Plan factories — content / honesty checks
# ---------------------------------------------------------------------------

class TestPlanContent:
    def test_all_actions_match_own_name(self):
        plans = [
            plan_tape_drive_load_media("drive1", "scratch01"),
            plan_tape_drive_load_slot("drive1", 3),
            plan_tape_drive_unload("drive1"),
            plan_tape_drive_eject("drive1"),
            plan_tape_drive_rewind("drive1"),
            plan_tape_drive_clean("drive1"),
            plan_tape_drive_inventory_update("drive1"),
            plan_tape_drive_label_media("drive1", "newlabel01"),
            plan_tape_drive_barcode_label_media("drive1"),
            plan_tape_drive_format("drive1"),
            plan_tape_drive_catalog("drive1"),
            plan_tape_drive_restore_key("drive1", "hunter2"),
            plan_tape_changer_transfer("changer1", 1, 5),
        ]
        expected = [
            "pbs_tape_drive_load_media", "pbs_tape_drive_load_slot", "pbs_tape_drive_unload",
            "pbs_tape_drive_eject", "pbs_tape_drive_rewind", "pbs_tape_drive_clean",
            "pbs_tape_drive_inventory_update", "pbs_tape_drive_label_media",
            "pbs_tape_drive_barcode_label_media", "pbs_tape_drive_format",
            "pbs_tape_drive_catalog", "pbs_tape_drive_restore_key", "pbs_tape_changer_transfer",
        ]
        assert [p.action for p in plans] == expected

    def test_format_no_undo_stated(self):
        plan = plan_tape_drive_format("drive1")
        blast = " ".join(plan.blast_radius)
        assert "DESTROYS ALL DATA" in blast
        assert "NO" in plan.note.upper()

    def test_format_with_label_text_states_protection(self):
        plan = plan_tape_drive_format("drive1", label_text="scratch01")
        blast = " ".join(plan.blast_radius)
        assert "protection" in blast.lower()
        assert "cancels" in blast.lower()

    def test_format_without_label_text_states_no_protection(self):
        plan = plan_tape_drive_format("drive1")
        blast = " ".join(plan.blast_radius)
        assert "unconditionally" in blast.lower()

    def test_label_media_states_no_emptiness_check(self):
        """label-media has NO opt-in match-check the way format-media does — the module docstring
        explicitly distinguishes the two; the plan must not imply one exists."""
        plan = plan_tape_drive_label_media("drive1", "newlabel01")
        blast = " ".join(plan.blast_radius)
        assert "unaddressable" in blast.lower() or "orphan" in blast.lower()
        assert "cancels" not in blast.lower()

    def test_label_media_pool_reflected(self):
        plan = plan_tape_drive_label_media("drive1", "newlabel01", pool="pool1")
        assert "pool1" in plan.change

    def test_barcode_label_media_pool_reflected(self):
        plan = plan_tape_drive_barcode_label_media("drive1", pool="pool1")
        assert "pool1" in plan.change

    def test_restore_key_password_never_in_change(self):
        """THE SECRET CONTRACT (module docstring fact #10)."""
        plan = plan_tape_drive_restore_key("drive1", "hunter2-super-secret")
        assert "hunter2-super-secret" not in plan.change
        assert "[redacted]" in plan.change

    def test_restore_key_password_never_in_note(self):
        plan = plan_tape_drive_restore_key("drive1", "hunter2-super-secret")
        assert "hunter2-super-secret" not in (plan.note or "")

    def test_clean_states_consumable(self):
        plan = plan_tape_drive_clean("drive1")
        blast = " ".join(plan.blast_radius)
        assert "cleaning" in blast.lower()

    def test_unload_default_slot_description(self):
        plan = plan_tape_drive_unload("drive1")
        assert "origin slot" in plan.change

    def test_unload_explicit_slot_description(self):
        plan = plan_tape_drive_unload("drive1", target_slot=7)
        assert "slot 7" in plan.change

    def test_transfer_reflects_slots(self):
        plan = plan_tape_changer_transfer("changer1", 2, 9)
        assert "2" in plan.change
        assert "9" in plan.change
        assert "changer1" in plan.target

    def test_no_undo_language_present_on_every_plan(self):
        plans = [
            plan_tape_drive_load_media("drive1", "scratch01"),
            plan_tape_drive_load_slot("drive1", 3),
            plan_tape_drive_unload("drive1"),
            plan_tape_drive_eject("drive1"),
            plan_tape_drive_rewind("drive1"),
            plan_tape_drive_clean("drive1"),
            plan_tape_drive_inventory_update("drive1"),
            plan_tape_drive_label_media("drive1", "newlabel01"),
            plan_tape_drive_barcode_label_media("drive1"),
            plan_tape_drive_format("drive1"),
            plan_tape_drive_catalog("drive1"),
            plan_tape_drive_restore_key("drive1", "hunter2"),
            plan_tape_changer_transfer("changer1", 1, 5),
        ]
        for p in plans:
            assert "no snapshot/undo" in (p.note or "").lower() or "no undo" in (p.note or "").lower()
