"""The always-on version-drift gate: pyproject == __init__ == CHANGELOG-has-entry."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import version_tools  # noqa: E402


def test_live_repo_is_version_consistent():
    problems = version_tools.check_consistency(REPO_ROOT)
    assert problems == [], "version drift:\n" + "\n".join(problems)


def _server_json(version: str) -> str:
    return (
        "{\n"
        '  "name": "io.github.x/x",\n'
        f'  "version": "{version}",\n'
        '  "packages": [\n'
        "    {\n"
        '      "registryType": "pypi",\n'
        '      "identifier": "x",\n'
        f'      "version": "{version}"\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )


def test_checker_flags_a_mismatch(tmp_path):
    # Build a tiny fake repo with a deliberate pyproject/__init__ mismatch.
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.2.3"\n', encoding="utf-8"
    )
    pkg = tmp_path / "src" / "proximo"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text('__version__ = "9.9.9"\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("## [1.2.3]\n", encoding="utf-8")
    (tmp_path / "server.json").write_text(_server_json("1.2.3"), encoding="utf-8")
    problems = version_tools.check_consistency(tmp_path)
    assert any("!=" in p for p in problems)


def _consistent_repo(tmp_path, v="1.2.3"):
    """A minimal repo that check_consistency passes cleanly, incl. the Debian packaging files."""
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "x"\nversion = "{v}"\n', encoding="utf-8"
    )
    pkg = tmp_path / "src" / "proximo"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(f'__version__ = "{v}"\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(f"## [{v}]\n", encoding="utf-8")
    (tmp_path / "server.json").write_text(_server_json(v), encoding="utf-8")
    deb = tmp_path / "debian"
    deb.mkdir()
    (deb / "proximo.1").write_text(
        f'.TH PROXIMO 1 "July 2026" "proximo {v}" "User Commands"\n.SH NAME\n', encoding="utf-8"
    )
    (deb / "changelog").write_text(f"proximo ({v}-1) UNRELEASED; urgency=medium\n", encoding="utf-8")
    return tmp_path


def test_debian_packaging_files_are_consistent_and_optional(tmp_path):
    # Present + matching -> clean.
    assert version_tools.check_consistency(_consistent_repo(tmp_path)) == []
    # Absent entirely -> still clean (a fork without debian/ is version-consistent).
    import shutil
    shutil.rmtree(tmp_path / "debian")
    assert version_tools.check_consistency(tmp_path) == []


def test_checker_flags_stale_manpage_stamp(tmp_path):
    _consistent_repo(tmp_path)
    (tmp_path / "debian" / "proximo.1").write_text(
        '.TH PROXIMO 1 "July 2026" "proximo 0.0.1" "User Commands"\n', encoding="utf-8"
    )
    problems = version_tools.check_consistency(tmp_path)
    assert any("proximo.1" in p and "!=" in p for p in problems)


def test_checker_flags_stale_debian_changelog(tmp_path):
    _consistent_repo(tmp_path)
    (tmp_path / "debian" / "changelog").write_text(
        "proximo (0.0.1-1) UNRELEASED; urgency=medium\n", encoding="utf-8"
    )
    problems = version_tools.check_consistency(tmp_path)
    assert any("changelog" in p and "!=" in p for p in problems)


def test_set_version_autobumps_the_manpage(tmp_path):
    _consistent_repo(tmp_path, "1.2.3")
    version_tools.set_version(tmp_path, "1.3.0")
    assert 'proximo 1.3.0' in (tmp_path / "debian" / "proximo.1").read_text(encoding="utf-8")


def test_checker_flags_missing_changelog_entry(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.2.3"\n', encoding="utf-8"
    )
    pkg = tmp_path / "src" / "proximo"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text('__version__ = "1.2.3"\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("## [Unreleased]\n", encoding="utf-8")
    (tmp_path / "server.json").write_text(_server_json("1.2.3"), encoding="utf-8")
    problems = version_tools.check_consistency(tmp_path)
    assert any("CHANGELOG" in p for p in problems)


def test_checker_flags_server_json_top_level_mismatch(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.2.3"\n', encoding="utf-8"
    )
    pkg = tmp_path / "src" / "proximo"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text('__version__ = "1.2.3"\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("## [1.2.3]\n", encoding="utf-8")
    (tmp_path / "server.json").write_text(_server_json("1.2.3"), encoding="utf-8")
    # Drift the top-level version only, leaving packages[0].version aligned.
    drifted = (tmp_path / "server.json").read_text(encoding="utf-8").replace(
        '"version": "1.2.3",\n', '"version": "9.9.9",\n', 1
    )
    (tmp_path / "server.json").write_text(drifted, encoding="utf-8")
    problems = version_tools.check_consistency(tmp_path)
    assert any("server.json top-level version" in p for p in problems)


def test_checker_flags_server_json_package_version_mismatch(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.2.3"\n', encoding="utf-8"
    )
    pkg = tmp_path / "src" / "proximo"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text('__version__ = "1.2.3"\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("## [1.2.3]\n", encoding="utf-8")
    (tmp_path / "server.json").write_text(_server_json("1.2.3"), encoding="utf-8")
    # Drift the packages[0].version only, leaving the top-level version aligned.
    drifted = (tmp_path / "server.json").read_text(encoding="utf-8").replace(
        '"version": "1.2.3"\n', '"version": "9.9.9"\n', 1
    )
    (tmp_path / "server.json").write_text(drifted, encoding="utf-8")
    problems = version_tools.check_consistency(tmp_path)
    assert any("server.json packages[0]" in p for p in problems)


def _release_repo(tmp_path: Path, pyproj_ver: str, top_changelog_ver: str | None = None) -> Path:
    top = top_changelog_ver or pyproj_ver
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "x"\nversion = "{pyproj_ver}"\n', encoding="utf-8"
    )
    pkg = tmp_path / "src" / "proximo"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(f'__version__ = "{pyproj_ver}"\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(
        f"## [Unreleased]\n\n## [{top}]\n", encoding="utf-8"
    )
    (tmp_path / "server.json").write_text(_server_json(pyproj_ver), encoding="utf-8")
    return tmp_path


def test_release_check_passes_when_all_aligned(tmp_path):
    root = _release_repo(tmp_path, "0.6.1")
    assert version_tools.check_release(root, "0.6.1") == []


def test_release_check_flags_tag_mismatch(tmp_path):
    root = _release_repo(tmp_path, "0.6.1")
    problems = version_tools.check_release(root, "0.6.2")
    assert any("tag" in p for p in problems)


def test_release_check_flags_changelog_not_top(tmp_path):
    # pyproject 0.6.1, but the top released CHANGELOG heading is 0.7.0 (out of order).
    root = _release_repo(tmp_path, "0.6.1", top_changelog_ver="0.7.0")
    problems = version_tools.check_release(root, "0.6.1")
    assert any("CHANGELOG top" in p for p in problems)
