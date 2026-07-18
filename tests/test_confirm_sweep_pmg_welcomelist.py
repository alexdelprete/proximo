"""Confirm=True sweep — PMG GLOBAL welcomelist (src/proximo/tools/pmg_welcomelist.py, Wave 8b).

Mirrors the `_wire()`/fake-backend template in `tests/test_confirm_sweep_pmg_ruledb_objects.py`
(itself mirroring `tests/test_confirm_sweep_pbs_s3.py`): `_svc` is monkeypatched (the ONE shared
audit ledger lives behind it) and `_pmg` is monkeypatched to a fake PmgBackend (`_Pmg`). This file
duplicates its own `_Pmg`/`_wire` rather than importing another confirm-sweep module's — same
self-contained convention every confirm-sweep module in this repo follows.

Wave 8b has NO secrets on this region (coordinator-verified, same as 8a — no digest, no
secret-shaped params anywhere in the 92-path/138-method region) so there is no raw-bytes-
never-in-ledger sweep to add here.

Covers:
  - the 2 new read tools (exact wire-path proof across all 8 typed families for the per-object
    GET; the aggregate list),
  - the 3 new mutations: exact-payload confirm=True proof for add (all 8 typed families — the
    field-mapping table, Fact #13) and update (a representative subset — the body-builder is
    shared with add so full re-coverage there would be redundant), dry-run-never-writes, and the
    CAPTURE-or-degrade update-plan behavior end-to-end through the full server wrapper (not just
    the bare plan factory already covered in tests/test_pmg_welcomelist.py); delete's generic
    (untyped) path and empty-body semantics,
  - the risk ladder through the SERVER wrapper (MEDIUM add/update, LOW delete — coordinator
    RULING 3),
  - a registration check: the 5 new tool names are present on the live FastMCP registry (this
    file's own analogue of test_server_pmg_wiring.py's hardcoded set, kept local to this new
    module rather than growing that file's giant literal set further).
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

    `get_return`: a single fixed value returned for ANY path not covered by `get_routes`.
    `get_routes`: path -> return value, for the update-plan CAPTURE test (the typed GET needs to
    answer with a specific "before" state).
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
        return 42  # PMG returns the new object's integer id

    def _put(self, path, data=None):
        self.puts.append((path, data))
        return None

    def _delete(self, path, params=None):
        self.deletes.append((path, params))
        return None


class _Api:
    """Minimal PVE API stub — only needed so server._svc() resolves (the ONE shared ledger lives
    behind it); pmg_welcomelist.py's tools never touch this backend."""

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
# Reads — exact wire-path proof.
# ---------------------------------------------------------------------------

_ALL_TYPES = ["email", "receiver", "domain", "receiver_domain", "regex", "receiver_regex", "ip", "network"]


@pytest.mark.parametrize("type_", _ALL_TYPES)
def test_object_get_reaches_pmg_at_expected_path(tmp_path, monkeypatch, type_):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch, get_return={"id": 1})
    server.pmg_welcomelist_object_get(type_=type_, id_="5")
    call_path, _ = pmg.gets[-1]
    assert call_path == f"/config/welcomelist/{type_}/5"
    assert not pmg.posts
    assert not pmg.puts
    assert not pmg.deletes


def test_objects_list_reaches_pmg_at_expected_path(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch, get_return=[{"id": 1}])
    server.pmg_welcomelist_objects_list()
    call_path, _ = pmg.gets[-1]
    assert call_path == "/config/welcomelist/objects"


def test_reads_are_audited_as_non_mutation(tmp_path, monkeypatch):
    _, _, _, log = _wire(tmp_path, monkeypatch, get_return={"id": 1})
    server.pmg_welcomelist_object_get(type_="email", id_="5")
    server.pmg_welcomelist_objects_list()
    for action in ("pmg_welcomelist_object_get", "pmg_welcomelist_objects_list"):
        entries = [e for e in _entries(log) if e["action"] == action]
        assert len(entries) == 1
        assert entries[0]["mutation"] is False


# ---------------------------------------------------------------------------
# pmg_welcomelist_object_add — exact-payload confirm=True proof, all 8 typed families
# (Fact #13's single-field-per-type mapping table).
# ---------------------------------------------------------------------------

