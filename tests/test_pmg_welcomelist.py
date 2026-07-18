"""PMG GLOBAL welcomelist tests (Wave 8b, full-surface campaign) — fully mocked, no live PMG.

Mirrors test_pmg.py's own Wave 8a (W6a) section style (this family is directly analogous to the
who/what per-object families it just built) and test_sdn_objects.py's "tiny fake api recording
method/path/data" convention for the new-module plane-per-module precedent.

Coverage:
 1. _check_welcomelist_object_type — accepts all 8 typed families, rejects unknown.
 2. _check_welcomelist_id is the §6.5 alias of pmg._check_ruledb_id (byte-identical regex,
    including "0" surviving — Fact #5 / falsy-id honesty).
 3. Reads — welcomelist_objects_list / welcomelist_object_get: path construction (all 8 types),
    validator rejections, None-response fallback to {}/[].
 4. _welcomelist_object_body — field mapping per family (Fact #13's single-field-per-type table),
    mismatched kwargs ignored, empty dict when nothing set.
 5. Mutations — welcomelist_object_add/update/delete: exact path + body construction, generic
    (untyped) delete path, id "0" survives end to end.
 6. Plan factories — risk ladder (MEDIUM add/update, LOW delete, coordinator RULING 3), the
    at-least-one-field guard (Fact #13), the CAPTURE-then-show update plan (typed GET, degrading
    honestly on a capture failure — mirrors pmg.py's own _ruledb_reset_capture_count idiom), and
    the scope/direction argument text in blast_radius.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

# proximo.server imported before proximo.tools.pmg_welcomelist: importing the tools wrapper
# module directly (before proximo.server has fully initialized) trips a circular-import error,
# since proximo/server.py's own bottom-of-file imports pull names out of
# proximo.tools.pmg_welcomelist mid-init. Importing proximo.server first guarantees it's either
# already fully loaded (no-op re-fetch from sys.modules) or completes its own full init here,
# which itself fully loads proximo.tools.pmg_welcomelist as a side effect.
import proximo.server as _proximo_server  # noqa: F401
import proximo.tools.pmg_welcomelist as _welcomelist_tools
from proximo.backends import ProximoError
from proximo.planning import RISK_LOW, RISK_MEDIUM
from proximo.pmg import _check_ruledb_id
from proximo.pmg_welcomelist import (
    _WELCOMELIST_OBJECT_TYPES,
    _check_welcomelist_id,
    _check_welcomelist_object_type,
    _welcomelist_object_body,
    plan_welcomelist_object_add,
    plan_welcomelist_object_delete,
    plan_welcomelist_object_update,
    welcomelist_object_add,
    welcomelist_object_delete,
    welcomelist_object_get,
    welcomelist_object_update,
    welcomelist_objects_list,
)


def _api():
    """Minimal PMG API fake recording _get/_post/_put/_delete calls (mirrors test_pmg.py's own
    _api() helper)."""
    seen: dict = {}

    def fake_get(path, params=None):
        seen["method"] = "GET"
        seen["path"] = path
        seen["params"] = params or {}
        return {}

    def fake_post(path, data=None):
        seen["method"] = "POST"
        seen["path"] = path
        seen["data"] = data or {}
        return None

    def fake_put(path, data=None):
        seen["method"] = "PUT"
        seen["path"] = path
        seen["data"] = data or {}
        return None

    def fake_delete(path, params=None):
        seen["method"] = "DELETE"
        seen["path"] = path
        seen["params"] = params or {}
        return None

    return SimpleNamespace(seen=seen, _get=fake_get, _post=fake_post, _put=fake_put, _delete=fake_delete)


def _capturing_api(get_return=None, raise_on_get=False):
    def fake_get(path, params=None):
        if raise_on_get:
            raise ProximoError(f"simulated capture failure for {path}")
        return get_return if get_return is not None else {"id": 1}

    return SimpleNamespace(_get=fake_get)


# ---------------------------------------------------------------------------
# 1. Validators
# ---------------------------------------------------------------------------


def test_welcomelist_object_types_are_the_8_flat_families():
    assert _WELCOMELIST_OBJECT_TYPES == {
        "email", "receiver", "domain", "receiver_domain",
        "regex", "receiver_regex", "ip", "network",
    }


@pytest.mark.parametrize("value", sorted(_WELCOMELIST_OBJECT_TYPES))
def test_check_welcomelist_object_type_accepts_all_8(value):
    assert _check_welcomelist_object_type(value) == value


def test_check_welcomelist_object_type_rejects_unknown():
    with pytest.raises(ProximoError):
        _check_welcomelist_object_type("ldap")


def test_check_welcomelist_id_is_the_ruledb_id_alias():
    # §6.5: a thin alias, not a duplicated regex/logic.
    assert _check_welcomelist_id is _check_ruledb_id


def test_check_welcomelist_id_accepts_falsy_zero():
    # Fact #5 / falsy-id honesty: "0" is a valid positive-integer STRING id and must survive.
    assert _check_welcomelist_id("0") == "0"


def test_check_welcomelist_id_rejects_non_numeric():
    with pytest.raises(ProximoError):
        _check_welcomelist_id("obj-abc")


# ---------------------------------------------------------------------------
# 2. Reads
# ---------------------------------------------------------------------------


def test_welcomelist_objects_list_uses_correct_path():
    api = _api()
    welcomelist_objects_list(api)
    assert api.seen["path"] == "/config/welcomelist/objects"
    assert api.seen["method"] == "GET"


def test_welcomelist_objects_list_falls_back_to_empty_list():
    api = _api()
    api._get = lambda path, params=None: None
    assert welcomelist_objects_list(api) == []


@pytest.mark.parametrize("type_", sorted(_WELCOMELIST_OBJECT_TYPES))
def test_welcomelist_object_get_uses_correct_path(type_):
    api = _api()
    welcomelist_object_get(api, type_, "5")
    assert api.seen["path"] == f"/config/welcomelist/{type_}/5"
    assert api.seen["method"] == "GET"


def test_welcomelist_object_get_rejects_invalid_type():
    api = _api()
    with pytest.raises(ProximoError):
        welcomelist_object_get(api, "ldap", "5")


def test_welcomelist_object_get_rejects_non_numeric_id():
    api = _api()
    with pytest.raises(ProximoError):
        welcomelist_object_get(api, "email", "obj-abc")


def test_welcomelist_object_get_falsy_id_survives():
    api = _api()
    welcomelist_object_get(api, "email", "0")
    assert api.seen["path"] == "/config/welcomelist/email/0"


def test_welcomelist_object_get_falls_back_to_empty_dict():
    api = _api()
    api._get = lambda path, params=None: None
    assert welcomelist_object_get(api, "email", "5") == {}


# ---------------------------------------------------------------------------
# 3. _welcomelist_object_body — field mapping (Fact #13)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("type_", ["email", "receiver"])
def test_body_email_family_maps_email_field(type_):
    assert _welcomelist_object_body(type_, email="a@example.com") == {"email": "a@example.com"}


@pytest.mark.parametrize("type_", ["domain", "receiver_domain"])
def test_body_domain_family_maps_domain_field(type_):
    assert _welcomelist_object_body(type_, domain="example.com") == {"domain": "example.com"}


@pytest.mark.parametrize("type_", ["regex", "receiver_regex"])
def test_body_regex_family_maps_regex_field(type_):
    assert _welcomelist_object_body(type_, regex=r".*@example\.com") == {"regex": r".*@example\.com"}


def test_body_ip_maps_ip_field():
    assert _welcomelist_object_body("ip", ip="10.99.99.5") == {"ip": "10.99.99.5"}


def test_body_network_maps_cidr_field():
    # network's field is 'cidr' on the wire, not 'network' — schema-verified (draft §2 chunk 8b).
    assert _welcomelist_object_body("network", cidr="10.99.99.0/24") == {"cidr": "10.99.99.0/24"}


def test_body_ignores_mismatched_fields():
    # Passing a field for a DIFFERENT type is silently ignored — mirrors who_object_add's
    # _who_object_body precedent.
    assert _welcomelist_object_body("email", domain="example.com") == {}


def test_body_empty_when_nothing_set():
    assert _welcomelist_object_body("email") == {}


# ---------------------------------------------------------------------------
# 4. Mutations
# ---------------------------------------------------------------------------


def test_welcomelist_object_add_posts_correct_path_and_body():
    api = _api()
    welcomelist_object_add(api, "email", email="good@example.com")
    assert api.seen["method"] == "POST"
    assert api.seen["path"] == "/config/welcomelist/email"
    assert api.seen["data"] == {"email": "good@example.com"}


def test_welcomelist_object_add_network_uses_cidr_field():
    api = _api()
    welcomelist_object_add(api, "network", cidr="10.99.99.0/24")
    assert api.seen["path"] == "/config/welcomelist/network"
    assert api.seen["data"] == {"cidr": "10.99.99.0/24"}


def test_welcomelist_object_add_rejects_invalid_type():
    api = _api()
    with pytest.raises(ProximoError):
        welcomelist_object_add(api, "bogus", email="good@example.com")


def test_welcomelist_object_update_puts_correct_path_and_body():
    api = _api()
    welcomelist_object_update(api, "domain", "5", domain="new.example.com")
    assert api.seen["method"] == "PUT"
    assert api.seen["path"] == "/config/welcomelist/domain/5"
    assert api.seen["data"] == {"domain": "new.example.com"}


def test_welcomelist_object_update_falsy_id_survives():
    api = _api()
    welcomelist_object_update(api, "email", "0", email="good@example.com")
    assert api.seen["path"] == "/config/welcomelist/email/0"


def test_welcomelist_object_update_rejects_non_numeric_id():
    api = _api()
    with pytest.raises(ProximoError):
        welcomelist_object_update(api, "email", "obj-abc", email="good@example.com")


def test_welcomelist_object_delete_is_generic_untyped_path():
    api = _api()
    welcomelist_object_delete(api, "5")
    assert api.seen["method"] == "DELETE"
    assert api.seen["path"] == "/config/welcomelist/objects/5"


def test_welcomelist_object_delete_falsy_id_survives():
    api = _api()
    welcomelist_object_delete(api, "0")
    assert api.seen["path"] == "/config/welcomelist/objects/0"


def test_welcomelist_object_delete_rejects_non_numeric_id():
    api = _api()
    with pytest.raises(ProximoError):
        welcomelist_object_delete(api, "obj-abc")


# ---------------------------------------------------------------------------
# 5. Plan factories
# ---------------------------------------------------------------------------


class TestPlanWelcomelistObjectAdd:
    def test_risk_is_medium(self):
        p = plan_welcomelist_object_add("email", email="good@example.com")
        assert p.risk == RISK_MEDIUM

    def test_action_and_target(self):
        p = plan_welcomelist_object_add("email", email="good@example.com")
        assert p.action == "pmg_welcomelist_object_add"
        assert p.target == "config/welcomelist/email"

    def test_current_is_empty_pure_plan(self):
        p = plan_welcomelist_object_add("email", email="good@example.com")
        assert p.current == {}

    def test_raises_when_required_field_missing(self):
        with pytest.raises(ProximoError):
            plan_welcomelist_object_add("email")

    def test_blast_radius_states_global_scope_and_bypass(self):
        p = plan_welcomelist_object_add("email", email="good@example.com")
        joined = " ".join(p.blast_radius)
        assert "GLOBAL" in joined
        assert "bypass" in joined.lower()
        assert "pmg_quarantine_welcomelist_add" in joined

    def test_network_type_uses_cidr(self):
        p = plan_welcomelist_object_add("network", cidr="10.99.99.0/24")
        assert "cidr" in p.change

    def test_blast_radius_states_sender_direction_for_plain_family(self):
        # "domain" is a plain family -> matches the message's SENDER side (Finding 2 fix).
        p = plan_welcomelist_object_add("domain", domain="example.com")
        joined = " ".join(p.blast_radius)
        assert "SENDER" in joined
        assert "RECIPIENT" not in joined

    def test_blast_radius_states_recipient_direction_for_receiver_family(self):
        # "receiver_domain" is a receiver_* family -> matches the message's RECIPIENT side.
        p = plan_welcomelist_object_add("receiver_domain", domain="example.com")
        joined = " ".join(p.blast_radius)
        assert "RECIPIENT" in joined
        assert "SENDER" not in joined

    def test_note_carries_direction_evidence_and_mailflow_hedge(self):
        # Live-verified 2026-07-17: PMG's own receivertest flag evidences the naming-convention
        # direction claim; full mail-flow behavior stays honestly hedged as not exercised.
        p = plan_welcomelist_object_add("receiver_domain", domain="example.com")
        assert "receivertest" in p.note
        assert "not exercised" in p.note
        assert "copy-paste" in p.note


class TestPlanWelcomelistObjectUpdate:
    def test_risk_is_medium(self):
        api = _capturing_api()
        p = plan_welcomelist_object_update(api, "email", "5", email="new@example.com")
        assert p.risk == RISK_MEDIUM

    def test_action_and_target(self):
        api = _capturing_api()
        p = plan_welcomelist_object_update(api, "email", "5", email="new@example.com")
        assert p.action == "pmg_welcomelist_object_update"
        assert p.target == "config/welcomelist/email/5"

    def test_raises_when_required_field_missing(self):
        api = _capturing_api()
        with pytest.raises(ProximoError):
            plan_welcomelist_object_update(api, "email", "5")

    def test_captures_current_state_via_typed_get(self):
        api = _capturing_api(get_return={"id": 5, "email": "old@example.com"})
        p = plan_welcomelist_object_update(api, "email", "5", email="new@example.com")
        assert p.current == {"id": 5, "email": "old@example.com"}
        assert p.complete is True

    def test_degrades_honestly_when_capture_fails(self):
        api = _capturing_api(raise_on_get=True)
        p = plan_welcomelist_object_update(api, "email", "5", email="new@example.com")
        assert p.current == {}
        assert p.complete is False
        assert any("current-state capture failed" in note for note in p.blast_radius)
        # the plan still renders fully — MEDIUM risk intact even on a partial capture
        assert p.risk == RISK_MEDIUM

    def test_blast_radius_states_no_digest_race_honesty(self):
        api = _capturing_api()
        p = plan_welcomelist_object_update(api, "email", "5", email="new@example.com")
        joined = " ".join(p.blast_radius)
        assert "race" in joined.lower()
        assert "digest" in joined.lower()

    def test_blast_radius_states_sender_direction_for_plain_family(self):
        # "domain" is a plain family -> matches the message's SENDER side (Finding 2 fix).
        api = _capturing_api()
        p = plan_welcomelist_object_update(api, "domain", "5", domain="example.com")
        joined = " ".join(p.blast_radius)
        assert "SENDER" in joined
        assert "RECIPIENT" not in joined

    def test_blast_radius_states_recipient_direction_for_receiver_family(self):
        # "receiver_domain" is a receiver_* family -> matches the message's RECIPIENT side.
        api = _capturing_api()
        p = plan_welcomelist_object_update(api, "receiver_domain", "5", domain="example.com")
        joined = " ".join(p.blast_radius)
        assert "RECIPIENT" in joined
        assert "SENDER" not in joined

    def test_note_carries_direction_evidence_and_mailflow_hedge(self):
        # Live-verified 2026-07-17: PMG's own receivertest flag evidences the naming-convention
        # direction claim; full mail-flow behavior stays honestly hedged as not exercised.
        api = _capturing_api()
        p = plan_welcomelist_object_update(api, "receiver_domain", "5", domain="example.com")
        assert "receivertest" in p.note
        assert "not exercised" in p.note
        assert "copy-paste" in p.note


class TestPlanWelcomelistObjectDelete:
    def test_risk_is_low(self):
        p = plan_welcomelist_object_delete("5")
        assert p.risk == RISK_LOW

    def test_action_and_target(self):
        p = plan_welcomelist_object_delete("5")
        assert p.action == "pmg_welcomelist_object_delete"
        assert p.target == "config/welcomelist/objects/5"

    def test_current_is_empty_pure_plan(self):
        p = plan_welcomelist_object_delete("5")
        assert p.current == {}

    def test_blast_radius_argues_protective_direction(self):
        p = plan_welcomelist_object_delete("5")
        joined = " ".join(p.blast_radius).lower()
        assert "protective" in joined

    def test_rejects_non_numeric_id(self):
        with pytest.raises(ProximoError):
            plan_welcomelist_object_delete("obj-abc")

    def test_falsy_id_survives(self):
        p = plan_welcomelist_object_delete("0")
        assert p.target == "config/welcomelist/objects/0"


# ---------------------------------------------------------------------------
# 6. RULING 5 disambiguation — every one of the 5 @tool()-decorated wrappers in
#    tools/pmg_welcomelist.py must carry the mandatory cross-reference to its
#    pmg_quarantine_welcomelist_* sibling in its OWN docstring (the surface an MCP client/agent
#    actually sees when introspecting that specific tool) — coordinator RULING 5. Pins all 5 so a
#    single missed line (the wave-8b review's Major finding #1, pmg_welcomelist_object_delete)
#    can't silently regress.
# ---------------------------------------------------------------------------

_RULING5_DISAMBIGUATION_CASES = [
    pytest.param(
        _welcomelist_tools.pmg_welcomelist_objects_list, "pmg_quarantine_welcomelist_list",
        id="objects_list",
    ),
    pytest.param(
        _welcomelist_tools.pmg_welcomelist_object_get, "pmg_quarantine_welcomelist_",
        id="object_get",
    ),
    pytest.param(
        _welcomelist_tools.pmg_welcomelist_object_add, "pmg_quarantine_welcomelist_add",
        id="object_add",
    ),
    pytest.param(
        _welcomelist_tools.pmg_welcomelist_object_update, "pmg_quarantine_welcomelist_",
        id="object_update",
    ),
    pytest.param(
        _welcomelist_tools.pmg_welcomelist_object_delete, "pmg_quarantine_welcomelist_remove",
        id="object_delete",
    ),
]


@pytest.mark.parametrize("fn,expected_sibling_ref", _RULING5_DISAMBIGUATION_CASES)
def test_all_5_wrapper_docstrings_carry_ruling5_disambiguation(fn, expected_sibling_ref):
    doc = fn.__doc__ or ""
    assert "NOT THE SAME" in doc
    assert expected_sibling_ref in doc
