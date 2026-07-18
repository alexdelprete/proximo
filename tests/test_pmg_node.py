"""PMG node core backend/validator/plan-factory unit tests (Wave 9a review fix pass + Wave 9b).

Mirrors `test_pmg_welcomelist.py`'s structure (fully mocked, no live PMG, no server/FastMCP
involved) — the Wave 9a review's MAJOR finding was that this module shipped with ONLY a
server-level confirm-sweep file (`test_confirm_sweep_pmg_node.py`), leaving validators,
`_join_delete_props`/`_check_config_digest`, and the `network_update` type-injection path
(including raising/falsy fakes) with zero direct coverage — precisely the gap that let the
CRITICAL (PLAN blind to `delete`/`delete_props`) and two MAJOR findings ship unnoticed. This file
closes that gap directly against the backend/plan-factory functions in `proximo.pmg_node`.

Sections:
 1. Validators — _check_iface, _check_iface_type_filter/_value (both enums + the cross-set
    rejection PMG's own schema documents), _check_config_digest, _join_delete_props, _delete_list,
    _strip_subscription_key.
 2. Backend functions — network family (reserved-key guards, `_resolve_iface_type`'s auto-inject
    path with raising/falsy fakes, delete_props threading), config_set's delete/digest threading.
 3. Plan factories — CAPTURE-or-declare success/failure branches, the delete/delete_props
    disclosure fix (CRITICAL), and plan_network_update's TYPE CHANGE disclosure (MAJOR).
 4. Chunk 9b — validators (queue/queue-id/backup-filename/sortfield/sortdir/nonneg-int,
    `_service_stop_risk`'s conditional tier), backend functions (task/postfix-queue/backup
    family path+param construction), and plan factories (the conditional-risk tools —
    postfix_queue_action, service_stop — and plan_backup_restore's CAPTURE-or-degrade-honestly
    ruledb-count reuse + no-undo first blast_radius line, mirroring pmg.py's own
    plan_ruledb_reset test coverage shape).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from proximo.backends import ProximoError
from proximo.planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM
from proximo.pmg_node import (
    _MAIL_CRITICAL_SERVICES,
    _QUEUE_ACTIONS,
    _QUEUE_NAMES,
    _SORTDIRS,
    _SORTFIELDS,
    _VALID_IFACE_TYPE_FILTER,
    _VALID_IFACE_TYPE_VALUE,
    _check_backup_filename,
    _check_config_digest,
    _check_iface,
    _check_iface_type_filter,
    _check_iface_type_value,
    _check_nonneg_int,
    _check_postfix_queue_action,
    _check_queue,
    _check_queue_id,
    _check_queue_ids,
    _check_sortdir,
    _check_sortfield,
    _delete_list,
    _join_delete_props,
    _reject_dot_traversal,
    _resolve_iface_type,
    _service_stop_risk,
    _strip_subscription_key,
    backup_delete,
    backup_list,
    backup_restore,
    clamav_database_get,
    clamav_database_update,
    config_get,
    config_set,
    dns_get,
    journal,
    network_create,
    network_get,
    network_list,
    network_update,
    plan_backup_delete,
    plan_backup_restore,
    plan_config_set,
    plan_dns_set,
    plan_network_create,
    plan_network_delete,
    plan_network_update,
    plan_postfix_queue_action,
    plan_postfix_queue_delete_all,
    plan_postfix_queue_delete_queue,
    plan_postfix_queue_message_delete,
    plan_postfix_queue_message_deliver,
    plan_service_stop,
    plan_task_stop,
    plan_time_set,
    postfix_discard_verify_cache,
    postfix_queue_action,
    postfix_queue_delete_all,
    postfix_queue_delete_queue,
    postfix_queue_list,
    postfix_queue_message_delete,
    postfix_queue_message_deliver,
    postfix_queue_message_get,
    report,
    service_reload,
    service_restart,
    service_start,
    service_stop,
    spamassassin_rules_get,
    spamassassin_rules_update,
    task_log,
    task_status,
    task_stop,
    time_get,
)


def _api(get_return=None, raise_on_get=False):
    """Path-recording fake PmgBackend — mirrors test_pmg_welcomelist.py's `_api()`."""
    seen: dict = {}

    def fake_get(path, params=None):
        seen["method"] = "GET"
        seen["path"] = path
        seen["params"] = params
        if raise_on_get:
            raise ProximoError(f"simulated read failure for {path}")
        if get_return is not None:
            return get_return
        return {}

    def fake_post(path, data=None):
        seen["method"] = "POST"
        seen["path"] = path
        seen["data"] = data
        return None

    def fake_put(path, data=None):
        seen["method"] = "PUT"
        seen["path"] = path
        seen["data"] = data
        return None

    def fake_delete(path, params=None):
        seen["method"] = "DELETE"
        seen["path"] = path
        seen["params"] = params
        return None

    return SimpleNamespace(seen=seen, _get=fake_get, _post=fake_post, _put=fake_put, _delete=fake_delete)


def _raising_get_api(exc: Exception):
    def fake_get(path, params=None):
        raise exc

    return SimpleNamespace(_get=fake_get)


# ---------------------------------------------------------------------------
# 1. Validators
# ---------------------------------------------------------------------------


class TestCheckIface:
    def test_accepts_2_char_lower_bound(self):
        assert _check_iface("e0") == "e0"

    def test_accepts_20_char_upper_bound(self):
        s = "a" * 20
        assert _check_iface(s) == s

    def test_rejects_1_char_too_short(self):
        with pytest.raises(ProximoError):
            _check_iface("e")

    def test_rejects_21_char_too_long(self):
        with pytest.raises(ProximoError):
            _check_iface("a" * 21)

    def test_rejects_bad_charset(self):
        with pytest.raises(ProximoError):
            _check_iface("eth0!")

    def test_rejects_lone_dot(self):
        with pytest.raises(ProximoError):
            _check_iface(".")

    def test_rejects_embedded_dotdot(self):
        with pytest.raises(ProximoError):
            _check_iface("et..0")

    def test_accepts_valid_dotted_name(self):
        assert _check_iface("eth0.10") == "eth0.10"


