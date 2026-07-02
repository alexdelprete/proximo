"""Stage S3 — taint-aware `enforce_envelope_forbid` (design doc
`.scratch/taint-design-v2-2026-07-02.md` §Component 3a): the PRIMARY prompt-injection
enforcement. Once the session's taint marker is present, a pre-declared `PROXIMO_TAINT_FORBID`
set becomes an additional hard forbid wall — no consent escape — checked with the SAME
composite-match/garble-fail-closed machinery as the base envelope forbid wall.

Harness mirrors test_envelope.py's `_wire_server`/`_entries` idiom: a REAL `AuditLedger` backed
by `tmp_path`, calling `envelope.enforce_envelope_forbid` directly (the exact seam under test)
rather than through the full `server._audited` stack.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from proximo import taint, targets
from proximo.audit import AuditLedger
from proximo.backends import ProximoError
from proximo.envelope import _FORBID_ALL_SENTINEL, enforce_envelope_forbid


def _wire(tmp_path) -> tuple[AuditLedger, str, str]:
    """Real ledger backed by tmp_path; returns (ledger, log_path, audit_dir)."""
    log = str(tmp_path / "audit.log")
    led = AuditLedger(log)
    return led, log, str(tmp_path)


def _entries(log_path) -> list[dict]:
    p = Path(log_path)
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("PROXIMO_FORBID", "PROXIMO_TARGETS", "PROXIMO_API_BASE_URL",
                taint.FORBID_ENV, taint.TAINT_TRACK_ENV, taint.REQUIRE_CONSENT_ENV,
                taint.FENCE_ENV):
        monkeypatch.delenv(var, raising=False)
    token = targets._active_target.set(None)
    yield
    targets._active_target.reset(token)


# === Inert invariant =============================================================================


def test_not_tainted_taint_forbid_configured_matching_action_passes(tmp_path, monkeypatch):
    """Taint gate is INERT when the session is clean, even with a matching PROXIMO_TAINT_FORBID
    entry -- taint only sharpens the wall for a session that already read something adversarial."""
    led, log, _audit_dir = _wire(tmp_path)
    monkeypatch.setenv(taint.FORBID_ENV, "pve_firewall_rule_add,delete")

    enforce_envelope_forbid("pve_firewall_rule_add", "pve/firewall", led)  # must NOT raise

    assert _entries(log) == []


def test_tainted_but_taint_forbid_unset_passes(tmp_path, monkeypatch):
    """Tainted, but PROXIMO_TAINT_FORBID is unset -> nothing configured to forbid, inert."""
    led, log, audit_dir = _wire(tmp_path)
    taint.mark_tainted(audit_dir, "ct_exec")
    assert taint.is_tainted(audit_dir) is True

    enforce_envelope_forbid("pve_firewall_rule_add", "pve/firewall", led)  # must NOT raise

    assert _entries(log) == []


# === Headline: tainted + configured + matching -> blocked:taint_forbidden ======================


def test_tainted_matching_action_raises_and_records_taint_forbidden(tmp_path, monkeypatch):
    led, log, audit_dir = _wire(tmp_path)
    monkeypatch.setenv(taint.FORBID_ENV, "pve_firewall_rule_add,delete")
    taint.mark_tainted(audit_dir, "ct_exec")

    with pytest.raises(ProximoError, match="forbidden after an untrusted read"):
        enforce_envelope_forbid("pve_firewall_rule_add", "pve/firewall", led)

    entries = _entries(log)
    assert len(entries) == 1
    assert entries[0]["action"] == "pve_firewall_rule_add"
    assert entries[0]["target"] == "pve/firewall"
    assert entries[0]["mutation"] is True
    assert entries[0]["outcome"] == "blocked:taint_forbidden"
    assert entries[0]["detail"]["taint_forbid"] == ["delete", "pve_firewall_rule_add"]


def test_tainted_nonmatching_action_passes(tmp_path, monkeypatch):
    """Tainted + a taint-forbid set configured, but the action doesn't match any entry -> proceeds
    (the taint wall only forbids what's actually declared, not everything)."""
    led, log, audit_dir = _wire(tmp_path)
    monkeypatch.setenv(taint.FORBID_ENV, "pve_firewall_rule_add,delete")
    taint.mark_tainted(audit_dir, "ct_exec")

    enforce_envelope_forbid("pve_guest_status", "lxc/100", led)  # must NOT raise

    assert _entries(log) == []


# === Composite match (mirror the base _forbidden tests) =========================================


def test_tainted_composite_match_on_target(tmp_path, monkeypatch):
    """The dangerous sub-action can live in the TARGET string (`lxc/100:stop`), not the bare
    action name -- the taint-forbid check reuses the same composite match as the base wall."""
    led, log, audit_dir = _wire(tmp_path)
    monkeypatch.setenv(taint.FORBID_ENV, "stop")
    taint.mark_tainted(audit_dir, "ct_exec")

    with pytest.raises(ProximoError, match="forbidden after an untrusted read"):
        enforce_envelope_forbid("pve_guest_power", "lxc/100:stop", led)

    entries = _entries(log)
    assert len(entries) == 1
    assert entries[0]["outcome"] == "blocked:taint_forbidden"


def test_tainted_composite_match_on_detail_action(tmp_path, monkeypatch):
    """The dangerous sub-action can also live in detail["action"] (e.g. pmg_quarantine_action's
    delete/deliver/whitelist choice)."""
    led, log, audit_dir = _wire(tmp_path)
    monkeypatch.setenv(taint.FORBID_ENV, "delete")
    taint.mark_tainted(audit_dir, "pmg_quarantine_spam")

    with pytest.raises(ProximoError, match="forbidden after an untrusted read"):
        enforce_envelope_forbid("pmg_quarantine_action", "pmg/quarantine/content", led,
                                 detail={"action": "delete"})

    entries = _entries(log)
    assert len(entries) == 1
    assert entries[0]["outcome"] == "blocked:taint_forbidden"
    assert entries[0]["detail"]["action"] == "delete"  # existing detail preserved
    assert entries[0]["detail"]["taint_forbid"] == ["delete"]


def test_tainted_composite_match_does_not_overreach(tmp_path, monkeypatch):
    """A taint-forbidden sub-action string must not blanket-match an unrelated call that merely
    shares the same action/plane but not the sub-action."""
    led, log, audit_dir = _wire(tmp_path)
    monkeypatch.setenv(taint.FORBID_ENV, "stop")
    taint.mark_tainted(audit_dir, "ct_exec")

    enforce_envelope_forbid("pve_guest_power", "lxc/100:start", led)  # must NOT raise

    assert _entries(log) == []


# === Garbled taint-forbid shape (unreachable via real env; exercised at the parse-consumer
# boundary the same way the module docstring names it: taint_forbid_set() returning garbled) ====


def test_tainted_garbled_taint_forbid_collapses_to_forbid_all(tmp_path, monkeypatch):
    """PROXIMO_TAINT_FORBID is always a str via os.environ, so `_parse_forbid` can never actually
    return garbled=True from a real env read (str is never the 'not None/str/list' branch) --
    the garbled path is only reachable if `taint.taint_forbid_set()` itself reports a garbled
    shape. Prove the consumer side (enforce_envelope_forbid) does the right fail-closed thing when
    it does: monkeypatch `taint.taint_forbid_set` to return the garbled shape directly, mirroring
    resolve_envelope's own garble-collapses-to-`_FORBID_ALL_SENTINEL` handling."""
    led, log, audit_dir = _wire(tmp_path)
    taint.mark_tainted(audit_dir, "ct_exec")
    monkeypatch.setattr(taint, "taint_forbid_set", lambda: (frozenset(), True))

    with pytest.raises(ProximoError, match="forbidden after an untrusted read"):
        enforce_envelope_forbid("pve_guest_status", "lxc/100", led)  # even an UNRELATED action

    entries = _entries(log)
    assert len(entries) == 1
    assert entries[0]["outcome"] == "blocked:taint_forbidden"
    assert entries[0]["detail"]["taint_forbid"] == [_FORBID_ALL_SENTINEL]


# === Base-forbid unchanged (still fires blocked:forbidden independently, not tainted) ===========


def test_base_forbid_still_fires_independently_when_not_tainted(tmp_path, monkeypatch):
    led, log, audit_dir = _wire(tmp_path)
    monkeypatch.setenv("PROXIMO_FORBID", "pve_delete_guest")
    assert taint.is_tainted(audit_dir) is False

    with pytest.raises(ProximoError, match="forbidden"):
        enforce_envelope_forbid("pve_delete_guest", "lxc/100", led)

    entries = _entries(log)
    assert len(entries) == 1
    assert entries[0]["outcome"] == "blocked:forbidden"


def test_base_forbid_fires_before_taint_check_even_when_tainted(tmp_path, monkeypatch):
    """Base envelope semantics run FIRST and are untouched by taint -- a base-forbidden action is
    still refused with the ORIGINAL blocked:forbidden outcome, not shadowed/renamed by taint."""
    led, log, audit_dir = _wire(tmp_path)
    monkeypatch.setenv("PROXIMO_FORBID", "pve_delete_guest")
    taint.mark_tainted(audit_dir, "ct_exec")

    with pytest.raises(ProximoError, match="forbidden"):
        enforce_envelope_forbid("pve_delete_guest", "lxc/100", led)

    entries = _entries(log)
    assert len(entries) == 1
    assert entries[0]["outcome"] == "blocked:forbidden"


# === Circular-import sanity (both modules importable standalone) ================================


def test_envelope_and_taint_both_importable_standalone():
    import importlib

    import proximo.envelope as envelope_mod
    import proximo.taint as taint_mod

    importlib.reload(envelope_mod)
    importlib.reload(taint_mod)
    assert hasattr(envelope_mod, "enforce_envelope_forbid")
    assert hasattr(taint_mod, "is_tainted")
