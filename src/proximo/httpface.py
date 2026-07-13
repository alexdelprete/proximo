"""Proximo HTTP/OpenAPI face — a transport over the governed core.

The full governed tool surface as plain HTTP, for the apps/dashboards/no-code clients (Open WebUI
and the like) that speak REST, not MCP: ``POST /tools/{name}`` with a JSON body of arguments,
discoverable via a generated ``GET /openapi.json``, plus ``GET /healthz``. Every call routes through
``governed.call_governed`` — the same spine path (PLAN-by-default, PROVE, UNDO, the gates, the
Proxmox token scope) an MCP client takes. No transport-local curation, no second mutate path: the
surface and its safety are the core's, uniform for every transport. Scope with ``PROXIMO_SURFACES`` and
the token ACL, exactly like the MCP face.

The face is an optional extra ([http]); the MCP core keeps zero extra deps. Fail-closed perimeter
(shared with A2A in ``proximo.webguard``): non-localhost binds refuse without a bearer token,
constant-time bearer on every ``/tools/*`` op (discovery stays open), a Host/DNS-rebind allowlist,
and a cross-origin (CSRF) guard on the mutating endpoint.
"""

from __future__ import annotations

import os
import sys
import warnings
from typing import Any
from urllib.parse import urlparse

from . import __version__

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 41242  # A2A is 41241; the HTTP face sits beside it
_TOKEN_FILE_ENV = "PROXIMO_HTTP_TOKEN_FILE"  # noqa: S105 -- env var NAME, not a secret value
_TOOLS_PREFIX = "/tools/"


def build_openapi(tools: list[Any], *, secured: bool = False) -> dict[str, Any]:
    """Build the OpenAPI 3.1 document from the governed tool surface (pure — no I/O).

    One ``POST /tools/{name}`` per tool; the request body schema IS the tool's MCP inputSchema
    (already JSON Schema). ``secured=True`` declares the bearer scheme globally so clients know to
    authenticate before they hit a 401.
    """
    paths: dict[str, Any] = {}
    for tool in tools:
        schema = tool.inputSchema if isinstance(tool.inputSchema, dict) else {"type": "object"}
        paths[f"/tools/{tool.name}"] = {
            "post": {
                "operationId": tool.name,
                "summary": tool.name,
                "description": tool.description or "",
                "requestBody": {
                    "required": bool(schema.get("required")),
                    "content": {"application/json": {"schema": schema}},
                },
                "responses": {
                    "200": {"description": "Result (a PLAN for an unconfirmed mutation)."},
                    "400": {"description": "Malformed request (non-object body / missing param)."},
                    "401": {"description": "Missing/invalid bearer token."},
                    "404": {"description": "Unknown tool."},
                    "413": {"description": "Request body too large."},
                    "415": {"description": "Content-Type must be application/json."},
                    "502": {"description": "The tool ran and failed (sanitized)."},
                },
            }
        }

    doc: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": "Proximo",
            "version": __version__,
            "description": (
                "Proximo's governed Proxmox surface over HTTP — the same tools, spine, and token "
                "scope the MCP face exposes. Mutations are PLAN-by-default: without confirm=true you "
                "get a recorded dry-run plan, never a change. Scope with PROXIMO_SURFACES + the "
                "Proxmox token ACL."
            ),
        },
        "paths": paths,
    }
    if secured:
        doc["components"] = {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}}
        doc["security"] = [{"bearerAuth": []}]
    return doc


def _audit_rejection(tool_name: str | None, reason: str) -> None:
    """Best-effort PROVE trace for a REJECTED HTTP call (unknown tool / bad body / malformed).

    The 4xx response is the primary guarantee; this records the rejection to the same tamper-evident
    ledger the tools use, so hostile enumeration of the surface isn't invisible. Uses the tolerant
    ``server._ledger()`` (not ``_svc()``, which raises when the PVE triple is unset — that would
    blackhole the trace during exactly the enumeration it exists to catch). Best-effort: a ledger
    write must never mask the rejection response.
    """
    from . import server  # noqa: PLC0415 -- late import; the app factory stays import-light

    try:
        server._ledger().record("http_rejected", target=str(tool_name or "<none>"), mutation=False,
                                outcome="rejected", detail={"reason": reason})
    except Exception as exc:  # noqa: BLE001 — supplementary audit; never break the rejection path
        warnings.warn(f"HTTP rejection audit failed to record: {type(exc).__name__}", stacklevel=2)


