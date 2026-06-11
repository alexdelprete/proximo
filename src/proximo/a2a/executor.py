"""ProximoAgentExecutor — the A2A dispatch seam.

Every inbound A2A skill call routes through ``_dispatch``, which is the single
chokepoint that enforces:
  1. the skill exists in the curated slice;
  2. ``validate_and_build`` guards params + PLAN-by-default before the server
     function is called;
  3. any exception is caught, classified, and surfaced as a clean failed-task
     status (no traceback / secret leakage to the caller).

The ``execute`` coroutine parses the inbound message, delegates to the
thread-offloaded ``_dispatch``, then emits the result (or failure) back through
the A2A event queue.

Message convention
------------------
The inbound ``Message`` must contain at least one ``DataPart`` whose ``.data``
is a JSON object with the shape::

    {"skill": "<skill-id>", "params": {<param-dict>}}

``params`` may be absent or null (treated as an empty dict).  Any other shape
produces a clean failed-task response with a description of the expected format.
"""

from __future__ import annotations

import warnings

import anyio.to_thread
from a2a.helpers.proto_helpers import get_data_parts, new_data_part, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.utils.errors import UnsupportedOperationError

from .. import server
from .skills import SKILLS_BY_ID, A2AParamError, validate_and_build


class ProximoAgentExecutor(AgentExecutor):
    """Stateless A2A executor — parses, validates, routes, and replies."""

    # ------------------------------------------------------------------
    # Sync dispatch (unit-testable without any async machinery)
    # ------------------------------------------------------------------

    def _dispatch(self, skill_id: str, raw_params: dict | None) -> dict:
        """Validate and execute one skill call.  Raises ``A2AParamError`` on bad input.

        This is the trust-critical chokepoint:
          * unknown skill id  → A2AParamError (never reaches any server fn)
          * bad/missing/mistyped params  → A2AParamError (via validate_and_build)
          * PLAN-by-default  → validate_and_build never injects confirm
          * EXCLUDED_FROM_SLICE used as skill id  → A2AParamError (those are server
            fn names, not skill ids; they don't appear in SKILLS_BY_ID)
        """
        skill = SKILLS_BY_ID.get(skill_id)
        if skill is None:
            raise A2AParamError(f"unknown skill '{skill_id}'")
        kwargs = validate_and_build(skill, raw_params)  # the guard — never bypass
        return skill.tool(**kwargs)

    def _audit_rejection(self, skill_id: str | None, reason: str) -> None:
        """Best-effort PROVE trace for a REJECTED A2A call (unknown skill / bad params / no skill).

        The primary guarantee is the failed-task returned to the caller; this records the rejection
        to the same tamper-evident ledger the routed tools use, so hostile enumeration of the slice
        is not invisible (it completes the PROVE chain at the A2A boundary). A ledger write must never
        mask the rejection response, so it is best-effort. Only the reason + skill id are recorded —
        never raw params or secrets.
        """
        try:
            _, _, _, audit = server._svc()
            audit.record("a2a_rejected", target=str(skill_id or "<none>"), mutation=False,
                         outcome="rejected", detail={"reason": reason})
        except Exception as exc:  # noqa: BLE001 — supplementary audit; never break the rejection path
            # Don't swallow silently: a PROVE ledger that can't record is itself worth surfacing. But
            # the rejection RESPONSE to the caller is the primary guarantee, so we warn — never raise.
            warnings.warn(f"A2A rejection audit failed to record: {type(exc).__name__}", stacklevel=2)

    # ------------------------------------------------------------------
    # Async execute (framework entry point)
    # ------------------------------------------------------------------

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Parse the inbound message, route to _dispatch, publish result or failure."""
        task_id = context.task_id or ""
        context_id = context.context_id or ""
        updater = TaskUpdater(event_queue, task_id, context_id)

        # --- parse inbound skill invocation ---
        skill_id: str | None = None
        params: dict | None = None

        message = context.message
        if message is not None:
            data_parts = get_data_parts(message.parts)
            for payload in data_parts:
                if isinstance(payload, dict) and "skill" in payload:
                    skill_id = payload["skill"]
                    raw = payload.get("params")
                    params = raw if isinstance(raw, dict) else {}
                    break

        if skill_id is None:
            self._audit_rejection(None, "no skill in inbound message")
            await updater.failed(
                updater.new_agent_message([
                    new_text_part(
                        "Expected a DataPart with shape {\"skill\": \"<id>\", \"params\": {...}}."
                        " No such part found in the inbound message."
                    )
                ])
            )
            return

        # --- dispatch (blocking I/O offloaded to a thread) ---
        try:
            result: dict = await anyio.to_thread.run_sync(self._dispatch, skill_id, params)
        except A2AParamError as exc:
            self._audit_rejection(skill_id, str(exc))
            await updater.failed(
                updater.new_agent_message([new_text_part(str(exc))])
            )
            return
        except Exception as exc:  # noqa: BLE001
            await updater.failed(
                updater.new_agent_message([
                    new_text_part(f"skill '{skill_id}' failed: {type(exc).__name__}")
                ])
            )
            return

        # --- emit result as a data artifact then complete ---
        await updater.add_artifact(parts=[new_data_part(result)], name="result")
        await updater.complete()

    # ------------------------------------------------------------------
    # Cancel — not supported (skills are short, single-shot operations)
    # ------------------------------------------------------------------

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise UnsupportedOperationError()
