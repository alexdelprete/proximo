"""Tests for the release leak-audit — it models the PUBLIC publish transform.

Pure logic (path partition + leak-shape scan + allowlist + inline-allow marker) is unit-tested
with synthetic inputs; the git I/O (`files_in_ref`, `build_public_tree`) is tested against the
real repo. `test_current_public_surface_is_leak_clean` is the live gate: the actual tree that
would publish (after stripping deny paths) must carry no leak shapes.

NOTE: fixtures here use FAKE-but-flaggable values (a made-up internal-TLD host, a 172.31.x private
IP, a fake /root-style path), never real infrastructure, and each fixture line carries a
`leak-audit: allow` marker so this file stays clean under its own live gate.
"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import release_leak_audit as rla  # noqa: E402


def _git_out(args: list[str]) -> str:
    return subprocess.run(["git", *args], cwd=str(REPO_ROOT),  # noqa: S603, S607
                          capture_output=True, text=True, check=True).stdout


# --- pure: deny-path partition ---
def test_deny_prefixed_paths_are_stripped_not_kept():
    files = {".gitea/workflows/ci.yml": "x", "src/proximo/server.py": "y"}
    res = rla.audit_files(files)
    assert ".gitea/workflows/ci.yml" in res.stripped
    assert "src/proximo/server.py" in res.kept
    assert ".gitea/workflows/ci.yml" not in res.kept


def test_leak_inside_a_stripped_file_is_not_reported():
    # An internal host inside .gitea is removed from the public tree, so it must NOT be a finding.
    files = {".gitea/workflows/ci.yml": "url=forge.internal:3000"}  # leak-audit: allow
    res = rla.audit_files(files)
    assert res.ok
    assert res.findings == []


# --- pure: content leak shapes ---
def test_internal_tld_hostname_is_flagged():
    files = {"docs/x.md": "clone from forge.internal:3000 today"}  # leak-audit: allow
    res = rla.audit_files(files)
    assert any(f.kind == "internal-host" for f in res.findings)


def test_rfc1918_ip_is_flagged():
    files = {"smoke.py": "API = 172.31.0.99 here"}  # leak-audit: allow
    res = rla.audit_files(files)
    assert any(f.kind == "rfc1918-ip" for f in res.findings)


def test_absolute_root_path_is_flagged():
    files = {"a.py": "open('/root/secret/file')"}  # leak-audit: allow
    res = rla.audit_files(files)
    assert any(f.kind == "root-path" for f in res.findings)


def test_pypi_token_shape_is_flagged():
    files = {"a.py": "T = 'pypi-AgEIcHlwaS5vcmcAbcd1234EFGHijkl5678'"}  # leak-audit: allow
    res = rla.audit_files(files)
    assert any(f.kind == "token" for f in res.findings)


def test_root_ellipsis_placeholder_is_not_flagged():
    # `/root/...` in prose is rule-text, not a real path.
    files = {"CLAUDE.md": "no absolute `/root/...` paths in tracked files"}
    assert rla.audit_files(files).ok


def test_root_in_grep_pattern_is_not_flagged():
    # `/root/` as a delimiter inside a leak-grep pattern is documentation, not a path.
    files = {"docs/p.md": "grep -nE '/root/|secret' diff"}
    assert rla.audit_files(files).ok


def test_finding_records_path_and_line():
    files = {"a.py": "ok line\nbad = 172.31.9.9\n"}  # leak-audit: allow
    res = rla.audit_files(files)
    hit = next(f for f in res.findings if f.kind == "rfc1918-ip")
    assert hit.path == "a.py"
    assert hit.line == 2


def test_inline_allow_marker_suppresses_that_line():
    files = {"t.md": "ip 172.31.0.5  # leak-audit: allow\nip 172.31.0.6\n"}  # leak-audit: allow
    res = rla.audit_files(files)
    assert all(f.line != 1 for f in res.findings)   # marked line suppressed
    assert any(f.line == 2 for f in res.findings)    # unmarked line still flagged


# --- pure: allowlist of documented examples (must NOT flag) ---
def test_rfc5737_doc_ip_is_allowed():
    files = {"README.md": "PROXIMO_API=https://192.0.2.10:8006"}
    assert rla.audit_files(files).ok


def test_example_sdn_range_is_allowed():
    files = {"scripts/live-smoke/sdn-smoke.py": 'CIDR = "10.99.99.0/24"'}
    assert rla.audit_files(files).ok


def test_example_hostname_is_allowed():
    files = {"README.md": "PROXIMO_API=https://pve.example.com:8006"}
    assert rla.audit_files(files).ok


def test_clean_file_yields_no_findings():
    files = {"src/proximo/server.py": "def main():\n    return 0\n"}
    res = rla.audit_files(files)
    assert res.ok and res.findings == []


# --- integration against the real repo (deterministic) ---
def test_files_in_ref_returns_tracked_text_files():
    files = rla.files_in_ref("HEAD")
    assert "pyproject.toml" in files
    assert isinstance(files["pyproject.toml"], str)
    assert "[project]" in files["pyproject.toml"]


def test_build_public_tree_strips_gitea_keeps_source():
    sha = rla.build_public_tree("HEAD")
    listing = _git_out(["ls-tree", "-r", "--name-only", sha])
    assert "pyproject.toml" in listing
    assert ".gitea/" not in listing


def test_build_public_tree_does_not_touch_real_index_or_worktree():
    before = _git_out(["status", "--porcelain"])
    rla.build_public_tree("HEAD")
    after = _git_out(["status", "--porcelain"])
    assert before == after


def test_current_public_surface_is_leak_clean():
    # The real publish surface (kept files, .gitea stripped) must carry no leak shapes.
    res = rla.audit_files(rla.files_in_ref("HEAD"))
    assert res.ok, "leak shapes in public surface:\n" + "\n".join(
        f"  {f.kind} {f.path}:{f.line}: {f.match}" for f in res.findings
    )