def test_reject_dot_traversal_raises_on_lone_dot():
    with pytest.raises(ProximoError):
        _reject_dot_traversal(".", "interface name")


def test_reject_dot_traversal_raises_on_embedded_dotdot():
    with pytest.raises(ProximoError):
        _reject_dot_traversal("a..b", "interface name")


def test_reject_dot_traversal_passes_normal_value():
    _reject_dot_traversal("eth0", "interface name")  # no raise


class TestIfaceTypeEnums:
    @pytest.mark.parametrize("value", sorted(_VALID_IFACE_TYPE_FILTER))
    def test_filter_accepts_all_declared_values(self, value):
        assert _check_iface_type_filter(value) == value

    @pytest.mark.parametrize("value", sorted(_VALID_IFACE_TYPE_VALUE))
    def test_value_accepts_all_declared_values(self, value):
        assert _check_iface_type_value(value) == value

    def test_filter_rejects_unknown_the_value_only_enum_member(self):
        # "unknown" is in the VALUE enum but NOT the FILTER enum (fact #2's cross-set split) —
        # a filter call must reject it, not silently accept it via a shared/merged set.
        with pytest.raises(ProximoError):
            _check_iface_type_filter("unknown")

    def test_value_rejects_any_bridge_the_filter_only_enum_member(self):
        # "any_bridge" is in the FILTER enum but NOT the VALUE enum — the mirror-image
        # cross-set rejection.
        with pytest.raises(ProximoError):
            _check_iface_type_value("any_bridge")

    def test_value_rejects_empty_string_falsy_edge(self):
        with pytest.raises(ProximoError):
            _check_iface_type_value("")

    def test_filter_rejects_garbage(self):
        with pytest.raises(ProximoError):
            _check_iface_type_filter("not-a-real-type")


class TestCheckConfigDigest:
    def test_none_passes_through(self):
        assert _check_config_digest(None) is None

    def test_accepts_short_hex(self):
        assert _check_config_digest("abc123") == "abc123"

    def test_accepts_40_char_upper_bound(self):
        s = "a" * 40
        assert _check_config_digest(s) == s

    def test_rejects_41_char_too_long(self):
        with pytest.raises(ProximoError):
            _check_config_digest("a" * 41)

    def test_rejects_non_hex_chars(self):
        with pytest.raises(ProximoError):
            _check_config_digest("not-hex-zzz")


class TestJoinDeleteProps:
    def test_list_is_comma_joined(self):
        assert _join_delete_props(["a", "b", "c"]) == "a,b,c"

    def test_tuple_is_comma_joined(self):
        assert _join_delete_props(("a", "b")) == "a,b"

    def test_pre_joined_string_passes_through(self):
        assert _join_delete_props("a,b") == "a,b"

    def test_single_item_list(self):
        assert _join_delete_props(["acmedomain0"]) == "acmedomain0"


class TestDeleteList:
    def test_none_is_empty_list(self):
        assert _delete_list(None) == []

    def test_list_passes_through_as_strings(self):
        assert _delete_list(["a", "b"]) == ["a", "b"]

    def test_tuple_normalizes_to_list(self):
        assert _delete_list(("a", "b")) == ["a", "b"]

    def test_comma_string_splits(self):
        assert _delete_list("a,b,c") == ["a", "b", "c"]

    def test_single_item_string_is_one_element_list(self):
        assert _delete_list("acmedomain0") == ["acmedomain0"]


def test_strip_subscription_key_removes_key():
    assert _strip_subscription_key({"key": "secret", "status": "active"}) == {"status": "active"}


def test_strip_subscription_key_no_op_when_absent():
    assert _strip_subscription_key({"status": "active"}) == {"status": "active"}


def test_strip_subscription_key_empty_dict():
    assert _strip_subscription_key({}) == {}


# ---------------------------------------------------------------------------
# 2. Backend functions
# ---------------------------------------------------------------------------


def test_network_list_uses_correct_path():
    api = _api()
    network_list(api, "pmg")
    assert api.seen["path"] == "/nodes/pmg/network"


def test_network_list_falls_back_to_empty_list():
    api = _api(get_return=None)
    assert network_list(api, "pmg") == []


def test_network_get_uses_correct_path():
    api = _api(get_return={"type": "bridge"})
    network_get(api, "eth0", "pmg")
    assert api.seen["path"] == "/nodes/pmg/network/eth0"


class TestNetworkCreate:
    def test_reserved_type_key_in_opts_raises(self):
        api = _api()
        with pytest.raises(ProximoError):
            network_create(api, "pmg", "eth1", "bridge", type="bridge")

    def test_builds_expected_body(self):
        api = _api()
        network_create(api, "pmg", "eth1", "bridge", comments="new")
        assert api.seen["path"] == "/nodes/pmg/network"
        assert api.seen["data"] == {"iface": "eth1", "type": "bridge", "comments": "new"}

    def test_rejects_invalid_type(self):
        api = _api()
        with pytest.raises(ProximoError):
            network_create(api, "pmg", "eth1", "any_bridge")  # value-only rejects filter member


# --- _resolve_iface_type (the auto-inject path — the review's most-flagged gap) ---


