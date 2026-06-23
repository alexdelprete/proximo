"""Tamper-evidence tests — the PROVE pillar's whole point is that these pass."""

from __future__ import annotations

import json
import os
import re as _re
import stat
from types import SimpleNamespace

import pytest

from proximo.audit import (
    _KEY_ALG,
    GENESIS_HASH,
    AuditLedger,
    _hash,
    detect_mode,
    load_or_create_key,
    looks_like_head,
    open_ledger,
    seal_and_rotate,
)
from proximo.backends import ProximoError

_KEY = bytes(range(32))          # deterministic 32-byte key for tests
_KEY2 = bytes(range(1, 33))      # a different key


def _ledger(tmp_path):
    return AuditLedger(str(tmp_path / "audit.log"))


def test_empty_ledger_verifies(tmp_path):
    v = _ledger(tmp_path).verify()
    assert v.ok and v.entries == 0


def test_chain_links_and_verifies(tmp_path):
    led = _ledger(tmp_path)
    e1 = led.record("a", target="t1")
    e2 = led.record("b", target="t2", mutation=True)
    assert e1["prev_hash"] == GENESIS_HASH
    assert e2["prev_hash"] == e1["entry_hash"]  # chain linkage
    v = led.verify()
    assert v.ok and v.entries == 2
    assert led.head() == e2["entry_hash"]


def test_detects_altered_field(tmp_path):
    led = _ledger(tmp_path)
    led.record("a", target="t1")
    led.record("b", target="t2")
    p = tmp_path / "audit.log"
    lines = p.read_text().splitlines()
    lines[0] = lines[0].replace('"t1"', '"HACKED"')  # tamper the first entry's target
    p.write_text("\n".join(lines) + "\n")
    v = led.verify()
    assert not v.ok
    assert v.broken_at == 1
    assert "altered" in (v.reason or "")


def test_detects_deleted_entry(tmp_path):
    led = _ledger(tmp_path)
    led.record("a", target="t1")
    led.record("b", target="t2")
    led.record("c", target="t3")
    p = tmp_path / "audit.log"
    lines = p.read_text().splitlines()
    del lines[1]  # remove the middle entry
    p.write_text("\n".join(lines) + "\n")
    v = led.verify()
    assert not v.ok
    assert "mismatch" in (v.reason or "")


def test_detects_reorder(tmp_path):
    led = _ledger(tmp_path)
    led.record("a", target="t1")
    led.record("b", target="t2")
    p = tmp_path / "audit.log"
    lines = p.read_text().splitlines()
    lines.reverse()  # swap order
    p.write_text("\n".join(lines) + "\n")
    assert not led.verify().ok


def test_ledger_adds_no_secret_fields(tmp_path):
    e = _ledger(tmp_path).record("x", target="t")
    assert set(e) == {"ts", "action", "target", "mutation", "outcome", "detail", "prev_hash", "entry_hash"}


def test_nondict_line_fails_clean_not_crash(tmp_path):
    # Redteam Finding 2: a valid-JSON-but-not-object line must fail cleanly, not crash verify().
    led = _ledger(tmp_path)
    led.record("a", target="t1")
    p = tmp_path / "audit.log"
    p.write_text(p.read_text() + "123\n")
    v = led.verify()
    assert not v.ok
    assert "non-object" in (v.reason or "")


def test_tail_deletion_caught_only_with_anchor(tmp_path):
    # Redteam Finding 1: a forward walk can't see tail truncation; an off-box head anchor can.
    led = _ledger(tmp_path)
    led.record("a", target="t1")
    led.record("b", target="t2")
    pinned = led.head()
    p = tmp_path / "audit.log"
    lines = p.read_text().splitlines()
    del lines[-1]  # truncate the tail
    p.write_text("\n".join(lines) + "\n")
    assert led.verify().ok  # honest limit: undetectable by the walk alone
    v = led.verify(expected_head=pinned)  # ...but the anchor catches it
    assert not v.ok
    assert "head mismatch" in (v.reason or "")


# --- keyed (HMAC) mode -----------------------------------------------------------------------


