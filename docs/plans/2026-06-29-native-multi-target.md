# Native Multi-Target Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let one Proximo instance register and reach multiple Proxmox remotes (PVE/PBS/PMG/PDM, internal or external) via an explicit per-tool `proximo_target=` selector, with no behavior change when it is omitted.

**Architecture:** A TOML registry of named remotes (`PROXIMO_TARGETS`). A per-call `contextvars.ContextVar` carries the active target; the four plane resolvers (`_svc/_pbs/_pmg/_pdm`) read it (`None` → today's `from_env()`). A single `@tool` decorator (wrapping `mcp.tool` + a `target_aware` wrapper) injects `proximo_target` into each tool's `__signature__` so FastMCP advertises it — tool bodies and helpers stay untouched, which makes wrong-box operations structurally impossible. PROVE records the active target in a new `remote` field on its one chain.

**Tech Stack:** Python 3.13, `mcp` FastMCP, `httpx`, stdlib `tomllib`/`contextvars`, pytest, ruff, pyright, uv.

## Global Constraints

- **Selector param name:** `proximo_target` (verbatim). NOT `target` (collides with migration-node param on 7 tools) and NOT `remote` (collides with PDM remote-name param on 10 tools).
- **Backward compat (locked):** `proximo_target=None` AND/OR no `PROXIMO_TARGETS` → `from_env()`, byte-identical to today. Every existing test must stay green untouched.
- **Secrets by reference:** registry carries `token_path`/`password_path`, never a secret value.
- **Fail-loud, fail-closed:** unknown target, kind mismatch, no-registry-but-named, malformed TOML, missing required field → `ProximoError` with a clear message. TLS fail-closed (`verify_tls=false` + no `ca_bundle` → backend refuses) applies to target configs exactly as to env.
- **Leak posture:** all fixtures + the committed `targets.example.toml` use doc ranges ONLY (`192.0.2.0/24`, `198.51.100.0/24`, `example.com`). No real IPs/nodes/`/root` paths/tokens.
- **Honest semver:** stays `0.x`. Version bump is a separate intentional step at release, not in these tasks.
- **Test command (authoritative):** `uv run python -m pytest -q` (full suite, 0 skipped). Single file: `uv run python -m pytest tests/test_targets.py -q`.
- **Ledger invariant:** `verify()` rebuilds `body = {k:v for k,v in entry.items() if k not in _CHAIN_FIELDS}` (`_CHAIN_FIELDS=("prev_hash","entry_hash","alg")`). Any new body field is hashed generically — so a `remote` field is backward-compatible by construction. Add `remote` to the body ONLY when targeted (omit on the default path) so default-path entry hashes are unchanged.

---

## File Structure

- **Create** `src/proximo/targets.py` — registry parse, `_active_target` contextvar, `active_target()`, `resolve_target_fields()`, `target_aware()` wrapper, `ledger_remote()`. One responsibility: target resolution + the selector mechanism. Imports `ProximoError` from `.backends` (no cycle: `config.py` does NOT import `targets.py`).
- **Create** `tests/test_targets.py` — registry + resolution + wrapper + schema-spike tests.
- **Create** `packaging/targets.example.toml` — documented example, doc-range values only.
- **Modify** `src/proximo/config.py` — refactor `from_env` to delegate to a shared `_build(...)`; add `ProximoConfig.from_target(fields)`.
- **Modify** `src/proximo/pbs.py`, `src/proximo/pmg.py`, `src/proximo/pdm.py` — add `<Config>.from_target(fields)`.
- **Modify** `src/proximo/audit.py` — `record(..., remote=None)`; include `remote` in body when not None.
- **Modify** `src/proximo/server.py` — `tool` combined decorator; resolvers read active target; apply `@tool` to plane tools (not instance-level ones); `_audited`/`_plan` pass `remote=active_target()`.
- **Modify** `tests/test_config.py`, `tests/test_audit.py`, `tests/test_server*.py` — new behavior coverage.
- **Modify** `docs/` README target section; `src/proximo/doctor.py` optional per-target check.

---

### Task 1: Target registry + contextvar (`targets.py`)

**Files:**
- Create: `src/proximo/targets.py`
- Test: `tests/test_targets.py`

**Interfaces:**
- Produces:
  - `active_target() -> str | None` — reads the contextvar (default `None`).
  - `_active_target: ContextVar[str | None]` — the contextvar (module-level).
  - `load_registry() -> dict[str, dict]` — `{name: fields}` from `PROXIMO_TARGETS`; `{}` if unset.
  - `resolve_target_fields(name: str, expected_kind: str) -> dict` — fields for `name`, asserting `kind == expected_kind`; raises `ProximoError` on no-registry / unknown / mismatch.
  - `ledger_remote() -> str | None` — `active_target()` (used as the audit `remote` value; `None` on the default path).
  - `VALID_KINDS = frozenset({"pve","pbs","pmg","pdm"})`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_targets.py
import contextvars
import textwrap
import pytest
from proximo import targets
from proximo.backends import ProximoError

def _write_registry(tmp_path, body: str):
    p = tmp_path / "targets.toml"
    p.write_text(textwrap.dedent(body))
    return str(p)

def test_no_env_var_means_empty_registry(monkeypatch):
    monkeypatch.delenv("PROXIMO_TARGETS", raising=False)
    assert targets.load_registry() == {}

def test_active_target_defaults_none():
    assert targets.active_target() is None

def test_load_registry_parses_named_targets(monkeypatch, tmp_path):
    reg = _write_registry(tmp_path, """
        [targets.edge-pve]
        kind = "pve"
        base_url = "https://192.0.2.20:8006/api2/json"
        node = "edge"
        token_path = "/etc/proximo/edge.token"
    """)
    monkeypatch.setenv("PROXIMO_TARGETS", reg)
    r = targets.load_registry()
    assert set(r) == {"edge-pve"}
    assert r["edge-pve"]["kind"] == "pve"
    assert r["edge-pve"]["node"] == "edge"

def test_resolve_unknown_target_raises(monkeypatch, tmp_path):
    reg = _write_registry(tmp_path, """
        [targets.edge-pve]
        kind = "pve"
        base_url = "https://192.0.2.20:8006/api2/json"
        node = "edge"
        token_path = "/etc/proximo/edge.token"
    """)
    monkeypatch.setenv("PROXIMO_TARGETS", reg)
    with pytest.raises(ProximoError, match="unknown target"):
        targets.resolve_target_fields("nope", "pve")

def test_resolve_without_registry_raises(monkeypatch):
    monkeypatch.delenv("PROXIMO_TARGETS", raising=False)
    with pytest.raises(ProximoError, match="no target registry"):
        targets.resolve_target_fields("edge-pve", "pve")

def test_resolve_kind_mismatch_raises(monkeypatch, tmp_path):
    reg = _write_registry(tmp_path, """
        [targets.edge-pbs]
        kind = "pbs"
        base_url = "https://192.0.2.7:8007"
        token_path = "/etc/proximo/pbs.token"
    """)
    monkeypatch.setenv("PROXIMO_TARGETS", reg)
    with pytest.raises(ProximoError, match="is kind 'pbs', not usable by a PVE tool"):
        targets.resolve_target_fields("edge-pbs", "pve")

def test_load_registry_missing_file_raises(monkeypatch):
    monkeypatch.setenv("PROXIMO_TARGETS", "/nonexistent/targets.toml")
    with pytest.raises(ProximoError, match="missing file"):
        targets.load_registry()

def test_load_registry_bad_toml_raises(monkeypatch, tmp_path):
    p = tmp_path / "bad.toml"
    p.write_text("this is = = not toml")
    monkeypatch.setenv("PROXIMO_TARGETS", str(p))
    with pytest.raises(ProximoError, match="not valid TOML"):
        targets.load_registry()

def test_unknown_kind_raises(monkeypatch, tmp_path):
    reg = _write_registry(tmp_path, """
        [targets.weird]
        kind = "vsphere"
        base_url = "https://192.0.2.99:8006/api2/json"
    """)
    monkeypatch.setenv("PROXIMO_TARGETS", reg)
    with pytest.raises(ProximoError, match="unknown kind 'vsphere'"):
        targets.load_registry()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_targets.py -q`
Expected: FAIL (`ModuleNotFoundError: proximo.targets` / attributes missing).

- [ ] **Step 3: Write `src/proximo/targets.py`**

```python
"""Native multi-target: a registry of named Proxmox remotes + per-call target selection.

One Proximo instance can address many boxes (PVE/PBS/PMG/PDM, internal or external).
A target is selected per call via the `proximo_target` tool parameter; the selection rides
a ContextVar so the four plane resolvers — and every internal helper that re-resolves —
auto-route to the same box. No target => the env-configured box (`from_env`), unchanged.
"""
from __future__ import annotations

import contextvars
import functools
import inspect
import os
import tomllib
from typing import Optional

from .backends import ProximoError

VALID_KINDS = frozenset({"pve", "pbs", "pmg", "pdm"})

# Per-call active target. None => the env-configured default box.
_active_target: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "proximo_active_target", default=None
)


