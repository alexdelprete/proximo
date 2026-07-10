"""Network & SDN pillar tests — fully mocked, no live Proxmox.

Mirrors test_backup.py / test_provisioning.py:
- Op functions: real ApiBackend(_cfg()) with monkeypatched _get/_post/_delete/_client.
- Plan functions: tiny fake apis (only the methods each plan needs).
- Every test is self-contained — no shared mutable state.

Coverage:
 1. network_list  — URL construction, type filter, empty/None guards, node, bad-node
 2. sdn_zones_list / sdn_vnets_list — cluster-scoped paths, empty guards
 3. network_iface_create — POST URL + body, validation (iface, type, bad node, reserved-type-in-opts)
 4. network_iface_update — PUT URL + body via api._put, validation
 5. network_apply — PUT URL, returns raw (None ok), connectivity warning
 6. sdn_apply — PUT URL, returns raw
 7. ApiBackend._put — form-encoded, uses api._client.request("PUT", ...), returns data field
 8. plan_iface_create — collision detection, MEDIUM risk, staged wording
 9. plan_iface_update — existing/missing/check-failed cases, MEDIUM risk
10. plan_network_apply — HIGH risk unconditional, pending diff surfaced, read-failed case
11. plan_sdn_apply — HIGH risk unconditional, pending zones/vnets surfaced, read-failed
12. Validators — _check_iface / _check_iface_type edge cases
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from proximo.backends import ApiBackend, ProximoError
from proximo.config import ProximoConfig
from proximo.network import (
    _check_filter_type,
    _check_iface,
    _check_iface_type,
    network_apply,
    network_iface_create,
    network_iface_update,
    network_list,
    plan_iface_create,
    plan_iface_update,
    plan_network_apply,
    plan_sdn_apply,
    plan_sdn_subnet_create,
    plan_sdn_subnet_delete,
    plan_sdn_subnet_update,
    plan_sdn_vnet_create,
    plan_sdn_vnet_delete,
    plan_sdn_vnet_update,
    plan_sdn_zone_create,
    plan_sdn_zone_delete,
    plan_sdn_zone_update,
    sdn_apply,
    sdn_subnet_create,
    sdn_subnet_delete,
    sdn_subnet_list,
    sdn_subnet_update,
    sdn_vnet_create,
    sdn_vnet_delete,
    sdn_vnet_update,
    sdn_vnets_list,
    sdn_zone_create,
    sdn_zone_delete,
    sdn_zone_update,
    sdn_zones_list,
)
from proximo.planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(**kw) -> ProximoConfig:
    base = dict(
        api_base_url="https://x:8006/api2/json",
        node="pve",
        token_path="/run/x",
        ct_allowlist=frozenset({"*"}),
    )
    base.update(kw)
    return ProximoConfig(**base)


# ---------------------------------------------------------------------------
# 1. network_list
# ---------------------------------------------------------------------------


def test_network_list_builds_correct_path(monkeypatch):
    api = ApiBackend(_cfg())
    seen: dict = {}
    monkeypatch.setattr(api, "_get", lambda path: seen.update(path=path) or [{"iface": "vmbr0"}])
    result = network_list(api)
    assert seen["path"] == "/nodes/pve/network"
    assert result[0]["iface"] == "vmbr0"


def test_network_list_uses_provided_node(monkeypatch):
    api = ApiBackend(_cfg())
    seen: dict = {}
    monkeypatch.setattr(api, "_get", lambda path: seen.update(path=path) or [])
    network_list(api, node="node2")
    assert "/nodes/node2/network" in seen["path"]


def test_network_list_with_type_filter(monkeypatch):
    api = ApiBackend(_cfg())
    seen: dict = {}
    monkeypatch.setattr(api, "_get", lambda path: seen.update(path=path) or [])
    network_list(api, iface_type="bridge")
    assert seen["path"] == "/nodes/pve/network?type=bridge"


def test_network_list_returns_empty_list_on_none(monkeypatch):
    api = ApiBackend(_cfg())
    monkeypatch.setattr(api, "_get", lambda path: None)
    assert network_list(api) == []


def test_network_list_rejects_bad_node():
    api = ApiBackend(_cfg())
    with pytest.raises(ProximoError):
        network_list(api, node="bad node!")


def test_check_iface_rejects_lone_dot_traversal():
    # iface='.' would normalize PUT /nodes/{n}/network/. onto PUT /nodes/{n}/network — the network
    # config APPLY/reload endpoint — a disruptive wrong-target op the plan would mislabel as an
    # iface update. '..' was already rejected; the lone-'.' gap must close too. VLANs (eth0.100) stay OK.
    import pytest as _pytest
    for bad in (".", ".."):
        with _pytest.raises(ProximoError):
            _check_iface(bad)
    assert _check_iface("eth0.100") == "eth0.100"   # legit VLAN iface (single dot) still allowed
    assert _check_iface("vmbr0") == "vmbr0"


def test_network_list_rejects_dangerous_iface_type_ampersand(monkeypatch):
    """iface_type with & must be rejected — charset guard blocks query-string injection."""
    api = ApiBackend(_cfg())
    monkeypatch.setattr(api, "_get", lambda path: [])
    with pytest.raises(ProximoError, match="invalid iface_type filter"):
        network_list(api, iface_type="bridge&foo=bar")


def test_network_list_rejects_iface_type_with_space(monkeypatch):
    api = ApiBackend(_cfg())
    monkeypatch.setattr(api, "_get", lambda path: [])
    with pytest.raises(ProximoError, match="invalid iface_type filter"):
        network_list(api, iface_type="bridge vlan")


def test_network_list_rejects_iface_type_with_newline(monkeypatch):
    """Trailing newline must be rejected — \\Z guard catches it without strip()."""
    api = ApiBackend(_cfg())
    monkeypatch.setattr(api, "_get", lambda path: [])
    with pytest.raises(ProximoError, match="invalid iface_type filter"):
        network_list(api, iface_type="bridge\n")


def test_network_list_allows_extended_filter_types(monkeypatch):
    """PVE accepts broader filter values (any_bridge, any_local_bridge) — charset guard allows them."""
    api = ApiBackend(_cfg())
    seen: dict = {}
    monkeypatch.setattr(api, "_get", lambda path: seen.update(path=path) or [])
    network_list(api, iface_type="any_bridge")
    assert "?type=any_bridge" in seen["path"]


# ---------------------------------------------------------------------------
# _check_filter_type unit tests
# ---------------------------------------------------------------------------


def test_check_filter_type_accepts_valid_values():
    assert _check_filter_type("bridge") == "bridge"
    assert _check_filter_type("any_bridge") == "any_bridge"
    assert _check_filter_type("any_local_bridge") == "any_local_bridge"
    assert _check_filter_type("OVSBridge") == "OVSBridge"


def test_check_filter_type_rejects_injection_chars():
    for bad in ["bridge&x=y", "bridge=x", "bridge x", "bridge#frag", "bridge\n"]:
        with pytest.raises(ProximoError, match="invalid iface_type filter"):
            _check_filter_type(bad)


def test_check_filter_type_rejects_empty():
    with pytest.raises(ProximoError, match="must not be empty"):
        _check_filter_type("")


# ---------------------------------------------------------------------------
# 2. sdn_zones_list / sdn_vnets_list (cluster-scoped)
# ---------------------------------------------------------------------------


def test_sdn_zones_list_uses_cluster_path(monkeypatch):
    api = ApiBackend(_cfg())
    seen: dict = {}
    monkeypatch.setattr(api, "_get", lambda path: seen.update(path=path) or [{"zone": "z1"}])
    result = sdn_zones_list(api)
    assert seen["path"] == "/cluster/sdn/zones"
    assert result[0]["zone"] == "z1"


def test_sdn_zones_list_returns_empty_list_on_none(monkeypatch):
    api = ApiBackend(_cfg())
    monkeypatch.setattr(api, "_get", lambda path: None)
    assert sdn_zones_list(api) == []


def test_sdn_vnets_list_uses_cluster_path(monkeypatch):
    api = ApiBackend(_cfg())
    seen: dict = {}
    monkeypatch.setattr(api, "_get", lambda path: seen.update(path=path) or [{"vnet": "vn1"}])
    result = sdn_vnets_list(api)
    assert seen["path"] == "/cluster/sdn/vnets"
    assert result[0]["vnet"] == "vn1"


def test_sdn_vnets_list_returns_empty_list_on_none(monkeypatch):
    api = ApiBackend(_cfg())
    monkeypatch.setattr(api, "_get", lambda path: None)
    assert sdn_vnets_list(api) == []


# ---------------------------------------------------------------------------
# 3. network_iface_create
# ---------------------------------------------------------------------------


def test_network_iface_create_posts_to_correct_path(monkeypatch):
    api = ApiBackend(_cfg())
    seen: dict = {}
    monkeypatch.setattr(api, "_post", lambda path, data=None: seen.update(path=path, data=data) or None)
    network_iface_create(api, "vmbr0", "bridge")
    assert seen["path"] == "/nodes/pve/network"
    assert seen["data"]["iface"] == "vmbr0"
    assert seen["data"]["type"] == "bridge"


def test_network_iface_create_passes_extra_opts(monkeypatch):
    api = ApiBackend(_cfg())
    seen: dict = {}
    monkeypatch.setattr(api, "_post", lambda path, data=None: seen.update(path=path, data=data) or None)
    network_iface_create(api, "vmbr0", "bridge", address="10.0.0.1", netmask="255.255.255.0")
    assert seen["data"]["address"] == "10.0.0.1"
    assert seen["data"]["netmask"] == "255.255.255.0"


def test_network_iface_create_uses_provided_node(monkeypatch):
    api = ApiBackend(_cfg())
    seen: dict = {}
    monkeypatch.setattr(api, "_post", lambda path, data=None: seen.update(path=path) or None)
    network_iface_create(api, "vmbr0", "bridge", node="nodeX")
    assert "/nodes/nodeX/network" in seen["path"]


def test_network_iface_create_rejects_invalid_iface():
    api = ApiBackend(_cfg())
    with pytest.raises(ProximoError, match="invalid interface name"):
        network_iface_create(api, "iface with space", "bridge")


def test_network_iface_create_rejects_traversal_iface():
    api = ApiBackend(_cfg())
    with pytest.raises(ProximoError, match="traversal"):
        network_iface_create(api, "../etc/passwd", "bridge")


def test_network_iface_create_rejects_unknown_type():
    api = ApiBackend(_cfg())
    with pytest.raises(ProximoError, match="unknown interface type"):
        network_iface_create(api, "vmbr0", "wireless")


def test_network_iface_create_rejects_bad_node():
    api = ApiBackend(_cfg())
    with pytest.raises(ProximoError):
        network_iface_create(api, "vmbr0", "bridge", node="bad\nnode")


def test_network_iface_create_rejects_type_in_opts():
    """Passing 'type' in opts must raise ProximoError — it's a reserved key."""
    api = ApiBackend(_cfg())
    with pytest.raises(ProximoError, match="reserved"):
        network_iface_create(api, "vmbr0", "bridge", type="vlan")



