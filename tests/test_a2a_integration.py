"""End-to-end integration tests for the A2A face.

These cover what the unit tests do NOT: the full async ``execute()`` path (TaskUpdater, get_data_parts,
new_data_part) and serving the agent card over real HTTP. The audit ledger is used as the oracle — because
every A2A skill routes to an audited server tool, PLAN-by-default and PROVE are both asserted through the
whole executor, not just the ``_dispatch`` seam.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from proximo.a2a.executor import ProximoAgentExecutor

pytest.importorskip("a2a")
from a2a.helpers.proto_helpers import new_data_part, new_text_part  # noqa: E402
from a2a.types import Message  # noqa: E402

from test_a2a_executor import _wire  # reuse the fake PVE backend harness  # noqa: E402


class _CapturingQueue:
    """Minimal EventQueue stand-in — TaskUpdater only awaits enqueue_event."""

    def __init__(self) -> None:
        self.events: list = []

    async def enqueue_event(self, event) -> None:
        self.events.append(event)


def _msg(skill: str | None, params=None, *, text_only: bool = False) -> Message:
    if text_only:
        return Message(message_id="m1", parts=[new_text_part("hello, no skill here")])
    data: dict = {"skill": skill}
    if params is not None:
        data["params"] = params
    return Message(message_id="m1", parts=[new_data_part(data)])


def _ctx(message: Message) -> SimpleNamespace:
    # execute() only reads task_id / context_id / message.
    return SimpleNamespace(task_id="t1", context_id="c1", message=message)


def _run(skill, params=None, *, text_only=False) -> None:
    asyncio.run(ProximoAgentExecutor().execute(_ctx(_msg(skill, params, text_only=text_only)), _CapturingQueue()))


def _entries(log_path: str) -> list[dict]:
    out: list[dict] = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


# ---------------------------------------------------------------------------
# PLAN-by-default through the FULL async execute() path
# ---------------------------------------------------------------------------


def test_execute_mutating_no_confirm_plans_and_does_not_mutate(tmp_path, monkeypatch):
    _, api, _, _, log = _wire(tmp_path, monkeypatch, status={"status": "running", "name": "w", "uptime": 9})
    _run("guest_power", {"vmid": "102", "action": "reboot"})

    assert api.powered == [], "no-confirm A2A call must NOT mutate (PLAN-by-default end-to-end)"
    acts = [(e["action"], e["outcome"]) for e in _entries(log)]
    assert ("pve_guest_power", "planned") in acts, "the plan must be recorded (PROVE)"
    assert not any(a == "pve_guest_power" and o != "planned" for a, o in acts), "must not execute"


def test_execute_mutating_confirm_true_executes(tmp_path, monkeypatch):
    _, api, _, _, log = _wire(tmp_path, monkeypatch)
    _run("guest_power", {"vmid": "102", "action": "reboot", "confirm": True})

    assert api.powered == [("102", "reboot")], "explicit confirm=true must execute over A2A"
    acts = [(e["action"], e["outcome"]) for e in _entries(log)]
    assert ("pve_guest_power", "planned") in acts and any(
        a == "pve_guest_power" and o not in ("planned",) for a, o in acts
    ), "confirm path records BOTH a plan and an execution (PLAN->PROVE weld)"


def test_execute_read_skill_returns_result(tmp_path, monkeypatch):
    _, _, _, _, log = _wire(tmp_path, monkeypatch)
    _run("node_status", {})
    acts = [e["action"] for e in _entries(log)]
    assert "pve_node_status" in acts, "a read skill must route through and be audited"


# ---------------------------------------------------------------------------
# Rejections are audited (PROVE at the A2A boundary) — the LOW redteam fix
# ---------------------------------------------------------------------------


def test_execute_unknown_skill_audits_rejection(tmp_path, monkeypatch):
    _, api, _, _, log = _wire(tmp_path, monkeypatch)
    _run("totally_not_a_skill", {})

    assert api.powered == []
    ents = _entries(log)
    assert any(e["action"] == "a2a_rejected" and e["outcome"] == "rejected" for e in ents), (
        "a rejected A2A probe must leave a PROVE trace"
    )


def test_execute_no_data_part_audits_rejection(tmp_path, monkeypatch):
    _, _, _, _, log = _wire(tmp_path, monkeypatch)
    _run(None, text_only=True)
    ents = _entries(log)
    assert any(e["action"] == "a2a_rejected" for e in ents)


def test_execute_bad_param_audits_rejection_and_does_not_mutate(tmp_path, monkeypatch):
    _, api, _, _, log = _wire(tmp_path, monkeypatch)
    _run("guest_power", {"vmid": "102", "action": "stop", "confirm": "true"})  # confirm as string -> reject
    assert api.powered == []
    assert any(e["action"] == "a2a_rejected" for e in _entries(log))


def test_execute_non_string_skill_audits_rejection(tmp_path, monkeypatch):
    """A non-string 'skill' field (e.g. a list) must not crash past the audit trail —
    it must be recorded as a rejected A2A call, same as any other malformed probe."""
    _, api, _, _, log = _wire(tmp_path, monkeypatch)
    _run(["not", "a", "string"], {})
    assert api.powered == []
    assert any(e["action"] == "a2a_rejected" and e["outcome"] == "rejected" for e in _entries(log))


# ---------------------------------------------------------------------------
# The agent card is served over real HTTP at the well-known path
# ---------------------------------------------------------------------------


def test_agent_card_served_over_http():
    from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH
    from starlette.testclient import TestClient

    from proximo.a2a.app import build_app
    from proximo.a2a.skills import SKILLS

    # The DNS-rebind Host guard (TrustedHostMiddleware) is now always installed, so the client must
    # present a loopback Host like a real client hitting the loopback-bound server — TestClient's
    # default "testserver" Host is correctly refused (400) by the guard.
    client = TestClient(build_app(), base_url="http://localhost")
    resp = client.get(AGENT_CARD_WELL_KNOWN_PATH)
    assert resp.status_code == 200, f"card endpoint returned {resp.status_code}"
    body = resp.json()
    assert "Proximo" in body.get("name", ""), f"unexpected card name: {body.get('name')!r}"
    assert len(body.get("skills", [])) == len(SKILLS), "every slice skill must be advertised on the card"
