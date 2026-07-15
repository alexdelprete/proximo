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
            return [{"pos": 0, "digest": "rule-digest-fallback", "action": "ACCEPT", "type": "in"}]
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