# Note: the 'iface' sub-branch of the reserved-key guard (network_iface_create) is
# intentionally not tested behaviourally. 'iface' is a named parameter in the function
# signature, so any call that passes both 'iface' as a keyword argument AND injects it
# via **opts hits a Python double-bind TypeError BEFORE the function body runs. The guard
# still exists for defensive depth (server-layer callers that build opts from JSON dicts
# dynamically), but it is unreachable from Python call syntax. The 'type' test above covers
# that the guard mechanism exists and raises ProximoError with the expected message.


# ---------------------------------------------------------------------------
# 4. network_iface_update (uses api._put)
# ---------------------------------------------------------------------------


def test_network_iface_update_calls_put_on_correct_path(monkeypatch):
    api = ApiBackend(_cfg())
    seen: dict = {}

    def fake_put(path, data=None):
        seen.update(path=path, data=data)
        return None

    # the update reads current config (for type injection) before the PUT
    monkeypatch.setattr(api, "_get", lambda path: [{"iface": "vmbr0", "type": "bridge"}])
    monkeypatch.setattr(api, "_put", fake_put)
    network_iface_update(api, "vmbr0", address="10.0.0.1")
    assert seen["path"] == "/nodes/pve/network/vmbr0"
    assert seen["data"]["address"] == "10.0.0.1"


