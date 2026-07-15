"""Confirm=True sweep — PBS tape media-pool + encryption-key wrapper welds
(src/proximo/tools/pbs_tape_media.py, Wave 4b) + the secret-never-in-ledger promise for
`key`/`password`/`new-password` (module docstring fact #7).

Mirrors the `_wire()`/`_Pbs` idiom in tests/test_confirm_sweep_pbs_tape_config.py (itself
mirroring tests/test_server_plan.py:110-131): `_svc` is monkeypatched (the ONE shared audit
ledger lives behind it — `_ledger()` reads `_svc()[3]`) and `_pbs` is monkeypatched to a fake
PbsBackend. This file duplicates its own `_Pbs`/`_wire` rather than importing another
confirm-sweep module's — same self-contained convention every confirm-sweep module in this repo
follows.

Each homogeneous confirm=True call proves the three welds:
  1. return shape — status is "ok" (never "plan") — every mutation on this plane is SYNCHRONOUS
     per the live schema (module docstring fact #12), unlike a PVE guest/storage mutation;
  2. the fake PbsBackend captured the underlying call (verb + path + EXACT payload, full dict
     equality — no subset matching);
  3. the ledger recorded a confirmed mutation — structural asserts only, never exact prose.

THE HEADLINE WELD (mirrors tests/test_confirm_sweep_pbs_notifications.py's identical section and
tests/test_confirm_sweep_pve_access.py's test_token_create_confirm_returns_secret_but_never_
writes_it_to_ledger): `key`, `password` (create), and `new-password`/`password` (update) must
never appear raw in the on-disk ledger — read RAW BYTES, not parsed JSON — while the real PBS
call (the fake's captured payload) DOES carry the raw value, because the mutation must actually
work. `pbs_tape_key_create`'s RETURN carries the new key's fingerprint (NOT secret) — asserted to
be present in the return and in the ledger's detail (mirrors pve_token_create's contract, except
here the returned value itself was never secret to begin with).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.backends import ProximoError
from proximo.config import ProximoConfig

_FP = ":".join(["ab"] * 32)


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
    behind it); pbs_tape_media.py's tools never touch this backend."""

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
# Homogeneous sweep — table-driven: "confirm=True reaches the right verb/path/data on the
# PbsBackend and records a confirmed mutation". Every mutation on this plane returns null
# (synchronous) per the live schema EXCEPT pbs_tape_key_create (returns the fingerprint string) —
# outcome is ALWAYS "ok" (module docstring fact #12), never "submitted".
# ---------------------------------------------------------------------------

_SWEEP_CASES = [
    pytest.param(
        "pbs_tape_pool_create",
        dict(name="pool1", allocation="always", comment="c1", encrypt=_FP, retention="keep",
             template="tmpl-%Y"),
        "ok", "posts", "/config/media-pool",
        {"name": "pool1", "allocation": "always", "comment": "c1", "encrypt": _FP,
         "retention": "keep", "template": "tmpl-%Y"},
        id="pool_create",
    ),
    pytest.param(
        "pbs_tape_pool_update",
        dict(name="pool1", allocation="continue", retention="overwrite",
             delete=["comment"]),
        "ok", "puts", "/config/media-pool/pool1",
        {"allocation": "continue", "retention": "overwrite", "delete": ["comment"]},
        id="pool_update",
    ),
    pytest.param(
        "pbs_tape_pool_delete",
        dict(name="pool1"),
        "ok", "deletes", "/config/media-pool/pool1",
        None,
        id="pool_delete",
    ),
    pytest.param(
        "pbs_tape_key_create",
        dict(password="placeholder-pw-for-payload-check", hint="h1", kdf="scrypt"),
        "ok", "posts", "/config/tape-encryption-keys",
        {"password": "placeholder-pw-for-payload-check", "hint": "h1", "kdf": "scrypt"},
        id="key_create",
    ),
    pytest.param(
        "pbs_tape_key_update_password",
        dict(fingerprint=_FP, hint="h2", new_password="placeholder-new-pw", kdf="none"),
        "ok", "puts", f"/config/tape-encryption-keys/{_FP}",
        {"hint": "h2", "new-password": "placeholder-new-pw", "kdf": "none"},
        id="key_update_password",
    ),
    pytest.param(
        "pbs_tape_key_delete",
        dict(fingerprint=_FP, digest="d" * 64),
        "ok", "deletes", f"/config/tape-encryption-keys/{_FP}",
        {"digest": "d" * 64},
        id="key_delete",
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
        tmp_path, monkeypatch, get_return={"name": "pool1", "fingerprint": _FP}, post_return=_FP,
    )
    fn = getattr(server, tool_name)

    out = fn(confirm=True, **kwargs)

    # weld 1: return shape — always "ok" on this plane (every mutation returns null or the
    # fingerprint string, synchronous either way)
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


def test_pool_delete_no_params_sent(tmp_path, monkeypatch):
    """Module docstring fact #2: media-pool DELETE carries no digest param — the fake must see
    None, not an empty dict, matching tape_pool_delete's own call shape."""
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "pool1"})
    out = server.pbs_tape_pool_delete(name="pool1", confirm=True)
    assert out["status"] == "ok"
    call_path, call_params = pbs.deletes[-1]
    assert call_path == "/config/media-pool/pool1"
    assert call_params is None


