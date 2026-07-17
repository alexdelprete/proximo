"""Server-level integration for SDN FABRICS (Wave 7d, full-surface campaign — the FINAL
chunk of Wave 7).

The canonical confirm-sweep exact-payload file for this chunk. Proves the trust gate holds
across the new wiring:
- every read is an audited call at the exact path, recorded to the ledger;
- every mutation is dry-run by default (confirm=False => status="plan", op NOT called);
- a confirm=True call routes to the real op and records to the ledger;
- risk ladder through the SERVER wrapper (not just the bare plan factory): container/node
  create+update are LOW, container/node delete is MEDIUM;
- PENDING/apply-gated framing (no "LIVE/IMMEDIATE" language) present on every mutation plan;
- `lock_token`/`digest` are accepted by create/update (fabric AND fabric-node) and forwarded
  raw to the wire, but NEVER written to the ledger's `detail=` — mirrors the 7a/7c/7e
  precedent; `fabric_delete`/`fabric_node_delete` accept NEITHER at all (schema-verified —
  no lock_token/digest parameter exists on either tool);
- the taint split holds at the server layer: `pve_sdn_fabric_status_neighbors`/
  `pve_sdn_fabric_status_routes` set the sticky taint marker when tracking is on;
  `pve_sdn_fabric_status_interfaces` does NOT (REVIEWED_TRUSTED).

Backend is faked; the ledger is real (tmp_path) so PLAN->PROVE is exercised end to end.
Mirrors the `_wire()`/`_FakeApi` idiom in tests/test_server_sdn_routing_wiring.py.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo import taint
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig


class _FakeApi:
    def __init__(self):
        self.config = SimpleNamespace(node="pve")
        self.gets: list = []
        self.posts: list = []
        self.puts: list = []
        self.dels: list = []
        self._get_return: object = []

    def _get(self, path):
        self.gets.append(path)
        return self._get_return

    def _post(self, path, data=None):
        self.posts.append((path, data))
        return None

    def _put(self, path, data=None):
        self.puts.append((path, data))
        return None

    def _delete(self, path, params=None):
        self.dels.append((path, params))
        return None


def _wire(tmp_path, monkeypatch):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(api_base_url="https://x:8006/api2/json", node="pve",
                        token_path="/run/x", audit_log_path=log)
    api = _FakeApi()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, SimpleNamespace(), ledger))
    return cfg, api, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _confirmed_entry(log: str, action: str) -> dict:
    entries = [e for e in _entries(log) if e["action"] == action and e["outcome"] == "ok"]
    assert len(entries) == 1, f"expected exactly one confirmed {action!r} entry, got {entries}"
    return entries[0]


_TAINT_ENV = (taint.TAINT_TRACK_ENV, taint.FORBID_ENV, taint.REQUIRE_CONSENT_ENV, taint.FENCE_ENV)


@pytest.fixture(autouse=True)
def _clean_taint_env(monkeypatch):
    for var in _TAINT_ENV:
        monkeypatch.delenv(var, raising=False)
    yield


# --- fabrics (container) — reads -------------------------------------------------------------


def test_fabrics_all_is_audited_read(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = {"fabrics": [{"id": "fab1"}], "nodes": [{"node_id": "n1"}]}
    out = server.pve_sdn_fabrics_all()
    assert api.gets == ["/cluster/sdn/fabrics/all"]
    assert out == {"fabrics": [{"id": "fab1"}], "nodes": [{"node_id": "n1"}]}
    assert any(e.get("action") == "pve_sdn_fabrics_all" for e in _entries(log))


def test_fabrics_list_is_audited_read(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"id": "fab1", "protocol": "bgp"}]
    out = server.pve_sdn_fabrics_list()
    assert api.gets == ["/cluster/sdn/fabrics/fabric"]
    assert out == [{"id": "fab1", "protocol": "bgp"}]
    assert any(e.get("action") == "pve_sdn_fabrics_list" for e in _entries(log))


def test_fabric_get_is_audited_read_no_query_params(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = {"id": "fab1", "protocol": "bgp"}
    out = server.pve_sdn_fabric_get("fab1")
    assert api.gets == ["/cluster/sdn/fabrics/fabric/fab1"]
    assert out == {"id": "fab1", "protocol": "bgp"}
    assert any(e.get("action") == "pve_sdn_fabric_get" for e in _entries(log))


# --- fabrics (container) — mutations ----------------------------------------------------------


def test_fabric_create_dry_run_low_then_confirm(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_fabric_create("fab1", "bgp", options={"asn": 65000})
    assert dry["status"] == "plan" and dry["risk"] == "low"
    assert api.posts == []
    server.pve_sdn_fabric_create("fab1", "bgp", options={"asn": 65000}, confirm=True)
    assert api.posts == [
        ("/cluster/sdn/fabrics/fabric", {"id": "fab1", "protocol": "bgp", "asn": 65000}),
    ]
    entry = _confirmed_entry(log, "pve_sdn_fabric_create")
    assert entry["mutation"] is True


def test_fabric_update_dry_run_low_then_confirm_restates_protocol(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_fabric_update("fab1", "bgp", options={"asn": 65001})
    assert dry["status"] == "plan" and dry["risk"] == "low"
    assert api.puts == []
    server.pve_sdn_fabric_update("fab1", "bgp", options={"asn": 65001}, confirm=True)
    assert api.puts == [
        ("/cluster/sdn/fabrics/fabric/fab1", {"protocol": "bgp", "asn": 65001}),
    ]


def test_fabric_delete_dry_run_medium_then_confirm_no_params(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"id": "fab1", "protocol": "bgp"}]
    dry = server.pve_sdn_fabric_delete("fab1")
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert api.dels == []
    server.pve_sdn_fabric_delete("fab1", confirm=True)
    assert api.dels == [("/cluster/sdn/fabrics/fabric/fab1", None)]
    assert any(e.get("action") == "pve_sdn_fabric_delete" for e in _entries(log))


def test_fabric_mutations_never_softened_by_live_language(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_fabric_create("fab1", "openfabric")
    blast = " ".join(dry["blast_radius"]).lower()
    assert "inert until pve_sdn_apply" in blast
    assert "live/immediate" not in blast


# --- fabric nodes — reads ----------------------------------------------------------------------


def test_fabric_nodes_list_all_is_audited_read(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"node_id": "n1", "fabric_id": "fab1"}]
    out = server.pve_sdn_fabric_nodes_list_all()
    assert api.gets == ["/cluster/sdn/fabrics/node"]
    assert out == [{"node_id": "n1", "fabric_id": "fab1"}]
    assert any(e.get("action") == "pve_sdn_fabric_nodes_list_all" for e in _entries(log))


def test_fabric_nodes_list_scoped_is_audited_read(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"node_id": "n1", "fabric_id": "fab1"}]
    out = server.pve_sdn_fabric_nodes_list("fab1")
    assert api.gets == ["/cluster/sdn/fabrics/node/fab1"]
    assert out == [{"node_id": "n1", "fabric_id": "fab1"}]
    assert any(e.get("action") == "pve_sdn_fabric_nodes_list" for e in _entries(log))


def test_fabric_node_get_is_audited_read_no_query_params(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = {"node_id": "n1", "fabric_id": "fab1"}
    out = server.pve_sdn_fabric_node_get("fab1", "n1")
    assert api.gets == ["/cluster/sdn/fabrics/node/fab1/n1"]
    assert out == {"node_id": "n1", "fabric_id": "fab1"}
    assert any(e.get("action") == "pve_sdn_fabric_node_get" for e in _entries(log))


# --- fabric nodes — mutations --------------------------------------------------------------------


def test_fabric_node_create_dry_run_low_then_confirm_fabric_id_path_only(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_fabric_node_create("fab1", "n1", "bgp", options={"ip": "10.99.99.5/24"})
    assert dry["status"] == "plan" and dry["risk"] == "low"
    assert api.posts == []
    server.pve_sdn_fabric_node_create("fab1", "n1", "bgp", options={"ip": "10.99.99.5/24"}, confirm=True)
    assert api.posts == [
        ("/cluster/sdn/fabrics/node/fab1", {"node_id": "n1", "protocol": "bgp", "ip": "10.99.99.5/24"}),
    ]
    entry = _confirmed_entry(log, "pve_sdn_fabric_node_create")
    assert entry["mutation"] is True


def test_fabric_node_update_dry_run_low_then_confirm(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_fabric_node_update("fab1", "n1", "wireguard", options={"endpoint": "1.2.3.4:51820"})
    assert dry["status"] == "plan" and dry["risk"] == "low"
    assert api.puts == []
    server.pve_sdn_fabric_node_update("fab1", "n1", "wireguard", options={"endpoint": "1.2.3.4:51820"}, confirm=True)
    assert api.puts == [
        ("/cluster/sdn/fabrics/node/fab1/n1", {"protocol": "wireguard", "endpoint": "1.2.3.4:51820"}),
    ]


def test_fabric_node_delete_dry_run_medium_then_confirm_no_params(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"node_id": "n1", "fabric_id": "fab1"}]
    dry = server.pve_sdn_fabric_node_delete("fab1", "n1")
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert api.dels == []
    server.pve_sdn_fabric_node_delete("fab1", "n1", confirm=True)
    assert api.dels == [("/cluster/sdn/fabrics/node/fab1/n1", None)]
    assert any(e.get("action") == "pve_sdn_fabric_node_delete" for e in _entries(log))


# --- node-scoped fabric status — reads + taint split -------------------------------------------


def test_fabric_status_interfaces_is_audited_read_and_reviewed_trusted(tmp_path, monkeypatch):
    monkeypatch.setenv(taint.TAINT_TRACK_ENV, "1")
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"name": "eth0", "state": "up", "type": "Point-to-Point"}]
    out = server.pve_sdn_fabric_status_interfaces("fab1")
    assert api.gets == ["/nodes/pve/sdn/fabrics/fab1/interfaces"]
    assert out == [{"name": "eth0", "state": "up", "type": "Point-to-Point"}]
    assert any(e.get("action") == "pve_sdn_fabric_status_interfaces" for e in _entries(log))
    assert taint.is_tainted(str(tmp_path)) is False


def test_fabric_status_neighbors_taints_when_tracking_on(tmp_path, monkeypatch):
    monkeypatch.setenv(taint.TAINT_TRACK_ENV, "1")
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"neighbor": "10.0.0.5", "status": "up", "uptime": "8h24m12s"}]
    out = server.pve_sdn_fabric_status_neighbors("fab1")
    assert api.gets == ["/nodes/pve/sdn/fabrics/fab1/neighbors"]
    assert out == [{"neighbor": "10.0.0.5", "status": "up", "uptime": "8h24m12s"}]
    assert taint.is_tainted(str(tmp_path)) is True
    entries = _entries(log)
    matched = [e for e in entries if e["action"] == "pve_sdn_fabric_status_neighbors"]
    assert matched[0]["detail"]["untrusted"] is True
    assert matched[0]["detail"]["content_trust"] == "adversarial"


def test_fabric_status_routes_taints_when_tracking_on(tmp_path, monkeypatch):
    monkeypatch.setenv(taint.TAINT_TRACK_ENV, "1")
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"route": "10.0.0.0/24", "via": ["10.0.0.1"]}]
    out = server.pve_sdn_fabric_status_routes("fab1")
    assert api.gets == ["/nodes/pve/sdn/fabrics/fab1/routes"]
    assert out == [{"route": "10.0.0.0/24", "via": ["10.0.0.1"]}]
    assert taint.is_tainted(str(tmp_path)) is True


def test_fabric_status_reads_no_taint_without_tracking_env(tmp_path, monkeypatch):
    """Default (no PROXIMO_TAINT_* env) -> completely inert, including for the adversarial
    neighbors/routes reads — matches the fail-closed-by-default posture the whole taint
    module documents."""
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = [{"neighbor": "10.0.0.5"}]
    server.pve_sdn_fabric_status_neighbors("fab1")
    assert taint.is_tainted(str(tmp_path)) is False


# --- lock_token/digest: accepted where the schema supports it, forwarded raw, never in ledger ---

_LOCK_TOKEN_SENTINEL = "sentinel-lock-token-value"  # noqa: S105 (test sentinel, not a real credential)
_DIGEST_SENTINEL = "sentinel-digest-value"

_LOCK_TOKEN_CASES = [
    pytest.param("pve_sdn_fabric_create", dict(fabric="fab1", protocol="bgp"), id="fabric_create"),
    pytest.param("pve_sdn_fabric_update", dict(fabric="fab1", protocol="bgp", options={"asn": 1}),
                 id="fabric_update"),
    pytest.param("pve_sdn_fabric_node_create", dict(fabric_id="fab1", node_id="n1", protocol="bgp"),
                 id="fabric_node_create"),
    pytest.param("pve_sdn_fabric_node_update",
                 dict(fabric_id="fab1", node_id="n1", protocol="bgp", options={"ip": "10.99.99.1/24"}),
                 id="fabric_node_update"),
]


@pytest.mark.parametrize("tool_name,kwargs", _LOCK_TOKEN_CASES)
def test_lock_token_and_digest_forwarded_raw_never_writes_to_ledger(tmp_path, monkeypatch, tool_name, kwargs):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)
    fn(confirm=True, lock_token=_LOCK_TOKEN_SENTINEL, digest=_DIGEST_SENTINEL, **kwargs)

    forwarded = [d for _, d in (api.posts + api.puts) if d]
    assert any(d.get("lock-token") == _LOCK_TOKEN_SENTINEL for d in forwarded), (
        f"{tool_name} confirm=True never forwarded lock_token to the wire"
    )
    assert any(d.get("digest") == _DIGEST_SENTINEL for d in forwarded), (
        f"{tool_name} confirm=True never forwarded digest to the wire"
    )

    raw = open(log, "rb").read()
    assert _LOCK_TOKEN_SENTINEL.encode("utf-8") not in raw
    assert _DIGEST_SENTINEL.encode("utf-8") not in raw


_NO_LOCK_TOKEN_PARAM_TOOLS = ["pve_sdn_fabric_delete", "pve_sdn_fabric_node_delete"]


@pytest.mark.parametrize("tool_name", _NO_LOCK_TOKEN_PARAM_TOOLS)
def test_delete_tools_accept_no_lock_token_or_digest_parameter(tool_name):
    """fabric_delete/fabric_node_delete have NEITHER digest NOR lock_token on this schema —
    verify the tool's own signature does not silently invent one."""
    import inspect
    fn = getattr(server, tool_name)
    params = inspect.signature(fn).parameters
    assert "lock_token" not in params
    assert "digest" not in params


