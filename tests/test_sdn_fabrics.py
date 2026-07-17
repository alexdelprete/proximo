"""SDN FABRICS tests (Wave 7d, full-surface campaign — the FINAL chunk of Wave 7) — fully
mocked, no live Proxmox.

Mirrors test_sdn_objects.py / test_sdn_routing.py's own conventions:
- Op functions: a tiny fake api recording method/path/data (`_rec()`).
- Plan functions: fake apis giving just enough for each plan's own safe-read (CAPTURE) to
  resolve.
- Every test is self-contained — no shared mutable state.

Coverage:
 1. Validators — _check_protocol, _check_fabric_node_id, _check_fabric_options,
    _check_fabric_node_options (reserved-key guards)
 2. Fabrics (container) — fabrics_all/fabrics_list (pending/running query) URL construction,
    fabric_get (NO pending/running — schema-verified absence) URL construction, create
    (digest accepted — one of three exceptions on this plane)/update (protocol REQUIRED,
    restated verbatim)/delete (NO digest, NO lock-token at all — schema-verified) payload
    construction, reserved-key smuggling guard
 3. Fabric nodes — fabric_nodes_list_all/fabric_nodes_list (pending/running query) URL
    construction, fabric_node_get (NO pending/running) URL construction, create (fabric_id
    path-only, NOT duplicated in body; node_id+protocol required; digest accepted — a THIRD
    exception the draft's own Fact #9 never examined)/update (protocol REQUIRED)/delete (NO
    digest, NO lock-token) payload construction
 4. Node-scoped fabric status — interfaces/neighbors/routes URL construction + node
    defaulting to api.config.node
 5. Plan factories — risk ladder (LOW create/update, MEDIUM delete), CAPTURE via list reads,
    "at least one option" guards on update, the redistribute Smoke-confirm note (fired only
    when protocol is NOT ospf/bgp AND redistribute is not supplied), PENDING/apply-gated
    blast language, referential-integrity Smoke-confirm language, the "no digest/no
    lock-token" blast note on delete plans
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from proximo.backends import ProximoError
from proximo.planning import RISK_LOW, RISK_MEDIUM
from proximo.sdn_fabrics import (
    _check_fabric_node_id,
    _check_fabric_node_options,
    _check_fabric_options,
    _check_protocol,
    fabric_create,
    fabric_delete,
    fabric_get,
    fabric_node_create,
    fabric_node_delete,
    fabric_node_get,
    fabric_node_update,
    fabric_nodes_list,
    fabric_nodes_list_all,
    fabric_status_interfaces,
    fabric_status_neighbors,
    fabric_status_routes,
    fabric_update,
    fabrics_all,
    fabrics_list,
    plan_fabric_create,
    plan_fabric_delete,
    plan_fabric_node_create,
    plan_fabric_node_delete,
    plan_fabric_node_update,
    plan_fabric_update,
)

# ---------------------------------------------------------------------------
# Fake api
# ---------------------------------------------------------------------------


def _rec():
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

    return SimpleNamespace(config=SimpleNamespace(node="pve"), _get=g, _post=p, _put=u, _delete=d, seen=seen)


def _boom_api():
    def _boom(_path):
        raise RuntimeError("api unavailable")
    return SimpleNamespace(config=SimpleNamespace(node="pve"), _get=_boom)


# ---------------------------------------------------------------------------
# 1. Validators
# ---------------------------------------------------------------------------


def test_check_protocol_accepts_all_four():
    for p in ("openfabric", "ospf", "wireguard", "bgp"):
        assert _check_protocol(p) == p


def test_check_protocol_rejects_unknown():
    with pytest.raises(ProximoError):
        _check_protocol("rip")


def test_check_fabric_node_id_accepts_hostname_shape():
    assert _check_fabric_node_id("pve-node-1") == "pve-node-1"


def test_check_fabric_node_id_rejects_none():
    with pytest.raises(ProximoError):
        _check_fabric_node_id(None)


def test_check_fabric_node_id_rejects_empty():
    with pytest.raises(ProximoError):
        _check_fabric_node_id("")


def test_check_fabric_node_id_rejects_malformed():
    with pytest.raises(ProximoError):
        _check_fabric_node_id("-bad-start")


def test_check_fabric_options_blocks_reserved_keys():
    with pytest.raises(ProximoError):
        _check_fabric_options({"id": "sneaky"})
    with pytest.raises(ProximoError):
        _check_fabric_options({"protocol": "bgp"})
    with pytest.raises(ProximoError):
        _check_fabric_options({"digest": "x"})
    with pytest.raises(ProximoError):
        _check_fabric_options({"lock_token": "x"})


def test_check_fabric_options_allows_legit_fields():
    _check_fabric_options({"area": "1", "redistribute": []})  # must not raise


def test_check_fabric_node_options_blocks_reserved_keys():
    with pytest.raises(ProximoError):
        _check_fabric_node_options({"fabric_id": "f1"})
    with pytest.raises(ProximoError):
        _check_fabric_node_options({"node_id": "n1"})
    with pytest.raises(ProximoError):
        _check_fabric_node_options({"protocol": "bgp"})


def test_check_fabric_node_options_allows_legit_fields():
    _check_fabric_node_options({"ip": "10.99.99.1/24"})  # must not raise


# ---------------------------------------------------------------------------
# 2. Fabrics (container)
# ---------------------------------------------------------------------------


def test_fabrics_all_url_construction_no_filters():
    api = _rec()
    fabrics_all(api)
    assert api.seen["path"] == "/cluster/sdn/fabrics/all"


def test_fabrics_all_url_construction_with_pending_running():
    api = _rec()
    fabrics_all(api, pending=True, running=False)
    assert "pending=1" in api.seen["path"]
    assert "running=0" in api.seen["path"]


def test_fabrics_all_defaults_to_empty_dict():
    api = _rec()
    api.seen["_get_return"] = None
    out = fabrics_all(api)
    assert out == {}


def test_fabrics_list_url_construction():
    api = _rec()
    fabrics_list(api, pending=True)
    assert api.seen["path"] == "/cluster/sdn/fabrics/fabric?pending=1"


def test_fabric_get_url_construction_no_query_params():
    """fabric_get has NO pending/running on this schema — fact #4."""
    api = _rec()
    fabric_get(api, "myfab")
    assert api.seen["path"] == "/cluster/sdn/fabrics/fabric/myfab"


