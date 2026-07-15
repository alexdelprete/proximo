"""Confirm=True sweep — PBS tape media CATALOG + tape-backup JOBS + backup/restore wrapper welds
(src/proximo/tools/pbs_tape_jobs.py, Wave 4d — CLOSES Wave 4: PBS tape).

Mirrors the `_wire()`/`_Pbs` idiom in tests/test_confirm_sweep_pbs_tape_media.py /
test_confirm_sweep_pbs_tape_ops.py (itself mirroring tests/test_server_plan.py:110-131): `_svc`
is monkeypatched (the ONE shared audit ledger lives behind it — `_ledger()` reads `_svc()[3]`)
and `_pbs` is monkeypatched to a fake PbsBackend. This file duplicates its own `_Pbs`/`_wire`
rather than importing another confirm-sweep module's — same self-contained convention every
confirm-sweep module in this repo follows.

THE HEADLINE WELD (per this wave's explicit brief): `pbs_tape_media_destroy` wraps
`GET /tape/media/destroy` — a GET verb that PERMANENTLY DESTROYS a media catalog record. This
file proves, with a dedicated test, that:
  1. confirm=False NEVER issues the GET at all — the dry-run PLAN path never touches the fake's
     `_get` (the plan factory is PURE, so not even a probe read happens);
  2. confirm=True issues EXACTLY ONE GET to `/tape/media/destroy` with the EXACT forwarded
     params — full dict equality, proving the verb-independent gating (PLAN + confirm, identical
     to every POST/PUT/DELETE mutation on this server) does not change what's actually sent over
     the wire.

Each homogeneous confirm=True call proves the three welds every confirm-sweep module proves:
  1. return shape — status matches the documented outcome (mostly "ok"; "submitted" for the two
     UPID-returning ops, pbs_tape_backup/pbs_tape_restore — module docstring fact #2 also means
     pbs_tape_backup_job_run stays "ok" despite doing real work, a genuine schema quirk);
  2. the fake PbsBackend captured the underlying call (verb + path + EXACT payload, full dict
     equality — no subset matching);
  3. the ledger recorded a confirmed mutation — structural asserts only, never exact prose.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.backends import ProximoError
from proximo.config import ProximoConfig

_UUID = "12345678-1234-1234-1234-123456789abc"
_UPID = "UPID:node1:00000001:00000000:00000000:taperestore:store1:root@pam:"


class _Pbs:
    """Path-aware fake PbsBackend: records every _get/_post/_put/_delete call."""

    def __init__(self, get_return=None, post_return=None):
        self._get_return = get_return
        self._post_return = post_return
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
        return None

    def _delete(self, path, params=None):
        self.deletes.append((path, params))
        return None


class _Api:
    """Minimal PVE API stub — only needed so server._svc() resolves (the ONE shared ledger lives
    behind it); pbs_tape_jobs.py's tools never touch this backend."""

    def __init__(self):
        self.config = SimpleNamespace(node="pve")


def _wire(tmp_path, monkeypatch, get_return=None, post_return=None):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log,
    )
    api = _Api()
    pbs = _Pbs(get_return=get_return, post_return=post_return)
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
# THE HEADLINE WELD — pbs_tape_media_destroy: GET verb, gated exactly like a mutation.
# ---------------------------------------------------------------------------

def test_media_destroy_dry_run_never_issues_the_get(tmp_path, monkeypatch):
    """confirm=False must NEVER touch the PbsBackend at all — the plan factory is PURE, so even
    a probe read never happens, let alone the real destroy GET."""
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_tape_media_destroy(label_text="tape1", confirm=False)
    assert out["status"] == "plan"
    assert pbs.gets == []


