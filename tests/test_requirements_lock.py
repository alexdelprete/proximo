"""requirements/{runtime,dev}.txt are exports of uv.lock — fail loud when they drift.

CI and the Dockerfile install with `pip --require-hashes` against these files; a stale
export silently pins yesterday's dependency set. This test re-exports from uv.lock and
compares the requirement lines (header comments carry the generating command/path, so
only non-comment content is compared). Skips where uv isn't installed (the pip-installed
CI env) — the dev environment and the release gate both run it with uv present.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")

_EXPORTS = {
    "runtime.txt": ["--no-dev", "--no-emit-project"],
    "dev.txt": ["--extra", "dev", "--no-emit-project"],
}


def _content_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln and not ln.lstrip().startswith("#")]


@pytest.mark.parametrize("name", sorted(_EXPORTS))
def test_requirements_export_matches_uv_lock(name, tmp_path):
    committed = REPO_ROOT / "requirements" / name
    assert committed.exists(), f"requirements/{name} missing — run scripts/gen_requirements.sh"

    out = tmp_path / name
    subprocess.run(  # noqa: S603 — fixed argv (same idiom as gen_lobehub_manifest)
        ["uv", "export", *_EXPORTS[name], "--format", "requirements-txt", "-o", str(out)],  # noqa: S607
        cwd=REPO_ROOT, check=True, capture_output=True,
    )
    assert _content_lines(committed.read_text()) == _content_lines(out.read_text()), (
        f"requirements/{name} has drifted from uv.lock — run scripts/gen_requirements.sh "
        f"and commit the result."
    )
