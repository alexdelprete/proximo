"""Proximo's A2A (Agent2Agent) face — the second protocol head on the same trust core.

Proximo is an MCP server first (see ``proximo.server``). This package adds an OPTIONAL
A2A slice so Proximo can also be a first-class Agent2Agent participant — "the Proxmox
operator agent" other agents can call.

Design (one core, two faces):
    Every A2A skill ROUTES to an existing ``proximo.server`` MCP tool function. It does NOT
    reimplement any management or trust logic. PLAN-by-default, the tamper-evident ledger
    (PROVE), auto-undo (UNDO), the CTID allowlist and exec-off fail-closed gates all hold
    automatically, because the A2A face calls the exact same trust-instrumented entrypoints.

Layering (import-safe):
    - ``skills``   — the curated skill registry + the PLAN-by-default param guard. Pure Python,
                     NO a2a-sdk import; importable anywhere (tests, card, executor).
    - ``card``     — builds the proto ``AgentCard`` from the registry (needs a2a-sdk).
    - ``executor`` — the ``AgentExecutor`` that validates + routes a skill call (needs a2a-sdk).
    - ``app``      — the Starlette/JSON-RPC server + ``proximo-a2a`` entrypoint (needs a2a-sdk + uvicorn).

The a2a-sdk is an OPTIONAL dependency (``pip install 'proximo-proxmox[a2a]'``); only ``card``/``executor``/
``app`` need it. ``skills`` stays dependency-light so the contract is always importable.
"""
