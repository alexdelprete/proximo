"""Proximo A2A server application factory + ``proximo-a2a`` entrypoint.

Wires the A2A SDK's request-handler stack into a Starlette ASGI app. The executor
(``ProximoAgentExecutor``) is imported from the sibling ``.executor`` module; this module owns
the plumbing (routes, card, handler, auth) and the ``main`` entry point.

Security model (fail-closed, like the rest of Proximo):
  - Default bind is loopback (``127.0.0.1``) — not reachable off-box.
  - The A2A face is a network CONTROL PLANE over Proxmox. Binding it to any non-localhost address
    is REFUSED unless an auth token is configured (``PROXIMO_A2A_TOKEN_FILE``) — a hard error, not a
    warning. "Exposed by accident" is structurally impossible.
  - When a token is configured, the JSON-RPC control endpoint requires ``Authorization: Bearer
    <token>`` (constant-time compared). The agent card stays readable so A2A clients can discover
    how to authenticate.
"""

from __future__ import annotations

import hmac
import os
import warnings
from urllib.parse import urlparse

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

from .card import build_agent_card
from .executor import ProximoAgentExecutor

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 41241
_LOCALHOST_ADDRS = frozenset({"127.0.0.1", "localhost", "::1"})
_TOKEN_FILE_ENV = "PROXIMO_A2A_TOKEN_FILE"  # noqa: S105 -- env var NAME, not a secret value


def _is_public(host: str | None) -> bool:
    """True when *host* is a non-localhost address (reachable off-box)."""
    return bool(host) and host not in _LOCALHOST_ADDRS


def _default_allowed_hosts(rpc_url: str) -> list[str]:
    """Host allowlist for the DNS-rebind guard: the served host + loopback forms (deduped)."""
    hosts = set(_LOCALHOST_ADDRS)
    host = urlparse(rpc_url).hostname
    if host:
        hosts.add(host)
    return sorted(hosts)


def _load_a2a_token() -> str | None:
    """Load the inbound bearer token from ``PROXIMO_A2A_TOKEN_FILE`` (run-but-not-read by path).

    Returns None when the env var is unset. Fails LOUD (RuntimeError) if the var is set but the file
    is missing/unreadable or empty — never silently run unauthenticated when auth was intended.
    """
    path = os.environ.get(_TOKEN_FILE_ENV)
    if not path:
        return None
    try:
        token = open(path, encoding="utf-8").read().strip()  # noqa: SIM115
    except OSError as e:
        raise RuntimeError(f"{_TOKEN_FILE_ENV}={path!r} could not be read: {e}") from e
    if not token:
        raise RuntimeError(f"{_TOKEN_FILE_ENV}={path!r} is empty — refusing to serve with a blank token.")
    return token


def _require_auth_for_public(host: str | None, token: str | None, *, where: str) -> None:
    """FAIL-CLOSED guard: refuse a non-localhost control plane that has no auth token.

    Raises ValueError (not a warning) so a public bind without a token cannot start. Fires from BOTH
    the bind path (``main``) and the application factory (``build_app``, on the advertised URL) so it
    can't be sidestepped via the uvicorn ``--factory`` path (defense-in-depth).
    """
    if _is_public(host) and not token:
        raise ValueError(
            f"Refusing to expose the Proximo A2A control plane: {where} is {host!r} (non-localhost) "
            f"with no auth token. The A2A face drives Proxmox — set {_TOKEN_FILE_ENV} to a file "
            "containing a bearer token, or bind localhost only."
        )


