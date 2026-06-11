"""Tamper-evidence tests — the PROVE pillar's whole point is that these pass."""

from __future__ import annotations

import json
import os
import stat

import pytest

from proximo.audit import _KEY_ALG, GENESIS_HASH, AuditLedger, _hash, load_or_create_key

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
