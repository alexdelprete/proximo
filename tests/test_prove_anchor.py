"""Off-box PROVE anchor — smallest first slice (file sink + on-demand export).

Automates the strong PROVE guarantee: pin the ledger head() OFF-BOX and verify against it,
so tail truncation / full wipe / forged append become visible without manual copy-paste.

This slice = a FileSink (write head as JSON to a file — e.g. an NFS mount that Proximo can
POST-to-but-not-rewrite) plus config-load auto-pin and on-demand export from audit_verify().
HTTP/syslog/journal sinks and a background export thread are deliberate later extensions and
are NOT exercised here.

FAIL-CLOSED is the whole point: a configured-but-unreachable anchor is SUSPICIOUS, never
silently skipped. The tests below assert refusal (AnchorError / RuntimeError / ProximoError)
on every unreachable/corrupt path, so a fail-OPEN regression can't slip in green.
"""

from __future__ import annotations

import json
import warnings
from types import SimpleNamespace

import pytest

from proximo.audit import AuditLedger
from proximo.audit_anchor import AnchorError, FileSink, build_anchor_sink
from proximo.config import ProximoConfig

_HEAD = "a" * 64
_OTHER_HEAD = "b" * 64


# --- FileSink: publish + fetch round-trip -----------------------------------------------------


def test_anchor_file_sink_publish_and_fetch(tmp_path):
    """FileSink.publish writes the head off-box; last_head() reads exactly that value back."""
    sink = FileSink(str(tmp_path / "anchor.json"))
    sink.publish(_HEAD, "2026-07-01T00:00:00+00:00", "pve", "/var/log/audit.log")
    assert sink.last_head() == _HEAD
    # Payload carries the documented shape (head + provenance), stored as parseable JSON.
    payload = json.loads((tmp_path / "anchor.json").read_text())
    assert payload["head"] == _HEAD
    assert payload["node"] == "pve"
    assert payload["ledger_path"] == "/var/log/audit.log"
    assert payload["ts"] == "2026-07-01T00:00:00+00:00"


def test_anchor_file_sink_publish_overwrites(tmp_path):
    """Idempotent: publishing a newer head overwrites the prior pin (latest head always wins)."""
    sink = FileSink(str(tmp_path / "anchor.json"))
    sink.publish(_HEAD, "t1", "pve", "/l")
    sink.publish(_OTHER_HEAD, "t2", "pve", "/l")
    assert sink.last_head() == _OTHER_HEAD


def test_anchor_file_sink_last_head_none_on_first_run(tmp_path):
    """Sink reachable but empty (file absent, parent dir present) => None (normal first run)."""
    sink = FileSink(str(tmp_path / "anchor.json"))
    assert sink.last_head() is None


# --- FileSink: fail-closed on every unreachable / corrupt path --------------------------------


def test_anchor_file_sink_missing_dir_publish_fail_closed(tmp_path):
    """Publish into a nonexistent parent directory => AnchorError (never a silent no-op)."""
    sink = FileSink(str(tmp_path / "nope" / "anchor.json"))
    with pytest.raises(AnchorError):
        sink.publish(_HEAD, "t", "pve", "/l")


def test_anchor_file_sink_missing_dir_fetch_fail_closed(tmp_path):
    """last_head() when the destination DIRECTORY is gone => AnchorError, NOT None.

    A missing file whose parent exists is a legit first run (None). A missing *directory* means
    the sink is unreachable/misconfigured — treat it as suspicious and fail closed, so config
    can refuse to start rather than run with tail-attack detection silently disabled.
    """
    sink = FileSink(str(tmp_path / "nope" / "anchor.json"))
    with pytest.raises(AnchorError):
        sink.last_head()


def test_anchor_file_sink_corrupt_fail_closed(tmp_path):
    """A non-JSON anchor file => AnchorError (corruption/tamper of the sink itself)."""
    p = tmp_path / "anchor.json"
    p.write_text("not json {{{")
    with pytest.raises(AnchorError):
        FileSink(str(p)).last_head()