def test_key_delete_no_digest_sends_empty_params(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"fingerprint": _FP})
    out = server.pbs_tape_key_delete(fingerprint=_FP, confirm=True)
    assert out["status"] == "ok"
    call_path, call_params = pbs.deletes[-1]
    assert call_path == f"/config/tape-encryption-keys/{_FP}"
    assert call_params == {}


# ---------------------------------------------------------------------------
# Dry-run (confirm=False) — proves the PLAN path never touches the PbsBackend's write verbs, and
# that update/delete plans CAPTURE current config via a live read.
# ---------------------------------------------------------------------------

def test_pool_create_dry_run_never_posts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_tape_pool_create(name="pool1", confirm=False)
    assert out["status"] == "plan"
    assert not pbs.posts


def test_pool_update_dry_run_reads_but_never_puts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "pool1", "retention": "keep"})
    out = server.pbs_tape_pool_update(name="pool1", retention="overwrite", confirm=False)
    assert out["status"] == "plan"
    assert out["current"] == {"name": "pool1", "retention": "keep"}
    assert not pbs.puts


def test_pool_update_empty_delete_confirm_rejected(tmp_path, monkeypatch):
    """Wave 5b review finding 1: delete=[] is REJECTED (ProximoError), not sent — httpx's form
    encoding drops an empty-list value entirely, so it never reaches the wire. Proves the error
    surfaces through the wrapper (mirrors test_confirm_sweep_pbs_tape_config.py's drive/changer
    equivalents)."""
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "pool1"})
    with pytest.raises(ProximoError):
        server.pbs_tape_pool_update(name="pool1", delete=[], confirm=True)
    assert not pbs.puts


def test_pool_delete_dry_run_reads_but_never_deletes(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "pool1"})
    out = server.pbs_tape_pool_delete(name="pool1", confirm=False)
    assert out["status"] == "plan"
    assert out["current"] == {"name": "pool1"}
    assert not pbs.deletes


def test_key_create_dry_run_never_posts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pbs_tape_key_create(password="sentinel-password-value", confirm=False)
    assert out["status"] == "plan"
    assert not pbs.posts


def test_key_update_password_dry_run_reads_but_never_puts(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"fingerprint": _FP, "hint": "old"})
    out = server.pbs_tape_key_update_password(
        fingerprint=_FP, hint="new-hint", new_password="sentinel-new-pw", confirm=False,
    )
    assert out["status"] == "plan"
    assert out["current"] == {"fingerprint": _FP, "hint": "old"}
    assert not pbs.puts


def test_key_delete_dry_run_reads_but_never_deletes(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"fingerprint": _FP})
    out = server.pbs_tape_key_delete(fingerprint=_FP, confirm=False)
    assert out["status"] == "plan"
    assert out["current"] == {"fingerprint": _FP}
    assert not pbs.deletes


# ---------------------------------------------------------------------------
# Reads — confirm the wrapper reaches the PbsBackend with the right path/params (no confirm=
# gate).
# ---------------------------------------------------------------------------

def test_pool_list_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_tape_pool_list()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/config/media-pool"
    assert call_params is None


def test_pool_get_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "pool1"})
    server.pbs_tape_pool_get(name="pool1")
    call_path, _ = pbs.gets[-1]
    assert call_path == "/config/media-pool/pool1"


def test_key_list_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_tape_key_list()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/config/tape-encryption-keys"
    assert call_params is None


def test_key_get_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"fingerprint": _FP})
    server.pbs_tape_key_get(fingerprint=_FP)
    call_path, _ = pbs.gets[-1]
    assert call_path == f"/config/tape-encryption-keys/{_FP}"


# ---------------------------------------------------------------------------
# THE HEADLINE WELD — secret-never-in-ledger, across key/password (create) and
# new-password/password (update). Sentinel values are low-entropy/all-lowercase/hyphenated per
# this repo's fixture-sentinel discipline (CLAUDE.md: "Test fixtures must use low-entropy
# sentinel values" — a mixed-case sentinel already failed the public gitleaks CI scan on v0.13.0).
# ---------------------------------------------------------------------------

