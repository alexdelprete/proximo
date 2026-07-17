"""SDN PREFIX-LISTS + ROUTE-MAPS tests (Wave 7e, full-surface campaign) — fully mocked, no
live Proxmox.

Mirrors test_sdn_objects.py / test_network.py's own conventions:
- Op functions: a tiny fake api recording method/path/data (`_rec()`).
- Plan functions: fake apis giving just enough for each plan's own safe-read (CAPTURE) to
  resolve.
- Every test is self-contained — no shared mutable state.

Coverage:
 1. Validators — _check_action, _check_bounded_int (+ order/ge_le/seq wrappers),
    _check_prefix_cidr, _check_entry_id (opaque path-safety, NOT integer-typed),
    _check_list_of_dicts, _check_dict
 2. Prefix lists (container) — list/get URL construction (pending/running/verbose query),
    create (digest ON create — a real plane exception)/update (delete=["entries"] enum,
    at-least-one-field guard, entries=[] distinct from omitted)/delete payload construction
 3. Prefix-list entries — list/get URL construction (opaque entry_id path-quoted), create (NO
    digest — asymmetry vs. update)/update (digest present, delete enum le/ge/seq)/delete
 4. Route maps — list URL construction (NO pending param — asymmetry vs. every other list on
    this module), entries_list_all/entries_list (scoped) URL construction, entry_get (order
    IS client-validated, unlike prefix-list's url_seq)
 5. Route-map entries — create (route_map_id free-form, NO container CRUD)/update (delete enum
    set/match/call/exit-action)/delete payload construction; match/set_clauses/exit_action
    generic-passthrough (no per-key enum enforcement); digest present on BOTH create and
    update (the third digest-availability pattern on this plane)
 6. Plan factories — risk ladder (LOW create/update, MEDIUM delete), "at least one field"
    guards, PENDING/apply-gated blast language, referential-integrity Smoke-confirm language,
    route-map orphan Smoke-confirm language, implicit-route-map-creation note
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from proximo.backends import ProximoError
from proximo.planning import RISK_LOW, RISK_MEDIUM
from proximo.sdn_routing import (
    _check_action,
    _check_bounded_int,
    _check_dict,
    _check_entry_id,
    _check_ge_le,
    _check_list_of_dicts,
    _check_order,
    _check_prefix_cidr,
    _check_seq,
    plan_prefix_list_create,
    plan_prefix_list_delete,
    plan_prefix_list_entry_create,
    plan_prefix_list_entry_delete,
    plan_prefix_list_entry_update,
    plan_prefix_list_update,
    plan_route_map_entry_create,
    plan_route_map_entry_delete,
    plan_route_map_entry_update,
    prefix_list_create,
    prefix_list_delete,
    prefix_list_entries_list,
    prefix_list_entry_create,
    prefix_list_entry_delete,
    prefix_list_entry_get,
    prefix_list_entry_update,
    prefix_list_get,
    prefix_list_update,
    prefix_lists_list,
    route_map_entries_list,
    route_map_entries_list_all,
    route_map_entry_create,
    route_map_entry_delete,
    route_map_entry_get,
    route_map_entry_update,
    route_maps_list,
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


@pytest.mark.parametrize("value", ["permit", "deny"])
def test_check_action_accepts_both(value):
    assert _check_action(value) == value


def test_check_action_rejects_unknown():
    with pytest.raises(ProximoError):
        _check_action("allow")


def test_check_bounded_int_accepts_in_range():
    assert _check_bounded_int(5, "x", 0, 10) == 5
    assert _check_bounded_int("5", "x", 0, 10) == 5


def test_check_bounded_int_accepts_zero_falsy_value():
    """falsy-value honesty (the osdid=0 lesson): 0 is a legitimate order/ge/le value, not a
    stand-in for None/omitted."""
    assert _check_bounded_int(0, "order", 0, 65535) == 0


@pytest.mark.parametrize("value", [-1, 129, "not-an-int", None])
def test_check_bounded_int_rejects_out_of_range_or_non_integer(value):
    with pytest.raises(ProximoError):
        _check_bounded_int(value, "ge", 0, 128)


def test_check_bounded_int_rejects_bool():
    with pytest.raises(ProximoError):
        _check_bounded_int(True, "order", 0, 65535)


def test_check_order_accepts_bounds():
    assert _check_order(0) == 0
    assert _check_order(65535) == 65535


def test_check_order_rejects_out_of_range():
    with pytest.raises(ProximoError):
        _check_order(65536)


def test_check_ge_le_accepts_bounds():
    assert _check_ge_le(0, "ge") == 0
    assert _check_ge_le(128, "le") == 128


def test_check_ge_le_rejects_out_of_range():
    with pytest.raises(ProximoError):
        _check_ge_le(129, "ge")


def test_check_seq_accepts_bounds():
    assert _check_seq(1) == 1
    assert _check_seq(4294967295) == 4294967295


def test_check_seq_rejects_zero():
    with pytest.raises(ProximoError):
        _check_seq(0)


def test_check_prefix_cidr_accepts_ipv4_and_ipv6():
    assert _check_prefix_cidr("10.99.99.0/24") == "10.99.99.0/24"
    assert _check_prefix_cidr("::/0") == "::/0"
    assert _check_prefix_cidr("0.0.0.0/0") == "0.0.0.0/0"


def test_check_prefix_cidr_rejects_garbage():
    with pytest.raises(ProximoError):
        _check_prefix_cidr("not-a-cidr")


def test_check_entry_id_accepts_opaque_token():
    """fact #1: entry_id is NOT integer-typed — any path-safe token passes, not just digits."""
    assert _check_entry_id("1") == "1"
    assert _check_entry_id("some-opaque-token") == "some-opaque-token"
    assert _check_entry_id(1) == "1"