def test_media_destroy_confirm_true_issues_exactly_one_get_with_exact_params(tmp_path, monkeypatch):
    """confirm=True issues EXACTLY ONE GET /tape/media/destroy with the EXACT forwarded params —
    full dict equality. This proves the verb-independent gating (this codebase's PLAN+confirm
    funnel) does not alter the real wire call: it is still a genuine HTTP GET, just gated like
    every other mutation."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch)
    out = server.pbs_tape_media_destroy(label_text="tape1", uuid=_UUID, force=True, confirm=True)
    assert out["status"] == "ok"
    assert out["status"] != "plan"
    assert len(pbs.gets) == 1, f"expected exactly one GET, got {pbs.gets}"
    call_path, call_params = pbs.gets[0]
    assert call_path == "/tape/media/destroy"
    assert call_params == {"label-text": "tape1", "uuid": _UUID, "force": True}
    entry = _confirmed_entry(log, "pbs_tape_media_destroy", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


def test_media_destroy_neither_identifier_never_reaches_pbs(tmp_path, monkeypatch):
    """The "at least one of label_text/uuid" rail fires at PLAN time — before any API call,
    confirm=True or not."""
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    with pytest.raises(Exception):  # noqa: B017 — ProximoError, re-raised through _plan
        server.pbs_tape_media_destroy(confirm=True)
    assert pbs.gets == []


# ---------------------------------------------------------------------------
# Homogeneous sweep — table-driven: "confirm=True reaches the right verb/path/data on the
# PbsBackend and records a confirmed mutation".
# ---------------------------------------------------------------------------

_SWEEP_CASES = [
    pytest.param(
        "pbs_tape_media_status_set",
        dict(uuid=_UUID, status="retired"),
        "ok", "posts", f"/tape/media/list/{_UUID}/status",
        {"status": "retired"},
        id="media_status_set",
    ),
    pytest.param(
        "pbs_tape_media_move",
        dict(uuid=_UUID, vault_name="offsite1"),
        "ok", "posts", "/tape/media/move",
        {"uuid": _UUID, "vault-name": "offsite1"},
        id="media_move",
    ),
    pytest.param(
        "pbs_tape_backup_job_create",
        dict(job_id="job1", drive="drive1", pool="pool1", store="store1"),
        "ok", "posts", "/config/tape-backup-job",
        {"id": "job1", "drive": "drive1", "pool": "pool1", "store": "store1"},
        id="job_create",
    ),
    pytest.param(
        "pbs_tape_backup_job_update",
        dict(job_id="job1", schedule="weekly", delete=["comment"]),
        "ok", "puts", "/config/tape-backup-job/job1",
        {"schedule": "weekly", "delete": ["comment"]},
        id="job_update",
    ),
    pytest.param(
        "pbs_tape_backup_job_delete",
        dict(job_id="job1"),
        "ok", "deletes", "/config/tape-backup-job/job1",
        {},
        id="job_delete",
    ),
    pytest.param(
        "pbs_tape_backup_job_run",
        dict(job_id="job1"),
        "ok", "posts", "/tape/backup/job1",
        {},
        id="job_run",
    ),
    pytest.param(
        "pbs_tape_backup",
        dict(drive="drive1", pool="pool1", store="store1"),
        "submitted", "posts", "/tape/backup",
        {"drive": "drive1", "pool": "pool1", "store": "store1"},
        id="one_off_backup",
    ),
    pytest.param(
        "pbs_tape_restore",
        dict(drive="drive1", media_set=_UUID, store="store1"),
        "submitted", "posts", "/tape/restore",
        {"drive": "drive1", "media-set": _UUID, "store": "store1"},
        id="restore",
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
    _, pbs, _, log = _wire(
        tmp_path, monkeypatch,
        get_return={"id": "job1", "drive": "drive1", "pool": "pool1", "store": "store1"},
        post_return=_UPID,
    )
    fn = getattr(server, tool_name)

    out = fn(confirm=True, **kwargs)

    # weld 1: return shape
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
# Dry-run (confirm=False) — proves the PLAN path never touches the PbsBackend's write verbs.
# All plan factories on this module are PURE (module docstring's Design note) except the two
# CONFIG job update/delete plans, which CAPTURE via a live GET.
# ---------------------------------------------------------------------------

def test_media_status_set_dry_run_never_posts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_tape_media_status_set(uuid=_UUID, status="full", confirm=False)
    assert out["status"] == "plan"
    assert not pbs.posts


def test_media_move_dry_run_never_posts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_tape_media_move(uuid=_UUID, confirm=False)
    assert out["status"] == "plan"
    assert not pbs.posts


def test_job_create_dry_run_never_posts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_tape_backup_job_create(
        job_id="job1", drive="drive1", pool="pool1", store="store1", confirm=False,
    )
    assert out["status"] == "plan"
    assert not pbs.posts


def test_job_update_dry_run_reads_but_never_puts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"id": "job1", "schedule": "daily"})
    out = server.pbs_tape_backup_job_update(job_id="job1", schedule="weekly", confirm=False)
    assert out["status"] == "plan"
    assert out["current"] == {"id": "job1", "schedule": "daily"}
    assert not pbs.puts


def test_job_update_empty_delete_confirm_rejected(tmp_path, monkeypatch):
    """Wave 5b review finding 1: delete=[] is REJECTED (ProximoError), not sent — httpx's form
    encoding drops an empty-list value entirely, so it never reaches the wire."""
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"id": "job1"})
    with pytest.raises(ProximoError):
        server.pbs_tape_backup_job_update(job_id="job1", delete=[], confirm=True)
    assert not pbs.puts


def test_job_delete_dry_run_reads_but_never_deletes(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"id": "job1"})
    out = server.pbs_tape_backup_job_delete(job_id="job1", confirm=False)
    assert out["status"] == "plan"
    assert out["current"] == {"id": "job1"}
    assert not pbs.deletes


def test_job_run_dry_run_never_posts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_tape_backup_job_run(job_id="job1", confirm=False)
    assert out["status"] == "plan"
    assert not pbs.posts


def test_one_off_backup_dry_run_never_posts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_tape_backup(drive="drive1", pool="pool1", store="store1", confirm=False)
    assert out["status"] == "plan"
    assert not pbs.posts


def test_restore_dry_run_never_posts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_tape_restore(drive="drive1", media_set=_UUID, store="store1", confirm=False)
    assert out["status"] == "plan"
    assert not pbs.posts


def test_restore_dry_run_surfaces_namespaces_owner_and_notification_params(tmp_path, monkeypatch):
    """Review finding 1 (Wave 4d, HIGH), proven through the WRAPPER's returned dry-run dict (the
    exact surface a calling agent reviews before confirm=True): namespaces/owner/notify_user/
    notification_mode must all be visible; namespaces + owner must additionally appear in
    blast_radius (where restored data lands + who owns it)."""
    import json as _json
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    ns_map = "store=backup2,source=prod/vms,target=quarantine/vms"
    out = server.pbs_tape_restore(
        drive="drive1", media_set=_UUID, store="store1",
        namespaces=[ns_map], owner="someuser@pve!some-token",
        notify_user="admin@pbs", notification_mode="legacy-sendmail",
        confirm=False,
    )
    assert out["status"] == "plan"
    assert not pbs.posts
    assert ns_map in out["change"]
    assert "someuser@pve!some-token" in out["change"]
    assert "admin@pbs" in out["change"]
    assert "legacy-sendmail" in out["change"]
    blast = _json.dumps(out["blast_radius"])
    assert ns_map in blast
    assert "someuser@pve!some-token" in blast


# ---------------------------------------------------------------------------
# Reads — confirm the wrapper reaches the PbsBackend with the right path/params (no confirm=
# gate).
# ---------------------------------------------------------------------------

def test_media_list_read_reaches_pbs_with_update_status_false_default(tmp_path, monkeypatch):
    """Module docstring fact #12: bare call sends update-status=false explicitly (Proximo's own
    override of PBS's upstream true default)."""
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_tape_media_list()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/tape/media/list"
    assert call_params == {"update-status": False}