# ---------------------------------------------------------------------------
# 6. lock-token strip at the read layer (MAJOR #2 fix, post-review 2026-07-17)
#
# `lock-token` (the live SDN cluster-lock capability secret — 7a's "capability handle, not a
# password" contract) is schema-documented in the RESPONSE of all six fabric/fabric-node
# config-read wire functions. It must never echo back through a plain read: strip it entirely
# at the read layer (mirrors sdn_objects.py's `_strip_secrets_at_read` idiom), per-row where
# the read returns a list.
# ---------------------------------------------------------------------------

_LOCK_TOKEN_SENTINEL = "sentinel-lock-token-echo"  # noqa: S105 (test sentinel, not a real credential)


def test_fabric_get_strips_lock_token_from_read():
    api = _rec()
    api.seen["_get_return"] = {"id": "myfab", "protocol": "bgp", "lock-token": _LOCK_TOKEN_SENTINEL}
    out = fabric_get(api, "myfab")
    assert "lock-token" not in out
    assert out == {"id": "myfab", "protocol": "bgp"}


def test_fabrics_list_strips_lock_token_per_row():
    api = _rec()
    api.seen["_get_return"] = [
        {"id": "fab1", "protocol": "bgp", "lock-token": _LOCK_TOKEN_SENTINEL},
        {"id": "fab2", "protocol": "ospf", "lock-token": _LOCK_TOKEN_SENTINEL},
    ]
    out = fabrics_list(api)
    assert all("lock-token" not in row for row in out)
    assert out == [{"id": "fab1", "protocol": "bgp"}, {"id": "fab2", "protocol": "ospf"}]


def test_fabrics_all_strips_lock_token_from_both_nested_lists():
    api = _rec()
    api.seen["_get_return"] = {
        "fabrics": [{"id": "fab1", "lock-token": _LOCK_TOKEN_SENTINEL}],
        "nodes": [{"node_id": "n1", "lock-token": _LOCK_TOKEN_SENTINEL}],
    }
    out = fabrics_all(api)
    assert "lock-token" not in out["fabrics"][0]
    assert "lock-token" not in out["nodes"][0]


def test_fabric_nodes_list_all_strips_lock_token_per_row():
    api = _rec()
    api.seen["_get_return"] = [{"node_id": "n1", "lock-token": _LOCK_TOKEN_SENTINEL}]
    out = fabric_nodes_list_all(api)
    assert "lock-token" not in out[0]


