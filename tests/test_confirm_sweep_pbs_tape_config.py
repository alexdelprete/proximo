"""Confirm=True sweep — PBS tape hardware config wrapper welds
(src/proximo/tools/pbs_tape_config.py, Wave 4a).

Mirrors the `_wire()`/`_Pbs` idiom in tests/test_confirm_sweep_pbs_acme.py (itself mirroring
tests/test_server_plan.py:110-131): `_svc` is monkeypatched (the ONE shared audit ledger lives
behind it — `_ledger()` reads `_svc()[3]`) and `_pbs` is monkeypatched to a fake PbsBackend. This
file duplicates its own `_Pbs`/`_wire` rather than importing another confirm-sweep module's —
same self-contained convention every confirm-sweep module in this repo follows.

Each homogeneous confirm=True call proves the three welds:
  1. return shape — status is "ok" (never "plan") — every mutation on this plane is SYNCHRONOUS
     per the live schema (module docstring fact #6), unlike a PVE guest/storage mutation;
  2. the fake PbsBackend captured the underlying call (verb + path + EXACT payload, full dict
     equality — no subset matching);
  3. the ledger recorded a confirmed mutation — structural asserts only, never exact prose.

No secret-shaped field exists on this plane (module docstring fact #7) — no "never in ledger"
sweep is needed here, unlike test_confirm_sweep_pbs_notifications.py / test_confirm_sweep_
pbs_acme.py.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.backends import ProximoError
from proximo.config import ProximoConfig


class _Pbs:
    """Path-aware fake PbsBackend: records every _get/_post/_put/_delete call."""

    def __init__(self, get_return=None):
        self._get_return = get_return
        self.gets: list[tuple[str, dict | None]] = []
        self.posts: list[tuple[str, dict | None]] = []
        self.puts: list[tuple[str, dict | None]] = []
        self.deletes: list[tuple[str, dict | None]] = []

    def _get(self, path, params=None):
        self.gets.append((path, params))
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
    behind it); pbs_tape_config.py's tools never touch this backend."""

    def __init__(self):
        self.config = SimpleNamespace(node="pve")


def _wire(tmp_path, monkeypatch, get_return=None):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log,
    )
    api = _Api()
    pbs = _Pbs(get_return=get_return)
    exec_ = SimpleNamespace()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, exec_, ledger))
    monkeypatch.setattr(server, "_pbs", lambda: (SimpleNamespace(), pbs))
    return cfg, pbs, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _confirmed_entry(log: str, action: str, outcome: str) -> dict:
    entries = [e for e in _entries(log) if e["action"] == action and e["outcome"] == outcome]
    assert len(entries) == 1, f"expected exactly one {action!r}/{outcome!r} ledger entry, got {entries}"
    return entries[0]


# ---------------------------------------------------------------------------
# Homogeneous sweep — table-driven: "confirm=True reaches the right verb/path/data on the
# PbsBackend and records a confirmed mutation". Every mutation on this plane returns null
# (synchronous) per the live schema — outcome is ALWAYS "ok", never "submitted".
# ---------------------------------------------------------------------------