class TestResolveIfaceType:
    def test_explicit_type_is_validated_and_returned(self):
        api = _api()
        assert _resolve_iface_type(api, "pmg", "eth0", "vlan") == "vlan"

    def test_explicit_invalid_type_raises(self):
        api = _api()
        with pytest.raises(ProximoError):
            _resolve_iface_type(api, "pmg", "eth0", "any_bridge")

    def test_omitted_type_injects_current_type(self):
        api = _api(get_return={"type": "bridge", "method": "static"})
        assert _resolve_iface_type(api, "pmg", "eth0", None) == "bridge"

    def test_omitted_type_with_no_current_type_raises(self):
        api = _api(get_return={"method": "static"})  # no 'type' key at all
        with pytest.raises(ProximoError):
            _resolve_iface_type(api, "pmg", "eth0", None)

    def test_omitted_type_falsy_live_value_raises_not_crashes(self):
        # MINOR finding (f): an empty-string LIVE type must not be sent to the wire unvalidated —
        # it must fail _check_iface_type_value and raise an honest ProximoError (a divergence
        # report), not silently pass "" through.
        api = _api(get_return={"type": ""})
        with pytest.raises(ProximoError):
            _resolve_iface_type(api, "pmg", "eth0", None)

    def test_omitted_type_garbage_live_value_raises_as_divergence(self):
        api = _api(get_return={"type": "totally-not-a-real-type"})
        with pytest.raises(ProximoError) as exc:
            _resolve_iface_type(api, "pmg", "eth0", None)
        # honest divergence framing, not a bare validator message mis-attributed to the caller
        assert "LIVE type" in str(exc.value) or "live" in str(exc.value).lower()

    def test_read_failure_propagates_uncaught(self):
        # Matches PVE's own identical asymmetry (network.py's _current_iface_type/
        # network_iface_update has no try/except around its own current-type read either) — not
        # widened beyond that precedent (MINOR finding f, noted not blocking).
        api = _raising_get_api(ConnectionError("simulated"))
        with pytest.raises(ConnectionError):
            _resolve_iface_type(api, "pmg", "eth0", None)


class TestNetworkUpdate:
    def test_reserved_type_key_in_opts_raises(self):
        api = _api(get_return={"type": "bridge"})
        with pytest.raises(ProximoError):
            network_update(api, "pmg", "eth0", "bridge", None, type="bridge")

    def test_reserved_delete_key_in_opts_raises(self):
        # MINOR finding (g): an explicit "delete" key in **opts must be rejected, pointing the
        # caller at delete_props instead of silently overwriting/being overwritten.
        api = _api(get_return={"type": "bridge"})
        with pytest.raises(ProximoError) as exc:
            network_update(api, "pmg", "eth0", "bridge", None, delete="comment")
        assert "delete_props" in str(exc.value)

    def test_explicit_type_forwarded(self):
        api = _api(get_return={"type": "bridge"})
        network_update(api, "pmg", "eth0", "vlan", None, mtu=1500)
        assert api.seen["path"] == "/nodes/pmg/network/eth0"
        assert api.seen["data"] == {"type": "vlan", "mtu": 1500}

    def test_omitted_type_injects_current(self):
        api = _api(get_return={"type": "bridge", "method": "static"})
        network_update(api, "pmg", "eth0", None, None, mtu=1500)
        assert api.seen["data"] == {"type": "bridge", "mtu": 1500}

    def test_delete_props_list_threaded_as_comma_string(self):
        api = _api(get_return={"type": "bridge"})
        network_update(api, "pmg", "eth0", "bridge", ["comment", "mtu"])
        assert api.seen["data"] == {"type": "bridge", "delete": "comment,mtu"}

    def test_falsy_live_type_raises_not_silently_sent(self):
        api = _api(get_return={"type": ""})
        with pytest.raises(ProximoError):
            network_update(api, "pmg", "eth0", None, None)


class TestConfigSet:
    def test_delete_list_threaded_as_comma_string(self):
        api = _api()
        config_set(api, "pmg", delete=["acmedomain0"])
        assert api.seen["path"] == "/nodes/pmg/config"
        assert api.seen["data"] == {"delete": "acmedomain0"}

    def test_delete_multiple_joined(self):
        api = _api()
        config_set(api, "pmg", delete=["acmedomain0", "acmedomain1"])
        assert api.seen["data"] == {"delete": "acmedomain0,acmedomain1"}

    def test_digest_validated_and_forwarded(self):
        api = _api()
        config_set(api, "pmg", acme="account=x", digest="abc123")
        assert api.seen["data"] == {"acme": "account=x", "digest": "abc123"}

    def test_invalid_digest_raises(self):
        api = _api()
        with pytest.raises(ProximoError):
            config_set(api, "pmg", acme="account=x", digest="not-hex-zzz")

    def test_no_fields_set_sends_empty_body(self):
        api = _api()
        config_set(api, "pmg")
        assert api.seen["data"] == {}


def test_config_get_uses_correct_path():
    api = _api(get_return={"acme": "account=x"})
    config_get(api, "pmg")
    assert api.seen["path"] == "/nodes/pmg/config"


def test_dns_get_uses_correct_path():
    api = _api(get_return={"search": "example.test"})
    dns_get(api, "pmg")
    assert api.seen["path"] == "/nodes/pmg/dns"


def test_time_get_uses_correct_path():
    api = _api(get_return={"timezone": "UTC"})
    time_get(api, "pmg")
    assert api.seen["path"] == "/nodes/pmg/time"


# ---------------------------------------------------------------------------
# 3. Plan factories
# ---------------------------------------------------------------------------