@pytest.mark.parametrize("value", ["a/b", "..", "with space", "with\nnewline", ""])
def test_check_entry_id_rejects_path_unsafe(value):
    with pytest.raises(ProximoError):
        _check_entry_id(value)


def test_check_list_of_dicts_passthrough_and_none():
    assert _check_list_of_dicts(None, "entries") is None
    assert _check_list_of_dicts([{"a": 1}], "entries") == [{"a": 1}]


def test_check_list_of_dicts_rejects_non_list():
    with pytest.raises(ProximoError):
        _check_list_of_dicts({"a": 1}, "entries")


def test_check_dict_passthrough_and_none():
    assert _check_dict(None, "exit_action") is None
    assert _check_dict({"key": "continue"}, "exit_action") == {"key": "continue"}


def test_check_dict_rejects_non_dict():
    with pytest.raises(ProximoError):
        _check_dict([1, 2], "exit_action")


# ---------------------------------------------------------------------------
# 2. Prefix lists (container) — reads
# ---------------------------------------------------------------------------


def test_prefix_lists_list_url_no_params():
    api = _rec()
    prefix_lists_list(api)
    assert api.seen["path"] == "/cluster/sdn/prefix-lists"


def test_prefix_lists_list_query_params():
    api = _rec()
    prefix_lists_list(api, pending=True, running=False, verbose=True)
    assert api.seen["path"] == "/cluster/sdn/prefix-lists?pending=1&running=0&verbose=1"


def test_prefix_list_get_url():
    api = _rec()
    prefix_list_get(api, "pl1")
    assert api.seen["path"] == "/cluster/sdn/prefix-lists/pl1"


def test_prefix_lists_list_empty_defaults_to_list():
    api = _rec()
    assert prefix_lists_list(api) == []


def test_prefix_list_get_empty_defaults_to_dict():
    api = _rec()
    assert prefix_list_get(api, "pl1") == {}


# ---------------------------------------------------------------------------
# 2b. Prefix lists (container) — mutations
# ---------------------------------------------------------------------------


def test_prefix_list_create_posts_id_only():
    api = _rec()
    prefix_list_create(api, "pl1")
    assert api.seen["method"] == "POST"
    assert api.seen["path"] == "/cluster/sdn/prefix-lists"
    assert api.seen["data"] == {"id": "pl1"}