def test_fabric_nodes_list_strips_lock_token_per_row():
    api = _rec()
    api.seen["_get_return"] = [{"node_id": "n1", "lock-token": _LOCK_TOKEN_SENTINEL}]
    out = fabric_nodes_list(api, "myfab")
    assert "lock-token" not in out[0]


def test_fabric_node_get_strips_lock_token_from_read():
    api = _rec()
    api.seen["_get_return"] = {"node_id": "n1", "lock-token": _LOCK_TOKEN_SENTINEL}
    out = fabric_node_get(api, "myfab", "n1")
    assert "lock-token" not in out


def test_plan_fabric_delete_capture_never_leaks_lock_token():
    """CAPTURE-bearing plan factory: plan_fabric_delete reads through the already-stripped
    fabrics_list(), so Plan.current must never carry the lock-token sentinel either — one
    layer (the read-layer strip) covers CAPTURE for free."""
    api = _rec()
    api.seen["_get_return"] = [{"id": "myfab", "protocol": "bgp", "lock-token": _LOCK_TOKEN_SENTINEL}]
    plan = plan_fabric_delete(api, "myfab")
    assert "lock-token" not in plan.current
    assert _LOCK_TOKEN_SENTINEL not in " ".join(plan.blast_radius)


def test_plan_fabric_node_delete_capture_never_leaks_lock_token():
    api = _rec()
    api.seen["_get_return"] = [{"node_id": "node2", "fabric_id": "myfab", "lock-token": _LOCK_TOKEN_SENTINEL}]
    plan = plan_fabric_node_delete(api, "myfab", "node2")
    assert "lock-token" not in plan.current
    assert _LOCK_TOKEN_SENTINEL not in " ".join(plan.blast_radius)


def test_fabric_create_payload_and_digest_accepted():
    api = _rec()
    fabric_create(api, "myfab", "bgp", options={"asn": 65000}, digest="deadbeef")
    assert api.seen["method"] == "POST"
    assert api.seen["path"] == "/cluster/sdn/fabrics/fabric"
    assert api.seen["data"] == {
        "id": "myfab", "protocol": "bgp", "asn": 65000, "digest": "deadbeef",
    }


def test_fabric_create_lock_token_forwarded():
    api = _rec()
    fabric_create(api, "myfab", "openfabric", lock_token="tok123")
    assert api.seen["data"]["lock-token"] == "tok123"


def test_fabric_create_rejects_reserved_key_in_options():
    api = _rec()
    with pytest.raises(ProximoError):
        fabric_create(api, "myfab", "bgp", options={"id": "smuggled"})


def test_fabric_update_requires_protocol_and_restates_it():
    api = _rec()
    fabric_update(api, "myfab", "bgp", options={"asn": 65001})
    assert api.seen["method"] == "PUT"
    assert api.seen["path"] == "/cluster/sdn/fabrics/fabric/myfab"
    assert api.seen["data"] == {"protocol": "bgp", "asn": 65001}


def test_fabric_update_requires_at_least_one_field():
    api = _rec()
    with pytest.raises(ProximoError):
        fabric_update(api, "myfab", "bgp")


def test_fabric_update_delete_and_digest():
    api = _rec()
    fabric_update(api, "myfab", "ospf", delete=["area"], digest="abc123")
    assert api.seen["data"]["delete"] == "area"
    assert api.seen["data"]["digest"] == "abc123"


def test_fabric_delete_no_digest_no_lock_token_param():
    """fabric_delete accepts no lock_token/digest at all — schema-verified (fact #6)."""
    api = _rec()
    fabric_delete(api, "myfab")
    assert api.seen["method"] == "DELETE"
    assert api.seen["path"] == "/cluster/sdn/fabrics/fabric/myfab"
    assert api.seen.get("params") is None


# ---------------------------------------------------------------------------
# 3. Fabric nodes
# ---------------------------------------------------------------------------


def test_fabric_nodes_list_all_url_construction():
    api = _rec()
    fabric_nodes_list_all(api, running=True)
    assert api.seen["path"] == "/cluster/sdn/fabrics/node?running=1"


def test_fabric_nodes_list_scoped_url_construction():
    api = _rec()
    fabric_nodes_list(api, "myfab", pending=True)
    assert api.seen["path"] == "/cluster/sdn/fabrics/node/myfab?pending=1"


