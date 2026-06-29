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


def test_pbs_fingerprint_has_not_yet_wire_enforced_caveat():
    """PROXIMO_PBS_FINGERPRINT must be accompanied by a 'not yet wire-enforced' note.

    The fingerprint field is stored in PbsConfig and surfaced in plans, but httpx
    fingerprint pinning is deferred (see pbs.py module docstring).  The example file
    must not advertise the setting as a live security control — it needs an honest
    caveat so operators know to use PROXIMO_PBS_CA_BUNDLE for cert verification.
    """
    text = _example_text()
    assert "not yet wire-enforced" in text, (
        "proximo.env.example advertises PROXIMO_PBS_FINGERPRINT with no caveat "
        "that fingerprint pinning is not yet wire-enforced at runtime.  "
        "Add a comment near the PROXIMO_PBS_FINGERPRINT line explaining this "
        "and directing operators to PROXIMO_PBS_CA_BUNDLE instead."
    )


def test_pbs_fingerprint_caveat_near_fingerprint_var():
    """The 'not yet wire-enforced' caveat must appear near the PROXIMO_PBS_FINGERPRINT line.

    Guards against the caveat existing elsewhere in the file but not near the
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
    caveat_phrase = "not yet wire-enforced"
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