class TestPlanNetworkCreate:
    def test_no_collision_stages_create(self):
        api = _api(get_return=[])
        p = plan_network_create(api, "pmg", "eth1", "bridge")
        assert p.risk == RISK_MEDIUM
        assert any("stages new interface" in b for b in p.blast_radius)

    def test_collision_detected(self):
        api = _api(get_return=[{"iface": "eth1", "type": "bridge"}])
        p = plan_network_create(api, "pmg", "eth1", "bridge")
        assert any("already exists" in b for b in p.blast_radius)

    def test_collision_check_failure_degrades_honestly(self):
        api = _raising_get_api(ConnectionError("simulated"))
        p = plan_network_create(api, "pmg", "eth1", "bridge")
        assert any("collision check failed" in b for b in p.blast_radius)


class TestPlanNetworkUpdate:
    def test_capture_success(self):
        api = _api(get_return={"type": "bridge", "method": "static"})
        p = plan_network_update(api, "pmg", "eth0")
        assert p.complete is True
        assert p.current == {"type": "bridge", "method": "static"}

    def test_capture_failure_degrades_honestly(self):
        api = _raising_get_api(ConnectionError("simulated"))
        p = plan_network_update(api, "pmg", "eth0")
        assert p.complete is False
        assert p.current == {}
        assert "Could not read current config" in p.note

    def test_capture_failure_with_explicit_type_still_renders(self):
        # Degrades honestly: no TYPE CHANGE claim can be made without a captured current type,
        # but the explicit-type line still renders (fix direction (d)'s "unchanged/omitted stays
        # as-is" — a capture failure must not crash the plan).
        api = _raising_get_api(ConnectionError("simulated"))
        p = plan_network_update(api, "pmg", "eth0", iface_type="vlan")
        assert p.complete is False
        joined = " ".join(p.blast_radius)
        assert "type='vlan' (explicit)" in joined
        assert "TYPE CHANGE" not in joined

    # --- CRITICAL fix: delete_props must be disclosed in the PLAN ---

    def test_delete_props_disclosed_in_blast_radius(self):
        api = _api(get_return={"type": "bridge"})
        p = plan_network_update(api, "pmg", "eth0", delete_props=["comment"])
        joined = " ".join(p.blast_radius)
        assert "comment" in joined
        assert "DELETES" in joined

    def test_multiple_delete_props_each_named(self):
        api = _api(get_return={"type": "bridge"})
        p = plan_network_update(api, "pmg", "eth0", delete_props=["comment", "mtu"])
        joined = " ".join(p.blast_radius)
        assert "comment" in joined
        assert "mtu" in joined

    def test_no_delete_props_no_delete_disclosure(self):
        api = _api(get_return={"type": "bridge"})
        p = plan_network_update(api, "pmg", "eth0")
        joined = " ".join(p.blast_radius)
        assert "DELETES" not in joined

    # --- MAJOR fix (d): explicit type CHANGE disclosure ---

    def test_explicit_type_matching_current_no_change_flagged(self):
        api = _api(get_return={"type": "bridge"})
        p = plan_network_update(api, "pmg", "eth0", iface_type="bridge")
        joined = " ".join(p.blast_radius)
        assert "TYPE CHANGE" not in joined
        assert "type='bridge' (explicit)" in joined

    def test_explicit_type_differing_from_current_flags_change(self):
        api = _api(get_return={"type": "bridge"})
        p = plan_network_update(api, "pmg", "eth0", iface_type="vlan")
        joined = " ".join(p.blast_radius)
        assert "TYPE CHANGE" in joined
        assert "bridge" in joined
        assert "vlan" in joined

    def test_omitted_type_shows_preserved_line(self):
        api = _api(get_return={"type": "bridge"})
        p = plan_network_update(api, "pmg", "eth0")
        joined = " ".join(p.blast_radius)
        assert "type='bridge' (preserved from current config)" in joined
        assert "TYPE CHANGE" not in joined


class TestPlanNetworkDelete:
    def test_capture_failure_degrades_honestly(self):
        api = _raising_get_api(ConnectionError("simulated"))
        p = plan_network_delete(api, "eth0", "pmg")
        assert p.complete is False
        assert p.current == {}


class TestPlanDnsSet:
    def test_capture_success(self):
        api = _api(get_return={"search": "example.test", "dns1": "9.9.9.9"})
        p = plan_dns_set(api, "pmg", search="new.example.test")
        assert p.complete is True
        assert p.current == {"search": "example.test", "dns1": "9.9.9.9"}

    def test_capture_failure_degrades_honestly(self):
        api = _raising_get_api(ConnectionError("simulated"))
        p = plan_dns_set(api, "pmg", search="new.example.test")
        assert p.complete is False
        assert "Could not capture current DNS config" in p.note


class TestPlanTimeSet:
    def test_capture_success(self):
        api = _api(get_return={"timezone": "UTC"})
        p = plan_time_set(api, "pmg", "America/Chicago")
        assert p.complete is True
        assert p.current == {"timezone": "UTC"}

    def test_capture_failure_degrades_honestly(self):
        api = _raising_get_api(ConnectionError("simulated"))
        p = plan_time_set(api, "pmg", "America/Chicago")
        assert p.complete is False
        assert "Could not capture current timezone" in p.note


class TestPlanConfigSet:
    def test_capture_success(self):
        api = _api(get_return={"acme": "account=x"})
        p = plan_config_set(api, "pmg", acme="account=y")
        assert p.complete is True
        assert p.current == {"acme": "account=x"}

    def test_capture_failure_degrades_honestly(self):
        api = _raising_get_api(ConnectionError("simulated"))
        p = plan_config_set(api, "pmg", acme="account=y")
        assert p.complete is False
        assert "Could not capture current node config" in p.note

    # --- CRITICAL fix: delete must be disclosed in the PLAN ---

    def test_delete_disclosed_in_blast_radius(self):
        api = _api(get_return={"acmedomain0": "domain=example.com"})
        p = plan_config_set(api, "pmg", delete=["acmedomain0"])
        joined = " ".join(p.blast_radius)
        assert "acmedomain0" in joined
        assert "DELETES" in joined

    def test_multiple_deletes_each_named(self):
        api = _api(get_return={})
        p = plan_config_set(api, "pmg", delete=["acmedomain0", "acmedomain1"])
        joined = " ".join(p.blast_radius)
        assert "acmedomain0" in joined
        assert "acmedomain1" in joined

    def test_no_delete_no_disclosure(self):
        api = _api(get_return={})
        p = plan_config_set(api, "pmg", acme="account=y")
        joined = " ".join(p.blast_radius)
        assert "DELETES" not in joined

    def test_risk_stays_medium_with_delete(self):
        api = _api(get_return={})
        p = plan_config_set(api, "pmg", delete=["acmedomain0"])
        assert p.risk == RISK_MEDIUM


