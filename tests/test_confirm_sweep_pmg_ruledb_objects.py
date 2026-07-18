"""Confirm=True sweep — PMG RuleDB per-object reads + ldapuser extension + rule<->action-group
read + RuleDB factory reset wrapper welds (src/proximo/tools/pmg_rules.py, Wave 8a). Starts the
PMG-specific confirm-sweep coverage (draft §6 follow-up debt item 3 — no `test_confirm_sweep_pmg_*`
file existed before this wave; backfilling the 81 already-shipped PMG mutations is out of scope
here, logged debt).

Mirrors the `_wire()`/fake-backend template in `tests/test_confirm_sweep_pbs_s3.py` (itself
mirroring `tests/test_server_plan.py:110-131`): `_svc` is monkeypatched (the ONE shared audit
ledger lives behind it — `_ledger()` reads `_svc()[3]`) and `_pmg` is monkeypatched to a fake
PmgBackend (`_Pmg`, the PMG-plane sibling of `_Pbs`). This file duplicates its own `_Pmg`/`_wire`
rather than importing another confirm-sweep module's — same self-contained convention every
confirm-sweep module in this repo follows.

Wave 8a has NO secrets on this region (coordinator-verified — no digest, no secret-shaped params
anywhere in the 92-path/138-method region) so there is no raw-bytes-never-in-ledger sweep to add
here, unlike the PBS S3 / tape-media / metrics confirm-sweep files.

Covers:
  - the 9 new read tools (exact wire-path proof, no confirm gate — reads execute unconditionally),
  - the 2 ldapuser signature-extension rows on the ALREADY-shipped pmg_who_object_add/update
    (additive-compat: the extension's own exact-payload proof, not a re-test of the 6 pre-existing
    types, which stay covered by tests/test_pmg.py's TestWhoObjectAdd/Update),
  - pmg_ruledb_reset: confirm=True exact-payload (empty POST body — the only shape possible, per
    the schema's own additionalProperties: 0), dry-run-never-posts, and the CAPTURE-or-degrade
    plan behavior (5 best-effort reads render the toll; a capture-read failure degrades to an
    honest note rather than blocking the plan — proven end-to-end through the full server wrapper,
    not just the bare plan factory already covered in tests/test_pmg.py).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.backends import ProximoError
from proximo.config import ProximoConfig


class _Pmg:
    """Path-aware fake PmgBackend: records every _get/_post/_put/_delete call.

    `get_return`: a single fixed value returned for ANY path not covered by `get_routes` (the
    simple case — the 9 read-wiring tests just need SOME dict back).
    `get_routes`: path -> return value, for tests that need different reads to answer differently
    (plan_ruledb_reset's 5-source CAPTURE).
    `raise_on`: a set of paths whose _get call raises ProximoError — proves the fail-open
    "capture read failure degrades to an honest note" behavior end-to-end.
    """

    def __init__(self, get_return=None, get_routes=None, raise_on=None):
        self._get_return = get_return
        self._get_routes = get_routes or {}
        self._raise_on = raise_on or set()
        self.gets: list[tuple[str, dict | None]] = []
        self.posts: list[tuple[str, dict | None]] = []
        self.puts: list[tuple[str, dict | None]] = []
        self.deletes: list[tuple[str, dict | None]] = []

    def _get(self, path, params=None):
        self.gets.append((path, params))
        if path in self._raise_on:
            raise ProximoError(f"simulated capture failure for {path}")
        if path in self._get_routes:
            return self._get_routes[path]
        return self._get_return

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
    behind it); pmg_rules.py's tools never touch this backend."""

    def __init__(self):
        self.config = SimpleNamespace(node="pve")


def _wire(tmp_path, monkeypatch, get_return=None, get_routes=None, raise_on=None):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log,
    )
    api = _Api()
    pmg = _Pmg(get_return=get_return, get_routes=get_routes, raise_on=raise_on)
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
# The 9 new reads — exact wire-path proof. Reads execute unconditionally (no confirm= gate);
# the weld under test is "the wrapper reaches PmgBackend at the exact expected path".
# ---------------------------------------------------------------------------