_SWEEP_CASES = [
    pytest.param(
        "pbs_tape_drive_create",
        dict(name="drive1", path="/dev/sg0", changer="chg1", changer_drivenum=2),
        "ok", "posts", "/config/drive",
        {"name": "drive1", "path": "/dev/sg0", "changer": "chg1", "changer-drivenum": 2},
        id="drive_create",
    ),
    pytest.param(
        "pbs_tape_drive_update",
        dict(name="drive1", path="/dev/sg1", changer="chg2", changer_drivenum=3,
             digest="d" * 64, delete=["changer-drivenum"]),
        "ok", "puts", "/config/drive/drive1",
        {"path": "/dev/sg1", "changer": "chg2", "changer-drivenum": 3, "digest": "d" * 64,
         "delete": ["changer-drivenum"]},
        id="drive_update",
    ),
    pytest.param(
        "pbs_tape_drive_delete",
        dict(name="drive1"),
        "ok", "deletes", "/config/drive/drive1",
        None,
        id="drive_delete",
    ),
    pytest.param(
        "pbs_tape_changer_create",
        dict(name="chg1", path="/dev/sg4", eject_before_unload=True, export_slots="1,2,3"),
        "ok", "posts", "/config/changer",
        {"name": "chg1", "path": "/dev/sg4", "eject-before-unload": True,
         "export-slots": "1,2,3"},
        id="changer_create",
    ),
    pytest.param(
        "pbs_tape_changer_update",
        dict(name="chg1", path="/dev/sg5", eject_before_unload=False, export_slots="4,5",
             digest="e" * 64, delete=["export-slots"]),
        "ok", "puts", "/config/changer/chg1",
        {"path": "/dev/sg5", "eject-before-unload": False, "export-slots": "4,5",
         "digest": "e" * 64, "delete": ["export-slots"]},
        id="changer_update",
    ),
    pytest.param(
        "pbs_tape_changer_delete",
        dict(name="chg1"),
        "ok", "deletes", "/config/changer/chg1",
        None,
        id="changer_delete",
    ),
]


@pytest.mark.parametrize(
    "tool_name,kwargs,expected_status,capture,path,data_exact", _SWEEP_CASES,
)
def test_confirm_true_executes_forwards_and_records(
    tmp_path, monkeypatch, tool_name, kwargs, expected_status, capture, path, data_exact,
):
    """confirm=True executes (never 'plan'), the fake captured the forwarded call, and the ledger
    recorded a confirmed mutation — the three welds every confirm-sweep module proves."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch, get_return={"name": "sentinel"})
    fn = getattr(server, tool_name)

    out = fn(confirm=True, **kwargs)

    # weld 1: return shape — always "ok" on this plane (every mutation returns null, synchronous)
    assert out["status"] == expected_status
    assert out["status"] != "plan"
    assert out["status"] != "submitted"

    # weld 2: the fake captured the underlying call at the expected verb + path, with the EXACT
    # forwarded payload (full dict equality — an accidental extra field now fails).
    calls = getattr(pbs, capture)
    assert calls, f"{tool_name} confirm=True never reached pbs.{capture}"
    call_path, call_data = calls[-1]
    assert call_path == path
    assert call_data == data_exact

    # weld 3: ledger structural asserts — never exact prose
    entry = _confirmed_entry(log, tool_name, expected_status)
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


def test_drive_create_no_optional_fields_sends_minimal_payload(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_tape_drive_create(name="drive1", path="/dev/sg0", confirm=True)
    assert out["status"] == "ok"
    _, data = pbs.posts[-1]
    assert data == {"name": "drive1", "path": "/dev/sg0"}


def test_changer_create_no_optional_fields_sends_minimal_payload(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_tape_changer_create(name="chg1", path="/dev/sg4", confirm=True)
    assert out["status"] == "ok"
    _, data = pbs.posts[-1]
    assert data == {"name": "chg1", "path": "/dev/sg4"}


def test_drive_update_no_fields_sends_empty_payload(tmp_path, monkeypatch):
    """No kwargs beyond name/confirm: the PUT still fires but the payload is an empty dict —
    proves no phantom fields are forwarded when nothing was asked to change."""
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "drive1"})
    out = server.pbs_tape_drive_update(name="drive1", confirm=True)
    assert out["status"] == "ok"
    _, data = pbs.puts[-1]
    assert data == {}


def test_changer_update_no_fields_sends_empty_payload(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "chg1"})
    out = server.pbs_tape_changer_update(name="chg1", confirm=True)
    assert out["status"] == "ok"
    _, data = pbs.puts[-1]
    assert data == {}


# ---------------------------------------------------------------------------
# Dry-run (confirm=False) — proves the PLAN path never touches the PbsBackend's write verbs, and
# that update/delete plans CAPTURE current config via a live read.
# ---------------------------------------------------------------------------

def test_drive_create_dry_run_never_posts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_tape_drive_create(name="drive1", path="/dev/sg0", confirm=False)
    assert out["status"] == "plan"
    assert not pbs.posts


def test_changer_create_dry_run_never_posts(tmp_path, monkeypatch):
    """Review finding (Wave 4a): the changer resource was systematically less tested than the
    near-identical drive resource — this closes the missing dry-run weld."""
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_tape_changer_create(name="chg1", path="/dev/sg4", confirm=False)
    assert out["status"] == "plan"
    assert not pbs.posts


def test_drive_update_empty_delete_confirm_rejected(tmp_path, monkeypatch):
    """Wave 5b review finding 1 corrects the Wave 4a claim above: delete=[] is REJECTED
    (ProximoError), not sent — httpx's form encoding drops an empty-list value entirely, so
    the OLD assertion here ("call_data == {'delete': []}") was never what actually reached the
    wire. _plan() runs before the confirm=True gate, so the error surfaces through the wrapper
    as a raised exception (mirrors how every other validator failure behaves at this layer —
    _plan()/_audited() both re-raise rather than returning a status="error" envelope) — proving
    plan and execute AGREE by both refusing, not by both (dishonestly) sending an empty delete."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch, get_return={"name": "drive1"})
    with pytest.raises(ProximoError):
        server.pbs_tape_drive_update(name="drive1", delete=[], confirm=True)
    assert not pbs.puts