_ADD_SWEEP_CASES = [
    pytest.param("email", dict(email="good@example.com"), "/config/welcomelist/email",
                 {"email": "good@example.com"}, id="add_email"),
    pytest.param("receiver", dict(email="good@example.com"), "/config/welcomelist/receiver",
                 {"email": "good@example.com"}, id="add_receiver"),
    pytest.param("domain", dict(domain="example.com"), "/config/welcomelist/domain",
                 {"domain": "example.com"}, id="add_domain"),
    pytest.param("receiver_domain", dict(domain="example.com"), "/config/welcomelist/receiver_domain",
                 {"domain": "example.com"}, id="add_receiver_domain"),
    pytest.param("regex", dict(regex=r".*@example\.com"), "/config/welcomelist/regex",
                 {"regex": r".*@example\.com"}, id="add_regex"),
    pytest.param("receiver_regex", dict(regex=r".*@example\.com"), "/config/welcomelist/receiver_regex",
                 {"regex": r".*@example\.com"}, id="add_receiver_regex"),
    pytest.param("ip", dict(ip="10.99.99.5"), "/config/welcomelist/ip",
                 {"ip": "10.99.99.5"}, id="add_ip"),
    pytest.param("network", dict(cidr="10.99.99.0/24"), "/config/welcomelist/network",
                 {"cidr": "10.99.99.0/24"}, id="add_network"),
]


