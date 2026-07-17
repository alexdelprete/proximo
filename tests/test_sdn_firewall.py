"""SDN vnet-scoped FIREWALL + IP MAPPINGS tests (Wave 7b, full-surface campaign) — fully
mocked, no live Proxmox.

Mirrors test_network.py / test_firewall.py's own conventions:
- Op functions: a tiny fake api recording method/path/data (`_rec()`).
- Plan functions: fake apis giving just enough for each plan's own safe-read to resolve.
- Every test is self-contained — no shared mutable state.

Coverage:
 1. Validators — _check_vnet_fw_type, _check_vnet_ip, _check_mac, option-key guards,
    _parse_delete_keys, _options_set_is_high, _vnet_fw_enable_flag
 2. Reads — vnet_firewall_options_get/rules_list/rule_get: URL construction
 3. vnet_firewall_options_set — PUT body, at-least-one-field guard, delete csv, digest,
    reserved-key guard
 4. vnet_firewall_rule_add — POST body (all fields), action/type validation, digest/pos
    forwarding (schema-declared, unlike the shipped guest/cluster/node family)
 5. vnet_firewall_rule_remove — digest pinned vs. op-time re-fetch vs. no-digest-found error
 6. vnet_firewall_rule_update — PUT body, moveto, at-least-one-field guard, digest handling
 7. vnet_ip_create/update/delete — POST/PUT/DELETE body construction, vmid PUT-only, no
    digest support at all on this family
 8. Plan factories — risk ladder (conditional HIGH/MEDIUM, MEDIUM floor, LOW/MEDIUM for IP
    mappings), safe-read found/not-found/check-error cases, LIVE/IMMEDIATE framing present
    in every mutation plan's blast_radius, digest disclosure, moveto framing
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from proximo.backends import ProximoError
from proximo.planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM
from proximo.sdn_firewall import (
    _check_mac,
    _check_vnet_fw_option_keys,
    _check_vnet_fw_type,
    _check_vnet_ip,
    _options_set_is_high,
    _parse_delete_keys,
    _vnet_fw_enable_flag,
    plan_vnet_firewall_options_set,
    plan_vnet_firewall_rule_add,
    plan_vnet_firewall_rule_remove,
    plan_vnet_firewall_rule_update,
    plan_vnet_ip_create,
    plan_vnet_ip_delete,
    plan_vnet_ip_update,
    vnet_firewall_options_get,
    vnet_firewall_options_set,
    vnet_firewall_rule_add,
    vnet_firewall_rule_get,
    vnet_firewall_rule_remove,
    vnet_firewall_rule_update,
    vnet_firewall_rules_list,
    vnet_ip_create,
    vnet_ip_delete,
    vnet_ip_update,
)

# ---------------------------------------------------------------------------
# Fake api
# ---------------------------------------------------------------------------


def _rec(node: str = "pve"):
    seen: dict = {}

    def g(path):
        seen["method"] = "GET"
        seen["path"] = path
        return seen.get("_get_return", [])

    def p(path, data=None):
        seen["method"] = "POST"
        seen["path"] = path
        seen["data"] = data
        return None

    def u(path, data=None):
        seen["method"] = "PUT"
        seen["path"] = path
        seen["data"] = data
        return None

    def d(path, params=None):
        seen["method"] = "DELETE"
        seen["path"] = path
        seen["params"] = params
        return None

    return SimpleNamespace(config=SimpleNamespace(node=node),
                           _get=g, _post=p, _put=u, _delete=d, seen=seen)


def _boom_api():
    def _boom(_path):
        raise RuntimeError("api unavailable")
    return SimpleNamespace(config=SimpleNamespace(node="pve"), _get=_boom)


# ---------------------------------------------------------------------------
# 1. Validators
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["in", "out", "forward", "group", "IN", "Forward"])
def test_check_vnet_fw_type_accepts_all_four(value):
    assert _check_vnet_fw_type(value) == value.lower()


def test_check_vnet_fw_type_rejects_unknown():
    with pytest.raises(ProximoError):
        _check_vnet_fw_type("sideways")


def test_check_vnet_fw_type_rejects_guest_direction_only_values_that_are_bogus():
    # 'in'/'out' ARE valid here too (subset overlap with firewall.py's direction enum) —
    # only values outside the 4-value set are rejected.
    assert _check_vnet_fw_type("in") == "in"
    assert _check_vnet_fw_type("out") == "out"


@pytest.mark.parametrize("value", ["10.0.0.5", "::1", "2001:db8::1", "192.168.1.1"])
def test_check_vnet_ip_accepts_v4_and_v6(value):
    assert _check_vnet_ip(value) == value


@pytest.mark.parametrize("value", ["10.0.0.0/24", "not-an-ip", "", "10.0.0.5,10.0.0.6"])
def test_check_vnet_ip_rejects_cidr_and_garbage(value):
    with pytest.raises(ProximoError):
        _check_vnet_ip(value)


@pytest.mark.parametrize("value", ["aa:bb:cc:dd:ee:ff", "AA:BB:CC:DD:EE:FF", "00:11:22:33:44:55"])
def test_check_mac_accepts_valid(value):
    assert _check_mac(value) == value


@pytest.mark.parametrize("value", ["aabbccddeeff", "aa:bb:cc:dd:ee", "aa:bb:cc:dd:ee:gg", "aa-bb-cc-dd-ee-ff", ""])
def test_check_mac_rejects_invalid(value):
    with pytest.raises(ProximoError):
        _check_mac(value)


def test_check_vnet_fw_option_keys_rejects_reserved():
    for bad in ("vnet", "delete", "digest"):
        with pytest.raises(ProximoError):
            _check_vnet_fw_option_keys({bad: "x"})


def test_check_vnet_fw_option_keys_accepts_real_options():
    _check_vnet_fw_option_keys({"enable": True, "policy_forward": "DROP", "log_level_forward": "info"})


def test_parse_delete_keys_list_and_csv():
    assert _parse_delete_keys(["enable", " policy_forward "]) == ["enable", "policy_forward"]
    assert _parse_delete_keys("enable, policy_forward") == ["enable", "policy_forward"]
    assert _parse_delete_keys(None) == []
    assert _parse_delete_keys("") == []


@pytest.mark.parametrize(
    "keys,deletes,expected",
    [
        (["enable"], [], True),
        (["policy_forward"], [], True),
        (["log_level_forward"], [], False),
        ([], ["enable"], True),
        ([], ["policy_forward"], True),
        ([], ["log_level_forward"], False),
        (["log_level_forward"], ["policy_forward"], True),
    ],
)
def test_options_set_is_high(keys, deletes, expected):
    assert _options_set_is_high(keys, deletes) is expected


@pytest.mark.parametrize(
    "raw,expected",
    [(None, True), (True, True), (False, False), (1, True), (0, False), ("1", True), ("0", False)],
)
def test_vnet_fw_enable_flag(raw, expected):
    assert _vnet_fw_enable_flag(raw) is expected


# ---------------------------------------------------------------------------
# 2. Reads
# ---------------------------------------------------------------------------


def test_vnet_firewall_options_get_url():
    api = _rec()
    vnet_firewall_options_get(api, "myvnet")
    assert api.seen["method"] == "GET"
    assert api.seen["path"] == "/cluster/sdn/vnets/myvnet/firewall/options"


def test_vnet_firewall_options_get_empty_defaults_to_dict():
    api = _rec()
    api.seen["_get_return"] = None
    assert vnet_firewall_options_get(api, "myvnet") == {}


def test_vnet_firewall_rules_list_url():
    api = _rec()
    vnet_firewall_rules_list(api, "myvnet")
    assert api.seen["path"] == "/cluster/sdn/vnets/myvnet/firewall/rules"


def test_vnet_firewall_rules_list_empty_defaults_to_list():
    api = _rec()
    api.seen["_get_return"] = None
    assert vnet_firewall_rules_list(api, "myvnet") == []


def test_vnet_firewall_rule_get_url():
    api = _rec()
    vnet_firewall_rule_get(api, "myvnet", 3)
    assert api.seen["path"] == "/cluster/sdn/vnets/myvnet/firewall/rules/3"


def test_vnet_firewall_rule_get_rejects_negative_pos():
    api = _rec()
    with pytest.raises(ProximoError):
        vnet_firewall_rule_get(api, "myvnet", -1)


def test_vnet_firewall_reads_reject_bad_vnet():
    api = _rec()
    with pytest.raises(ProximoError):
        vnet_firewall_options_get(api, "bad/vnet")
    with pytest.raises(ProximoError):
        vnet_firewall_rules_list(api, "bad vnet")


# ---------------------------------------------------------------------------
# 3. vnet_firewall_options_set
# ---------------------------------------------------------------------------


def test_vnet_firewall_options_set_puts_options():
    api = _rec()
    vnet_firewall_options_set(api, "myvnet", options={"enable": True, "policy_forward": "DROP"})
    assert api.seen["method"] == "PUT"
    assert api.seen["path"] == "/cluster/sdn/vnets/myvnet/firewall/options"
    assert api.seen["data"] == {"enable": True, "policy_forward": "DROP"}


def test_vnet_firewall_options_set_delete_csv():
    api = _rec()
    vnet_firewall_options_set(api, "myvnet", delete=["enable", "policy_forward"])
    assert api.seen["data"]["delete"] == "enable,policy_forward"


def test_vnet_firewall_options_set_digest():
    api = _rec()
    vnet_firewall_options_set(api, "myvnet", options={"enable": True}, digest="abc123")
    assert api.seen["data"]["digest"] == "abc123"


def test_vnet_firewall_options_set_requires_something():
    api = _rec()
    with pytest.raises(ProximoError):
        vnet_firewall_options_set(api, "myvnet")


def test_vnet_firewall_options_set_digest_alone_is_not_enough():
    api = _rec()
    with pytest.raises(ProximoError):
        vnet_firewall_options_set(api, "myvnet", digest="abc123")


def test_vnet_firewall_options_set_rejects_reserved_key_in_bag():
    api = _rec()
    with pytest.raises(ProximoError):
        vnet_firewall_options_set(api, "myvnet", options={"digest": "smuggled"})


# ---------------------------------------------------------------------------
# 4. vnet_firewall_rule_add
# ---------------------------------------------------------------------------


def test_vnet_firewall_rule_add_minimal():
    api = _rec()
    vnet_firewall_rule_add(api, "myvnet", "accept")
    assert api.seen["method"] == "POST"
    assert api.seen["path"] == "/cluster/sdn/vnets/myvnet/firewall/rules"
    assert api.seen["data"] == {"action": "ACCEPT", "type": "in"}


def test_vnet_firewall_rule_add_all_fields():
    api = _rec()
    vnet_firewall_rule_add(
        api, "myvnet", "drop", fw_type="forward", source="10.0.0.0/24", dest="10.99.99.0/24",
        proto="tcp", dport="22", sport="1024:2048", icmp_type="echo-request", iface="net0",
        log="info", macro="SSH", comment="test rule", enable=False, pos=2, digest="d1",
    )
    assert api.seen["data"] == {
        "action": "DROP", "type": "forward", "source": "10.0.0.0/24", "dest": "10.99.99.0/24",
        "proto": "tcp", "dport": "22", "sport": "1024:2048", "icmp-type": "echo-request",
        "iface": "net0", "log": "info", "macro": "SSH", "comment": "test rule", "enable": 0,
        "pos": 2, "digest": "d1",
    }


def test_vnet_firewall_rule_add_rejects_bad_action():
    api = _rec()
    with pytest.raises(ProximoError):
        vnet_firewall_rule_add(api, "myvnet", "sideways")


def test_vnet_firewall_rule_add_rejects_bad_type():
    api = _rec()
    with pytest.raises(ProximoError):
        vnet_firewall_rule_add(api, "myvnet", "accept", fw_type="sideways")


def test_vnet_firewall_rule_add_rejects_control_chars_in_comment():
    api = _rec()
    with pytest.raises(ProximoError):
        vnet_firewall_rule_add(api, "myvnet", "accept", comment="line1\nline2")


def test_vnet_firewall_rule_add_group_type_accepted():
    api = _rec()
    vnet_firewall_rule_add(api, "myvnet", "accept", fw_type="group")
    assert api.seen["data"]["type"] == "group"


# ---------------------------------------------------------------------------
# 5. vnet_firewall_rule_remove
# ---------------------------------------------------------------------------


def test_vnet_firewall_rule_remove_uses_pinned_digest():
    api = _rec()
    vnet_firewall_rule_remove(api, "myvnet", 0, digest="pinned")
    assert api.seen["method"] == "DELETE"
    assert api.seen["path"] == "/cluster/sdn/vnets/myvnet/firewall/rules/0"
    assert api.seen["params"] == {"digest": "pinned"}


def test_vnet_firewall_rule_remove_default_no_digest_succeeds():
    """Finding 1 fix: this schema's reads (rules list / rule get) never expose a digest field
    (schema-verified) — the default, no-digest-supplied call must SUCCEED, not raise. This is
    the exact break the Wave 7b review reproduced against the old fetch-or-fail design."""
    api = _rec()
    api.seen["_get_return"] = [{"pos": 0, "action": "ACCEPT", "type": "in"}]  # schema-true, no digest
    vnet_firewall_rule_remove(api, "myvnet", 0)
    assert api.seen["method"] == "DELETE"
    assert api.seen["params"] == {}


def test_vnet_firewall_rule_remove_never_reads_rules_list():
    """No plan-side/op-time re-fetch exists anymore — removing a rule with no digest given
    must not call the rules-list read at all."""
    api = _rec()
    calls = []
    orig_get = api._get
    def tracking_get(path):
        calls.append(path)
        return orig_get(path)
    api._get = tracking_get
    vnet_firewall_rule_remove(api, "myvnet", 0)
    assert calls == []


def test_vnet_firewall_rule_remove_rejects_bad_pos():
    api = _rec()
    with pytest.raises(ProximoError):
        vnet_firewall_rule_remove(api, "myvnet", -5, digest="x")


# ---------------------------------------------------------------------------
# 6. vnet_firewall_rule_update
# ---------------------------------------------------------------------------


def test_vnet_firewall_rule_update_puts_changed_fields_and_pinned_digest():
    api = _rec()
    vnet_firewall_rule_update(api, "myvnet", 1, action="drop", comment="updated", digest="pinned")
    assert api.seen["method"] == "PUT"
    assert api.seen["path"] == "/cluster/sdn/vnets/myvnet/firewall/rules/1"
    assert api.seen["data"] == {"action": "DROP", "comment": "updated", "digest": "pinned"}


def test_vnet_firewall_rule_update_type_key_is_type_not_fw_type():
    api = _rec()
    vnet_firewall_rule_update(api, "myvnet", 0, fw_type="forward", digest="d")
    assert api.seen["data"]["type"] == "forward"
    assert "fw_type" not in api.seen["data"]


def test_vnet_firewall_rule_update_moveto():
    api = _rec()
    vnet_firewall_rule_update(api, "myvnet", 0, moveto=5, digest="d")
    assert api.seen["data"]["moveto"] == 5


def test_vnet_firewall_rule_update_default_no_digest_succeeds():
    """Finding 1 fix: same schema-true fact as rule_remove — no digest field on any read on
    this plane. The default, no-digest-supplied update must SUCCEED (no digest key at all in
    the PUT body), not raise."""
    api = _rec()
    api.seen["_get_return"] = [{"pos": 0, "action": "ACCEPT", "type": "in"}]  # schema-true, no digest
    vnet_firewall_rule_update(api, "myvnet", 0, action="drop")
    assert api.seen["data"] == {"action": "DROP"}
    assert "digest" not in api.seen["data"]


def test_vnet_firewall_rule_update_requires_at_least_one_field():
    api = _rec()
    with pytest.raises(ProximoError):
        vnet_firewall_rule_update(api, "myvnet", 0)


def test_vnet_firewall_rule_update_enable_false_sends_zero():
    api = _rec()
    vnet_firewall_rule_update(api, "myvnet", 0, enable=False, digest="d")
    assert api.seen["data"]["enable"] == 0


# ---------------------------------------------------------------------------
# 7. vnet_ip_create/update/delete
# ---------------------------------------------------------------------------


def test_vnet_ip_create_minimal():
    api = _rec()
    vnet_ip_create(api, "myvnet", "myzone", "10.0.0.5")
    assert api.seen["method"] == "POST"
    assert api.seen["path"] == "/cluster/sdn/vnets/myvnet/ips"
    assert api.seen["data"] == {"ip": "10.0.0.5", "vnet": "myvnet", "zone": "myzone"}


def test_vnet_ip_create_with_mac():
    api = _rec()
    vnet_ip_create(api, "myvnet", "myzone", "10.0.0.5", mac="aa:bb:cc:dd:ee:ff")
    assert api.seen["data"]["mac"] == "aa:bb:cc:dd:ee:ff"


def test_vnet_ip_create_rejects_bad_ip():
    api = _rec()
    with pytest.raises(ProximoError):
        vnet_ip_create(api, "myvnet", "myzone", "10.0.0.0/24")


def test_vnet_ip_create_rejects_bad_mac():
    api = _rec()
    with pytest.raises(ProximoError):
        vnet_ip_create(api, "myvnet", "myzone", "10.0.0.5", mac="not-a-mac")


def test_vnet_ip_create_never_sends_digest():
    api = _rec()
    vnet_ip_create(api, "myvnet", "myzone", "10.0.0.5")
    assert "digest" not in api.seen["data"]


def test_vnet_ip_update_with_vmid_and_mac():
    api = _rec()
    vnet_ip_update(api, "myvnet", "myzone", "10.0.0.5", mac="aa:bb:cc:dd:ee:ff", vmid="100")
    assert api.seen["method"] == "PUT"
    assert api.seen["path"] == "/cluster/sdn/vnets/myvnet/ips"
    assert api.seen["data"] == {
        "ip": "10.0.0.5", "vnet": "myvnet", "zone": "myzone",
        "mac": "aa:bb:cc:dd:ee:ff", "vmid": "100",
    }


def test_vnet_ip_update_minimal_has_no_optional_fields():
    api = _rec()
    vnet_ip_update(api, "myvnet", "myzone", "10.0.0.5")
    assert api.seen["data"] == {"ip": "10.0.0.5", "vnet": "myvnet", "zone": "myzone"}


def test_vnet_ip_update_rejects_bad_vmid():
    api = _rec()
    with pytest.raises(ProximoError):
        vnet_ip_update(api, "myvnet", "myzone", "10.0.0.5", vmid="not-numeric")


def test_vnet_ip_delete_minimal():
    api = _rec()
    vnet_ip_delete(api, "myvnet", "myzone", "10.0.0.5")
    assert api.seen["method"] == "DELETE"
    assert api.seen["path"] == "/cluster/sdn/vnets/myvnet/ips"
    assert api.seen["params"] == {"ip": "10.0.0.5", "vnet": "myvnet", "zone": "myzone"}


def test_vnet_ip_delete_with_mac_disambiguates():
    api = _rec()
    vnet_ip_delete(api, "myvnet", "myzone", "10.0.0.5", mac="aa:bb:cc:dd:ee:ff")
    assert api.seen["params"]["mac"] == "aa:bb:cc:dd:ee:ff"


def test_vnet_ip_ops_reject_bad_zone_or_vnet():
    api = _rec()
    with pytest.raises(ProximoError):
        vnet_ip_create(api, "bad/vnet", "myzone", "10.0.0.5")
    with pytest.raises(ProximoError):
        vnet_ip_create(api, "myvnet", "bad zone", "10.0.0.5")


# ---------------------------------------------------------------------------
# 8. Plan factories
# ---------------------------------------------------------------------------

# --- options_set ---

def test_plan_vnet_firewall_options_set_high_on_enable():
    api = _rec()
    api.seen["_get_return"] = {"enable": 0}
    plan = plan_vnet_firewall_options_set(api, "myvnet", options={"enable": True})
    assert plan.risk == RISK_HIGH
    assert any("immediate" in b.lower() for b in plan.blast_radius)


def test_plan_vnet_firewall_options_set_high_on_policy_forward():
    api = _rec()
    api.seen["_get_return"] = {}
    plan = plan_vnet_firewall_options_set(api, "myvnet", options={"policy_forward": "DROP"})
    assert plan.risk == RISK_HIGH


def test_plan_vnet_firewall_options_set_medium_on_log_level_only():
    api = _rec()
    api.seen["_get_return"] = {}
    plan = plan_vnet_firewall_options_set(api, "myvnet", options={"log_level_forward": "info"})
    assert plan.risk == RISK_MEDIUM


def test_plan_vnet_firewall_options_set_high_on_delete_enable():
    api = _rec()
    api.seen["_get_return"] = {}
    plan = plan_vnet_firewall_options_set(api, "myvnet", delete=["enable"])
    assert plan.risk == RISK_HIGH


# --- Finding 2 fix: direction-aware blast_radius text (Wave 7b review) ---
# The review's three exact repro cases were all classified with the SAME "cutting ALL
# forwarded traffic" text even though all three actually REMOVE protection. Each must now
# assert the loosening (protection-removal) text, not the tightening/cut text.


def test_plan_vnet_firewall_options_set_disable_enable_is_loosening_text():
    """Review repro case 1: enable=False actually REMOVES enforcement — must NOT get the
    'cut ALL forwarded traffic' tightening line."""
    api = _rec()
    api.seen["_get_return"] = {"enable": 1}
    plan = plan_vnet_firewall_options_set(api, "myvnet", options={"enable": False})
    blast = " ".join(plan.blast_radius).lower()
    assert "removes" in blast and "protection" in blast
    assert "cut all forwarded traffic" not in blast


def test_plan_vnet_firewall_options_set_policy_forward_accept_is_loosening_text():
    """Review repro case 2: policy_forward=ACCEPT actually OPENS forwarded traffic — must
    NOT get the 'cut ALL forwarded traffic' tightening line."""
    api = _rec()
    api.seen["_get_return"] = {"policy_forward": "DROP"}
    plan = plan_vnet_firewall_options_set(api, "myvnet", options={"policy_forward": "ACCEPT"})
    blast = " ".join(plan.blast_radius).lower()
    assert "removes" in blast and "protection" in blast
    assert "cut all forwarded traffic" not in blast


def test_plan_vnet_firewall_options_set_delete_enable_is_loosening_text():
    """Review repro case 3: delete=["enable"] reverts to the schema's default (0/disabled) —
    a protection-removing operation — must NOT get the tightening line."""
    api = _rec()
    api.seen["_get_return"] = {"enable": 1}
    plan = plan_vnet_firewall_options_set(api, "myvnet", delete=["enable"])
    blast = " ".join(plan.blast_radius).lower()
    assert "removes" in blast and "protection" in blast
    assert "cut all forwarded traffic" not in blast


def test_plan_vnet_firewall_options_set_enable_true_is_tightening_cut_warning():
    """An actual tightening call (enable=True) still gets the immediate-cut warning."""
    api = _rec()
    api.seen["_get_return"] = {"enable": 0}
    plan = plan_vnet_firewall_options_set(api, "myvnet", options={"enable": True})
    blast = " ".join(plan.blast_radius).lower()
    assert "cut all forwarded traffic" in blast


def test_plan_vnet_firewall_options_set_policy_forward_drop_is_tightening_cut_warning():
    api = _rec()
    api.seen["_get_return"] = {}
    plan = plan_vnet_firewall_options_set(api, "myvnet", options={"policy_forward": "DROP"})
    blast = " ".join(plan.blast_radius).lower()
    assert "cut all forwarded traffic" in blast


def test_plan_vnet_firewall_options_set_unclassifiable_value_is_mixed_line():
    """An unrecognized policy_forward value can't be classified tighten/loosen — must go to
    the honest combined/mixed line, never silently to either side."""
    api = _rec()
    api.seen["_get_return"] = {}
    plan = plan_vnet_firewall_options_set(api, "myvnet", options={"policy_forward": "SIDEWAYS"})
    blast = " ".join(plan.blast_radius).lower()
    assert "cut all forwarded traffic" not in blast
    assert "depending on" in blast or "verify" in blast


def test_plan_vnet_firewall_options_set_conflicting_directions_is_mixed_line():
    """enable=True (tighten) + policy_forward=ACCEPT (loosen) in the SAME call is a genuine
    conflicting-direction case — must go to the mixed line, not either single-direction one."""
    api = _rec()
    api.seen["_get_return"] = {}
    plan = plan_vnet_firewall_options_set(
        api, "myvnet", options={"enable": True, "policy_forward": "ACCEPT"},
    )
    blast = " ".join(plan.blast_radius).lower()
    assert "cut all forwarded traffic" not in blast
    assert "depending on" in blast or "verify" in blast


def test_plan_vnet_firewall_options_set_never_softened_by_apply_language():
    api = _rec()
    api.seen["_get_return"] = {}
    plan = plan_vnet_firewall_options_set(api, "myvnet", options={"enable": True})
    blast = " ".join(plan.blast_radius).lower()
    assert "inert" not in blast
    assert "immediate" in blast or "instant" in blast


def test_plan_vnet_firewall_options_set_read_failed_is_incomplete():
    plan = plan_vnet_firewall_options_set(_boom_api(), "myvnet", options={"enable": True})
    assert plan.complete is False
    assert any("could not read" in b.lower() for b in plan.blast_radius)


def test_plan_vnet_firewall_options_set_current_filtered_to_touched_keys():
    api = _rec()
    api.seen["_get_return"] = {"enable": 1, "policy_forward": "ACCEPT", "log_level_forward": "info"}
    plan = plan_vnet_firewall_options_set(api, "myvnet", options={"enable": False})
    assert plan.current == {"enable": 1}


# --- rule_add ---

def test_plan_vnet_firewall_rule_add_is_medium_floor():
    plan = plan_vnet_firewall_rule_add("myvnet", "accept", "in", dport="22")
    assert plan.risk == RISK_MEDIUM
    assert plan.current == {}


def test_plan_vnet_firewall_rule_add_live_immediate_language():
    plan = plan_vnet_firewall_rule_add("myvnet", "drop", "forward")
    blast = " ".join(plan.blast_radius).lower()
    assert "instant" in blast
    assert "no pve_sdn_apply gate" in blast


def test_plan_vnet_firewall_rule_add_discloses_rule_summary():
    plan = plan_vnet_firewall_rule_add("myvnet", "accept", "in", source="10.0.0.0/24", dport="22")
    blast = " ".join(plan.blast_radius) + plan.change
    assert "10.0.0.0/24" in blast
    assert "22" in blast


def test_plan_vnet_firewall_rule_add_rejects_bad_action():
    with pytest.raises(ProximoError):
        plan_vnet_firewall_rule_add("myvnet", "sideways")


# --- rule_remove ---

def test_plan_vnet_firewall_rule_remove_found_case():
    api = _rec()
    api.seen["_get_return"] = [{"pos": 0, "action": "ACCEPT", "type": "in"}]  # schema-true, no digest
    plan = plan_vnet_firewall_rule_remove(api, "myvnet", 0)
    assert plan.risk == RISK_MEDIUM
    assert plan.complete is True
    assert "digest" not in plan.current


def test_plan_vnet_firewall_rule_remove_not_found_case():
    api = _rec()
    api.seen["_get_return"] = []
    plan = plan_vnet_firewall_rule_remove(api, "myvnet", 3)
    assert plan.risk == RISK_MEDIUM
    assert plan.complete is True
    assert plan.current == {}


def test_plan_vnet_firewall_rule_remove_check_error_is_incomplete():
    plan = plan_vnet_firewall_rule_remove(_boom_api(), "myvnet", 0)
    assert plan.complete is False
    assert any("lookup failed" in b.lower() for b in plan.blast_radius)


def test_plan_vnet_firewall_rule_remove_race_honesty_line():
    """Finding 1 fix: the plan states the digest-asymmetry race honestly instead of
    disclosing a digest that will never actually be there against a real server."""
    api = _rec()
    api.seen["_get_return"] = [{"pos": 0, "action": "ACCEPT", "type": "in"}]
    plan = plan_vnet_firewall_rule_remove(api, "myvnet", 0)
    blast = " ".join(plan.blast_radius).lower()
    assert "no digest field" in blast
    assert "out-of-band" in blast
    assert "positions can shift" in blast


def test_plan_vnet_firewall_rule_remove_disabled_rule_is_staged_language():
    api = _rec()
    api.seen["_get_return"] = [{"pos": 0, "action": "ACCEPT", "type": "in", "enable": 0}]
    plan = plan_vnet_firewall_rule_remove(api, "myvnet", 0)
    blast = " ".join(plan.blast_radius).lower()
    assert "staged" in blast


# --- rule_update ---

def test_plan_vnet_firewall_rule_update_found_case():
    api = _rec()
    api.seen["_get_return"] = [{"pos": 0, "action": "ACCEPT", "type": "in"}]  # schema-true, no digest
    plan = plan_vnet_firewall_rule_update(api, "myvnet", 0, action="DROP")
    assert plan.risk == RISK_MEDIUM
    assert plan.complete is True
    assert "DROP" in plan.change


def test_plan_vnet_firewall_rule_update_check_error_is_incomplete():
    plan = plan_vnet_firewall_rule_update(_boom_api(), "myvnet", 0, action="DROP")
    assert plan.complete is False


def test_plan_vnet_firewall_rule_update_moveto_framing():
    api = _rec()
    api.seen["_get_return"] = [{"pos": 0, "action": "ACCEPT", "type": "in"}]
    plan = plan_vnet_firewall_rule_update(api, "myvnet", 0, moveto=5)
    blast = " ".join(plan.blast_radius).lower()
    assert "moves" in blast
    assert "ignores" in blast


def test_plan_vnet_firewall_rule_update_rejects_bad_action():
    api = _rec()
    with pytest.raises(ProximoError):
        plan_vnet_firewall_rule_update(api, "myvnet", 0, action="sideways")


def test_plan_vnet_firewall_rule_update_race_honesty_line():
    """Finding 1 fix: same race-honesty line as rule_remove — no digest field ever appears
    in this schema's reads, so the plan can only offer the captured snapshot as best-effort
    identity evidence, not disclose a digest to pin."""
    api = _rec()
    api.seen["_get_return"] = [{"pos": 0, "action": "ACCEPT", "type": "in"}]  # schema-true, no digest
    plan = plan_vnet_firewall_rule_update(api, "myvnet", 0, action="DROP")
    assert "digest" not in plan.current
    blast = " ".join(plan.blast_radius).lower()
    assert "no digest field" in blast
    assert "out-of-band" in blast
    assert "positions can shift" in blast


# --- ip mappings ---

def test_plan_vnet_ip_create_is_low_no_api_needed():
    plan = plan_vnet_ip_create("myvnet", "myzone", "10.0.0.5")
    assert plan.risk == RISK_LOW
    assert plan.current == {}
    assert any("no digest support" in b.lower() for b in plan.blast_radius)


def test_plan_vnet_ip_update_is_low():
    plan = plan_vnet_ip_update("myvnet", "myzone", "10.0.0.5", vmid="100")
    assert plan.risk == RISK_LOW
    assert "100" in plan.change


def test_plan_vnet_ip_delete_is_medium():
    plan = plan_vnet_ip_delete("myvnet", "myzone", "10.0.0.5")
    assert plan.risk == RISK_MEDIUM
    assert any("active use" in b.lower() for b in plan.blast_radius)


def test_plan_vnet_ip_create_rejects_bad_ip():
    with pytest.raises(ProximoError):
        plan_vnet_ip_create("myvnet", "myzone", "not-an-ip")


def test_plan_vnet_ip_ops_no_read_back_language():
    for plan in (
        plan_vnet_ip_create("myvnet", "myzone", "10.0.0.5"),
        plan_vnet_ip_update("myvnet", "myzone", "10.0.0.5"),
        plan_vnet_ip_delete("myvnet", "myzone", "10.0.0.5"),
    ):
        assert any("no get" in b.lower() or "no read-back" in b.lower() for b in plan.blast_radius)
