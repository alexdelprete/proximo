"""Confirm=True sweep — PBS notifications wrapper welds (src/proximo/tools/pbs_notifications.py,
Wave 3a) + the secret-never-in-ledger promise for the WIDER {token,password,secret,header} set.

Mirrors the `_wire()`/`_Pbs` idiom in tests/test_confirm_sweep_pbs_disks.py (itself mirroring
tests/test_server_plan.py:110-131): `_svc` is monkeypatched (the ONE shared audit ledger lives
behind it — `_ledger()` reads `_svc()[3]`) and `_pbs` is monkeypatched to a fake PbsBackend. This
file duplicates its own `_Pbs`/`_wire` rather than importing another confirm-sweep module's — same
self-contained convention every confirm-sweep module in this repo follows.

Each homogeneous confirm=True call proves the three welds:
  1. return shape — status is "ok" (never "plan") — every mutation on this plane is SYNCHRONOUS
     per the live schema (module docstring fact #8), unlike a PVE guest/storage mutation;
  2. the fake PbsBackend captured the underlying call (verb + path + EXACT payload, full dict
     equality — no subset matching);
  3. the ledger recorded a confirmed mutation — structural asserts only, never exact prose.

THE HEADLINE WELD (mirrors tests/test_confirm_sweep_pve_access.py's
test_token_create_confirm_returns_secret_but_never_writes_it_to_ledger): gotify `token`, smtp
`password`, webhook `secret`, and webhook `header` values must never appear raw in the on-disk
ledger — read RAW BYTES, not parsed JSON — while the real PBS call (the fake's captured payload)
DOES carry the raw value, because the mutation must actually work.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig


class _Pbs:
    """Path-aware fake PbsBackend: records every _get/_post/_put/_delete call."""

    def __init__(self, get_return=None):
        self._get_return = get_return
        self.gets: list[tuple[str, dict | None]] = []
        self.posts: list[tuple[str, dict | None]] = []
        self.puts: list[tuple[str, dict | None]] = []
        self.deletes: list[tuple[str, dict | None]] = []

    def _get(self, path, params=None):
        self.gets.append((path, params))
        return self._get_return

    def _post(self, path, data=None):
        self.posts.append((path, data))
        return None

    def _put(self, path, data=None):
        self.puts.append((path, data))
        return None

    def _delete(self, path, params=None):
        self.deletes.append((path, params))
        return None


class _Api:
    """Minimal PVE API stub — only needed so server._svc() resolves (the ONE shared ledger lives
    behind it); pbs_notifications.py's tools never touch this backend."""

    def __init__(self):
        self.config = SimpleNamespace(node="pve")


def _wire(tmp_path, monkeypatch, get_return=None):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log,
    )
    api = _Api()
    pbs = _Pbs(get_return=get_return)
    exec_ = SimpleNamespace()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, exec_, ledger))
    monkeypatch.setattr(server, "_pbs", lambda: (SimpleNamespace(), pbs))
    return cfg, pbs, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _confirmed_entry(log: str, action: str, outcome: str) -> dict:
    entries = [e for e in _entries(log) if e["action"] == action and e["outcome"] == outcome]
    assert len(entries) == 1, f"expected exactly one {action!r}/{outcome!r} ledger entry, got {entries}"
    return entries[0]


# ---------------------------------------------------------------------------
# Homogeneous sweep — table-driven: "confirm=True reaches the right verb/path/data on the
# PbsBackend and records a confirmed mutation". Every mutation on this plane returns null
# (synchronous) per the live schema — outcome is ALWAYS "ok", never "submitted".
# ---------------------------------------------------------------------------

