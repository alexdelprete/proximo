"""Confirm=True sweep — PMG mail routing config remainder (Wave 9d: domains/transport/mynetworks
GET+PUT halves, tlspolicy, tls-inbound-domains, mimetypes, regextest — src/proximo/pmg.py +
src/proximo/tools/pmg_mail.py).

Mirrors the `_wire()`/`_Pmg` idiom already established in `tests/test_confirm_sweep_pmg_node.py`
(itself mirroring `tests/test_confirm_sweep_pbs_node.py`'s own `_Pbs` template): `_svc` is
monkeypatched (the ONE shared audit ledger lives behind it — `_ledger()` reads `_svc()[3]`) and
`_pmg` is monkeypatched to a fake PmgBackend. This file duplicates its own `_Pmg`/`_wire` rather
than importing another confirm-sweep module's — same self-contained convention every confirm-sweep
module in this repo follows.

Every 9d PLAN function is PURE (no `api` parameter, matching the already-shipped
domain_create/transport_create/mynetworks_add sibling family's own convention) — so unlike the
9a/9b sweep, dry-run previews here never touch the fake backend at all; `_Pmg._get` only matters
for the read-reaches-pmg tests below.

Each confirm=True call proves the three welds every confirm-sweep module proves:
  1. return shape — status is "ok" (synchronous), never "plan";
  2. the fake PmgBackend captured the underlying call (verb + path + EXACT payload);
  3. the ledger recorded a confirmed mutation — structural asserts only, never exact prose.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig


class _Pmg:
    """Path-aware fake PmgBackend: records every _get/_post/_put/_delete call."""

    def __init__(self):
        self.gets: list[tuple[str, dict | None]] = []
        self.posts: list[tuple[str, dict | None]] = []
        self.puts: list[tuple[str, dict | None]] = []
        self.deletes: list[tuple[str, dict | None]] = []
        self.config = SimpleNamespace(node="pmg", username="root@pam")

    def _get(self, path, params=None):
        self.gets.append((path, params))
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


class _Api:
    """Minimal PVE API stub — only needed so server._svc() resolves (the ONE shared ledger lives
    behind it); pmg.py's Wave 9d tools never touch this backend."""

    def __init__(self):
        self.config = SimpleNamespace(node="pve")


def _wire(tmp_path, monkeypatch):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log,
    )
    api = _Api()
    pmg = _Pmg()
    exec_ = SimpleNamespace()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, exec_, ledger))
    monkeypatch.setattr(server, "_pmg", lambda: (SimpleNamespace(node="pmg"), pmg))
    return cfg, pmg, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _confirmed_entry(log: str, action: str, outcome: str) -> dict:
    entries = [e for e in _entries(log) if e["action"] == action and e["outcome"] == outcome]
    assert len(entries) == 1, f"expected exactly one {action!r}/{outcome!r} ledger entry, got {entries}"
    return entries[0]


# ---------------------------------------------------------------------------
# Homogeneous sweep — table-driven: "confirm=True reaches the right verb/path/data on the
# PmgBackend and records a confirmed mutation".
# ---------------------------------------------------------------------------

_SWEEP_CASES = [
    pytest.param(
        "pmg_domain_update",
        dict(domain="example.com", comment="primary domain"),
        "puts", "/config/domains/example.com",
        {"comment": "primary domain"},
        id="domain_update",
    ),
    pytest.param(
        "pmg_transport_update",
        dict(domain="example.com", host="relay2.example.com"),
        "puts", "/config/transport/example.com",
        {"host": "relay2.example.com"},
        id="transport_update",
    ),
    pytest.param(
        "pmg_mynetworks_update",
        dict(cidr="10.0.0.0/8", comment="internal net"),
        "puts", "/config/mynetworks/10.0.0.0%2F8",
        {"comment": "internal net"},
        id="mynetworks_update",
    ),
    pytest.param(
        "pmg_tlspolicy_create",
        dict(destination="example.com", policy="secure"),
        "posts", "/config/tlspolicy",
        {"destination": "example.com", "policy": "secure"},
        id="tlspolicy_create",
    ),
    pytest.param(
        "pmg_tlspolicy_update",
        dict(destination="example.com", policy="none"),
        "puts", "/config/tlspolicy/example.com",
        {"policy": "none"},
        id="tlspolicy_update",
    ),
    pytest.param(
        "pmg_tlspolicy_delete",
        dict(destination="example.com"),
        "deletes", "/config/tlspolicy/example.com",
        None,
        id="tlspolicy_delete",
    ),
    pytest.param(
        "pmg_tls_inbound_domains_create",
        dict(domain="example.com"),
        "posts", "/config/tls-inbound-domains",
        {"domain": "example.com"},
        id="tls_inbound_domains_create",
    ),
    pytest.param(
        "pmg_tls_inbound_domains_delete",
        dict(domain="example.com"),
        "deletes", "/config/tls-inbound-domains/example.com",
        None,
        id="tls_inbound_domains_delete",
    ),
]