def test_prefix_list_create_with_entries_digest_lock_token():
    """digest IS accepted on prefix-list CREATE — a real plane exception (fact #4)."""
    api = _rec()
    entries = [{"action": "permit", "prefix": "10.99.99.0/24"}]
    prefix_list_create(api, "pl1", entries=entries, digest="d1", lock_token="t1")
    assert api.seen["data"] == {
        "id": "pl1", "entries": entries, "digest": "d1", "lock-token": "t1",
    }


def test_prefix_list_create_rejects_non_list_entries():
    api = _rec()
    with pytest.raises(ProximoError):
        prefix_list_create(api, "pl1", entries={"not": "a list"})


def test_prefix_list_update_puts_entries():
    api = _rec()
    entries = [{"action": "deny", "prefix": "10.99.99.0/24"}]
    prefix_list_update(api, "pl1", entries=entries)
    assert api.seen["method"] == "PUT"
    assert api.seen["path"] == "/cluster/sdn/prefix-lists/pl1"
    assert api.seen["data"] == {"entries": entries}


def test_prefix_list_update_delete_entries_enum():
    api = _rec()
    prefix_list_update(api, "pl1", delete=["entries"])
    assert api.seen["data"] == {"delete": "entries"}


def test_prefix_list_update_digest_and_lock_token():
    api = _rec()
    prefix_list_update(api, "pl1", entries=[], digest="d1", lock_token="t1")
    assert api.seen["data"] == {"entries": [], "digest": "d1", "lock-token": "t1"}


def test_prefix_list_update_requires_at_least_one_field():
    api = _rec()
    with pytest.raises(ProximoError):
        prefix_list_update(api, "pl1")


def test_prefix_list_update_accepts_explicit_empty_entries_list():
    """falsy-value honesty: entries=[] is a legitimate, distinct 'replace with nothing' input
    from omitting entries entirely — it must NOT trip the at-least-one-field guard."""
    api = _rec()
    prefix_list_update(api, "pl1", entries=[])  # no raise
    assert api.seen["data"] == {"entries": []}


def test_prefix_list_delete_url_and_params():
    api = _rec()
    prefix_list_delete(api, "pl1")
    assert api.seen["method"] == "DELETE"
    assert api.seen["path"] == "/cluster/sdn/prefix-lists/pl1"
    assert api.seen["params"] == {}


def test_prefix_list_delete_with_lock_token():
    api = _rec()
    prefix_list_delete(api, "pl1", lock_token="t1")
    assert api.seen["params"] == {"lock-token": "t1"}


# ---------------------------------------------------------------------------
# 3. Prefix-list entries
# ---------------------------------------------------------------------------


def test_prefix_list_entries_list_url():
    api = _rec()
    prefix_list_entries_list(api, "pl1")
    assert api.seen["path"] == "/cluster/sdn/prefix-lists/pl1/entries"


def test_prefix_list_entry_get_url_opaque_token():
    api = _rec()
    prefix_list_entry_get(api, "pl1", "1")
    assert api.seen["path"] == "/cluster/sdn/prefix-lists/pl1/entries/1"


def test_prefix_list_entry_get_quotes_special_chars_in_token():
    """'#' is path-safe per _check_entry_id (no '/', no whitespace/control) but would
    otherwise terminate the URL early if not percent-encoded — proves quote() is real."""
    api = _rec()
    prefix_list_entry_get(api, "pl1", "a#b")
    assert api.seen["path"] == "/cluster/sdn/prefix-lists/pl1/entries/a%23b"


def test_prefix_list_entry_create_posts_required_fields_no_digest():
    """NO digest on entry CREATE — asymmetry vs. entry UPDATE (fact #4)."""
    api = _rec()
    prefix_list_entry_create(api, "pl1", "permit", "10.99.99.0/24")
    assert api.seen["method"] == "POST"
    assert api.seen["path"] == "/cluster/sdn/prefix-lists/pl1/entries"
    assert api.seen["data"] == {"action": "permit", "prefix": "10.99.99.0/24"}