def test_anchor_file_sink_malformed_head_fail_closed(tmp_path):
    """A JSON anchor whose 'head' isn't a 64-hex head() value => AnchorError."""
    p = tmp_path / "anchor.json"
    p.write_text(json.dumps({"head": "deadbeef"}))
    with pytest.raises(AnchorError):
        FileSink(str(p)).last_head()


def test_anchor_file_sink_missing_head_key_fail_closed(tmp_path):
    """A JSON anchor with no 'head' key => AnchorError (not a silent None)."""
    p = tmp_path / "anchor.json"
    p.write_text(json.dumps({"ts": "t"}))
    with pytest.raises(AnchorError):
        FileSink(str(p)).last_head()


# --- build_anchor_sink: config-factory validation ---------------------------------------------


def test_build_anchor_sink_none_disabled():
    assert build_anchor_sink("none", None) is None
    assert build_anchor_sink("", None) is None


def test_build_anchor_sink_file_requires_path():
    with pytest.raises(RuntimeError, match="(?i)PROXIMO_AUDIT_ANCHOR_FILE_PATH"):
        build_anchor_sink("file", None)


def test_build_anchor_sink_unknown_type_fails():
    with pytest.raises(RuntimeError, match="(?i)not a recognized sink"):
        build_anchor_sink("s3", None)


def test_build_anchor_sink_file_ok(tmp_path):
    sink = build_anchor_sink("file", str(tmp_path / "anchor.json"))
    assert isinstance(sink, FileSink)
    assert sink.name == "file"


# --- config wiring: from_env parses + auto-pins, fails closed ---------------------------------


def _base_env(monkeypatch, **extra):
    monkeypatch.setenv("PROXIMO_API_BASE_URL", "https://x:8006/api2/json")
    monkeypatch.setenv("PROXIMO_NODE", "pve")
    monkeypatch.setenv("PROXIMO_TOKEN_PATH", "/run/x")
    for k, v in extra.items():
        monkeypatch.setenv(k, v)


def test_config_anchor_none_by_default(monkeypatch):
    _base_env(monkeypatch)
    assert ProximoConfig.from_env().anchor_sink is None


def test_config_from_env_file_anchor(monkeypatch, tmp_path):
    anchor = tmp_path / "anchor.json"
    FileSink(str(anchor)).publish(_HEAD, "t", "pve", "/l")
    _base_env(
        monkeypatch,
        PROXIMO_AUDIT_ANCHOR_SINK="file",
        PROXIMO_AUDIT_ANCHOR_FILE_PATH=str(anchor),
    )
    cfg = ProximoConfig.from_env()
    assert isinstance(cfg.anchor_sink, FileSink)
    # No manual pin => the off-box anchor auto-pins expected_head (tail-attack detection is now on).
    assert cfg.expected_head == _HEAD


def test_config_file_anchor_empty_sink_first_run_no_pin(monkeypatch, tmp_path):
    """Configured sink but empty (first run) => sink wired, expected_head stays unpinned (None)."""
    _base_env(
        monkeypatch,
        PROXIMO_AUDIT_ANCHOR_SINK="file",
        PROXIMO_AUDIT_ANCHOR_FILE_PATH=str(tmp_path / "anchor.json"),
    )
    cfg = ProximoConfig.from_env()
    assert isinstance(cfg.anchor_sink, FileSink)
    assert cfg.expected_head is None


def test_config_file_anchor_missing_path_fails(monkeypatch, tmp_path):
    """Configured anchor whose destination directory is gone => REFUSE to start (fail-closed)."""
    _base_env(
        monkeypatch,
        PROXIMO_AUDIT_ANCHOR_SINK="file",
        PROXIMO_AUDIT_ANCHOR_FILE_PATH=str(tmp_path / "gone" / "anchor.json"),
    )
    with pytest.raises(RuntimeError, match="(?i)anchor"):
        ProximoConfig.from_env()


