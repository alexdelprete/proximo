"""Proximo MCP-over-streamable-HTTP face — the MCP protocol itself, served over the network.

The stdio server IS MCP; this face serves the SAME FastMCP instance over the MCP Streamable HTTP
transport (the SDK's native ``streamable_http_app()``), for the distributed MCP clients (Claude
Desktop/Code on another machine, web clients) that would otherwise need a third-party stdio→HTTP
bridge. Those bridges sit OUTSIDE Proximo's perimeter — whatever auth/rebind/CSRF posture exists is
then the bridge's, not Proximo's (upstream FR #25). Here every call lands on ``server.mcp`` itself:
the identical tool registry, trust spine (PLAN-by-default, PROVE, UNDO, the gates), and Proxmox
token scope a stdio client gets. There is no adapter layer at all — not even ``governed`` — so this
face cannot diverge from MCP: it IS MCP.

The face is an optional extra ([mcp-http], which also pins the SDK floor for the streamable-HTTP
API); the MCP core keeps zero extra deps. Fail-closed perimeter shared with A2A + HTTP
(``proximo.webguard``): non-localhost binds refuse without a bearer token, constant-time bearer on
the ``/mcp`` endpoint (liveness stays open), a Host/DNS-rebind allowlist, and the cross-origin
(CSRF) guard on POST. The SDK ships its own optional DNS-rebind protection but it defaults OFF
(backwards compat) — we do not lean on it; the webguard perimeter is authoritative, identical to
the sibling faces, so the hardening contract cannot drift between transports.
"""

from __future__ import annotations

import os
import sys
import warnings
from urllib.parse import urlparse

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 41243  # A2A is 41241, HTTP/OpenAPI 41242; the MCP-HTTP face sits beside them
_TOKEN_FILE_ENV = "PROXIMO_MCP_HTTP_TOKEN_FILE"  # noqa: S105 -- env var NAME, not a secret value
_MCP_PATH = "/mcp"  # the SDK's default streamable-HTTP path, pinned explicitly (the guards match it)

_TRUEISH = frozenset({"1", "true", "yes", "on"})
_FALSISH = frozenset({"0", "false", "no", "off"})


def build_app(url: str | None = None, *, token: str | None = None,
              allowed_hosts: list[str] | None = None,
              stateless: bool = True, json_response: bool = False):
    """Build the Proximo MCP-over-streamable-HTTP ASGI application.

    Args:
        url:   Advertised base URL (default ``http://127.0.0.1:41243/``). Its hostname feeds the
               fail-closed public-bind guard and the default Host allowlist.
        token: Inbound bearer token. When set, every request to ``/mcp`` (POST message, GET SSE
               stream, DELETE session) requires it. When None and *url* advertises a non-localhost
               host, construction is REFUSED (fail-closed). This factory does NOT read the
               environment — ``main`` loads the token and passes it in.
        allowed_hosts: Host allowlist for the DNS-rebind guard (all modes). Defaults to the served
               host + loopback forms. ``["*"]`` only behind a trusted reverse-proxy (warns).
        stateless: Serve in the SDK's stateless mode (no per-session state; each request is
               self-contained). Default TRUE — the maintainer's call on FR #25: multi-client
               behind a proxy is the deployment model this face exists for, and nothing in the
               governed surface needs a session. Pass False for session-stateful serving.
        json_response: Answer POSTs with plain JSON bodies instead of an SSE stream, for clients
               that prefer it.

    NOTE: the returned app carries a lifespan (the SDK's session manager) — it must be served by a
    lifespan-running host (uvicorn does; a bare ``httpx.ASGITransport`` does not).
    """
    from starlette.middleware.trustedhost import TrustedHostMiddleware  # noqa: PLC0415
    from starlette.responses import JSONResponse  # noqa: PLC0415
    from starlette.routing import Route  # noqa: PLC0415

    from . import server  # noqa: PLC0415
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
                            face="MCP-HTTP", token_env=_TOKEN_FILE_ENV)

    from mcp.server.transport_security import TransportSecuritySettings  # noqa: PLC0415

    server.mcp.settings.streamable_http_path = _MCP_PATH
    server.mcp.settings.stateless_http = stateless
    server.mcp.settings.json_response = json_response
    # ONE authoritative perimeter, not two: newer SDKs default their own DNS-rebind guard ON with
    # a fixed loopback-only, port-suffixed allowlist — which would 421 every legitimate non-default
    # deployment (public bind with token, reverse-proxy Hosts, the operator's PROXIMO_MCP_HTTP_
    # ALLOWED_HOSTS) and cannot express webguard's list (no bare-host match, no "*"). The shared
    # webguard stack below covers both of its checks — TrustedHost validates Host (rebind), the
    # CSRF guard validates Origin + Content-Type — so the SDK layer is disabled rather than fed a
    # second, driftable copy of the allowlist. (Its POST Content-Type check stays on in either mode.)
    server.mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False)
    # Fresh session manager per app: FastMCP caches its manager on first use, and a manager's
    # run() is once-per-instance — a second build (tests, embedders) would otherwise crash at
    # lifespan start, and the settings above would silently not apply. Private-attr reach, like
    # governed.list_governed_sync's — the SDK exposes no reset.
    server.mcp._session_manager = None
    app = server.mcp.streamable_http_app()

    async def _healthz(_request):
        return JSONResponse({"ok": True})

    app.router.routes.append(Route("/healthz", _healthz, methods=["GET"]))

    hosts = allowed_hosts or default_allowed_hosts(url)
    if "*" in hosts:
        warnings.warn(
            "PROXIMO MCP-HTTP host allowlist contains '*' — DNS-rebind/Host protection is DISABLED; "
            "any Host header is accepted. Only safe behind a trusted reverse-proxy that validates "
            "Host.", stacklevel=2,
        )
    _protect_mcp = lambda path: path.rstrip("/") == _MCP_PATH  # noqa: E731
    # add_middleware PREPENDS, so add inner→outer: the final stack matches the sibling faces —
    # TrustedHost outermost, then the CSRF guard, bearer innermost. (/healthz stays open, like
    # the other faces' discovery routes; /mcp itself is the whole protected protocol endpoint.)
    if token:
        app.add_middleware(
            BearerAuthMiddleware, token=token, protect=_protect_mcp,
            # MCP streamable HTTP is JSON-RPC over HTTP — same 401 body shape as the A2A face.
            unauthorized_body={"jsonrpc": "2.0", "id": None,
                               "error": {"code": -32001, "message": "unauthorized"}},
        )
    app.add_middleware(CrossOriginGuardMiddleware, protect=_protect_mcp)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    return app