def active_target() -> Optional[str]:
    return _active_target.get()


def ledger_remote() -> Optional[str]:
    """The value recorded in the PROVE ledger's `remote` field (None on the default path)."""
    return _active_target.get()


def load_registry() -> dict[str, dict]:
    """Parse PROXIMO_TARGETS into {name: fields}. Empty dict when unset. Fail-loud otherwise."""
    path = os.environ.get("PROXIMO_TARGETS")
    if not path:
        return {}
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError as e:
        raise ProximoError(f"PROXIMO_TARGETS points to a missing file: {path}") from e
    except tomllib.TOMLDecodeError as e:
        raise ProximoError(f"PROXIMO_TARGETS is not valid TOML ({path}): {e}") from e
    targets = data.get("targets", {})
    if not isinstance(targets, dict):
        raise ProximoError("PROXIMO_TARGETS: [targets] must be a table of named remotes")
    for name, fields in targets.items():
        if not isinstance(fields, dict):
            raise ProximoError(f"PROXIMO_TARGETS: target {name!r} must be a table")
        kind = fields.get("kind")
        if kind not in VALID_KINDS:
            raise ProximoError(
                f"PROXIMO_TARGETS: target {name!r} has unknown kind {kind!r} "
                f"(valid: {sorted(VALID_KINDS)})"
            )
    return targets