def test_config_file_anchor_requires_path_fails(monkeypatch):
    """sink=file with no PROXIMO_AUDIT_ANCHOR_FILE_PATH => refuse to start."""
    _base_env(monkeypatch, PROXIMO_AUDIT_ANCHOR_SINK="file")
    monkeypatch.delenv("PROXIMO_AUDIT_ANCHOR_FILE_PATH", raising=False)
    with pytest.raises(RuntimeError, match="(?i)PROXIMO_AUDIT_ANCHOR_FILE_PATH"):
        ProximoConfig.from_env()


def test_config_manual_pin_differs_from_sink_warns(monkeypatch, tmp_path):
    """Manual pin AND sink pin, differing => warn but HONOR the manual pin (sink is advisory)."""
    anchor = tmp_path / "anchor.json"
    FileSink(str(anchor)).publish(_OTHER_HEAD, "t", "pve", "/l")
    _base_env(
        monkeypatch,
        PROXIMO_AUDIT_EXPECTED_HEAD=_HEAD,
        PROXIMO_AUDIT_ANCHOR_SINK="file",
        PROXIMO_AUDIT_ANCHOR_FILE_PATH=str(anchor),
    )
    with pytest.warns(UserWarning, match="(?i)manual|differs|anchor"):
        cfg = ProximoConfig.from_env()
    assert cfg.expected_head == _HEAD  # manual pin wins


def test_config_manual_pin_matches_sink_no_warn(monkeypatch, tmp_path):
    """Manual pin == sink pin => no drift warning."""
    anchor = tmp_path / "anchor.json"
    FileSink(str(anchor)).publish(_HEAD, "t", "pve", "/l")
    _base_env(
        monkeypatch,
        PROXIMO_AUDIT_EXPECTED_HEAD=_HEAD,
        PROXIMO_AUDIT_ANCHOR_SINK="file",
        PROXIMO_AUDIT_ANCHOR_FILE_PATH=str(anchor),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        cfg = ProximoConfig.from_env()
    assert cfg.expected_head == _HEAD


# --- server.audit_verify(): on-demand export + anchor metadata --------------------------------


def _wire_audit(monkeypatch, tmp_path, *, anchor_sink=None, cfg_head=None):
    import proximo.server as server

    led = AuditLedger(str(tmp_path / "audit.log"))
    cfg = SimpleNamespace(expected_head=cfg_head, node="pve", anchor_sink=anchor_sink)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, None, None, led))
    return server, led


def test_audit_verify_with_file_anchor_on_demand(monkeypatch, tmp_path):
    """audit_verify with a configured sink exports the live head on-demand and reports it."""
    import proximo.server as server  # noqa: F401  (imported for symmetry / clarity)

    anchor = tmp_path / "anchor.json"
    sink = FileSink(str(anchor))
    srv, led = _wire_audit(monkeypatch, tmp_path, anchor_sink=sink)
    led.record("a", target="t1")

    out = srv.audit_verify()
    assert out["ok"] is True
    assert out["anchor_sink"] == "file"
    assert out["anchor_last_export"] is not None
    # The sink now holds the CURRENT head — the anchor tracked the ledger automatically.
    assert sink.last_head() == led.head()


def test_audit_verify_no_anchor_reports_null_metadata(monkeypatch, tmp_path):
    """No sink configured => anchor metadata is present-but-null (legible, backward-compatible)."""
    srv, led = _wire_audit(monkeypatch, tmp_path, anchor_sink=None)
    led.record("a", target="t1")
    out = srv.audit_verify()
    assert out["anchor_sink"] is None
    assert out["anchor_last_export"] is None


def test_audit_verify_forward_growth_holds_pin_and_hints_forward(monkeypatch, tmp_path):
    """Legit forward growth past an EXISTING off-box pin: the pin is HELD (never auto-advanced, so a
    truncation can't ride the same path to poison it), and the anchor_hint says the ledger grew
    FORWARD (benign stale-pin lag) rather than firing a silent tamper alarm. The anti-poisoning
    invariant wearing its benign face — the count discriminates forward growth from a shrink."""
    anchor = tmp_path / "anchor.json"
    sink = FileSink(str(anchor))
    srv, led = _wire_audit(monkeypatch, tmp_path, anchor_sink=sink)
    led.record("a", target="t1")
    pinned = led.head()
    sink.publish(pinned, "t0", "pve", str(led.path), entries=1)   # an EXISTING pin at 1 entry
    led.record("b", target="t2")                                   # ledger grows forward -> 2 entries

    import proximo.server as server
    cfg = SimpleNamespace(expected_head=pinned, node="pve", anchor_sink=sink)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, None, None, led))
    out = server.audit_verify()

    assert out["ok"] is False and "head mismatch" in out["reason"]
    assert out["anchor_hint"] is not None and "forward" in out["anchor_hint"].lower()
    assert out["anchor_last_export"] is None          # pin was NOT auto-advanced
    assert sink.last_head() == pinned                 # pin HELD at the pre-growth head


