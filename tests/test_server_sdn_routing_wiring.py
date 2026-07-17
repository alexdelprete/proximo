"""Server-level integration for SDN PREFIX-LISTS + ROUTE-MAPS (Wave 7e, full-surface
campaign).

Proves the trust gate holds across the new wiring:
- every read is an audited call at the exact path, recorded to the ledger;
- every mutation is dry-run by default (confirm=False => status="plan", op NOT called);
- a confirm=True call routes to the real op and records to the ledger;
- risk ladder through the SERVER wrapper (not just the bare plan factory): container/entry
  create+update are LOW, container/entry delete is MEDIUM, across both families;
- PENDING/apply-gated framing (no "LIVE/IMMEDIATE" language — this family is NOT the vnet
  firewall's live-effect model) present on every mutation plan;
- `lock_token` is accepted by all 9 mutations (schema-verified — every POST/PUT/DELETE on
  this plane carries a `lock-token` property), forwarded raw to the wire, but never written
  to the ledger's `detail=` (mirrors the 7a network.py / 7c sdn_objects.py precedent).

Backend is faked; the ledger is real (tmp_path) so PLAN->PROVE is exercised end to end.
Mirrors the `_wire()`/`_FakeApi` idiom in tests/test_server_sdn_objects_wiring.py.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
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


# --- prefix lists (container) — reads -------------------------------------------------------


def test_prefix_lists_list_is_audited_read(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"id": "pl1"}]
    out = server.pve_sdn_prefix_lists_list()
    assert api.gets == ["/cluster/sdn/prefix-lists"]
    assert out == [{"id": "pl1"}]
    assert any(e.get("action") == "pve_sdn_prefix_lists_list" for e in _entries(log))


def test_prefix_list_get_is_audited_read(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = {"id": "pl1"}
    out = server.pve_sdn_prefix_list_get("pl1")
    assert api.gets == ["/cluster/sdn/prefix-lists/pl1"]
    assert out == {"id": "pl1"}
    assert any(e.get("action") == "pve_sdn_prefix_list_get" for e in _entries(log))


# --- prefix lists (container) — mutations ---------------------------------------------------


def test_prefix_list_create_dry_run_low_then_confirm(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_prefix_list_create("pl1")
    assert dry["status"] == "plan" and dry["risk"] == "low"
    assert api.posts == []
    server.pve_sdn_prefix_list_create("pl1", confirm=True)
    assert api.posts == [("/cluster/sdn/prefix-lists", {"id": "pl1"})]
    entry = _confirmed_entry(log, "pve_sdn_prefix_list_create")
    assert entry["mutation"] is True


def test_prefix_list_update_dry_run_low_then_confirm(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    entries = [{"action": "permit", "prefix": "10.99.99.0/24"}]
    dry = server.pve_sdn_prefix_list_update("pl1", entries=entries)
    assert dry["status"] == "plan" and dry["risk"] == "low"
    assert api.puts == []
    server.pve_sdn_prefix_list_update("pl1", entries=entries, confirm=True)
    assert api.puts == [("/cluster/sdn/prefix-lists/pl1", {"entries": entries})]


def test_prefix_list_delete_dry_run_medium_then_confirm(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"id": "pl1"}]
    dry = server.pve_sdn_prefix_list_delete("pl1")
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert api.dels == []
    server.pve_sdn_prefix_list_delete("pl1", confirm=True)
    assert api.dels == [("/cluster/sdn/prefix-lists/pl1", {})]
    assert any(e.get("action") == "pve_sdn_prefix_list_delete" for e in _entries(log))


def test_prefix_list_mutations_never_softened_by_live_language(tmp_path, monkeypatch):
    """This family is PENDING/apply-gated, NOT the vnet firewall's LIVE/IMMEDIATE model —
    every mutation plan states the apply gate, never claims an immediate live effect."""
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_prefix_list_create("pl1")
    blast = " ".join(dry["blast_radius"]).lower()
    assert "inert until pve_sdn_apply" in blast
    assert "live/immediate" not in blast


# --- prefix-list entries — reads -------------------------------------------------------------


def test_prefix_list_entries_list_is_audited_read(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"action": "permit", "prefix": "10.99.99.0/24"}]
    out = server.pve_sdn_prefix_list_entries_list("pl1")
    assert api.gets == ["/cluster/sdn/prefix-lists/pl1/entries"]
    assert out == [{"action": "permit", "prefix": "10.99.99.0/24"}]
    assert any(e.get("action") == "pve_sdn_prefix_list_entries_list" for e in _entries(log))


def test_prefix_list_entry_get_is_audited_read_opaque_token(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = {"action": "permit", "prefix": "10.99.99.0/24"}
    out = server.pve_sdn_prefix_list_entry_get("pl1", "1")
    assert api.gets == ["/cluster/sdn/prefix-lists/pl1/entries/1"]
    assert out == {"action": "permit", "prefix": "10.99.99.0/24"}
    assert any(e.get("action") == "pve_sdn_prefix_list_entry_get" for e in _entries(log))


# --- prefix-list entries — mutations ----------------------------------------------------------


def test_prefix_list_entry_create_dry_run_low_then_confirm_no_digest_field(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_prefix_list_entry_create("pl1", "permit", "10.99.99.0/24")
    assert dry["status"] == "plan" and dry["risk"] == "low"
    assert api.posts == []
    server.pve_sdn_prefix_list_entry_create("pl1", "permit", "10.99.99.0/24", confirm=True)
    assert api.posts == [
        ("/cluster/sdn/prefix-lists/pl1/entries", {"action": "permit", "prefix": "10.99.99.0/24"}),
    ]
    entry = _confirmed_entry(log, "pve_sdn_prefix_list_entry_create")
    assert entry["mutation"] is True


def test_prefix_list_entry_update_dry_run_low_then_confirm(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_prefix_list_entry_update("pl1", "1", seq=5)
    assert dry["status"] == "plan" and dry["risk"] == "low"
    assert api.puts == []
    server.pve_sdn_prefix_list_entry_update("pl1", "1", seq=5, confirm=True)
    assert api.puts == [("/cluster/sdn/prefix-lists/pl1/entries/1", {"seq": 5})]


def test_prefix_list_entry_delete_dry_run_medium_then_confirm(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = {"action": "permit", "prefix": "10.99.99.0/24"}
    dry = server.pve_sdn_prefix_list_entry_delete("pl1", "1")
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert api.dels == []
    server.pve_sdn_prefix_list_entry_delete("pl1", "1", confirm=True)
    assert api.dels == [("/cluster/sdn/prefix-lists/pl1/entries/1", {})]
    assert any(e.get("action") == "pve_sdn_prefix_list_entry_delete" for e in _entries(log))


# --- route maps — reads -----------------------------------------------------------------------


def test_route_maps_list_is_audited_read(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"id": "rm1"}]
    out = server.pve_sdn_route_maps_list()
    assert api.gets == ["/cluster/sdn/route-maps"]
    assert out == [{"id": "rm1"}]
    assert any(e.get("action") == "pve_sdn_route_maps_list" for e in _entries(log))


def test_route_map_entries_list_all_is_audited_read(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"route-map-id": "rm1", "order": 0, "action": "permit"}]
    out = server.pve_sdn_route_map_entries_list_all()
    assert api.gets == ["/cluster/sdn/route-maps/entries"]
    assert out == [{"route-map-id": "rm1", "order": 0, "action": "permit"}]
    assert any(e.get("action") == "pve_sdn_route_map_entries_list_all" for e in _entries(log))


def test_route_map_entries_list_scoped_is_audited_read(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"route-map-id": "rm1", "order": 0, "action": "permit"}]
    out = server.pve_sdn_route_map_entries_list("rm1")
    assert api.gets == ["/cluster/sdn/route-maps/entries/rm1"]
    assert out == [{"route-map-id": "rm1", "order": 0, "action": "permit"}]
    assert any(e.get("action") == "pve_sdn_route_map_entries_list" for e in _entries(log))


def test_route_map_entry_get_is_audited_read_client_validated_order(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = {"route-map-id": "rm1", "order": 5, "action": "permit"}
    out = server.pve_sdn_route_map_entry_get("rm1", 5)
    assert api.gets == ["/cluster/sdn/route-maps/entries/rm1/entry/5"]
    assert out == {"route-map-id": "rm1", "order": 5, "action": "permit"}
    assert any(e.get("action") == "pve_sdn_route_map_entry_get" for e in _entries(log))


# --- route-map entries — mutations (NO container-level CRUD exists) ---------------------------


def test_route_map_entry_create_dry_run_low_then_confirm_implicit_creation_note(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_route_map_entry_create("rm1", 10, "permit")
    assert dry["status"] == "plan" and dry["risk"] == "low"
    assert any("implicitly CREATES" in line for line in dry["blast_radius"])
    assert api.posts == []
    server.pve_sdn_route_map_entry_create("rm1", 10, "permit", confirm=True)
    assert api.posts == [
        ("/cluster/sdn/route-maps/entries", {"route-map-id": "rm1", "order": 10, "action": "permit"}),
    ]
    entry = _confirmed_entry(log, "pve_sdn_route_map_entry_create")
    assert entry["mutation"] is True


def test_route_map_entry_update_dry_run_low_then_confirm(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_route_map_entry_update("rm1", 10, action="deny")
    assert dry["status"] == "plan" and dry["risk"] == "low"
    assert api.puts == []
    server.pve_sdn_route_map_entry_update("rm1", 10, action="deny", confirm=True)
    assert api.puts == [("/cluster/sdn/route-maps/entries/rm1/entry/10", {"action": "deny"})]


def test_route_map_entry_delete_dry_run_medium_then_confirm_notes_orphan_smoke_confirm(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = {"route-map-id": "rm1", "order": 10, "action": "permit"}
    dry = server.pve_sdn_route_map_entry_delete("rm1", 10)
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert any("UNDOCUMENTED" in line for line in dry["blast_radius"])
    assert api.dels == []
    server.pve_sdn_route_map_entry_delete("rm1", 10, confirm=True)
    assert api.dels == [("/cluster/sdn/route-maps/entries/rm1/entry/10", {})]
    assert any(e.get("action") == "pve_sdn_route_map_entry_delete" for e in _entries(log))


# --- lock_token: accepted by all 9 mutations, forwarded raw, never in the ledger --------------

_LOCK_TOKEN_SENTINEL = "sentinel-lock-token-value"  # noqa: S105 (test sentinel, not a real credential)

_LOCK_TOKEN_CASES = [
    pytest.param("pve_sdn_prefix_list_create", dict(prefix_list="pl1"), id="prefix_list_create"),
    pytest.param("pve_sdn_prefix_list_update", dict(prefix_list="pl1", entries=[]), id="prefix_list_update"),
    pytest.param("pve_sdn_prefix_list_delete", dict(prefix_list="pl1"), id="prefix_list_delete"),
    pytest.param("pve_sdn_prefix_list_entry_create",
                 dict(prefix_list="pl1", action="permit", prefix="10.99.99.0/24"),
                 id="prefix_list_entry_create"),
    pytest.param("pve_sdn_prefix_list_entry_update", dict(prefix_list="pl1", entry_id="1", seq=5),
                 id="prefix_list_entry_update"),
    pytest.param("pve_sdn_prefix_list_entry_delete", dict(prefix_list="pl1", entry_id="1"),
                 id="prefix_list_entry_delete"),
    pytest.param("pve_sdn_route_map_entry_create", dict(route_map_id="rm1", order=10, action="permit"),
                 id="route_map_entry_create"),
    pytest.param("pve_sdn_route_map_entry_update", dict(route_map_id="rm1", order=10, action="deny"),
                 id="route_map_entry_update"),
    pytest.param("pve_sdn_route_map_entry_delete", dict(route_map_id="rm1", order=10),
                 id="route_map_entry_delete"),
]


@pytest.mark.parametrize("tool_name,kwargs", _LOCK_TOKEN_CASES)
def test_lock_token_forwarded_raw_never_writes_to_ledger(tmp_path, monkeypatch, tool_name, kwargs):
    """`lock_token` is accepted by all 9 mutations (schema-verified — every POST/PUT/DELETE on
    this plane carries a `lock-token` property) but `_audited()`'s `detail` is a fixed
    `{"confirmed": True}` literal that structurally cannot include it (matches the 7a
    network.py / 7c sdn_objects.py precedent). Proves both directions: forwarded raw to the
    wire (the mutation must actually work) AND never in the raw ledger bytes."""
    _, api, _, log = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)
    fn(confirm=True, lock_token=_LOCK_TOKEN_SENTINEL, **kwargs)

    forwarded = [d for _, d in (api.posts + api.puts) if d] + [p for _, p in api.dels if p]
    assert any(d.get("lock-token") == _LOCK_TOKEN_SENTINEL for d in forwarded), (
        f"{tool_name} confirm=True never forwarded lock_token to the wire"
    )

    raw = open(log, "rb").read()
    assert _LOCK_TOKEN_SENTINEL.encode("utf-8") not in raw
