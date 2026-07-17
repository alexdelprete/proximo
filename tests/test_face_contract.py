"""The transport-face contract, made structural: a face is a mouth, not a brain.

Transport-agnosticism is only real if it's enforced. Every network face must (1) route tool
calls through ``governed.call_governed``/``list_governed`` — never import a Proxmox backend or
call the service builders directly, (2) touch ``server`` only for the two sanctioned seams
(``_apply_surfaces`` registry scoping, ``_ledger`` rejection audits), and (3) mount the ONE
shared perimeter stack from ``webguard.guard_middleware``, in its contract order. A new face
(e.g. MCP over streamable HTTP) inherits the spine by following these imports; this test
refuses the shortcut that would give a transport its own path.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "proximo"

# Every module that implements or enters a network face. A NEW FACE MUST BE ADDED HERE —
# test_new_face_modules_are_listed below fails if a face-shaped module appears unlisted.
FACE_SOURCES = (
    "httpface.py",
    "_http_entry.py",
    "_a2a_entry.py",
    "a2a/app.py",
    "a2a/executor.py",
    "a2a/card.py",
    "a2a/signing.py",
    "a2a/__main__.py",
    "a2a/__init__.py",
)

# A face must never reach these — they are the core's internals, behind the governed dispatch.
FORBIDDEN = (
    r"\bfrom \.+backends\b",          # the Proxmox client builders
    r"\bimport backends\b",
    r"\bProxmoxAPI\b",                # the raw client
    r"server\._svc\b",                # service builders — the spine wraps these
    r"server\._pbs\b",
    r"server\._pmg\b",
    r"server\._pdm\b",
    r"\b_audited\s*\(",               # calling the funnel directly = skipping name-based dispatch
)

# The ONLY server attributes a face may touch (the two sanctioned seams).
ALLOWED_SERVER_ATTRS = {"_apply_surfaces", "_ledger"}


def _source(rel: str) -> str:
    return (SRC / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize("rel", FACE_SOURCES)
def test_face_never_touches_core_internals(rel):
    text = _source(rel)
    hits = [pat for pat in FORBIDDEN if re.search(pat, text)]
    assert not hits, f"{rel} reaches core internals ({hits}) — faces go through governed.call_governed."


@pytest.mark.parametrize("rel", FACE_SOURCES)
def test_face_server_seams_are_the_sanctioned_two(rel):
    text = _source(rel)
    # (?<!a2a\.) — `a2a.server.*` is the A2A SDK's namespace, not proximo's server module.
    used = set(re.findall(r"(?<!a2a\.)\bserver\.(\w+)", text))
    stray = used - ALLOWED_SERVER_ATTRS
    assert not stray, (
        f"{rel} uses server.{sorted(stray)} — a face may touch only "
        f"{sorted(ALLOWED_SERVER_ATTRS)}; everything else goes through the governed dispatch."
    )


def test_tool_calling_faces_route_through_governed():
    # The two modules that actually execute tools must do it via the governed dispatch.
    for rel in ("httpface.py", "a2a/executor.py"):
        assert "call_governed" in _source(rel), f"{rel} does not route through governed.call_governed"


def test_new_face_modules_are_listed():
    """A face-shaped module (mounts middleware / serves a port) must be in FACE_SOURCES."""
    face_shaped = re.compile(r"guard_middleware|uvicorn\.run|Starlette\(")
    listed = {str(Path(rel)) for rel in FACE_SOURCES}
    for path in SRC.rglob("*.py"):
        rel = str(path.relative_to(SRC))
        if rel.startswith(("tools/",)) or rel in ("webguard.py",):
            continue
        if rel in listed:
            continue
        text = path.read_text(encoding="utf-8")
        assert not face_shaped.search(text), (
            f"{rel} looks like a transport face (middleware/serve/Starlette) but is not in "
            f"FACE_SOURCES — add it so the contract covers it."
        )


def _middleware_names(app) -> list[str]:
    return [m.cls.__name__ for m in app.user_middleware]


def test_faces_mount_the_same_perimeter_in_contract_order():
    """Both factories produce the identical guard stack — the faces cannot drift."""
    a2a_app_mod = pytest.importorskip("proximo.a2a.app")
    from proximo.httpface import build_app as build_http

    with_token = ["TrustedHostMiddleware", "CrossOriginGuardMiddleware", "BearerAuthMiddleware"]
    without = ["TrustedHostMiddleware", "CrossOriginGuardMiddleware"]

    assert _middleware_names(build_http(token="sentinel-token")) == with_token
    assert _middleware_names(build_http()) == without
    assert _middleware_names(a2a_app_mod.build_app(token="sentinel-token")) == with_token
    assert _middleware_names(a2a_app_mod.build_app()) == without