def test_audit_verify_anchor_publish_failure_fails_closed(monkeypatch, tmp_path):
    """On-demand export failure => the audit_verify call FAILS (fail-closed), never silent success.

    A configured anchor that can't be written is suspicious; the operator must see it, not get a
    green verify while the off-box pin silently went stale.
    """
    from proximo.backends import ProximoError

    class _BrokenSink(FileSink):
        def publish(self, head, ts, node, ledger_path, entries=None):
            raise AnchorError("sink down")

    broken = _BrokenSink(str(tmp_path / "anchor.json"))
    srv, led = _wire_audit(monkeypatch, tmp_path, anchor_sink=broken)
    led.record("a", target="t1")
    with pytest.raises(ProximoError, match="(?i)anchor"):
        srv.audit_verify()


# --- Anti-poisoning invariant: audit_verify must NEVER move the pin to a tampered head ---------
# The whole value of the off-box anchor is detecting tail truncation / wipe. If a verify that
# DETECTS an attack then re-pins the anchor to the tampered head, the attack becomes permanently
# invisible after the next restart re-pins from the poisoned anchor. The single invariant below —
# "the pin never changes to a head other than the previously-pinned one" — catches truncation,
# full wipe, and the expected_head='' one-shot in one assertion.


def _truncate_last_entry(log_path):
    lines = log_path.read_text().splitlines()
    log_path.write_text(("\n".join(lines[:-1]) + "\n") if len(lines) > 1 else "")


def test_audit_verify_truncation_does_not_poison_pin(monkeypatch, tmp_path):
    """Ledger truncated after the pin => audit_verify reports ok:False AND leaves the pin UNCHANGED
    (it must not re-publish the tampered head over the good off-box pin)."""
    import proximo.server as server

    sink = FileSink(str(tmp_path / "anchor.json"))
    led = AuditLedger(str(tmp_path / "audit.log"))
    led.record("a", target="t1")
    led.record("b", target="t2")
    led.record("c", target="t3")
    pinned = led.head()
    sink.publish(pinned, "t0", "pve", str(led.path))   # establish the off-box pin at H3

    _truncate_last_entry(tmp_path / "audit.log")        # attacker lops the last entry -> head H2

    cfg = SimpleNamespace(expected_head=pinned, node="pve", anchor_sink=sink)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, None, None, led))
    out = server.audit_verify()

    assert out["ok"] is False                           # truncation detected
    assert sink.last_head() == pinned                   # INVARIANT: pin NOT poisoned


def test_audit_verify_empty_expected_head_does_not_poison_pin(monkeypatch, tmp_path):
    """The one-shot: expected_head='' normalizes to no pin, so verify can't see truncation on its
    own (ok:True) — but the on-demand export must STILL not advance the off-box pin to the
    truncated head."""
    import proximo.server as server

    sink = FileSink(str(tmp_path / "anchor.json"))
    led = AuditLedger(str(tmp_path / "audit.log"))
    led.record("a", target="t1")
    led.record("b", target="t2")
    pinned = led.head()
    sink.publish(pinned, "t0", "pve", str(led.path))

    _truncate_last_entry(tmp_path / "audit.log")

    cfg = SimpleNamespace(expected_head=None, node="pve", anchor_sink=sink)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, None, None, led))
    server.audit_verify(expected_head="")

    assert sink.last_head() == pinned                   # INVARIANT: pin NOT poisoned
