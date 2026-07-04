#!/usr/bin/env python3
"""Single source of truth for "where proximo's version lives" + a drift checker.

Version locations kept in sync: pyproject.toml, src/proximo/__init__.py,
CHANGELOG.md (has a release heading), server.json (the MCP registry
manifest — its top-level `version` plus every `packages[].version`), the
Debian man page `.TH` stamp, and the top `debian/changelog` entry's upstream
version. (The man-page stamp auto-bumps on `set`; the Debian changelog entry
is human-added like CHANGELOG.md and only verified here.)

Consumed by:
  - tests/test_version_consistency.py  (the always-on gate)
  - tests/test_version_tools.py        (set_version unit tests)
  - scripts/release.sh                 (set_version on release)
  - .github/workflows, .gitea/workflows (python scripts/version_tools.py check)

Stdlib only — tomllib ships on the project's Python floor (>=3.12).
"""
from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = "pyproject.toml"
INIT = "src/proximo/__init__.py"
CHANGELOG = "CHANGELOG.md"
SERVER_JSON = "server.json"
MANPAGE = "debian/proximo.1"
DEBIAN_CHANGELOG = "debian/changelog"

_INIT_RE = re.compile(r'(?m)^__version__\s*=\s*"([^"]+)"')
_HEADING_RE = re.compile(r'(?m)^##\s*\[([^\]]+)\]')
_SERVER_JSON_VERSION_RE = re.compile(r'"version"\s*:\s*"[^"]*"')
# man page .TH line:  .TH PROXIMO 1 "July 2026" "proximo 0.15.0" "User Commands"
_MANPAGE_RE = re.compile(r'"proximo\s+([0-9][^"]*)"')
# debian/changelog top entry:  proximo (0.15.0-1) UNRELEASED; ...
_DEB_CHANGELOG_RE = re.compile(r'(?m)^proximo\s+\(([0-9][^-)~]*)')


def read_pyproject_version(root: Path) -> str:
    data = tomllib.loads((root / PYPROJECT).read_text(encoding="utf-8"))
    return data["project"]["version"]


def read_init_version(root: Path) -> str:
    m = _INIT_RE.search((root / INIT).read_text(encoding="utf-8"))
    if not m:
        raise ValueError(f"no __version__ found in {INIT}")
    return m.group(1)


def read_server_json_versions(root: Path) -> list[tuple[str, str]]:
    """Return (label, version) for every version field in server.json (the MCP
    registry manifest): the top-level `version` plus each `packages[].version`.
    """
    data = json.loads((root / SERVER_JSON).read_text(encoding="utf-8"))
    versions: list[tuple[str, str]] = []
    if "version" in data:
        versions.append((f"{SERVER_JSON} top-level version", data["version"]))
    for i, pkg in enumerate(data.get("packages", [])):
        if "version" in pkg:
            ident = pkg.get("identifier", f"packages[{i}]")
            versions.append((f"{SERVER_JSON} packages[{i}] ({ident}) version", pkg["version"]))
    return versions


def read_manpage_version(root: Path) -> str:
    m = _MANPAGE_RE.search((root / MANPAGE).read_text(encoding="utf-8"))
    if not m:
        raise ValueError(f'no "proximo <version>" .TH stamp found in {MANPAGE}')
    return m.group(1)


def read_debian_changelog_version(root: Path) -> str:
    """Upstream version of the TOP debian/changelog entry (the part before the -N revision)."""
    m = _DEB_CHANGELOG_RE.search((root / DEBIAN_CHANGELOG).read_text(encoding="utf-8"))
    if not m:
        raise ValueError(f"no leading 'proximo (X.Y.Z-N)' entry found in {DEBIAN_CHANGELOG}")
    return m.group(1)


def read_changelog_headings(root: Path) -> list[str]:
    text = (root / CHANGELOG).read_text(encoding="utf-8")
    return [h.strip() for h in _HEADING_RE.findall(text)]


def top_released_changelog_version(root: Path) -> str | None:
    for h in read_changelog_headings(root):
        if h.lower() != "unreleased":
            return h
    return None