def test_network_iface_update_uses_provided_node(monkeypatch):
    api = ApiBackend(_cfg())
    seen: dict = {}

    def fake_put(path, data=None):
        seen.update(path=path)
        return None

    monkeypatch.setattr(api, "_get", lambda path: [{"iface": "vmbr0", "type": "bridge"}])
    monkeypatch.setattr(api, "_put", fake_put)
    network_iface_update(api, "vmbr0", node="nodeY")
    assert "/nodes/nodeY/network/vmbr0" in seen["path"]


def test_network_iface_update_rejects_invalid_iface():
    api = ApiBackend(_cfg())
    with pytest.raises(ProximoError, match="invalid interface name"):
        network_iface_update(api, "iface/slash", node=None)


def test_network_iface_update_rejects_reserved_type_key(monkeypatch):
    # changing an iface's 'type' via a field update is structural — reject it (symmetry with create).
    api = ApiBackend(_cfg())
    monkeypatch.setattr(api, "_put", lambda *a, **k: None)
    with pytest.raises(ProximoError, match="reserved key"):
        network_iface_update(api, "vmbr0", type="bond")


def test_network_iface_update_injects_current_type():
    # PVE's PUT /network/{iface} requires `type`; we inject the iface's CURRENT type so a
    # plain field update (e.g. address) goes through while a type CHANGE stays impossible.
    api = _NetworkListApi(ifaces=[{"iface": "vmbr0", "type": "bridge", "address": "10.0.0.1"}])
    network_iface_update(api, "vmbr0", address="10.0.0.9")
    path, data = api.puts[0]
    assert path == "/nodes/pve/network/vmbr0"
    assert data["address"] == "10.0.0.9"
    assert data["type"] == "bridge"  # injected from current config, never caller-supplied


def test_network_iface_update_unknown_iface_raises():
    # no current config to preserve the type from → fail loud rather than 400 at PVE.
    api = _NetworkListApi(ifaces=[])
    with pytest.raises(ProximoError, match="not found"):
        network_iface_update(api, "vmbr0", address="10.0.0.1")


def test_plan_iface_update_previews_staged_fields():
    # the confirmed PLAN must disclose WHAT changes — the staged option keys, not just "(staged)".
    api = _NetworkListApi(ifaces=[{"iface": "vmbr0", "type": "bridge"}])
    p = plan_iface_update(api, "vmbr0", opts={"bridge_ports": "eth1", "address": "10.0.0.9"})
    blast = " ".join(p.blast_radius)
    assert "bridge_ports" in blast and "address" in blast


def test_network_iface_update_rejects_traversal_iface():
    api = ApiBackend(_cfg())
    with pytest.raises(ProximoError, match="traversal"):
        network_iface_update(api, "../etc", node=None)


def test_network_iface_update_rejects_bad_node():
    api = ApiBackend(_cfg())
    with pytest.raises(ProximoError):
        network_iface_update(api, "vmbr0", node="bad node!")


# ---------------------------------------------------------------------------
# 5. network_apply
# ---------------------------------------------------------------------------


def test_network_apply_calls_put_on_correct_path(monkeypatch):
    api = ApiBackend(_cfg())
    seen: dict = {}

    def fake_put(path, data=None):
        seen.update(path=path)
        return "UPID:pve:1:0:0:0:network:pve:root@pam:"

    monkeypatch.setattr(api, "_put", fake_put)
    result = network_apply(api)
    assert seen["path"] == "/nodes/pve/network"
    # Returns raw — may be UPID or None
    assert result.startswith("UPID:")


def test_network_apply_returns_none_for_sync_apply(monkeypatch):
    api = ApiBackend(_cfg())
    monkeypatch.setattr(api, "_put", lambda path, data=None: None)
    assert network_apply(api) is None


def test_network_apply_uses_provided_node(monkeypatch):
    api = ApiBackend(_cfg())
    seen: dict = {}
    monkeypatch.setattr(api, "_put", lambda path, data=None: seen.update(path=path) or None)
    network_apply(api, node="nodeZ")
    assert "/nodes/nodeZ/network" in seen["path"]


def test_network_apply_rejects_bad_node():
    api = ApiBackend(_cfg())
    with pytest.raises(ProximoError):
        network_apply(api, node="bad node!")


# ---------------------------------------------------------------------------
# 6. sdn_apply
# ---------------------------------------------------------------------------


def test_sdn_apply_calls_put_on_cluster_path(monkeypatch):
    api = ApiBackend(_cfg())
    seen: dict = {}
    monkeypatch.setattr(api, "_put", lambda path, data=None: seen.update(path=path) or None)
    sdn_apply(api)
    assert seen["path"] == "/cluster/sdn"


def test_sdn_apply_returns_none_for_sync(monkeypatch):
    api = ApiBackend(_cfg())
    monkeypatch.setattr(api, "_put", lambda path, data=None: None)
    assert sdn_apply(api) is None


def test_sdn_apply_returns_upid_when_async(monkeypatch):
    api = ApiBackend(_cfg())
    monkeypatch.setattr(
        api, "_put",
        lambda path, data=None: "UPID:pve:1:0:0:0:sdn:pve:root@pam:",
    )
    result = sdn_apply(api)
    assert result and result.startswith("UPID:")


# ---------------------------------------------------------------------------
# 7. ApiBackend._put — exercises api._client.request("PUT", ...) with form-encoded data
# ---------------------------------------------------------------------------


def test_apibackend_put_calls_request_with_put_method():
    """ApiBackend._put must call _client.request with method='PUT'."""
    from unittest.mock import MagicMock
    api = ApiBackend(_cfg())
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": "ok"}
    mock_client = MagicMock()
    mock_client.request.return_value = mock_resp
    api._client = mock_client
    api._auth_header = lambda: {"Authorization": "PVEAPIToken=test"}
    result = api._put("/nodes/pve/network", {"key": "val"})
    call_args = mock_client.request.call_args
    assert call_args[0][0] == "PUT"
    assert call_args[0][1] == "/nodes/pve/network"
    assert call_args[1].get("data") == {"key": "val"}
    assert result == "ok"


def test_apibackend_put_form_encoded_not_json():
    """ApiBackend._put must use data= (form-encoded), not json= — mirrors _post."""
    from unittest.mock import MagicMock
    api = ApiBackend(_cfg())
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": None}
    mock_client = MagicMock()
    mock_client.request.return_value = mock_resp
    api._client = mock_client
    api._auth_header = lambda: {}
    api._put("/some/path", {"x": 1})
    _, kwargs = mock_client.request.call_args
    assert "data" in kwargs
    assert "json" not in kwargs


