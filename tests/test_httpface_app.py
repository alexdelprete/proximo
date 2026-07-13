"""HTTP face dispatch — the full surface, over REST, through the spine.

Every POST /tools/{name} routes through governed.call_governed (the shared spine path), so:
unknown tool 404s, malformed requests 400, tool failures 502 (sanitized), and rejections land on
the PROVE ledger. Behavior parity with the governed core is covered in test_governed.py; here we
pin the HTTP mapping of it.
"""
from __future__ import annotations

from starlette.testclient import TestClient

from proximo import governed
from proximo.httpface import build_app

LOCAL = "http://localhost"


def _client() -> TestClient:
    return TestClient(build_app(), base_url=LOCAL)


async def _ok(name, args):
    return {"tool": name, "args": args, "ok": True}


def test_tool_call_returns_result(monkeypatch):
    monkeypatch.setattr(governed, "call_governed", _ok)
    r = TestClient(build_app(), base_url=LOCAL).post("/tools/pve_node_status", json={})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_unknown_tool_is_404():
    r = _client().post("/tools/definitely_not_a_tool", json={})
    assert r.status_code == 404
    assert "unknown tool" in r.json()["error"]


def test_missing_required_param_is_400():
    # pve_snapshot_list requires a vmid — an empty body is a malformed request.
    r = _client().post("/tools/pve_snapshot_list", json={})
    assert r.status_code == 400
    assert "required" in r.json()["error"]


def test_non_object_body_is_400():
    r = _client().post("/tools/pve_list_guests", json=[1, 2])
    assert r.status_code == 400


def test_invalid_json_body_is_400():
    r = _client().post("/tools/pve_list_guests", content=b"{not json",
                       headers={"content-type": "application/json"})
    assert r.status_code == 400


def test_valid_call_without_backend_is_502_sanitized():
    # A well-formed call to a real tool with no PVE env fails inside the tool -> 502, the tool's own
    # error, never a traceback.
    r = _client().post("/tools/pve_list_guests", json={})
    assert r.status_code == 502
    assert "traceback" not in r.text.lower()


def test_rejection_is_audited(monkeypatch):
    recorded: list = []

    class _Audit:
        def record(self, *a, **kw):
            recorded.append((a, kw))

    from proximo import server
    monkeypatch.setattr(server, "_ledger", lambda: _Audit())
    _client().post("/tools/definitely_not_a_tool", json={})
    assert recorded and recorded[0][0][0] == "http_rejected"


def test_healthz():
    assert _client().get("/healthz").json() == {"ok": True}