def test_fabric_node_get_url_construction_no_query_params():
    api = _rec()
    fabric_node_get(api, "myfab", "node2")
    assert api.seen["path"] == "/cluster/sdn/fabrics/node/myfab/node2"


def test_fabric_node_create_fabric_id_path_only_not_in_body():
    api = _rec()
    fabric_node_create(api, "myfab", "node2", "bgp", options={"ip": "10.99.99.5/24"})
    assert api.seen["method"] == "POST"
    assert api.seen["path"] == "/cluster/sdn/fabrics/node/myfab"
    assert api.seen["data"] == {"node_id": "node2", "protocol": "bgp", "ip": "10.99.99.5/24"}
    assert "fabric_id" not in api.seen["data"]


def test_fabric_node_create_digest_accepted():
    """A third digest-on-create exception the draft's own Fact #9 never examined."""
    api = _rec()
    fabric_node_create(api, "myfab", "node2", "openfabric", digest="cafef00d")
    assert api.seen["data"]["digest"] == "cafef00d"


def test_fabric_node_create_rejects_reserved_key_in_options():
    api = _rec()
    with pytest.raises(ProximoError):
        fabric_node_create(api, "myfab", "node2", "bgp", options={"node_id": "smuggled"})


def test_fabric_node_update_requires_protocol_path_ids_not_in_body():
    api = _rec()
    fabric_node_update(api, "myfab", "node2", "wireguard", options={"endpoint": "1.2.3.4:51820"})
    assert api.seen["method"] == "PUT"
    assert api.seen["path"] == "/cluster/sdn/fabrics/node/myfab/node2"
    assert api.seen["data"] == {"protocol": "wireguard", "endpoint": "1.2.3.4:51820"}
    assert "fabric_id" not in api.seen["data"]
    assert "node_id" not in api.seen["data"]


def test_fabric_node_update_requires_at_least_one_field():
    api = _rec()
    with pytest.raises(ProximoError):
        fabric_node_update(api, "myfab", "node2", "bgp")


def test_fabric_node_delete_no_digest_no_lock_token_param():
    api = _rec()
    fabric_node_delete(api, "myfab", "node2")
    assert api.seen["method"] == "DELETE"
    assert api.seen["path"] == "/cluster/sdn/fabrics/node/myfab/node2"
    assert api.seen.get("params") is None


# ---------------------------------------------------------------------------
# 4. Node-scoped fabric status
# ---------------------------------------------------------------------------


def test_fabric_status_interfaces_url_and_node_default():
    api = _rec()
    fabric_status_interfaces(api, "myfab")
    assert api.seen["path"] == "/nodes/pve/sdn/fabrics/myfab/interfaces"


def test_fabric_status_interfaces_explicit_node():
    api = _rec()
    fabric_status_interfaces(api, "myfab", node="othernode")
    assert api.seen["path"] == "/nodes/othernode/sdn/fabrics/myfab/interfaces"


def test_fabric_status_neighbors_url():
    api = _rec()
    fabric_status_neighbors(api, "myfab")
    assert api.seen["path"] == "/nodes/pve/sdn/fabrics/myfab/neighbors"


def test_fabric_status_routes_url():
    api = _rec()
    fabric_status_routes(api, "myfab")
    assert api.seen["path"] == "/nodes/pve/sdn/fabrics/myfab/routes"


# ---------------------------------------------------------------------------
# 5. Plan factories
# ---------------------------------------------------------------------------


def test_plan_fabric_create_risk_low():
    plan = plan_fabric_create("myfab", "bgp", options={"asn": 65000, "redistribute": []})
    assert plan.risk == RISK_LOW
    blast = " ".join(plan.blast_radius).lower()
    assert "inert until pve_sdn_apply" in blast


def test_plan_fabric_create_smoke_confirm_note_fires_for_non_ospf_bgp_omitting_redistribute():
    plan = plan_fabric_create("myfab", "openfabric")
    blast = " ".join(plan.blast_radius)
    assert "Smoke-confirm" in blast
    assert "redistribute" in blast


def test_plan_fabric_create_smoke_confirm_note_absent_for_bgp_with_redistribute_supplied():
    plan = plan_fabric_create("myfab", "bgp", options={"redistribute": []})
    blast = " ".join(plan.blast_radius)
    assert "Smoke-confirm" not in blast


def test_plan_fabric_create_smoke_confirm_note_absent_for_ospf_even_without_redistribute():
    """ospf/bgp are the two protocols redistribute IS meaningful for — no note needed."""
    plan = plan_fabric_create("myfab", "ospf")
    blast = " ".join(plan.blast_radius)
    assert "Smoke-confirm" not in blast