def test_apibackend_put_returns_data_from_response():
    from unittest.mock import MagicMock
    api = ApiBackend(_cfg())
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"applied": True}}
    mock_client = MagicMock()
    mock_client.request.return_value = mock_resp
    api._client = mock_client
    api._auth_header = lambda: {}
    result = api._put("/cluster/sdn")
    assert result == {"applied": True}


# ---------------------------------------------------------------------------
# 8. plan_iface_create
# ---------------------------------------------------------------------------


class _NetworkListApi:
    """Fake api for plan_iface_create/_update: returns a configurable iface list."""

    def __init__(self, ifaces: list[dict] | None = None, fail: bool = False):
        self.config = SimpleNamespace(node="pve")
        self._ifaces = ifaces or []
        self._fail = fail
        self.puts: list = []

    def _get(self, path):
        if self._fail:
            raise RuntimeError("network read failed")
        return self._ifaces

    def _put(self, path, data=None):
        self.puts.append((path, data))
        return None


def test_plan_iface_create_free_iface_is_medium():
    api = _NetworkListApi(ifaces=[{"iface": "vmbr1"}])
    p = plan_iface_create(api, "vmbr0", "bridge")
    assert p.risk == RISK_MEDIUM


def test_plan_iface_create_free_iface_blast_says_staged():
    api = _NetworkListApi(ifaces=[])
    p = plan_iface_create(api, "vmbr0", "bridge")
    blast = " ".join(p.blast_radius).lower()
    assert "staged" in blast or "interfaces.new" in blast


def test_plan_iface_create_free_iface_blast_says_not_live_until_apply():
    api = _NetworkListApi(ifaces=[])
    p = plan_iface_create(api, "vmbr0", "bridge")
    blast = " ".join(p.blast_radius).lower()
    assert "network_apply" in blast or "apply" in blast


def test_plan_iface_create_collision_blast_says_fail():
    api = _NetworkListApi(ifaces=[{"iface": "vmbr0"}])
    p = plan_iface_create(api, "vmbr0", "bridge")
    blast = " ".join(p.blast_radius).lower()
    assert "fail" in blast


def test_plan_iface_create_collision_still_medium():
    """Collision means the op FAILS — not a HIGH-risk operation."""
    api = _NetworkListApi(ifaces=[{"iface": "vmbr0"}])
    p = plan_iface_create(api, "vmbr0", "bridge")
    assert p.risk == RISK_MEDIUM


def test_plan_iface_create_check_failed_is_medium_not_low():
    """Check failure: uncertainty, but create is staged — MEDIUM maintained."""
    api = _NetworkListApi(fail=True)
    p = plan_iface_create(api, "vmbr0", "bridge")
    assert p.risk == RISK_MEDIUM


def test_plan_iface_create_check_failed_discloses_uncertainty():
    api = _NetworkListApi(fail=True)
    p = plan_iface_create(api, "vmbr0", "bridge")
    text = " ".join(p.blast_radius + p.risk_reasons).lower()
    assert "check" in text or "collision" in text or "could not" in text


def test_plan_iface_create_action_name():
    api = _NetworkListApi()
    p = plan_iface_create(api, "vmbr0", "bridge")
    assert p.action == "pve_network_iface_create"


def test_plan_iface_create_target_includes_iface_name():
    api = _NetworkListApi()
    p = plan_iface_create(api, "vmbr0", "bridge")
    assert "vmbr0" in p.target


def test_plan_iface_create_rejects_invalid_iface():
    api = _NetworkListApi()
    with pytest.raises(ProximoError):
        plan_iface_create(api, "bad iface!", "bridge")


def test_plan_iface_create_rejects_unknown_type():
    api = _NetworkListApi()
    with pytest.raises(ProximoError):
        plan_iface_create(api, "vmbr0", "wifi")


def test_plan_iface_create_note_warns_about_apply_risk():
    api = _NetworkListApi()
    p = plan_iface_create(api, "vmbr0", "bridge")
    assert "HIGH" in p.note or "RISK_HIGH" in p.note or "apply" in p.note.lower()


def test_plan_iface_create_previews_staged_fields():
    # the confirmed PLAN must disclose WHAT will be written to interfaces.new, not just "(staged)" —
    # otherwise an operator approves a bland preview and the real payload (address/gateway/etc.)
    # is staged sight-unseen.
    api = _NetworkListApi(ifaces=[])
    p = plan_iface_create(
        api, "vmbr0", "bridge", opts={"bridge_ports": "eth0", "address": "203.0.113.9"}
    )
    blast = " ".join(p.blast_radius)
    assert "bridge_ports" in blast and "address" in blast


def test_plan_iface_create_no_opts_omits_staged_fields_line():
    api = _NetworkListApi(ifaces=[])
    p = plan_iface_create(api, "vmbr0", "bridge")
    blast = " ".join(p.blast_radius)
    assert "staged fields" not in blast


# ---------------------------------------------------------------------------
# 9. plan_iface_update
# ---------------------------------------------------------------------------


def test_plan_iface_update_existing_is_medium():
    api = _NetworkListApi(ifaces=[{"iface": "vmbr0", "type": "bridge", "active": 1}])
    p = plan_iface_update(api, "vmbr0")
    assert p.risk == RISK_MEDIUM


def test_plan_iface_update_existing_blast_says_staged():
    api = _NetworkListApi(ifaces=[{"iface": "vmbr0", "type": "bridge"}])
    p = plan_iface_update(api, "vmbr0")
    blast = " ".join(p.blast_radius).lower()
    assert "staged" in blast or "interfaces.new" in blast


def test_plan_iface_update_existing_current_has_live_facts():
    api = _NetworkListApi(ifaces=[{"iface": "vmbr0", "type": "bridge", "active": 1}])
    p = plan_iface_update(api, "vmbr0")
    assert p.current.get("iface") == "vmbr0"
    assert p.current.get("type") == "bridge"


def test_plan_iface_update_missing_blast_says_fail():
    api = _NetworkListApi(ifaces=[{"iface": "vmbr1"}])
    p = plan_iface_update(api, "vmbr0")
    blast = " ".join(p.blast_radius).lower()
    assert "fail" in blast or "not found" in blast


