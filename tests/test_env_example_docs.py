"""
Structural tests for packaging/proximo.env.example.

Guard that settings advertised in the published example config are accompanied
by honest caveats when the runtime behavior differs from what the setting name
implies.  These tests read the file as text — no env parsing, no imports.
"""

from __future__ import annotations

import pathlib

_EXAMPLE = pathlib.Path(__file__).parent.parent / "packaging" / "proximo.env.example"


def _example_text() -> str:
    return _EXAMPLE.read_text(encoding="utf-8")


def test_pbs_fingerprint_line_exists():
    """Sanity: the PROXIMO_PBS_FINGERPRINT line is still present in the example."""
    assert "PROXIMO_PBS_FINGERPRINT" in _example_text(), (
        "Expected PROXIMO_PBS_FINGERPRINT to appear in proximo.env.example; "
        "remove this test if the line is intentionally dropped."
    )


def test_pbs_fingerprint_documented_as_wire_enforced():
    """PROXIMO_PBS_FINGERPRINT must be documented as WIRE-ENFORCED — and the old
    "not yet wire-enforced" caveat must be GONE.

    History: the caveat was the honest note while pinning was stored-only. Pinning
    is now enforced on the handshake (see pbs.py + _tls.fingerprint_pinned_context),
    so the docs must state the new truth — and must not carry the stale caveat,
    which would now UNDERSELL a live security control.
    """
    text = _example_text()
    assert "not yet wire-enforced" not in text, (
        "proximo.env.example still carries the stale 'not yet wire-enforced' caveat — "
        "fingerprint pinning IS wire-enforced now; the docs must say so"
    )
    assert "WIRE-ENFORCED" in text, (
        "proximo.env.example advertises PROXIMO_PBS_FINGERPRINT with no caveat "
        "that fingerprint pinning is not yet wire-enforced at runtime.  "
        "Add a comment near the PROXIMO_PBS_FINGERPRINT line explaining this "
        "and directing operators to PROXIMO_PBS_CA_BUNDLE instead."
    )


def test_pbs_fingerprint_caveat_near_fingerprint_var():
    """The WIRE-ENFORCED note must appear near the PROXIMO_PBS_FINGERPRINT line.

    Guards against the note existing elsewhere in the file but not near the
    setting it refers to — ensuring an operator reading the PBS section sees it.
    """
    text = _example_text()
    lines = text.splitlines()

    fingerprint_indices = [
        i for i, line in enumerate(lines) if "PROXIMO_PBS_FINGERPRINT" in line
    ]
    assert fingerprint_indices, "PROXIMO_PBS_FINGERPRINT not found in example file"

    # Look for the caveat within ±5 lines of any PROXIMO_PBS_FINGERPRINT mention.
    window = 5
    caveat_phrase = "WIRE-ENFORCED"
    found_nearby = False
    for idx in fingerprint_indices:
        start = max(0, idx - window)
        end = min(len(lines), idx + window + 1)
        nearby = "\n".join(lines[start:end])
        if caveat_phrase in nearby:
            found_nearby = True
            break

    assert found_nearby, (
        f"'{caveat_phrase}' not found within {window} lines of any "
        "PROXIMO_PBS_FINGERPRINT line.  Place the caveat comment directly "
        "above the commented-out fingerprint var so operators see it in context."
    )