@pytest.mark.parametrize("type_,kwargs,path,data_exact", _ADD_SWEEP_CASES)
def test_object_add_confirm_true_executes_forwards_and_records(
    tmp_path, monkeypatch, type_, kwargs, path, data_exact,
):
    _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_welcomelist_object_add(type_=type_, confirm=True, **kwargs)

    assert out["status"] == "ok"
    assert out["status"] != "plan"
    assert out["result"] == 42

    assert pmg.posts, "pmg_welcomelist_object_add confirm=True never reached pmg._post"
    call_path, call_data = pmg.posts[-1]
    assert call_path == path
    assert call_data == data_exact

    entry = _confirmed_entry(log, "pmg_welcomelist_object_add", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


def test_object_add_dry_run_never_posts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_welcomelist_object_add(type_="email", email="good@example.com", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.posts


def test_object_add_risk_is_medium(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    out = server.pmg_welcomelist_object_add(type_="email", email="good@example.com", confirm=False)
    assert out["risk"] == "medium"


def test_object_add_missing_required_field_errors_before_any_write(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(tmp_path, monkeypatch)
    with pytest.raises(ProximoError):
        server.pmg_welcomelist_object_add(type_="email", confirm=True)
    assert not pmg.posts
    entries = [e for e in _entries(log) if e["action"] == "pmg_welcomelist_object_add"]
    assert entries and entries[-1]["outcome"] == "error"


# ---------------------------------------------------------------------------
# pmg_welcomelist_object_update — exact-payload confirm=True proof (representative subset — the
# body-builder is shared with add, already fully covered there) + the CAPTURE-or-degrade plan
# proven end-to-end through the full server wrapper.
# ---------------------------------------------------------------------------

_UPDATE_SWEEP_CASES = [
    pytest.param("email", "5", dict(email="new@example.com"), "/config/welcomelist/email/5",
                 {"email": "new@example.com"}, id="update_email"),
    pytest.param("network", "9", dict(cidr="10.99.99.0/24"), "/config/welcomelist/network/9",
                 {"cidr": "10.99.99.0/24"}, id="update_network"),
]


@pytest.mark.parametrize("type_,id_,kwargs,path,data_exact", _UPDATE_SWEEP_CASES)
def test_object_update_confirm_true_executes_forwards_and_records(
    tmp_path, monkeypatch, type_, id_, kwargs, path, data_exact,
):
    _, pmg, _, log = _wire(tmp_path, monkeypatch, get_return={"id": int(id_)})
    out = server.pmg_welcomelist_object_update(type_=type_, id_=id_, confirm=True, **kwargs)

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    assert pmg.puts, "pmg_welcomelist_object_update confirm=True never reached pmg._put"
    call_path, call_data = pmg.puts[-1]
    assert call_path == path
    assert call_data == data_exact

    entry = _confirmed_entry(log, "pmg_welcomelist_object_update", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


def test_object_update_dry_run_never_puts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch, get_return={"id": 5})
    out = server.pmg_welcomelist_object_update(type_="email", id_="5", email="new@example.com", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.puts


def test_object_update_risk_is_medium(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch, get_return={"id": 5})
    out = server.pmg_welcomelist_object_update(type_="email", id_="5", email="new@example.com", confirm=False)
    assert out["risk"] == "medium"


def test_object_update_dry_run_captures_current_via_typed_get(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch, get_routes={
        "/config/welcomelist/email/5": {"id": 5, "email": "old@example.com"},
    })
    out = server.pmg_welcomelist_object_update(type_="email", id_="5", email="new@example.com", confirm=False)
    assert out["current"] == {"id": 5, "email": "old@example.com"}
    assert out["complete"] is True
    assert ("/config/welcomelist/email/5", None) in pmg.gets


def test_object_update_dry_run_degrades_honestly_when_capture_fails(tmp_path, monkeypatch):
    """A capture-read failure must degrade to an honest note, not block the plan from rendering —
    the ceph.py _cmd_safety_note fail-open precedent, mirrored from pmg.py's own W6a
    _ruledb_reset_capture_count idiom."""
    _, pmg, _, _ = _wire(tmp_path, monkeypatch, raise_on={"/config/welcomelist/email/5"})
    out = server.pmg_welcomelist_object_update(type_="email", id_="5", email="new@example.com", confirm=False)
    assert out["status"] == "plan"
    assert out["complete"] is False
    assert out["current"] == {}
    assert any("current-state capture failed" in note for note in out["blast_radius"])
    assert out["risk"] == "medium"
    assert not pmg.puts


def test_object_update_confirm_true_still_executes_even_if_capture_failed(tmp_path, monkeypatch):
    """CAPTURE is preview-only evidence, not a gate — confirm=True must still run the update."""
    _, pmg, _, log = _wire(tmp_path, monkeypatch, raise_on={"/config/welcomelist/email/5"})
    out = server.pmg_welcomelist_object_update(type_="email", id_="5", email="new@example.com", confirm=True)
    assert out["status"] == "ok"
    assert pmg.puts
    call_path, call_data = pmg.puts[-1]
    assert call_path == "/config/welcomelist/email/5"
    assert call_data == {"email": "new@example.com"}
    entry = _confirmed_entry(log, "pmg_welcomelist_object_update", "ok")
    assert entry["detail"]["confirmed"] is True


def test_object_update_missing_required_field_errors_before_any_write(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(tmp_path, monkeypatch, get_return={"id": 5})
    with pytest.raises(ProximoError):
        server.pmg_welcomelist_object_update(type_="email", id_="5", confirm=True)
    assert not pmg.puts
    entries = [e for e in _entries(log) if e["action"] == "pmg_welcomelist_object_update"]
    assert entries and entries[-1]["outcome"] == "error"


# ---------------------------------------------------------------------------
# pmg_welcomelist_object_delete — generic (untyped) path, empty-payload semantics, LOW risk.
# ---------------------------------------------------------------------------


def test_object_delete_confirm_true_reaches_generic_untyped_path(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_welcomelist_object_delete(id_="7", confirm=True)

    assert out["status"] == "ok"
    assert pmg.deletes, "pmg_welcomelist_object_delete confirm=True never reached pmg._delete"
    call_path, _ = pmg.deletes[-1]
    assert call_path == "/config/welcomelist/objects/7"

    entry = _confirmed_entry(log, "pmg_welcomelist_object_delete", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


def test_object_delete_falsy_id_survives_end_to_end(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_welcomelist_object_delete(id_="0", confirm=True)
    call_path, _ = pmg.deletes[-1]
    assert call_path == "/config/welcomelist/objects/0"


def test_object_delete_dry_run_never_deletes(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_welcomelist_object_delete(id_="7", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.deletes


def test_object_delete_risk_is_low(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    out = server.pmg_welcomelist_object_delete(id_="7", confirm=False)
    assert out["risk"] == "low"


# ---------------------------------------------------------------------------
# Registration — this new module's own analogue of test_server_pmg_wiring.py's hardcoded set.
# ---------------------------------------------------------------------------


async def test_welcomelist_tools_registered_with_fastmcp():
    names = {t.name for t in await server.mcp.list_tools()}
    expected = {
        "pmg_welcomelist_objects_list",
        "pmg_welcomelist_object_get",
        "pmg_welcomelist_object_add",
        "pmg_welcomelist_object_update",
        "pmg_welcomelist_object_delete",
    }
    assert expected <= names, f"missing from MCP surface: {expected - names}"