_READ_CASES = [
    pytest.param(
        "pmg_who_object_get", dict(ogroup="2", type_="email", id_="5"),
        "/config/ruledb/who/2/email/5", id="who_object_get",
    ),
    pytest.param(
        "pmg_who_object_get", dict(ogroup="2", type_="ldapuser", id_="9"),
        "/config/ruledb/who/2/ldapuser/9", id="who_object_get_ldapuser",
    ),
    pytest.param(
        "pmg_what_object_get", dict(ogroup="8", type_="contenttype", id_="3"),
        "/config/ruledb/what/8/contenttype/3", id="what_object_get",
    ),
    pytest.param(
        "pmg_when_object_get", dict(ogroup="4", id_="6"),
        "/config/ruledb/when/4/timeframe/6", id="when_object_get",
    ),
    pytest.param(
        "pmg_action_bcc_get", dict(id_="13_26"),
        "/config/ruledb/action/bcc/13_26", id="action_bcc_get",
    ),
    pytest.param(
        "pmg_action_field_get", dict(id_="13_27"),
        "/config/ruledb/action/field/13_27", id="action_field_get",
    ),
    pytest.param(
        "pmg_action_notification_get", dict(id_="13_28"),
        "/config/ruledb/action/notification/13_28", id="action_notification_get",
    ),
    pytest.param(
        "pmg_action_disclaimer_get", dict(id_="13_29"),
        "/config/ruledb/action/disclaimer/13_29", id="action_disclaimer_get",
    ),
    pytest.param(
        "pmg_action_removeattachments_get", dict(id_="13_30"),
        "/config/ruledb/action/removeattachments/13_30", id="action_removeattachments_get",
    ),
    pytest.param(
        "pmg_ruledb_rule_action_groups_list", dict(id_="100"),
        "/config/ruledb/rules/100/action", id="ruledb_rule_action_groups_list",
    ),
]


@pytest.mark.parametrize("tool_name,kwargs,path", _READ_CASES)
def test_read_reaches_pmg_at_expected_path(tmp_path, monkeypatch, tool_name, kwargs, path):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch, get_return={"id": 1})
    fn = getattr(server, tool_name)
    fn(**kwargs)
    call_path, _ = pmg.gets[-1]
    assert call_path == path
    # reads never touch the write verbs
    assert not pmg.posts
    assert not pmg.puts
    assert not pmg.deletes


def test_read_is_audited_as_non_mutation(tmp_path, monkeypatch):
    _, _, _, log = _wire(tmp_path, monkeypatch, get_return={"id": 1})
    server.pmg_who_object_get(ogroup="2", type_="email", id_="5")
    entries = [e for e in _entries(log) if e["action"] == "pmg_who_object_get"]
    assert len(entries) == 1
    assert entries[0]["mutation"] is False


# ---------------------------------------------------------------------------
# ldapuser signature extension — exact-payload proof on the ALREADY-shipped
# pmg_who_object_add/pmg_who_object_update (additive-compat: the 6 pre-existing types stay
# covered by tests/test_pmg.py's TestWhoObjectAdd/TestWhoObjectUpdate, untouched by this wave).
# ---------------------------------------------------------------------------

_LDAPUSER_SWEEP_CASES = [
    pytest.param(
        "pmg_who_object_add",
        dict(ogroup="2", type_="ldapuser", account="jdoe", profile="corp"),
        "ok", "posts", "/config/ruledb/who/2/ldapuser",
        {"account": "jdoe", "profile": "corp"},
        id="who_object_add_ldapuser",
    ),
    pytest.param(
        "pmg_who_object_update",
        dict(ogroup="2", type_="ldapuser", id_="9", account="jdoe2"),
        "ok", "puts", "/config/ruledb/who/2/ldapuser/9",
        {"account": "jdoe2"},
        id="who_object_update_ldapuser",
    ),
]


@pytest.mark.parametrize(
    "tool_name,kwargs,expected_status,capture,path,data_exact", _LDAPUSER_SWEEP_CASES,
)
def test_ldapuser_confirm_true_executes_forwards_and_records(
    tmp_path, monkeypatch, tool_name, kwargs, expected_status, capture, path, data_exact,
):
    _, pmg, _, log = _wire(tmp_path, monkeypatch, get_return={"id": 1})
    fn = getattr(server, tool_name)

    out = fn(confirm=True, **kwargs)

    assert out["status"] == expected_status
    assert out["status"] != "plan"

    calls = getattr(pmg, capture)
    assert calls, f"{tool_name} confirm=True never reached pmg.{capture}"
    call_path, call_data = calls[-1]
    assert call_path == path
    assert call_data == data_exact

    entry = _confirmed_entry(log, tool_name, expected_status)
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


def test_who_object_add_ldapuser_dry_run_never_posts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_who_object_add(
        ogroup="2", type_="ldapuser", account="jdoe", profile="corp", confirm=False,
    )
    assert out["status"] == "plan"
    assert not pmg.posts


# ---------------------------------------------------------------------------
# pmg_ruledb_reset — the wave's only RISK_HIGH mutation. Zero params upstream
# (additionalProperties: 0) so the exact-payload proof is an EMPTY POST body; the plan CAPTURES
# 5 sources and renders the toll, degrading honestly (never blocking) on a capture-read failure.
# ---------------------------------------------------------------------------