# ---------------------------------------------------------------------------
# 4. Chunk 9b — validators
# ---------------------------------------------------------------------------


class TestCheckQueue:
    @pytest.mark.parametrize("value", sorted(_QUEUE_NAMES))
    def test_accepts_all_declared_values(self, value):
        assert _check_queue(value) == value

    def test_rejects_garbage(self):
        with pytest.raises(ProximoError):
            _check_queue("not-a-real-queue")


class TestCheckPostfixQueueAction:
    @pytest.mark.parametrize("value", sorted(_QUEUE_ACTIONS))
    def test_accepts_all_declared_values(self, value):
        assert _check_postfix_queue_action(value) == value

    def test_rejects_garbage(self):
        with pytest.raises(ProximoError):
            _check_postfix_queue_action("purge")


class TestCheckQueueId:
    def test_accepts_alnum(self):
        assert _check_queue_id("4RXXXX1234") == "4RXXXX1234"

    def test_rejects_slash(self):
        with pytest.raises(ProximoError):
            _check_queue_id("abc/def")

    def test_rejects_empty(self):
        with pytest.raises(ProximoError):
            _check_queue_id("")

    def test_rejects_too_long(self):
        with pytest.raises(ProximoError):
            _check_queue_id("a" * 41)

    def test_rejects_comma(self):
        # a single queue_id path segment never carries a comma
        with pytest.raises(ProximoError):
            _check_queue_id("abc,def")


class TestCheckQueueIds:
    def test_single_id_passes(self):
        assert _check_queue_ids("ABC123") == "ABC123"

    def test_multiple_comma_separated_ids_pass(self):
        assert _check_queue_ids("ABC123,DEF456") == "ABC123,DEF456"

    def test_empty_string_raises(self):
        with pytest.raises(ProximoError):
            _check_queue_ids("")

    def test_one_bad_token_raises(self):
        with pytest.raises(ProximoError):
            _check_queue_ids("ABC123,bad/token")

    def test_embedded_empty_token_raises(self):
        # tokens are never silently dropped — 'ABC,,DEF' is a malformed list, not "ABC,DEF"
        with pytest.raises(ProximoError):
            _check_queue_ids("ABC123,,DEF456")

    def test_lone_comma_raises(self):
        with pytest.raises(ProximoError):
            _check_queue_ids(",")

    def test_trailing_comma_raises(self):
        with pytest.raises(ProximoError):
            _check_queue_ids("ABC123,")


class TestCheckBackupFilename:
    def test_accepts_valid_filename(self):
        assert _check_backup_filename("pmg-backup_2026_07_17.tgz") == "pmg-backup_2026_07_17.tgz"

    def test_rejects_wrong_prefix(self):
        # the schema PATTERN is 'pmg-backup_...', not the description prose's 'proxmox-backup_'
        with pytest.raises(ProximoError):
            _check_backup_filename("proxmox-backup_2026_07_17.tgz")

    def test_rejects_wrong_extension(self):
        with pytest.raises(ProximoError):
            _check_backup_filename("pmg-backup_2026_07_17.tar.gz")

    def test_rejects_path_traversal(self):
        with pytest.raises(ProximoError):
            _check_backup_filename("../../etc/passwd")

    def test_rejects_too_short(self):
        with pytest.raises(ProximoError):
            _check_backup_filename("a.tgz")


class TestCheckSortfieldSortdir:
    @pytest.mark.parametrize("value", sorted(_SORTFIELDS))
    def test_sortfield_accepts_all_declared_values(self, value):
        assert _check_sortfield(value) == value

    def test_sortfield_rejects_garbage(self):
        with pytest.raises(ProximoError):
            _check_sortfield("not-a-field")

    @pytest.mark.parametrize("value", sorted(_SORTDIRS))
    def test_sortdir_accepts_all_declared_values(self, value):
        assert _check_sortdir(value) == value

    def test_sortdir_rejects_garbage(self):
        with pytest.raises(ProximoError):
            _check_sortdir("sideways")


class TestCheckNonnegInt:
    def test_accepts_zero(self):
        assert _check_nonneg_int(0, "start") == 0

    def test_accepts_positive(self):
        assert _check_nonneg_int(50, "limit") == 50

    def test_rejects_negative(self):
        with pytest.raises(ProximoError):
            _check_nonneg_int(-1, "start")

    def test_rejects_non_integer(self):
        with pytest.raises(ProximoError):
            _check_nonneg_int("not-a-number", "limit")


class TestServiceStopRisk:
    @pytest.mark.parametrize("service", sorted(_MAIL_CRITICAL_SERVICES))
    def test_mail_critical_services_are_high(self, service):
        assert _service_stop_risk(service) == RISK_HIGH

    @pytest.mark.parametrize("service", ["pmgproxy", "pmgdaemon", "ssh", "clamav-daemon"])
    def test_other_services_are_medium(self, service):
        assert _service_stop_risk(service) == RISK_MEDIUM


# ---------------------------------------------------------------------------
# 4. Chunk 9b — backend functions
# ---------------------------------------------------------------------------


