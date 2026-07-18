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
from types import SimpleNamespace

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
    # Defaults — which means STATELESS (`stateless_http=True`, the FR #25 maintainer decision:
    # multi-client behind a proxy is the deployment model; the governed surface needs no session).
    _configure_env(tmp_path, monkeypatch)
    await _drive(build_app())


async def test_mcp_client_end_to_end_with_bearer(tmp_path, monkeypatch):
    # The same full protocol run with the bearer guard armed: the official client carries the
    # token on EVERY request (POST message, GET stream, DELETE session), so nothing 401s.
    _configure_env(tmp_path, monkeypatch)
    await _drive(build_app(token="s3cret"), headers={"Authorization": "Bearer s3cret"})


async def test_stateful_opt_out_end_to_end(tmp_path, monkeypatch):
    # The opt-out posture (PROXIMO_MCP_HTTP_STATELESS=0): real per-session state still works.
    _configure_env(tmp_path, monkeypatch)
    await _drive(build_app(stateless=False))


async def test_json_response_mode_end_to_end(tmp_path, monkeypatch):
    # Plain-JSON responses instead of SSE, for clients that prefer it.
    _configure_env(tmp_path, monkeypatch)
    await _drive(build_app(json_response=True))


class _PlanOnlyApi:
    """The minimal Proxmox fake a pve_guest_power PLAN needs — and a tripwire for EXECUTE."""

    def __init__(self):
        self.config = SimpleNamespace(node="e2e-node")
        self.powered: list[tuple] = []

    def guest_status(self, vmid, kind="lxc", node=None):
        return {"status": "running", "name": "web", "uptime": 500}

    def guest_power(self, vmid, action, kind="lxc", node=None):
        self.powered.append((vmid, action))  # reaching here means the PLAN gate failed
        return {"ok": True}


async def test_mutating_tool_through_the_face_is_plan_gated(tmp_path, monkeypatch):
    """The spine, proven through the new mouth (0.24 post-merge review nit): the OFFICIAL client
    calls a MUTATING tool without confirm and gets a recorded PLAN back — never a change. The
    read-only e2e above can't prove the PLAN gate; this asserts both halves of the PLAN→PROVE
    weld from outside the process boundary: status=="plan" in the MCP response, a "planned"
    entry in the real ledger, and the fake API's power method never reached. Backend faked at
    the same `server._svc` seam the server-level plan tests use — the face is in-process, so
    the seam works while the real client drives the full HTTP protocol.
    """
    import proximo.server as server  # noqa: PLC0415
    from proximo.audit import AuditLedger  # noqa: PLC0415
    from proximo.config import ProximoConfig  # noqa: PLC0415

    _configure_env(tmp_path, monkeypatch)
    log = str(tmp_path / "e2e-audit.log")
    cfg = ProximoConfig(api_base_url="https://127.0.0.1:8006/api2/json", node="e2e-node",
                        token_path=str(tmp_path / "e2e.tok"), audit_log_path=log)
    api = _PlanOnlyApi()
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, None, AuditLedger(log)))

    app = build_app()
    hx = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE, timeout=30)
    async with app.router.lifespan_context(app):
        async with streamable_http_client(f"{BASE}/mcp", http_client=hx) as (read, write, _sid):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "pve_guest_power", {"vmid": "1975", "action": "stop"})  # no confirm
                assert result.isError is False
                out = json.loads(result.content[0].text)
                assert out["status"] == "plan", "an unconfirmed mutation must return a PLAN"
                assert api.powered == [], "the PLAN gate let a mutation through the face"

    with open(log, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]
    planned = [e for e in entries if e.get("outcome") == "planned"]
    assert planned and planned[0]["mutation"] is True, "the plan must land on the PROVE ledger"
