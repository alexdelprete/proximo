"""Stage 4 — taint -> CONSENT becomes MANDATORY (the in-domain residue).

When the session is tainted (the file-backed marker from taint.py is present) AND the operator has
opted in via PROXIMO_TAINT_REQUIRE_CONSENT, enforce_consent() must REQUIRE a valid out-of-band grant
for this mutation -- even in a deployment that does not require consent globally (PROXIMO_CONSENT_DIR
unset). See .scratch/taint-design-v2-2026-07-02.md Component 3b + the F7 / F1 fail-closed rules.

Reuses the _wire / _consent_dir / _grant / _entries harness idiom from test_consent.py.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import proximo.consent as consent
import proximo.server as server
import proximo.taint as taint
from proximo.audit import AuditLedger
from proximo.backends import ProximoError
from proximo.config import ProximoConfig

_CID = "a" * 64


def _wire(tmp_path, monkeypatch):
    """Wire proximo.server with a real ledger and no live backends (mirrors test_consent.py's _wire)."""
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log, audit_keyed=False,
    )
    led = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, None, None, led))
    return led, log


def _consent_dir(tmp_path, monkeypatch):
    cdir = tmp_path / "consent"
    cdir.mkdir()
    monkeypatch.setenv("PROXIMO_CONSENT_DIR", str(cdir))
    return cdir


def _grant(cdir, consent_id) -> str:
    p = os.path.join(str(cdir), consent_id)
    with open(p, "w", encoding="utf-8") as f:
        f.write("")
    return p


def _entries(log_path) -> list[dict]:
    return [json.loads(ln) for ln in Path(log_path).read_text().splitlines() if ln.strip()]


def _taint(audit_dir: str) -> None:
    taint.mark_tainted(audit_dir, "src")


# --- F7: tainted + require-consent + no consent dir configured => fail-closed refuse -------------


def test_tainted_require_consent_no_dir_configured_fails_closed(tmp_path, monkeypatch):
    """The F7 hole: tainted, PROXIMO_TAINT_REQUIRE_CONSENT=1, PROXIMO_CONSENT_DIR UNSET. The old
    `if not dir_: return` would silently no-op here -- must instead refuse."""
    _wire(tmp_path, monkeypatch)
    audit_dir = str(tmp_path)
    monkeypatch.delenv("PROXIMO_CONSENT_DIR", raising=False)
    monkeypatch.setenv("PROXIMO_TAINT_REQUIRE_CONSENT", "1")
    _taint(audit_dir)
    consent.set_pending_consent(_CID)

    calls = []
    with pytest.raises(ProximoError):
        server._audited("pve_guest_power", "lxc/100", lambda: calls.append(1), mutation=True)
    assert calls == []


def test_tainted_require_consent_no_dir_configured_ledger_outcome(tmp_path, monkeypatch):
    """Ledger records blocked:taint_consent_unconfigured for the F7 case."""
    led, log = _wire(tmp_path, monkeypatch)
    audit_dir = str(tmp_path)
    monkeypatch.delenv("PROXIMO_CONSENT_DIR", raising=False)
    monkeypatch.setenv("PROXIMO_TAINT_REQUIRE_CONSENT", "1")
    _taint(audit_dir)
    consent.set_pending_consent(_CID)

    with pytest.raises(ProximoError):
        server._audited("pve_guest_power", "lxc/100", lambda: {"ok": True}, mutation=True)

    entries = _entries(log)
    assert len(entries) == 1
    assert entries[0]["outcome"] == "blocked:taint_consent_unconfigured"
    assert entries[0]["mutation"] is True


# --- Mandatory-when-tainted: dir set, no grant => refused (the existing flow now MANDATORY) -------


def test_tainted_require_consent_dir_set_no_grant_refused(tmp_path, monkeypatch):
    """Tainted + require-consent + dir set but NO grant present -> refused (mandatory)."""
    _wire(tmp_path, monkeypatch)
    audit_dir = str(tmp_path)
    _consent_dir(tmp_path, monkeypatch)
    monkeypatch.setenv("PROXIMO_TAINT_REQUIRE_CONSENT", "1")
    _taint(audit_dir)
    consent.set_pending_consent(_CID)

    calls = []
    with pytest.raises(ProximoError):
        server._audited("pve_guest_power", "lxc/100", lambda: calls.append(1), mutation=True)
    assert calls == []


def test_tainted_require_consent_dir_set_no_grant_ledger_outcome(tmp_path, monkeypatch):
    led, log = _wire(tmp_path, monkeypatch)
    audit_dir = str(tmp_path)
    _consent_dir(tmp_path, monkeypatch)
    monkeypatch.setenv("PROXIMO_TAINT_REQUIRE_CONSENT", "1")
    _taint(audit_dir)
    consent.set_pending_consent(_CID)

    with pytest.raises(ProximoError):
        server._audited("pve_guest_power", "lxc/100", lambda: {"ok": True}, mutation=True)

    entries = _entries(log)
    assert len(entries) == 1
    assert entries[0]["outcome"] == "blocked:consent_required"