_SWEEP_CASES = [
    pytest.param(
        "pbs_notification_endpoint_create",
        dict(ep_type="smtp", name="mail1", comment="c1", options={"server": "smtp.example.com"}),
        "ok", "posts", "/config/notifications/endpoints/smtp",
        {"name": "mail1", "comment": "c1", "server": "smtp.example.com"},
        id="endpoint_create",
    ),
    pytest.param(
        "pbs_notification_endpoint_update",
        dict(ep_type="smtp", name="mail1", comment="c2", digest="d" * 64, options={"port": 587}),
        "ok", "puts", "/config/notifications/endpoints/smtp/mail1",
        {"comment": "c2", "digest": "d" * 64, "port": 587},
        id="endpoint_update",
    ),
    pytest.param(
        "pbs_notification_endpoint_delete",
        dict(ep_type="smtp", name="mail1"),
        "ok", "deletes", "/config/notifications/endpoints/smtp/mail1",
        None,
        id="endpoint_delete",
    ),
    pytest.param(
        "pbs_notification_matcher_set",
        dict(name="m1", comment="route all", mode="any", target=["ep1"]),
        "ok", "posts", "/config/notifications/matchers",
        {"name": "m1", "comment": "route all", "mode": "any", "target": ["ep1"]},
        id="matcher_set_create",
    ),
    pytest.param(
        "pbs_notification_matcher_delete",
        dict(name="m1"),
        "ok", "deletes", "/config/notifications/matchers/m1",
        None,
        id="matcher_delete",
    ),
    pytest.param(
        "pbs_notification_target_test",
        dict(name="smtp1"),
        "ok", "posts", "/config/notifications/targets/smtp1/test",
        None,
        id="target_test",
    ),
]