def test_task_stop_uses_correct_path():
    api = _api()
    task_stop(api, "UPID:pmg:00001:0:0:0:test:0:root@pam:", "pmg")
    assert api.seen["path"] == "/nodes/pmg/tasks/UPID:pmg:00001:0:0:0:test:0:root@pam:"
    assert api.seen["method"] == "DELETE"


def test_task_stop_rejects_invalid_upid():
    api = _api()
    with pytest.raises(ProximoError):
        task_stop(api, "not-a-upid", "pmg")


def test_task_log_uses_correct_path_and_params():
    api = _api(get_return=[{"n": 1, "t": "line one"}])
    result = task_log(api, "UPID:pmg:1:2:3:test:0:root@pam:", "pmg", start=5, limit=10)
    assert api.seen["path"] == "/nodes/pmg/tasks/UPID:pmg:1:2:3:test:0:root@pam:/log"
    assert api.seen["params"] == {"start": 5, "limit": 10}
    assert result == [{"n": 1, "t": "line one"}]


def test_task_status_uses_correct_path():
    api = _api(get_return={"pid": 123, "status": "running"})
    result = task_status(api, "UPID:pmg:1:2:3:test:0:root@pam:", "pmg")
    assert api.seen["path"] == "/nodes/pmg/tasks/UPID:pmg:1:2:3:test:0:root@pam:/status"
    assert result == {"pid": 123, "status": "running"}


def test_report_uses_correct_path():
    api = _api(get_return="diagnostic dump")
    result = report(api, "pmg")
    assert api.seen["path"] == "/nodes/pmg/report"
    assert result == "diagnostic dump"


def test_report_falls_back_to_empty_string():
    api = _api(get_return=None)
    assert report(api, "pmg") == ""


class TestJournal:
    def test_uses_correct_path_no_params(self):
        api = _api(get_return=["line1", "line2"])
        result = journal(api, "pmg")
        assert api.seen["path"] == "/nodes/pmg/journal"
        assert api.seen["params"] is None
        assert result == ["line1", "line2"]

    def test_forwards_lastentries_since_until_as_ints(self):
        api = _api(get_return=[])
        journal(api, "pmg", lastentries=100, since=1700000000, until=1700003600)
        assert api.seen["params"] == {
            "lastentries": 100, "since": 1700000000, "until": 1700003600,
        }

    def test_forwards_cursor_params_as_strings(self):
        api = _api(get_return=[])
        journal(api, "pmg", startcursor="s;i=1", endcursor="s;i=2")
        assert api.seen["params"] == {"startcursor": "s;i=1", "endcursor": "s;i=2"}

    def test_rejects_negative_since(self):
        api = _api(get_return=[])
        with pytest.raises(ProximoError):
            journal(api, "pmg", since=-1)


class TestBackupFiles:
    def test_backup_list_uses_correct_path(self):
        api = _api(get_return=[{"filename": "pmg-backup_x.tgz", "size": 1, "timestamp": 1}])
        result = backup_list(api, "pmg")
        assert api.seen["path"] == "/nodes/pmg/backup"
        assert result == [{"filename": "pmg-backup_x.tgz", "size": 1, "timestamp": 1}]

    def test_backup_delete_uses_correct_path(self):
        api = _api()
        backup_delete(api, "pmg", "pmg-backup_x.tgz")
        assert api.seen["path"] == "/nodes/pmg/backup/pmg-backup_x.tgz"
        assert api.seen["method"] == "DELETE"

    def test_backup_delete_rejects_invalid_filename(self):
        api = _api()
        with pytest.raises(ProximoError):
            backup_delete(api, "pmg", "not-a-backup-file.zip")

    def test_backup_restore_uses_correct_path_and_defaults(self):
        api = _api()
        backup_restore(api, "pmg", "pmg-backup_x.tgz")
        assert api.seen["path"] == "/nodes/pmg/backup/pmg-backup_x.tgz"
        assert api.seen["method"] == "POST"
        assert api.seen["data"] == {"config": False, "database": True, "statistic": False}

    def test_backup_restore_forwards_all_flags(self):
        api = _api()
        backup_restore(api, "pmg", "pmg-backup_x.tgz", config=True, database=False, statistic=True)
        assert api.seen["data"] == {"config": True, "database": False, "statistic": True}

    def test_backup_restore_rejects_invalid_filename(self):
        api = _api()
        with pytest.raises(ProximoError):
            backup_restore(api, "pmg", "../../etc/passwd")


