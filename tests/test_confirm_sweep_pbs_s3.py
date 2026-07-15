"""Confirm=True sweep — PBS S3 client configs + client encryption keys wrapper welds
(src/proximo/tools/pbs_s3.py, Wave 5a) + the secret-never-in-ledger promise for
`secret-key`/`key` (module docstring facts #1/#8). `access-key` is DELIBERATELY proven to reach
the ledger unredacted — the mirror-image assertion of the secret-never-in-ledger promise.

Mirrors the `_wire()`/`_Pbs` idiom in tests/test_confirm_sweep_pbs_tape_media.py (itself
mirroring tests/test_server_plan.py:110-131): `_svc` is monkeypatched (the ONE shared audit
ledger lives behind it — `_ledger()` reads `_svc()[3]`) and `_pbs` is monkeypatched to a fake
PbsBackend. This file duplicates its own `_Pbs`/`_wire` rather than importing another
confirm-sweep module's — same self-contained convention every confirm-sweep module in this repo
follows.

Each homogeneous confirm=True call proves the three welds:
  1. return shape — status is "ok" (never "plan") — every mutation on this plane is SYNCHRONOUS
     per the live schema (module docstring facts #1/#5/#9/#13 — all returns: null);
  2. the fake PbsBackend captured the underlying call (verb + path + EXACT payload, full dict
     equality — no subset matching);
  3. the ledger recorded a confirmed mutation — structural asserts only, never exact prose.

THE HEADLINE WELD (mirrors tests/test_confirm_sweep_pbs_tape_media.py's identical section):
`secret-key` (s3 create/update) and `key` (encryption key create) must never appear raw in the
on-disk ledger — read RAW BYTES, not parsed JSON — while the real PBS call (the fake's captured
payload) DOES carry the raw value, because the mutation must actually work. `access-key` is
proven to appear UNREDACTED in the ledger (module docstring fact #1's decision) — the deliberate
mirror-image assertion.
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
    behind it); pbs_s3.py's tools never touch this backend."""

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


_SECRET_SENTINEL = "sentinel-s3-secret-key-value"  # noqa: S105 (test sentinel, not a real credential)
_KEY_SENTINEL = "sentinel-encryption-key-blob-" + "k" * 280

# ---------------------------------------------------------------------------
# Homogeneous sweep — table-driven: "confirm=True reaches the right verb/path/data on the
# PbsBackend and records a confirmed mutation". Every mutation on this plane returns null
# (synchronous) — outcome is ALWAYS "ok" (module docstring facts #1/#5/#9/#13), never "submitted".
# ---------------------------------------------------------------------------

