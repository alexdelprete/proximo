"""HTTP face — localhost cross-origin (CSRF) defense on the full-surface mutating endpoint.

A loopback face with no token (the dev default) is reachable by any web page the operator loads.
A cross-origin page can POST with a CORS-safelisted Content-Type (text/plain) — no preflight — and
drive a real mutation, no credential. The shared CrossOriginGuardMiddleware refuses cross-origin
POSTs to /tools/*; these pin it and prove no legit client is caught. The guard runs BEFORE dispatch,
so a rejected request never reaches call_governed (asserted via a call-recording patch).
"""
from __future__ import annotations

from starlette.testclient import TestClient

from proximo import governed
from proximo.httpface import build_app

LOCAL = "http://localhost"


def _spy(monkeypatch) -> list:
    calls: list = []

    async def _rec(name, args):
        calls.append((name, args))
        return {"ok": True}

    monkeypatch.setattr(governed, "call_governed", _rec)
    return calls


def _client() -> TestClient:
    return TestClient(build_app(), base_url=LOCAL)


# --- the attack is blocked, and the tool is NEVER reached --------------------------------------

def test_text_plain_mutation_is_refused_and_not_dispatched(monkeypatch):
    calls = _spy(monkeypatch)
    r = _client().post("/tools/pve_guest_power",
                       content=b'{"vmid":"102","action":"stop","confirm":true}',
                       headers={"content-type": "text/plain"})
    assert r.status_code == 415
    assert calls == []


def test_form_urlencoded_body_is_refused(monkeypatch):
    calls = _spy(monkeypatch)
    r = _client().post("/tools/pve_snapshot_delete",
                       content=b'{"vmid":"102","snapname":"x","confirm":true}',
                       headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 415
    assert calls == []


def test_sec_fetch_site_cross_site_is_refused_even_with_json(monkeypatch):
    calls = _spy(monkeypatch)
    r = _client().post("/tools/pve_guest_power",
                       json={"vmid": "102", "action": "stop", "confirm": True},
                       headers={"sec-fetch-site": "cross-site"})
    assert r.status_code == 403
    assert calls == []


def test_sec_fetch_site_same_site_is_refused(monkeypatch):
    calls = _spy(monkeypatch)
    r = _client().post("/tools/pve_guest_power",
                       json={"vmid": "102", "action": "stop", "confirm": True},
                       headers={"sec-fetch-site": "same-site"})
    assert r.status_code == 403
    assert calls == []


# --- legit clients are NOT caught --------------------------------------------------------------

def test_application_json_client_passes(monkeypatch):
    calls = _spy(monkeypatch)
    r = _client().post("/tools/pve_guest_power",
                       json={"vmid": "102", "action": "stop", "confirm": True})
    assert r.status_code == 200
    assert calls and calls[0][0] == "pve_guest_power"


def test_json_with_charset_param_passes(monkeypatch):
    _spy(monkeypatch)
    r = _client().post("/tools/pve_node_status", content=b"{}",
                       headers={"content-type": "application/json; charset=utf-8"})
    assert r.status_code == 200


def test_same_origin_browser_request_passes(monkeypatch):
    _spy(monkeypatch)
    r = _client().post("/tools/pve_node_status", json={},
                       headers={"sec-fetch-site": "same-origin"})
    assert r.status_code == 200


def test_user_initiated_navigation_passes(monkeypatch):
    _spy(monkeypatch)
    r = _client().post("/tools/pve_node_status", json={},
                       headers={"sec-fetch-site": "none"})
    assert r.status_code == 200


def test_empty_body_no_content_type_still_works(monkeypatch):
    _spy(monkeypatch)
    r = _client().post("/tools/pve_node_status")
    assert r.status_code == 200


def test_cross_origin_header_without_sec_fetch_is_refused(monkeypatch):
    # The gap the Sec-Fetch-Site check alone misses: a browser that omits Fetch-Metadata still sends
    # Origin on a cross-origin POST. A zero-body request (no Content-Type to catch) must be refused
    # on the Origin mismatch alone, and never dispatched.
    calls = _spy(monkeypatch)
    r = _client().post("/tools/pve_node_status",
                       headers={"origin": "http://evil.example"})
    assert r.status_code == 403
    assert calls == []


def test_origin_null_is_refused(monkeypatch):
    # Sandboxed iframe / file:// pages send `Origin: null` — never same-origin, so refuse.
    calls = _spy(monkeypatch)
    r = _client().post("/tools/pve_node_status", headers={"origin": "null"})
    assert r.status_code == 403
    assert calls == []


def test_same_origin_header_passes(monkeypatch):
    # A same-origin browser POST carries a matching Origin — must pass.
    _spy(monkeypatch)
    r = _client().post("/tools/pve_node_status", json={},
                       headers={"origin": "http://localhost"})
    assert r.status_code == 200


def test_malformed_origin_fails_closed(monkeypatch):
    # A protocol-relative / schemeless Origin must NOT be read as same-origin (fail closed).
    calls = _spy(monkeypatch)
    r = _client().post("/tools/pve_node_status", headers={"origin": "//localhost"})
    assert r.status_code == 403
    assert calls == []


def test_discovery_get_is_never_csrf_checked():
    c = _client()
    assert c.get("/openapi.json", headers={"sec-fetch-site": "cross-site"}).status_code == 200
    assert c.get("/healthz", headers={"sec-fetch-site": "cross-site"}).status_code == 200


def test_oversized_body_is_refused(monkeypatch):
    calls = _spy(monkeypatch)
    big = b'{"x":"' + b"a" * 200_000 + b'"}'
    r = _client().post("/tools/pve_node_status", content=big,
                       headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert calls == []