def build_app(url: str | None = None, *, token: str | None = None,
              allowed_hosts: list[str] | None = None):
    """Build the Proximo HTTP-face ASGI application.

    Args:
        url:   Advertised base URL (default ``http://127.0.0.1:41242/``). Its hostname feeds the
               fail-closed public-bind guard and the default Host allowlist.
        token: Inbound bearer token. When set, every ``/tools/*`` op requires it and the served
               OpenAPI doc declares the bearer scheme. When None and *url* advertises a non-localhost
               host, construction is REFUSED (fail-closed). This factory does NOT read the
               environment — ``main`` loads the token and passes it in.
        allowed_hosts: Host allowlist for the DNS-rebind guard (all modes). Defaults to the served
               host + loopback forms. ``["*"]`` only behind a trusted reverse-proxy (warns).
    """
    import json as _json  # noqa: PLC0415

    import anyio.to_thread  # noqa: PLC0415, F401 -- [http]-extra deps present only with the extra
    from starlette.applications import Starlette  # noqa: PLC0415
    from starlette.middleware import Middleware  # noqa: PLC0415
    from starlette.middleware.trustedhost import TrustedHostMiddleware  # noqa: PLC0415
    from starlette.responses import JSONResponse  # noqa: PLC0415
    from starlette.routing import Route  # noqa: PLC0415

    from .governed import GovernedError, call_governed, list_governed  # noqa: PLC0415
    from .webguard import (  # noqa: PLC0415
        BearerAuthMiddleware,
        CrossOriginGuardMiddleware,
        default_allowed_hosts,
        require_auth_for_public,
    )

    if url is None:
        url = f"http://{_DEFAULT_HOST}:{_DEFAULT_PORT}/"

    # Defense-in-depth: refuse a public advertised URL without a token (covers --factory paths).
    require_auth_for_public(urlparse(url).hostname, token, where="advertised URL",
                            face="HTTP", token_env=_TOKEN_FILE_ENV)

    _doc: list[dict | None] = [None]  # lazily built + cached on first discovery request

    async def _serve_openapi(_request):
        if _doc[0] is None:
            _doc[0] = build_openapi(await list_governed(), secured=bool(token))
        return JSONResponse(_doc[0])

    async def _healthz(_request):
        return JSONResponse({"ok": True})

    async def _tool(request):
        name = request.path_params["tool_name"]
        raw = await request.body()
        if raw:
            try:
                args = _json.loads(raw)
            except ValueError:
                _audit_rejection(name, "request body is not valid JSON")
                return JSONResponse({"error": "request body must be a JSON object"}, status_code=400)
        else:
            args = {}
        try:
            result = await call_governed(name, args)
        except GovernedError as exc:
            if exc.status in (400, 404):
                _audit_rejection(name, exc.message)
            return JSONResponse({"error": exc.message}, status_code=exc.status)
        return JSONResponse(result)

    routes = [
        Route("/openapi.json", _serve_openapi, methods=["GET"]),
        Route("/healthz", _healthz, methods=["GET"]),
        Route("/tools/{tool_name}", _tool, methods=["POST"]),
    ]

    hosts = allowed_hosts or default_allowed_hosts(url)
    if "*" in hosts:
        warnings.warn(
            "PROXIMO HTTP host allowlist contains '*' — DNS-rebind/Host protection is DISABLED; "
            "any Host header is accepted. Only safe behind a trusted reverse-proxy that validates "
            "Host.", stacklevel=2,
        )
    _protect_tools = lambda path: path.startswith(_TOOLS_PREFIX)  # noqa: E731
    middleware = [
        Middleware(TrustedHostMiddleware, allowed_hosts=hosts),
        # CSRF/cross-origin guard on the mutating endpoint — closes the loopback-CSRF vector the
        # bearer guard can't cover in no-token dev mode (see CrossOriginGuardMiddleware).
        Middleware(CrossOriginGuardMiddleware, protect=_protect_tools),
    ]
    if token:
        middleware.append(Middleware(
            BearerAuthMiddleware, token=token,
            protect=_protect_tools,
            unauthorized_body={"error": "unauthorized"},
        ))
    return Starlette(routes=routes, middleware=middleware)


def main() -> None:
    """``proximo-http`` entry point — run the HTTP face with uvicorn (fail-closed)."""
    import uvicorn  # noqa: PLC0415 -- only needed when actually serving

    from . import server  # noqa: PLC0415
    from .webguard import load_token_file, require_auth_for_public  # noqa: PLC0415

    # Scope the live tool registry to PROXIMO_SURFACES / configured planes BEFORE serving — the
    # network faces read the same global registry, so without this the operator's surface config
    # is silently ignored on this face (it is applied here exactly as the stdio server does it).
    try:
        server._apply_surfaces()
    except ValueError as e:
        print(f"proximo-http: {e}", file=sys.stderr)
        raise SystemExit(1) from None

    host = os.environ.get("PROXIMO_HTTP_HOST", _DEFAULT_HOST)
    port = int(os.environ.get("PROXIMO_HTTP_PORT", str(_DEFAULT_PORT)))
    token = load_token_file(_TOKEN_FILE_ENV)

    # FAIL-CLOSED: a public bind with no token never starts.
    require_auth_for_public(host, token, where="bind host", face="HTTP", token_env=_TOKEN_FILE_ENV)

    allowed = os.environ.get("PROXIMO_HTTP_ALLOWED_HOSTS", "")
    allowed_hosts = [h.strip() for h in allowed.split(",") if h.strip()] or None

    # Bracket bare IPv6 hosts for the URL authority (same fix as the A2A entry — an unbracketed
    # ::1 parses to hostname=None, which the factory's guard misreads as bind-all/public).
    url_host = f"[{host}]" if (":" in host and not host.startswith("[")) else host
    app = build_app(f"http://{url_host}:{port}/", token=token, allowed_hosts=allowed_hosts)
    uvicorn.run(app, host=host, port=port)
