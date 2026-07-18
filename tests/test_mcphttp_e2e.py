"""End-to-end: the OFFICIAL MCP streamable-HTTP client drives the Proximo MCP-HTTP app.

The perimeter tests prove hostile requests are refused; this proves the legit path WORKS — the
whole point of the face (upstream FR #25: no third-party stdio→HTTP bridge). The SDK's real client
speaks the full Streamable HTTP protocol (initialize handshake, session header, SSE-or-JSON
responses) through the complete middleware stack (TrustedHost → CSRF guard → bearer) into the SAME
FastMCP instance the stdio server runs — list_tools returns the full governed surface and a real
tool (audit_verify) executes through the spine. Uses httpx ASGITransport (in-process, no socket)
with the app lifespan run explicitly, since the SDK app's session manager lives in the lifespan.
No live Proxmox (audit_verify reads a temp ledger).
"""
from __future__ import annotations

import json

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from proximo.mcphttp import build_app

BASE = "http://localhost"


def _configure_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PROXIMO_API_BASE_URL", "https://127.0.0.1:8006/api2/json")
    monkeypatch.setenv("PROXIMO_NODE", "e2e-node")
    tok = tmp_path / "e2e.tok"
    tok.write_text("e2e@pam!t=00000000-0000-0000-0000-000000000000")
    tok.chmod(0o600)  # the config guard refuses group/other-readable tokens
    monkeypatch.setenv("PROXIMO_TOKEN_PATH", str(tok))
    monkeypatch.setenv("PROXIMO_VERIFY_TLS", "true")
    monkeypatch.setenv("PROXIMO_AUDIT_LOG", str(tmp_path / "e2e-audit.log"))


async def _drive(app, headers=None):
    """Full client session against *app*: initialize → list_tools → call audit_verify."""
    hx = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE,
                           headers=headers, timeout=30)
    async with app.router.lifespan_context(app):  # the SDK session manager runs in the lifespan
        async with streamable_http_client(f"{BASE}/mcp", http_client=hx) as (read, write, _sid):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                assert len(names) > 300, "the FULL governed surface, not a curated slice"
                assert "audit_verify" in names
                result = await session.call_tool("audit_verify", {})
                assert result.isError is False
                # Proximo tools return their JSON as text content — same as over stdio.
                verdict = json.loads(result.content[0].text)
                assert verdict["ok"] is True


async def test_mcp_client_end_to_end_no_token(tmp_path, monkeypatch):
    _configure_env(tmp_path, monkeypatch)
    await _drive(build_app())


async def test_mcp_client_end_to_end_with_bearer(tmp_path, monkeypatch):
    # The same full protocol run with the bearer guard armed: the official client carries the
    # token on EVERY request (POST message, GET stream, DELETE session), so nothing 401s.
    _configure_env(tmp_path, monkeypatch)
    await _drive(build_app(token="s3cret"), headers={"Authorization": "Bearer s3cret"})


async def test_stateless_json_mode_end_to_end(tmp_path, monkeypatch):
    # The load-balancer-friendly posture: stateless sessions + plain-JSON responses.
    _configure_env(tmp_path, monkeypatch)
    await _drive(build_app(stateless=True, json_response=True))