_EMPTY_RULEDB_ROUTES = {
    "/config/ruledb/rules": [],
    "/config/ruledb/who": [],
    "/config/ruledb/what": [],
    "/config/ruledb/when": [],
    "/config/ruledb/action/objects": [],
}


def test_ruledb_reset_confirm_true_posts_empty_body_and_records(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(tmp_path, monkeypatch, get_routes=_EMPTY_RULEDB_ROUTES)

    out = server.pmg_ruledb_reset(confirm=True)

    # weld 1: return shape — synchronous "ok", never "submitted" (schema: returns null)
    assert out["status"] == "ok"
    assert out["status"] != "plan"
    assert out["status"] != "submitted"

    # weld 2: the fake captured the underlying POST with the EXACT (empty) payload — the only
    # shape possible per the schema's own additionalProperties: 0 / zero params.
    assert pmg.posts, "pmg_ruledb_reset confirm=True never reached pmg._post"
    call_path, call_data = pmg.posts[-1]
    assert call_path == "/config/ruledb"
    assert call_data == {}

    # weld 3: ledger structural asserts
    entry = _confirmed_entry(log, "pmg_ruledb_reset", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


def test_ruledb_reset_dry_run_never_posts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch, get_routes=_EMPTY_RULEDB_ROUTES)
    out = server.pmg_ruledb_reset(confirm=False)
    assert out["status"] == "plan"
    assert not pmg.posts


def test_ruledb_reset_risk_is_high(tmp_path, monkeypatch):
    _, _, _, _ = _wire(tmp_path, monkeypatch, get_routes=_EMPTY_RULEDB_ROUTES)
    out = server.pmg_ruledb_reset(confirm=False)
    assert out["risk"] == "high"


def test_ruledb_reset_dry_run_captures_toll_from_all_five_sources(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch, get_routes={
        "/config/ruledb/rules": [{"id": 1}, {"id": 2}],
        "/config/ruledb/who": [{"id": 1}],
        "/config/ruledb/what": [{"id": 1}, {"id": 2}, {"id": 3}],
        "/config/ruledb/when": [],
        "/config/ruledb/action/objects": [{"id": 1}],
    })

    out = server.pmg_ruledb_reset(confirm=False)

    assert out["status"] == "plan"
    assert out["blast_radius"][0] == "Proximo has NO undo for this; take pmg_backup_create first."
    toll = out["blast_radius"][1]
    assert "2 rules" in toll
    assert "1 who" in toll
    assert "3 what" in toll
    assert "0 when" in toll
    assert "1 action objects" in toll

    read_paths = {p for p, _ in pmg.gets}
    assert read_paths == set(_EMPTY_RULEDB_ROUTES)
    assert not pmg.posts


def test_ruledb_reset_dry_run_degrades_honestly_when_a_capture_read_fails(tmp_path, monkeypatch):
    """A capture-read failure must degrade to an honest note, not block the plan from rendering
    (the ceph.py _cmd_safety_note fail-open precedent — PMG may be partially unreachable and the
    plan still needs to preview the reset)."""
    _, pmg, _, _ = _wire(
        tmp_path, monkeypatch,
        get_routes={"/config/ruledb/rules": [{"id": 1}]},
        raise_on={"/config/ruledb/who"},
    )

    out = server.pmg_ruledb_reset(confirm=False)

    assert out["status"] == "plan"
    assert out["complete"] is False
    assert any("who_groups count capture failed" in note for note in out["blast_radius"])
    # the plan still renders, still HIGH, still leads with the no-undo line
    assert out["risk"] == "high"
    assert out["blast_radius"][0] == "Proximo has NO undo for this; take pmg_backup_create first."
    assert not pmg.posts


def test_ruledb_reset_confirm_true_still_executes_even_if_a_capture_read_failed(
    tmp_path, monkeypatch,
):
    """The PLAN's own capture failure must never block confirm=True from actually running the
    reset — CAPTURE is preview-only evidence, not a gate."""
    _, pmg, _, log = _wire(
        tmp_path, monkeypatch,
        get_routes={"/config/ruledb/rules": [{"id": 1}]},
        raise_on={"/config/ruledb/who"},
    )

    out = server.pmg_ruledb_reset(confirm=True)

    assert out["status"] == "ok"
    assert pmg.posts
    call_path, call_data = pmg.posts[-1]
    assert call_path == "/config/ruledb"
    assert call_data == {}
    entry = _confirmed_entry(log, "pmg_ruledb_reset", "ok")
    assert entry["detail"]["confirmed"] is True