class TestPostfixQueue:
    def test_queue_list_uses_correct_path(self):
        api = _api(get_return=[{"sender": "a@example.test"}])
        result = postfix_queue_list(api, "pmg", "deferred")
        assert api.seen["path"] == "/nodes/pmg/postfix/queue/deferred"
        assert api.seen["params"] is None
        assert result == [{"sender": "a@example.test"}]

    def test_queue_list_forwards_filters(self):
        api = _api(get_return=[])
        postfix_queue_list(api, "pmg", "active", filter="x", limit=10, sortfield="sender", sortdir="ASC", start=5)
        assert api.seen["params"] == {
            "filter": "x", "limit": 10, "sortfield": "sender", "sortdir": "ASC", "start": 5,
        }

    def test_queue_list_sortdir_without_sortfield_raises(self):
        api = _api(get_return=[])
        with pytest.raises(ProximoError):
            postfix_queue_list(api, "pmg", "active", sortdir="ASC")

    def test_queue_list_rejects_invalid_queue(self):
        api = _api(get_return=[])
        with pytest.raises(ProximoError):
            postfix_queue_list(api, "pmg", "not-a-queue")

    def test_queue_list_rejects_filter_over_maxlength(self):
        # schema declares maxLength: 64 on GET /nodes/{node}/postfix/queue/{queue}'s filter param
        # (Wave-9b-review MINOR fix — mirrors _check_backup_filename/_check_config_digest's
        # own bounds-check convention).
        api = _api(get_return=[])
        with pytest.raises(ProximoError):
            postfix_queue_list(api, "pmg", "active", filter="x" * 65)

    def test_queue_list_accepts_filter_at_maxlength(self):
        api = _api(get_return=[])
        postfix_queue_list(api, "pmg", "active", filter="x" * 64)
        assert api.seen["params"]["filter"] == "x" * 64

    def test_message_get_uses_correct_path_and_default_params(self):
        api = _api(get_return="raw message content")
        result = postfix_queue_message_get(api, "pmg", "deferred", "ABC123")
        assert api.seen["path"] == "/nodes/pmg/postfix/queue/deferred/ABC123"
        assert api.seen["params"] == {"header": True, "body": False, "decode-header": False}
        assert result == "raw message content"

    def test_message_get_forwards_body_and_decode_header(self):
        api = _api(get_return="x")
        postfix_queue_message_get(api, "pmg", "deferred", "ABC123", header=False, body=True, decode_header=True)
        assert api.seen["params"] == {"header": False, "body": True, "decode-header": True}

    def test_queue_action_builds_expected_body(self):
        api = _api()
        postfix_queue_action(api, "pmg", "deferred", "delete", "ABC123,DEF456")
        assert api.seen["path"] == "/nodes/pmg/postfix/queue/deferred"
        assert api.seen["data"] == {"action": "delete", "ids": "ABC123,DEF456"}

    def test_queue_action_rejects_invalid_action(self):
        api = _api()
        with pytest.raises(ProximoError):
            postfix_queue_action(api, "pmg", "deferred", "purge", "ABC123")

    def test_queue_delete_all_uses_bare_path(self):
        api = _api()
        postfix_queue_delete_all(api, "pmg")
        assert api.seen["path"] == "/nodes/pmg/postfix/queue"
        assert api.seen["method"] == "DELETE"

    def test_queue_delete_queue_uses_scoped_path(self):
        api = _api()
        postfix_queue_delete_queue(api, "pmg", "hold")
        assert api.seen["path"] == "/nodes/pmg/postfix/queue/hold"
        assert api.seen["method"] == "DELETE"

    def test_message_delete_uses_correct_path(self):
        api = _api()
        postfix_queue_message_delete(api, "pmg", "deferred", "ABC123")
        assert api.seen["path"] == "/nodes/pmg/postfix/queue/deferred/ABC123"
        assert api.seen["method"] == "DELETE"

    def test_message_deliver_uses_correct_path(self):
        api = _api()
        postfix_queue_message_deliver(api, "pmg", "deferred", "ABC123")
        assert api.seen["path"] == "/nodes/pmg/postfix/queue/deferred/ABC123"
        assert api.seen["method"] == "POST"

    def test_discard_verify_cache_uses_correct_path(self):
        api = _api()
        postfix_discard_verify_cache(api, "pmg")
        assert api.seen["path"] == "/nodes/pmg/postfix/discard_verify_cache"
        assert api.seen["method"] == "POST"


class TestClamavSpamassassin:
    def test_clamav_database_get_uses_correct_path(self):
        api = _api(get_return=[{"type": "main", "nsigs": 100, "build_time": "x", "version": "1"}])
        result = clamav_database_get(api, "pmg")
        assert api.seen["path"] == "/nodes/pmg/clamav/database"
        assert result == [{"type": "main", "nsigs": 100, "build_time": "x", "version": "1"}]

    def test_clamav_database_update_uses_correct_path(self):
        api = _api()
        clamav_database_update(api, "pmg")
        assert api.seen["path"] == "/nodes/pmg/clamav/database"
        assert api.seen["method"] == "POST"

    def test_spamassassin_rules_get_uses_correct_path(self):
        api = _api(get_return=[{"channel": "x", "update_avail": False}])
        result = spamassassin_rules_get(api, "pmg")
        assert api.seen["path"] == "/nodes/pmg/spamassassin/rules"
        assert result == [{"channel": "x", "update_avail": False}]

    def test_spamassassin_rules_update_uses_correct_path(self):
        api = _api()
        spamassassin_rules_update(api, "pmg")
        assert api.seen["path"] == "/nodes/pmg/spamassassin/rules"
        assert api.seen["method"] == "POST"


class TestServiceLifecycle:
    def test_service_start_uses_correct_path(self):
        api = _api()
        service_start(api, "pmg", "postfix")
        assert api.seen["path"] == "/nodes/pmg/services/postfix/start"
        assert api.seen["method"] == "POST"

    def test_service_stop_uses_correct_path(self):
        api = _api()
        service_stop(api, "pmg", "postfix")
        assert api.seen["path"] == "/nodes/pmg/services/postfix/stop"

    def test_service_restart_uses_correct_path(self):
        api = _api()
        service_restart(api, "pmg", "postfix")
        assert api.seen["path"] == "/nodes/pmg/services/postfix/restart"

    def test_service_reload_uses_correct_path(self):
        api = _api()
        service_reload(api, "pmg", "postfix")
        assert api.seen["path"] == "/nodes/pmg/services/postfix/reload"

    def test_service_start_rejects_invalid_service_name(self):
        api = _api()
        with pytest.raises(ProximoError):
            service_start(api, "pmg", "not valid!")


# ---------------------------------------------------------------------------
# 5. Chunk 9b — plan factories
# ---------------------------------------------------------------------------


class TestPlanTaskStop:
    def test_risk_is_high(self):
        p = plan_task_stop("UPID:pmg:1:2:3:test:0:root@pam:", "pmg")
        assert p.risk == RISK_HIGH
        joined = " ".join(p.blast_radius).lower()
        assert "no undo" in joined or "cannot be automatically undone" in joined


