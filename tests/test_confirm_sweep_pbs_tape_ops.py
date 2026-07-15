"""Confirm=True sweep — PBS tape drive + changer OPERATIONS wrapper welds
(src/proximo/tools/pbs_tape_ops.py, Wave 4c) + the secret-never-in-ledger promise for
restore-key's `password` (module docstring fact #10).

Mirrors the `_wire()`/`_Pbs` idiom in tests/test_confirm_sweep_pbs_tape_media.py (itself
mirroring tests/test_server_plan.py:110-131): `_svc` is monkeypatched (the ONE shared audit
ledger lives behind it — `_ledger()` reads `_svc()[3]`) and `_pbs` is monkeypatched to a fake
PbsBackend. This file duplicates its own `_Pbs`/`_wire` rather than importing another
confirm-sweep module's — same self-contained convention every confirm-sweep module in this repo
follows.

Each homogeneous confirm=True call proves the three welds:
  1. return shape — outcome is EXACTLY what the schema declares per endpoint (module docstring
     fact #2): "submitted" for the 9 UPID-returning ops, "ok" for the 4 null-returning ops
     (load-slot, restore-key, transfer — plus every read, which never gates on confirm at all);
  2. the fake PbsBackend captured the underlying call (verb + path + EXACT payload, full dict
     equality — no subset matching);
  3. the ledger recorded a confirmed mutation — structural asserts only, never exact prose.

THE HEADLINE WELD (mirrors tests/test_confirm_sweep_pbs_tape_media.py's identical section):
restore-key's `password` must never appear raw in the on-disk ledger — read RAW BYTES, not
parsed JSON — while the real PBS call (the fake's captured payload) DOES carry the raw value,
because the restore attempt must actually work.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig

_UPID = "UPID:node1:00000001:00000000:00000000:tapeop:drive1:root@pam:"


class _Pbs:
    """Path-aware fake PbsBackend: records every _get/_post/_put/_delete call."""

    def __init__(self, get_return=None, post_return=None, put_return=None):
        self._get_return = get_return
        self._post_return = post_return
        self._put_return = put_return
        self.gets: list[tuple[str, dict | None]] = []
        self.posts: list[tuple[str, dict | None]] = []
        self.puts: list[tuple[str, dict | None]] = []
        self.deletes: list[tuple[str, dict | None]] = []

    def _get(self, path, params=None):
        self.gets.append((path, params))
        return self._get_return

    def _post(self, path, data=None):
        self.posts.append((path, data))
        return self._post_return

    def _put(self, path, data=None):
        self.puts.append((path, data))
        return self._put_return

    def _delete(self, path, params=None):
        self.deletes.append((path, params))
        return None


class _Api:
    """Minimal PVE API stub — only needed so server._svc() resolves (the ONE shared ledger lives
    behind it); pbs_tape_ops.py's tools never touch this backend."""

    def __init__(self):
        self.config = SimpleNamespace(node="pve")


def _wire(tmp_path, monkeypatch, get_return=None, post_return=None, put_return=None):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log,
    )
    api = _Api()
    pbs = _Pbs(get_return=get_return, post_return=post_return, put_return=put_return)
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
# PbsBackend and records a confirmed mutation with the SCHEMA-CORRECT outcome". Outcomes are
# module docstring fact #2, checked endpoint by endpoint, not assumed uniform.
# ---------------------------------------------------------------------------

_SWEEP_CASES = [
    pytest.param(
        "pbs_tape_drive_load_media",
        dict(drive="drive1", label_text="scratch01"),
        "submitted", "posts", "/tape/drive/drive1/load-media",
        {"label-text": "scratch01"},
        id="load_media",
    ),
    pytest.param(
        "pbs_tape_drive_load_slot",
        dict(drive="drive1", source_slot=3),
        "ok", "posts", "/tape/drive/drive1/load-slot",
        {"source-slot": 3},
        id="load_slot",
    ),
    pytest.param(
        "pbs_tape_drive_unload",
        dict(drive="drive1", target_slot=5),
        "submitted", "posts", "/tape/drive/drive1/unload",
        {"target-slot": 5},
        id="unload",
    ),
    pytest.param(
        "pbs_tape_drive_eject",
        dict(drive="drive1"),
        "submitted", "posts", "/tape/drive/drive1/eject-media",
        {},
        id="eject",
    ),
    pytest.param(
        "pbs_tape_drive_rewind",
        dict(drive="drive1"),
        "submitted", "posts", "/tape/drive/drive1/rewind",
        {},
        id="rewind",
    ),
    pytest.param(
        "pbs_tape_drive_clean",
        dict(drive="drive1"),
        "submitted", "puts", "/tape/drive/drive1/clean",
        {},
        id="clean",
    ),
    pytest.param(
        "pbs_tape_drive_inventory_update",
        dict(drive="drive1", catalog=True, read_all_labels=False),
        "submitted", "puts", "/tape/drive/drive1/inventory",
        {"catalog": True, "read-all-labels": False},
        id="inventory_update",
    ),
    pytest.param(
        "pbs_tape_drive_label_media",
        dict(drive="drive1", label_text="newlabel01", pool="pool1"),
        "submitted", "posts", "/tape/drive/drive1/label-media",
        {"label-text": "newlabel01", "pool": "pool1"},
        id="label_media",
    ),
    pytest.param(
        "pbs_tape_drive_barcode_label_media",
        dict(drive="drive1", pool="pool1"),
        "submitted", "posts", "/tape/drive/drive1/barcode-label-media",
        {"pool": "pool1"},
        id="barcode_label_media",
    ),
    pytest.param(
        "pbs_tape_drive_format",
        dict(drive="drive1", fast=False, label_text="scratch01"),
        "submitted", "posts", "/tape/drive/drive1/format-media",
        {"fast": False, "label-text": "scratch01"},
        id="format",
    ),
    pytest.param(
        "pbs_tape_drive_catalog",
        dict(drive="drive1", force=True, scan=False),
        "submitted", "posts", "/tape/drive/drive1/catalog",
        {"force": True, "scan": False},
        id="catalog",
    ),
    pytest.param(
        "pbs_tape_changer_transfer",
        dict(name="changer1", from_slot=1, to_slot=5),
        "ok", "posts", "/tape/changer/changer1/transfer",
        {"from": 1, "to": 5},
        id="changer_transfer",
    ),
]