def test_plan_iface_update_missing_still_medium():
    api = _NetworkListApi(ifaces=[])
    p = plan_iface_update(api, "vmbr0")
    assert p.risk == RISK_MEDIUM


def test_plan_iface_update_check_failed_discloses():
    api = _NetworkListApi(fail=True)
    p = plan_iface_update(api, "vmbr0")
    text = " ".join(p.blast_radius + p.risk_reasons).lower()
    assert "could not" in text or "failed" in text or "check" in text


def test_plan_iface_update_action_name():
    api = _NetworkListApi()
    p = plan_iface_update(api, "vmbr0")
    assert p.action == "pve_network_iface_update"


def test_plan_iface_update_rejects_invalid_iface():
    api = _NetworkListApi()
    with pytest.raises(ProximoError):
        plan_iface_update(api, "/etc/passwd")


# ---------------------------------------------------------------------------
# 10. plan_network_apply — HIGH unconditional + pending diff
# ---------------------------------------------------------------------------


class _NetworkApplyApi:
    """Fake api for plan_network_apply: returns configurable iface list."""

    def __init__(self, ifaces: list[dict] | None = None, fail: bool = False):
        self.config = SimpleNamespace(node="pve")
        self._ifaces = ifaces or []
        self._fail = fail

    def _get(self, path):
        if self._fail:
            raise RuntimeError("network read failed")
        return self._ifaces


def test_plan_network_apply_is_always_high():
    api = _NetworkApplyApi(ifaces=[])
    p = plan_network_apply(api)
    assert p.risk == RISK_HIGH


def test_plan_network_apply_is_high_even_when_read_fails():
    api = _NetworkApplyApi(fail=True)
    p = plan_network_apply(api)
    assert p.risk == RISK_HIGH


def test_plan_network_apply_blast_warns_connectivity_lockout():
    api = _NetworkApplyApi(ifaces=[])
    p = plan_network_apply(api)
    text = " ".join(p.blast_radius).lower()
    assert "connectivity" in text or "lockout" in text or "ssh" in text


def test_plan_network_apply_reasons_mention_no_undo():
    api = _NetworkApplyApi(ifaces=[])
    p = plan_network_apply(api)
    reasons = " ".join(p.risk_reasons).lower()
    assert "undo" in reasons or "rollback" in reasons or "recovery" in reasons or "no automatic" in reasons


def test_plan_network_apply_surfaces_pending_ifaces():
    api = _NetworkApplyApi(ifaces=[
        {"iface": "vmbr0", "pending": 1},
        {"iface": "vmbr1"},
    ])
    p = plan_network_apply(api)
    # Pending iface must appear in blast or current
    blast_text = " ".join(p.blast_radius)
    assert "vmbr0" in blast_text or "vmbr0" in str(p.current)


def test_plan_network_apply_read_fail_discloses_unknown():
    api = _NetworkApplyApi(fail=True)
    p = plan_network_apply(api)
    text = " ".join(p.blast_radius + p.risk_reasons).lower()
    assert "could not" in text or "unknown" in text or "read" in text


def test_plan_network_apply_action_name():
    api = _NetworkApplyApi()
    p = plan_network_apply(api)
    assert p.action == "pve_network_apply"


def test_plan_network_apply_does_not_claim_safe():
    """Must not claim the op is safe. 'safety signal' (advisory phrase) is ok; 'is safe' is not."""
    api = _NetworkApplyApi(ifaces=[])
    p = plan_network_apply(api)
    text = " ".join(p.blast_radius + p.risk_reasons).lower()
    # "safety signal" is the honest advisory phrase (mirrors other plans); "is safe" is a false claim
    assert "is safe" not in text
    assert "no risk" not in text


def test_plan_network_apply_high_even_no_pending_detected():
    """HIGH is maintained even when read shows no pending changes — read may miss entries."""
    api = _NetworkApplyApi(ifaces=[{"iface": "vmbr0"}])  # no 'pending' flag
    p = plan_network_apply(api)
    assert p.risk == RISK_HIGH


class _MgmtNetworkApplyApi:
    """Fake api for plan_network_apply lockout naming: carries an api_base_url with the mgmt IP."""

    def __init__(self, ifaces, mgmt_url="https://10.0.0.10:8006/api2/json"):
        self.config = SimpleNamespace(node="pve", api_base_url=mgmt_url)
        self._ifaces = ifaces

    def _get(self, path):
        return self._ifaces


def test_plan_network_apply_names_mgmt_iface_when_pending(monkeypatch):
    # vmbr0 (pending) holds the mgmt IP from api_base_url => names it loudly, HIGH stays.
    api = _MgmtNetworkApplyApi(ifaces=[
        {"iface": "vmbr0", "address": "10.0.0.10", "pending": 1},
        {"iface": "vmbr1", "address": "10.0.0.20"},
    ])
    p = plan_network_apply(api)
    assert p.risk == RISK_HIGH
    assert any(a.get("iface") == "vmbr0" for a in p.affected)
    blast = " ".join(p.blast_radius)
    assert "vmbr0" in blast and "10.0.0.10" in blast
    assert "lockout" in blast.lower()


def test_plan_network_apply_hostname_mgmt_high_stands(monkeypatch):
    # mgmt_host is a hostname (no iface address match) => could-not-identify, HIGH stays, never safe.
    api = _MgmtNetworkApplyApi(
        ifaces=[{"iface": "vmbr0", "address": "10.0.0.10", "pending": 1}],
        mgmt_url="https://pve.example.lan:8006/api2/json",
    )
    p = plan_network_apply(api)
    assert p.risk == RISK_HIGH
    assert any("could not identify" in line.lower() for line in p.blast_radius)
    assert not any(a.get("severity") == "low" for a in p.affected)


def test_plan_network_apply_no_base_url_attr_is_high_and_unidentified():
    # the plain _NetworkApplyApi has no api_base_url attr => must NOT crash; HIGH stands.
    api = _NetworkApplyApi(ifaces=[{"iface": "vmbr0", "pending": 1}])
    p = plan_network_apply(api)
    assert p.risk == RISK_HIGH
    assert any("could not identify" in line.lower() for line in p.blast_radius)