def test_drive_update_dry_run_reads_but_never_puts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "drive1", "path": "/dev/sg0"})
    out = server.pbs_tape_drive_update(name="drive1", path="/dev/sg1", confirm=False)
    assert out["status"] == "plan"
    assert out["current"] == {"name": "drive1", "path": "/dev/sg0"}
    assert not pbs.puts


def test_drive_delete_dry_run_reads_but_never_deletes(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "drive1", "path": "/dev/sg0"})
    out = server.pbs_tape_drive_delete(name="drive1", confirm=False)
    assert out["status"] == "plan"
    assert out["current"] == {"name": "drive1", "path": "/dev/sg0"}
    assert not pbs.deletes


def test_changer_update_empty_delete_confirm_rejected(tmp_path, monkeypatch):
    """Changer mirror of test_drive_update_empty_delete_confirm_rejected (Wave 5b review finding 1)."""
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "chg1"})
    with pytest.raises(ProximoError):
        server.pbs_tape_changer_update(name="chg1", delete=[], confirm=True)
    assert not pbs.puts


def test_changer_update_dry_run_reads_but_never_puts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "chg1", "path": "/dev/sg4"})
    out = server.pbs_tape_changer_update(name="chg1", path="/dev/sg5", confirm=False)
    assert out["status"] == "plan"
    assert out["current"] == {"name": "chg1", "path": "/dev/sg4"}
    assert not pbs.puts


def test_changer_delete_dry_run_reads_but_never_deletes(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "chg1", "path": "/dev/sg4"})
    out = server.pbs_tape_changer_delete(name="chg1", confirm=False)
    assert out["status"] == "plan"
    assert out["current"] == {"name": "chg1", "path": "/dev/sg4"}
    assert not pbs.deletes


# ---------------------------------------------------------------------------
# Reads — confirm the wrapper reaches the PbsBackend with the right path/params (no confirm=
# gate).
# ---------------------------------------------------------------------------

def test_drive_list_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_tape_drive_list()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/config/drive"
    assert call_params is None


def test_drive_get_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "drive1"})
    server.pbs_tape_drive_get(name="drive1")
    call_path, _ = pbs.gets[-1]
    assert call_path == "/config/drive/drive1"


def test_changer_list_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_tape_changer_list()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/config/changer"
    assert call_params is None


def test_changer_get_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "chg1"})
    server.pbs_tape_changer_get(name="chg1")
    call_path, _ = pbs.gets[-1]
    assert call_path == "/config/changer/chg1"


def test_scan_drives_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_tape_scan_drives()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/tape/scan-drives"
    assert call_params is None


def test_scan_changers_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_tape_scan_changers()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/tape/scan-changers"
    assert call_params is None
