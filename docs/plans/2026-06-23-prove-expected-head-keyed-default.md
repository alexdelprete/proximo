# PROVE: `expected_head` + keyed-by-default — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose `expected_head` head-pinning through `audit_verify` (+ A2A) and make keyed (HMAC) PROVE the default, with zero-breakage auto seal-and-rotate of existing unkeyed ledgers.

**Architecture:** All ledger-mode/lifecycle decisions move into one factory `open_ledger(cfg)` in `audit.py` (resolve mode → load/generate key → detect on-disk mode → seal-and-rotate if unkeyed-but-keyed-wanted → return ledger). `server._svc()` calls it. The `audit_verify` tool and A2A skill gain an optional `expected_head` that falls back to a config default.

**Tech Stack:** Python 3, `uv`-managed venv, pytest, ruff, pyright, FastMCP, a2a-sdk. Stdlib `hashlib`/`hmac`/`fcntl`/`os` for the crypto/locking (already used in `audit.py`).

## Global Constraints

- Spec: `docs/specs/2026-06-23-prove-expected-head-keyed-default-design.md`. Branch: `prove-expected-head` (already created, spec committed).
- Commands (Proximo's own venv): `uv run python -m pytest -q` (full suite, 2,500+ green, 0 skipped) · `uv run ruff check src tests` · `uv run pyright` (src only).
- **Public repo** — no secrets, RFC1918 IPs, internal hostnames, or `/root/...` paths in any tracked file.
- **Ledger invariant (do not break):** a log file is all-keyed or all-unkeyed for its whole life; verification decides keyed-vs-unkeyed from the ledger's key, **never** the entry's own `alg` tag.
- **Honesty (keep in all docs/output):** tamper-EVIDENT not tamper-PROOF; keying is *marginal* hardening (same-user write-attacker can usually read the 0600 key); the off-box `expected_head` anchor is the strong guarantee.
- **No silent downgrade:** keyed-on + key-gen failure → fail loud; never fall back to unkeyed silently.
- Commit style: conventional prefix (`feat:`/`test:`/`docs:`/`refactor:`), no `Co-Authored-By` trailer, identity stays John Broadway (repo default).

---

### Task 1: Config — `expected_head` field + parse + validate

**Files:**
- Modify: `src/proximo/config.py` (add field after `redact_ledger`; parse in `from_env`)
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `ProximoConfig.expected_head: str | None` (default `None`); env `PROXIMO_AUDIT_EXPECTED_HEAD`; malformed (not 64-char lowercase hex) → `RuntimeError` at `from_env`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py — append
import os
import pytest
from proximo.config import ProximoConfig

def _base_env(monkeypatch, **extra):
    monkeypatch.setenv("PROXIMO_API_BASE_URL", "https://x:8006/api2/json")
    monkeypatch.setenv("PROXIMO_NODE", "pve")
    monkeypatch.setenv("PROXIMO_TOKEN_PATH", "/run/x")
    for k, v in extra.items():
        monkeypatch.setenv(k, v)

def test_expected_head_defaults_none(monkeypatch):
    _base_env(monkeypatch)
    assert ProximoConfig.from_env().expected_head is None

def test_expected_head_accepts_64_hex(monkeypatch):
    h = "a" * 64
    _base_env(monkeypatch, PROXIMO_AUDIT_EXPECTED_HEAD=h)
    assert ProximoConfig.from_env().expected_head == h

def test_expected_head_rejects_malformed(monkeypatch):
    _base_env(monkeypatch, PROXIMO_AUDIT_EXPECTED_HEAD="not-a-hash")
    with pytest.raises(RuntimeError, match="PROXIMO_AUDIT_EXPECTED_HEAD"):
        ProximoConfig.from_env()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/test_config.py -k expected_head -q`
Expected: FAIL (`AttributeError: ... 'expected_head'` / no `RuntimeError` raised).

- [ ] **Step 3: Implement**

In `src/proximo/config.py`, add the dataclass field (after `redact_ledger`):

```python
    expected_head: str | None = None  # PROXIMO_AUDIT_EXPECTED_HEAD — off-box-pinned head() for tail-attack detection
```

Add a module-level helper near the top (after imports):

```python
import re

_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")
```

In `from_env`, before the `return cls(...)`:

```python
        expected_head = os.environ.get("PROXIMO_AUDIT_EXPECTED_HEAD") or None
        if expected_head is not None and not _HEX64.match(expected_head):
            raise RuntimeError(
                "PROXIMO_AUDIT_EXPECTED_HEAD must be a 64-char lowercase hex head() value "
                "(a sha256/hmac-sha256 hexdigest); got a malformed value"
            )
```

Add `expected_head=expected_head,` to the `return cls(...)` kwargs.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run python -m pytest tests/test_config.py -k expected_head -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/proximo/config.py tests/test_config.py
git commit -m "feat(config): PROXIMO_AUDIT_EXPECTED_HEAD (off-box head pin, 64-hex validated)"
```

---

### Task 2: Config — `audit_keyed` field (keyed default on, opt-out)

**Files:**
- Modify: `src/proximo/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `ProximoConfig.audit_keyed: bool` (default `True`); env `PROXIMO_AUDIT_KEYED` in `("0","false","off","no")` → `False`. `audit_key_path` semantics unchanged (explicit override).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py — append (reuses _base_env from Task 1)
def test_audit_keyed_defaults_true(monkeypatch):
    _base_env(monkeypatch)
    assert ProximoConfig.from_env().audit_keyed is True

def test_audit_keyed_opt_out_off(monkeypatch):
    _base_env(monkeypatch, PROXIMO_AUDIT_KEYED="off")
    assert ProximoConfig.from_env().audit_keyed is False

def test_audit_keyed_opt_out_zero(monkeypatch):
    _base_env(monkeypatch, PROXIMO_AUDIT_KEYED="0")
    assert ProximoConfig.from_env().audit_keyed is False

def test_audit_keyed_on_stays_true(monkeypatch):
    _base_env(monkeypatch, PROXIMO_AUDIT_KEYED="on")
    assert ProximoConfig.from_env().audit_keyed is True
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/test_config.py -k audit_keyed -q`
Expected: FAIL (`AttributeError: ... 'audit_keyed'`).

- [ ] **Step 3: Implement**

Add the field (after `audit_key_path`):

```python
    audit_keyed: bool = True  # PROXIMO_AUDIT_KEYED — keyed (HMAC) PROVE by default; "off"/"0"/"false"/"no" disables
```

In `from_env`, parse it (near the other bool parses):

```python
        audit_keyed = os.environ.get("PROXIMO_AUDIT_KEYED", "true").lower() not in ("0", "false", "off", "no")
```

Add `audit_keyed=audit_keyed,` to `return cls(...)`.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run python -m pytest tests/test_config.py -k audit_keyed -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/proximo/config.py tests/test_config.py
git commit -m "feat(config): PROXIMO_AUDIT_KEYED — keyed PROVE default-on with opt-out"
```

---

### Task 3: `audit.py` — `detect_mode` log inspector

**Files:**
- Modify: `src/proximo/audit.py`
- Test: `tests/test_ledger.py`

**Interfaces:**
- Produces: `detect_mode(path: str) -> str` returning `"empty"` (absent / no parseable entries), `"keyed"` (last parseable entry `alg == "hmac-sha256"`), or `"unkeyed"` (last parseable entry has no `alg`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ledger.py — append (reuses _ledger, _keyed, _KEY)
from proximo.audit import detect_mode

def test_detect_mode_empty_for_absent(tmp_path):
    assert detect_mode(str(tmp_path / "nope.log")) == "empty"

def test_detect_mode_unkeyed(tmp_path):
    _ledger(tmp_path).record("a", target="t1")
    assert detect_mode(str(tmp_path / "audit.log")) == "unkeyed"

def test_detect_mode_keyed(tmp_path):
    _keyed(tmp_path).record("a", target="t1")
    assert detect_mode(str(tmp_path / "audit.log")) == "keyed"

def test_detect_mode_empty_for_blank_file(tmp_path):
    p = tmp_path / "audit.log"
    p.write_text("\n\n")
    assert detect_mode(str(p)) == "empty"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/test_ledger.py -k detect_mode -q`
Expected: FAIL (`ImportError: cannot import name 'detect_mode'`).

- [ ] **Step 3: Implement**

In `src/proximo/audit.py`, add after `load_or_create_key`:

```python
def detect_mode(path: str) -> str:
    """Inspect an on-disk ledger's chaining mode without trusting it for verification.

    Returns "empty" (absent / no parseable entries), "keyed" (last entry is HMAC-keyed),
    or "unkeyed". Used ONLY to decide migration (seal-and-rotate); verify() still treats
    the ledger's key as authoritative, never the entry's `alg`.
    """
    if not os.path.exists(path):
        return "empty"
    last: dict[str, Any] | None = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                last = obj
    if last is None:
        return "empty"
    return "keyed" if last.get("alg") == _KEY_ALG else "unkeyed"
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run python -m pytest tests/test_ledger.py -k detect_mode -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/proximo/audit.py tests/test_ledger.py
git commit -m "feat(audit): detect_mode — classify an on-disk ledger as empty/keyed/unkeyed"
```

---

### Task 4: `audit.py` — `seal_and_rotate` (terminal entry → archive → keyed genesis)

**Files:**
- Modify: `src/proximo/audit.py`
- Test: `tests/test_ledger.py`

**Interfaces:**
- Consumes: `AuditLedger`, `detect_mode`, `GENESIS_HASH`, `_KEY_ALG`.
- Produces: `seal_and_rotate(log_path: str, key: bytes) -> tuple[str, str]` returning `(archive_path, sealed_head)`. Writes a terminal unkeyed `audit_rotate` entry to the old log, renames it to `<log>.unkeyed-<UTCstamp>-<head8>`, then starts a new keyed log whose first entry records `prev_log`/`prev_head`. Idempotent under a sidecar `<log>.lock`; a no-op (returns `("", current_head)`) if the log is not unkeyed when the lock is held.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ledger.py — append
import re as _re
from proximo.audit import seal_and_rotate

def test_seal_and_rotate_archives_and_starts_keyed(tmp_path):
    log = str(tmp_path / "audit.log")
    old = AuditLedger(log)
    old.record("a", target="t1")
    old.record("b", target="t2")
    pre_head = old.head()

    archive, sealed_head = seal_and_rotate(log, _KEY)

    # archive named with the sealed head's first 8 chars; old chain still verifies UNKEYED
    assert _re.search(r"audit\.log\.unkeyed-\d{8}T\d{6}Z-[0-9a-f]{8}$", archive)
    assert sealed_head[:8] in archive
    assert AuditLedger(archive).verify().ok            # old log intact as an unkeyed chain
    arch_lines = (tmp_path / archive.split("/")[-1]).read_text().splitlines()
    assert json.loads(arch_lines[-1])["action"] == "audit_rotate"   # terminal sealed marker
    assert json.loads(arch_lines[-1])["detail"]["sealed"] is True

    # new keyed log exists, verifies WITH the key, and records the custody seam
    new = AuditLedger(log, key=_KEY)
    assert new.verify().ok and new.keyed
    genesis = json.loads((tmp_path / "audit.log").read_text().splitlines()[0])
    assert genesis["action"] == "audit_rotate"
    assert genesis["detail"]["prev_head"] == sealed_head
    assert genesis["detail"]["prev_log"].startswith("audit.log.unkeyed-")
    assert genesis["alg"] == _KEY_ALG
    assert pre_head != sealed_head   # the terminal entry advanced the old head

def test_seal_and_rotate_is_idempotent_on_keyed(tmp_path):
    log = str(tmp_path / "audit.log")
    AuditLedger(log, key=_KEY).record("a", target="t1")   # already keyed
    archive, _ = seal_and_rotate(log, _KEY)
    assert archive == ""                                   # no-op: nothing to seal
    assert AuditLedger(log, key=_KEY).verify().ok
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/test_ledger.py -k seal_and_rotate -q`
Expected: FAIL (`ImportError: cannot import name 'seal_and_rotate'`).

- [ ] **Step 3: Implement**

In `src/proximo/audit.py`, add (after `detect_mode`); note `fcntl`, `os`, `datetime`/`UTC` are already imported:

```python
def seal_and_rotate(log_path: str, key: bytes) -> tuple[str, str]:
    """Seal an existing UNKEYED ledger and start a fresh keyed one in its place.

    Under a sidecar `<log_path>.lock` (the log itself gets renamed, so we can't lock it):
    append a terminal `audit_rotate` entry to the old log, archive it untouched-as-a-chain
    to `<log>.unkeyed-<UTCstamp>-<head8>`, then start the new keyed log whose genesis records
    `prev_log`/`prev_head` — an auditable custody seam. No-op (returns ("", head)) if the log
    is not unkeyed once the lock is held (a racing process already rotated). NEVER deletes the
    old log.
    """
    lock_path = log_path + ".lock"
    with open(lock_path, "a+", encoding="utf-8",
              opener=lambda p, flags: os.open(p, flags, 0o600)) as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            if detect_mode(log_path) != "unkeyed":
                return "", AuditLedger(log_path, key=key).head()
            old = AuditLedger(log_path)  # unkeyed
            old.record("audit_rotate", target="ledger",
                       detail={"reason": "keyed-default upgrade", "sealed": True})
            sealed_head = old.head()
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            archive_path = f"{log_path}.unkeyed-{stamp}-{sealed_head[:8]}"
            os.rename(log_path, archive_path)
            new = AuditLedger(log_path, key=key)
            new.record("audit_rotate", target="ledger",
                       detail={"prev_log": os.path.basename(archive_path),
                               "prev_head": sealed_head, "prev_alg": "sha256"})
            return archive_path, sealed_head
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run python -m pytest tests/test_ledger.py -k seal_and_rotate -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/proximo/audit.py tests/test_ledger.py
git commit -m "feat(audit): seal_and_rotate — non-destructive unkeyed->keyed migration with custody seam"
```

---

### Task 5: `audit.py` — `open_ledger(cfg)` factory

**Files:**
- Modify: `src/proximo/audit.py`
- Test: `tests/test_ledger.py`

**Interfaces:**
- Consumes: `ProximoConfig` (`audit_log_path`, `audit_key_path`, `audit_keyed`), `load_or_create_key`, `detect_mode`, `seal_and_rotate`.
- Produces: `open_ledger(cfg) -> AuditLedger`. Keyed-off → unkeyed ledger. Keyed-on → key at explicit `audit_key_path` else derived `<logdir>/audit.key`; existing unkeyed log → seal-and-rotate first; key-gen failure → `RuntimeError` naming the `=off` remedy.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ledger.py — append
from types import SimpleNamespace
from proximo.audit import open_ledger

def _cfg(tmp_path, **kw):
    base = dict(audit_log_path=str(tmp_path / "audit.log"), audit_key_path=None, audit_keyed=True)
    base.update(kw)
    return SimpleNamespace(**base)

def test_open_ledger_keyed_default_for_new_log(tmp_path):
    led = open_ledger(_cfg(tmp_path))
    assert led.keyed
    led.record("a", target="t1")
    assert (tmp_path / "audit.key").exists()          # default key path beside the log
    assert led.verify().ok

def test_open_ledger_opt_out_is_unkeyed(tmp_path):
    led = open_ledger(_cfg(tmp_path, audit_keyed=False))
    assert not led.keyed

def test_open_ledger_explicit_key_path_wins(tmp_path):
    kp = str(tmp_path / "custom.key")
    led = open_ledger(_cfg(tmp_path, audit_key_path=kp, audit_keyed=False))  # explicit wins even if keyed flag off
    led.record("a", target="t1")
    assert led.keyed and (tmp_path / "custom.key").exists()

def test_open_ledger_rotates_existing_unkeyed_log(tmp_path):
    log = str(tmp_path / "audit.log")
    AuditLedger(log).record("legacy", target="t1")    # pre-existing unkeyed ledger
    led = open_ledger(_cfg(tmp_path))
    assert led.keyed and led.verify().ok
    archives = list(tmp_path.glob("audit.log.unkeyed-*"))
    assert len(archives) == 1                          # old log archived, not lost
    assert AuditLedger(str(archives[0])).verify().ok   # ...and still verifiable unkeyed

def test_open_ledger_keeps_existing_keyed_log(tmp_path):
    kp = str(tmp_path / "audit.key")
    key = load_or_create_key(kp)
    AuditLedger(str(tmp_path / "audit.log"), key=key).record("a", target="t1")
    led = open_ledger(_cfg(tmp_path))
    assert led.keyed and led.verify().ok
    assert not list(tmp_path.glob("audit.log.unkeyed-*"))   # no rotation of an already-keyed log

def test_open_ledger_fail_closed_on_keygen_error(tmp_path, monkeypatch):
    import proximo.audit as audit_mod
    def _boom(_p):
        raise OSError("read-only fs")
    monkeypatch.setattr(audit_mod, "load_or_create_key", _boom)
    with pytest.raises(RuntimeError, match="PROXIMO_AUDIT_KEYED=off"):
        open_ledger(_cfg(tmp_path))
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/test_ledger.py -k open_ledger -q`
Expected: FAIL (`ImportError: cannot import name 'open_ledger'`).

- [ ] **Step 3: Implement**

In `src/proximo/audit.py`, add at the end of the module:

```python
def open_ledger(cfg: Any) -> AuditLedger:
    """Build the AuditLedger for `cfg`, applying the keyed-default + seal-and-rotate policy.

    - keyed off (PROXIMO_AUDIT_KEYED=off) and no explicit key path -> unkeyed ledger.
    - else keyed: key at cfg.audit_key_path if set, else <logdir>/audit.key. An existing
      UNKEYED log is sealed-and-rotated first. Key-gen failure fails loud (no silent downgrade).
    """
    log = cfg.audit_log_path
    if cfg.audit_key_path:
        key_path = cfg.audit_key_path
    elif cfg.audit_keyed:
        key_path = os.path.join(os.path.dirname(log) or ".", "audit.key")
    else:
        return AuditLedger(log)  # unkeyed (opt-out)
    try:
        key = load_or_create_key(key_path)
    except (OSError, ValueError) as e:
        raise RuntimeError(
            f"cannot create audit key at {key_path}: {e}; "
            "set PROXIMO_AUDIT_KEYED=off to run an unkeyed ledger"
        ) from e
    if detect_mode(log) == "unkeyed":
        seal_and_rotate(log, key)
    return AuditLedger(log, key=key)
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run python -m pytest tests/test_ledger.py -k open_ledger -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/proximo/audit.py tests/test_ledger.py
git commit -m "feat(audit): open_ledger factory — keyed default + fail-closed + rotate-on-upgrade"
```

---

### Task 6: `server.py` — `_svc()` uses `open_ledger`

**Files:**
- Modify: `src/proximo/server.py:331-336` (`_svc`) and the import on line 77.
- Test: full suite (existing wiring/e2e tests prove no regression).

**Interfaces:**
- Consumes: `open_ledger` from `audit`.
- Produces: `_svc()` returns a ledger built via `open_ledger(cfg)` instead of the inline `load_or_create_key` + `AuditLedger`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ledger.py — append: prove _svc honors keyed-default via env
def test_svc_builds_keyed_ledger_by_default(tmp_path, monkeypatch):
    import proximo.server as server
    monkeypatch.setenv("PROXIMO_API_BASE_URL", "https://x:8006/api2/json")
    monkeypatch.setenv("PROXIMO_NODE", "pve")
    monkeypatch.setenv("PROXIMO_TOKEN_PATH", "/run/x")
    monkeypatch.setenv("PROXIMO_AUDIT_LOG", str(tmp_path / "audit.log"))
    server._svc.cache_clear()
    try:
        _, _, _, audit = server._svc()
        assert audit.keyed   # keyed by default through the real factory path
    finally:
        server._svc.cache_clear()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m pytest tests/test_ledger.py -k svc_builds_keyed -q`
Expected: FAIL (`assert audit.keyed` is False — `_svc` still builds unkeyed by default).

- [ ] **Step 3: Implement**

`src/proximo/server.py` line 77 — change the import:

```python
from .audit import AuditLedger, open_ledger
```

Replace `_svc` body (lines 334-336):

```python
    cfg = ProximoConfig.from_env()
    return cfg, ApiBackend(cfg), ExecBackend(cfg), open_ledger(cfg)
```

(`AuditLedger` is still imported for type/use elsewhere; `load_or_create_key` import is dropped if now unused — ruff will flag it. Remove it from the import line if unused.)

- [ ] **Step 4: Run to verify it passes + no regression**

Run: `uv run python -m pytest tests/test_ledger.py -k svc_builds_keyed -q`
Expected: PASS.
Run: `uv run python -m pytest -q`
Expected: full suite green (2,500+ passed, 0 failed). If an e2e test now asserts unkeyed-specific output, fix it to reflect keyed-default (the behavior change is intended) — do NOT weaken a tamper-evidence assertion.

- [ ] **Step 5: Commit**

```bash
git add src/proximo/server.py tests/test_ledger.py
git commit -m "feat(server): _svc builds the ledger via open_ledger (keyed PROVE default-on)"
```

---

### Task 7: `server.py` — `audit_verify(expected_head=None)` tool

**Files:**
- Modify: `src/proximo/server.py:732-744` (`audit_verify`)
- Test: `tests/test_ledger.py` (tool-level; patches `server._svc` like the wiring tests)

**Interfaces:**
- Consumes: `cfg.expected_head` (Task 1), `audit.verify(expected_head=...)`, `audit.head()`.
- Produces: `audit_verify(expected_head: str | None = None) -> dict` with keys `ok, entries, broken_at_line, reason, head, expected_head, keyed`. Explicit param wins over `cfg.expected_head`; response `expected_head` is the value actually checked (or `None`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ledger.py — append
def _wire_audit(tmp_path, monkeypatch, *, cfg_head=None, key=None):
    import proximo.server as server
    led = AuditLedger(str(tmp_path / "audit.log"), key=key)
    cfg = SimpleNamespace(expected_head=cfg_head)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, None, None, led))
    return server, led

def test_audit_verify_pins_param_match(tmp_path, monkeypatch):
    server, led = _wire_audit(tmp_path, monkeypatch)
    led.record("a", target="t1")
    out = server.audit_verify(expected_head=led.head())
    assert out["ok"] and out["expected_head"] == led.head() and out["head"] == led.head()

def test_audit_verify_pins_param_mismatch_catches_truncation(tmp_path, monkeypatch):
    server, led = _wire_audit(tmp_path, monkeypatch)
    led.record("a", target="t1")
    led.record("b", target="t2")
    pinned = led.head()
    p = tmp_path / "audit.log"
    p.write_text("\n".join(p.read_text().splitlines()[:-1]) + "\n")  # truncate tail
    out = server.audit_verify(expected_head=pinned)
    assert not out["ok"] and "head mismatch" in out["reason"]
    assert out["expected_head"] == pinned and out["head"] != pinned

def test_audit_verify_falls_back_to_config_default(tmp_path, monkeypatch):
    server, led = _wire_audit(tmp_path, monkeypatch, cfg_head="f" * 64)
    led.record("a", target="t1")
    out = server.audit_verify()                 # no param -> uses cfg.expected_head
    assert not out["ok"] and out["expected_head"] == "f" * 64

def test_audit_verify_unpinned_shows_null(tmp_path, monkeypatch):
    server, led = _wire_audit(tmp_path, monkeypatch)
    led.record("a", target="t1")
    out = server.audit_verify()
    assert out["ok"] and out["expected_head"] is None   # legibly unprotected against tail attacks
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/test_ledger.py -k audit_verify -q`
Expected: FAIL (`TypeError: audit_verify() got an unexpected keyword argument 'expected_head'` / missing `expected_head` key).

- [ ] **Step 3: Implement**

Replace `audit_verify` in `src/proximo/server.py`:

```python
@mcp.tool()
def audit_verify(expected_head: str | None = None) -> dict:
    """Verify the tamper-evident audit ledger's hash chain — PROVE the log is intact.

    Pass `expected_head` (the head() value you pinned off-box) to also catch tail
    truncation, a forged tail-append, or a full file replacement — a forward walk
    alone can't see those. Falls back to PROXIMO_AUDIT_EXPECTED_HEAD when omitted.
    """
    cfg, _, _, audit = _svc()
    pin = expected_head if expected_head is not None else cfg.expected_head
    v = audit.verify(expected_head=pin)
    return {
        "ok": v.ok,
        "entries": v.entries,
        "broken_at_line": v.broken_at,
        "reason": v.reason,
        "head": audit.head(),
        "expected_head": pin,
        "keyed": audit.keyed,
    }
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run python -m pytest tests/test_ledger.py -k audit_verify -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/proximo/server.py tests/test_ledger.py
git commit -m "feat(server): audit_verify(expected_head=) head-pinning + config-default fallback"
```

---

### Task 8: A2A — thread `expected_head` through the `audit_verify` skill

**Files:**
- Modify: `src/proximo/a2a/skills.py:153-158` (the `audit_verify` `A2ASkill`)
- Test: `tests/test_a2a_executor.py`

**Interfaces:**
- Consumes: `validate_and_build` (passes named params as kwargs → `skill.tool(**kwargs)`), the `audit_verify(expected_head=...)` tool from Task 7.
- Produces: the `audit_verify` A2A skill accepts an optional `expected_head` string param, forwarded to the tool; stays `mutating=False`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_a2a_executor.py — append (match the file's existing import/dispatch style)
from proximo.a2a.skills import SKILLS_BY_ID, validate_and_build

def test_audit_verify_skill_accepts_expected_head():
    skill = SKILLS_BY_ID["audit_verify"]
    names = {p.name for p in skill.params}
    assert "expected_head" in names
    kwargs = validate_and_build(skill, {"expected_head": "a" * 64})
    assert kwargs == {"expected_head": "a" * 64}

def test_audit_verify_skill_expected_head_optional():
    skill = SKILLS_BY_ID["audit_verify"]
    assert validate_and_build(skill, {}) == {}     # optional: omittable
```

> Confirmed against `src/proximo/a2a/skills.py`: registry is `SKILLS` (`SKILLS_BY_ID: dict[str, A2ASkill]` is the by-id map), `A2ASkill.id`/`.params` exist, and `A2AParam(name, type, required, description)` is the call shape.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m pytest tests/test_a2a_executor.py -k expected_head -q`
Expected: FAIL (`expected_head` not in params; `validate_and_build` rejects the unknown param).

- [ ] **Step 3: Implement**

In `src/proximo/a2a/skills.py`, change the `audit_verify` registration (line ~156) to declare the param:

```python
    A2ASkill(
        "audit_verify", "Verify audit ledger",
        "PROVE: verify the tamper-evident audit ledger's hash chain is intact. Pass expected_head "
        "(your off-box-pinned head) to also catch tail truncation / forged append / wipe.",
        server.audit_verify,
        (A2AParam("expected_head", "string", False, "off-box-pinned head() hash; detects tail attacks"),),
        mutating=False,
        tags=("trust", "prove", "read"), examples=("Is the audit log intact?",),
    ),
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run python -m pytest tests/test_a2a_executor.py -k expected_head -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/proximo/a2a/skills.py tests/test_a2a_executor.py
git commit -m "feat(a2a): audit_verify skill forwards expected_head head-pin"
```

---

### Task 9: Docs + CHANGELOG + final gate

**Files:**
- Modify: `src/proximo/audit.py` (module docstring), `CLAUDE.md`, `packaging/proximo.env.example`, `README.md` (PROVE scorecard), `CHANGELOG.md`
- Verify: full suite + ruff + pyright + leak-audit.

**Interfaces:** none (docs + verification).

- [ ] **Step 1: Update the `audit.py` module docstring**

In the module docstring (top of `src/proximo/audit.py`), update the keyed-mode paragraph to say keyed is now the **default** (via `open_ledger`/`PROXIMO_AUDIT_KEYED`), and add one sentence: an existing unkeyed log is **sealed-and-rotated** on first keyed start (terminal `audit_rotate` entry → `*.unkeyed-<stamp>-<head8>` archive → new keyed log records `prev_head`); never deleted. Keep the honest "marginal vs off-box anchor" framing intact.

- [ ] **Step 2: Update `packaging/proximo.env.example`**

After the `PROXIMO_AUDIT_LOG=...` line (line 23), add:

```bash
# PROVE ledger: keyed (HMAC) chaining is ON by default. Opt out with PROXIMO_AUDIT_KEYED=off.
# Key auto-generated 0600 at <audit-log-dir>/audit.key (override with PROXIMO_AUDIT_KEY_PATH).
# An existing unkeyed log is sealed + archived (never deleted) and a fresh keyed log started.
#PROXIMO_AUDIT_KEYED=off
#PROXIMO_AUDIT_KEY_PATH=/var/lib/proximo/audit.key
# Pin your ledger head OFF-BOX to detect tail truncation/forged-append/wipe (the strong guarantee).
# Read it from audit_verify's "head" field, store it somewhere the box can't rewrite, set it here:
#PROXIMO_AUDIT_EXPECTED_HEAD=<64-hex head() value>
```

- [ ] **Step 3: Correct the README PROVE scorecard**

In `README.md`, find the PROVE pillar / scorecard claim and make it honest-and-current: PROVE is a hash-chained ledger, **keyed by default**, with **head-pinning** (`audit_verify(expected_head=...)` / `PROXIMO_AUDIT_EXPECTED_HEAD`) to catch tail attacks — while keeping the "tamper-evident, not tamper-proof; off-box anchor is the strong guarantee" line. (Grep: `grep -n "PROVE\|tamper" README.md` to locate.)

- [ ] **Step 4: Update `CLAUDE.md` trust-spine note**

In the "Trust spine" section, update the **PROVE** bullet: keyed-by-default HMAC chaining + head-pinning available; existing unkeyed ledgers auto seal-and-rotate.

- [ ] **Step 5: Add the CHANGELOG entry**

Under the existing `## [Unreleased]` section (confirmed present, above `## [0.6.5]`), add:

```markdown
### Added
- PROVE head-pinning: `audit_verify(expected_head=...)` and `PROXIMO_AUDIT_EXPECTED_HEAD`
  catch tail truncation / forged append / full wipe (the off-box anchor is the strong guarantee).

### Changed
- PROVE ledger is now **keyed (HMAC-SHA256) by default** (`PROXIMO_AUDIT_KEYED`, opt out with `off`).
  An existing unkeyed ledger is sealed and archived (never deleted), and a fresh keyed log is
  started recording the prior head as a custody seam. Key-gen failure fails closed (no silent downgrade).
```

- [ ] **Step 6: Final gate**

Run, expecting all green:

```bash
uv run python -m pytest -q                                   # full suite, 0 failed
uv run ruff check src tests                                  # clean
uv run pyright                                               # 0 errors
uv run python scripts/release_leak_audit.py audit            # leak-audit CLEAN
```

Expected: suite green, ruff clean, pyright 0, leak-audit reports no leak.

- [ ] **Step 7: Commit**

```bash
git add src/proximo/audit.py packaging/proximo.env.example README.md CLAUDE.md CHANGELOG.md
git commit -m "docs(prove): document keyed-default + head-pinning; correct PROVE scorecard; CHANGELOG"
```

---

## Self-Review (completed by author)

**Spec coverage:** Feature A (`expected_head`) → Tasks 1, 7, 8. Feature B (keyed-default + seal-and-rotate) → Tasks 2, 3, 4, 5, 6. Config defaults/validation → 1, 2. Fail-closed → 5. Sidecar-lock rotation → 4. A2A → 8. Docs/honesty/scorecard → 9. Security tests (tail-truncate/forged-append/downgrade) → existing `test_ledger.py` + Tasks 4, 7. No spec section left without a task.

**Placeholder scan:** none — every code/test step carries complete code; the two "locate via grep" notes (README/CHANGELOG anchors) point at real, gREP-findable strings rather than leaving content unspecified.

**Type consistency:** `detect_mode(str)->str`, `seal_and_rotate(str,bytes)->tuple[str,str]`, `open_ledger(cfg)->AuditLedger`, `audit_verify(expected_head: str|None)->dict` used consistently across producer and consumer tasks. `A2AParam(name,type,required,desc)` matches the file's existing call shape.

**Known confirm-before-coding points (called out inline):** Task 6 may surface an e2e test that assumed the unkeyed default — fix forward to keyed (never weaken a tamper assertion). (The A2A registry/field names in Task 8 are now confirmed against `skills.py`.)