def _keyed(tmp_path, key=_KEY):
    return AuditLedger(str(tmp_path / "audit.log"), key=key)


def test_keyed_chain_verifies_with_key(tmp_path):
    led = _keyed(tmp_path)
    e1 = led.record("a", target="t1")
    led.record("b", target="t2", mutation=True)
    assert led.keyed and e1["alg"] == _KEY_ALG
    v = led.verify()
    assert v.ok and v.entries == 2


def test_keyed_chain_fails_with_wrong_key(tmp_path):
    _keyed(tmp_path).record("a", target="t1")
    v = AuditLedger(str(tmp_path / "audit.log"), key=_KEY2).verify()  # holder of a DIFFERENT key
    assert not v.ok and "mismatch" in (v.reason or "")


def test_keyed_chain_fails_without_key(tmp_path):
    _keyed(tmp_path).record("a", target="t1")
    v = AuditLedger(str(tmp_path / "audit.log")).verify()  # no key at all
    assert not v.ok and "keyed" in (v.reason or "")


def test_keyed_detects_altered_field(tmp_path):
    led = _keyed(tmp_path)
    led.record("a", target="t1")
    p = tmp_path / "audit.log"
    lines = p.read_text().splitlines()
    lines[0] = lines[0].replace('"t1"', '"HACKED"')
    p.write_text("\n".join(lines) + "\n")
    v = led.verify()
    assert not v.ok and "altered" in (v.reason or "")


def test_keyed_downgrade_attack_is_caught(tmp_path):
    """THE cardinal property: an attacker WITHOUT the key cannot rewrite a keyed entry as plain
    SHA-256 (strip `alg`, recompute) and pass — the ledger's key is authoritative, not the entry tag."""
    led = _keyed(tmp_path)
    led.record("a", target="t1")
    p = tmp_path / "audit.log"
    entry = json.loads(p.read_text().splitlines()[0])
    body = {k: v for k, v in entry.items() if k not in ("prev_hash", "entry_hash", "alg")}
    body["target"] = "HACKED"  # the forgery
    forged = {**body, "prev_hash": entry["prev_hash"],
              "entry_hash": _hash(body, entry["prev_hash"], None)}  # recomputed UNKEYED (no key)
    p.write_text(json.dumps(forged, separators=(",", ":")) + "\n")
    v = led.verify()  # verified by the legit operator, who holds the key
    assert not v.ok and "downgrade" in (v.reason or "")


def test_keyed_entry_has_alg_and_no_secret_fields(tmp_path):
    e = _keyed(tmp_path).record("x", target="t")
    assert e["alg"] == _KEY_ALG
    assert set(e) == {"ts", "action", "target", "mutation", "outcome", "detail",
                      "prev_hash", "entry_hash", "alg"}


def test_keyed_head_anchor_catches_tail_truncation(tmp_path):
    led = _keyed(tmp_path)
    led.record("a", target="t1")
    led.record("b", target="t2")
    pinned = led.head()
    p = tmp_path / "audit.log"
    lines = p.read_text().splitlines()
    del lines[-1]
    p.write_text("\n".join(lines) + "\n")
    assert led.verify().ok                          # the walk alone can't see a tail truncation
    assert not led.verify(expected_head=pinned).ok  # the off-box anchor does


def test_unkeyed_default_has_no_alg_and_stays_byte_compatible(tmp_path):
    e = _ledger(tmp_path).record("x", target="t")
    assert "alg" not in e and AuditLedger(str(tmp_path / "x")).keyed is False
    assert set(e) == {"ts", "action", "target", "mutation", "outcome", "detail", "prev_hash", "entry_hash"}


def test_load_or_create_key_generates_0600_and_is_idempotent(tmp_path):
    kp = str(tmp_path / "sub" / "audit.key")
    k1 = load_or_create_key(kp)
    assert len(k1) == 32
    assert stat.S_IMODE(os.stat(kp).st_mode) == 0o600
    assert load_or_create_key(kp) == k1  # second call reads the same key, doesn't regenerate