@pytest.mark.parametrize(
    "tool_name,kwargs,expected_status,capture,path,data_exact", _SWEEP_CASES,
)
def test_confirm_true_executes_forwards_and_records(
    tmp_path, monkeypatch, tool_name, kwargs, expected_status, capture, path, data_exact,
):
    """confirm=True executes (never 'plan'), the fake captured the forwarded call, and the ledger
    recorded a confirmed mutation — the three welds every confirm-sweep module proves."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)

    out = fn(confirm=True, **kwargs)

    # weld 1: return shape — always "ok" on this plane (every mutation returns null, synchronous)
    assert out["status"] == expected_status
    assert out["status"] != "plan"
    assert out["status"] != "submitted"

    # weld 2: the fake captured the underlying call at the expected verb + path, with the EXACT
    # forwarded payload (full dict equality — an accidental extra field now fails).
    calls = getattr(pbs, capture)
    assert calls, f"{tool_name} confirm=True never reached pbs.{capture}"
    call_path, call_data = calls[-1]
    assert call_path == path
    assert call_data == data_exact

    # weld 3: ledger structural asserts — never exact prose
    entry = _confirmed_entry(log, tool_name, expected_status)
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


def test_matcher_set_update_branch_puts_with_digest_and_delete(tmp_path, monkeypatch):
    """The upsert's OTHER branch: an existing matcher (fake _get returns a matching name) takes
    the PUT path, forwarding digest/delete — properties the create (POST) branch never accepts
    (module docstring: notification_matcher_set's own docstring)."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch, get_return=[{"name": "m1"}])

    out = server.pbs_notification_matcher_set(
        name="m1", comment="updated", digest="e" * 64, delete=["target"], confirm=True,
    )

    assert out["status"] == "ok"
    assert pbs.puts and not pbs.posts
    call_path, call_data = pbs.puts[-1]
    assert call_path == "/config/notifications/matchers/m1"
    assert call_data == {"comment": "updated", "digest": "e" * 64, "delete": ["target"]}

    entry = _confirmed_entry(log, "pbs_notification_matcher_set", "ok")
    assert entry["mutation"] is True


# ---------------------------------------------------------------------------
# Reads — confirm the wrapper reaches the PbsBackend with the right path/params (no confirm= gate).
# ---------------------------------------------------------------------------

def test_targets_list_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_notification_targets_list()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/config/notifications/targets"
    assert call_params is None


def test_endpoint_list_no_filter_aggregates_all_four_types(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_notification_endpoint_list()
    paths = [p for p, _ in pbs.gets]
    assert paths == [
        "/config/notifications/endpoints/gotify",
        "/config/notifications/endpoints/sendmail",
        "/config/notifications/endpoints/smtp",
        "/config/notifications/endpoints/webhook",
    ]


def test_endpoint_list_with_filter_calls_only_that_type(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_notification_endpoint_list(ep_type="webhook")
    call_path, _ = pbs.gets[-1]
    assert call_path == "/config/notifications/endpoints/webhook"


def test_endpoint_get_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "mail1"})
    server.pbs_notification_endpoint_get(ep_type="smtp", name="mail1")
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/config/notifications/endpoints/smtp/mail1"
    assert call_params is None


def test_matchers_list_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_notification_matchers_list()
    call_path, _ = pbs.gets[-1]
    assert call_path == "/config/notifications/matchers"


def test_matcher_get_read_reaches_pbs(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return={"name": "m1"})
    server.pbs_notification_matcher_get(name="m1")
    call_path, _ = pbs.gets[-1]
    assert call_path == "/config/notifications/matchers/m1"


def test_matcher_fields_read_reaches_pbs_no_params(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_notification_matcher_fields()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/config/notifications/matcher-fields"
    assert call_params is None


def test_matcher_field_values_read_reaches_pbs_no_params(tmp_path, monkeypatch):
    _, pbs, _, _ = _wire(tmp_path, monkeypatch, get_return=[])
    server.pbs_notification_matcher_field_values()
    call_path, call_params = pbs.gets[-1]
    assert call_path == "/config/notifications/matcher-field-values"
    assert call_params is None


# ---------------------------------------------------------------------------
# THE HEADLINE WELD — secret-never-in-ledger, across the WIDER {token, password, secret, header}
# set (module docstring fact #3): gotify token, smtp password, webhook secret, webhook header.
# Sentinel values are low-entropy/all-lowercase/hyphenated per this repo's fixture-sentinel
# discipline (CLAUDE.md: "Test fixtures must use low-entropy sentinel values" — a mixed-case
# sentinel already failed the public gitleaks CI scan on v0.13.0).
# ---------------------------------------------------------------------------

_TOKEN_SENTINEL = "sentinel-gotify-token-value"
_PASSWORD_SENTINEL = "sentinel-smtp-password-value"  # noqa: S105 (test sentinel, not a real credential)
_SECRET_SENTINEL = "sentinel-webhook-secret-value"
_HEADER_SENTINEL = "sentinel-webhook-header-value"

_SECRET_CASES = [
    pytest.param(
        "gotify", {"server": "https://gotify.example.com", "token": _TOKEN_SENTINEL},
        _TOKEN_SENTINEL, id="gotify_token",
    ),
    pytest.param(
        "smtp", {"server": "smtp.example.com", "password": _PASSWORD_SENTINEL},
        _PASSWORD_SENTINEL, id="smtp_password",
    ),
    pytest.param(
        "webhook",
        {"url": "https://example.com/hook", "secret": [{"name": "auth", "value": _SECRET_SENTINEL}]},
        _SECRET_SENTINEL, id="webhook_secret",
    ),
    pytest.param(
        "webhook",
        {"url": "https://example.com/hook",
         "header": [{"name": "Authorization", "value": _HEADER_SENTINEL}]},
        _HEADER_SENTINEL, id="webhook_header",
    ),
]


@pytest.mark.parametrize("ep_type,options,sentinel", _SECRET_CASES)
def test_endpoint_create_confirm_never_writes_secret_to_ledger(
    tmp_path, monkeypatch, ep_type, options, sentinel,
):
    """weld 1: the operator's real PBS call DOES carry the raw secret (the mutation must actually
    work) — the fake captured it. weld 2: read the ledger file RAW (bytes, not parsed JSON) and
    assert the secret substring appears NOWHERE — not in the 'planned' entry, not in the
    'confirmed' entry, not anywhere in the file."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch)

    out = server.pbs_notification_endpoint_create(
        ep_type=ep_type, name="ep1", options=options, confirm=True,
    )

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    # weld 1: the fake captured the underlying POST with the RAW secret — a real PBS call must
    # actually carry it.
    assert pbs.posts, f"{ep_type} endpoint_create confirm=True never reached pbs._post"
    call_path, call_data = pbs.posts[-1]
    assert call_path == f"/config/notifications/endpoints/{ep_type}"
    assert sentinel in json.dumps(call_data)

    # weld 2: ledger entries (parsed JSON) never carry the sentinel, in EITHER the planned or the
    # confirmed entry.
    entries = _entries(log)
    assert entries, "no ledger entries recorded at all"
    assert all(sentinel not in json.dumps(e) for e in entries)

    # THE HEADLINE WELD: read the ledger file RAW (bytes) — the secret must appear NOWHERE in the
    # on-disk ledger, across every entry, not just the ones inspected above as parsed JSON.
    raw = open(log, "rb").read()
    assert sentinel.encode("utf-8") not in raw


@pytest.mark.parametrize("ep_type,options,sentinel", _SECRET_CASES)
def test_endpoint_update_confirm_never_writes_secret_to_ledger(
    tmp_path, monkeypatch, ep_type, options, sentinel,
):
    """Same headline weld as create, for the update path — including the CAPTURE read (plan.
    current), which module docstring fact #4 specifically fixes over the PVE precedent."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch, get_return={"name": "ep1"})

    out = server.pbs_notification_endpoint_update(
        ep_type=ep_type, name="ep1", options=options, confirm=True,
    )

    assert out["status"] == "ok"

    assert pbs.puts, f"{ep_type} endpoint_update confirm=True never reached pbs._put"
    call_path, call_data = pbs.puts[-1]
    assert call_path == f"/config/notifications/endpoints/{ep_type}/ep1"
    assert sentinel in json.dumps(call_data)

    entries = _entries(log)
    assert entries
    assert all(sentinel not in json.dumps(e) for e in entries)

    raw = open(log, "rb").read()
    assert sentinel.encode("utf-8") not in raw


_CAPTURE_SECRET_CASES = [
    pytest.param(
        "gotify", {"name": "ep1", "server": "https://gotify.example.com", "token": _TOKEN_SENTINEL},
        _TOKEN_SENTINEL, id="gotify_token_capture",
    ),
    pytest.param(
        "smtp", {"name": "ep1", "server": "smtp.example.com", "password": _PASSWORD_SENTINEL},
        _PASSWORD_SENTINEL, id="smtp_password_capture",
    ),
    pytest.param(
        "webhook",
        {"name": "ep1", "url": "https://example.com/hook",
         "header": [{"name": "Authorization", "value": _HEADER_SENTINEL}]},
        _HEADER_SENTINEL, id="webhook_header_capture",
    ),
]


@pytest.mark.parametrize("ep_type,current,sentinel", _CAPTURE_SECRET_CASES)
def test_endpoint_delete_confirm_never_writes_captured_secret_to_ledger(
    tmp_path, monkeypatch, ep_type, current, sentinel,
):
    """Same headline weld for the DELETE path (review finding, Wave 3a): delete's plan factory
    performs the same live-read-then-redact CAPTURE as update — the module's own headline
    improvement over the PVE precedent — so it gets the same raw-ledger-bytes proof. The fake
    GET returns secret-BEARING config (the shape PBS actually returns for webhook header),
    exercising the redaction of Plan.current, not just Plan.change."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch, get_return=current)

    out = server.pbs_notification_endpoint_delete(ep_type=ep_type, name="ep1", confirm=True)

    assert out["status"] == "ok"
    assert pbs.deletes, f"{ep_type} endpoint_delete confirm=True never reached pbs._delete"
    call_path, _ = pbs.deletes[-1]
    assert call_path == f"/config/notifications/endpoints/{ep_type}/ep1"

    entries = _entries(log)
    assert entries, "no ledger entries recorded at all"
    assert all(sentinel not in json.dumps(e) for e in entries)

    raw = open(log, "rb").read()
    assert sentinel.encode("utf-8") not in raw


def test_endpoint_delete_dry_run_plan_never_carries_captured_secret(tmp_path, monkeypatch):
    """The dry-run PLAN dict for delete is returned directly to the calling agent and embeds the
    CAPTURE read — it must never carry the raw header value the GET returned."""
    _, _, _, _ = _wire(
        tmp_path, monkeypatch,
        get_return={"name": "ep1", "url": "https://example.com/hook",
                    "header": [{"name": "Authorization", "value": _HEADER_SENTINEL}]},
    )

    out = server.pbs_notification_endpoint_delete(ep_type="webhook", name="ep1", confirm=False)

    assert out["status"] == "plan"
    assert _HEADER_SENTINEL not in json.dumps(out)


def test_endpoint_create_dry_run_plan_never_carries_secret(tmp_path, monkeypatch):
    """Even confirm=False (the returned PLAN dict itself, not just the ledger) must never carry
    a raw secret — the plan is returned directly to the calling agent."""
    _, _, _, _ = _wire(tmp_path, monkeypatch)

    out = server.pbs_notification_endpoint_create(
        ep_type="gotify", name="ep1",
        options={"server": "https://gotify.example.com", "token": _TOKEN_SENTINEL},
        confirm=False,
    )

    assert out["status"] == "plan"
    assert _TOKEN_SENTINEL not in json.dumps(out)
