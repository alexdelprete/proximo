"""Confirm=True sweep — pve_firewall + pve_network wrapper welds.

Closes the coverage-audit gap (`.scratch/2026-07-14-tool-coverage-audit-findings.json`):
every tool below has its confirm=False PLAN branch tested (tests/test_firewall.py,
tests/test_network.py) but its confirm=True EXECUTE branch was never exercised through
the actual `server.pve_*` wrapper — only the underlying op/plan functions, bypassed the
wrapper's own argument-forwarding and _audited() wiring.

Mirrors the `_wire()` idiom in tests/test_server_plan.py:110-131: `proximo.server._svc` is
monkeypatched to a fake api + a REAL AuditLedger in tmp_path, so a confirm=True call proves
three welds at once:
  1. return shape — status is the EXECUTED shape ("ok"/"submitted"), never "plan";
  2. the fake api captured the underlying call (verb + path + data/params) — for the two
     firewall rule tools with an optimistic-lock digest, the digest/changes forwarding
     specifically;
  3. the ledger recorded a confirmed mutation — structural asserts only (action, mutation,
     outcome, detail.confirmed), never exact prose.

The fake api's `_get` is path-aware, reusing the idioms already established in
tests/test_firewall.py (`_api`/`_OptionsApi`) and tests/test_network.py (`_NetworkListApi`/
`_SdnApplyApi`): rules reads return a fixture rule with a digest, options reads return an
enable flag, network reads return one pre-existing iface, cluster/sdn reads return empty
lists. This lets every tool's _plan() build (which runs even on confirm=True — no plan, no
mutation) resolve without raising, while the mutation calls land in per-verb capture lists.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig


class _Api:
    """Path-aware fake Proxmox api: records every _post/_put/_delete call, and answers
    _get reads just enough for the PLAN builders (which always run first, even on
    confirm=True) to resolve without raising."""

    def __init__(self, node: str = "pve"):
        self.config = SimpleNamespace(node=node)
        self.gets: list[str] = []
        self.posts: list[tuple[str, dict]] = []
        self.puts: list[tuple[str, dict | None]] = []
        self.deletes: list[tuple[str, dict | None]] = []

    def _get(self, path):
        self.gets.append(path)
        if path.endswith("/rules"):
            # Schema-true fixture: NO digest field (neither cluster/node/guest rules-list
            # nor the SDN vnet-firewall rules-list/rule-get schema ever returns one — see
            # Wave 7b review Finding 1). A synthetic digest here would mask the exact break
            # that finding reproduced.
            return [{"pos": 0, "action": "ACCEPT", "type": "in"}]
        if path.endswith("/options"):
            return {"enable": 0}
        if "/cluster/resources" in path:
            return []
        if path.endswith("/network"):
            return [{"iface": "vmbr1", "type": "bridge"}]
        if path in ("/cluster/sdn/zones", "/cluster/sdn/vnets"):
            return []
        return []

    def _post(self, path, data=None):
        self.posts.append((path, data))
        return None

    def _put(self, path, data=None):
        self.puts.append((path, data))
        return None

    def _delete(self, path, params=None):
        self.deletes.append((path, params))
        return None


def _wire(tmp_path, monkeypatch):
    """The `_wire()` idiom from tests/test_server_plan.py:110-131 — fake api, real ledger."""
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        ct_allowlist=frozenset({"*"}), audit_log_path=log,
    )
    api = _Api()
    exec_ = SimpleNamespace()  # unused by firewall/network wrappers
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, exec_, ledger))
    return cfg, api, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _confirmed_entry(log: str, action: str, outcome: str) -> dict:
    entries = [e for e in _entries(log) if e["action"] == action and e["outcome"] == outcome]
    assert len(entries) == 1, f"expected exactly one {action!r}/{outcome!r} ledger entry, got {entries}"
    return entries[0]


# ---------------------------------------------------------------------------
# Homogeneous sweep — table-driven over the tools with no unique weld beyond
# "confirm=True reaches the right verb/path/data and records a confirmed mutation".
# ---------------------------------------------------------------------------

_SWEEP_CASES = [
    pytest.param(
        "pve_firewall_rule_add",
        dict(action="ACCEPT", direction="in", scope="cluster", source="10.0.0.0/8", dport="22"),
        "ok", "posts", "/cluster/firewall/rules",
        # enable defaults True -> 1; dest/proto/sport/comment omitted (not passed, all None).
        {"action": "ACCEPT", "type": "in", "enable": 1, "source": "10.0.0.0/8", "dport": "22"},
        id="firewall_rule_add",
    ),
    pytest.param(
        "pve_firewall_set_enabled",
        dict(enabled=True, scope="cluster"),
        "ok", "puts", "/cluster/firewall/options",
        {"enable": 1},
        id="firewall_set_enabled",
    ),
    pytest.param(
        "pve_network_apply",
        dict(),
        "submitted", "puts", "/nodes/pve/network",
        # network_apply() calls api._put(path) with no data arg -> fake captures data=None.
        None,
        id="network_apply",
    ),
    pytest.param(
        "pve_sdn_apply",
        dict(),
        "submitted", "puts", "/cluster/sdn",
        # sdn_apply() calls api._put(path) with no data arg -> fake captures data=None.
        None,
        id="sdn_apply",
    ),
    pytest.param(
        "pve_network_iface_create",
        dict(iface="vmbr2", iface_type="bridge", options={"address": "10.0.0.5"}),
        "ok", "posts", "/nodes/pve/network",
        # network_iface_create() builds data={"iface":.., "type":.., **opts} verbatim.
        {"iface": "vmbr2", "type": "bridge", "address": "10.0.0.5"},
        id="network_iface_create",
    ),
    pytest.param(
        "pve_network_iface_update",
        dict(iface="vmbr1", options={"address": "10.0.0.9"}),
        "ok", "puts", "/nodes/pve/network/vmbr1",
        # network_iface_update() sends {**opts, "type": current_type} — type is read back from
        # the fixture's network_list() ([{"iface": "vmbr1", "type": "bridge"}]), not passed by us.
        {"address": "10.0.0.9", "type": "bridge"},
        id="network_iface_update",
    ),
    pytest.param(
        "pve_sdn_vnet_update",
        dict(vnet="myvnet", options={"alias": "web2"}),
        "ok", "puts", "/cluster/sdn/vnets/myvnet",
        # sdn_vnet_update() sends dict(options) verbatim when delete/digest/lock_token are None.
        {"alias": "web2"},
        id="sdn_vnet_update",
    ),
    pytest.param(
        "pve_sdn_subnet_update",
        dict(vnet="myvnet", subnet="myzone-10.0.0.0-24", options={"gateway": "10.0.0.9"}),
        "ok", "puts", "/cluster/sdn/vnets/myvnet/subnets/myzone-10.0.0.0-24",
        # sdn_subnet_update() sends dict(options) verbatim when delete/digest/lock_token are None.
        {"gateway": "10.0.0.9"},
        id="sdn_subnet_update",
    ),
    # --- Wave 7a: global SDN control plane (lock/rollback) + the sdn_apply extension ---
    pytest.param(
        "pve_sdn_lock_acquire",
        dict(allow_pending=True),
        "ok", "posts", "/cluster/sdn/lock",
        # sdn_lock_acquire() sends {"allow-pending": True} verbatim when given.
        {"allow-pending": True},
        id="sdn_lock_acquire",
    ),
    pytest.param(
        "pve_sdn_lock_release",
        dict(lock_token="tok-sweep-1"),
        "ok", "deletes", "/cluster/sdn/lock",
        # sdn_lock_release() ALWAYS passes a params dict (possibly {}) — DELETE-family convention.
        {"lock-token": "tok-sweep-1"},
        id="sdn_lock_release",
    ),
    pytest.param(
        "pve_sdn_lock_release",
        dict(force=True),
        "ok", "deletes", "/cluster/sdn/lock",
        {"force": True},
        id="sdn_lock_release_force",
    ),
    pytest.param(
        "pve_sdn_rollback",
        dict(lock_token="tok-sweep-2", release_lock=False),
        "ok", "posts", "/cluster/sdn/rollback",
        # sdn_rollback() sends {"lock-token":.., "release-lock":..} verbatim when given.
        {"lock-token": "tok-sweep-2", "release-lock": False},
        id="sdn_rollback",
    ),
    pytest.param(
        "pve_sdn_apply",
        dict(lock_token="tok-sweep-3", release_lock=True),
        "submitted", "puts", "/cluster/sdn",
        # Wave 7a extension: sdn_apply() now forwards lock-token/release-lock when given — the
        # NEW params pinned (the pre-extension bare-call shape is covered by the "sdn_apply" row
        # above, unmodified: kwargs={}, data_exact=None).
        {"lock-token": "tok-sweep-3", "release-lock": True},
        id="sdn_apply_with_lock_params",
    ),
    # --- Wave 7b: vnet-scoped firewall + IP mappings (LIVE/IMMEDIATE — new sdn_firewall.py) ---
    pytest.param(
        "pve_sdn_vnet_firewall_options_set",
        dict(vnet="vnet1", options={"enable": True, "policy_forward": "DROP"}),
        "ok", "puts", "/cluster/sdn/vnets/vnet1/firewall/options",
        # vnet_firewall_options_set() passes the options bag through verbatim (no bool->1/0
        # coercion — matches firewall.py's own generic options-bag setter, not the dedicated
        # single-field firewall_set_enabled()).
        {"enable": True, "policy_forward": "DROP"},
        id="sdn_vnet_firewall_options_set",
    ),
    pytest.param(
        "pve_sdn_vnet_firewall_rule_add",
        dict(vnet="vnet1", action="accept", fw_type="in", dport="22"),
        "ok", "posts", "/cluster/sdn/vnets/vnet1/firewall/rules",
        # action is uppercased by _check_action; fw_type is always sent as 'type'.
        {"action": "ACCEPT", "type": "in", "dport": "22"},
        id="sdn_vnet_firewall_rule_add",
    ),
    pytest.param(
        "pve_sdn_vnet_firewall_rule_update",
        dict(vnet="vnet1", pos=0, action="drop", digest="caller-digest-77"),
        "ok", "puts", "/cluster/sdn/vnets/vnet1/firewall/rules/0",
        # Finding 1 fix: this schema's reads never expose a digest (neither rules-list nor
        # rule-get) — there is no op-time re-fetch anymore. digest is an OPTIONAL
        # caller-supplied passthrough only, forwarded byte-exact when given.
        {"action": "DROP", "digest": "caller-digest-77"},
        id="sdn_vnet_firewall_rule_update",
    ),
    pytest.param(
        "pve_sdn_vnet_firewall_rule_remove",
        dict(vnet="vnet1", pos=0, digest="caller-digest-88"),
        "ok", "deletes", "/cluster/sdn/vnets/vnet1/firewall/rules/0",
        # Finding 1 fix: same as rule_update — caller-supplied passthrough only.
        {"digest": "caller-digest-88"},
        id="sdn_vnet_firewall_rule_remove",
    ),
    pytest.param(
        "pve_sdn_vnet_ip_create",
        dict(vnet="vnet1", zone="zone1", ip="10.0.0.5", mac="aa:bb:cc:dd:ee:ff"),
        "ok", "posts", "/cluster/sdn/vnets/vnet1/ips",
        {"ip": "10.0.0.5", "vnet": "vnet1", "zone": "zone1", "mac": "aa:bb:cc:dd:ee:ff"},
        id="sdn_vnet_ip_create",
    ),
    pytest.param(
        "pve_sdn_vnet_ip_update",
        dict(vnet="vnet1", zone="zone1", ip="10.0.0.5", vmid="100"),
        "ok", "puts", "/cluster/sdn/vnets/vnet1/ips",
        # vmid is not accepted on create/delete — PUT-only (schema-verified).
        {"ip": "10.0.0.5", "vnet": "vnet1", "zone": "zone1", "vmid": "100"},
        id="sdn_vnet_ip_update",
    ),
    pytest.param(
        "pve_sdn_vnet_ip_delete",
        dict(vnet="vnet1", zone="zone1", ip="10.0.0.5"),
        "ok", "deletes", "/cluster/sdn/vnets/vnet1/ips",
        # no digest support at all on this endpoint (schema-verified) — never sent.
        {"ip": "10.0.0.5", "vnet": "vnet1", "zone": "zone1"},
        id="sdn_vnet_ip_delete",
    ),
    # --- Wave 7c: SDN controllers/dns/ipams (PENDING — new sdn_objects.py) ---
    #
    # Wave 7c's own report originally claimed 7b set a "no pre-existing sweep file to extend"
    # precedent and skipped this file entirely — FALSE (Wave 7c review MEDIUM-2): the block
    # above IS that precedent, and 7b extended it for its own 9 new mutations despite already
    # having a dedicated wiring test (test_server_sdn_firewall_wiring.py) with its own
    # confirm=True coverage. 7c's 9 new mutations get the same treatment here for consistency
    # — the module-specific test_server_sdn_objects_wiring.py additionally covers the
    # secret-redaction/url-userinfo-masking end-to-end proofs this generic sweep does not.
    pytest.param(
        "pve_sdn_controller_create",
        dict(controller="ctrl-sweep", controller_type="bgp", options={"asn": 65000}),
        "ok", "posts", "/cluster/sdn/controllers",
        {"type": "bgp", "controller": "ctrl-sweep", "asn": 65000},
        id="sdn_controller_create",
    ),
    pytest.param(
        "pve_sdn_controller_update",
        dict(controller="ctrl-sweep", options={"asn": 65001}),
        "ok", "puts", "/cluster/sdn/controllers/ctrl-sweep",
        {"asn": 65001},
        id="sdn_controller_update",
    ),
    pytest.param(
        "pve_sdn_controller_delete",
        dict(controller="ctrl-sweep"),
        "ok", "deletes", "/cluster/sdn/controllers/ctrl-sweep",
        {},
        id="sdn_controller_delete",
    ),
    pytest.param(
        "pve_sdn_dns_create",
        dict(dns="dns-sweep", url="https://pdns.example.com", key="sekret-key-sweep"),
        "ok", "posts", "/cluster/sdn/dns",
        {"type": "powerdns", "dns": "dns-sweep", "url": "https://pdns.example.com",
         "key": "sekret-key-sweep"},
        id="sdn_dns_create",
    ),
    pytest.param(
        "pve_sdn_dns_update",
        dict(dns="dns-sweep", dns_ttl=300),
        "ok", "puts", "/cluster/sdn/dns/dns-sweep",
        {"ttl": 300},
        id="sdn_dns_update",
    ),
    pytest.param(
        "pve_sdn_dns_delete",
        dict(dns="dns-sweep"),
        "ok", "deletes", "/cluster/sdn/dns/dns-sweep",
        {},
        id="sdn_dns_delete",
    ),
    pytest.param(
        "pve_sdn_ipam_create",
        dict(ipam="ipam-sweep", ipam_type="netbox", url="https://netbox.example.com",
             token="sekret-token-sweep"),
        "ok", "posts", "/cluster/sdn/ipams",
        {"type": "netbox", "ipam": "ipam-sweep", "url": "https://netbox.example.com",
         "token": "sekret-token-sweep"},
        id="sdn_ipam_create",
    ),
    pytest.param(
        "pve_sdn_ipam_update",
        dict(ipam="ipam-sweep", section=5),
        "ok", "puts", "/cluster/sdn/ipams/ipam-sweep",
        {"section": 5},
        id="sdn_ipam_update",
    ),
    pytest.param(
        "pve_sdn_ipam_delete",
        dict(ipam="ipam-sweep"),
        "ok", "deletes", "/cluster/sdn/ipams/ipam-sweep",
        {},
        id="sdn_ipam_delete",
    ),
    # --- Wave 7e: SDN prefix-lists + route-maps (PENDING — new sdn_routing.py) ---
    #
    # Same consistency treatment 7c gave this sweep for its own 9 mutations (see the block
    # above's own note) — module-specific secret/redaction proofs don't apply here (no
    # secret-shaped field exists on this plane), so this generic sweep is the primary
    # confirm=True coverage for these 9 tools; entry_id/order path-construction and the
    # 3-way digest asymmetry get their own dedicated unit coverage in test_sdn_routing.py.
    pytest.param(
        "pve_sdn_prefix_list_create",
        dict(prefix_list="pl-sweep"),
        "ok", "posts", "/cluster/sdn/prefix-lists",
        {"id": "pl-sweep"},
        id="sdn_prefix_list_create",
    ),
    pytest.param(
        "pve_sdn_prefix_list_update",
        dict(prefix_list="pl-sweep", entries=[{"action": "permit", "prefix": "10.99.99.0/24"}]),
        "ok", "puts", "/cluster/sdn/prefix-lists/pl-sweep",
        {"entries": [{"action": "permit", "prefix": "10.99.99.0/24"}]},
        id="sdn_prefix_list_update",
    ),
    pytest.param(
        "pve_sdn_prefix_list_delete",
        dict(prefix_list="pl-sweep"),
        "ok", "deletes", "/cluster/sdn/prefix-lists/pl-sweep",
        {},
        id="sdn_prefix_list_delete",
    ),
    pytest.param(
        "pve_sdn_prefix_list_entry_create",
        dict(prefix_list="pl-sweep", action="permit", prefix="10.99.99.0/24"),
        "ok", "posts", "/cluster/sdn/prefix-lists/pl-sweep/entries",
        {"action": "permit", "prefix": "10.99.99.0/24"},
        id="sdn_prefix_list_entry_create",
    ),
    pytest.param(
        "pve_sdn_prefix_list_entry_update",
        dict(prefix_list="pl-sweep", entry_id="1", seq=5),
        "ok", "puts", "/cluster/sdn/prefix-lists/pl-sweep/entries/1",
        # seq is the ONLY field touched here — no digest passed, none forwarded.
        {"seq": 5},
        id="sdn_prefix_list_entry_update",
    ),
    pytest.param(
        "pve_sdn_prefix_list_entry_delete",
        dict(prefix_list="pl-sweep", entry_id="1"),
        "ok", "deletes", "/cluster/sdn/prefix-lists/pl-sweep/entries/1",
        {},
        id="sdn_prefix_list_entry_delete",
    ),
    pytest.param(
        "pve_sdn_route_map_entry_create",
        dict(route_map_id="rm-sweep", order=10, action="permit"),
        "ok", "posts", "/cluster/sdn/route-maps/entries",
        {"route-map-id": "rm-sweep", "order": 10, "action": "permit"},
        id="sdn_route_map_entry_create",
    ),
    pytest.param(
        "pve_sdn_route_map_entry_update",
        dict(route_map_id="rm-sweep", order=10, action="deny"),
        "ok", "puts", "/cluster/sdn/route-maps/entries/rm-sweep/entry/10",
        {"action": "deny"},
        id="sdn_route_map_entry_update",
    ),
    pytest.param(
        "pve_sdn_route_map_entry_delete",
        dict(route_map_id="rm-sweep", order=10),
        "ok", "deletes", "/cluster/sdn/route-maps/entries/rm-sweep/entry/10",
        {},
        id="sdn_route_map_entry_delete",
    ),
]


@pytest.mark.parametrize(
    "tool_name,kwargs,expected_status,capture,path,data_exact", _SWEEP_CASES,
)
def test_confirm_true_executes_forwards_and_records(
    tmp_path, monkeypatch, tool_name, kwargs, expected_status, capture, path, data_exact,
):
    """confirm=True executes (never 'plan'), the fake captured the forwarded call, and the
    ledger recorded a confirmed mutation — the three welds the audit found untested."""
    _, api, _, log = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)

    out = fn(confirm=True, **kwargs)

    # weld 1: return shape is the EXECUTED shape, never "plan"
    assert out["status"] == expected_status
    assert out["status"] != "plan"

    # weld 2: the fake captured the underlying call at the expected verb + path, with the
    # EXACT forwarded payload (full dict equality — an accidental extra field now fails).
    calls = getattr(api, capture)
    assert calls, f"{tool_name} confirm=True never reached api.{capture}"
    call_path, call_data = calls[-1]
    assert call_path == path
    assert call_data == data_exact

    # weld 3: ledger structural asserts — never exact prose
    entry = _confirmed_entry(log, tool_name, expected_status)
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


# ---------------------------------------------------------------------------
# pve_firewall_rule_remove — unique weld: the optimistic-lock digest forwarding.
# ---------------------------------------------------------------------------


def test_firewall_rule_remove_confirm_forwards_digest_and_records_confirmed(tmp_path, monkeypatch):
    """confirm=True on pve_firewall_rule_remove forwards the caller-supplied digest to the
    DELETE params verbatim — the optimistic-lock promise the docstring makes — and records
    a confirmed mutation."""
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_firewall_rule_remove(
        pos=0, scope="cluster", digest="caller-digest-77", confirm=True,
    )

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    assert api.deletes, "pve_firewall_rule_remove confirm=True never reached api._delete"
    call_path, call_params = api.deletes[-1]
    assert call_path == "/cluster/firewall/rules/0"
    # exact: firewall_rule_remove() sends {"digest": effective_digest} — nothing else.
    assert call_params == {"digest": "caller-digest-77"}

    entry = _confirmed_entry(log, "pve_firewall_rule_remove", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


# ---------------------------------------------------------------------------
# pve_firewall_rule_update — unique weld: digest AND **changes forwarding.
# ---------------------------------------------------------------------------


def test_firewall_rule_update_confirm_forwards_digest_and_changes_and_records_confirmed(
    tmp_path, monkeypatch,
):
    """confirm=True on pve_firewall_rule_update forwards BOTH the caller-supplied digest AND
    the built **changes kwargs (only the fields actually passed) to the PUT body, and records
    a confirmed mutation."""
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_firewall_rule_update(
        pos=0, scope="cluster", action="DROP", comment="updated rule",
        digest="caller-digest-99", confirm=True,
    )

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    assert api.puts, "pve_firewall_rule_update confirm=True never reached api._put"
    call_path, call_data = api.puts[-1]
    assert call_path == "/cluster/firewall/rules/0"
    # exact: only action/comment were passed as changes, plus the digest — direction/source/dest/
    # proto/dport/sport/enable stay OUT of the PUT body entirely (omitted, not None-valued).
    assert call_data == {"action": "DROP", "comment": "updated rule", "digest": "caller-digest-99"}

    entry = _confirmed_entry(log, "pve_firewall_rule_update", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


# ---------------------------------------------------------------------------
# Wave 7b Finding 1 fix — pve_sdn_vnet_firewall_rule_update/_remove: the DEFAULT
# no-digest-supplied confirm=True path must SUCCEED, not raise. This is the exact break the
# review reproduced against the old op-time-refetch-or-fail digest design: this schema's
# reads (rules list / rule get) never expose a digest field at all (schema-verified), so a
# fetch-or-fail posture failed on EVERY confirm call. digest is now an OPTIONAL
# caller-supplied passthrough only — see the sweep rows above for the forwarded-when-given
# proof.
# ---------------------------------------------------------------------------


def test_sdn_vnet_firewall_rule_remove_confirm_without_digest_succeeds(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_sdn_vnet_firewall_rule_remove(vnet="vnet1", pos=0, confirm=True)

    assert out["status"] == "ok"
    assert out["status"] != "plan"
    assert api.deletes[-1] == ("/cluster/sdn/vnets/vnet1/firewall/rules/0", {})

    entry = _confirmed_entry(log, "pve_sdn_vnet_firewall_rule_remove", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


def test_sdn_vnet_firewall_rule_update_confirm_without_digest_succeeds(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_sdn_vnet_firewall_rule_update(vnet="vnet1", pos=0, action="drop", confirm=True)

    assert out["status"] == "ok"
    assert out["status"] != "plan"
    assert api.puts[-1] == ("/cluster/sdn/vnets/vnet1/firewall/rules/0", {"action": "DROP"})

    entry = _confirmed_entry(log, "pve_sdn_vnet_firewall_rule_update", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