def test_load_or_create_key_rejects_empty(tmp_path):
    kp = tmp_path / "empty.key"
    kp.write_text("")
    with pytest.raises(ValueError, match="empty"):
        load_or_create_key(str(kp))


def test_load_or_create_key_rejects_non_hex(tmp_path):
    kp = tmp_path / "bad.key"
    kp.write_text("zz-not-hex\n")
    with pytest.raises(ValueError, match="hex"):
        load_or_create_key(str(kp))


def test_load_or_create_key_rejects_short_key(tmp_path):
    # Redteam (key-handling): a hand-rolled <32-byte key is weak — fail closed, don't silently accept it.
    kp = tmp_path / "short.key"
    kp.write_text("deadbeef\n")  # 4 bytes
    with pytest.raises(ValueError, match="too short"):
        load_or_create_key(str(kp))


def test_ledger_file_created_owner_only(tmp_path):
    """The ledger holds command/SQL detail — it must be created 0600, not the umask default."""
    log = str(tmp_path / "audit.log")
    AuditLedger(log).record("ct_psql", target="100", detail={"sql": "select 1"})
    assert stat.S_IMODE(os.stat(log).st_mode) == 0o600


def test_ledger_existing_file_keeps_operator_mode(tmp_path):
    """0600 applies at creation only — an operator-loosened existing file is not re-tightened."""
    log = str(tmp_path / "audit.log")
    ledger = AuditLedger(log)
    ledger.record("a", target="t")
    os.chmod(log, 0o644)
    ledger.record("b", target="t")
    assert stat.S_IMODE(os.stat(log).st_mode) == 0o644


# --- detect_mode inspector -----------------------------------------------------------------------


def test_detect_mode_empty_for_absent(tmp_path):
    assert detect_mode(str(tmp_path / "nope.log")) == "empty"


def test_detect_mode_unkeyed(tmp_path):
    _ledger(tmp_path).record("a", target="t1")
    assert detect_mode(str(tmp_path / "audit.log")) == "unkeyed"


def test_detect_mode_keyed(tmp_path):
    _keyed(tmp_path).record("a", target="t1")
    assert detect_mode(str(tmp_path / "audit.log")) == "keyed"


def test_detect_mode_empty_for_blank_file(tmp_path):
    p = tmp_path / "audit.log"
    p.write_text("\n\n")
    assert detect_mode(str(p)) == "empty"


# --- seal_and_rotate -----------------------------------------------------------------------


def test_seal_and_rotate_archives_and_starts_keyed(tmp_path):
    log = str(tmp_path / "audit.log")
    old = AuditLedger(log)
    old.record("a", target="t1")
    old.record("b", target="t2")
    pre_head = old.head()

    archive, sealed_head = seal_and_rotate(log, _KEY)

    # archive named with the sealed head's first 8 chars; old chain still verifies UNKEYED
    assert _re.search(r"audit\.log\.unkeyed-\d{8}T\d{6}Z-[0-9a-f]{8}$", archive)
    assert sealed_head[:8] in archive
    assert AuditLedger(archive).verify().ok            # old log intact as an unkeyed chain
    arch_lines = (tmp_path / archive.split("/")[-1]).read_text().splitlines()
    assert json.loads(arch_lines[-1])["action"] == "audit_rotate"   # terminal sealed marker
    assert json.loads(arch_lines[-1])["detail"]["sealed"] is True

    # new keyed log exists, verifies WITH the key, and records the custody seam
    new = AuditLedger(log, key=_KEY)
    assert new.verify().ok and new.keyed
    genesis = json.loads((tmp_path / "audit.log").read_text().splitlines()[0])
    assert genesis["action"] == "audit_rotate"
    assert genesis["detail"]["prev_head"] == sealed_head
    assert genesis["detail"]["prev_log"].startswith("audit.log.unkeyed-")
    assert genesis["alg"] == _KEY_ALG
    assert pre_head != sealed_head   # the terminal entry advanced the old head