def resolve_target_fields(name: str, expected_kind: str) -> dict:
    """Look up `name`, asserting it is of `expected_kind`. Fail-loud on every miss."""
    reg = load_registry()
    if not reg:
        raise ProximoError(
            f"no target registry configured (set PROXIMO_TARGETS); cannot resolve target {name!r}"
        )
    if name not in reg:
        raise ProximoError(f"unknown target {name!r} (known: {sorted(reg)})")
    fields = reg[name]
    kind = fields.get("kind")
    if kind != expected_kind:
        raise ProximoError(
            f"target {name!r} is kind {kind!r}, not usable by a {expected_kind.upper()} tool"
        )
    return fields


# Real type object (NOT a string) so FastMCP's inspect.signature(..., eval_str=True) is a no-op for it.
_TARGET_PARAM = inspect.Parameter(
    "proximo_target", inspect.Parameter.KEYWORD_ONLY, default=None, annotation=Optional[str]
)


def target_aware(fn):
    """Wrap a tool so it advertises `proximo_target` and routes the call to that box.

    The wrapped fn's body is untouched: it still calls `_svc()` etc., which read the contextvar.
    """
    @functools.wraps(fn)
    def wrapper(*args, proximo_target: Optional[str] = None, **kwargs):
        token = _active_target.set(proximo_target)
        try:
            return fn(*args, **kwargs)
        finally:
            _active_target.reset(token)

    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    insert_at = len(params)
    for i, p in enumerate(params):
        if p.kind is inspect.Parameter.VAR_KEYWORD:
            insert_at = i
            break
    params.insert(insert_at, _TARGET_PARAM)
    wrapper.__signature__ = sig.replace(parameters=params)
    return wrapper
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_targets.py -q`
Expected: PASS (all 9).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src/proximo/targets.py tests/test_targets.py
git add src/proximo/targets.py tests/test_targets.py
git commit -m "feat(targets): registry parse + active-target contextvar + target_aware wrapper"
```

---

### Task 2: `ProximoConfig.from_target` + DRY `_build` (`config.py`)

**Files:**
- Modify: `src/proximo/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: a `fields` dict (from `targets.resolve_target_fields`).
- Produces: `ProximoConfig.from_target(fields: dict) -> ProximoConfig` — same validations/defaults as `from_env`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py (add)
import pytest
from proximo.config import ProximoConfig

def test_from_target_builds_config():
    cfg = ProximoConfig.from_target({
        "kind": "pve",
        "base_url": "https://192.0.2.20:8006/api2/json",
        "node": "edge",
        "token_path": "/etc/proximo/edge.token",
        "ca_bundle": "/etc/proximo/edge-ca.pem",
        "verify_tls": True,
        "ssh_target": "edge-host",
    })
    assert cfg.api_base_url == "https://192.0.2.20:8006/api2/json"
    assert cfg.node == "edge"
    assert cfg.token_path == "/etc/proximo/edge.token"
    assert cfg.ca_bundle == "/etc/proximo/edge-ca.pem"
    assert cfg.ssh_target == "edge-host"

def test_from_target_missing_required_field_raises():
    with pytest.raises(RuntimeError, match="missing required field: node"):
        ProximoConfig.from_target({"kind": "pve",
                                   "base_url": "https://192.0.2.20:8006/api2/json",
                                   "token_path": "/etc/proximo/edge.token"})

def test_from_target_defaults_match_from_env_defaults():
    cfg = ProximoConfig.from_target({
        "kind": "pve", "base_url": "https://192.0.2.20:8006/api2/json",
        "node": "edge", "token_path": "/etc/proximo/edge.token",
    })
    assert cfg.verify_tls is True          # default on
    assert cfg.ssh_target == "pve"         # same default as from_env
    assert cfg.enable_exec is False        # safe default
    assert cfg.api_base_url.endswith("/api2/json")  # rstrip('/') applied
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/test_config.py -k from_target -q`
Expected: FAIL (`from_target` not defined).

