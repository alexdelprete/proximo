"""End-to-end: a real MCP client drives `python -m proximo` over the stdio transport.

The other tests call the tool functions directly; this is the only one that exercises the *protocol*:
the `initialize` handshake (including the server advertising Proximo's OWN version, not the MCP SDK's),
`tools/list`, and a clean `tools/call` round-trip. No live Proxmox — `audit_verify` reads a temp ledger,
and the server is pointed at an unreachable API so nothing real is touched.
"""
import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import proximo


def _params(tmp_path) -> StdioServerParameters:
    tok = tmp_path / "e2e.tok"
    tok.write_text("e2e@pam!t=00000000-0000-0000-0000-000000000000")  # dummy; never used (no live PVE)
    tok.chmod(0o600)  # deploy like production: the config guard refuses group/other-readable tokens
    env = {
        **os.environ,
        "PROXIMO_API_BASE_URL": "https://127.0.0.1:8006/api2/json",  # unreachable on purpose
        "PROXIMO_NODE": "e2e-node",
        "PROXIMO_TOKEN_PATH": str(tok),
        "PROXIMO_VERIFY_TLS": "true",  # construct over verified TLS (H-2); PVE is unreachable here anyway
        "PROXIMO_AUDIT_LOG": str(tmp_path / "e2e-audit.log"),
    }
    return StdioServerParameters(command=sys.executable, args=["-m", "proximo"], env=env)


async def test_mcp_stdio_transport_end_to_end(tmp_path):
    async with stdio_client(_params(tmp_path)) as (read, write):
        async with ClientSession(read, write) as session:
            init = await asyncio.wait_for(session.initialize(), timeout=30)
            # The handshake must advertise Proximo's OWN version, not the MCP SDK's.
            assert init.serverInfo.name == "proximo"
            assert init.serverInfo.version == proximo.__version__

            tools = await asyncio.wait_for(session.list_tools(), timeout=30)
            names = {t.name for t in tools.tools}
            assert "audit_verify" in names
            assert len(names) > 100  # the full tool surface is exposed over the protocol

            # A clean round-trip through the protocol (no PVE needed).
            res = await asyncio.wait_for(session.call_tool("audit_verify", {}), timeout=30)
            assert res.isError is False
            text = " ".join(getattr(c, "text", "") or "" for c in (res.content or []))
            assert "ok" in text and "true" in text.lower()