def main() -> None:
    """``proximo-mcp-http`` entry point — run the MCP-HTTP face with uvicorn (fail-closed)."""
    import uvicorn  # noqa: PLC0415 -- only needed when actually serving

    from . import server  # noqa: PLC0415
    from .webguard import load_token_file, require_auth_for_public  # noqa: PLC0415

    # Scope the live tool registry to PROXIMO_SURFACES / configured planes BEFORE serving — the
    # network faces read the same global registry, so without this the operator's surface config
    # is silently ignored on this face (it is applied here exactly as the stdio server does it).
    try:
        server._apply_surfaces()
    except ValueError as e:
        print(f"proximo-mcp-http: {e}", file=sys.stderr)
        raise SystemExit(1) from None

    host = os.environ.get("PROXIMO_MCP_HTTP_HOST", _DEFAULT_HOST)
    port = int(os.environ.get("PROXIMO_MCP_HTTP_PORT", str(_DEFAULT_PORT)))
    token = load_token_file(_TOKEN_FILE_ENV)

    # FAIL-CLOSED: a public bind with no token never starts.
    require_auth_for_public(host, token, where="bind host", face="MCP-HTTP",
                            token_env=_TOKEN_FILE_ENV)

    allowed = os.environ.get("PROXIMO_MCP_HTTP_ALLOWED_HOSTS", "")
    allowed_hosts = [h.strip() for h in allowed.split(",") if h.strip()] or None

    # Stateless is the DEFAULT (FR #25 maintainer decision) — opt out with
    # PROXIMO_MCP_HTTP_STATELESS=0/false/no/off for session-stateful serving.
    stateless = os.environ.get("PROXIMO_MCP_HTTP_STATELESS", "").strip().lower() not in _FALSISH
    json_response = os.environ.get("PROXIMO_MCP_HTTP_JSON", "").strip().lower() in _TRUEISH

    # Bracket bare IPv6 hosts for the URL authority (same fix as the A2A/HTTP entries — an
    # unbracketed ::1 parses to hostname=None, which the factory's guard misreads as bind-all).
    url_host = f"[{host}]" if (":" in host and not host.startswith("[")) else host
    app = build_app(f"http://{url_host}:{port}/", token=token, allowed_hosts=allowed_hosts,
                    stateless=stateless, json_response=json_response)
    uvicorn.run(app, host=host, port=port)