- [ ] **Step 3: Refactor `from_env` to delegate to `_build`, add `from_target`**

In `config.py`, extract the post-gather logic (validation, warnings, construction) currently inside `from_env` into a private classmethod `_build` that takes already-extracted primitives, then have `from_env` gather from `os.environ` and call `_build`, and add `from_target` gathering from `fields` and calling `_build`. The required-field extraction differs (env raises `RuntimeError(f"Missing required Proximo env var: {k}")`; target raises `RuntimeError(f"target missing required field: {k}")`), so keep those two extraction heads separate and converge at `_build`.

```python
    @classmethod
    def _build(cls, *, api_base_url, node, token_path, ssh_target, ct_allow_raw,
               agent_allow_raw, vtls_raw, ca_bundle, enable_exec, enable_agent,
               audit_key_path, audit_keyed, redact_ledger, expected_head_raw, audit_log_path):
        # (body = the existing validation/warning/normalization block from from_env,
        #  operating on these params instead of reading os.environ directly)
        ...
        return cls(api_base_url=api_base_url.rstrip("/"), node=node, token_path=token_path,
                   ssh_target=ssh_target, ct_allowlist=ct_allowlist, audit_log_path=audit_log_path,
                   verify_tls=verify_tls, ca_bundle=ca_bundle, enable_exec=enable_exec,
                   audit_key_path=audit_key_path, audit_keyed=audit_keyed,
                   redact_ledger=redact_ledger, expected_head=expected_head, enable_agent=enable_agent,
                   agent_allowlist=agent_allowlist)

    @classmethod
    def from_env(cls) -> "ProximoConfig":
        try:
            api_base_url = os.environ["PROXIMO_API_BASE_URL"]
            node = os.environ["PROXIMO_NODE"]
            token_path = os.environ["PROXIMO_TOKEN_PATH"]
        except KeyError as e:
            raise RuntimeError(f"Missing required Proximo env var: {e.args[0]}") from e
        return cls._build(
            api_base_url=api_base_url, node=node, token_path=token_path,
            ssh_target=os.environ.get("PROXIMO_SSH_TARGET", "pve"),
            ct_allow_raw=os.environ.get("PROXIMO_CT_ALLOWLIST", ""),
            agent_allow_raw=os.environ.get("PROXIMO_AGENT_ALLOWLIST", ""),
            vtls_raw=os.environ.get("PROXIMO_VERIFY_TLS", "true"),
            ca_bundle=os.environ.get("PROXIMO_CA_BUNDLE") or None,
            enable_exec=os.environ.get("PROXIMO_ENABLE_EXEC", "false").lower() in ("1","true","yes","on"),
            enable_agent=os.environ.get("PROXIMO_ENABLE_AGENT", "false").lower() in ("1","true","yes","on"),
            audit_key_path=os.environ.get("PROXIMO_AUDIT_KEY_PATH") or None,
            audit_keyed=os.environ.get("PROXIMO_AUDIT_KEYED", "true"),
            redact_ledger=os.environ.get("PROXIMO_LEDGER_REDACT", "false").lower() in ("1","true","yes","on"),
            expected_head_raw=os.environ.get("PROXIMO_AUDIT_EXPECTED_HEAD") or "",
            audit_log_path=os.environ.get("PROXIMO_AUDIT_LOG", cls.audit_log_path),
        )

    @classmethod
    def from_target(cls, fields: dict) -> "ProximoConfig":
        try:
            api_base_url = fields["base_url"]
            node = fields["node"]
            token_path = fields["token_path"]
        except KeyError as e:
            raise RuntimeError(f"target missing required field: {e.args[0]}") from e
        return cls._build(
            api_base_url=api_base_url, node=node, token_path=token_path,
            ssh_target=fields.get("ssh_target", "pve"),
            ct_allow_raw=fields.get("ct_allowlist", ""),
            agent_allow_raw=fields.get("agent_allowlist", ""),
            vtls_raw=str(fields.get("verify_tls", "true")).lower(),
            ca_bundle=fields.get("ca_bundle") or None,
            enable_exec=bool(fields.get("enable_exec", False)),
            enable_agent=bool(fields.get("enable_agent", False)),
            audit_key_path=fields.get("audit_key_path") or None,
            audit_keyed=str(fields.get("audit_keyed", "true")),
            redact_ledger=bool(fields.get("redact_ledger", False)),
            expected_head_raw=fields.get("audit_expected_head") or "",
            audit_log_path=fields.get("audit_log", cls.audit_log_path),
        )
```

