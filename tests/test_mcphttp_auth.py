"""MCP-HTTP face perimeter hardening — fail-closed bind + bearer auth + Host (DNS-rebind) allowlist.

The MCP-over-streamable-HTTP face is a network control plane over Proxmox, exactly like the A2A and
HTTP faces — and it must obey the same fail-closed rules:
  - building a PUBLIC-bound app WITHOUT an auth token is REFUSED (not merely warned)
  - when a token is set: every /mcp request (POST message, GET SSE stream, DELETE session) requires
    a correct Bearer token; liveness (/healthz) stays open, like the other faces' discovery routes
  - localhost-default with no token still works for loopback Hosts (dev ergonomics preserved)
  - the Host guard is installed in ALL modes — non-loopback Hosts are rejected even tokenless

Perimeter rejections happen in middleware, BEFORE the SDK's session manager — so these tests never
need the app lifespan running: a request that got past the guards would 500 on the unstarted
manager, never 401/403/400, making any pass here proof the guard fired first.
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from proximo.mcphttp import build_app

PUBLIC_URL = "http://10.1.2.3:41243/"
LOCAL = "http://localhost"


# --- fail-closed bind -----------------------------------------------------------------------

def test_public_bind_without_token_is_refused():
    with pytest.raises(ValueError):
        build_app(PUBLIC_URL)


def test_public_bind_with_token_is_allowed():
    assert build_app(PUBLIC_URL, token="s3cret") is not None


def test_bind_all_interfaces_counts_as_public():
    with pytest.raises(ValueError):
        build_app("http://0.0.0.0:41243/")


def test_localhost_without_token_is_allowed():
    assert build_app() is not None


# --- bearer auth ----------------------------------------------------------------------------

def test_mcp_post_requires_bearer_when_token_set():
    client = TestClient(build_app(token="s3cret"), base_url=LOCAL)
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"] == "Bearer"
    # JSON-RPC error body, like the A2A face's 401.
    assert r.json()["error"]["message"] == "unauthorized"


def test_mcp_get_sse_stream_requires_bearer_too():
    # The GET side of streamable HTTP (the server→client SSE stream) is part of the protocol
    # endpoint — it must not be reachable unauthenticated.
    client = TestClient(build_app(token="s3cret"), base_url=LOCAL)
    r = client.get("/mcp", headers={"Accept": "text/event-stream"})
    assert r.status_code == 401


def test_mcp_delete_session_requires_bearer_too():
    client = TestClient(build_app(token="s3cret"), base_url=LOCAL)
    assert client.delete("/mcp").status_code == 401


def test_wrong_bearer_is_rejected():
    client = TestClient(build_app(token="s3cret"), base_url=LOCAL)
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
                    headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_health_stays_open_with_token_set():
    client = TestClient(build_app(token="s3cret"), base_url=LOCAL)
    assert client.get("/healthz").json() == {"ok": True}


# --- Host (DNS-rebind) guard ----------------------------------------------------------------

def test_host_guard_rejects_non_loopback_host_even_tokenless():
    client = TestClient(build_app(), base_url=LOCAL)
    r = client.get("/healthz", headers={"Host": "evil.example"})
    assert r.status_code == 400


def test_host_guard_star_warns_loudly():
    with pytest.warns(UserWarning, match="DNS-rebind"):
        build_app(allowed_hosts=["*"])