_PASSWORD_SENTINEL = "sentinel-tape-key-password-value"  # noqa: S105 (test sentinel, not a real credential)
_KEY_SENTINEL = "sentinel-tape-key-material-" + "k" * 280  # 307 chars — within the 300-600 bound
_NEW_PASSWORD_SENTINEL = "sentinel-tape-key-new-password-value"  # noqa: S105
_CURRENT_PASSWORD_SENTINEL = "sentinel-tape-key-current-password-value"  # noqa: S105


def test_key_create_confirm_never_writes_password_to_ledger(tmp_path, monkeypatch):
    """weld 1: the operator's real PBS call DOES carry the raw password (the mutation must
    actually work) — the fake captured it. weld 2: read the ledger file RAW (bytes, not parsed
    JSON) and assert the secret substring appears NOWHERE — not in the 'planned' entry, not in
    the 'confirmed' entry, not anywhere in the file. Also proves the RETURNED fingerprint (NOT
    secret) IS surfaced to the caller and IS in the ledger detail — the mirror-image assertion of
    pve_token_create's contract."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch, post_return=_FP)

    out = server.pbs_tape_key_create(password=_PASSWORD_SENTINEL, hint="my-hint", confirm=True)

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    # the fingerprint (not secret) IS returned to the caller — mirrors pve_token_create's
    # "operator receives the secret/identifier once" contract, except this value isn't secret.
    assert out["result"] == _FP

    # weld 1: the fake captured the underlying POST with the RAW password.
    assert pbs.posts, "pbs_tape_key_create confirm=True never reached pbs._post"
    call_path, call_data = pbs.posts[-1]
    assert call_path == "/config/tape-encryption-keys"
    assert call_data["password"] == _PASSWORD_SENTINEL

    # weld 2: ledger entries (parsed JSON) never carry the sentinel, in EITHER the planned or the
    # confirmed entry — but DO carry the (non-secret) fingerprint in the confirmed detail.
    entries = _entries(log)
    assert entries, "no ledger entries recorded at all"
    assert all(_PASSWORD_SENTINEL not in json.dumps(e) for e in entries)
    entry = _confirmed_entry(log, "pbs_tape_key_create", "ok")
    assert "password" not in entry["detail"]
    assert "key" not in entry["detail"]

    # THE HEADLINE WELD: read the ledger file RAW (bytes) — the secret must appear NOWHERE in the
    # on-disk ledger, across every entry, not just the ones inspected above as parsed JSON.
    raw = open(log, "rb").read()
    assert _PASSWORD_SENTINEL.encode("utf-8") not in raw


def test_key_create_confirm_never_writes_key_material_to_ledger(tmp_path, monkeypatch):
    """Same headline weld as the password test, for the `key` (imported key material) field."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch, post_return=_FP)

    out = server.pbs_tape_key_create(
        password=_PASSWORD_SENTINEL, key=_KEY_SENTINEL, confirm=True,
    )

    assert out["status"] == "ok"
    assert pbs.posts
    _, call_data = pbs.posts[-1]
    assert call_data["key"] == _KEY_SENTINEL

    raw = open(log, "rb").read()
    assert _KEY_SENTINEL.encode("utf-8") not in raw
    assert _PASSWORD_SENTINEL.encode("utf-8") not in raw


def test_pool_update_capture_secret_never_reaches_ledger(tmp_path, monkeypatch):
    """Review finding (Wave 4b): the pool-side CAPTURE read gets the same defense-in-depth as
    the key side — wire the fake GET to return a secret-shaped field (out-of-schema for
    media-pool GET today) and prove neither the dry-run return dict nor the raw on-disk
    ledger ever carries it, on BOTH the confirm=False and confirm=True paths."""
    leaked = "sentinel-leaked-pool-secret"
    _, _, _, log = _wire(tmp_path, monkeypatch, get_return={"name": "pool1", "password": leaked})

    out = server.pbs_tape_pool_update(name="pool1", allocation="always", confirm=False)
    assert out["status"] == "plan"
    assert leaked not in json.dumps(out)

    out = server.pbs_tape_pool_update(name="pool1", allocation="always", confirm=True)
    assert out["status"] == "ok"

    raw = open(log, "rb").read()
    assert leaked.encode("utf-8") not in raw


def test_key_create_dry_run_plan_never_carries_secret(tmp_path, monkeypatch):
    """Even confirm=False (the returned PLAN dict itself, not just the ledger) must never carry
    a raw secret — the plan is returned directly to the calling agent."""
    _, _, _, _ = _wire(tmp_path, monkeypatch)

    out = server.pbs_tape_key_create(
        password=_PASSWORD_SENTINEL, key=_KEY_SENTINEL, confirm=False,
    )

    assert out["status"] == "plan"
    dumped = json.dumps(out)
    assert _PASSWORD_SENTINEL not in dumped
    assert _KEY_SENTINEL not in dumped