Notes for the implementer:
- `vtls_raw` in `_build` keeps the existing `.strip().lower()` + `_VTLS_FALSY`/`_VTLS_TRUTHY` logic.
- `enable_exec`/`enable_agent`/`redact_ledger` arrive already-boolean (env head computes the bool; target head uses `bool(...)`), so `_build` takes them as bools. Keep the warning blocks in `_build`.
- `ct_allow_raw`/`agent_allow_raw` are comma-strings split inside `_build` (unchanged logic). A TOML list is also fine: accept `fields.get("ct_allowlist","")` either as a string or join a list — to keep it simple, in `from_target` do `",".join(fields["ct_allowlist"]) if isinstance(fields.get("ct_allowlist"), list) else fields.get("ct_allowlist","")`.

- [ ] **Step 4: Run the full config suite (regression + new)**

Run: `uv run python -m pytest tests/test_config.py -q`
Expected: PASS — new `from_target` tests AND every existing `from_env` test (the refactor must not change `from_env` behavior).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src/proximo/config.py tests/test_config.py
git add src/proximo/config.py tests/test_config.py
git commit -m "feat(config): ProximoConfig.from_target via shared _build (from_env unchanged)"
```

---

### Task 3: Schema spike — prove `proximo_target` reaches the live tool schema

**Files:**
- Test: `tests/test_targets.py` (add)

**Interfaces:**
- Consumes: `targets.target_aware`, `mcp.server.fastmcp.FastMCP`.

This is the de-risking gate from the spec. It must pass before the per-plane sweeps (Tasks 4/6).

- [ ] **Step 1: Write the spike test**

```python
# tests/test_targets.py (add)
def test_target_aware_injects_proximo_target_into_fastmcp_schema():
    from mcp.server.fastmcp import FastMCP
    from proximo import targets as T

    captured = {}

    m = FastMCP("spike")

    @m.tool()
    @T.target_aware
    def sample(vmid: str, node: str | None = None) -> dict:
        captured["active"] = T.active_target()
        return {"vmid": vmid, "node": node}

    # 1. The generated input schema advertises proximo_target.
    import anyio
    tools = anyio.run(m.list_tools)
    sample_tool = next(t for t in tools if t.name == "sample")
    assert "proximo_target" in sample_tool.inputSchema["properties"]

    # 2. Calling with proximo_target routes the contextvar; body never sees it.
    anyio.run(lambda: m.call_tool("sample", {"vmid": "131", "proximo_target": "edge-pve"}))
    assert captured["active"] == "edge-pve"

    # 3. The contextvar is reset after the call (no leak across calls).
    assert T.active_target() is None
```

- [ ] **Step 2: Run the spike**

Run: `uv run python -m pytest tests/test_targets.py -k injects -q`
Expected: PASS.

**If it FAILS** (FastMCP ignores `__signature__`): STOP and switch to the fallback in the spec — add a literal `proximo_target: str | None = None` param to each tool signature via script, keeping the contextvar resolution. Re-confirm with this same test (minus the wrapper) before proceeding. Record the decision in the plan before continuing.

- [ ] **Step 3: Commit**

```bash
git add tests/test_targets.py
git commit -m "test(targets): spike — proximo_target round-trips into the FastMCP schema"
```

---

### Task 4: Wire PVE resolution + `@tool` decorator + apply to PVE tools

**Files:**
- Modify: `src/proximo/server.py`
- Test: `tests/test_server_multitarget.py` (create)

**Interfaces:**
- Consumes: `targets.active_target`, `targets.resolve_target_fields`, `targets.target_aware`, `ProximoConfig.from_target`.
- Produces: `tool` decorator (`= target-aware mcp.tool`); `_svc()` routes by active target.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_server_multitarget.py
import textwrap
import pytest
from proximo import server, targets
from proximo.backends import ProximoError

def _registry(monkeypatch, tmp_path, body):
    p = tmp_path / "targets.toml"; p.write_text(textwrap.dedent(body))
    monkeypatch.setenv("PROXIMO_TARGETS", str(p))

def test_svc_default_uses_from_env(monkeypatch):
    monkeypatch.setenv("PROXIMO_API_BASE_URL", "https://192.0.2.10:8006/api2/json")
    monkeypatch.setenv("PROXIMO_NODE", "home")
    monkeypatch.setenv("PROXIMO_TOKEN_PATH", "/etc/proximo/home.token")
    token = targets._active_target.set(None)
    try:
        cfg, _api, _exec, _led = server._svc()
        assert cfg.node == "home"
    finally:
        targets._active_target.reset(token)

def test_svc_named_target_uses_registry(monkeypatch, tmp_path):
    monkeypatch.setenv("PROXIMO_API_BASE_URL", "https://192.0.2.10:8006/api2/json")
    monkeypatch.setenv("PROXIMO_NODE", "home")
    monkeypatch.setenv("PROXIMO_TOKEN_PATH", "/etc/proximo/home.token")
    _registry(monkeypatch, tmp_path, """
        [targets.edge]
        kind = "pve"
        base_url = "https://198.51.100.20:8006/api2/json"
        node = "edge"
        token_path = "/etc/proximo/edge.token"
    """)
    token = targets._active_target.set("edge")
    try:
        cfg, _api, _exec, _led = server._svc()
        assert cfg.node == "edge"
        assert cfg.api_base_url.startswith("https://198.51.100.20")
    finally:
        targets._active_target.reset(token)

def test_svc_pbs_target_on_pve_resolver_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("PROXIMO_API_BASE_URL", "https://192.0.2.10:8006/api2/json")
    monkeypatch.setenv("PROXIMO_NODE", "home")
    monkeypatch.setenv("PROXIMO_TOKEN_PATH", "/etc/proximo/home.token")
    _registry(monkeypatch, tmp_path, """
        [targets.backup]
        kind = "pbs"
        base_url = "https://192.0.2.7:8007"
        token_path = "/etc/proximo/pbs.token"
    """)
    token = targets._active_target.set("backup")
    try:
        with pytest.raises(ProximoError, match="not usable by a PVE tool"):
            server._svc()
    finally:
        targets._active_target.reset(token)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/test_server_multitarget.py -q`