_SWEEP_CASES = [
    pytest.param(
        "pbs_s3_client_create",
        dict(s3_id="s3a", endpoint="s3.example.com", access_key="AKIA-sentinel",
             secret_key=_SECRET_SENTINEL, region="us-east-1"),
        "ok", "posts", "/config/s3",
        {"id": "s3a", "endpoint": "s3.example.com", "access-key": "AKIA-sentinel",
         "secret-key": _SECRET_SENTINEL, "region": "us-east-1"},
        id="s3_client_create",
    ),
    pytest.param(
        "pbs_s3_client_update",
        dict(s3_id="s3a", region="us-west-2"),
        "ok", "puts", "/config/s3/s3a",
        {"region": "us-west-2"},
        id="s3_client_update",
    ),
    pytest.param(
        "pbs_s3_client_delete",
        dict(s3_id="s3a"),
        "ok", "deletes", "/config/s3/s3a",
        {},
        id="s3_client_delete",
    ),
    pytest.param(
        "pbs_s3_check",
        dict(s3_id="s3a", bucket="my-bucket"),
        "ok", "puts", "/admin/s3/s3a/check",
        {"bucket": "my-bucket"},
        id="s3_check",
    ),
    pytest.param(
        "pbs_s3_reset_counters",
        dict(s3_id="s3a", bucket="my-bucket"),
        "ok", "puts", "/admin/s3/s3a/reset-counters",
        {"bucket": "my-bucket"},
        id="s3_reset_counters",
    ),
    pytest.param(
        "pbs_encryption_key_create",
        dict(key_id="key1", key=_KEY_SENTINEL),
        "ok", "posts", "/config/encryption-keys",
        {"id": "key1", "key": _KEY_SENTINEL},
        id="encryption_key_create",
    ),
    pytest.param(
        "pbs_encryption_key_delete",
        dict(key_id="key1"),
        "ok", "deletes", "/config/encryption-keys/key1",
        {},
        id="encryption_key_delete",
    ),
    pytest.param(
        "pbs_encryption_key_toggle_archive",
        dict(key_id="key1"),
        "ok", "posts", "/config/encryption-keys/key1",
        {},
        id="encryption_key_toggle_archive",
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
    _, pbs, _, log = _wire(tmp_path, monkeypatch, get_return={"id": "s3a"})
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


# ---------------------------------------------------------------------------
# Dry-run (confirm=False) — proves the PLAN path never touches the PbsBackend's write verbs, and
# that update/delete plans CAPTURE current config via a live read.
# ---------------------------------------------------------------------------

def test_s3_client_create_dry_run_never_posts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_s3_client_create(
        s3_id="s3a", endpoint="s3.example.com", access_key="AKIA1",
        secret_key=_SECRET_SENTINEL, confirm=False,
    )
    assert out["status"] == "plan"
    assert not pbs.posts


def test_s3_client_update_dry_run_reads_but_never_puts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"id": "s3a", "region": "us-east-1"})
    out = server.pbs_s3_client_update(s3_id="s3a", region="us-west-2", confirm=False)
    assert out["status"] == "plan"
    assert out["current"] == {"id": "s3a", "region": "us-east-1"}
    assert not pbs.puts


def test_s3_client_update_empty_delete_rejected_dry_run(tmp_path, monkeypatch):
    # Wave 5b review finding 1: delete=[] is REJECTED (ProximoError), not disclosed — httpx
    # drops an empty-list form value entirely, so confirm=True would never actually send it.
    # _plan() runs before the confirm check, so this raises on the dry-run path too.
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"id": "s3a"})
    with pytest.raises(ProximoError):
        server.pbs_s3_client_update(s3_id="s3a", delete=[], confirm=False)
    assert not pbs.puts


def test_s3_client_update_empty_delete_rejected_confirm(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"id": "s3a"})
    with pytest.raises(ProximoError):
        server.pbs_s3_client_update(s3_id="s3a", delete=[], confirm=True)
    assert not pbs.puts


def test_s3_client_delete_dry_run_reads_but_never_deletes(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"id": "s3a"})
    out = server.pbs_s3_client_delete(s3_id="s3a", confirm=False)
    assert out["status"] == "plan"
    assert out["current"] == {"id": "s3a"}
    assert not pbs.deletes


def test_s3_check_dry_run_never_puts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_s3_check(s3_id="s3a", bucket="my-bucket", confirm=False)
    assert out["status"] == "plan"
    assert not pbs.puts


def test_s3_reset_counters_dry_run_never_puts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_s3_reset_counters(s3_id="s3a", bucket="my-bucket", confirm=False)
    assert out["status"] == "plan"
    assert not pbs.puts


def test_encryption_key_create_dry_run_never_posts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_encryption_key_create(key_id="key1", key=_KEY_SENTINEL, confirm=False)
    assert out["status"] == "plan"
    assert not pbs.posts


def test_encryption_key_delete_dry_run_never_deletes(tmp_path, monkeypatch):
    """No individual GET exists on this plane (module docstring fact #10) — the dry-run PLAN
    never reads at all."""
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_encryption_key_delete(key_id="key1", confirm=False)
    assert out["status"] == "plan"
    assert out["current"] == {}
    assert not pbs.gets
    assert not pbs.deletes