class TestPlanBackupDelete:
    def test_risk_is_medium(self):
        p = plan_backup_delete("pmg", "pmg-backup_x.tgz")
        assert p.risk == RISK_MEDIUM


def _ruledb_capture_api(rules=2, who=1, what=1, when=1, actions=3, backup_exists=True,
                        raise_paths=()):
    """Path-aware fake for plan_backup_restore: backup_list + the 5 ruledb-family reads
    (mirrors pmg.py's own plan_ruledb_reset test fixtures' shape, kept self-contained here per
    this module's own confirm-sweep/unit-test convention)."""

    def fake_get(path, params=None):
        if path in raise_paths:
            raise ProximoError(f"simulated failure for {path}")
        if path == "/nodes/pmg/backup":
            fname = "pmg-backup_2026_07_17.tgz" if backup_exists else "pmg-backup_other.tgz"
            return [{"filename": fname, "size": 1, "timestamp": 1}]
        if path == "/config/ruledb/rules":
            return [{}] * rules
        if path == "/config/ruledb/who":
            return [{}] * who
        if path == "/config/ruledb/what":
            return [{}] * what
        if path == "/config/ruledb/when":
            return [{}] * when
        if path == "/config/ruledb/action/objects":
            return [{}] * actions
        return []

    return SimpleNamespace(_get=fake_get)


class TestPlanBackupRestore:
    def test_risk_is_high(self):
        api = _ruledb_capture_api()
        p = plan_backup_restore(api, "pmg", "pmg-backup_2026_07_17.tgz")
        assert p.risk == RISK_HIGH

    def test_first_blast_line_states_no_undo(self):
        api = _ruledb_capture_api()
        p = plan_backup_restore(api, "pmg", "pmg-backup_2026_07_17.tgz")
        assert "no undo" in p.blast_radius[0].lower()
        assert "pmg_backup_create" in p.blast_radius[0]

    def test_captures_ruledb_counts_when_database_true(self):
        api = _ruledb_capture_api(rules=5, who=2, what=3, when=4, actions=6)
        p = plan_backup_restore(api, "pmg", "pmg-backup_2026_07_17.tgz", database=True)
        assert p.current == {"rules": 5, "who_groups": 2, "what_groups": 3, "when_groups": 4, "action_objects": 6}
        joined = " ".join(p.blast_radius)
        assert "5 rules" in joined

    def test_no_ruledb_capture_when_database_false(self):
        api = _ruledb_capture_api()
        p = plan_backup_restore(api, "pmg", "pmg-backup_2026_07_17.tgz", database=False)
        assert p.current == {}
        joined = " ".join(p.blast_radius)
        assert "left untouched" in joined

    def test_existence_check_flags_missing_file(self):
        api = _ruledb_capture_api(backup_exists=False)
        p = plan_backup_restore(api, "pmg", "pmg-backup_2026_07_17.tgz")
        joined = " ".join(p.blast_radius)
        assert "not found" in joined

    def test_capture_failure_degrades_honestly(self):
        api = _ruledb_capture_api(raise_paths=("/config/ruledb/rules", "/nodes/pmg/backup"))
        p = plan_backup_restore(api, "pmg", "pmg-backup_2026_07_17.tgz")
        assert p.complete is False

    def test_config_true_adds_disclosure_line(self):
        api = _ruledb_capture_api()
        p = plan_backup_restore(api, "pmg", "pmg-backup_2026_07_17.tgz", config=True)
        joined = " ".join(p.blast_radius)
        assert "system configuration" in joined

    def test_statistic_true_adds_disclosure_line(self):
        api = _ruledb_capture_api()
        p = plan_backup_restore(api, "pmg", "pmg-backup_2026_07_17.tgz", statistic=True)
        joined = " ".join(p.blast_radius)
        assert "statistic" in joined.lower()


class TestPlanPostfixQueueAction:
    def test_delete_is_high(self):
        p = plan_postfix_queue_action("pmg", "deferred", "delete", "ABC123")
        assert p.risk == RISK_HIGH

    def test_deliver_is_medium(self):
        p = plan_postfix_queue_action("pmg", "deferred", "deliver", "ABC123")
        assert p.risk == RISK_MEDIUM


class TestPlanPostfixQueueDeleteAll:
    def test_risk_is_high(self):
        p = plan_postfix_queue_delete_all("pmg")
        assert p.risk == RISK_HIGH


class TestPlanPostfixQueueDeleteQueue:
    def test_risk_is_high(self):
        p = plan_postfix_queue_delete_queue("pmg", "hold")
        assert p.risk == RISK_HIGH


class TestPlanPostfixQueueMessageDelete:
    def test_risk_is_medium(self):
        p = plan_postfix_queue_message_delete("pmg", "deferred", "ABC123")
        assert p.risk == RISK_MEDIUM


class TestPlanPostfixQueueMessageDeliver:
    def test_risk_is_low(self):
        # mirrors pmg_postfix_flush's own LOW rating (pmg.py::plan_postfix_flush)
        p = plan_postfix_queue_message_deliver("pmg", "deferred", "ABC123")
        assert p.risk == RISK_LOW


class TestPlanServiceStop:
    @pytest.mark.parametrize("service", sorted(_MAIL_CRITICAL_SERVICES))
    def test_mail_critical_service_is_high(self, service):
        p = plan_service_stop("pmg", service)
        assert p.risk == RISK_HIGH
        assert "mail-flow-critical" in " ".join(p.blast_radius)

    def test_other_service_is_medium(self):
        p = plan_service_stop("pmg", "ssh")
        assert p.risk == RISK_MEDIUM
        assert "mail-flow-critical" not in " ".join(p.blast_radius)