Expected: FAIL (`_svc` still calls `from_env` unconditionally).

- [ ] **Step 3: Add the `tool` decorator and route `_svc()`**

In `server.py`, after `mcp = FastMCP("proximo")` and the imports, add:

```python
from .targets import active_target, resolve_target_fields, target_aware

def tool(*d_args, **d_kwargs):
    """Like @mcp.tool(), but the tool also advertises `proximo_target` and routes the call.

    Apply to every plane tool (pve_/pbs_/pmg_/pdm_). Instance-level tools that act on THIS
    Proximo (e.g. audit_verify) intentionally stay on @mcp.tool() — no proximo_target.
    """
    inner = mcp.tool(*d_args, **d_kwargs)
    def deco(fn):
        return inner(target_aware(fn))
    return deco

def _resolve_pve_config() -> ProximoConfig:
    name = active_target()
    if name is None:
        return ProximoConfig.from_env()
    return ProximoConfig.from_target(resolve_target_fields(name, "pve"))
```

Then change `_svc()` (server.py:1023-1026):

```python
def _svc() -> tuple[ProximoConfig, ApiBackend, ExecBackend, AuditLedger]:
    cfg = _resolve_pve_config()
    return cfg, ApiBackend(cfg), ExecBackend(cfg), open_ledger(cfg)
```

- [ ] **Step 4: Apply `@tool` to all `pve_*` tools**

The pve tool decorators are uniform `@mcp.tool()`. Sweep ONLY the pve ones (leave pbs/pmg/pdm for Task 6, and leave instance-level tools on `@mcp.tool`). Identify each `@mcp.tool()` immediately preceding a `def pve_...(`:

```bash
# Preview the pve decorator sites:
uv run python - <<'PY'
import re, pathlib
src = pathlib.Path("src/proximo/server.py").read_text().splitlines()
for i, ln in enumerate(src):
    if ln.strip().startswith("def pve_") and i and src[i-1].strip() == "@mcp.tool()":
        print(i, src[i].strip()[:60])
PY
```

Replace the `@mcp.tool()` line directly above each `def pve_...` with `@tool()`. Do it with a Python rewrite (NOT a blind global sed — instance-level tools and other planes must stay `@mcp.tool`):

```bash
uv run python - <<'PY'
import re, pathlib
p = pathlib.Path("src/proximo/server.py")
src = p.read_text().splitlines()
out = list(src)
for i, ln in enumerate(src):
    if ln.strip().startswith("def pve_") and i and src[i-1].strip() == "@mcp.tool()":
        out[i-1] = src[i-1].replace("@mcp.tool()", "@tool()")
p.write_text("\n".join(out) + "\n")
print("done")
PY
```

- [ ] **Step 5: Run the new tests + the full suite**

Run: `uv run python -m pytest tests/test_server_multitarget.py -q && uv run python -m pytest -q`
Expected: PASS (new multitarget tests green; full suite unchanged-green — `proximo_target` defaults to None so existing pve tool tests are unaffected).

- [ ] **Step 6: Lint, type-check, commit**

```bash
uv run ruff check src/proximo/server.py tests/test_server_multitarget.py
uv run pyright
git add src/proximo/server.py tests/test_server_multitarget.py
git commit -m "feat(server): route PVE tools by proximo_target (contextvar); @tool decorator"
```

---

### Task 5: PROVE — record the active target in a `remote` field

**Files:**
- Modify: `src/proximo/audit.py`, `src/proximo/server.py`
- Test: `tests/test_audit.py`, `tests/test_server_multitarget.py`