def test_encryption_key_toggle_archive_dry_run_never_posts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_encryption_key_toggle_archive(key_id="key1", confirm=False)
    assert out["status"] == "plan"
    assert not pbs.gets
    assert not pbs.posts


# ---------------------------------------------------------------------------
# Reads — confirm the wrapper reaches the PbsBackend with the right path/params (no confirm=
# gate).
# ---------------------------------------------------------------------------

def test_client_list_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_s3_client_list()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/config/s3"
    assert call_params is None


def test_client_get_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"id": "s3a"})
    server.pbs_s3_client_get(s3_id="s3a")
    call_path, _ = pbs.gets[-1]
    assert call_path == "/config/s3/s3a"


def test_list_buckets_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=["bucket1"])
    server.pbs_s3_list_buckets(s3_id="s3a")
    call_path, _ = pbs.gets[-1]
    assert call_path == "/config/s3/s3a/list-buckets"


def test_encryption_key_list_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_encryption_key_list()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/config/encryption-keys"
    assert call_params == {"include-archived": False}


# ---------------------------------------------------------------------------
# THE HEADLINE WELD — secret-never-in-ledger for secret-key/key, and the DELIBERATE mirror-image
# proof that access-key DOES reach the ledger unredacted (module docstring fact #1's decision).
# Sentinel values are low-entropy/all-lowercase/hyphenated per this repo's fixture-sentinel
# discipline (CLAUDE.md: a mixed-case sentinel already failed the public gitleaks CI scan on
# v0.13.0).
# ---------------------------------------------------------------------------

