#!/usr/bin/env python
"""Trust-core mutation smoke — a hand-picked, reproducible mutation test of the PROVE
ledger's tamper-detection logic. NOT a substitute for full mutmut coverage (that pilot is
tracked separately); this proves the *specific* invariants below are killed by the suite.

Each mutation is a one-line change at the heart of AuditLedger.verify(). A mutant is
"killed" if the trust-core test subset FAILS with it applied — i.e. a real test notices
the safety guarantee broke. A "survived" mutant is a coverage gap worth a test.

Run from repo root:  uv run python scripts/mutation_smoke.py
Restores audit.py from git after every mutation (and on exit).
"""
import subprocess
import sys
from pathlib import Path

AUDIT = "src/proximo/audit.py"
TESTS = ["tests/test_ledger.py", "tests/test_audit_harden_0_7_1.py",
         "tests/test_prove_anchor.py"]

# (label, exact source substring, replacement) — each targets one tamper-detection invariant.
MUTATIONS = [
    ("chain-linkage check inverted (prev_hash != prev -> ==)",
     'if entry.get("prev_hash") != prev:',
     'if entry.get("prev_hash") == prev:'),
    ("tamper compare negated (not compare_digest -> compare_digest)",
     "if not hmac.compare_digest(expected, found_hash):",
     "if hmac.compare_digest(expected, found_hash):"),
    ("altered-entry verdict flipped (False -> True)",
     'return LedgerVerification(False, count, lineno, "entry_hash mismatch (entry altered)")',
     'return LedgerVerification(True, count, lineno, "entry_hash mismatch (entry altered)")'),
    ("keyed-downgrade guard inverted (alg != KEY -> ==)",
     "if entry_alg != _KEY_ALG:",
     "if entry_alg == _KEY_ALG:"),
]

src_path = Path(AUDIT)
original = src_path.read_text()


def restore():
    src_path.write_text(original)


def run_tests() -> bool:
    """True = suite passed (mutant SURVIVED); False = suite failed (mutant KILLED)."""
    r = subprocess.run(  # noqa: S603 — dev tool; fixed argv
        [sys.executable, "-m", "pytest", "-x", "-q", *TESTS],
        capture_output=True, text=True,
    )
    return r.returncode == 0


def main() -> int:
    # sanity: clean tree must pass
    if not run_tests():
        print("BASELINE FAILS — fix tests before mutation smoke")
        return 2
    print(f"baseline: trust-core suite green\n{'='*60}")

    killed = survived = 0
    for label, find, repl in MUTATIONS:
        if find not in original:
            print(f"  SKIP  (anchor not found): {label}")
            continue
        src_path.write_text(original.replace(find, repl, 1))
        try:
            passed = run_tests()
        finally:
            restore()
        if passed:
            survived += 1
            print(f"  SURVIVED (coverage gap!): {label}")
        else:
            killed += 1
            print(f"  killed: {label}")

    print(f"{'='*60}\n{killed} killed / {survived} survived  (of {killed+survived} mutants)")
    return 1 if survived else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        restore()