def test_media_content_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_tape_media_content(pool="pool1")
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/tape/media/content"
    assert call_params == {"pool": "pool1"}


def test_media_sets_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_tape_media_sets()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/tape/media/media-sets"
    assert call_params is None


def test_media_status_get_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"status": "writable"})
    server.pbs_tape_media_status_get(uuid=_UUID)
    call_path, _ = pbs.gets[-1]
    assert call_path == f"/tape/media/list/{_UUID}/status"


def test_backup_job_list_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_tape_backup_job_list()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/config/tape-backup-job"
    assert call_params is None


def test_backup_job_get_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"id": "job1"})
    server.pbs_tape_backup_job_get(job_id="job1")
    call_path, _ = pbs.gets[-1]
    assert call_path == "/config/tape-backup-job/job1"


# ---------------------------------------------------------------------------
# Outcome honesty — the two documented "returns null despite doing real work" schema quirks
# (module docstring facts #1/#2) never get upgraded to "submitted".
# ---------------------------------------------------------------------------

def test_media_destroy_returns_ok_never_submitted(tmp_path, monkeypatch):
    """Module docstring fact #1: /tape/media/destroy returns null (synchronous) — outcome is
    always 'ok', never 'submitted', regardless of the destructive/GET-verb nature."""
    _, _, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_tape_media_destroy(label_text="tape1", confirm=True)
    assert out["status"] == "ok"


def test_job_run_returns_ok_never_submitted(tmp_path, monkeypatch):
    """Module docstring fact #2: /tape/backup/{id} declares returns:null despite doing real
    work — outcome recorded as 'ok', never 'submitted'."""
    _, _, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_tape_backup_job_run(job_id="job1", confirm=True)
    assert out["status"] == "ok"


def test_one_off_backup_and_restore_return_submitted_with_upid(tmp_path, monkeypatch):
    """UPID-returning ops (the two genuine async tasks on this module) use outcome='submitted'."""
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, post_return=_UPID)
    out = server.pbs_tape_backup(drive="drive1", pool="pool1", store="store1", confirm=True)
    assert out["status"] == "submitted"
    assert out["result"] == _UPID

    out = server.pbs_tape_restore(drive="drive1", media_set=_UUID, store="store1", confirm=True)
    assert out["status"] == "submitted"
    assert out["result"] == _UPID