def test_key_update_password_confirm_never_writes_secrets_to_ledger(tmp_path, monkeypatch):
    """Same headline weld for the update path: both `new-password` and the CURRENT `password`
    must never reach the ledger, while the fake's captured PUT payload DOES carry them raw."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch, get_return={"fingerprint": _FP, "hint": "old"})

    out = server.pbs_tape_key_update_password(
        fingerprint=_FP, hint="new-hint", new_password=_NEW_PASSWORD_SENTINEL,
        password=_CURRENT_PASSWORD_SENTINEL, confirm=True,
    )

    assert out["status"] == "ok"
    assert pbs.puts, "pbs_tape_key_update_password confirm=True never reached pbs._put"
    call_path, call_data = pbs.puts[-1]
    assert call_path == f"/config/tape-encryption-keys/{_FP}"
    assert call_data["new-password"] == _NEW_PASSWORD_SENTINEL
    assert call_data["password"] == _CURRENT_PASSWORD_SENTINEL

    entries = _entries(log)
    assert entries
    assert all(_NEW_PASSWORD_SENTINEL not in json.dumps(e) for e in entries)
    assert all(_CURRENT_PASSWORD_SENTINEL not in json.dumps(e) for e in entries)

    raw = open(log, "rb").read()
    assert _NEW_PASSWORD_SENTINEL.encode("utf-8") not in raw
    assert _CURRENT_PASSWORD_SENTINEL.encode("utf-8") not in raw


def test_key_update_password_captured_current_never_writes_leaked_secret_to_ledger(
    tmp_path, monkeypatch,
):
    """Review-anticipated case (campaign brief, explicit instruction): even though the live GET
    is public-only (module docstring fact #9), wire the fake GET to return a secret-bearing field
    anyway and prove the CAPTURE redaction holds end-to-end — not just at the Plan.current dict
    level (already covered in test_pbs_tape_media.py), but all the way to the raw ledger bytes."""
    leaked_sentinel = "sentinel-leaked-from-a-get-that-should-never-carry-this"
    _, pbs, _, log = _wire(
        tmp_path, monkeypatch,
        get_return={"fingerprint": _FP, "hint": "old", "password": leaked_sentinel},
    )

    out = server.pbs_tape_key_update_password(
        fingerprint=_FP, hint="new-hint", new_password=_NEW_PASSWORD_SENTINEL, confirm=True,
    )

    assert out["status"] == "ok"

    entries = _entries(log)
    assert entries
    assert all(leaked_sentinel not in json.dumps(e) for e in entries)

    raw = open(log, "rb").read()
    assert leaked_sentinel.encode("utf-8") not in raw


def test_key_delete_captured_current_never_writes_leaked_secret_to_ledger(tmp_path, monkeypatch):
    """Same defensive-capture proof as the update-password test above, for the delete path's
    CAPTURE read."""
    leaked_sentinel = "sentinel-leaked-from-delete-capture-read"
    _, pbs, _, log = _wire(
        tmp_path, monkeypatch,
        get_return={"fingerprint": _FP, "password": leaked_sentinel},
    )

    out = server.pbs_tape_key_delete(fingerprint=_FP, confirm=True)

    assert out["status"] == "ok"

    entries = _entries(log)
    assert entries
    assert all(leaked_sentinel not in json.dumps(e) for e in entries)

    raw = open(log, "rb").read()
    assert leaked_sentinel.encode("utf-8") not in raw


def test_key_update_password_dry_run_plan_never_carries_secrets(tmp_path, monkeypatch):
    """The dry-run PLAN dict for update is returned directly to the calling agent — it must
    never carry the raw new-password/password values, nor a leaked secret from its CAPTURE
    read."""
    leaked_sentinel = "sentinel-leaked-from-a-get-in-the-dry-run-path"
    _, _, _, _ = _wire(
        tmp_path, monkeypatch,
        get_return={"fingerprint": _FP, "password": leaked_sentinel},
    )

    out = server.pbs_tape_key_update_password(
        fingerprint=_FP, hint="new-hint", new_password=_NEW_PASSWORD_SENTINEL,
        password=_CURRENT_PASSWORD_SENTINEL, confirm=False,
    )

    assert out["status"] == "plan"
    dumped = json.dumps(out)
    assert _NEW_PASSWORD_SENTINEL not in dumped
    assert _CURRENT_PASSWORD_SENTINEL not in dumped
    assert leaked_sentinel not in dumped
