"""Firewall pillar tests — fully mocked, no live Proxmox.

Mirrors test_provisioning.py / test_storage.py style:
- Op functions: SimpleNamespace fake apis that record _post / _delete / _put calls.
- Plan functions: fake apis that supply firewall_rules_list / firewall_options_get.
- Validator-rejection tests use pytest.raises(ProximoError).
- Every test is self-contained — no shared mutable state.

Key invariants verified:
  1. URL / param construction for each scope (cluster / node / guest).
  2. PLAN-before-mutate (plan factories are separate from ops — server gates them).
  3. RISK_HIGH for firewall_set_enabled (both enable and disable directions).
  4. RISK_MEDIUM floor for rule add / remove / update.
  5. Validator rejection for bad scope / pos / action / direction.
  6. plan_firewall_rule_remove reads the current rule (one safe read) to show what is removed.
  7. plan_firewall_set_enabled reads current options to show the current state.
  8. No-UNDO language present in all mutating plans.
  9. Lockout warning present in set_enabled plans.
 10. Cluster-scope kill-switch warning in set_enabled plans.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from proximo.backends import ProximoError
from proximo.firewall import (
    firewall_options_get,
    firewall_rule_add,
    firewall_rule_remove,
    firewall_rule_update,
    firewall_rules_list,
    firewall_set_enabled,
    ipset_list,
    plan_firewall_rule_add,
    plan_firewall_rule_remove,
    plan_firewall_rule_update,
    plan_firewall_set_enabled,
    security_groups_list,
)
from proximo.planning import RISK_HIGH, RISK_MEDIUM

# ---------------------------------------------------------------------------
# Test fakes
# ---------------------------------------------------------------------------


def _api(node: str = "pve") -> SimpleNamespace:
    """Fake api that records _get / _post / _delete / _put calls and exposes config.node.

    By default _get returns [{"pos": 0, "digest": "test-digest-abc"}] so that
    firewall_rule_remove and firewall_rule_update can obtain a digest (FIX 3).
    Override seen["_get_return"] to change the returned list.
    """
    seen: dict = {}

    def fake_get(path):
        seen["method"] = "GET"
        seen["path"] = path
        # Default: a single rule entry with a digest so remove/update ops have a digest.
        return seen.get("_get_return", [{"pos": 0, "digest": "test-digest-abc"}])

    def fake_post(path, data=None):
        seen["method"] = "POST"
        seen["path"] = path
        seen["data"] = data
        return None

    def fake_delete(path, params=None):
        seen["method"] = "DELETE"
        seen["path"] = path
        seen["params"] = params
        return None

    def fake_put(path, data=None):
        seen["method"] = "PUT"
        seen["path"] = path
        seen["data"] = data
        return None

    return SimpleNamespace(
        config=SimpleNamespace(node=node),
        _get=fake_get,
        _post=fake_post,
        _delete=fake_delete,
        _put=fake_put,
        seen=seen,
    )


class _RulesApi:
    """Fake api for plan_firewall_rule_remove and plan_firewall_rule_update:
    supplies firewall_rules_list via a fake _get that returns configured rules."""

    def __init__(
        self,
        rules: list[dict],
        node: str = "pve",
        raise_on_list: bool = False,
    ):
        self._rules = rules
        self.config = SimpleNamespace(node=node)
        self._raise = raise_on_list
        self._get_calls: list = []

    def _get(self, path):
        self._get_calls.append(path)
        if self._raise:
            raise RuntimeError("api unavailable")
        return self._rules


class _OptionsApi:
    """Fake api for plan_firewall_set_enabled: supplies firewall_options_get via _get."""

    def __init__(
        self,
        options: dict | None,
        node: str = "pve",
        raise_on_get: bool = False,
    ):
        self._options = options
        self.config = SimpleNamespace(node=node)
        self._raise = raise_on_get

    def _get(self, path):
        if self._raise:
            raise RuntimeError("api unavailable")
        return self._options or {}


# ---------------------------------------------------------------------------
# READ: firewall_rules_list — URL construction per scope
# ---------------------------------------------------------------------------


def test_rules_list_cluster_scope():
    api = _api()
    firewall_rules_list(api, scope="cluster")
    assert api.seen["path"] == "/cluster/firewall/rules"
    assert api.seen["method"] == "GET"


def test_rules_list_node_scope():
    api = _api(node="pve")
    firewall_rules_list(api, scope="node")
    assert api.seen["path"] == "/nodes/pve/firewall/rules"


def test_rules_list_node_scope_explicit_node():
    api = _api(node="pve")
    firewall_rules_list(api, scope="node", node="node2")
    assert "/nodes/node2/" in api.seen["path"]


def test_rules_list_guest_scope_lxc():
    api = _api()
    firewall_rules_list(api, scope="guest", vmid="100", kind="lxc")
    assert api.seen["path"] == "/nodes/pve/lxc/100/firewall/rules"


def test_rules_list_guest_scope_qemu():
    api = _api()
    firewall_rules_list(api, scope="guest", vmid="200", kind="qemu")
    assert api.seen["path"] == "/nodes/pve/qemu/200/firewall/rules"


def test_rules_list_returns_empty_list_on_none():
    api = _api()
    api.seen["_get_return"] = None
    result = firewall_rules_list(api, scope="cluster")
    assert result == []


def test_rules_list_rejects_bad_scope():
    api = _api()
    with pytest.raises(ProximoError):
        firewall_rules_list(api, scope="vpc")


def test_rules_list_guest_scope_requires_vmid():
    api = _api()
    with pytest.raises(ProximoError):
        firewall_rules_list(api, scope="guest")


# ---------------------------------------------------------------------------
# READ: firewall_options_get — URL construction per scope
# ---------------------------------------------------------------------------


def test_options_get_cluster_scope():
    api = _api()
    firewall_options_get(api, scope="cluster")
    assert api.seen["path"] == "/cluster/firewall/options"


def test_options_get_node_scope():
    api = _api()
    firewall_options_get(api, scope="node")
    assert "/firewall/options" in api.seen["path"]
    assert "/nodes/" in api.seen["path"]


def test_options_get_guest_scope():
    api = _api()
    firewall_options_get(api, scope="guest", vmid="100")
    assert api.seen["path"] == "/nodes/pve/lxc/100/firewall/options"


def test_options_get_returns_empty_dict_on_none():
    api = _api()
    api.seen["_get_return"] = None
    result = firewall_options_get(api, scope="cluster")
    assert result == {}


# ---------------------------------------------------------------------------
# READ: security_groups_list
# ---------------------------------------------------------------------------


def test_security_groups_list_uses_cluster_path():
    api = _api()
    security_groups_list(api)
    assert api.seen["path"] == "/cluster/firewall/groups"
    assert api.seen["method"] == "GET"


# ---------------------------------------------------------------------------
# READ: ipset_list
# ---------------------------------------------------------------------------


def test_ipset_list_cluster_scope():
    api = _api()
    ipset_list(api, scope="cluster")
    assert api.seen["path"] == "/cluster/firewall/ipset"


def test_ipset_list_node_scope():
    api = _api()
    ipset_list(api, scope="node")
    assert "/nodes/pve/firewall/ipset" == api.seen["path"]


# ---------------------------------------------------------------------------
# MUTATION: firewall_rule_add — URL + data shapes
# ---------------------------------------------------------------------------


def test_rule_add_cluster_scope_posts_correct_path():
    api = _api()
    firewall_rule_add(api, "ACCEPT", scope="cluster")
    assert api.seen["path"] == "/cluster/firewall/rules"
    assert api.seen["method"] == "POST"


def test_rule_add_node_scope_posts_correct_path():
    api = _api()
    firewall_rule_add(api, "DROP", scope="node")
    assert api.seen["path"] == "/nodes/pve/firewall/rules"


def test_rule_add_guest_scope_posts_correct_path():
    api = _api()
    firewall_rule_add(api, "ACCEPT", scope="guest", vmid="100")
    assert api.seen["path"] == "/nodes/pve/lxc/100/firewall/rules"


def test_rule_add_sends_required_fields():
    api = _api()
    firewall_rule_add(api, "ACCEPT", direction="in")
    d = api.seen["data"]
    assert d["action"] == "ACCEPT"
    assert d["type"] == "in"
    assert "enable" in d


def test_rule_add_enable_true_sends_1():
    api = _api()
    firewall_rule_add(api, "DROP", enable=True)
    assert api.seen["data"]["enable"] == 1


def test_rule_add_enable_false_sends_0():
    api = _api()
    firewall_rule_add(api, "DROP", enable=False)
    assert api.seen["data"]["enable"] == 0


def test_rule_add_sends_optional_fields():
    api = _api()
    firewall_rule_add(api, "ACCEPT", source="192.168.1.0/24", dest="0.0.0.0/0",
                      dport="22", comment="allow ssh")
    d = api.seen["data"]
    assert d["source"] == "192.168.1.0/24"
    assert d["dest"] == "0.0.0.0/0"
    assert d["dport"] == "22"
    assert d["comment"] == "allow ssh"


def test_rule_add_omits_absent_optional_fields():
    api = _api()
    firewall_rule_add(api, "ACCEPT")
    d = api.seen["data"]
    assert "source" not in d
    assert "dest" not in d
    assert "dport" not in d
    assert "comment" not in d


def test_rule_add_rejects_invalid_action():
    api = _api()
    with pytest.raises(ProximoError):
        firewall_rule_add(api, "FORWARD")


def test_rule_add_rejects_invalid_direction():
    api = _api()
    with pytest.raises(ProximoError):
        firewall_rule_add(api, "ACCEPT", direction="both")


def test_rule_add_rejects_bad_scope():
    api = _api()
    with pytest.raises(ProximoError):
        firewall_rule_add(api, "ACCEPT", scope="unknown")


def test_rule_add_action_is_uppercased():
    api = _api()
    firewall_rule_add(api, "accept")
    assert api.seen["data"]["action"] == "ACCEPT"


def test_rule_add_direction_is_lowercased():
    api = _api()
    firewall_rule_add(api, "DROP", direction="IN")
    assert api.seen["data"]["type"] == "in"


# ---------------------------------------------------------------------------
# MUTATION: firewall_rule_remove — URL + method
# ---------------------------------------------------------------------------


def test_rule_remove_cluster_scope_deletes_correct_path():
    api = _api()
    firewall_rule_remove(api, 3, scope="cluster")
    assert api.seen["path"] == "/cluster/firewall/rules/3"
    assert api.seen["method"] == "DELETE"


def test_rule_remove_node_scope():
    api = _api()
    firewall_rule_remove(api, 0, scope="node")
    assert api.seen["path"] == "/nodes/pve/firewall/rules/0"


def test_rule_remove_guest_scope():
    api = _api()
    firewall_rule_remove(api, 2, scope="guest", vmid="100")
    assert api.seen["path"] == "/nodes/pve/lxc/100/firewall/rules/2"


def test_rule_remove_rejects_negative_pos():
    api = _api()
    with pytest.raises(ProximoError):
        firewall_rule_remove(api, -1, scope="cluster")


def test_rule_remove_rejects_non_numeric_pos():
    api = _api()
    with pytest.raises(ProximoError):
        firewall_rule_remove(api, "first")


def test_rule_remove_rejects_bad_scope():
    api = _api()
    with pytest.raises(ProximoError):
        firewall_rule_remove(api, 0, scope="region")


# ---------------------------------------------------------------------------
# MUTATION: firewall_rule_update — URL + data + PUT verb
# ---------------------------------------------------------------------------


def test_rule_update_cluster_scope_puts_correct_path():
    api = _api()
    firewall_rule_update(api, 1, action="DROP")
    assert api.seen["path"] == "/cluster/firewall/rules/1"
    assert api.seen["method"] == "PUT"


def test_rule_update_node_scope():
    api = _api()
    firewall_rule_update(api, 2, scope="node", comment="updated")
    assert api.seen["path"] == "/nodes/pve/firewall/rules/2"


def test_rule_update_guest_scope():
    api = _api()
    firewall_rule_update(api, 0, scope="guest", vmid="100", action="REJECT")
    assert api.seen["path"] == "/nodes/pve/lxc/100/firewall/rules/0"


def test_rule_update_sends_action_field():
    api = _api()
    firewall_rule_update(api, 0, action="REJECT")
    assert api.seen["data"]["action"] == "REJECT"


def test_rule_update_sends_direction_as_type():
    api = _api()
    firewall_rule_update(api, 0, direction="out")
    assert api.seen["data"]["type"] == "out"


def test_rule_update_sends_enable_as_int():
    api = _api()
    firewall_rule_update(api, 0, enable=True)
    assert api.seen["data"]["enable"] == 1


def test_rule_update_rejects_empty_update():
    api = _api()
    with pytest.raises(ProximoError):
        firewall_rule_update(api, 0)


def test_rule_update_rejects_bad_action():
    api = _api()
    with pytest.raises(ProximoError):
        firewall_rule_update(api, 0, action="PASS")


def test_rule_update_rejects_negative_pos():
    api = _api()
    with pytest.raises(ProximoError):
        firewall_rule_update(api, -3, action="DROP")


# ---------------------------------------------------------------------------
# MUTATION: firewall_set_enabled — URL + data + PUT verb
# ---------------------------------------------------------------------------


def test_set_enabled_cluster_scope_puts_correct_path():
    api = _api()
    firewall_set_enabled(api, True, scope="cluster")
    assert api.seen["path"] == "/cluster/firewall/options"
    assert api.seen["method"] == "PUT"


def test_set_enabled_node_scope():
    api = _api()
    firewall_set_enabled(api, False, scope="node")
    assert api.seen["path"] == "/nodes/pve/firewall/options"


def test_set_enabled_guest_scope():
    api = _api()
    firewall_set_enabled(api, True, scope="guest", vmid="100")
    assert api.seen["path"] == "/nodes/pve/lxc/100/firewall/options"


def test_set_enabled_true_sends_enable_1():
    api = _api()
    firewall_set_enabled(api, True)
    assert api.seen["data"]["enable"] == 1


def test_set_enabled_false_sends_enable_0():
    api = _api()
    firewall_set_enabled(api, False)
    assert api.seen["data"]["enable"] == 0


def test_set_enabled_rejects_bad_scope():
    api = _api()
    with pytest.raises(ProximoError):
        firewall_set_enabled(api, True, scope="datacenter")


# ---------------------------------------------------------------------------
# PLAN: plan_firewall_rule_add
# ---------------------------------------------------------------------------


def test_plan_rule_add_is_medium_risk():
    p = plan_firewall_rule_add("ACCEPT", scope="cluster")
    assert p.risk == RISK_MEDIUM


def test_plan_rule_add_action_string():
    p = plan_firewall_rule_add("DROP")
    assert p.action == "pve_firewall_rule_add"


def test_plan_rule_add_surfaces_scope_in_target():
    p = plan_firewall_rule_add("ACCEPT", scope="cluster")
    assert "cluster" in p.target


def test_plan_rule_add_surfaces_rule_in_change():
    p = plan_firewall_rule_add("ACCEPT", direction="in", scope="cluster")
    assert "ACCEPT" in p.change
    assert "in" in p.change


def test_plan_rule_add_surfaces_source_and_dport_when_given():
    p = plan_firewall_rule_add("ACCEPT", source="10.0.0.0/8", dport="22")
    assert "10.0.0.0/8" in p.change or any("10.0.0.0/8" in b for b in p.blast_radius)
    assert "22" in p.change or any("22" in b for b in p.blast_radius)


def test_plan_rule_add_blast_mentions_no_undo():
    p = plan_firewall_rule_add("ACCEPT")
    text = " ".join(p.blast_radius).lower()
    assert "no undo" in text or "not in guest snapshots" in text


def test_plan_rule_add_risk_reasons_not_empty():
    p = plan_firewall_rule_add("DROP")
    assert len(p.risk_reasons) >= 1


def test_plan_rule_add_rejects_invalid_action():
    with pytest.raises(ProximoError):
        plan_firewall_rule_add("MASQUERADE")


def test_plan_rule_add_rejects_bad_scope():
    with pytest.raises(ProximoError):
        plan_firewall_rule_add("ACCEPT", scope="zone")


def test_plan_rule_add_action_case_insensitive():
    p = plan_firewall_rule_add("accept")
    assert "ACCEPT" in p.change


# ---------------------------------------------------------------------------
# PLAN: plan_firewall_rule_remove
# ---------------------------------------------------------------------------


def test_plan_rule_remove_is_medium_risk():
    api = _RulesApi([{"pos": 0, "action": "DROP", "type": "in"}])
    p = plan_firewall_rule_remove(api, 0)
    assert p.risk == RISK_MEDIUM


def test_plan_rule_remove_action_string():
    api = _RulesApi([])
    p = plan_firewall_rule_remove(api, 1)
    assert p.action == "pve_firewall_rule_remove"


def test_plan_rule_remove_reads_rule_and_surfaces_in_current():
    api = _RulesApi([{"pos": 2, "action": "ACCEPT", "type": "in", "dport": "22"}])
    p = plan_firewall_rule_remove(api, 2)
    assert p.current.get("action") == "ACCEPT"
    assert p.current.get("pos") == 2


def test_plan_rule_remove_surfaces_action_in_change():
    api = _RulesApi([{"pos": 0, "action": "DROP", "type": "in"}])
    p = plan_firewall_rule_remove(api, 0)
    assert "DROP" in p.change or "DROP" in " ".join(p.blast_radius)


def test_plan_rule_remove_blast_mentions_position_shift():
    api = _RulesApi([{"pos": 0, "action": "DROP", "type": "out"}])
    p = plan_firewall_rule_remove(api, 0)
    text = " ".join(p.blast_radius).lower()
    assert "shift" in text or "position" in text


def test_plan_rule_remove_blast_mentions_no_undo():
    api = _RulesApi([])
    p = plan_firewall_rule_remove(api, 0)
    text = " ".join(p.blast_radius).lower()
    assert "no undo" in text or "not in guest snapshots" in text


def test_plan_rule_remove_blast_mentions_lockout_risk():
    api = _RulesApi([{"pos": 0, "action": "ACCEPT", "type": "in"}])
    p = plan_firewall_rule_remove(api, 0)
    text = " ".join(p.blast_radius).lower()
    assert "lockout" in text or "ssh" in text or "8006" in text


def test_plan_rule_remove_discloses_lookup_failure():
    api = _RulesApi([], raise_on_list=True)
    p = plan_firewall_rule_remove(api, 0)
    text = " ".join(p.blast_radius + p.risk_reasons).lower()
    assert "failed" in text or "could not" in text


def test_plan_rule_remove_rejects_negative_pos():
    api = _RulesApi([])
    with pytest.raises(ProximoError):
        plan_firewall_rule_remove(api, -1)


def test_plan_rule_remove_pos_in_target():
    api = _RulesApi([{"pos": 5, "action": "DROP", "type": "in"}])
    p = plan_firewall_rule_remove(api, 5)
    assert "5" in p.target


# ---------------------------------------------------------------------------
# PLAN: plan_firewall_rule_update
# ---------------------------------------------------------------------------


def test_plan_rule_update_is_medium_risk():
    api = _RulesApi([{"pos": 1, "action": "ACCEPT", "type": "in"}])
    p = plan_firewall_rule_update(api, 1, action="DROP")
    assert p.risk == RISK_MEDIUM


def test_plan_rule_update_action_string():
    api = _RulesApi([])
    p = plan_firewall_rule_update(api, 0, comment="new")
    assert p.action == "pve_firewall_rule_update"


def test_plan_rule_update_reads_current_state():
    api = _RulesApi([{"pos": 2, "action": "ACCEPT", "type": "out", "enable": 1}])
    p = plan_firewall_rule_update(api, 2, action="DROP")
    assert p.current.get("action") == "ACCEPT"


def test_plan_rule_update_change_includes_new_fields():
    api = _RulesApi([{"pos": 0, "action": "DROP", "type": "in"}])
    p = plan_firewall_rule_update(api, 0, action="ACCEPT", dport="443")
    assert "ACCEPT" in p.change or any("ACCEPT" in b for b in p.blast_radius)


def test_plan_rule_update_blast_mentions_position_shift():
    api = _RulesApi([{"pos": 0, "action": "DROP", "type": "in"}])
    p = plan_firewall_rule_update(api, 0, action="ACCEPT")
    text = " ".join(p.blast_radius).lower()
    assert "shift" in text or "position" in text


def test_plan_rule_update_blast_mentions_no_undo():
    api = _RulesApi([])
    p = plan_firewall_rule_update(api, 0, comment="x")
    text = " ".join(p.blast_radius).lower()
    assert "no undo" in text or "not in guest snapshots" in text


def test_plan_rule_update_discloses_lookup_failure():
    api = _RulesApi([], raise_on_list=True)
    p = plan_firewall_rule_update(api, 0, action="DROP")
    text = " ".join(p.blast_radius + p.risk_reasons).lower()
    assert "failed" in text or "could not" in text


# ---------------------------------------------------------------------------
# PLAN: plan_firewall_set_enabled
# ---------------------------------------------------------------------------


def test_plan_set_enabled_is_high_risk_when_enabling():
    api = _OptionsApi({"enable": 0})
    p = plan_firewall_set_enabled(api, True)
    assert p.risk == RISK_HIGH


def test_plan_set_enabled_is_high_risk_when_disabling():
    api = _OptionsApi({"enable": 1})
    p = plan_firewall_set_enabled(api, False)
    assert p.risk == RISK_HIGH


def test_plan_set_enabled_action_string():
    api = _OptionsApi({})
    p = plan_firewall_set_enabled(api, True)
    assert p.action == "pve_firewall_set_enabled"


def test_plan_set_enabled_reads_current_state():
    api = _OptionsApi({"enable": 0})
    p = plan_firewall_set_enabled(api, True)
    assert p.current.get("enable") == 0


def test_plan_set_enabled_enable_blast_mentions_lockout():
    api = _OptionsApi({"enable": 0})
    p = plan_firewall_set_enabled(api, True)
    text = " ".join(p.blast_radius).lower()
    assert "lockout" in text or "lock" in text or "block access" in text or "8006" in text or "ssh" in text


def test_plan_set_enabled_disable_blast_strips_protection():
    api = _OptionsApi({"enable": 1})
    p = plan_firewall_set_enabled(api, False)
    text = " ".join(p.blast_radius).lower()
    assert "strip" in text or "protection" in text or "disables" in text


def test_plan_set_enabled_cluster_scope_mentions_kill_switch():
    api = _OptionsApi({"enable": 1})
    p = plan_firewall_set_enabled(api, False, scope="cluster")
    text = " ".join(p.blast_radius).lower()
    assert "cluster" in text or "all nodes" in text or "kill" in text


def test_plan_set_enabled_enable_blast_mentions_no_undo():
    api = _OptionsApi({"enable": 0})
    p = plan_firewall_set_enabled(api, False)
    text = " ".join(p.blast_radius).lower()
    assert "no undo" in text or "not in guest snapshots" in text or "re-enable" in text


def test_plan_set_enabled_change_says_enable():
    api = _OptionsApi({})
    p = plan_firewall_set_enabled(api, True)
    assert "enable" in p.change.lower() or "ENABLE" in p.change


def test_plan_set_enabled_change_says_disable():
    api = _OptionsApi({})
    p = plan_firewall_set_enabled(api, False)
    assert "disable" in p.change.lower() or "DISABLE" in p.change


def test_plan_set_enabled_discloses_lookup_failure_stays_high():
    api = _OptionsApi({}, raise_on_get=True)
    p = plan_firewall_set_enabled(api, True)
    assert p.risk == RISK_HIGH
    text = " ".join(p.blast_radius + p.risk_reasons).lower()
    assert "could not" in text or "unknown" in text or "failed" in text


def test_plan_set_enabled_node_scope_target():
    api = _OptionsApi({})
    p = plan_firewall_set_enabled(api, True, scope="node")
    assert "node" in p.target


def test_plan_set_enabled_guest_scope_target():
    api = _OptionsApi({})
    p = plan_firewall_set_enabled(api, True, scope="guest", vmid="100")
    assert "guest" in p.target


# ---------------------------------------------------------------------------
# PLAN-before-mutate contract: plan factories return Plans, ops are separate
# ---------------------------------------------------------------------------


def test_firewall_rule_add_does_not_call_plan():
    """Op function is pure mutation — it calls _post, not any plan factory."""
    api = _api()
    firewall_rule_add(api, "ACCEPT")
    # If plan was called, _get would also appear in seen; only POST must be seen.
    assert api.seen["method"] == "POST"


def test_firewall_rule_remove_does_not_call_plan():
    """Op function is pure mutation — it calls _delete, not any plan factory."""
    api = _api()
    firewall_rule_remove(api, 0)
    assert api.seen["method"] == "DELETE"


def test_firewall_rule_update_does_not_call_plan():
    """Op function is pure mutation — it calls _put, not any plan factory."""
    api = _api()
    firewall_rule_update(api, 0, action="DROP")
    assert api.seen["method"] == "PUT"


def test_firewall_set_enabled_does_not_call_plan():
    """Op function is pure mutation — it calls _put, not any plan factory."""
    api = _api()
    firewall_set_enabled(api, True)
    assert api.seen["method"] == "PUT"


def test_plan_rule_add_does_not_call_api():
    """Plan factory is pure — no API call happens at plan time."""
    # If this raises AttributeError (no api arg), the factory incorrectly tried to call one.
    p = plan_firewall_rule_add("DROP", direction="out")
    assert p.risk == RISK_MEDIUM


# ---------------------------------------------------------------------------
# Scope / node / vmid edge cases
# ---------------------------------------------------------------------------


def test_rules_list_uses_config_node_when_none():
    api = _api(node="pve3")
    firewall_rules_list(api, scope="node")
    assert "/nodes/pve3/" in api.seen["path"]


def test_rule_add_uses_explicit_node_over_config():
    api = _api(node="pve")
    firewall_rule_add(api, "DROP", scope="node", node="node5")
    assert "/nodes/node5/" in api.seen["path"]


def test_rule_remove_uses_explicit_node_over_config():
    api = _api(node="pve")
    firewall_rule_remove(api, 1, scope="node", node="node9")
    assert "/nodes/node9/" in api.seen["path"]


def test_set_enabled_guest_scope_uses_qemu_kind():
    api = _api()
    firewall_set_enabled(api, False, scope="guest", vmid="200", kind="qemu")
    assert "/qemu/200/" in api.seen["path"]


def test_rules_list_guest_scope_rejects_invalid_vmid():
    api = _api()
    with pytest.raises(ProximoError):
        firewall_rules_list(api, scope="guest", vmid="abc")


def test_set_enabled_guest_scope_rejects_invalid_vmid():
    api = _api()
    with pytest.raises(ProximoError):
        firewall_set_enabled(api, True, scope="guest", vmid="not-a-number")


# ---------------------------------------------------------------------------
# plan_firewall_rule_update: new_fields validation (action / direction)
# ---------------------------------------------------------------------------


def test_plan_rule_update_rejects_invalid_action_in_new_fields():
    """plan_firewall_rule_update must validate action in new_fields at plan time."""
    api = _RulesApi([{"pos": 0, "action": "ACCEPT", "type": "in"}])
    with pytest.raises(ProximoError):
        plan_firewall_rule_update(api, 0, action="GARBAGE")


def test_plan_rule_update_rejects_invalid_direction_in_new_fields():
    """plan_firewall_rule_update must validate direction in new_fields at plan time."""
    api = _RulesApi([{"pos": 0, "action": "DROP", "type": "in"}])
    with pytest.raises(ProximoError):
        plan_firewall_rule_update(api, 0, direction="both")


def test_plan_rule_update_normalizes_action_case_in_new_fields():
    """plan_firewall_rule_update must uppercase the action in new_fields."""
    api = _RulesApi([{"pos": 0, "action": "DROP", "type": "in"}])
    p = plan_firewall_rule_update(api, 0, action="accept")
    # The change string should reference the normalized ACCEPT, not the raw 'accept'.
    assert "ACCEPT" in p.change or any("ACCEPT" in b for b in p.blast_radius)


# ---------------------------------------------------------------------------
# Return-value contract: mutating ops return None (synchronous, no UPID)
# ---------------------------------------------------------------------------


def test_rule_add_returns_none():
    """firewall_rule_add is synchronous and must return None (no UPID)."""
    api = _api()
    result = firewall_rule_add(api, "ACCEPT")
    assert result is None


def test_rule_remove_returns_none():
    """firewall_rule_remove is synchronous and must return None."""
    api = _api()
    result = firewall_rule_remove(api, 0)
    assert result is None


def test_rule_update_returns_none():
    """firewall_rule_update is synchronous and must return None (no UPID)."""
    api = _api()
    result = firewall_rule_update(api, 0, action="DROP")
    assert result is None


def test_set_enabled_returns_none():
    """firewall_set_enabled is synchronous and must return None (no UPID)."""
    api = _api()
    result = firewall_set_enabled(api, True)
    assert result is None


# ---------------------------------------------------------------------------
# FIX 3: digest optimistic-locking — remove and update send digest in body/params
# ---------------------------------------------------------------------------


def test_rule_remove_sends_digest_in_delete_params():
    """firewall_rule_remove must re-read rules and pass the digest as a DELETE param."""
    api = _api()
    api.seen["_get_return"] = [{"pos": 3, "digest": "abc123"}]
    firewall_rule_remove(api, 3, scope="cluster")
    # _delete is called with params containing the digest.
    assert api.seen.get("params", {}).get("digest") == "abc123"


def test_rule_remove_aborts_when_no_digest_available():
    """If rules list has no digest field, firewall_rule_remove must raise ProximoError."""
    from proximo.backends import ProximoError as PE
    api = _api()
    api.seen["_get_return"] = [{"pos": 0, "action": "ACCEPT"}]  # no 'digest' key
    with pytest.raises(PE, match="digest"):
        firewall_rule_remove(api, 0, scope="cluster")


def test_rule_update_sends_digest_in_put_body():
    """firewall_rule_update must re-read rules and include the digest in the PUT body."""
    api = _api()
    api.seen["_get_return"] = [{"pos": 1, "digest": "def456"}]
    firewall_rule_update(api, 1, action="DROP")
    assert api.seen.get("data", {}).get("digest") == "def456"


def test_rule_update_aborts_when_no_digest_available():
    """If rules list has no digest field, firewall_rule_update must raise ProximoError."""
    from proximo.backends import ProximoError as PE
    api = _api()
    api.seen["_get_return"] = [{"pos": 0, "action": "ACCEPT"}]  # no 'digest' key
    with pytest.raises(PE, match="digest"):
        firewall_rule_update(api, 0, action="DROP")