# --- F1: valid grant present => proceeds AND taint marker is NOT cleared -------------------------


def test_tainted_require_consent_valid_grant_proceeds_and_taint_survives(tmp_path, monkeypatch):
    """Tainted + require-consent + dir set + a valid matching grant -> mutation proceeds, AND (F1)
    the taint marker still exists afterward -- consuming a grant must NOT clear taint."""
    _wire(tmp_path, monkeypatch)
    audit_dir = str(tmp_path)
    cdir = _consent_dir(tmp_path, monkeypatch)
    monkeypatch.setenv("PROXIMO_TAINT_REQUIRE_CONSENT", "1")
    _taint(audit_dir)
    consent.set_pending_consent(_CID)
    path = _grant(cdir, _CID)

    calls = []
    resp = server._audited("pve_guest_power", "lxc/100",
                           lambda: calls.append(1) or {"ok": True}, mutation=True)
    assert calls == [1]
    assert resp == {"status": "ok", "result": {"ok": True}}
    assert not os.path.exists(path)  # grant consumed (single-use), unchanged from base consent flow

    assert taint.is_tainted(audit_dir) is True  # F1: consent did NOT clear taint


# --- Inert invariants: the taint gate must not fire when it shouldn't -----------------------------


def test_not_tainted_require_consent_on_dir_unset_is_inert(tmp_path, monkeypatch):
    """NOT tainted + require-consent=1 + dir unset -> passes. Taint gate doesn't fire when clean, and
    the base inert opt-in (no PROXIMO_CONSENT_DIR) is unchanged."""
    _wire(tmp_path, monkeypatch)
    monkeypatch.delenv("PROXIMO_CONSENT_DIR", raising=False)
    monkeypatch.setenv("PROXIMO_TAINT_REQUIRE_CONSENT", "1")
    # deliberately NOT tainted: no mark_tainted call
    consent.set_pending_consent(_CID)

    calls = []
    resp = server._audited("pve_guest_power", "lxc/100",
                           lambda: calls.append(1) or {"ok": True}, mutation=True)
    assert calls == [1]
    assert resp == {"status": "ok", "result": {"ok": True}}


def test_tainted_but_require_consent_off_and_dir_unset_stays_inert(tmp_path, monkeypatch):
    """Tainted + PROXIMO_TAINT_REQUIRE_CONSENT unset/off + dir unset -> unchanged inert opt-in path
    (the base `if not dir_: return`, byte-for-byte as before this stage)."""
    _wire(tmp_path, monkeypatch)
    audit_dir = str(tmp_path)
    monkeypatch.delenv("PROXIMO_CONSENT_DIR", raising=False)
    monkeypatch.delenv("PROXIMO_TAINT_REQUIRE_CONSENT", raising=False)
    _taint(audit_dir)
    consent.set_pending_consent(_CID)

    calls = []
    resp = server._audited("pve_guest_power", "lxc/100",
                           lambda: calls.append(1) or {"ok": True}, mutation=True)
    assert calls == [1]
    assert resp == {"status": "ok", "result": {"ok": True}}


def test_tainted_require_consent_off_explicitly_zero_stays_inert(tmp_path, monkeypatch):
    """PROXIMO_TAINT_REQUIRE_CONSENT=0 (explicit falsy) + tainted + dir unset -> still inert (matches
    taint.py's truthiness gating, not mere presence)."""
    _wire(tmp_path, monkeypatch)
    audit_dir = str(tmp_path)
    monkeypatch.delenv("PROXIMO_CONSENT_DIR", raising=False)
    monkeypatch.setenv("PROXIMO_TAINT_REQUIRE_CONSENT", "0")
    _taint(audit_dir)
    consent.set_pending_consent(_CID)

    calls = []
    resp = server._audited("pve_guest_power", "lxc/100",
                           lambda: calls.append(1) or {"ok": True}, mutation=True)
    assert calls == [1]
    assert resp == {"status": "ok", "result": {"ok": True}}


# --- Existing global-consent behavior is untouched when clean (no taint at all) -------------------


def test_not_tainted_dir_set_no_grant_still_refused_by_base_flow(tmp_path, monkeypatch):
    """Sanity: base (non-taint) consent behavior is untouched -- dir set + no grant refuses regardless
    of taint state, with the ORIGINAL outcome string (not taint-flavored)."""
    led, log = _wire(tmp_path, monkeypatch)
    _consent_dir(tmp_path, monkeypatch)
    # not tainted, PROXIMO_TAINT_REQUIRE_CONSENT unset
    consent.set_pending_consent(_CID)

    with pytest.raises(ProximoError):
        server._audited("pve_guest_power", "lxc/100", lambda: {"ok": True}, mutation=True)

    entries = _entries(log)
    assert entries[0]["outcome"] == "blocked:consent_required"