def check_consistency(root: Path) -> list[str]:
    """Always-on checks. Returns problems; empty == consistent."""
    problems: list[str] = []
    py = read_pyproject_version(root)
    init = read_init_version(root)
    if py != init:
        problems.append(f"pyproject version {py!r} != __init__ __version__ {init!r}")
    for label, v in read_server_json_versions(root):
        if v != py:
            problems.append(f"{label} {v!r} != pyproject version {py!r}")
    if py not in set(read_changelog_headings(root)):
        problems.append(
            f"CHANGELOG has no '## [{py}]' heading for version {py!r} "
            f"(add the release entry — a bare '## [Unreleased]' does not satisfy this)"
        )
    # Debian packaging is optional in a checkout — only enforce these when the files exist.
    if (root / MANPAGE).exists():
        man = read_manpage_version(root)
        if man != py:
            problems.append(f"{MANPAGE} .TH version {man!r} != pyproject version {py!r}")
    if (root / DEBIAN_CHANGELOG).exists():
        deb = read_debian_changelog_version(root)
        if deb != py:
            problems.append(
                f"{DEBIAN_CHANGELOG} top entry upstream version {deb!r} != pyproject version {py!r} "
                f"(add a 'proximo ({py}-1) ...' entry above the older ones)"
            )
    return problems


def check_release(root: Path, tag_version: str) -> list[str]:
    """Release-time checks: tag == pyproject == __init__ == CHANGELOG top released heading.

    Stricter than check_consistency: the git tag must match, and the version must be
    the TOP released CHANGELOG entry (catches out-of-order / stale headings).
    """
    problems = check_consistency(root)
    py = read_pyproject_version(root)
    if tag_version != py:
        problems.append(f"git tag version {tag_version!r} != pyproject version {py!r}")
    top = top_released_changelog_version(root)
    if top != py:
        problems.append(f"CHANGELOG top released heading {top!r} != version {py!r}")
    return problems


def set_version(root: Path, version: str) -> None:
    """Rewrite the version in pyproject.toml, src/proximo/__init__.py, and every
    version field in server.json (top-level + each packages[] entry)."""
    pp = root / PYPROJECT
    pp_new, n = re.subn(
        r'(?m)^version\s*=\s*"[^"]*"', f'version = "{version}"',
        pp.read_text(encoding="utf-8"), count=1,
    )
    if n != 1:
        raise ValueError(f"expected exactly one top-level version= in {PYPROJECT}, found {n}")
    pp.write_text(pp_new, encoding="utf-8")

    init = root / INIT
    init_new, n = re.subn(
        r'(?m)^__version__\s*=\s*"[^"]*"', f'__version__ = "{version}"',
        init.read_text(encoding="utf-8"), count=1,
    )
    if n != 1:
        raise ValueError(f"expected exactly one __version__= in {INIT}, found {n}")
    init.write_text(init_new, encoding="utf-8")

    sj = root / SERVER_JSON
    sj_text = sj.read_text(encoding="utf-8")
    sj_new, n = _SERVER_JSON_VERSION_RE.subn(f'"version": "{version}"', sj_text)
    if n == 0:
        raise ValueError(f'expected at least one "version": ... field in {SERVER_JSON}, found 0')
    sj.write_text(sj_new, encoding="utf-8")

    # Man-page .TH stamp auto-bumps (a plain literal), when the packaging file is present; the
    # debian/changelog entry is NOT rewritten here — a native-package changelog is human-authored
    # append-a-dated-entry, verified by check_consistency.
    mp = root / MANPAGE
    if mp.exists():
        mp_new, n = _MANPAGE_RE.subn(f'"proximo {version}"', mp.read_text(encoding="utf-8"), count=1)
        if n != 1:
            raise ValueError(f'expected exactly one "proximo <version>" stamp in {MANPAGE}, found {n}')
        mp.write_text(mp_new, encoding="utf-8")


def _main(argv: list[str]) -> int:
    if argv[:1] == ["check"]:
        problems = check_consistency(REPO_ROOT)
        if problems:
            print("version drift:")
            for p in problems:
                print(f"  - {p}")
            return 1
        print(f"version consistent: {read_pyproject_version(REPO_ROOT)}")
        return 0
    if len(argv) == 2 and argv[0] == "release-check":
        tag = argv[1]
        tag = tag[1:] if tag.startswith("v") else tag
        problems = check_release(REPO_ROOT, tag)
        if problems:
            print("release drift:")
            for p in problems:
                print(f"  - {p}")
            return 1
        print(f"release consistent: {read_pyproject_version(REPO_ROOT)}")
        return 0
    if len(argv) == 2 and argv[0] == "set":
        set_version(REPO_ROOT, argv[1])
        print(f"set version -> {argv[1]}")
        return 0
    print("usage: version_tools.py [check | release-check vX.Y.Z | set X.Y.Z]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