def test_prefix_list_entry_create_with_ge_le_seq_and_lock_token():
    api = _rec()
    prefix_list_entry_create(api, "pl1", "deny", "10.99.99.0/24", ge=24, le=32, seq=10,
                              lock_token="t1")
    assert api.seen["data"] == {
        "action": "deny", "prefix": "10.99.99.0/24", "ge": 24, "le": 32, "seq": 10,
        "lock-token": "t1",
    }


def test_prefix_list_entry_create_accepts_ge_zero():
    """falsy-value honesty: ge=0 is legitimate (matches every prefix length), not "omitted"."""
    api = _rec()
    prefix_list_entry_create(api, "pl1", "permit", "10.99.99.0/24", ge=0)
    assert api.seen["data"]["ge"] == 0


def test_prefix_list_entry_update_puts_fields_with_digest():
    """digest IS accepted on entry UPDATE — asymmetry vs. entry CREATE (fact #4)."""
    api = _rec()
    prefix_list_entry_update(api, "pl1", "1", seq=5, digest="d1")
    assert api.seen["method"] == "PUT"
    assert api.seen["path"] == "/cluster/sdn/prefix-lists/pl1/entries/1"
    assert api.seen["data"] == {"seq": 5, "digest": "d1"}


def test_prefix_list_entry_update_delete_enum():
    api = _rec()
    prefix_list_entry_update(api, "pl1", "1", delete=["ge", "le", "seq"])
    assert api.seen["data"] == {"delete": "ge,le,seq"}


def test_prefix_list_entry_update_requires_at_least_one_field():
    api = _rec()
    with pytest.raises(ProximoError):
        prefix_list_entry_update(api, "pl1", "1")


def test_prefix_list_entry_delete_url_and_params():
    api = _rec()
    prefix_list_entry_delete(api, "pl1", "1", lock_token="t1")
    assert api.seen["method"] == "DELETE"
    assert api.seen["path"] == "/cluster/sdn/prefix-lists/pl1/entries/1"
    assert api.seen["params"] == {"lock-token": "t1"}


# ---------------------------------------------------------------------------
# 4. Route maps — reads
# ---------------------------------------------------------------------------


def test_route_maps_list_url_no_params():
    api = _rec()
    route_maps_list(api)
    assert api.seen["path"] == "/cluster/sdn/route-maps"


def test_route_maps_list_running_query_only():
    """fact #7: NO 'pending' param exists on this endpoint — only 'running'."""
    api = _rec()
    route_maps_list(api, running=True)
    assert api.seen["path"] == "/cluster/sdn/route-maps?running=1"


def test_route_map_entries_list_all_url():
    api = _rec()
    route_map_entries_list_all(api, pending=True, running=False)
    assert api.seen["path"] == "/cluster/sdn/route-maps/entries?pending=1&running=0"


def test_route_map_entries_list_scoped_url():
    api = _rec()
    route_map_entries_list(api, "rm1", pending=True)
    assert api.seen["path"] == "/cluster/sdn/route-maps/entries/rm1?pending=1"


def test_route_map_entry_get_url_client_validated_order():
    """fact #2: order IS client-validated as an integer, unlike prefix-list's url_seq."""
    api = _rec()
    route_map_entry_get(api, "rm1", 5)
    assert api.seen["path"] == "/cluster/sdn/route-maps/entries/rm1/entry/5"


def test_route_map_entry_get_rejects_out_of_range_order():
    api = _rec()
    with pytest.raises(ProximoError):
        route_map_entry_get(api, "rm1", 65536)


def test_route_map_entry_get_accepts_order_zero():
    """falsy-value honesty: order=0 is a legitimate first-position entry."""
    api = _rec()
    route_map_entry_get(api, "rm1", 0)
    assert api.seen["path"] == "/cluster/sdn/route-maps/entries/rm1/entry/0"