@pytest.mark.parametrize(
    "tool_name,kwargs,expected_status,capture,path,data_exact", _SWEEP_CASES,
)
def test_confirm_true_executes_forwards_and_records(
    tmp_path, monkeypatch, tool_name, kwargs, expected_status, capture, path, data_exact,
):
    """confirm=True executes (never 'plan'), the fake captured the forwarded call, and the ledger
    recorded a confirmed mutation with the SCHEMA-correct outcome — the three welds every
    confirm-sweep module proves."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch, post_return=_UPID, put_return=_UPID)
    fn = getattr(server, tool_name)

    out = fn(confirm=True, **kwargs)

    # weld 1: return shape — matches the schema's own outcome for this specific endpoint.
    assert out["status"] == expected_status
    assert out["status"] != "plan"

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


def test_load_slot_returns_ok_not_submitted_even_when_fake_returns_upid_shaped_string(
    tmp_path, monkeypatch,
):
    """module docstring fact #2 — the one surprise on this plane. Even though the fake's
    post_return is set to a UPID-shaped string (as it is for every other case above), load-slot's
    OWN backend function discards the return value entirely (the live schema declares null) — the
    wrapper's outcome is a FIXED 'ok' literal, not schema/return-shape-derived."""
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, post_return=_UPID)
    out = server.pbs_tape_drive_load_slot(drive="drive1", source_slot=1, confirm=True)
    assert out["status"] == "ok"
    assert out["result"] is None


def test_restore_key_returns_ok_result_none(tmp_path, monkeypatch):
    _, pbs, _, log = _wire(tmp_path, monkeypatch, post_return=_UPID)
    out = server.pbs_tape_drive_restore_key(
        drive="drive1", password="placeholder-restore-pw", confirm=True,
    )
    assert out["status"] == "ok"
    assert out["result"] is None
    call_path, call_data = pbs.posts[-1]
    assert call_path == "/tape/drive/drive1/restore-key"
    assert call_data == {"password": "placeholder-restore-pw"}


def test_unload_omits_target_slot_when_not_given(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, post_return=_UPID)
    out = server.pbs_tape_drive_unload(drive="drive1", confirm=True)
    assert out["status"] == "submitted"
    call_path, call_data = pbs.posts[-1]
    assert call_path == "/tape/drive/drive1/unload"
    assert call_data == {}


# ---------------------------------------------------------------------------
# Dry-run (confirm=False) — proves the PLAN path never touches the PbsBackend's write verbs.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "tool_name,kwargs",
    [
        ("pbs_tape_drive_load_media", dict(drive="drive1", label_text="scratch01")),
        ("pbs_tape_drive_load_slot", dict(drive="drive1", source_slot=3)),
        ("pbs_tape_drive_unload", dict(drive="drive1")),
        ("pbs_tape_drive_eject", dict(drive="drive1")),
        ("pbs_tape_drive_rewind", dict(drive="drive1")),
        ("pbs_tape_drive_clean", dict(drive="drive1")),
        ("pbs_tape_drive_inventory_update", dict(drive="drive1")),
        ("pbs_tape_drive_label_media", dict(drive="drive1", label_text="newlabel01")),
        ("pbs_tape_drive_barcode_label_media", dict(drive="drive1")),
        ("pbs_tape_drive_format", dict(drive="drive1")),
        ("pbs_tape_drive_catalog", dict(drive="drive1")),
        ("pbs_tape_drive_restore_key", dict(drive="drive1", password="sentinel-pw")),
        ("pbs_tape_changer_transfer", dict(name="changer1", from_slot=1, to_slot=5)),
    ],
)
def test_dry_run_never_reaches_write_verbs(tmp_path, monkeypatch, tool_name, kwargs):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)
    out = fn(confirm=False, **kwargs)
    assert out["status"] == "plan"
    assert not pbs.posts
    assert not pbs.puts
    assert not pbs.deletes