**Interfaces:**
- Produces: `AuditLedger.record(..., remote: str | None = None)` — adds `remote` to the body iff not None.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_audit.py (add)
def test_record_targeted_includes_remote(tmp_path):
    from proximo.audit import AuditLedger
    led = AuditLedger(str(tmp_path / "audit.log"), key=None)
    entry = led.record("pve_guest_power", target="131", mutation=True, remote="edge")
    assert entry["remote"] == "edge"
    assert led.verify().ok

def test_record_default_omits_remote_unchanged_body(tmp_path):
    from proximo.audit import AuditLedger
    led = AuditLedger(str(tmp_path / "audit.log"), key=None)
    entry = led.record("pve_guest_power", target="131", mutation=True)  # no remote
    assert "remote" not in entry
    assert led.verify().ok

def test_mixed_remote_and_default_entries_verify(tmp_path):
    from proximo.audit import AuditLedger
    led = AuditLedger(str(tmp_path / "audit.log"), key=None)
    led.record("a", target="1")                       # default
    led.record("b", target="2", remote="edge")        # targeted
    led.record("c", target="3")                       # default
    assert led.verify().ok
```

```python
# tests/test_server_multitarget.py (add) — the wrong-box-undo regression guard
def test_audited_records_active_target_as_remote(monkeypatch, tmp_path):
    """A targeted, audited mutation must record remote=<target>, proving PROVE saw the right box."""
    import proximo.server as server
    from proximo import targets
    recorded = {}
    class _FakeLedger:
        def record(self, action, *, target, mutation=False, outcome="ok", detail=None, remote=None):
            recorded.update(action=action, remote=remote); return {}
    monkeypatch.setattr(server, "_svc", lambda: (None, None, None, _FakeLedger()))
    token = targets._active_target.set("edge")
    try:
        server._audited("pve_guest_power", "131", lambda: {"ok": True}, mutation=True)
    finally:
        targets._active_target.reset(token)
    assert recorded["remote"] == "edge"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/test_audit.py -k remote tests/test_server_multitarget.py -k remote -q`
Expected: FAIL (`record()` has no `remote` kwarg).

- [ ] **Step 3: Add `remote` to `record()` and pass it from the server helpers**

`audit.py` `record()` signature + body:

```python
    def record(self, action: str, *, target: str, mutation: bool = False,
               outcome: str = "ok", detail: dict[str, Any] | None = None,
               remote: str | None = None) -> dict[str, Any]:
        target = _sanitize_target(target)
        body = {
            "ts": datetime.now(UTC).isoformat(),
            "action": action,
            "target": target,
            "mutation": mutation,
            "outcome": outcome,
            "detail": detail or {},
        }
        if remote is not None:                     # omit on the default path => default-entry hashes unchanged
            body["remote"] = _sanitize_target(remote)
        # ... (rest unchanged: json-finite check, lock, chain append)
```

In `server.py`, import `ledger_remote` and pass it at every `audit.record(...)` call inside `_audited` and `_plan` (and the other recorders in 1079-1226). Pattern, for each `audit.record(...)` site:

```python
from .targets import ledger_remote
# ...
audit.record(action, target=target, mutation=mutation, outcome=outcome,
             detail=detail, remote=ledger_remote())
```

(`verify()` needs NO change — it rebuilds `body` from all non-`_CHAIN_FIELDS` keys, so `remote` is hashed generically.)

- [ ] **Step 4: Run the audit + server suites**

Run: `uv run python -m pytest tests/test_audit.py tests/test_server_multitarget.py -q && uv run python -m pytest -q`
Expected: PASS (new tests green; full suite unchanged-green).

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/proximo/audit.py src/proximo/server.py
git add src/proximo/audit.py src/proximo/server.py tests/test_audit.py tests/test_server_multitarget.py
git commit -m "feat(prove): record active target as the ledger remote field (default path unchanged)"
```

---

### Task 6: Enable PBS, PMG, PDM (per plane)

**Files:**
- Modify: `src/proximo/pbs.py`, `src/proximo/pmg.py`, `src/proximo/pdm.py`, `src/proximo/server.py`
- Test: `tests/test_server_multitarget.py`

**Interfaces:**
- Produces: `PbsConfig.from_target`, `PmgConfig.from_target`, `PdmConfig.from_target`; `_pbs/_pmg/_pdm` route by active target; `@tool` applied to pbs_/pmg_/pdm_ tools.

Do ONE plane at a time (pbs → pmg → pdm). For each plane:

- [ ] **Step 1: Write the failing resolver tests** (mirror Task 4's three tests for the plane — default-from-env, named-from-registry, wrong-kind-raises — using that plane's required env vars from the spec: PBS `PROXIMO_PBS_BASE_URL`/`PROXIMO_PBS_TOKEN_PATH`; PMG `PROXIMO_PMG_BASE_URL`/`PROXIMO_PMG_PASSWORD_PATH`; PDM `PROXIMO_PDM_BASE_URL`/`PROXIMO_PDM_TOKEN_PATH`).

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Add `<Config>.from_target(fields)`** to the plane module (mirror the env field-mapping in that class's `from_env`, reading from `fields` with the same defaults; secret stays a path: `token_path` / `password_path`). Route the resolver in `server.py`:

```python
def _resolve_pbs_config() -> PbsConfig:
    name = active_target()
    if name is None:
        return PbsConfig.from_env()
    return PbsConfig.from_target(resolve_target_fields(name, "pbs"))
# _pbs(): cfg = _resolve_pbs_config(); return cfg, PbsBackend(cfg)
```

(pmg → `"pmg"` + `PmgConfig`/`PmgBackend`; pdm → `"pdm"` + `PdmConfig`/`PdmBackend`.)

- [ ] **Step 4: Apply `@tool`** to that plane's tool decorators via the same scoped Python rewrite as Task 4 step 4, with the prefix changed (`def pbs_` / `def pmg_` / `def pdm_`).

- [ ] **Step 5: Run plane tests + full suite green.** `uv run python -m pytest -q`

- [ ] **Step 6: Commit** (`feat(server): route <PLANE> tools by proximo_target`).

---

### Task 7: Example registry + docs + doctor

**Files:**
- Create: `packaging/targets.example.toml`
- Modify: `README` (target section), `src/proximo/doctor.py`

- [ ] **Step 1:** Write `packaging/targets.example.toml` — the §"Target registry" example from the spec verbatim (doc-range values only), with a header comment: secrets by reference, file is runtime config (untracked), `kind` ∈ {pve,pbs,pmg,pdm}, omit `proximo_target` for the env box.

- [ ] **Step 2:** Add a README "Multiple targets" subsection: set `PROXIMO_TARGETS`, pass `proximo_target="name"`, the `None`→env rule, kind-safety, that PROVE records `remote`, and that arming is per-target/out-of-band (John's hand).

- [ ] **Step 3 (optional, CAPTURE-only):** extend `proximo doctor` to, when `PROXIMO_TARGETS` is set, list each target and do a read-only reachability probe (`ApiBackend(...).version()` etc.) per target, reporting reachable/unreachable. No mutation. Test with a registry pointing at an unreachable doc-range IP → reported unreachable, not crash.

- [ ] **Step 4:** `uv run python -m pytest -q && uv run ruff check src && uv run pyright`; commit.

---

### Task 8: Verification & hardening (NOT plain TDD — run via the team + live lab)

- [ ] **Step 1: Authoritative full suite** — `uv run python -m pytest -q` (0 failures, 0 unexpected skips), `uv run ruff check src tests`, `uv run pyright`.
- [ ] **Step 2: Leak audit** — `uv run python scripts/release_leak_audit.py audit` (models the publish tree); grep new files for real IPs/nodes/`/root`/tokens. All fixtures doc-range only.
- [ ] **Step 3: Live lab validation** — register `pve-test1` and `pve-test2` (proximo-lab, sealed `vmbr1`) as two pve targets; prove a read hits the intended box and a (throwaway) mutation's ledger entry shows the right `remote`; confirm wrong-kind error live. STOP the lab guests through Proximo when done.
- [ ] **Step 4: Adversarial redteam** — dispatch reviewers (per `feedback_haiku-redteam-before-done` / agent-teams) against: registry parse (path traversal / injection in target names), kind-confusion bypass, contextvar leak across calls/threads, secret-by-reference (no token in registry/ledger), wrong-box on every multi-step/UNDO path. Fix findings TDD.
- [ ] **Step 5:** Update CHANGELOG (Unreleased), `docs/specs` status → Implemented. Hold the version bump + public push for John.

---

## Self-Review

**Spec coverage:** registry (T1,T7) · contextvar resolution + None→env (T1,T4,T6) · proximo_target per tool, bodies untouched (T1,T3,T4,T6) · kind safety (T1,T4,T6) · PROVE remote, one chain (T5) · arm out-of-scope (docs T7) · backward-compat (Global Constraints + every "full suite green" step) · leak posture (Global + T7,T8) · testing incl. wrong-box-undo (T5) + live lab + redteam (T8). No gaps.

**Placeholder scan:** `_build` body in T2 references "the existing validation block" — this is a guided refactor of named existing code, not a placeholder (the exact source is `config.py:96-160`); every other step has runnable code/commands.

**Type consistency:** `proximo_target` (selector) and `remote` (ledger field) used consistently throughout; `resolve_target_fields(name, expected_kind)`, `ProximoConfig.from_target(fields)`, `record(..., remote=...)` signatures match across tasks.
