"""Per-plane MCP tool submodules — split out of proximo.server (2026-07-02).

Each module here defines a cohesive group of `@tool()`-decorated wrappers. The mutation
funnel (mcp, tool, _svc/_pbs/_pmg/_pdm, _plan, _audited, _auto_undo, _ledger, the 5-gate
wiring, and the three manual-audit-path exec tools) stays in `proximo.server`; these
modules import the shared names they need from there.

Two import shapes are used, deliberately different:

- `_plan`, `_audited`, `tool`, and the sibling-module plan_*/action functions are imported
  directly by name (`from proximo.server import _plan, _audited, tool`) — nothing ever
  monkeypatches these, so a plain import-time binding is fine.
- `_svc`, `_pbs`, `_pmg`, `_pdm` are NEVER imported by name. Tests monkeypatch these four
  directly on the `proximo.server` module object (`monkeypatch.setattr(server, "_svc",
  fake)`) to inject fake backends; a bare `from proximo.server import _svc` would capture
  its OWN module-level binding at import time, so patching `server._svc` would silently
  not affect it (the classic stale-binding trap). These modules instead do
  `import proximo.server as _proximo_server` and call `_proximo_server._svc()` etc., which
  resolves the (possibly-patched) attribute at CALL time. Don't "simplify" these back to
  bare-name imports — it would silently break every test that patches `server._svc`.

`proximo.server` re-imports every name from these modules by hand (see the bottom of
server.py) so that (a) importing `proximo.server` still registers all tools with FastMCP
as a side effect, and (b) the pre-existing `server.<tool_name>` attribute surface (direct
tool calls in tests, `getattr(server, name)` introspection sweeps, the CLI's `pve_doctor`
call) keeps working unchanged.
"""