# ---------------------------------------------------------------------------
# 5. Route-map entries — mutations
# ---------------------------------------------------------------------------


def test_route_map_entry_create_posts_required_fields():
    """fact #3: route_map_id is free-form — no container-level create exists."""
    api = _rec()
    route_map_entry_create(api, "rm1", 10, "permit")
    assert api.seen["method"] == "POST"
    assert api.seen["path"] == "/cluster/sdn/route-maps/entries"
    assert api.seen["data"] == {"route-map-id": "rm1", "order": 10, "action": "permit"}


def test_route_map_entry_create_with_match_set_exit_action_call_digest():
    """digest IS accepted on entry CREATE here — unlike prefix-list's own entry create
    (fact #4, the third digest-availability pattern on this plane). match/set/exit-action are
    forwarded as generic passthrough — no per-key enum enforced client-side (fact #8)."""
    api = _rec()
    match = [{"key": "tag", "value": "100"}]
    set_clauses = [{"key": "local-preference", "value": "200"}]
    exit_action = {"key": "continue"}
    route_map_entry_create(api, "rm1", 10, "permit", match=match, set_clauses=set_clauses,
                            exit_action=exit_action, call="rm2", digest="d1", lock_token="t1")
    assert api.seen["data"] == {
        "route-map-id": "rm1", "order": 10, "action": "permit",
        "match": match, "set": set_clauses, "exit-action": exit_action, "call": "rm2",
        "digest": "d1", "lock-token": "t1",
    }


def test_route_map_entry_create_accepts_order_zero():
    api = _rec()
    route_map_entry_create(api, "rm1", 0, "deny")
    assert api.seen["data"]["order"] == 0


def test_route_map_entry_update_puts_fields_with_digest():
    api = _rec()
    route_map_entry_update(api, "rm1", 10, action="deny", digest="d1")
    assert api.seen["method"] == "PUT"
    assert api.seen["path"] == "/cluster/sdn/route-maps/entries/rm1/entry/10"
    assert api.seen["data"] == {"action": "deny", "digest": "d1"}


def test_route_map_entry_update_delete_enum():
    api = _rec()
    route_map_entry_update(api, "rm1", 10, delete=["set", "match", "call", "exit-action"])
    assert api.seen["data"] == {"delete": "set,match,call,exit-action"}


def test_route_map_entry_update_requires_at_least_one_field():
    api = _rec()
    with pytest.raises(ProximoError):
        route_map_entry_update(api, "rm1", 10)


def test_route_map_entry_update_accepts_explicit_empty_match_list():
    """falsy-value honesty: match=[] clears the clause set explicitly, distinct from omitted."""
    api = _rec()
    route_map_entry_update(api, "rm1", 10, match=[])
    assert api.seen["data"] == {"match": []}


def test_route_map_entry_delete_url_and_params():
    api = _rec()
    route_map_entry_delete(api, "rm1", 10, lock_token="t1")
    assert api.seen["method"] == "DELETE"
    assert api.seen["path"] == "/cluster/sdn/route-maps/entries/rm1/entry/10"
    assert api.seen["params"] == {"lock-token": "t1"}


# ---------------------------------------------------------------------------
# 6. Plan factories — prefix lists (container)
# ---------------------------------------------------------------------------


def test_plan_prefix_list_create_is_low_and_pending():
    plan = plan_prefix_list_create("pl1")
    assert plan.risk == RISK_LOW
    assert "inert until pve_sdn_apply" in " ".join(plan.blast_radius).lower()


def test_plan_prefix_list_create_discloses_seeded_entry_count():
    plan = plan_prefix_list_create("pl1", entries=[{"action": "permit", "prefix": "10.99.99.0/24"}])
    assert "seeded with 1 entrie(s)" in " ".join(plan.blast_radius)


def test_plan_prefix_list_update_requires_at_least_one_field():
    with pytest.raises(ProximoError):
        plan_prefix_list_update("pl1")


def test_plan_prefix_list_update_accepts_explicit_empty_entries():
    plan = plan_prefix_list_update("pl1", entries=[])  # no raise
    assert plan.risk == RISK_LOW