# ---------------------------------------------------------------------------
# 11. plan_sdn_apply — HIGH unconditional + pending zones/vnets
# ---------------------------------------------------------------------------


class _SdnApplyApi:
    """Fake api for plan_sdn_apply: returns configurable SDN state."""

    def __init__(
        self,
        zones: list[dict] | None = None,
        vnets: list[dict] | None = None,
        fail: bool = False,
    ):
        self._zones = zones or []
        self._vnets = vnets or []
        self._fail = fail

    def _get(self, path):
        if self._fail:
            raise RuntimeError("sdn read failed")
        if "zones" in path:
            return self._zones
        if "vnets" in path:
            return self._vnets
        return []


def test_plan_sdn_apply_is_always_high():
    api = _SdnApplyApi()
    p = plan_sdn_apply(api)
    assert p.risk == RISK_HIGH


def test_plan_sdn_apply_is_high_even_when_read_fails():
    api = _SdnApplyApi(fail=True)
    p = plan_sdn_apply(api)
    assert p.risk == RISK_HIGH


def test_plan_sdn_apply_blast_warns_cluster_wide():
    api = _SdnApplyApi()
    p = plan_sdn_apply(api)
    text = " ".join(p.blast_radius).lower()
    assert "cluster" in text


def test_plan_sdn_apply_blast_mentions_connectivity():
    api = _SdnApplyApi()
    p = plan_sdn_apply(api)
    text = " ".join(p.blast_radius).lower()
    assert "connectivity" in text or "networking" in text or "disrupt" in text


def test_plan_sdn_apply_notes_mgmt_rarely_on_vnet():
    # light touch (Part B): SDN apply rarely carries the mgmt path; note it, no deep modeling.
    api = _SdnApplyApi()
    p = plan_sdn_apply(api)
    text = " ".join(p.blast_radius).lower()
    assert "management" in text and "vmbr" in text
    assert p.risk == RISK_HIGH


def test_plan_sdn_apply_reasons_mention_no_undo():
    api = _SdnApplyApi()
    p = plan_sdn_apply(api)
    reasons = " ".join(p.risk_reasons).lower()
    assert "undo" in reasons or "rollback" in reasons or "recovery" in reasons or "no automatic" in reasons


def test_plan_sdn_apply_surfaces_pending_zones():
    api = _SdnApplyApi(zones=[{"zone": "z1", "state": "pending"}])
    p = plan_sdn_apply(api)
    blast_text = " ".join(p.blast_radius)
    assert "z1" in blast_text or "z1" in str(p.current)


def test_plan_sdn_apply_surfaces_pending_vnets():
    api = _SdnApplyApi(vnets=[{"vnet": "vn1", "pending": 1}])
    p = plan_sdn_apply(api)
    blast_text = " ".join(p.blast_radius)
    assert "vn1" in blast_text or "vn1" in str(p.current)


def test_plan_sdn_apply_read_fail_discloses_unknown():
    api = _SdnApplyApi(fail=True)
    p = plan_sdn_apply(api)
    text = " ".join(p.blast_radius + p.risk_reasons).lower()
    assert "could not" in text or "unknown" in text or "read" in text


def test_plan_sdn_apply_action_name():
    api = _SdnApplyApi()
    p = plan_sdn_apply(api)
    assert p.action == "pve_sdn_apply"


def test_plan_sdn_apply_target_is_cluster_sdn():
    api = _SdnApplyApi()
    p = plan_sdn_apply(api)
    assert p.target == "cluster/sdn"


def test_plan_sdn_apply_does_not_claim_safe():
    """Must not claim the op is safe. 'safety signal' (advisory phrase) is ok; 'is safe' is not."""
    api = _SdnApplyApi()
    p = plan_sdn_apply(api)
    text = " ".join(p.blast_radius + p.risk_reasons).lower()
    assert "is safe" not in text
    assert "no risk" not in text


def test_plan_sdn_apply_high_even_no_pending_detected():
    """HIGH maintained even when both zone/vnet reads show nothing pending."""
    api = _SdnApplyApi(
        zones=[{"zone": "z1"}],   # no state/pending flags
        vnets=[{"vnet": "vn1"}],  # no state/pending flags
    )
    p = plan_sdn_apply(api)
    assert p.risk == RISK_HIGH


# ---------------------------------------------------------------------------
# 12. Validators — _check_iface / _check_iface_type
# ---------------------------------------------------------------------------


def test_check_iface_accepts_valid_names():
    for name in ("vmbr0", "eth0", "bond0", "vlan10", "br-test", "en.0"):
        assert _check_iface(name) == name


def test_check_iface_rejects_slash():
    with pytest.raises(ProximoError):
        _check_iface("iface/subdir")


def test_check_iface_rejects_traversal():
    with pytest.raises(ProximoError, match="traversal"):
        _check_iface("../etc")


def test_check_iface_rejects_space():
    with pytest.raises(ProximoError):
        _check_iface("iface name")


def test_check_iface_rejects_newline():
    with pytest.raises(ProximoError):
        _check_iface("iface\n")


def test_check_iface_rejects_empty():
    with pytest.raises(ProximoError):
        _check_iface("")


def test_check_iface_rejects_too_long():
    with pytest.raises(ProximoError):
        _check_iface("a" * 16)  # > 15 chars (IFNAMSIZ-1)


def test_check_iface_type_accepts_known_types():
    for t in ("bridge", "bond", "eth", "alias", "vlan"):
        assert _check_iface_type(t) == t


def test_check_iface_type_accepts_ovs_types():
    for t in ("OVSBridge", "OVSBond", "OVSPort", "OVSIntPort"):
        assert _check_iface_type(t) == t


def test_check_iface_type_rejects_unknown():
    with pytest.raises(ProximoError, match="unknown interface type"):
        _check_iface_type("wifi")


def test_check_iface_type_rejects_empty():
    with pytest.raises(ProximoError):
        _check_iface_type("")


