"""Console-script shim for ``proximo-a2a``.

The A2A face is an optional extra, but the console script is registered in the base wheel.
Importing ``proximo.a2a.app`` without the extra raises ModuleNotFoundError deep inside the
a2a-sdk import chain; this shim turns that into a one-line install hint instead of a traceback.
"""

from __future__ import annotations

import sys

# Top-level modules the [a2a] extra provides — only their absence means "extra not installed".
# Any other ModuleNotFoundError is a real bug and must traceback, not hide behind the hint.
_EXTRA_MODULES = ("a2a", "uvicorn", "starlette")


def main() -> None:
    try:
        # app.main() imports uvicorn lazily at runtime — probe it HERE so a missing-uvicorn
        # install gets the hint below instead of a raw traceback out of the running app.
        import uvicorn  # noqa: F401

        from proximo.a2a.app import main as a2a_main
    except ModuleNotFoundError as exc:
        # Exact top-level match only: a missing SUBmodule (e.g. 'a2a._core') means the package
        # is installed but broken — that must traceback so the real error is visible.
        missing = exc.name or ""
        if missing not in _EXTRA_MODULES:
            raise
        print(
            f"proximo-a2a needs the optional A2A dependencies ('{missing}' is not installed).\n"
            'Install them with:  pip install "proximo[a2a]"',
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    a2a_main()
