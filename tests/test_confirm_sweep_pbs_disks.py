"""Confirm=True sweep — PBS disk admin wrapper welds (src/proximo/tools/pbs_disks.py, Wave 2d).

Mirrors the `_wire()`/`_Pbs` idiom in tests/test_confirm_sweep_pbs_node.py (itself mirroring
tests/test_server_plan.py:110-131, re-used across every prior confirm-sweep module): `_svc` is
monkeypatched (the ONE shared audit ledger lives behind it — `_ledger()` reads `_svc()[3]`) and
`_pbs` is monkeypatched to a fake PbsBackend, matching how pbs_disks.py's tools never touch the
PVE ApiBackend. This file duplicates its own `_Pbs`/`_wire` rather than importing
test_confirm_sweep_pbs_node.py's — every confirm-sweep module in this repo is self-contained
(same convention: test_confirm_sweep_pbs.py and test_confirm_sweep_pbs_node.py each carry their
own copy too, no shared conftest fixture for this pattern).

Each confirm=True call proves the three welds:
  1. return shape — status is the EXECUTED shape ("ok"/"submitted"), never "plan";
  2. the fake PbsBackend captured the underlying call (verb + path + EXACT payload);
  3. the ledger recorded a confirmed mutation — structural asserts only, never exact prose.

Directory-delete is the one outlier proven separately below: PBS's own schema documents that
endpoint as SYNCHRONOUS (returns null, not a UPID) — outcome="ok", not "submitted", unlike every
other mutation in this module (all async task-UPID ops).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig


class _Pbs:
    """Path-aware fake PbsBackend: records every _get/_post/_put/_delete call."""

    def __init__(self):
        self.gets: list[tuple[str, dict | None]] = []
        self.posts: list[tuple[str, dict | None]] = []
        self.puts: list[tuple[str, dict | None]] = []
        self.deletes: list[tuple[str, dict | None]] = []

    def _get(self, path, params=None):
        self.gets.append((path, params))
        return {}

    def _post(self, path, data=None):
        self.posts.append((path, data))
        return "UPID:localhost:00000001:00000000:00000000:disk:sda:root@pam:"

    def _put(self, path, data=None):
        self.puts.append((path, data))
        return "UPID:localhost:00000001:00000000:00000000:disk:sda:root@pam:"

    def _delete(self, path, params=None):
        self.deletes.append((path, params))
        return None


class _Api:
    """Minimal PVE API stub — only needed so server._svc() resolves (the ONE shared ledger lives
    behind it); pbs_disks.py's tools never touch this backend."""

    def __init__(self):
        self.config = SimpleNamespace(node="pve")


def _wire(tmp_path, monkeypatch):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log,
    )
    api = _Api()
    pbs = _Pbs()
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
# PbsBackend and records a confirmed mutation".
# ---------------------------------------------------------------------------

_SWEEP_CASES = [
    pytest.param(
        "pbs_node_disk_wipe",
        dict(disk="sda1"),
        "submitted", "puts", "/nodes/localhost/disks/wipedisk",
        {"disk": "sda1"},
        id="disk_wipe",
    ),
    pytest.param(
        "pbs_node_disk_initgpt",
        dict(disk="sda"),
        "submitted", "posts", "/nodes/localhost/disks/initgpt",
        {"disk": "sda"},
        id="disk_initgpt",
    ),
    pytest.param(
        "pbs_node_disk_initgpt",
        dict(disk="sda", uuid="12345678-1234-1234-1234-123456789012"),
        "submitted", "posts", "/nodes/localhost/disks/initgpt",
        {"disk": "sda", "uuid": "12345678-1234-1234-1234-123456789012"},
        id="disk_initgpt_with_uuid",
    ),
    pytest.param(
        "pbs_node_disk_directory_create",
        dict(disk="sda", name="tank"),
        "submitted", "posts", "/nodes/localhost/disks/directory",
        {"disk": "sda", "name": "tank"},
        id="disk_directory_create_minimal",
    ),
    pytest.param(
        "pbs_node_disk_directory_create",
        dict(disk="sda", name="tank", filesystem="xfs", add_datastore=True, removable_datastore=True),
        "submitted", "posts", "/nodes/localhost/disks/directory",
        {"disk": "sda", "name": "tank", "filesystem": "xfs",
         "add-datastore": True, "removable-datastore": True},
        id="disk_directory_create_full",
    ),
    pytest.param(
        "pbs_node_disk_zfs_create",
        dict(devices="sda,sdb", name="tank", raidlevel="mirror"),
        "submitted", "posts", "/nodes/localhost/disks/zfs",
        {"devices": "sda,sdb", "name": "tank", "raidlevel": "mirror"},
        id="disk_zfs_create_minimal",
    ),
    pytest.param(
        "pbs_node_disk_zfs_create",
        dict(devices="sda,sdb", name="tank", raidlevel="mirror",
             ashift=13, compression="lz4", add_datastore=True),
        "submitted", "posts", "/nodes/localhost/disks/zfs",
        {"devices": "sda,sdb", "name": "tank", "raidlevel": "mirror",
         "ashift": 13, "compression": "lz4", "add-datastore": True},
        id="disk_zfs_create_full",
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
    _, pbs, _, log = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)

    out = fn(confirm=True, **kwargs)

    # weld 1: return shape is the EXECUTED shape, never "plan"
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


# ---------------------------------------------------------------------------
# pbs_node_disk_directory_delete — dedicated weld: SYNCHRONOUS on PBS (outcome="ok", never
# "submitted") and takes NO cleanup params (PBS's own schema exposes none) — unlike every other
# mutation in this module, which are all async task-UPID ops.
# ---------------------------------------------------------------------------

def test_directory_delete_confirm_is_synchronous_ok_not_submitted(tmp_path, monkeypatch):
    _, pbs, _, log = _wire(tmp_path, monkeypatch)

    out = server.pbs_node_disk_directory_delete(name="tank", confirm=True)

    assert out["status"] == "ok"
    assert out["status"] != "submitted"
    call_path, call_params = pbs.deletes[-1]
    assert call_path == "/nodes/localhost/disks/directory/tank"
    assert call_params is None

    entry = _confirmed_entry(log, "pbs_node_disk_directory_delete", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


# ---------------------------------------------------------------------------
# Reads — confirm the wrapper reaches the PbsBackend with the right path/params (no confirm= gate).
# ---------------------------------------------------------------------------

def test_disks_list_read_reaches_pbs_with_filters(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    server.pbs_node_disks_list(include_partitions=True, skipsmart=True, usage_type="unused")
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/nodes/localhost/disks/list"
    assert call_params == {"include-partitions": True, "skipsmart": True, "usage-type": "unused"}


def test_disk_smart_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    server.pbs_node_disk_smart(disk="sda", healthonly=True)
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/nodes/localhost/disks/smart"
    assert call_params == {"disk": "sda", "healthonly": True}


def test_disk_directory_list_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    server.pbs_node_disk_directory_list()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/nodes/localhost/disks/directory"
    assert call_params is None


def test_disk_zfs_list_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    server.pbs_node_disk_zfs_list()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/nodes/localhost/disks/zfs"
    assert call_params is None


def test_disk_zfs_get_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    server.pbs_node_disk_zfs_get(name="tank")
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/nodes/localhost/disks/zfs/tank"
    assert call_params is None