@pytest.mark.parametrize(
    "tool_name,kwargs,capture,path,data_exact", _SWEEP_CASES,
)
def test_confirm_true_executes_forwards_and_records(
    tmp_path, monkeypatch, tool_name, kwargs, capture, path, data_exact,
):
    """confirm=True executes (never 'plan'), the fake captured the forwarded call, and the ledger
    recorded a confirmed mutation — the three welds every confirm-sweep module proves."""
    _, pmg, _, log = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)

    out = fn(confirm=True, **kwargs)

    # weld 1: return shape is the EXECUTED shape, never "plan" (all 9d mutations are synchronous)
    assert out["status"] == "ok"

    # weld 2: the fake captured the underlying call at the expected verb + path, with the EXACT
    # forwarded payload (full dict equality — an accidental extra field now fails).
    calls = getattr(pmg, capture)
    assert calls, f"{tool_name} confirm=True never reached pmg.{capture}"
    call_path, call_data = calls[-1]
    assert call_path == path
    assert call_data == data_exact

    # weld 3: ledger structural asserts — never exact prose
    entry = _confirmed_entry(log, tool_name, "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


# ---------------------------------------------------------------------------
# Dry-run: confirm=False never touches the backend (spot-check across verb shapes)
# ---------------------------------------------------------------------------

def test_domain_update_dry_run_never_puts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_domain_update(domain="example.com", comment="x", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.puts


def test_tlspolicy_create_dry_run_never_posts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_tlspolicy_create(destination="example.com", policy="secure", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.posts


def test_tlspolicy_delete_dry_run_never_deletes(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_tlspolicy_delete(destination="example.com", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.deletes


def test_transport_update_dry_run_requires_at_least_one_field(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    with pytest.raises(Exception):  # noqa: B017 — ProximoError surfaces as a tool-call exception
        server.pmg_transport_update(domain="example.com", confirm=False)


# ---------------------------------------------------------------------------
# Direction-aware disclosure: the dry-run PLAN's blast_radius names the real security direction
# BEFORE confirm=True executes it (mirrors the 9a Critical "plan discloses every destructive
# component" class, extended to this chunk's own direction-aware family).
# ---------------------------------------------------------------------------

def test_tlspolicy_create_plan_discloses_downgrade_direction(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    out = server.pmg_tlspolicy_create(destination="example.com", policy="none", confirm=False)
    assert out["status"] == "plan"
    joined = " ".join(out["blast_radius"]).lower()
    assert "downgrade" in joined


def test_tls_inbound_domains_delete_plan_discloses_loosening_direction(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    out = server.pmg_tls_inbound_domains_delete(domain="example.com", confirm=False)
    assert out["status"] == "plan"
    joined = " ".join(out["blast_radius"]).lower()
    assert "loosen" in joined


# ---------------------------------------------------------------------------
# Reads reach the fake PmgBackend and are audited as non-mutations (no PLAN/confirm ceremony).
# ---------------------------------------------------------------------------

_READ_CASES = [
    pytest.param("pmg_domain_get", dict(domain="example.com"), "/config/domains/example.com", id="domain_get"),
    pytest.param("pmg_transport_list", dict(), "/config/transport", id="transport_list"),
    pytest.param("pmg_transport_get", dict(domain="example.com"), "/config/transport/example.com", id="transport_get"),
    pytest.param("pmg_mynetworks_list", dict(), "/config/mynetworks", id="mynetworks_list"),
    pytest.param("pmg_mynetworks_get", dict(cidr="10.0.0.0/8"), "/config/mynetworks/10.0.0.0%2F8", id="mynetworks_get"),
    pytest.param("pmg_tlspolicy_list", dict(), "/config/tlspolicy", id="tlspolicy_list"),
    pytest.param(
        "pmg_tlspolicy_get", dict(destination="example.com"), "/config/tlspolicy/example.com",
        id="tlspolicy_get",
    ),
    pytest.param("pmg_tls_inbound_domains_list", dict(), "/config/tls-inbound-domains", id="tls_inbound_domains_list"),
    pytest.param("pmg_mimetypes_list", dict(), "/config/mimetypes", id="mimetypes_list"),
]


@pytest.mark.parametrize("tool_name,kwargs,path", _READ_CASES)
def test_read_reaches_pmg_and_is_audited_as_non_mutation(tmp_path, monkeypatch, tool_name, kwargs, path):
    _, pmg, _, log = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)
    fn(**kwargs)
    assert any(g[0] == path for g in pmg.gets), f"{tool_name} never reached {path!r}: {pmg.gets}"
    assert any(e["action"] == tool_name and not e["mutation"] for e in _entries(log))


def test_regextest_reaches_pmg_via_post_but_is_audited_as_non_mutation(tmp_path, monkeypatch):
    """regextest is POST-verbed but classified by EFFECT not verb (pmg.py Wave 9d fact #6) — no
    PLAN/confirm ceremony, audited exactly like the GET-verbed reads above."""
    _, pmg, _, log = _wire(tmp_path, monkeypatch)
    server.pmg_regextest(regex="^foo", text="foobar")
    assert pmg.posts[-1] == ("/config/regextest", {"regex": "^foo", "text": "foobar"})
    assert any(e["action"] == "pmg_regextest" and not e["mutation"] for e in _entries(log))
