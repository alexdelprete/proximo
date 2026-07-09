"""The always-on copy-drift gate — the story is told once, zones fill slots, nothing accretes.

Companion to test_version_consistency.py: that gate pins version STRINGS; this one pins
copy SHAPE. Canon: docs/plans/internal/COPY-CANON.md (internal-only).
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import copy_ripple_check  # noqa: E402
import version_tools  # noqa: E402

CURRENT = version_tools.read_pyproject_version(REPO_ROOT)


def test_live_repo_copy_is_clean():
    problems = copy_ripple_check.check_repo(REPO_ROOT)
    assert problems == [], "copy drift:\n" + "\n".join(problems)


# --- unit behavior, on synthetic content ---------------------------------


def test_new_in_block_must_match_current_version():
    problems = copy_ripple_check.check_new_in("> **New in 0.1.0 — old.**", "0.2.0")
    assert any("New in" in p for p in problems)
    assert copy_ripple_check.check_new_in("> **New in 0.2.0 — theme.**", "0.2.0") == []


def test_new_in_block_must_not_stack_releases():
    stacked = "> **New in 0.3.0 — a.**\n> **New in 0.2.0 — b.**"
    problems = copy_ripple_check.check_new_in(stacked, "0.3.0")
    assert any("exactly one" in p for p in problems)


def test_status_bullets_capped_and_freshest_first():
    bullets = "\n".join(f"- 🩸 **0.{n}.0** — thing" for n in range(9, 2, -1))  # 7 bullets
    problems = copy_ripple_check.check_status(bullets, "0.9.0")
    assert any("6" in p for p in problems), problems

    ok = "\n".join(f"- 🩸 **0.{n}.0** — thing" for n in range(9, 4, -1))  # 5 bullets
    assert copy_ripple_check.check_status(ok, "0.9.0") == []

    stale_top = "- 🩸 **0.8.0** — thing\n- 🩸 **0.7.0** — thing"
    problems = copy_ripple_check.check_status(stale_top, "0.9.0")
    assert any("top" in p.lower() for p in problems)


def test_tool_count_claims_must_agree():
    text = "It has 364 tools. Later: 360 MCP tools."
    problems = copy_ripple_check.check_tool_counts({"README.md": text}, canonical=364)
    assert any("360" in p for p in problems)


def test_tool_count_ignores_scoped_registration_examples():
    text = (
        "364 tools is the whole estate.\n"
        "`PROXIMO_SURFACES=pve,exec` registers only those planes (that pair = 194 tools).\n"
    )
    assert copy_ripple_check.check_tool_counts({"README.md": text}, canonical=364) == []


def test_tagline_must_survive_on_metadata_surfaces():
    files = {"pyproject.toml": 'description = "A cool Proxmox helper."'}
    problems = copy_ripple_check.check_tagline(files)
    assert any("hand the keys" in p for p in problems)
    files = {"pyproject.toml": 'description = "The Proxmox MCP you can hand the keys."'}
    assert copy_ripple_check.check_tagline(files) == []


def test_satellite_must_carry_current_version():
    problems = copy_ripple_check.check_satellite_text("v0.1.0 is live", "0.2.0", "index.html")
    assert problems and "0.2.0" in problems[0]
    assert copy_ripple_check.check_satellite_text("v0.2.0 is live", "0.2.0", "x") == []