# ---------------------------------------------------------------------------
# Reads — confirm each wrapper reaches the PbsBackend with the right path (no confirm= gate).
# ---------------------------------------------------------------------------

def test_drive_status_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={})
    server.pbs_tape_drive_status(drive="drive1")
    call_path, _ = pbs.gets[-1]
    assert call_path == "/tape/drive/drive1/status"


def test_drive_read_label_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"label-text": "scratch01"})
    server.pbs_tape_drive_read_label(drive="drive1")
    call_path, _ = pbs.gets[-1]
    assert call_path == "/tape/drive/drive1/read-label"


def test_drive_cartridge_memory_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_tape_drive_cartridge_memory(drive="drive1")
    call_path, _ = pbs.gets[-1]
    assert call_path == "/tape/drive/drive1/cartridge-memory"


def test_drive_volume_statistics_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={})
    server.pbs_tape_drive_volume_statistics(drive="drive1")
    call_path, _ = pbs.gets[-1]
    assert call_path == "/tape/drive/drive1/volume-statistics"


def test_drive_inventory_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_tape_drive_inventory(drive="drive1")
    call_path, _ = pbs.gets[-1]
    assert call_path == "/tape/drive/drive1/inventory"


def test_changer_status_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_tape_changer_status(name="changer1")
    call_path, _ = pbs.gets[-1]
    assert call_path == "/tape/changer/changer1/status"


def test_reads_never_mutation_in_ledger(tmp_path, monkeypatch):
    _, _, _, log = _wire(tmp_path, monkeypatch, get_return={})
    server.pbs_tape_drive_status(drive="drive1")
    entries = [e for e in _entries(log) if e["action"] == "pbs_tape_drive_status"]
    assert entries
    assert all(not e["mutation"] for e in entries)


# ---------------------------------------------------------------------------
# THE HEADLINE WELD — secret-never-in-ledger, restore-key's `password`. Sentinel values are
# low-entropy/all-lowercase/hyphenated per this repo's fixture-sentinel discipline (CLAUDE.md:
# "Test fixtures must use low-entropy sentinel values" — a mixed-case sentinel already failed the
# public gitleaks CI scan on v0.13.0).
# ---------------------------------------------------------------------------

_PASSWORD_SENTINEL = "sentinel-tape-restore-key-password-value"  # noqa: S105


def test_restore_key_confirm_never_writes_password_to_ledger(tmp_path, monkeypatch):
    """weld 1: the operator's real PBS call DOES carry the raw password (the restore attempt must
    actually work) — the fake captured it. weld 2: read the ledger file RAW (bytes, not parsed
    JSON) and assert the secret substring appears NOWHERE — not in the 'planned' entry, not in the
    'confirmed' entry, not anywhere in the file."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch, post_return=None)

    out = server.pbs_tape_drive_restore_key(
        drive="drive1", password=_PASSWORD_SENTINEL, confirm=True,
    )

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    # weld 1: the fake captured the underlying POST with the RAW password.
    assert pbs.posts, "pbs_tape_drive_restore_key confirm=True never reached pbs._post"
    call_path, call_data = pbs.posts[-1]
    assert call_path == "/tape/drive/drive1/restore-key"
    assert call_data["password"] == _PASSWORD_SENTINEL

    # weld 2: ledger entries (parsed JSON) never carry the sentinel.
    entries = _entries(log)
    assert entries, "no ledger entries recorded at all"
    assert all(_PASSWORD_SENTINEL not in json.dumps(e) for e in entries)
    entry = _confirmed_entry(log, "pbs_tape_drive_restore_key", "ok")
    assert "password" not in entry["detail"]

    # THE HEADLINE WELD: read the ledger file RAW (bytes) — the secret must appear NOWHERE in the
    # on-disk ledger, across every entry, not just the ones inspected above as parsed JSON.
    raw = open(log, "rb").read()
    assert _PASSWORD_SENTINEL.encode("utf-8") not in raw


def test_restore_key_dry_run_plan_never_carries_secret(tmp_path, monkeypatch):
    """Even confirm=False (the returned PLAN dict itself, not just the ledger) must never carry a
    raw secret — the plan is returned directly to the calling agent."""
    _, _, _, _ = _wire(tmp_path, monkeypatch)

    out = server.pbs_tape_drive_restore_key(
        drive="drive1", password=_PASSWORD_SENTINEL, confirm=False,
    )

    assert out["status"] == "plan"
    dumped = json.dumps(out)
    assert _PASSWORD_SENTINEL not in dumped
    assert "[redacted]" in dumped