# ===========================================================================
# SDN — zone / vnet / subnet CRUD
# Grounded against live PVE 9.1.7 schema (2026-06-14):
#   POST   /cluster/sdn/zones                       {type, zone, ...type-conditional}
#   PUT    /cluster/sdn/zones/{zone}                 {<opts>, delete?:csv, digest?}
#   DELETE /cluster/sdn/zones/{zone}
#   POST   /cluster/sdn/vnets                        {type:vnet, vnet, zone, tag?, ...}
#   PUT/DELETE /cluster/sdn/vnets/{vnet}
#   GET/POST   /cluster/sdn/vnets/{vnet}/subnets     {type:subnet, subnet(=CIDR), gateway?, ...}
#   PUT/DELETE /cluster/sdn/vnets/{vnet}/subnets/{subnet}
# SDN objects are PENDING until pve_sdn_apply (NOT re-added here) — CRUD stages config with
# NO live-network effect. lock-token is an optional PVE-9 global-SDN-lock param.
# ===========================================================================


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


# --- zones ---

def test_sdn_zone_create_posts_type_zone_options():
    api = _rec()
    sdn_zone_create(api, "myzone", "simple", options={"ipam": "pve"})
    assert api.seen["method"] == "POST"
    assert api.seen["path"] == "/cluster/sdn/zones"
    assert api.seen["data"]["type"] == "simple"
    assert api.seen["data"]["zone"] == "myzone"
    assert api.seen["data"]["ipam"] == "pve"


def test_sdn_zone_create_rejects_bad_type():
    api = _rec()
    with pytest.raises(ProximoError):
        sdn_zone_create(api, "myzone", "bogus")


def test_sdn_zone_create_rejects_bad_id():
    api = _rec()
    with pytest.raises(ProximoError):
        sdn_zone_create(api, "bad/zone", "simple")


def test_sdn_zone_create_rejects_reserved_option_key():
    api = _rec()
    with pytest.raises(ProximoError):
        sdn_zone_create(api, "myzone", "simple", options={"zone": "x"})


def test_sdn_zone_create_includes_lock_token():
    api = _rec()
    sdn_zone_create(api, "myzone", "simple", lock_token="tok")
    assert api.seen["data"]["lock-token"] == "tok"


def test_sdn_zone_update_puts_options_and_delete_csv():
    api = _rec()
    sdn_zone_update(api, "myzone", options={"mtu": "1450"}, delete=["dns", "dnszone"])
    assert api.seen["method"] == "PUT"
    assert api.seen["path"] == "/cluster/sdn/zones/myzone"
    assert api.seen["data"]["mtu"] == "1450"
    assert api.seen["data"]["delete"] == "dns,dnszone"


def test_sdn_zone_update_requires_something():
    api = _rec()
    with pytest.raises(ProximoError):
        sdn_zone_update(api, "myzone")


def test_sdn_zone_update_includes_digest():
    api = _rec()
    sdn_zone_update(api, "myzone", options={"mtu": "1450"}, digest="abc")
    assert api.seen["data"]["digest"] == "abc"


def test_sdn_zone_delete_path():
    api = _rec()
    sdn_zone_delete(api, "myzone")
    assert api.seen["method"] == "DELETE"
    assert api.seen["path"] == "/cluster/sdn/zones/myzone"


def test_plan_sdn_zone_create_is_low_pending_no_apply():
    plan = plan_sdn_zone_create("myzone", "simple")
    assert plan.risk == RISK_LOW
    assert any("pending" in b.lower() for b in plan.blast_radius)
    assert any("apply" in b.lower() for b in plan.blast_radius)


def test_plan_sdn_zone_delete_is_medium_pending():
    api = _rec()
    plan = plan_sdn_zone_delete(api, "myzone")
    assert plan.risk == RISK_MEDIUM
    assert any("pending" in b.lower() for b in plan.blast_radius)


def _boom_api():
    def _boom(_path):
        raise RuntimeError("api unavailable")
    return SimpleNamespace(config=SimpleNamespace(node="pve"), _get=_boom)


def test_plan_sdn_zone_delete_read_failure_is_incomplete():
    # L16 (2026-07-10 audit): a swallowed current-state read must set complete=False + disclose it.
    plan = plan_sdn_zone_delete(_boom_api(), "myzone")
    assert plan.complete is False
    assert any("could not read" in b.lower() or "unknown" in b.lower() for b in plan.blast_radius)


def test_plan_sdn_vnet_delete_read_failure_is_incomplete():
    plan = plan_sdn_vnet_delete(_boom_api(), "myvnet")
    assert plan.complete is False
    assert any("could not read" in b.lower() or "unknown" in b.lower() for b in plan.blast_radius)


# --- vnets ---

def test_sdn_vnet_create_posts_type_vnet_zone():
    api = _rec()
    sdn_vnet_create(api, "myvnet", "myzone", options={"tag": 100})
    assert api.seen["path"] == "/cluster/sdn/vnets"
    assert api.seen["data"]["type"] == "vnet"
    assert api.seen["data"]["vnet"] == "myvnet"
    assert api.seen["data"]["zone"] == "myzone"
    assert api.seen["data"]["tag"] == 100


def test_sdn_vnet_create_rejects_bad_id():
    api = _rec()
    with pytest.raises(ProximoError):
        sdn_vnet_create(api, "bad/vnet", "myzone")


def test_sdn_vnet_update_puts():
    api = _rec()
    sdn_vnet_update(api, "myvnet", options={"alias": "web"})
    assert api.seen["method"] == "PUT"
    assert api.seen["path"] == "/cluster/sdn/vnets/myvnet"
    assert api.seen["data"]["alias"] == "web"


def test_sdn_vnet_delete_path():
    api = _rec()
    sdn_vnet_delete(api, "myvnet")
    assert api.seen["path"] == "/cluster/sdn/vnets/myvnet"


def test_plan_sdn_vnet_create_is_low_pending():
    plan = plan_sdn_vnet_create("myvnet", "myzone")
    assert plan.risk == RISK_LOW
    assert any("pending" in b.lower() for b in plan.blast_radius)


# --- subnets ---

def test_sdn_subnet_list_path():
    api = _rec()
    sdn_subnet_list(api, "myvnet")
    assert api.seen["method"] == "GET"
    assert api.seen["path"] == "/cluster/sdn/vnets/myvnet/subnets"


def test_sdn_subnet_create_posts_type_subnet_cidr():
    api = _rec()
    sdn_subnet_create(api, "myvnet", "10.0.0.0/24", options={"gateway": "10.0.0.1"})
    assert api.seen["path"] == "/cluster/sdn/vnets/myvnet/subnets"
    assert api.seen["data"]["type"] == "subnet"
    assert api.seen["data"]["subnet"] == "10.0.0.0/24"
    assert api.seen["data"]["gateway"] == "10.0.0.1"