def test_seal_and_rotate_is_idempotent_on_keyed(tmp_path):
    log = str(tmp_path / "audit.log")
    AuditLedger(log, key=_KEY).record("a", target="t1")   # already keyed
    archive, _ = seal_and_rotate(log, _KEY)
    assert archive == ""                                   # no-op: nothing to seal
    assert AuditLedger(log, key=_KEY).verify().ok


# --- open_ledger factory -----------------------------------------------------------------------


def _cfg(tmp_path, **kw):
    base = dict(audit_log_path=str(tmp_path / "audit.log"), audit_key_path=None, audit_keyed=True)
    base.update(kw)
    return SimpleNamespace(**base)


def test_open_ledger_keyed_default_for_new_log(tmp_path):
    led = open_ledger(_cfg(tmp_path))
    assert led.keyed
    led.record("a", target="t1")
    assert (tmp_path / "audit.key").exists()          # default key path beside the log
    assert led.verify().ok


def test_open_ledger_opt_out_is_unkeyed(tmp_path):
    led = open_ledger(_cfg(tmp_path, audit_keyed=False))
    assert not led.keyed


def test_open_ledger_explicit_key_path_wins(tmp_path):
    kp = str(tmp_path / "custom.key")
    led = open_ledger(_cfg(tmp_path, audit_key_path=kp, audit_keyed=False))  # explicit wins even if keyed flag off
    led.record("a", target="t1")
    assert led.keyed and (tmp_path / "custom.key").exists()


def test_open_ledger_rotates_existing_unkeyed_log(tmp_path):
    log = str(tmp_path / "audit.log")
    AuditLedger(log).record("legacy", target="t1")    # pre-existing unkeyed ledger
    led = open_ledger(_cfg(tmp_path))
    assert led.keyed and led.verify().ok
    archives = list(tmp_path.glob("audit.log.unkeyed-*"))
    assert len(archives) == 1                          # old log archived, not lost
    assert AuditLedger(str(archives[0])).verify().ok   # ...and still verifiable unkeyed


def test_open_ledger_keeps_existing_keyed_log(tmp_path):
    kp = str(tmp_path / "audit.key")
    key = load_or_create_key(kp)
    AuditLedger(str(tmp_path / "audit.log"), key=key).record("a", target="t1")
    led = open_ledger(_cfg(tmp_path))
    assert led.keyed and led.verify().ok
    assert not list(tmp_path.glob("audit.log.unkeyed-*"))   # no rotation of an already-keyed log


def test_open_ledger_fail_closed_on_keygen_error(tmp_path, monkeypatch):
    import proximo.audit as audit_mod
    def _boom(_p):
        raise OSError("read-only fs")
    monkeypatch.setattr(audit_mod, "load_or_create_key", _boom)
    with pytest.raises(RuntimeError, match="PROXIMO_AUDIT_KEYED=off"):
        open_ledger(_cfg(tmp_path))


def test_svc_builds_keyed_ledger_by_default(tmp_path, monkeypatch):
    import proximo.server as server
    monkeypatch.setenv("PROXIMO_API_BASE_URL", "https://x:8006/api2/json")
    monkeypatch.setenv("PROXIMO_NODE", "pve")
    monkeypatch.setenv("PROXIMO_TOKEN_PATH", "/run/x")
    monkeypatch.setenv("PROXIMO_AUDIT_LOG", str(tmp_path / "audit.log"))
    server._svc.cache_clear()
    try:
        _, _, _, audit = server._svc()
        assert audit.keyed   # keyed by default through the real factory path
    finally:
        server._svc.cache_clear()


# --- server.audit_verify() tool wiring tests -----------------------------------------------------------------------


def _wire_audit(tmp_path, monkeypatch, *, cfg_head=None, key=None):
    import proximo.server as server
    led = AuditLedger(str(tmp_path / "audit.log"), key=key)
    cfg = SimpleNamespace(expected_head=cfg_head)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, None, None, led))
    return server, led


def test_audit_verify_pins_param_match(tmp_path, monkeypatch):
    server, led = _wire_audit(tmp_path, monkeypatch)
    led.record("a", target="t1")
    out = server.audit_verify(expected_head=led.head())
    assert out["ok"] and out["expected_head"] == led.head() and out["head"] == led.head()


