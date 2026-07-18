"""Confirm=True sweep — PMG LDAP profiles + fetchmail wrapper welds (src/proximo/pmg.py +
src/proximo/tools/pmg_mail.py, Wave 9c, full-surface campaign) + THE SECRET CONTRACT proof for
`bindpw` (LDAP) and `pass` (fetchmail).

Mirrors the `_wire()`/`_Pmg` idiom already established in `tests/test_confirm_sweep_pmg_node.py`
(itself mirroring `tests/test_confirm_sweep_pbs_node.py`'s own `_Pbs` template): `_svc` is
monkeypatched (the ONE shared audit ledger lives behind it — `_ledger()` reads `_svc()[3]`) and
`_pmg` is monkeypatched to a fake PmgBackend. This file duplicates its own `_Pmg`/`_wire` rather
than importing another confirm-sweep module's — same self-contained convention every confirm-sweep
module in this repo follows. New file (no prior confirm-sweep coverage existed for pmg_mail.py's
own tools) per the Wave 9c dispatch brief.

Each homogeneous confirm=True call proves the three welds every confirm-sweep module proves:
  1. return shape — status is "ok" (never "plan") — every mutation in this chunk's live schema
     returns `null` (synchronous);
  2. the fake PmgBackend captured the underlying call (verb + path + EXACT payload, full dict
     equality — no subset matching);
  3. the ledger recorded a confirmed mutation — structural asserts only, never exact prose.

THE HEADLINE WELD (the wave's biggest risk axis): `bindpw` (LDAP) and `pass` (fetchmail) must
NEVER appear raw in the on-disk ledger — read RAW BYTES, not parsed JSON — on EITHER the dry-run
plan path or the confirm path, while the real PMG call (the fake's captured payload) DOES carry
the raw value, because the mutation must actually work. Fetchmail's `pass` is additionally proven
MANDATORILY stripped at the READ layer (list AND single-item — both CONFIRMED echoing on the live
schema); LDAP's `bindpw` is proven DEFENSIVELY stripped at the read layer (schema-thin, silence is
not evidence of absence) using the SAME mechanism. Sentinel values are low-entropy (all-lowercase,
hyphenated) per this repo's fixture-sentinel discipline (CLAUDE.md: a mixed-case sentinel already
failed the public gitleaks CI scan on v0.13.0).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.backends import ProximoError
from proximo.config import ProximoConfig

_BINDPW_SENTINEL = "sentinel-ldap-bindpw-value"  # noqa: S105 (test sentinel, not a real credential)
_PASS_SENTINEL = "sentinel-fetchmail-pass-value"  # noqa: S105 (test sentinel, not a real credential)


class _Pmg:
    """Path-aware fake PmgBackend: records every _get/_post/_put/_delete call.

    `_get` returns a fixed, secret-FREE LDAP profile config dict for
    `/config/ldap/{profile}/config` (the CAPTURE read `plan_ldap_profile_delete`/
    `plan_ldap_profile_config_update` use) and a fixed, secret-FREE fetchmail entry dict for
    `/config/fetchmail/{id}` (the CAPTURE read `plan_fetchmail_update`/`plan_fetchmail_delete`
    use) — every other path gets `[]` (list reads default to empty). `_post`/`_put`/`_delete`
    all return `None` (every mutation on this chunk's live schema returns `null`), except
    `POST /config/fetchmail` (fetchmail_create), which returns the schema's own
    "Unique ID" string shape.
    """

    _FETCHMAIL_NEW_ID = "sentinelid1"

    def __init__(self, ldap_config_get_return=None, fetchmail_get_return=None):
        self._ldap_config_get_return = ldap_config_get_return or {
            "profile": "my-ad", "server1": "ldap.example.com", "mode": "ldap",
        }
        self._fetchmail_get_return = fetchmail_get_return or {
            "id": "abc123", "server": "mail.example.com", "user": "alice",
            "target": "user@example.com", "protocol": "pop3",
        }
        self.gets: list[tuple[str, dict | None]] = []
        self.posts: list[tuple[str, dict | None]] = []
        self.puts: list[tuple[str, dict | None]] = []
        self.deletes: list[tuple[str, dict | None]] = []

    def _get(self, path, params=None):
        self.gets.append((path, params))
        if path == "/config/ldap/my-ad/config":
            return self._ldap_config_get_return
        if path == "/config/fetchmail/abc123":
            return self._fetchmail_get_return
        return []

    def _post(self, path, data=None):
        self.posts.append((path, data))
        if path == "/config/fetchmail":
            return self._FETCHMAIL_NEW_ID
        return None

    def _put(self, path, data=None):
        self.puts.append((path, data))
        return None

    def _delete(self, path, params=None):
        self.deletes.append((path, params))
        return None


class _Api:
    """Minimal PVE API stub — only needed so server._svc() resolves (the ONE shared ledger lives
    behind it); pmg.py's/tools/pmg_mail.py's tools never touch this backend."""

    def __init__(self):
        self.config = SimpleNamespace(node="pve")


def _wire(tmp_path, monkeypatch, ldap_config_get_return=None, fetchmail_get_return=None):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log,
    )
    api = _Api()
    pmg = _Pmg(ldap_config_get_return=ldap_config_get_return,
               fetchmail_get_return=fetchmail_get_return)
    exec_ = SimpleNamespace()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, exec_, ledger))
    monkeypatch.setattr(server, "_pmg", lambda: (SimpleNamespace(node="pmg"), pmg))
    return cfg, pmg, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _confirmed_entry(log: str, action: str, outcome: str) -> dict:
    entries = [e for e in _entries(log) if e["action"] == action and e["outcome"] == outcome]
    assert len(entries) == 1, f"expected exactly one {action!r}/{outcome!r} ledger entry, got {entries}"
    return entries[0]


# ---------------------------------------------------------------------------
# Homogeneous sweep — table-driven: "confirm=True reaches the right verb/path/data on the
# PmgBackend and records a confirmed mutation". Every mutation in this chunk's live schema returns
# `null` EXCEPT fetchmail_create (a schema-typed "Unique ID" string, not ambiguous) — outcome is
# "ok" throughout (never "submitted"), matching module docstring facts.
# ---------------------------------------------------------------------------

_SWEEP_CASES = [
    pytest.param(
        "pmg_ldap_profile_create",
        dict(profile="my-ad", server1="ldap.example.com", mode="ldaps", port=636),
        "ok", "posts", "/config/ldap",
        {"profile": "my-ad", "server1": "ldap.example.com", "mode": "ldaps", "port": 636},
        id="ldap_profile_create",
    ),
    pytest.param(
        "pmg_ldap_profile_delete",
        dict(profile="my-ad"),
        "ok", "deletes", "/config/ldap/my-ad",
        None,
        id="ldap_profile_delete",
    ),
    pytest.param(
        "pmg_ldap_profile_config_update",
        dict(profile="my-ad", comment="updated profile"),
        "ok", "puts", "/config/ldap/my-ad/config",
        {"comment": "updated profile"},
        id="ldap_profile_config_update",
    ),
    pytest.param(
        "pmg_ldap_profile_sync",
        dict(profile="my-ad"),
        "ok", "posts", "/config/ldap/my-ad/sync",
        {},
        id="ldap_profile_sync",
    ),
    pytest.param(
        "pmg_fetchmail_create",
        dict(server="mail.example.com", user="alice", password="sentinel-pw",
             target="user@example.com", protocol="pop3"),
        "ok", "posts", "/config/fetchmail",
        {"server": "mail.example.com", "user": "alice", "pass": "sentinel-pw",
         "target": "user@example.com", "protocol": "pop3"},
        id="fetchmail_create",
    ),
    pytest.param(
        "pmg_fetchmail_update",
        dict(id_="abc123", server="mail2.example.com"),
        "ok", "puts", "/config/fetchmail/abc123",
        {"server": "mail2.example.com"},
        id="fetchmail_update",
    ),
    pytest.param(
        "pmg_fetchmail_delete",
        dict(id_="abc123"),
        "ok", "deletes", "/config/fetchmail/abc123",
        None,
        id="fetchmail_delete",
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
    _, pmg, _, log = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)

    out = fn(confirm=True, **kwargs)

    # weld 1: return shape — always "ok" on this plane (module docstring facts).
    assert out["status"] == expected_status
    assert out["status"] != "plan"
    assert out["status"] != "submitted"

    # weld 2: the fake captured the underlying call at the expected verb + path. For the two
    # bare (no-params) DELETE calls, only path/verb are asserted (data_exact is None).
    calls = getattr(pmg, capture)
    assert calls, f"{tool_name} confirm=True never reached pmg.{capture}"
    call_path, call_data = calls[-1]
    assert call_path == path
    if data_exact is not None:
        assert call_data == data_exact

    # weld 3: ledger structural asserts — never exact prose.
    entry = _confirmed_entry(log, tool_name, expected_status)
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


# ---------------------------------------------------------------------------
# fetchmail_create's return: NOT ambiguous (schema explicitly documents "Unique ID") — the
# server-generated id flows through to the caller in `result`.
# ---------------------------------------------------------------------------

def test_fetchmail_create_returns_the_new_id_in_result(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_fetchmail_create(
        server="mail.example.com", user="alice", password="sentinel-pw",
        target="user@example.com", protocol="pop3", confirm=True,
    )
    assert out["result"] == pmg._FETCHMAIL_NEW_ID


# ---------------------------------------------------------------------------
# Dry-run (confirm=False) — proves the PLAN path never touches the PmgBackend's write verbs, and
# that update/delete plans CAPTURE current config via a live read.
# ---------------------------------------------------------------------------

def test_ldap_profile_create_dry_run_never_posts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_ldap_profile_create(profile="my-ad", server1="ldap.example.com", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.posts


def test_ldap_profile_delete_dry_run_reads_but_never_deletes(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_ldap_profile_delete(profile="my-ad", confirm=False)
    assert out["status"] == "plan"
    assert out["current"]["server1"] == "ldap.example.com"
    assert not pmg.deletes


def test_ldap_profile_config_update_dry_run_reads_but_never_puts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_ldap_profile_config_update(profile="my-ad", comment="new", confirm=False)
    assert out["status"] == "plan"
    assert out["current"]["server1"] == "ldap.example.com"
    assert not pmg.puts


def test_ldap_profile_config_update_dry_run_requires_at_least_one_field(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    with pytest.raises(ProximoError):
        server.pmg_ldap_profile_config_update(profile="my-ad", confirm=False)


def test_ldap_profile_sync_dry_run_never_posts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_ldap_profile_sync(profile="my-ad", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.posts


def test_fetchmail_create_dry_run_never_posts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_fetchmail_create(
        server="mail.example.com", user="alice", password="sentinel-pw",
        target="user@example.com", protocol="pop3", confirm=False,
    )
    assert out["status"] == "plan"
    assert not pmg.posts


def test_fetchmail_update_dry_run_reads_but_never_puts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_fetchmail_update(id_="abc123", server="mail2.example.com", confirm=False)
    assert out["status"] == "plan"
    assert out["current"]["server"] == "mail.example.com"
    assert not pmg.puts


def test_fetchmail_update_dry_run_requires_at_least_one_field(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    with pytest.raises(ProximoError):
        server.pmg_fetchmail_update(id_="abc123", confirm=False)


def test_fetchmail_delete_dry_run_reads_but_never_deletes(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_fetchmail_delete(id_="abc123", confirm=False)
    assert out["status"] == "plan"
    assert out["current"]["server"] == "mail.example.com"
    assert not pmg.deletes


# ---------------------------------------------------------------------------
# Reads — confirm the wrapper reaches the PmgBackend with the right path (no confirm= gate).
# ---------------------------------------------------------------------------

def test_ldap_profiles_list_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_ldap_profiles_list()
    call_path, _ = pmg.gets[-1]
    assert call_path == "/config/ldap"


def test_ldap_profile_config_get_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_ldap_profile_config_get(profile="my-ad")
    call_path, _ = pmg.gets[-1]
    assert call_path == "/config/ldap/my-ad/config"


def test_ldap_users_list_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_ldap_users_list(profile="my-ad")
    call_path, _ = pmg.gets[-1]
    assert call_path == "/config/ldap/my-ad/users"


def test_ldap_user_emails_get_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_ldap_user_emails_get(profile="my-ad", email="user@example.com")
    call_path, _ = pmg.gets[-1]
    assert call_path == "/config/ldap/my-ad/users/user@example.com"


def test_ldap_groups_list_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_ldap_groups_list(profile="my-ad")
    call_path, _ = pmg.gets[-1]
    assert call_path == "/config/ldap/my-ad/groups"


def test_ldap_group_members_get_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_ldap_group_members_get(profile="my-ad", gid=42)
    call_path, _ = pmg.gets[-1]
    assert call_path == "/config/ldap/my-ad/groups/42"


def test_fetchmail_list_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_fetchmail_list()
    call_path, _ = pmg.gets[-1]
    assert call_path == "/config/fetchmail"


def test_fetchmail_get_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_fetchmail_get(id_="abc123")
    call_path, _ = pmg.gets[-1]
    assert call_path == "/config/fetchmail/abc123"


# ---------------------------------------------------------------------------
# THE HEADLINE WELD — secret-never-in-ledger for `bindpw` (LDAP, defensive-strip contract) and
# `pass` (fetchmail, MANDATORY-strip contract), plus the read-layer strip proofs. Sentinel values
# are low-entropy/all-lowercase/hyphenated per this repo's fixture-sentinel discipline.
# ---------------------------------------------------------------------------

def test_ldap_profile_create_confirm_never_writes_bindpw_to_ledger(tmp_path, monkeypatch):
    """weld 1: the operator's real PMG call DOES carry the raw bindpw (the mutation must actually
    work) — the fake captured it. weld 2: read the ledger file RAW (bytes, not parsed JSON) and
    assert the secret substring appears NOWHERE — not in the 'planned' entry, not in the
    'confirmed' entry, not anywhere in the file."""
    _, pmg, _, log = _wire(tmp_path, monkeypatch)

    out = server.pmg_ldap_profile_create(
        profile="my-ad", server1="ldap.example.com", bindpw=_BINDPW_SENTINEL, confirm=True,
    )

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    # weld 1: the fake captured the underlying POST with the RAW bindpw.
    assert pmg.posts, "pmg_ldap_profile_create confirm=True never reached pmg._post"
    call_path, call_data = pmg.posts[-1]
    assert call_path == "/config/ldap"
    assert call_data["bindpw"] == _BINDPW_SENTINEL

    # weld 2: ledger entries (parsed JSON) never carry the bindpw sentinel.
    entries = _entries(log)
    assert entries, "no ledger entries recorded at all"
    assert all(_BINDPW_SENTINEL not in json.dumps(e) for e in entries)
    entry = _confirmed_entry(log, "pmg_ldap_profile_create", "ok")
    assert "bindpw" not in entry["detail"]

    # THE HEADLINE WELD: read the ledger file RAW (bytes) — the secret must appear NOWHERE.
    raw = open(log, "rb").read()
    assert _BINDPW_SENTINEL.encode("utf-8") not in raw

    # MIRROR-IMAGE: server1 IS present raw in the on-disk ledger (non-secret, deliberately visible).
    assert b"ldap.example.com" in raw


def test_ldap_profile_create_dry_run_plan_never_carries_bindpw(tmp_path, monkeypatch):
    """Even confirm=False (the returned PLAN dict itself, not just the ledger) must never carry
    the raw bindpw — the plan is returned directly to the calling agent."""
    _wire(tmp_path, monkeypatch)

    out = server.pmg_ldap_profile_create(
        profile="my-ad", server1="ldap.example.com", bindpw=_BINDPW_SENTINEL, confirm=False,
    )

    assert out["status"] == "plan"
    dumped = json.dumps(out)
    assert _BINDPW_SENTINEL not in dumped
    assert "ldap.example.com" in dumped  # server1 IS visible — not secret


def test_ldap_profile_config_update_confirm_never_writes_bindpw_to_ledger(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(tmp_path, monkeypatch)

    out = server.pmg_ldap_profile_config_update(
        profile="my-ad", bindpw=_BINDPW_SENTINEL, confirm=True,
    )

    assert out["status"] == "ok"
    assert pmg.puts
    _, call_data = pmg.puts[-1]
    assert call_data["bindpw"] == _BINDPW_SENTINEL

    raw = open(log, "rb").read()
    assert _BINDPW_SENTINEL.encode("utf-8") not in raw


def test_ldap_profile_config_update_dry_run_plan_never_carries_bindpw(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)

    out = server.pmg_ldap_profile_config_update(
        profile="my-ad", bindpw=_BINDPW_SENTINEL, confirm=False,
    )

    assert out["status"] == "plan"
    assert _BINDPW_SENTINEL not in json.dumps(out)


def test_ldap_profile_config_update_capture_secret_never_reaches_ledger(tmp_path, monkeypatch):
    """Defense-in-depth: the CAPTURE read (schema is thin — ldap_profile_config_get already
    strips bindpw at the read layer, but wire the fake to return one anyway to prove the
    redaction-on-top-of-strip holds even if the read-layer strip regressed) must never leak into
    the ledger either, on BOTH confirm=False and confirm=True paths."""
    leaked = "sentinel-leaked-from-a-ldap-get-that-should-have-been-stripped"
    _, _, _, log = _wire(tmp_path, monkeypatch,
                          ldap_config_get_return={"profile": "my-ad", "bindpw": leaked})

    out = server.pmg_ldap_profile_config_update(profile="my-ad", comment="new", confirm=False)
    assert out["status"] == "plan"
    assert leaked not in json.dumps(out)

    out = server.pmg_ldap_profile_config_update(profile="my-ad", comment="new", confirm=True)
    assert out["status"] == "ok"

    raw = open(log, "rb").read()
    assert leaked.encode("utf-8") not in raw


def test_ldap_profile_delete_capture_secret_never_reaches_ledger(tmp_path, monkeypatch):
    leaked = "sentinel-leaked-from-ldap-delete-capture-read"
    _, _, _, log = _wire(tmp_path, monkeypatch,
                          ldap_config_get_return={"profile": "my-ad", "bindpw": leaked})

    out = server.pmg_ldap_profile_delete(profile="my-ad", confirm=True)

    assert out["status"] == "ok"
    raw = open(log, "rb").read()
    assert leaked.encode("utf-8") not in raw


def test_ldap_profile_config_get_strips_bindpw_at_read_layer(tmp_path, monkeypatch):
    """The base read function (not just the Plan factories) strips bindpw DEFENSIVELY — proven
    through the live tool wrapper. The single-profile GET schema is bare (returns: {}), so this
    is a defensive strip, not a confirmed-echo mandatory one (contrast fetchmail below)."""
    leaked = "sentinel-leaked-bindpw-from-config-get"
    _, _, _, _ = _wire(tmp_path, monkeypatch,
                        ldap_config_get_return={"profile": "my-ad", "bindpw": leaked})

    result = server.pmg_ldap_profile_config_get(profile="my-ad")
    assert leaked not in json.dumps(result)
    assert result["profile"] == "my-ad"


def test_fetchmail_create_confirm_never_writes_pass_to_ledger(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(tmp_path, monkeypatch)

    out = server.pmg_fetchmail_create(
        server="mail.example.com", user="alice", password=_PASS_SENTINEL,
        target="user@example.com", protocol="pop3", confirm=True,
    )

    assert out["status"] == "ok"
    assert pmg.posts
    call_path, call_data = pmg.posts[-1]
    assert call_path == "/config/fetchmail"
    assert call_data["pass"] == _PASS_SENTINEL

    entries = _entries(log)
    assert entries, "no ledger entries recorded at all"
    assert all(_PASS_SENTINEL not in json.dumps(e) for e in entries)
    entry = _confirmed_entry(log, "pmg_fetchmail_create", "ok")
    assert "pass" not in entry["detail"]
    assert "password" not in entry["detail"]

    raw = open(log, "rb").read()
    assert _PASS_SENTINEL.encode("utf-8") not in raw

    # MIRROR-IMAGE: server/target ARE present raw (non-secret, deliberately visible).
    assert b"mail.example.com" in raw
    assert b"user@example.com" in raw


def test_fetchmail_create_dry_run_plan_never_carries_pass(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)

    out = server.pmg_fetchmail_create(
        server="mail.example.com", user="alice", password=_PASS_SENTINEL,
        target="user@example.com", protocol="pop3", confirm=False,
    )

    assert out["status"] == "plan"
    dumped = json.dumps(out)
    assert _PASS_SENTINEL not in dumped
    assert "mail.example.com" in dumped


def test_fetchmail_update_confirm_never_writes_pass_to_ledger(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(tmp_path, monkeypatch)

    out = server.pmg_fetchmail_update(id_="abc123", password=_PASS_SENTINEL, confirm=True)

    assert out["status"] == "ok"
    assert pmg.puts
    _, call_data = pmg.puts[-1]
    assert call_data["pass"] == _PASS_SENTINEL

    raw = open(log, "rb").read()
    assert _PASS_SENTINEL.encode("utf-8") not in raw


def test_fetchmail_update_capture_secret_never_reaches_ledger(tmp_path, monkeypatch):
    """Defense-in-depth: the CAPTURE read (schema CONFIRMS pass echoes here — fetchmail_get
    already strips it at the read layer, but wire the fake to return one anyway to prove the
    redaction-on-top-of-strip holds even if the read-layer strip regressed) must never leak into
    the ledger either, on BOTH confirm=False and confirm=True paths."""
    leaked = "sentinel-leaked-from-a-fetchmail-get-that-should-have-been-stripped"
    _, _, _, log = _wire(tmp_path, monkeypatch,
                          fetchmail_get_return={"id": "abc123", "pass": leaked})

    out = server.pmg_fetchmail_update(id_="abc123", server="mail2.example.com", confirm=False)
    assert out["status"] == "plan"
    assert leaked not in json.dumps(out)

    out = server.pmg_fetchmail_update(id_="abc123", server="mail2.example.com", confirm=True)
    assert out["status"] == "ok"

    raw = open(log, "rb").read()
    assert leaked.encode("utf-8") not in raw


def test_fetchmail_delete_capture_secret_never_reaches_ledger(tmp_path, monkeypatch):
    leaked = "sentinel-leaked-from-fetchmail-delete-capture-read"
    _, _, _, log = _wire(tmp_path, monkeypatch,
                          fetchmail_get_return={"id": "abc123", "pass": leaked})

    out = server.pmg_fetchmail_delete(id_="abc123", confirm=True)

    assert out["status"] == "ok"
    raw = open(log, "rb").read()
    assert leaked.encode("utf-8") not in raw


def test_fetchmail_list_strips_pass_at_read_layer_mandatory(tmp_path, monkeypatch):
    """MANDATORY (not defensive) — the live schema CONFIRMS pass echoes on the list endpoint."""
    leaked = "sentinel-leaked-pass-from-fetchmail-list"

    class _LeakyPmg(_Pmg):
        def _get(self, path, params=None):
            self.gets.append((path, params))
            if path == "/config/fetchmail":
                return [{"id": "abc123", "server": "mail.example.com", "pass": leaked}]
            return super()._get(path, params)

    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
                         audit_log_path=log)
    pmg = _LeakyPmg()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, _Api(), SimpleNamespace(), ledger))
    monkeypatch.setattr(server, "_pmg", lambda: (SimpleNamespace(node="pmg"), pmg))

    result = server.pmg_fetchmail_list()
    assert leaked not in json.dumps(result)
    assert result[0]["id"] == "abc123"


def test_fetchmail_get_strips_pass_at_read_layer_mandatory(tmp_path, monkeypatch):
    """MANDATORY (not defensive) — the live schema CONFIRMS pass echoes on the single-item GET
    too (unlike LDAP's schema-thin single-profile GET)."""
    leaked = "sentinel-leaked-pass-from-fetchmail-get"
    _, _, _, _ = _wire(tmp_path, monkeypatch,
                        fetchmail_get_return={"id": "abc123", "pass": leaked})

    result = server.pmg_fetchmail_get(id_="abc123")
    assert leaked not in json.dumps(result)
    assert result["id"] == "abc123"


def test_ldap_profiles_list_strips_bindpw_at_read_layer_defensive(tmp_path, monkeypatch):
    """DEFENSIVE (not mandatory — schema-confirmed absent) — but applied as defense-in-depth
    using the SAME mechanism as fetchmail_list. Proves each list item is stripped if bindpw
    leaks."""
    leaked = "sentinel-leaked-bindpw-from-ldap-profiles-list"

    class _LeakyPmg(_Pmg):
        def _get(self, path, params=None):
            self.gets.append((path, params))
            if path == "/config/ldap":
                return [{"profile": "my-ad", "server1": "ldap.example.com", "bindpw": leaked}]
            return super()._get(path, params)

    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
                         audit_log_path=log)
    pmg = _LeakyPmg()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, _Api(), SimpleNamespace(), ledger))
    monkeypatch.setattr(server, "_pmg", lambda: (SimpleNamespace(node="pmg"), pmg))

    result = server.pmg_ldap_profiles_list()
    assert leaked not in json.dumps(result)
    assert result[0]["profile"] == "my-ad"


def test_pmg_fetchmail_update_detail_includes_id(tmp_path, monkeypatch):
    """pmg_fetchmail_update's ledger detail must include id_ for audit trail clarity."""
    _, _, _, log = _wire(tmp_path, monkeypatch)

    out = server.pmg_fetchmail_update(id_="abc123", server="mail2.example.com", confirm=True)

    assert out["status"] == "ok"
    entry = _confirmed_entry(log, "pmg_fetchmail_update", "ok")
    assert entry["detail"]["id_"] == "abc123"


def test_pmg_fetchmail_delete_detail_includes_id(tmp_path, monkeypatch):
    """pmg_fetchmail_delete's ledger detail must include id_ for audit trail clarity."""
    _, _, _, log = _wire(tmp_path, monkeypatch)

    out = server.pmg_fetchmail_delete(id_="abc123", confirm=True)

    assert out["status"] == "ok"
    entry = _confirmed_entry(log, "pmg_fetchmail_delete", "ok")
    assert entry["detail"]["id_"] == "abc123"
