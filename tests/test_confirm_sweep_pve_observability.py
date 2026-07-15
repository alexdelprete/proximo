"""Confirm=True sweep — pve_observability wrapper welds (src/proximo/tools/pve_observability.py).

Closes the coverage-audit gap (`.scratch/2026-07-14-tool-coverage-audit-findings.json`, module
`src/proximo/tools/pve_observability.py`, 2 high findings): the confirm=True EXECUTE branch --
the wrapper's own `_audited(...)` call -- of all 6 PCI/USB mapping mutation tools and all 8
notification/metrics mutation tools was never invoked through the actual `server.pve_*` wrapper.
tests/test_mappings.py and tests/test_notifications.py thoroughly test the underlying op/plan
functions directly, and tests/test_wrapper_shapes.py's generic sweep dry-runs every mutating
wrapper (confirm=False only, by design) -- neither ever proves that confirm=True actually reaches
the wrapper's own argument-forwarding + `_audited()` wiring (a copy-paste kwarg mismatch in the
lambda would go undetected). `pve_node_service_control` (this module's other mutation tool) is
NOT in scope here -- it already has confirm=True coverage in test_server_new_wiring.py.

Mirrors the `_wire()` idiom in tests/test_server_plan.py:110-131 (already re-used and
review-approved in tests/test_confirm_sweep_pve_guest.py and
tests/test_confirm_sweep_pve_backup.py): `proximo.server._svc` is monkeypatched to a fake api +
a REAL AuditLedger in tmp_path, so a confirm=True call proves three welds at once:
  1. return shape -- status is the EXECUTED shape ("ok"), never "plan";
  2. the fake captured the underlying call (verb + path + data) -- reusing the fake idioms
     already established in test_mappings.py / test_notifications.py;
  3. the ledger recorded a confirmed mutation -- structural asserts only (action, mutation,
     outcome, detail.confirmed), never exact prose.

All 14 tools in this sweep record outcome="ok" (none of them return a task UPID -- these are
all synchronous config-plane REST calls), so the sweep table is fully homogeneous.

A second section (test-first, closing the med finding) proves the fix to
pve_notification_endpoint_create/_update: the dry-run PLAN must echo the `options` payload
(endpoint-specific config), not just `comment` -- key/value presence only, never exact prose.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig


class _Api:
    """Recording fake api: records every _post/_put/_delete call. `_get` always returns a
    generic `{}` -- falsy, so notification_matcher_set's `api._get(...) or []` existing-names
    read resolves to an empty list (routing it to the POST/create branch), and the mapping/
    endpoint plan builders' `api._get(path) or {}` current-config reads resolve to an empty
    dict. That's enough for every tool's _plan() build (which always runs first, even on
    confirm=True -- no plan, no mutation) to resolve without raising, while the mutation calls
    land in per-verb capture lists."""

    def __init__(self, node: str = "pve"):
        self.config = SimpleNamespace(node=node)
        self.gets: list[str] = []
        self.posts: list[tuple[str, dict | None]] = []
        self.puts: list[tuple[str, dict | None]] = []
        self.deletes: list[tuple[str, dict | None]] = []

    def _get(self, path):
        self.gets.append(path)
        return {}

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
    """The `_wire()` idiom from tests/test_server_plan.py:110-131."""
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        ct_allowlist=frozenset({"*"}), audit_log_path=log,
    )
    api = _Api()
    exec_ = SimpleNamespace()  # unused by pve_observability's non-exec wrappers
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
# Homogeneous sweep — table-driven over all 14 tools: "confirm=True reaches the right
# verb/path/data and records a confirmed mutation". Every tool here records outcome="ok".
# ---------------------------------------------------------------------------

_SWEEP_CASES = [
    # --- Plane F: PCI/USB hardware mappings ---
    pytest.param(
        "pve_mapping_pci_create",
        dict(mapping_id="gpu0", description="GPU passthrough", map="0000:01:00.0"),
        "posts", "/cluster/mapping/pci",
        {"id": "gpu0", "description": "GPU passthrough", "map": "0000:01:00.0"},
        id="mapping_pci_create",
    ),
    pytest.param(
        "pve_mapping_pci_update",
        dict(mapping_id="gpu0", description="GPU passthrough v2",
             map="0000:01:00.0;0000:01:00.1", digest="abc123"),
        "puts", "/cluster/mapping/pci/gpu0",
        {"description": "GPU passthrough v2", "map": "0000:01:00.0;0000:01:00.1",
         "digest": "abc123"},
        id="mapping_pci_update",
    ),
    pytest.param(
        "pve_mapping_pci_delete",
        dict(mapping_id="gpu0"),
        "deletes", "/cluster/mapping/pci/gpu0",
        None,
        id="mapping_pci_delete",
    ),
    pytest.param(
        "pve_mapping_usb_create",
        dict(mapping_id="scanner0", description="USB scanner", map="1-1.2"),
        "posts", "/cluster/mapping/usb",
        {"id": "scanner0", "description": "USB scanner", "map": "1-1.2"},
        id="mapping_usb_create",
    ),
    pytest.param(
        "pve_mapping_usb_update",
        dict(mapping_id="scanner0", description="USB scanner v2", map="1-1.3", digest="def456"),
        "puts", "/cluster/mapping/usb/scanner0",
        {"description": "USB scanner v2", "map": "1-1.3", "digest": "def456"},
        id="mapping_usb_update",
    ),
    pytest.param(
        "pve_mapping_usb_delete",
        dict(mapping_id="scanner0"),
        "deletes", "/cluster/mapping/usb/scanner0",
        None,
        id="mapping_usb_delete",
    ),
    # --- Plane E: notifications & metrics ---
    pytest.param(
        "pve_notification_endpoint_create",
        dict(ep_type="webhook", name="ep1", comment="alerts",
             options={"url": "https://example.test/hook"}),
        "posts", "/cluster/notifications/endpoints/webhook",
        {"name": "ep1", "comment": "alerts", "url": "https://example.test/hook"},
        id="notification_endpoint_create",
    ),
    pytest.param(
        "pve_notification_endpoint_update",
        dict(ep_type="webhook", name="ep1", comment="alerts v2",
             options={"url": "https://example.test/hook2"}),
        "puts", "/cluster/notifications/endpoints/webhook/ep1",
        {"comment": "alerts v2", "url": "https://example.test/hook2"},
        id="notification_endpoint_update",
    ),
    pytest.param(
        "pve_notification_endpoint_delete",
        dict(ep_type="webhook", name="ep1"),
        "deletes", "/cluster/notifications/endpoints/webhook/ep1",
        None,
        id="notification_endpoint_delete",
    ),
    pytest.param(
        "pve_notification_matcher_set",
        dict(name="m1", comment="route to ops"),
        "posts", "/cluster/notifications/matchers",
        {"name": "m1", "comment": "route to ops"},
        id="notification_matcher_set",
    ),
    pytest.param(
        "pve_notification_matcher_delete",
        dict(name="m1"),
        "deletes", "/cluster/notifications/matchers/m1",
        None,
        id="notification_matcher_delete",
    ),
    pytest.param(
        "pve_notification_test",
        dict(name="m1"),
        "posts", "/cluster/notifications/targets/m1/test",
        None,
        id="notification_test",
    ),
    pytest.param(
        "pve_metrics_server_set",
        dict(metrics_id="influx1", metrics_type="influxdb",
             server="influx.example.com", port=8089),
        "posts", "/cluster/metrics/server/influx1",
        {"type": "influxdb", "server": "influx.example.com", "port": 8089},
        id="metrics_server_set",
    ),
    pytest.param(
        "pve_metrics_server_delete",
        dict(metrics_id="influx1"),
        "deletes", "/cluster/metrics/server/influx1",
        None,
        id="metrics_server_delete",
    ),
]


@pytest.mark.parametrize("tool_name,kwargs,capture,path,data_exact", _SWEEP_CASES)
def test_confirm_true_executes_forwards_and_records(
    tmp_path, monkeypatch, tool_name, kwargs, capture, path, data_exact,
):
    """confirm=True executes (never 'plan'), the fake captured the forwarded call, and the
    ledger recorded a confirmed mutation — the three welds the audit found untested."""
    _, api, _, log = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)

    out = fn(confirm=True, **kwargs)

    # weld 1: return shape is the EXECUTED shape, never "plan"
    assert out["status"] == "ok"
    assert out["status"] != "plan"

    # weld 2: the fake captured the underlying call at the expected verb + path, with the
    # EXACT forwarded payload (full dict equality — an accidental extra field now fails).
    calls = getattr(api, capture)
    assert calls, f"{tool_name} confirm=True never reached api.{capture}"
    call_path, call_data = calls[-1]
    assert call_path == path
    assert call_data == data_exact

    # weld 3: ledger structural asserts — never exact prose
    entry = _confirmed_entry(log, tool_name, "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


# ---------------------------------------------------------------------------
# Fix (test-first): pve_notification_endpoint_create/_update PLAN must show the `options`
# payload -- an approver reviewing the dry-run PLAN before confirming never saw the actual
# endpoint config (gotify server/token, smtp server, webhook url, ...) that confirm=True goes
# on to apply, even though `options` is the central thing these tools configure (only `comment`
# reached the plan builder). Key/value presence only -- never exact prose (the plan's `change`
# text format is not this test's concern).
# ---------------------------------------------------------------------------


def test_notification_endpoint_create_plan_shows_options_payload(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)

    out = server.pve_notification_endpoint_create(
        ep_type="webhook", name="ep1",
        options={"url": "https://example.test/hook", "http-method": "post"},
        confirm=False,
    )

    assert out["status"] == "plan"
    haystack = json.dumps(out, default=str)
    assert "url" in haystack
    assert "https://example.test/hook" in haystack
    assert "http-method" in haystack
    assert "post" in haystack


def test_notification_endpoint_update_plan_shows_options_payload(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)

    out = server.pve_notification_endpoint_update(
        ep_type="smtp", name="ep2",
        options={"server": "smtp.example.com", "port": 587},
        confirm=False,
    )

    assert out["status"] == "plan"
    haystack = json.dumps(out, default=str)
    assert "server" in haystack
    assert "smtp.example.com" in haystack
    assert "port" in haystack
    assert "587" in haystack