def test_plan_prefix_list_update_notes_replace_vs_merge_ambiguity():
    plan = plan_prefix_list_update("pl1", entries=[{"action": "permit", "prefix": "10.99.99.0/24"}])
    assert any("UNDOCUMENTED" in line for line in plan.blast_radius)


def test_plan_prefix_list_delete_is_medium_with_smoke_confirm_language():
    api = _rec()
    api.seen["_get_return"] = [{"id": "pl1"}]
    plan = plan_prefix_list_delete(api, "pl1")
    assert plan.risk == RISK_MEDIUM
    assert plan.complete is True
    assert any("Smoke-confirm" in line for line in plan.blast_radius)


def test_plan_prefix_list_delete_read_failure_discloses_uncertainty():
    plan = plan_prefix_list_delete(_boom_api(), "pl1")
    assert plan.risk == RISK_MEDIUM
    assert plan.complete is False
    assert any("UNKNOWN" in line for line in plan.blast_radius)


# ---------------------------------------------------------------------------
# 6b. Plan factories — prefix-list entries
# ---------------------------------------------------------------------------


def test_plan_prefix_list_entry_create_is_low():
    plan = plan_prefix_list_entry_create("pl1", "permit", "10.99.99.0/24")
    assert plan.risk == RISK_LOW


def test_plan_prefix_list_entry_update_requires_at_least_one_field():
    with pytest.raises(ProximoError):
        plan_prefix_list_entry_update("pl1", "1")


def test_plan_prefix_list_entry_delete_is_medium_and_captures():
    api = _rec()
    api.seen["_get_return"] = {"action": "permit", "prefix": "10.99.99.0/24"}
    plan = plan_prefix_list_entry_delete(api, "pl1", "1")
    assert plan.risk == RISK_MEDIUM
    assert plan.current == {"action": "permit", "prefix": "10.99.99.0/24"}


def test_plan_prefix_list_entry_delete_read_failure_discloses_uncertainty():
    plan = plan_prefix_list_entry_delete(_boom_api(), "pl1", "1")
    assert plan.complete is False
    assert any("UNKNOWN" in line for line in plan.blast_radius)


# ---------------------------------------------------------------------------
# 6c. Plan factories — route-map entries
# ---------------------------------------------------------------------------


def test_plan_route_map_entry_create_is_low_and_notes_implicit_creation():
    plan = plan_route_map_entry_create("rm1", 10, "permit")
    assert plan.risk == RISK_LOW
    assert any("implicitly CREATES" in line for line in plan.blast_radius)


def test_plan_route_map_entry_update_requires_at_least_one_field():
    with pytest.raises(ProximoError):
        plan_route_map_entry_update("rm1", 10)


def test_plan_route_map_entry_delete_is_medium_and_notes_orphan_smoke_confirm():
    api = _rec()
    api.seen["_get_return"] = {"action": "permit", "order": 10}
    plan = plan_route_map_entry_delete(api, "rm1", 10)
    assert plan.risk == RISK_MEDIUM
    assert any("Smoke-confirm" in line for line in plan.blast_radius)
    assert any("UNDOCUMENTED" in line for line in plan.blast_radius)


def test_plan_route_map_entry_delete_read_failure_discloses_uncertainty():
    plan = plan_route_map_entry_delete(_boom_api(), "rm1", 10)
    assert plan.complete is False
    assert any("UNKNOWN" in line for line in plan.blast_radius)


# ---------------------------------------------------------------------------
# Tests for MAJOR fix: composite content disclosure in plan previews
# ---------------------------------------------------------------------------


def test_plan_prefix_list_create_discloses_entry_content():
    """Entry content (not just count) must appear in plan text."""
    plan = plan_prefix_list_create("pl1", entries=[
        {"action": "permit", "prefix": "192.168.0.0/24"}
    ])
    plan_text = " ".join(plan.blast_radius)
    assert "action=permit" in plan_text
    assert "prefix=192.168.0.0/24" in plan_text