def test_audit_verify_pins_param_mismatch_catches_truncation(tmp_path, monkeypatch):
    server, led = _wire_audit(tmp_path, monkeypatch)
    led.record("a", target="t1")
    led.record("b", target="t2")
    pinned = led.head()
    p = tmp_path / "audit.log"
    p.write_text("\n".join(p.read_text().splitlines()[:-1]) + "\n")  # truncate tail
    out = server.audit_verify(expected_head=pinned)
    assert not out["ok"] and "head mismatch" in out["reason"]
    assert out["expected_head"] == pinned and out["head"] != pinned


def test_audit_verify_falls_back_to_config_default(tmp_path, monkeypatch):
    server, led = _wire_audit(tmp_path, monkeypatch, cfg_head="f" * 64)
    led.record("a", target="t1")
    out = server.audit_verify()                 # no param -> uses cfg.expected_head
    assert not out["ok"] and out["expected_head"] == "f" * 64


def test_audit_verify_unpinned_shows_null(tmp_path, monkeypatch):
    server, led = _wire_audit(tmp_path, monkeypatch)
    led.record("a", target="t1")
    out = server.audit_verify()
    assert out["ok"] and out["expected_head"] is None   # legibly unprotected against tail attacks


# --- migration warning + head-advancement interaction ---------------------------------------------------


def test_open_ledger_migration_warns_and_advances_head(tmp_path):
    log = str(tmp_path / "audit.log")
    AuditLedger(log).record("legacy", target="t1")  # pre-existing unkeyed ledger
    old_head = AuditLedger(log).head()
    with pytest.warns(UserWarning, match="upgraded to keyed mode"):
        led = open_ledger(_cfg(tmp_path))
    new_head = led.head()
    assert new_head != old_head                                   # rotation advanced the head
    assert list(tmp_path.glob("audit.log.unkeyed-*"))             # archived, not lost
    # the known interaction: a stale pin (the pre-migration head) now reads as a head mismatch
    v = led.verify(expected_head=old_head)
    assert not v.ok and "head mismatch" in (v.reason or "")


# --- expected_head shape validation: a typo'd pin is a caller error, not a tamper alarm ----------


def test_looks_like_head_accepts_64_lowercase_hex():
    assert looks_like_head("a" * 64)
    assert looks_like_head(GENESIS_HASH)  # the all-zeros genesis is a valid head shape


def test_looks_like_head_rejects_malformed():
    assert not looks_like_head("xyz")          # too short / nonsense
    assert not looks_like_head("A" * 64)       # uppercase is not a hexdigest shape
    assert not looks_like_head("a" * 63)       # one char short
    assert not looks_like_head("a" * 65)       # one char long
    assert not looks_like_head("g" * 64)       # non-hex character


def test_audit_verify_malformed_pin_raises_not_tamper_alarm(tmp_path, monkeypatch):
    # A fat-fingered pin must raise a CLEAR caller error — never masquerade as a
    # "head mismatch" tamper alarm (crying wolf on a security signal).
    server, led = _wire_audit(tmp_path, monkeypatch)
    led.record("a", target="t1")
    with pytest.raises(ProximoError, match="invalid expected_head"):
        server.audit_verify(expected_head="not-a-real-head")


def test_audit_verify_unpinned_emits_discoverability_hint(tmp_path, monkeypatch):
    # Unpinned = unprotected against tail attacks; the response nudges the operator to pin (legible).
    server, led = _wire_audit(tmp_path, monkeypatch)
    led.record("a", target="t1")
    out = server.audit_verify()
    assert out["hint"] is not None
    assert "PROXIMO_AUDIT_EXPECTED_HEAD" in out["hint"]


def test_audit_verify_pinned_has_no_hint(tmp_path, monkeypatch):
    # A pinned verify is already protected — no nudge.
    server, led = _wire_audit(tmp_path, monkeypatch)
    led.record("a", target="t1")
    out = server.audit_verify(expected_head=led.head())
    assert out["hint"] is None