def test_s3_client_create_confirm_never_writes_secret_key_to_ledger(tmp_path, monkeypatch):
    """weld 1: the operator's real PBS call DOES carry the raw secret-key (the mutation must
    actually work) — the fake captured it. weld 2: read the ledger file RAW (bytes, not parsed
    JSON) and assert the secret substring appears NOWHERE — not in the 'planned' entry, not in
    the 'confirmed' entry, not anywhere in the file."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch)

    out = server.pbs_s3_client_create(
        s3_id="s3a", endpoint="s3.example.com", access_key="AKIA-sentinel-visible",
        secret_key=_SECRET_SENTINEL, confirm=True,
    )

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    # weld 1: the fake captured the underlying POST with the RAW secret-key.
    assert pbs.posts, "pbs_s3_client_create confirm=True never reached pbs._post"
    call_path, call_data = pbs.posts[-1]
    assert call_path == "/config/s3"
    assert call_data["secret-key"] == _SECRET_SENTINEL

    # weld 2: ledger entries (parsed JSON) never carry the secret-key sentinel.
    entries = _entries(log)
    assert entries, "no ledger entries recorded at all"
    assert all(_SECRET_SENTINEL not in json.dumps(e) for e in entries)
    entry = _confirmed_entry(log, "pbs_s3_client_create", "ok")
    assert "secret_key" not in entry["detail"]
    assert "secret-key" not in entry["detail"]

    # THE HEADLINE WELD: read the ledger file RAW (bytes) — the secret must appear NOWHERE.
    raw = open(log, "rb").read()
    assert _SECRET_SENTINEL.encode("utf-8") not in raw

    # MIRROR-IMAGE: access-key IS present raw in the on-disk ledger (module docstring fact #1's
    # decision — deliberately NOT redacted).
    assert b"AKIA-sentinel-visible" in raw


def test_s3_client_update_confirm_never_writes_secret_key_to_ledger(tmp_path, monkeypatch):
    _, pbs, _, log = _wire(tmp_path, monkeypatch, get_return={"id": "s3a"})

    out = server.pbs_s3_client_update(s3_id="s3a", secret_key=_SECRET_SENTINEL, confirm=True)

    assert out["status"] == "ok"
    assert pbs.puts
    _, call_data = pbs.puts[-1]
    assert call_data["secret-key"] == _SECRET_SENTINEL

    raw = open(log, "rb").read()
    assert _SECRET_SENTINEL.encode("utf-8") not in raw


def test_s3_client_update_capture_secret_never_reaches_ledger(tmp_path, monkeypatch):
    """Defense-in-depth: the CAPTURE read (schema says secret-key never appears in GET, but wire
    the fake to return one anyway) must never leak into the ledger either, on BOTH confirm=False
    and confirm=True paths."""
    leaked = "sentinel-leaked-from-a-get-that-should-never-carry-this"
    _, _, _, log = _wire(tmp_path, monkeypatch, get_return={"id": "s3a", "secret-key": leaked})

    out = server.pbs_s3_client_update(s3_id="s3a", region="us-west-2", confirm=False)
    assert out["status"] == "plan"
    assert leaked not in json.dumps(out)

    out = server.pbs_s3_client_update(s3_id="s3a", region="us-west-2", confirm=True)
    assert out["status"] == "ok"

    raw = open(log, "rb").read()
    assert leaked.encode("utf-8") not in raw


def test_s3_client_delete_capture_secret_never_reaches_ledger(tmp_path, monkeypatch):
    leaked = "sentinel-leaked-from-delete-capture-read"
    _, _, _, log = _wire(tmp_path, monkeypatch, get_return={"id": "s3a", "secret-key": leaked})

    out = server.pbs_s3_client_delete(s3_id="s3a", confirm=True)

    assert out["status"] == "ok"
    raw = open(log, "rb").read()
    assert leaked.encode("utf-8") not in raw


def test_s3_client_create_dry_run_plan_never_carries_secret(tmp_path, monkeypatch):
    """Even confirm=False (the returned PLAN dict itself, not just the ledger) must never carry
    the raw secret-key — the plan is returned directly to the calling agent."""
    _, _, _, _ = _wire(tmp_path, monkeypatch)

    out = server.pbs_s3_client_create(
        s3_id="s3a", endpoint="s3.example.com", access_key="AKIA1",
        secret_key=_SECRET_SENTINEL, confirm=False,
    )

    assert out["status"] == "plan"
    dumped = json.dumps(out)
    assert _SECRET_SENTINEL not in dumped
    assert "AKIA1" in dumped  # access-key IS visible in the plan — deliberately not redacted


def test_s3_client_update_dry_run_plan_never_carries_secret(tmp_path, monkeypatch):
    """Review finding (Wave 5a): the update path's dry-run dict gets the same proof the
    create path already had."""
    _, _, _, _ = _wire(tmp_path, monkeypatch, get_return={"id": "s3a", "endpoint": "old"})

    out = server.pbs_s3_client_update(s3_id="s3a", secret_key=_SECRET_SENTINEL, confirm=False)

    assert out["status"] == "plan"
    assert _SECRET_SENTINEL not in json.dumps(out)


def test_encryption_key_create_confirm_never_writes_key_material_to_ledger(tmp_path, monkeypatch):
    """Same headline weld as the s3 secret-key test, for the encryption-key plane's `key`
    (import material) field."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch)

    out = server.pbs_encryption_key_create(key_id="key1", key=_KEY_SENTINEL, confirm=True)

    assert out["status"] == "ok"
    assert pbs.posts
    _, call_data = pbs.posts[-1]
    assert call_data["key"] == _KEY_SENTINEL

    entries = _entries(log)
    assert entries
    assert all(_KEY_SENTINEL not in json.dumps(e) for e in entries)
    entry = _confirmed_entry(log, "pbs_encryption_key_create", "ok")
    assert "key" not in entry["detail"]
    assert entry["detail"]["key_supplied"] is True

    raw = open(log, "rb").read()
    assert _KEY_SENTINEL.encode("utf-8") not in raw


def test_encryption_key_create_dry_run_plan_never_carries_key_material(tmp_path, monkeypatch):
    _, _, _, _ = _wire(tmp_path, monkeypatch)

    out = server.pbs_encryption_key_create(key_id="key1", key=_KEY_SENTINEL, confirm=False)

    assert out["status"] == "plan"
    dumped = json.dumps(out)
    assert _KEY_SENTINEL not in dumped
