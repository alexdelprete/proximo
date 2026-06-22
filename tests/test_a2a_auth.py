"""A2A perimeter hardening — fail-closed bind + bearer auth + Host (DNS-rebind) allowlist + card decl.

The A2A face is a network control plane over Proxmox. Proximo's thesis is fail-closed / safe-by-default;
these tests pin that the A2A front door obeys it:
  - building a PUBLIC-bound app WITHOUT an auth token is REFUSED (not merely warned)
  - when a token is set: the JSON-RPC control endpoint requires a correct Bearer token, the Host header
    is validated against an allowlist (DNS-rebind defense), and the agent card DECLARES the bearer scheme
  - localhost-default with no token still works unrestricted (dev ergonomics preserved)

When a token is set the Host allowlist is enforced, so token'd TestClients use a loopback base_url.
"""
from __future__ import annotations

import pytest
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH
from starlette.testclient import TestClient

from proximo.a2a.app import _is_public, _require_auth_for_public, build_app
from proximo.a2a.card import build_agent_card

PUBLIC_URL = "http://10.1.2.3:41241/"
LOCAL = "http://localhost"  # a Host in the default allowlist
_RPC_BODY = {"jsonrpc": "2.0", "id": "1", "method": "message/send", "params": {}}


# --- fail-closed bind -----------------------------------------------------------------------------

def test_public_bind_without_token_is_refused():
    with pytest.raises(ValueError):
        build_app(PUBLIC_URL)


def test_public_bind_with_token_is_allowed():
    assert build_app(PUBLIC_URL, token="s3cret") is not None


def test_localhost_without_token_still_serves_card():
    # no regression: dev default (loopback, no token, no Host restriction) keeps working
    client = TestClient(build_app())
    assert client.get(AGENT_CARD_WELL_KNOWN_PATH).status_code == 200


# An empty/None/whitespace bind host means "bind all interfaces" (0.0.0.0) — the MOST public. It must
# be treated as public so the fail-closed gate refuses it without a token. (Regression: bool("") is
# False made _is_public("") read as non-public, so PROXIMO_A2A_HOST="" slipped the gate unauthenticated.)
@pytest.mark.parametrize("host", ["", "   ", None, "0.0.0.0", "::", "10.1.2.3"])  # noqa: S104 -- testing bind-all IS public
def test_bindall_or_remote_host_is_public(host):
    assert _is_public(host) is True


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_localhost_host_is_not_public(host):
    assert _is_public(host) is False


@pytest.mark.parametrize("host", ["", "   ", None])
def test_empty_bind_host_without_token_is_refused(host):
    with pytest.raises(ValueError):
        _require_auth_for_public(host, None, where="bind host")


# --- bearer auth on the control endpoint ----------------------------------------------------------

def test_rpc_without_bearer_is_401_when_token_set():
    client = TestClient(build_app(token="s3cret"), base_url=LOCAL)
    assert client.post("/", json=_RPC_BODY).status_code == 401


def test_rpc_with_wrong_bearer_is_401():
    client = TestClient(build_app(token="s3cret"), base_url=LOCAL)
    assert client.post("/", headers={"Authorization": "Bearer nope"}, json=_RPC_BODY).status_code == 401


def test_rpc_with_correct_bearer_passes_auth():
    client = TestClient(build_app(token="s3cret"), base_url=LOCAL)
    r = client.post("/", headers={"Authorization": "Bearer s3cret"}, json=_RPC_BODY)
    assert r.status_code != 401


def test_card_stays_open_even_when_token_set():
    client = TestClient(build_app(token="s3cret"), base_url=LOCAL)
    assert client.get(AGENT_CARD_WELL_KNOWN_PATH).status_code == 200


# --- Host allowlist / DNS-rebind protection -------------------------------------------------------

def test_bad_host_rejected_when_token_set():
    # a Host the server doesn't recognise is refused BEFORE auth (DNS-rebind defense)
    client = TestClient(build_app(token="s3cret"), base_url="http://evil.example.com")
    assert client.get(AGENT_CARD_WELL_KNOWN_PATH).status_code == 400


def test_allowed_host_passes_host_check():
    client = TestClient(build_app(token="s3cret"), base_url=LOCAL)
    # localhost is in the default allowlist → host check passes → card served
    assert client.get(AGENT_CARD_WELL_KNOWN_PATH).status_code == 200


def test_no_host_restriction_without_token():
    # dev mode (no token): no Host allowlist installed; default TestClient Host ('testserver') is fine
    client = TestClient(build_app())
    assert client.get(AGENT_CARD_WELL_KNOWN_PATH).status_code == 200


def test_custom_allowed_hosts_honored():
    client = TestClient(build_app(token="s3cret", allowed_hosts=["proxmox.lan", "localhost"]),
                        base_url="http://proxmox.lan")
    # proxmox.lan is explicitly allowed → host check passes (then auth applies on the rpc route)
    assert client.get(AGENT_CARD_WELL_KNOWN_PATH).status_code == 200
    assert client.post("/", json=_RPC_BODY).status_code == 401  # host ok, but no bearer


# --- agent card declares the bearer scheme when secured -------------------------------------------

def test_card_declares_bearer_scheme_when_secured():
    card = build_agent_card("http://127.0.0.1:41241/", secured=True)
    assert len(card.security_schemes) >= 1
    scheme = card.security_schemes["bearerAuth"]
    assert scheme.http_auth_security_scheme.scheme.lower() == "bearer"


def test_card_omits_scheme_when_not_secured():
    card = build_agent_card("http://127.0.0.1:41241/")
    assert len(card.security_schemes) == 0


def test_wildcard_allowed_hosts_warns_not_silent():
    # "*" disables the DNS-rebind guard (Starlette allow-any). It's a legitimate behind-a-proxy
    # choice, but it must NOT be silent — warn loudly (matches the MCP CT_ALLOWLIST='*' precedent).
    with pytest.warns(UserWarning, match="(?i)host|rebind"):
        build_app(token="s3cret", allowed_hosts=["*"])