def test_plan_prefix_list_create_discloses_multiple_entries():
    """Multiple entries must all appear in plan text."""
    plan = plan_prefix_list_create("pl1", entries=[
        {"action": "permit", "prefix": "192.168.0.0/24"},
        {"action": "deny", "prefix": "10.0.0.0/8"}
    ])
    plan_text = " ".join(plan.blast_radius)
    assert "action=permit" in plan_text
    assert "prefix=192.168.0.0/24" in plan_text
    assert "action=deny" in plan_text
    assert "prefix=10.0.0.0/8" in plan_text


def test_plan_prefix_list_create_discloses_empty_entries():
    """Empty entries list must be clearly shown as empty, not omitted."""
    plan = plan_prefix_list_create("pl1", entries=[])
    plan_text = " ".join(plan.blast_radius)
    # Should show the empty array, not skip it
    assert "[]" in plan_text


def test_plan_prefix_list_update_discloses_entry_content():
    """Updated entry content must appear in plan text."""
    plan = plan_prefix_list_update("pl1", entries=[
        {"action": "deny", "prefix": "203.0.113.0/24"}
    ])
    plan_text = " ".join(plan.blast_radius) + plan.change
    assert "action=deny" in plan_text
    assert "prefix=203.0.113.0/24" in plan_text


def test_plan_route_map_entry_create_discloses_match_content():
    """Route-map match clauses content must appear in plan text."""
    plan = plan_route_map_entry_create("rm1", 10, "permit", match=[
        {"key": "ip-type", "value": "ipv4"}
    ])
    plan_text = " ".join(plan.blast_radius)
    # Verify the key and value both appear in the composite format
    assert "key=ip-type" in plan_text and "value=ipv4" in plan_text


def test_plan_route_map_entry_create_discloses_set_content():
    """Route-map set clauses content must appear in plan text."""
    plan = plan_route_map_entry_create("rm1", 10, "permit", set_clauses=[
        {"key": "ip-next-hop", "value": "192.168.0.99"}
    ])
    plan_text = " ".join(plan.blast_radius)
    # Verify the key and value both appear in the composite format
    assert "key=ip-next-hop" in plan_text and "value=192.168.0.99" in plan_text


def test_plan_route_map_entry_create_discloses_multiple_set_clauses():
    """Multiple set clauses must all appear in plan text."""
    plan = plan_route_map_entry_create("rm1", 10, "permit", set_clauses=[
        {"key": "ip-next-hop", "value": "192.168.0.99"},
        {"key": "local-preference", "value": "100"}
    ])
    plan_text = " ".join(plan.blast_radius)
    # Verify all keys and values appear
    assert "key=ip-next-hop" in plan_text and "value=192.168.0.99" in plan_text
    assert "key=local-preference" in plan_text and "value=100" in plan_text


def test_plan_route_map_entry_create_discloses_exit_action():
    """Route-map exit-action content must appear in plan text."""
    plan = plan_route_map_entry_create("rm1", 10, "permit", exit_action={
        "key": "on-match-goto", "value": "next-route-map"
    })
    plan_text = " ".join(plan.blast_radius)
    # Verify the key and value both appear
    assert "key=on-match-goto" in plan_text and "value=next-route-map" in plan_text


def test_plan_route_map_entry_update_discloses_match_content():
    """Updated match clauses content must appear in plan text."""
    plan = plan_route_map_entry_update("rm1", 10, match=[
        {"key": "route-type", "value": "bgp"}
    ])
    plan_text = plan.change
    # Verify the key and value both appear
    assert "key=route-type" in plan_text and "value=bgp" in plan_text


def test_plan_route_map_entry_update_discloses_set_content():
    """Updated set clauses content must appear in plan text."""
    plan = plan_route_map_entry_update("rm1", 10, set_clauses=[
        {"key": "metric", "value": "50"}
    ])
    plan_text = plan.change
    # Verify the key and value both appear
    assert "key=metric" in plan_text and "value=50" in plan_text
