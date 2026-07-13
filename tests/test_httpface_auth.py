"""HTTP face perimeter hardening — fail-closed bind + bearer auth + Host (DNS-rebind) allowlist.

The HTTP face is a network control plane over Proxmox, exactly like the A2A face — and it
must obey the same fail-closed rules:
  - building a PUBLIC-bound app WITHOUT an auth token is REFUSED (not merely warned)
  - when a token is set: every /skills operation requires a correct Bearer token; discovery
    (/openapi.json) and liveness (/healthz) stay open, like the A2A agent card
  - localhost-default with no token still works for loopback Hosts (dev ergonomics preserved)
  - the Host guard is installed in ALL modes — non-loopback Hosts are rejected even tokenless
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from proximo.httpface import build_app

PUBLIC_URL = "http://10.1.2.3:41242/"
LOCAL = "http://localhost"


# --- fail-closed bind -----------------------------------------------------------------------

def test_public_bind_without_token_is_refused():
    with pytest.raises(ValueError):
        build_app(PUBLIC_URL)


def test_public_bind_with_token_is_allowed():
    assert build_app(PUBLIC_URL, token="s3cret") is not None


def test_bind_all_interfaces_counts_as_public():
    with pytest.raises(ValueError):
        build_app("http://0.0.0.0:41242/")


def test_localhost_without_token_is_allowed():
    assert build_app() is not None


# --- bearer auth ----------------------------------------------------------------------------

def test_tools_post_requires_bearer_when_token_set():
    client = TestClient(build_app(token="s3cret"), base_url=LOCAL)
    r = client.post("/tools/pve_node_status", json={})
    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"] == "Bearer"


def test_wrong_bearer_is_rejected():
    client = TestClient(build_app(token="s3cret"), base_url=LOCAL)
    r = client.post("/tools/pve_node_status", json={},
                    headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_discovery_and_health_stay_open_with_token_set():
    client = TestClient(build_app(token="s3cret"), base_url=LOCAL)
    assert client.get("/healthz").status_code == 200
    r = client.get("/openapi.json")
    assert r.status_code == 200
    # And the doc DECLARES the bearer scheme, so clients learn how to authenticate.
    assert r.json()["security"] == [{"bearerAuth": []}]


def test_openapi_unsecured_when_no_token():
    client = TestClient(build_app(), base_url=LOCAL)
    assert "security" not in client.get("/openapi.json").json()


# --- Host (DNS-rebind) guard ----------------------------------------------------------------

def test_host_guard_rejects_non_loopback_host_even_tokenless():
    client = TestClient(build_app(), base_url=LOCAL)
    r = client.get("/healthz", headers={"Host": "evil.example"})
    assert r.status_code == 400


def test_host_guard_star_warns_loudly():
    with pytest.warns(UserWarning, match="DNS-rebind"):
        build_app(allowed_hosts=["*"])