class _BearerAuthMiddleware(BaseHTTPMiddleware):
    """Require ``Authorization: Bearer <token>`` on the JSON-RPC control endpoint.

    Protects the exact RPC path only; the agent-card / well-known discovery routes stay open so A2A
    clients can read the card (and its declared auth requirement) before authenticating.
    """

    def __init__(self, app, *, token: str, rpc_path: str) -> None:
        super().__init__(app)
        self._token = token
        self._rpc = rpc_path.rstrip("/")

    async def dispatch(self, request, call_next):
        if request.url.path.rstrip("/") == self._rpc:
            scheme, _, presented = request.headers.get("authorization", "").partition(" ")
            if scheme.lower() != "bearer" or not presented or not hmac.compare_digest(presented, self._token):
                return JSONResponse(
                    {"jsonrpc": "2.0", "id": None,
                     "error": {"code": -32001, "message": "unauthorized"}},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return await call_next(request)


def build_app(rpc_url: str | None = None, *, token: str | None = None,
              allowed_hosts: list[str] | None = None) -> Starlette:
    """Build the Proximo A2A ASGI application.

    Args:
        rpc_url: Fully-qualified JSON-RPC endpoint URL (default ``http://127.0.0.1:41241/``). Used
                 as the card's interface URL and (path-only) as the Starlette route path.
        token:   Inbound bearer token. When set, the JSON-RPC endpoint requires it, the card declares
                 the bearer scheme, and the Host header is validated (DNS-rebind defense). When None
                 and ``rpc_url`` advertises a non-localhost host, construction is REFUSED (fail-closed).
                 NOTE: this factory does NOT read the environment — the ``proximo-a2a`` entrypoint
                 (``main``) loads the token and passes it in. Embedders must pass ``token=`` explicitly.
        allowed_hosts: Host allowlist for the DNS-rebind guard (only applied when ``token`` is set).
                 Defaults to the served host + loopback forms.
    """
    if rpc_url is None:
        rpc_url = f"http://{_DEFAULT_HOST}:{_DEFAULT_PORT}/"

    # Defense-in-depth: refuse a public advertised URL without a token (covers the --factory path).
    _require_auth_for_public(urlparse(rpc_url).hostname, token, where="advertised URL")

    rpc_path = urlparse(rpc_url).path or "/"
    card = build_agent_card(rpc_url, secured=bool(token))

    handler = DefaultRequestHandler(
        agent_executor=ProximoAgentExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    routes = (
        create_jsonrpc_routes(request_handler=handler, rpc_url=rpc_path)
        + create_agent_card_routes(agent_card=card)
    )

    # When auth is on (i.e. an exposed deployment), harden the perimeter: validate the Host header
    # (DNS-rebind defense, OUTERMOST so a bad host is refused before anything) then require the bearer.
    middleware: list[Middleware] = []
    if token:
        hosts = allowed_hosts or _default_allowed_hosts(rpc_url)
        if "*" in hosts:
            # Starlette treats "*" as allow-any → the DNS-rebind guard is OFF. Legitimate only behind
            # a trusted reverse-proxy that validates Host. Never let that be silent (cf. the MCP-side
            # CT_ALLOWLIST='*' warning) — surface it loudly.
            warnings.warn(
                "PROXIMO A2A host allowlist contains '*' — DNS-rebind/Host protection is DISABLED; "
                "any Host header is accepted. Only safe behind a trusted reverse-proxy that validates Host.",
                stacklevel=2,
            )
        middleware.append(Middleware(TrustedHostMiddleware, allowed_hosts=hosts))
        middleware.append(Middleware(_BearerAuthMiddleware, token=token, rpc_path=rpc_path))
    return Starlette(routes=routes, middleware=middleware)


def main() -> None:
    """``proximo-a2a`` entry point — run the A2A server with uvicorn (fail-closed)."""
    import uvicorn  # noqa: PLC0415 -- only needed when actually serving

    host = os.environ.get("PROXIMO_A2A_HOST", _DEFAULT_HOST)
    port = int(os.environ.get("PROXIMO_A2A_PORT", str(_DEFAULT_PORT)))
    token = _load_a2a_token()

    # FAIL-CLOSED: a public bind with no token never starts.
    _require_auth_for_public(host, token, where="bind host")

    allowed = os.environ.get("PROXIMO_A2A_ALLOWED_HOSTS", "")
    allowed_hosts = [h.strip() for h in allowed.split(",") if h.strip()] or None

    app = build_app(f"http://{host}:{port}/", token=token, allowed_hosts=allowed_hosts)
    uvicorn.run(app, host=host, port=port)