# --- lock-token ECHO from a config READ: MAJOR #2 fix (post-review, 2026-07-17) -----------------
#
# `lock-token` is schema-documented in the RESPONSE of every fabric/fabric-node config read (the
# live SDN cluster-lock capability secret — a distinct concern from the CALLER-SUPPLIED
# lock_token param proven above, which is a legitimate write-side input, never a leak). A sentinel
# planted in the fake backend's read response must never surface in (a) the tool's return, (b)
# any plan text, (c) raw ledger bytes.

_LOCK_TOKEN_ECHO_SENTINEL = "sentinel-lock-token-echo-from-read"  # noqa: S105 (test sentinel)


def test_fabric_get_lock_token_echo_stripped_from_return_and_ledger(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = {"id": "fab1", "protocol": "bgp", "lock-token": _LOCK_TOKEN_ECHO_SENTINEL}
    out = server.pve_sdn_fabric_get("fab1")
    assert "lock-token" not in out
    assert out == {"id": "fab1", "protocol": "bgp"}
    raw = open(log, "rb").read()
    assert _LOCK_TOKEN_ECHO_SENTINEL.encode("utf-8") not in raw


def test_fabrics_list_lock_token_echo_stripped_per_row_and_ledger(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [
        {"id": "fab1", "protocol": "bgp", "lock-token": _LOCK_TOKEN_ECHO_SENTINEL},
        {"id": "fab2", "protocol": "ospf", "lock-token": _LOCK_TOKEN_ECHO_SENTINEL},
    ]
    out = server.pve_sdn_fabrics_list()
    assert all("lock-token" not in row for row in out)
    raw = open(log, "rb").read()
    assert _LOCK_TOKEN_ECHO_SENTINEL.encode("utf-8") not in raw


def test_plan_fabric_delete_capture_lock_token_echo_never_in_plan_or_ledger(tmp_path, monkeypatch):
    """CAPTURE-bearing plan factory: pve_sdn_fabric_delete's dry-run PLAN reads current fabrics
    via the same fabrics_list() that MAJOR #2 strips at the read layer — the sentinel must never
    surface in the plan's `current`/blast text, nor reach the ledger."""
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"id": "fab1", "protocol": "bgp", "lock-token": _LOCK_TOKEN_ECHO_SENTINEL}]
    dry = server.pve_sdn_fabric_delete("fab1")
    assert "lock-token" not in dry["current"]
    assert _LOCK_TOKEN_ECHO_SENTINEL not in json.dumps(dry)
    raw = open(log, "rb").read()
    assert _LOCK_TOKEN_ECHO_SENTINEL.encode("utf-8") not in raw