def test_sdn_subnet_create_rejects_bad_cidr():
    api = _rec()
    with pytest.raises(ProximoError):
        sdn_subnet_create(api, "myvnet", "not-a-cidr")


def test_sdn_subnet_update_path():
    api = _rec()
    sdn_subnet_update(api, "myvnet", "myzone-10.0.0.0-24", options={"snat": 1})
    assert api.seen["method"] == "PUT"
    assert api.seen["path"] == "/cluster/sdn/vnets/myvnet/subnets/myzone-10.0.0.0-24"


def test_sdn_subnet_delete_path():
    api = _rec()
    sdn_subnet_delete(api, "myvnet", "myzone-10.0.0.0-24")
    assert api.seen["method"] == "DELETE"
    assert api.seen["path"] == "/cluster/sdn/vnets/myvnet/subnets/myzone-10.0.0.0-24"


def test_sdn_subnet_delete_rejects_traversal():
    api = _rec()
    with pytest.raises(ProximoError):
        sdn_subnet_delete(api, "myvnet", "../../zones/x")


def test_plan_sdn_subnet_create_is_low_pending():
    plan = plan_sdn_subnet_create("myvnet", "10.0.0.0/24")
    assert plan.risk == RISK_LOW
    assert any("pending" in b.lower() for b in plan.blast_radius)


def test_plan_sdn_subnet_delete_is_medium():
    plan = plan_sdn_subnet_delete("myvnet", "myzone-10.0.0.0-24")
    assert plan.risk == RISK_MEDIUM


# --- SDN REDTEAM fix (2026-06-14): plan/op no-op parity on update ---

def test_plan_sdn_zone_update_requires_something():
    with pytest.raises(ProximoError):
        plan_sdn_zone_update("myzone")


def test_plan_sdn_vnet_update_requires_something():
    with pytest.raises(ProximoError):
        plan_sdn_vnet_update("myvnet")


def test_plan_sdn_subnet_update_requires_something():
    with pytest.raises(ProximoError):
        plan_sdn_subnet_update("myvnet", "myzone-10.0.0.0-24")


# --- SDN plan previews disclose options key=value, not just key names (harden) ---
# A confirm=False preview must show the actual field VALUES about to be staged — otherwise
# an operator approves a bland "(pending)" preview while an arbitrary VLAN tag/alias/gateway
# is queued sight-unseen (mirrors plan_firewall_options_set's set_summary disclosure).

def test_plan_sdn_zone_create_discloses_option_values():
    plan = plan_sdn_zone_create("myzone", "simple", options={"mtu": "1450"})
    blast = " ".join(plan.blast_radius) + plan.change
    assert "mtu" in blast and "1450" in blast


def test_plan_sdn_zone_update_discloses_option_values():
    plan = plan_sdn_zone_update("myzone", options={"mtu": "1450"})
    blast = " ".join(plan.blast_radius) + plan.change
    assert "mtu" in blast and "1450" in blast


def test_plan_sdn_vnet_create_discloses_option_values():
    plan = plan_sdn_vnet_create("myvnet", "myzone", options={"tag": "999", "alias": "web"})
    blast = " ".join(plan.blast_radius) + plan.change
    assert "tag" in blast and "999" in blast and "alias" in blast and "web" in blast


def test_plan_sdn_vnet_update_discloses_option_values():
    plan = plan_sdn_vnet_update("myvnet", options={"tag": "999", "alias": "exfil-net"})
    blast = " ".join(plan.blast_radius) + plan.change
    assert "tag" in blast and "999" in blast and "alias" in blast and "exfil-net" in blast


def test_plan_sdn_subnet_create_discloses_option_values():
    plan = plan_sdn_subnet_create("myvnet", "10.0.0.0/24", options={"gateway": "10.0.0.1"})
    blast = " ".join(plan.blast_radius) + plan.change
    assert "gateway" in blast and "10.0.0.1" in blast


def test_plan_sdn_subnet_update_discloses_option_values():
    plan = plan_sdn_subnet_update("myvnet", "myzone-10.0.0.0-24", options={"gateway": "10.0.0.9"})
    blast = " ".join(plan.blast_radius) + plan.change
    assert "gateway" in blast and "10.0.0.9" in blast


# ---------------------------------------------------------------------------
# plan_iface_update — attachment blast wiring (rank 4): names guests on the bridge
# ---------------------------------------------------------------------------


class _IfaceGuestApi:
    """Path-aware fake: network list + cluster guests + guest configs for the attachment blast."""

    def __init__(self, *, ifaces, rows, configs):
        self.config = SimpleNamespace(node="pve")
        self._ifaces = ifaces
        self._rows = rows
        self._configs = configs

    def _get(self, path):
        if path.endswith("/network"):
            return self._ifaces
        if path == "/cluster/resources":
            return self._rows
        if path.endswith("/config"):
            return self._configs.get(path.strip("/").split("/")[3], {})
        return {}


def test_plan_iface_update_names_attached_guests():
    api = _IfaceGuestApi(
        ifaces=[{"iface": "vmbr1", "type": "bridge", "method": "static", "address": "10.0.0.1"}],
        rows=[{"vmid": "101", "type": "qemu", "node": "pve", "name": "web"},
              {"vmid": "102", "type": "qemu", "node": "pve", "name": "other"}],
        configs={"101": {"net0": "virtio=AA:BB,bridge=vmbr1"},
                 "102": {"net0": "virtio=CC:DD,bridge=vmbr0"}},
    )
    p = plan_iface_update(api, "vmbr1")
    assert any(a["vmid"] == "101" for a in p.affected)
    assert all(a["vmid"] != "102" for a in p.affected)   # 102 is on vmbr0
    assert p.risk == RISK_MEDIUM
    assert p.complete is True


def test_plan_iface_update_no_attached_guests_clean():
    api = _IfaceGuestApi(
        ifaces=[{"iface": "vmbr9", "type": "bridge"}],
        rows=[{"vmid": "101", "type": "qemu", "node": "pve", "name": "web"}],
        configs={"101": {"net0": "virtio=AA:BB,bridge=vmbr0"}},
    )
    p = plan_iface_update(api, "vmbr9")
    assert p.affected == []