def test_plan_fabric_update_requires_protocol_and_at_least_one_field():
    with pytest.raises(ProximoError):
        plan_fabric_update("myfab", "bgp")
    plan = plan_fabric_update("myfab", "bgp", options={"asn": 65001})
    assert plan.risk == RISK_LOW
    assert "protocol restated as bgp" in " ".join(plan.blast_radius)


def test_plan_fabric_update_smoke_confirm_note_fires_for_non_ospf_bgp_omitting_redistribute():
    """MINOR #2 fix: the schema requires 'redistribute' identically on UPDATE and CREATE
    (Coordinator ruling #6) — the Smoke-confirm note must fire on both, not CREATE only."""
    plan = plan_fabric_update("myfab", "openfabric", options={"hello_interval": 5})
    blast = " ".join(plan.blast_radius)
    assert "Smoke-confirm" in blast
    assert "redistribute" in blast


def test_plan_fabric_update_smoke_confirm_note_absent_for_bgp_with_redistribute_supplied():
    plan = plan_fabric_update("myfab", "bgp", options={"redistribute": []})
    blast = " ".join(plan.blast_radius)
    assert "Smoke-confirm" not in blast


def test_plan_fabric_update_smoke_confirm_note_absent_for_ospf_even_without_redistribute():
    """ospf/bgp are the two protocols redistribute IS meaningful for — no note needed."""
    plan = plan_fabric_update("myfab", "ospf", options={"area": "1"})
    blast = " ".join(plan.blast_radius)
    assert "redistribute" not in blast


def test_plan_fabric_create_and_update_both_carry_the_redistribute_smoke_confirm_note():
    """The note must appear in BOTH plans for the identical omission scenario — the whole
    point of this fix."""
    create_blast = " ".join(plan_fabric_create("myfab", "openfabric").blast_radius)
    update_blast = " ".join(
        plan_fabric_update("myfab", "openfabric", options={"hello_interval": 5}).blast_radius
    )
    assert "Smoke-confirm" in create_blast and "redistribute" in create_blast
    assert "Smoke-confirm" in update_blast and "redistribute" in update_blast


def test_plan_fabric_delete_risk_medium_and_no_lock_token_note():
    api = _rec()
    api.seen["_get_return"] = [{"id": "myfab", "protocol": "bgp"}]
    plan = plan_fabric_delete(api, "myfab")
    assert plan.risk == RISK_MEDIUM
    assert plan.current == {"id": "myfab", "protocol": "bgp"}
    blast = " ".join(plan.blast_radius)
    assert "NO digest and NO lock-token" in blast
    assert "Smoke-confirm" in blast


def test_plan_fabric_delete_read_failure_discloses_uncertainty():
    plan = plan_fabric_delete(_boom_api(), "myfab")
    assert plan.complete is False
    assert any("UNKNOWN" in line for line in plan.blast_radius)


def test_plan_fabric_node_create_risk_low():
    plan = plan_fabric_node_create("myfab", "node2", "ospf", options={"ip": "10.99.99.2/24"})
    assert plan.risk == RISK_LOW
    assert "inert until pve_sdn_apply" in " ".join(plan.blast_radius).lower()


def test_plan_fabric_node_update_requires_at_least_one_field():
    with pytest.raises(ProximoError):
        plan_fabric_node_update("myfab", "node2", "bgp")
    plan = plan_fabric_node_update("myfab", "node2", "bgp", delete=["ip"])
    assert plan.risk == RISK_LOW


def test_plan_fabric_node_delete_risk_medium_captures_scoped_list():
    api = _rec()
    api.seen["_get_return"] = [{"node_id": "node2", "fabric_id": "myfab"}]
    plan = plan_fabric_node_delete(api, "myfab", "node2")
    assert plan.risk == RISK_MEDIUM
    assert plan.current == {"node_id": "node2", "fabric_id": "myfab"}
    assert api.seen["path"] == "/cluster/sdn/fabrics/node/myfab"
    assert "NO digest and NO lock-token" in " ".join(plan.blast_radius)


def test_plan_fabric_node_delete_read_failure_discloses_uncertainty():
    plan = plan_fabric_node_delete(_boom_api(), "myfab", "node2")
    assert plan.complete is False
    assert any("UNKNOWN" in line for line in plan.blast_radius)
