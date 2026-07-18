"""Confirm=True sweep — PMG identity (auth-realm, local users, TFA — chunk 9h; global appliance
config + cluster bootstrap/join — chunk 9i) wrapper welds (src/proximo/pmg_identity.py +
src/proximo/tools/pmg_identity.py, full-surface campaign) + THE SECRET CONTRACT proof for all
EIGHT secret shapes this file carries: chunk 9h's SIX — user `password`/`crypt_pass`/`keys` (the
third a genuine find, Fact 3), TFA step-up `password`, TFA `recovery` codes (in the CREATE
RESPONSE, not a param), and OIDC realm `client-key` — PLUS chunk 9i's TWO: cluster `password`
(the target master's own THIRD-PARTY superuser credential, Fact 18 — including the Wave 9i review
CRITICAL fix's hostile-echoed-response repro, "THE CLUSTER DANGER CONTRACT" below) and admin
config's `http_proxy` (secret-SHAPED embedded userinfo).

Mirrors the `_wire()`/`_Pmg` idiom already established in `tests/test_confirm_sweep_pmg_acme_certs.py`
(itself mirroring `tests/test_confirm_sweep_pbs_node.py`'s own `_Pbs` template): `_svc` is
monkeypatched (the ONE shared audit ledger lives behind it) and `_pmg` is monkeypatched to a fake
PmgBackend. New file (no prior confirm-sweep coverage existed before chunk 9h landed).

Each homogeneous confirm=True call proves the three welds every confirm-sweep module proves:
  1. return shape — status is "ok" (every write in this chunk is schema-typed `null`, synchronous);
  2. the fake PmgBackend captured the underlying call (verb + path + EXACT payload);
  3. the ledger recorded a confirmed mutation — structural asserts only, never exact prose.

THE HEADLINE WELDS (chunk 9h's secret contract, §5 of the draft):
  - user `password`/`crypt_pass`/`keys`: never-in-ledger on create/update; defensive strip on the
    single-user read (schema-thin).
  - TFA `password` (step-up, add/update/delete): never-in-ledger on write.
  - TFA `recovery` (one-time codes, tfa_add's CREATE RESPONSE only): never-in-ledger — the
    campaign's Wave-2b PBS precedent, proven here for PMG.
  - OIDC realm `client-key`: never-in-ledger on create/update; defensive strip on the single-realm
    read (schema-thin).
RULING 3 (conditional MEDIUM/HIGH on `role`) and the last-admin-equivalent-account footgun
warning are also proven here at the wrapper level (dry-run plan output), complementing the direct
plan-factory coverage in tests/test_pmg_identity.py.

THE HEADLINE WELDS (chunk 9i's secret contract, "CHUNK 9i" section below):
  - cluster `password`: never-in-ledger on pmg_cluster_join, proven with a raw-ledger-bytes sweep.
    Wave 9i review CRITICAL fix: the join endpoint's own RESPONSE is schema-unconstrained
    (`{"type": "string"}`) and could echo the submitted password back (e.g. a hostile or
    auth-failure-shaped message) — `test_cluster_join_password_never_leaks_via_hostile_echoed_response`
    reproduces that exact shape with a fake that echoes the password inline, and proves it reaches
    neither the caller-facing result nor the raw on-disk ledger. `raw_result` is therefore omitted
    from the ledger entirely for cluster_join (unlike cluster_create, which takes no secret
    parameter and safely keeps it).
  - admin config's `http_proxy`: masked at the plan DISPLAY layer and the ledger, forwarded RAW on
    the actual PUT (the write must still work).

Sentinel values are low-entropy (all-lowercase, hyphenated) per this repo's fixture-sentinel
discipline (CLAUDE.md: a mixed-case test-sentinel password failed CI on v0.13.0).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.backends import ProximoError
from proximo.config import ProximoConfig

_PASSWORD_SENTINEL = "sentinel-user-password-value"  # noqa: S105 (test sentinel, not a real credential)
_CRYPT_PASS_SENTINEL = "sentinel-crypt-pass-hash-placeholder"  # noqa: S105
_KEYS_SENTINEL = "sentinel-yubico-key-material"  # noqa: S105
_TFA_STEPUP_PASSWORD_SENTINEL = "sentinel-tfa-stepup-password"  # noqa: S105
_CLIENT_KEY_SENTINEL = "sentinel-oidc-client-key-value"  # noqa: S105
_RECOVERY_CODES = ["sentinel-recovery-code-1", "sentinel-recovery-code-2"]

_REALM_GET_RETURN = {"realm": "myrealm", "type": "oidc", "comment": "old-comment"}
_USER_GET_RETURN = {"userid": "alice@pmg", "role": "audit", "comment": "old-comment"}
_TFA_USER_LIST_RETURN = [{"id": "totp1", "type": "totp", "enable": True}]
_TFA_ENTRY_GET_RETURN = {"id": "totp1", "type": "totp", "enable": True}

# 9i fixtures — global-config captures + cluster reads.
_ADMIN_GET_RETURN = {"email": "admin@old.example.com", "demo": False, "clamav": True}
_CLAMAV_GET_RETURN = {"archiveblockencrypted": True, "archivemaxfiles": 1000}
_MAIL_GET_RETURN = {"banner": "old-banner", "tls": True, "spf": True}
_SPAMQUAR_GET_RETURN = {"authmode": "ldap", "quarantinelink": False}
_VIRUSQUAR_GET_RETURN = {"allowhrefs": False}
_WEBAUTHN_GET_RETURN = {"rp": "PMG", "id": "old.example.com"}
_CLUSTER_STATUS_RETURN = [{"cid": 0, "name": "pmg", "type": "node"}]
_CLUSTER_JOIN_INFO_RETURN = {"ip": "10.0.0.1", "fingerprint": "aa:bb:cc", "product": "PMG", "version": "9.1"}
_CLUSTER_NODES_RETURN = [{"cid": 0, "name": "pmg", "ip": "10.0.0.1"}]
_MASTER_PASSWORD_SENTINEL = "sentinel-target-master-superuser-password"  # noqa: S105


class _Pmg:
    """Path-aware fake PmgBackend: records every _get/_post/_put/_delete call.

    `_get` returns fixed, secret-free captures for the CAPTURE reads (realm/user/tfa
    update-or-delete plan previews, PLUS the 9i global-config reads + cluster status) keyed by
    path; every other GET path defaults to `[]`.
    `_post`/`_put`/`_delete` return `None` (schema `null`) for everything except
    `POST /access/tfa/{userid}` (tfa_add — returns the TFA-entry-with-optional-recovery shape),
    `PUT /access/users/{userid}/unlock-tfa` (returns a bool), and the 9i cluster create/join
    POSTs (return a schema-ambiguous string).

    `cluster_join_echoes_password=True` (Wave 9i review CRITICAL repro) makes
    `POST /config/cluster/join` HOSTILE: instead of the fixed `cluster_join_return` string, it
    echoes the submitted `password` back inline, in a realistic auth-failure-message shape
    (`"error: join refused, presented credential {password!r} did not match"`) — the exact
    reproduction the review used to prove the leak, since PMG's own schema for this endpoint's
    return is `{"type": "string"}` with no further constraint (Fact 19): nothing guarantees the
    response CONTENT is safe.
    """

    def __init__(self, realm_get_return=None, user_get_return=None, users_list_return=None,
                 tfa_user_list_return=None, tfa_entry_get_return=None, tfa_add_return=None,
                 unlock_tfa_return=True,
                 admin_get_return=None, clamav_get_return=None, mail_get_return=None,
                 spamquar_get_return=None, virusquar_get_return=None, webauthn_get_return=None,
                 cluster_status_return=None, cluster_create_return="OK: cluster created",
                 cluster_join_return="OK: joined cluster", cluster_join_echoes_password=False):
        self._realm_get_return = realm_get_return or dict(_REALM_GET_RETURN)
        self._user_get_return = user_get_return or dict(_USER_GET_RETURN)
        self._users_list_return = users_list_return  # for access_permissions's own GET /access/users
        self._tfa_user_list_return = tfa_user_list_return or list(_TFA_USER_LIST_RETURN)
        self._tfa_entry_get_return = tfa_entry_get_return or dict(_TFA_ENTRY_GET_RETURN)
        self._tfa_add_return = tfa_add_return
        self._unlock_tfa_return = unlock_tfa_return
        def _or_default(value, default):
            return value if value is not None else default
        self._admin_get_return = _or_default(admin_get_return, dict(_ADMIN_GET_RETURN))
        self._clamav_get_return = _or_default(clamav_get_return, dict(_CLAMAV_GET_RETURN))
        self._mail_get_return = _or_default(mail_get_return, dict(_MAIL_GET_RETURN))
        self._spamquar_get_return = _or_default(spamquar_get_return, dict(_SPAMQUAR_GET_RETURN))
        self._virusquar_get_return = _or_default(virusquar_get_return, dict(_VIRUSQUAR_GET_RETURN))
        self._webauthn_get_return = _or_default(webauthn_get_return, dict(_WEBAUTHN_GET_RETURN))
        self._cluster_status_return = _or_default(cluster_status_return, list(_CLUSTER_STATUS_RETURN))
        self._cluster_create_return = cluster_create_return
        self._cluster_join_return = cluster_join_return
        self._cluster_join_echoes_password = cluster_join_echoes_password
        self.gets: list[tuple[str, dict | None]] = []
        self.posts: list[tuple[str, dict | None]] = []
        self.puts: list[tuple[str, dict | None]] = []
        self.deletes: list[tuple[str, dict | None]] = []

    def _get(self, path, params=None):
        self.gets.append((path, params))
        if path == "/access/auth-realm/myrealm":
            return self._realm_get_return
        if path == "/access/users/alice@pmg":
            return self._user_get_return
        if path == "/access/users":
            return self._users_list_return if self._users_list_return is not None else []
        if path == "/access/tfa/alice@pmg":
            return self._tfa_user_list_return
        if path == "/access/tfa/alice@pmg/totp1":
            return self._tfa_entry_get_return
        if path == "/config/admin":
            return self._admin_get_return
        if path == "/config/clamav":
            return self._clamav_get_return
        if path == "/config/mail":
            return self._mail_get_return
        if path == "/config/spamquar":
            return self._spamquar_get_return
        if path == "/config/virusquar":
            return self._virusquar_get_return
        if path == "/config/tfa/webauthn":
            return self._webauthn_get_return
        if path == "/config/cluster/status":
            return self._cluster_status_return
        if path == "/config/cluster/join":
            return dict(_CLUSTER_JOIN_INFO_RETURN)
        if path == "/config/cluster/nodes":
            return list(_CLUSTER_NODES_RETURN)
        return []

    def _post(self, path, data=None):
        self.posts.append((path, data))
        if path == "/access/tfa/alice@pmg":
            if self._tfa_add_return is not None:
                return self._tfa_add_return
            if data and data.get("type") == "recovery":
                return {"id": "new-tfa-1", "recovery": list(_RECOVERY_CODES)}
            return {"id": "new-tfa-1"}
        if path == "/config/cluster/create":
            return self._cluster_create_return
        if path == "/config/cluster/join":
            if self._cluster_join_echoes_password:
                pw = (data or {}).get("password", "")
                return f"error: join refused, presented credential {pw!r} did not match"
            return self._cluster_join_return
        if path == "/config/cluster/nodes":
            return [{"cid": 3}]
        return None

    def _put(self, path, data=None):
        self.puts.append((path, data))
        if path == "/access/users/alice@pmg/unlock-tfa":
            return self._unlock_tfa_return
        return None

    def _delete(self, path, params=None):
        self.deletes.append((path, params))
        return None


class _Api:
    """Minimal PVE API stub — only needed so server._svc() resolves (the ONE shared ledger lives
    behind it); the identity tools never touch this backend."""

    def __init__(self):
        self.config = SimpleNamespace(node="pve")


def _wire(tmp_path, monkeypatch, **pmg_kwargs):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log,
    )
    api = _Api()
    pmg = _Pmg(**pmg_kwargs)
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
# PmgBackend and records a confirmed mutation".
# ---------------------------------------------------------------------------

_SWEEP_CASES = [
    pytest.param(
        "pmg_access_realm_create",
        dict(realm="myrealm", realm_type="oidc", issuer_url="https://idp.example.com", client_id="cid"),
        "posts", "/access/auth-realm",
        {"realm": "myrealm", "type": "oidc", "issuer-url": "https://idp.example.com", "client-id": "cid"},
        id="realm_create",
    ),
    pytest.param(
        "pmg_access_realm_update",
        dict(realm="myrealm", comment="new-comment"),
        "puts", "/access/auth-realm/myrealm",
        {"comment": "new-comment"},
        id="realm_update",
    ),
    pytest.param(
        "pmg_access_realm_delete",
        dict(realm="myrealm"),
        "deletes", "/access/auth-realm/myrealm",
        None,
        id="realm_delete",
    ),
    pytest.param(
        "pmg_access_user_create",
        dict(userid="alice@pmg", role="audit"),
        "posts", "/access/users",
        {"userid": "alice@pmg", "role": "audit"},
        id="user_create",
    ),
    pytest.param(
        "pmg_access_user_update",
        dict(userid="alice@pmg", comment="new-comment"),
        "puts", "/access/users/alice@pmg",
        {"comment": "new-comment"},
        id="user_update",
    ),
    pytest.param(
        "pmg_access_user_delete",
        dict(userid="alice@pmg"),
        "deletes", "/access/users/alice@pmg",
        None,
        id="user_delete",
    ),
    pytest.param(
        "pmg_access_user_unlock_tfa",
        dict(userid="alice@pmg"),
        "puts", "/access/users/alice@pmg/unlock-tfa",
        None,
        id="user_unlock_tfa",
    ),
    pytest.param(
        "pmg_access_tfa_add",
        dict(userid="alice@pmg", tfa_type="totp", totp="otpauth://totp/sentinel"),
        "posts", "/access/tfa/alice@pmg",
        {"type": "totp", "totp": "otpauth://totp/sentinel"},
        id="tfa_add",
    ),
    pytest.param(
        "pmg_access_tfa_update",
        dict(userid="alice@pmg", tfa_id="totp1", enable=False),
        "puts", "/access/tfa/alice@pmg/totp1",
        {"enable": False},
        id="tfa_update",
    ),
    pytest.param(
        "pmg_access_tfa_delete",
        dict(userid="alice@pmg", tfa_id="totp1"),
        "deletes", "/access/tfa/alice@pmg/totp1",
        None,
        id="tfa_delete",
    ),
]


@pytest.mark.parametrize("tool_name,kwargs,capture,path,data_exact", _SWEEP_CASES)
def test_confirm_true_executes_forwards_and_records(
    tmp_path, monkeypatch, tool_name, kwargs, capture, path, data_exact,
):
    """confirm=True executes (status='ok', every write in this chunk is schema-null/sync), the
    fake captured the forwarded call, and the ledger recorded a confirmed mutation."""
    _, pmg, _, log = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)

    out = fn(confirm=True, **kwargs)

    # weld 1: return shape.
    assert out["status"] == "ok"
    assert out["status"] != "plan"

    # weld 2: the fake captured the underlying call at the expected verb + path.
    calls = getattr(pmg, capture)
    assert calls, f"{tool_name} confirm=True never reached pmg.{capture}"
    call_path, call_data = calls[-1]
    assert call_path == path
    if data_exact is not None:
        for k, v in data_exact.items():
            assert call_data[k] == v

    # weld 3: ledger structural asserts — never exact prose.
    entry = _confirmed_entry(log, tool_name, "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


# ---------------------------------------------------------------------------
# Reads — confirm the wrapper reaches the PmgBackend with the right path.
# ---------------------------------------------------------------------------

def test_realm_list_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_access_realm_list()
    call_path, _ = pmg.gets[-1]
    assert call_path == "/access/auth-realm"


def test_realm_get_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_access_realm_get(realm="myrealm")
    call_path, _ = pmg.gets[-1]
    assert call_path == "/access/auth-realm/myrealm"


def test_user_get_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_access_user_get(userid="alice@pmg")
    call_path, _ = pmg.gets[-1]
    assert call_path == "/access/users/alice@pmg"


def test_tfa_list_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_access_tfa_list()
    call_path, _ = pmg.gets[-1]
    assert call_path == "/access/tfa"


def test_tfa_user_list_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_access_tfa_user_list(userid="alice@pmg")
    call_path, _ = pmg.gets[-1]
    assert call_path == "/access/tfa/alice@pmg"


def test_tfa_get_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_access_tfa_get(userid="alice@pmg", tfa_id="totp1")
    call_path, _ = pmg.gets[-1]
    assert call_path == "/access/tfa/alice@pmg/totp1"


# ---------------------------------------------------------------------------
# Dry-run (confirm=False) — proves the PLAN path never touches the PmgBackend's write verbs, and
# that update/delete plans CAPTURE current config via a live read.
# ---------------------------------------------------------------------------

def test_realm_create_dry_run_never_posts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_access_realm_create(realm="myrealm", realm_type="oidc", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.posts


def test_realm_update_dry_run_reads_but_never_puts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_access_realm_update(realm="myrealm", comment="new", confirm=False)
    assert out["status"] == "plan"
    assert out["current"]["comment"] == "old-comment"
    assert not pmg.puts


def test_realm_delete_dry_run_reads_but_never_deletes(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_access_realm_delete(realm="myrealm", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.deletes


def test_user_create_dry_run_never_posts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_access_user_create(userid="alice@pmg", role="audit", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.posts


def test_user_update_dry_run_reads_but_never_puts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_access_user_update(userid="alice@pmg", comment="new", confirm=False)
    assert out["status"] == "plan"
    assert out["current"]["role"] == "audit"
    assert not pmg.puts


def test_user_delete_dry_run_reads_but_never_deletes(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_access_user_delete(userid="alice@pmg", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.deletes


def test_user_unlock_tfa_dry_run_never_puts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_access_user_unlock_tfa(userid="alice@pmg", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.puts


def test_tfa_add_dry_run_never_posts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_access_tfa_add(userid="alice@pmg", tfa_type="totp", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.posts


def test_tfa_update_dry_run_reads_but_never_puts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_access_tfa_update(userid="alice@pmg", tfa_id="totp1", enable=False, confirm=False)
    assert out["status"] == "plan"
    assert out["current"]["id"] == "totp1"
    assert not pmg.puts


def test_tfa_delete_dry_run_reads_but_never_deletes(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_access_tfa_delete(userid="alice@pmg", tfa_id="totp1", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.deletes


# ---------------------------------------------------------------------------
# RULING 3 — conditional MEDIUM/HIGH on `role`, proven at the wrapper (dry-run) level.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role", ["root", "admin"])
def test_user_create_admin_equivalent_role_is_high(tmp_path, monkeypatch, role):
    _wire(tmp_path, monkeypatch)
    out = server.pmg_access_user_create(userid="alice@pmg", role=role, confirm=False)
    assert out["risk"] == "high"


@pytest.mark.parametrize("role", ["helpdesk", "qmanager", "audit"])
def test_user_create_non_admin_role_is_medium(tmp_path, monkeypatch, role):
    _wire(tmp_path, monkeypatch)
    out = server.pmg_access_user_create(userid="alice@pmg", role=role, confirm=False)
    assert out["risk"] == "medium"


def test_user_update_resolves_effective_role_from_capture(tmp_path, monkeypatch):
    _, _, _, _ = _wire(tmp_path, monkeypatch, user_get_return={"userid": "alice@pmg", "role": "admin"})
    out = server.pmg_access_user_update(userid="alice@pmg", comment="hi", confirm=False)
    assert out["risk"] == "high"


def test_user_update_supplied_role_overrides_captured_role(tmp_path, monkeypatch):
    _, _, _, _ = _wire(tmp_path, monkeypatch, user_get_return={"userid": "alice@pmg", "role": "admin"})
    out = server.pmg_access_user_update(userid="alice@pmg", role="audit", confirm=False)
    assert out["risk"] == "medium"


# ---------------------------------------------------------------------------
# Last-admin-equivalent-account footgun — proven at the wrapper level, reusing the real
# access_permissions(GET /access/users) read through the fake.
# ---------------------------------------------------------------------------

def test_user_delete_warns_when_deleting_the_last_admin(tmp_path, monkeypatch):
    _, _, _, _ = _wire(
        tmp_path, monkeypatch,
        user_get_return={"userid": "alice@pmg", "role": "admin", "enable": True},
        users_list_return=[{"userid": "alice@pmg", "role": "admin", "enable": True}],
    )
    out = server.pmg_access_user_delete(userid="alice@pmg", confirm=False)
    assert any("LAST ENABLED ADMIN" in b for b in out["blast_radius"])


def test_user_delete_no_warning_with_multiple_admins(tmp_path, monkeypatch):
    _, _, _, _ = _wire(
        tmp_path, monkeypatch,
        user_get_return={"userid": "alice@pmg", "role": "admin", "enable": True},
        users_list_return=[
            {"userid": "alice@pmg", "role": "admin", "enable": True},
            {"userid": "bob@pmg", "role": "root", "enable": True},
        ],
    )
    out = server.pmg_access_user_delete(userid="alice@pmg", confirm=False)
    assert not any("LAST ENABLED ADMIN" in b for b in out["blast_radius"])


def test_user_delete_no_warning_for_non_admin_user(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)  # default user_get_return has role='audit'
    out = server.pmg_access_user_delete(userid="alice@pmg", confirm=False)
    assert not any("LAST ENABLED ADMIN" in b for b in out["blast_radius"])


# ---------------------------------------------------------------------------
# THE HEADLINE WELD #1 — user password/crypt_pass/keys (THREE secrets, Fact 3): never-in-ledger
# on create/update; defensive strip on the single-user read.
# ---------------------------------------------------------------------------

def test_user_create_confirm_never_writes_any_of_the_three_secrets_to_ledger(tmp_path, monkeypatch):
    """weld 1: the real PMG call DOES carry all three raw secrets (the create must actually
    work). weld 2: read the ledger file RAW (bytes) — NONE of the three secrets appear anywhere."""
    _, pmg, _, log = _wire(tmp_path, monkeypatch)

    out = server.pmg_access_user_create(
        userid="alice@pmg", role="audit", password=_PASSWORD_SENTINEL,
        crypt_pass=_CRYPT_PASS_SENTINEL, keys=_KEYS_SENTINEL, confirm=True,
    )

    assert out["status"] == "ok"

    # weld 1: the fake captured the underlying POST with all three raw secrets.
    assert pmg.posts, "pmg_access_user_create confirm=True never reached pmg._post"
    call_path, call_data = pmg.posts[-1]
    assert call_path == "/access/users"
    assert call_data["password"] == _PASSWORD_SENTINEL
    assert call_data["crypt_pass"] == _CRYPT_PASS_SENTINEL
    assert call_data["keys"] == _KEYS_SENTINEL

    # weld 2: ledger entries (parsed JSON) never carry any of the three secrets.
    entries = _entries(log)
    assert entries, "no ledger entries recorded at all"
    assert all(_PASSWORD_SENTINEL not in json.dumps(e) for e in entries)
    assert all(_CRYPT_PASS_SENTINEL not in json.dumps(e) for e in entries)
    assert all(_KEYS_SENTINEL not in json.dumps(e) for e in entries)
    entry = _confirmed_entry(log, "pmg_access_user_create", "ok")
    assert entry["detail"]["password"] == "[redacted]"
    assert entry["detail"]["crypt_pass"] == "[redacted]"
    assert entry["detail"]["keys"] == "[redacted]"

    # THE HEADLINE WELD: read the ledger file RAW (bytes) — none of the three secrets appear.
    raw = open(log, "rb").read()
    assert _PASSWORD_SENTINEL.encode("utf-8") not in raw
    assert _CRYPT_PASS_SENTINEL.encode("utf-8") not in raw
    assert _KEYS_SENTINEL.encode("utf-8") not in raw

    # MIRROR-IMAGE: role IS present raw in the on-disk ledger (non-secret, deliberately visible).
    assert b"audit" in raw


def test_user_create_dry_run_plan_never_carries_any_secret(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)

    out = server.pmg_access_user_create(
        userid="alice@pmg", role="audit", password=_PASSWORD_SENTINEL,
        crypt_pass=_CRYPT_PASS_SENTINEL, keys=_KEYS_SENTINEL, confirm=False,
    )

    assert out["status"] == "plan"
    dumped = json.dumps(out)
    assert _PASSWORD_SENTINEL not in dumped
    assert _CRYPT_PASS_SENTINEL not in dumped
    assert _KEYS_SENTINEL not in dumped
    assert out["password"] == "[redacted]"
    assert out["crypt_pass"] == "[redacted]"
    assert out["keys"] == "[redacted]"


def test_user_update_confirm_never_writes_any_of_the_three_secrets_to_ledger(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(tmp_path, monkeypatch)

    out = server.pmg_access_user_update(
        userid="alice@pmg", password=_PASSWORD_SENTINEL, crypt_pass=_CRYPT_PASS_SENTINEL,
        keys=_KEYS_SENTINEL, confirm=True,
    )

    assert out["status"] == "ok"
    assert pmg.puts
    _, call_data = pmg.puts[-1]
    assert call_data["password"] == _PASSWORD_SENTINEL
    assert call_data["crypt_pass"] == _CRYPT_PASS_SENTINEL
    assert call_data["keys"] == _KEYS_SENTINEL

    raw = open(log, "rb").read()
    assert _PASSWORD_SENTINEL.encode("utf-8") not in raw
    assert _CRYPT_PASS_SENTINEL.encode("utf-8") not in raw
    assert _KEYS_SENTINEL.encode("utf-8") not in raw


def test_user_get_strips_all_three_secrets_at_read_layer_defensive(tmp_path, monkeypatch):
    """DEFENSIVE — the single-user read is schema-thin (unconfirmed either way); stripped
    regardless of schema silence."""
    leaked = {"userid": "alice@pmg", "role": "audit",
              "password": "leaked-pw", "crypt_pass": "leaked-crypt", "keys": "leaked-keys"}
    _, _, _, _ = _wire(tmp_path, monkeypatch, user_get_return=leaked)

    result = server.pmg_access_user_get(userid="alice@pmg")
    dumped = json.dumps(result)
    assert "leaked-pw" not in dumped
    assert "leaked-crypt" not in dumped
    assert "leaked-keys" not in dumped
    assert result["role"] == "audit"


def test_user_update_capture_secrets_never_reach_ledger(tmp_path, monkeypatch):
    """Defense-in-depth: the CAPTURE read for plan_user_update already strips all three secret
    fields at the read layer, but the fake is wired to return them anyway to prove the
    redaction-on-top-of-strip holds even if the read-layer strip regressed."""
    leaked = {"userid": "alice@pmg", "role": "audit",
              "password": "leaked-pw2", "crypt_pass": "leaked-crypt2", "keys": "leaked-keys2"}
    _, _, _, log = _wire(tmp_path, monkeypatch, user_get_return=leaked)

    out = server.pmg_access_user_update(userid="alice@pmg", comment="hi", confirm=False)
    assert out["status"] == "plan"
    dumped = json.dumps(out)
    assert "leaked-pw2" not in dumped
    assert "leaked-crypt2" not in dumped
    assert "leaked-keys2" not in dumped

    out = server.pmg_access_user_update(userid="alice@pmg", comment="hi", confirm=True)
    assert out["status"] == "ok"

    raw = open(log, "rb").read()
    assert b"leaked-pw2" not in raw
    assert b"leaked-crypt2" not in raw
    assert b"leaked-keys2" not in raw


# ---------------------------------------------------------------------------
# THE HEADLINE WELD #2 — TFA step-up `password` (add/update/delete): never-in-ledger on write.
# ---------------------------------------------------------------------------

def test_tfa_add_confirm_never_writes_stepup_password_to_ledger(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(tmp_path, monkeypatch)

    out = server.pmg_access_tfa_add(
        userid="alice@pmg", tfa_type="totp", totp="otpauth://x",
        password=_TFA_STEPUP_PASSWORD_SENTINEL, confirm=True,
    )

    assert out["status"] == "ok"
    assert pmg.posts
    _, call_data = pmg.posts[-1]
    assert call_data["password"] == _TFA_STEPUP_PASSWORD_SENTINEL

    raw = open(log, "rb").read()
    assert _TFA_STEPUP_PASSWORD_SENTINEL.encode("utf-8") not in raw
    entry = _confirmed_entry(log, "pmg_access_tfa_add", "ok")
    assert entry["detail"]["password"] == "[redacted]"


def test_tfa_update_confirm_never_writes_stepup_password_to_ledger(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(tmp_path, monkeypatch)

    out = server.pmg_access_tfa_update(
        userid="alice@pmg", tfa_id="totp1", enable=False,
        password=_TFA_STEPUP_PASSWORD_SENTINEL, confirm=True,
    )

    assert out["status"] == "ok"
    _, call_data = pmg.puts[-1]
    assert call_data["password"] == _TFA_STEPUP_PASSWORD_SENTINEL

    raw = open(log, "rb").read()
    assert _TFA_STEPUP_PASSWORD_SENTINEL.encode("utf-8") not in raw


def test_tfa_delete_confirm_never_writes_stepup_password_to_ledger(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(tmp_path, monkeypatch)

    out = server.pmg_access_tfa_delete(
        userid="alice@pmg", tfa_id="totp1", password=_TFA_STEPUP_PASSWORD_SENTINEL, confirm=True,
    )

    assert out["status"] == "ok"
    _, call_params = pmg.deletes[-1]
    assert call_params["password"] == _TFA_STEPUP_PASSWORD_SENTINEL

    raw = open(log, "rb").read()
    assert _TFA_STEPUP_PASSWORD_SENTINEL.encode("utf-8") not in raw


def test_tfa_add_dry_run_plan_never_carries_stepup_password(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    out = server.pmg_access_tfa_add(
        userid="alice@pmg", tfa_type="totp", password=_TFA_STEPUP_PASSWORD_SENTINEL, confirm=False,
    )
    assert out["status"] == "plan"
    assert _TFA_STEPUP_PASSWORD_SENTINEL not in json.dumps(out)
    assert out["password"] == "[redacted]"


def test_tfa_add_totp_uri_and_registration_value_never_reach_the_ledger(tmp_path, monkeypatch):
    """The 7d 'hunt a 3rd/4th secret' discipline, applied one step further: `totp` (a caller-
    generated otpauth:// URI that embeds a long-lived shared TOTP secret) and `value`/`challenge`
    (the registration/verification payload) are never redacted with an explicit marker — they are
    simply never added to the `detail=` dict at all (matching the shipped PBS twin's own
    tools/pbs_access.py convention: only `password`/`confirmed`/`type` are ever put in `detail=`
    for this call). Proven here with a raw-ledger-bytes assertion rather than just inspecting the
    wrapper source, so a future refactor that widens `detail=` would be caught."""
    _, pmg, _, log = _wire(tmp_path, monkeypatch)
    totp_uri = "otpauth://totp/sentinel-account?secret=SENTINELBASE32SECRETVALUE&issuer=pmg"
    reg_value = "sentinel-registration-verification-value"

    out = server.pmg_access_tfa_add(
        userid="alice@pmg", tfa_type="totp", totp=totp_uri, value=reg_value, confirm=True,
    )

    assert out["status"] == "ok"
    _, call_data = pmg.posts[-1]
    assert call_data["totp"] == totp_uri
    assert call_data["value"] == reg_value

    entry = _confirmed_entry(log, "pmg_access_tfa_add", "ok")
    assert "totp" not in entry["detail"]
    assert "value" not in entry["detail"]

    raw = open(log, "rb").read()
    assert totp_uri.encode("utf-8") not in raw
    assert reg_value.encode("utf-8") not in raw


# ---------------------------------------------------------------------------
# THE HEADLINE WELD #3 — TFA `recovery` codes: returned ONCE in tfa_add's CREATE RESPONSE,
# never written to the ledger (the campaign's Wave-2b PBS precedent, proven here for PMG).
# ---------------------------------------------------------------------------

def test_tfa_add_recovery_codes_reach_the_caller_but_never_the_ledger(tmp_path, monkeypatch):
    """weld 1: the caller's own response DOES carry the recovery codes (they must actually be
    usable). weld 2: read the ledger file RAW (bytes) — the codes never appear anywhere."""
    _, pmg, _, log = _wire(
        tmp_path, monkeypatch,
        tfa_add_return={"id": "rec1", "recovery": list(_RECOVERY_CODES)},
    )

    out = server.pmg_access_tfa_add(userid="alice@pmg", tfa_type="recovery", confirm=True)

    assert out["status"] == "ok"
    # weld 1: the caller sees the actual recovery codes.
    assert out["result"]["recovery"] == _RECOVERY_CODES

    # weld 2: ledger entries never carry either code.
    entries = _entries(log)
    for code in _RECOVERY_CODES:
        assert all(code not in json.dumps(e) for e in entries)
    entry = _confirmed_entry(log, "pmg_access_tfa_add", "ok")
    assert "recovery" not in entry["detail"]
    assert "id" not in entry["detail"]

    # THE HEADLINE WELD: read the ledger file RAW (bytes) — neither code appears anywhere.
    raw = open(log, "rb").read()
    for code in _RECOVERY_CODES:
        assert code.encode("utf-8") not in raw


# ---------------------------------------------------------------------------
# THE HEADLINE WELD #4 — OIDC realm `client-key`: never-in-ledger on create/update; defensive
# strip on the single-realm read.
# ---------------------------------------------------------------------------

def test_realm_create_confirm_never_writes_client_key_to_ledger(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(tmp_path, monkeypatch)

    out = server.pmg_access_realm_create(
        realm="myrealm", realm_type="oidc", issuer_url="https://idp.example.com",
        client_id="cid", client_key=_CLIENT_KEY_SENTINEL, confirm=True,
    )

    assert out["status"] == "ok"
    assert pmg.posts
    _, call_data = pmg.posts[-1]
    assert call_data["client-key"] == _CLIENT_KEY_SENTINEL

    raw = open(log, "rb").read()
    assert _CLIENT_KEY_SENTINEL.encode("utf-8") not in raw
    entry = _confirmed_entry(log, "pmg_access_realm_create", "ok")
    assert entry["detail"]["client-key"] == "[redacted]"


def test_realm_update_confirm_never_writes_client_key_to_ledger(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(tmp_path, monkeypatch)

    out = server.pmg_access_realm_update(
        realm="myrealm", client_key=_CLIENT_KEY_SENTINEL, confirm=True,
    )

    assert out["status"] == "ok"
    _, call_data = pmg.puts[-1]
    assert call_data["client-key"] == _CLIENT_KEY_SENTINEL

    raw = open(log, "rb").read()
    assert _CLIENT_KEY_SENTINEL.encode("utf-8") not in raw


def test_realm_create_dry_run_plan_never_carries_client_key(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    out = server.pmg_access_realm_create(
        realm="myrealm", realm_type="oidc", client_key=_CLIENT_KEY_SENTINEL, confirm=False,
    )
    assert out["status"] == "plan"
    assert _CLIENT_KEY_SENTINEL not in json.dumps(out)
    assert out["client-key"] == "[redacted]"


def test_realm_get_strips_client_key_at_read_layer_defensive(tmp_path, monkeypatch):
    leaked = {"realm": "myrealm", "type": "oidc", "client-key": "leaked-client-key"}
    _, _, _, _ = _wire(tmp_path, monkeypatch, realm_get_return=leaked)

    result = server.pmg_access_realm_get(realm="myrealm")
    dumped = json.dumps(result)
    assert "leaked-client-key" not in dumped
    assert result["realm"] == "myrealm"


def test_realm_update_capture_client_key_never_reaches_ledger(tmp_path, monkeypatch):
    leaked = {"realm": "myrealm", "type": "oidc", "client-key": "leaked-client-key2"}
    _, _, _, log = _wire(tmp_path, monkeypatch, realm_get_return=leaked)

    out = server.pmg_access_realm_update(realm="myrealm", comment="hi", confirm=False)
    assert out["status"] == "plan"
    assert "leaked-client-key2" not in json.dumps(out)

    out = server.pmg_access_realm_update(realm="myrealm", comment="hi", confirm=True)
    assert out["status"] == "ok"

    raw = open(log, "rb").read()
    assert b"leaked-client-key2" not in raw


# ---------------------------------------------------------------------------
# KITCHEN-SINK independent sweep — every mutation in this chunk fired against ONE shared ledger,
# every one of the six secret shapes present at once, then the on-disk ledger file is read RAW
# (bytes) exactly ONCE at the end and checked against every sentinel. This is the "content-blind,
# not schema-shaped" form of the guarantee (mirrors the 9f review's own framing) — it does not
# rely on knowing which specific ledger key would have carried a leak, only that the raw bytes on
# disk never contain any of the six secret sentinel values, no matter how many mutations ran
# first. Non-secret sentinels (role, comment, realm type) DO appear — proving the sweep isn't
# vacuously passing because nothing was ever written to the ledger at all.
# ---------------------------------------------------------------------------

def test_kitchen_sink_no_secret_survives_across_every_mutation_in_this_chunk(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(
        tmp_path, monkeypatch,
        tfa_add_return={"id": "rec1", "recovery": list(_RECOVERY_CODES)},
    )

    server.pmg_access_realm_create(
        realm="myrealm", realm_type="oidc", client_key=_CLIENT_KEY_SENTINEL, confirm=True,
    )
    server.pmg_access_realm_update(realm="myrealm", client_key=_CLIENT_KEY_SENTINEL, confirm=True)
    server.pmg_access_realm_delete(realm="myrealm", confirm=True)
    server.pmg_access_user_create(
        userid="alice@pmg", role="admin", password=_PASSWORD_SENTINEL,
        crypt_pass=_CRYPT_PASS_SENTINEL, keys=_KEYS_SENTINEL, confirm=True,
    )
    server.pmg_access_user_update(
        userid="alice@pmg", password=_PASSWORD_SENTINEL, crypt_pass=_CRYPT_PASS_SENTINEL,
        keys=_KEYS_SENTINEL, role="audit", confirm=True,
    )
    server.pmg_access_user_delete(userid="alice@pmg", confirm=True)
    server.pmg_access_user_unlock_tfa(userid="alice@pmg", confirm=True)
    server.pmg_access_tfa_add(
        userid="alice@pmg", tfa_type="recovery", password=_TFA_STEPUP_PASSWORD_SENTINEL, confirm=True,
    )
    server.pmg_access_tfa_update(
        userid="alice@pmg", tfa_id="totp1", password=_TFA_STEPUP_PASSWORD_SENTINEL, confirm=True,
    )
    server.pmg_access_tfa_delete(
        userid="alice@pmg", tfa_id="totp1", password=_TFA_STEPUP_PASSWORD_SENTINEL, confirm=True,
    )

    raw = open(log, "rb").read()

    # THE SIX SECRETS: none survive anywhere in the on-disk ledger, across ANY of the 10 mutations.
    assert _CLIENT_KEY_SENTINEL.encode("utf-8") not in raw
    assert _PASSWORD_SENTINEL.encode("utf-8") not in raw
    assert _CRYPT_PASS_SENTINEL.encode("utf-8") not in raw
    assert _KEYS_SENTINEL.encode("utf-8") not in raw
    assert _TFA_STEPUP_PASSWORD_SENTINEL.encode("utf-8") not in raw
    for code in _RECOVERY_CODES:
        assert code.encode("utf-8") not in raw

    # MIRROR-IMAGE: the sweep isn't vacuous — non-secret values DO appear on disk.
    assert b"myrealm" in raw
    assert b"alice@pmg" in raw
    assert b"admin" in raw or b"audit" in raw


# ===========================================================================
# CHUNK 9i — Global appliance config + cluster bootstrap/join (Wave 9i, full-surface campaign,
# `.scratch/2026-07-15-full-surface-campaign.md` "Wave 9 decomposition", RULING 1 + RULING 5)
#
# THE CLUSTER DANGER CONTRACT — this section's headline: `pmg_cluster_join`'s `password` is the
# TARGET MASTER's own root/superuser credential (a THIRD-PARTY secret, Fact 18) — proven
# never-in-ledger with a raw-ledger-bytes sweep (the campaign's mandatory proof form). `admin
# config`'s `http_proxy` is secret-SHAPED (embedded userinfo) — proven masked at both the plan
# DISPLAY layer and the ledger, while still forwarded RAW to the actual PUT.
# ===========================================================================

_SWEEP_CASES_9I = [
    pytest.param(
        "pmg_config_admin_update", dict(demo=True), "puts", "/config/admin",
        {"demo": True}, id="config_admin_update",
    ),
    pytest.param(
        "pmg_config_clamav_update", dict(scriptedupdates=False), "puts", "/config/clamav",
        {"scriptedupdates": False}, id="config_clamav_update",
    ),
    pytest.param(
        "pmg_config_mail_update", dict(banner="new-banner"), "puts", "/config/mail",
        {"banner": "new-banner"}, id="config_mail_update",
    ),
    pytest.param(
        "pmg_config_spamquar_update", dict(quarantinelink=False), "puts", "/config/spamquar",
        {"quarantinelink": False}, id="config_spamquar_update",
    ),
    pytest.param(
        "pmg_config_virusquar_update", dict(allowhrefs=False), "puts", "/config/virusquar",
        {"allowhrefs": False}, id="config_virusquar_update",
    ),
    pytest.param(
        "pmg_config_tfa_webauthn_update", dict(rp="new-rp"), "puts", "/config/tfa/webauthn",
        {"rp": "new-rp"}, id="config_tfa_webauthn_update",
    ),
    pytest.param(
        "pmg_cluster_node_add",
        dict(
            fingerprint="fp", hostrsapubkey="hostkey", ip="10.0.0.7", name="node3",
            rootrsapubkey="rootkey",
        ),
        "posts", "/config/cluster/nodes",
        {
            "fingerprint": "fp", "hostrsapubkey": "hostkey", "ip": "10.0.0.7", "name": "node3",
            "rootrsapubkey": "rootkey",
        },
        id="cluster_node_add",
    ),
    pytest.param(
        "pmg_cluster_update_fingerprints", {}, "posts", "/config/cluster/update-fingerprints",
        None, id="cluster_update_fingerprints",
    ),
]


@pytest.mark.parametrize("tool_name,kwargs,capture,path,data_exact", _SWEEP_CASES_9I)
def test_9i_confirm_true_executes_forwards_and_records(
    tmp_path, monkeypatch, tool_name, kwargs, capture, path, data_exact,
):
    """9i's own homogeneous sweep — same three welds as the 9h table above (return shape / fake
    captured the call / ledger recorded a confirmed mutation), for the 8 tools whose write is
    schema-null/thin-array and synchronous ("ok"), i.e. everything EXCEPT cluster_create/join
    (schema-ambiguous string -> "submitted", covered separately below)."""
    _, pmg, _, log = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)

    out = fn(confirm=True, **kwargs)

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    calls = getattr(pmg, capture)
    assert calls, f"{tool_name} confirm=True never reached pmg.{capture}"
    call_path, call_data = calls[-1]
    assert call_path == path
    if data_exact is not None:
        for k, v in data_exact.items():
            assert call_data[k] == v

    entry = _confirmed_entry(log, tool_name, "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


# ---------------------------------------------------------------------------
# Reads — the 8 read-only 9i tools reach the PmgBackend at the right path.
# ---------------------------------------------------------------------------

def test_config_admin_get_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_config_admin_get()
    assert pmg.gets[-1][0] == "/config/admin"


def test_config_clamav_get_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_config_clamav_get()
    assert pmg.gets[-1][0] == "/config/clamav"


def test_config_spamquar_get_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_config_spamquar_get()
    assert pmg.gets[-1][0] == "/config/spamquar"


def test_config_virusquar_get_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_config_virusquar_get()
    assert pmg.gets[-1][0] == "/config/virusquar"


def test_config_tfa_webauthn_get_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_config_tfa_webauthn_get()
    assert pmg.gets[-1][0] == "/config/tfa/webauthn"


def test_cluster_join_info_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_cluster_join_info()
    assert pmg.gets[-1][0] == "/config/cluster/join"


def test_cluster_nodes_list_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_cluster_nodes_list()
    assert pmg.gets[-1][0] == "/config/cluster/nodes"


def test_cluster_status_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_cluster_status()
    assert pmg.gets[-1][0] == "/config/cluster/status"


# ---------------------------------------------------------------------------
# Dry-run (confirm=False) — the 10 9i mutations never touch their write verb; update-type
# tools CAPTURE current config via a live read first.
# ---------------------------------------------------------------------------

def test_config_admin_update_dry_run_reads_but_never_puts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_config_admin_update(demo=True, confirm=False)
    assert out["status"] == "plan"
    assert out["current"]["email"] == "admin@old.example.com"
    assert not pmg.puts


def test_config_clamav_update_dry_run_never_puts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_config_clamav_update(scriptedupdates=False, confirm=False)
    assert out["status"] == "plan"
    assert not pmg.puts


def test_config_mail_update_dry_run_captures_via_relay_config(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_config_mail_update(banner="new-banner", confirm=False)
    assert out["status"] == "plan"
    assert out["current"]["banner"] == "old-banner"
    assert not pmg.puts


def test_config_spamquar_update_dry_run_never_puts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_config_spamquar_update(quarantinelink=True, confirm=False)
    assert out["status"] == "plan"
    assert not pmg.puts


def test_config_virusquar_update_dry_run_never_puts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_config_virusquar_update(allowhrefs=True, confirm=False)
    assert out["status"] == "plan"
    assert not pmg.puts


def test_config_tfa_webauthn_update_dry_run_never_puts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_config_tfa_webauthn_update(id_="new.example.com", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.puts


def test_cluster_node_add_dry_run_never_posts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_cluster_node_add(
        fingerprint="fp", hostrsapubkey="hostkey", ip="10.0.0.7", name="node3",
        rootrsapubkey="rootkey", confirm=False,
    )
    assert out["status"] == "plan"
    assert not pmg.posts


def test_cluster_update_fingerprints_dry_run_never_posts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_cluster_update_fingerprints(confirm=False)
    assert out["status"] == "plan"
    assert not pmg.posts


def test_cluster_create_dry_run_never_posts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_cluster_create(confirm=False)
    assert out["status"] == "plan"
    assert not pmg.posts


def test_cluster_join_dry_run_never_posts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_cluster_join(
        fingerprint="ab:cd", master_ip="10.0.0.5", password=_MASTER_PASSWORD_SENTINEL, confirm=False,
    )
    assert out["status"] == "plan"
    assert not pmg.posts


# ---------------------------------------------------------------------------
# RULING 1 — cluster create/join: RISK_HIGH, no-undo first line, at the wrapper (dry-run) level.
# ---------------------------------------------------------------------------

def test_cluster_create_dry_run_is_high_with_no_undo_first_line(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    out = server.pmg_cluster_create(confirm=False)
    assert out["risk"] == "high"
    assert "NO UNDO" in out["blast_radius"][0]


def test_cluster_join_dry_run_is_high_with_no_undo_first_line(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    out = server.pmg_cluster_join(
        fingerprint="ab:cd", master_ip="10.0.0.5", password=_MASTER_PASSWORD_SENTINEL, confirm=False,
    )
    assert out["risk"] == "high"
    assert "NO UNDO" in out["blast_radius"][0]


def test_cluster_node_add_dry_run_is_medium(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    out = server.pmg_cluster_node_add(
        fingerprint="fp", hostrsapubkey="hostkey", ip="10.0.0.7", name="node3",
        rootrsapubkey="rootkey", confirm=False,
    )
    assert out["risk"] == "medium"


def test_cluster_update_fingerprints_dry_run_is_medium(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    out = server.pmg_cluster_update_fingerprints(confirm=False)
    assert out["risk"] == "medium"


# ---------------------------------------------------------------------------
# Ambiguous-string outcome — cluster_create/join return a schema-ambiguous string; confirm=True
# records outcome="submitted". `cluster_create` (no secret parameter at all) still mirrors
# pmg_node_network_reload's established idiom exactly — the raw string in BOTH the response and
# the ledger's own detail.raw_result. `cluster_join` is DIFFERENT (Wave 9i review CRITICAL fix):
# its raw response is untrusted, possibly-secret-bearing content (see THE CLUSTER DANGER CONTRACT
# below) — the raw string still comes back in the response's "result" (password-scrubbed, defense
# in depth), but is NEVER forwarded into the ledger detail at all.
# ---------------------------------------------------------------------------

def test_cluster_create_confirm_records_submitted_and_raw_result(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(tmp_path, monkeypatch, cluster_create_return="UPID:pmg:...:cluster-create:")
    out = server.pmg_cluster_create(confirm=True)
    assert out["status"] == "submitted"
    assert out["status"] != "ok"
    assert out["result"] == "UPID:pmg:...:cluster-create:"
    entry = _confirmed_entry(log, "pmg_cluster_create", "submitted")
    assert entry["detail"]["raw_result"] == "UPID:pmg:...:cluster-create:"
    assert pmg.posts[-1][0] == "/config/cluster/create"


def test_cluster_join_confirm_records_submitted_but_omits_raw_result_from_ledger(tmp_path, monkeypatch):
    """Wave 9i review CRITICAL fix: unlike cluster_create, cluster_join's raw response is NEVER
    forwarded into the ledger detail — the ledger instead carries a fixed, safe marker (no
    runtime-derived content at all, so it cannot possibly leak anything). The caller-facing
    "result" still carries the (harmless-here) benign string."""
    _, pmg, _, log = _wire(tmp_path, monkeypatch, cluster_join_return="OK")
    out = server.pmg_cluster_join(
        fingerprint="ab:cd", master_ip="10.0.0.5", password=_MASTER_PASSWORD_SENTINEL, confirm=True,
    )
    assert out["status"] == "submitted"
    assert out["result"] == "OK"
    entry = _confirmed_entry(log, "pmg_cluster_join", "submitted")
    assert "raw_result" not in entry["detail"]
    assert pmg.posts[-1][0] == "/config/cluster/join"


# ===========================================================================
# THE CLUSTER DANGER CONTRACT — MANDATORY raw-ledger-bytes sweep for pmg_cluster_join's
# `password` (the target master's own THIRD-PARTY superuser credential, Fact 18).
# ===========================================================================

def test_cluster_join_password_never_reaches_ledger_raw_bytes(tmp_path, monkeypatch):
    """weld 1: the REAL join call DOES carry the raw password (the join must actually work).
    weld 2: read the ledger file RAW (bytes) — the password appears NOWHERE, across the plan
    preview, the confirmed-mutation entry, or any other line in the file."""
    _, pmg, _, log = _wire(tmp_path, monkeypatch)

    # Dry-run first — the plan preview itself must never carry it either.
    plan_out = server.pmg_cluster_join(
        fingerprint="ab:cd", master_ip="10.0.0.5", password=_MASTER_PASSWORD_SENTINEL, confirm=False,
    )
    assert _MASTER_PASSWORD_SENTINEL not in json.dumps(plan_out)
    assert plan_out["password"] == "[redacted]"

    out = server.pmg_cluster_join(
        fingerprint="ab:cd", master_ip="10.0.0.5", password=_MASTER_PASSWORD_SENTINEL, confirm=True,
    )
    assert out["status"] == "submitted"

    # weld 1: the fake captured the underlying POST with the RAW password (the join must work).
    assert pmg.posts, "pmg_cluster_join confirm=True never reached pmg._post"
    call_path, call_data = pmg.posts[-1]
    assert call_path == "/config/cluster/join"
    assert call_data["password"] == _MASTER_PASSWORD_SENTINEL

    # ledger entries (parsed JSON) never carry it either.
    entries = _entries(log)
    assert entries, "no ledger entries recorded at all"
    assert all(_MASTER_PASSWORD_SENTINEL not in json.dumps(e) for e in entries)
    entry = _confirmed_entry(log, "pmg_cluster_join", "submitted")
    assert entry["detail"]["password"] == "[redacted]"

    # THE HEADLINE WELD: read the ledger file RAW (bytes) — the password appears nowhere at all.
    raw = open(log, "rb").read()
    assert _MASTER_PASSWORD_SENTINEL.encode("utf-8") not in raw

    # MIRROR-IMAGE: the sweep isn't vacuous — non-secret values DO appear on disk (fingerprint,
    # master_ip, and the redaction marker itself are all fine to be visible).
    assert b"ab:cd" in raw
    assert b"10.0.0.5" in raw
    assert b"[redacted]" in raw


def test_cluster_join_password_never_leaks_via_hostile_echoed_response(tmp_path, monkeypatch):
    """Wave 9i review CRITICAL, the mandatory hostile repro: the benign-response sweep above
    (`cluster_join_return="OK"`-shaped) can NEVER demonstrate this leak path — it only proves the
    obvious case. `POST /config/cluster/join`'s return is schema-typed ONLY as
    `{"type": "string"}` (Fact 19) — nothing in the schema guarantees the CONTENT is safe. This
    test wires a hostile fake (`cluster_join_echoes_password=True`) that responds the way a real
    auth-failure message plausibly would: by echoing the submitted credential back inline
    (`"error: join refused, presented credential {password!r} did not match"`). Proves the
    password sentinel reaches NEITHER the dry-run plan, NOR the raw on-disk ledger bytes, NOR the
    caller-facing result dict — closing the exact gap the benign sweep leaves open."""
    _, pmg, _, log = _wire(tmp_path, monkeypatch, cluster_join_echoes_password=True)

    # Dry-run first — must never carry it (structurally impossible: the plan factory never
    # receives `password` at all — but re-proven here at the wrapper level too).
    plan_out = server.pmg_cluster_join(
        fingerprint="ab:cd", master_ip="10.0.0.5", password=_MASTER_PASSWORD_SENTINEL, confirm=False,
    )
    assert _MASTER_PASSWORD_SENTINEL not in json.dumps(plan_out)

    out = server.pmg_cluster_join(
        fingerprint="ab:cd", master_ip="10.0.0.5", password=_MASTER_PASSWORD_SENTINEL, confirm=True,
    )
    assert out["status"] == "submitted"

    # weld: the repro is REAL, not vacuous — the underlying POST really did carry the password,
    # so the hostile fake's echoed response really did embed it.
    assert pmg.posts, "pmg_cluster_join confirm=True never reached pmg._post"
    call_path, call_data = pmg.posts[-1]
    assert call_path == "/config/cluster/join"
    assert call_data["password"] == _MASTER_PASSWORD_SENTINEL

    # THE LEAK PATH #1: the caller-facing result dict must not carry the password even though
    # PMG's own hostile response string embedded it.
    assert _MASTER_PASSWORD_SENTINEL not in out["result"]
    assert _MASTER_PASSWORD_SENTINEL not in json.dumps(out)

    # ledger entries (parsed JSON) never carry it either.
    entries = _entries(log)
    assert entries, "no ledger entries recorded at all"
    assert all(_MASTER_PASSWORD_SENTINEL not in json.dumps(e) for e in entries)

    # THE LEAK PATH #2 / HEADLINE WELD: raw on-disk ledger bytes never carry it either, even
    # though PMG's own response string embedded it.
    raw = open(log, "rb").read()
    assert _MASTER_PASSWORD_SENTINEL.encode("utf-8") not in raw

    # MIRROR-IMAGE: the sweep isn't vacuous — non-secret values DO appear on disk.
    assert b"ab:cd" in raw
    assert b"10.0.0.5" in raw


def test_cluster_join_plan_factory_signature_never_declares_password(tmp_path, monkeypatch):
    """Structural proof (complements the byte-sweep above): the PLAN factory ITSELF is
    structurally unable to receive the secret — mirrors the wave-9g/9h `inspect.signature`
    discipline for compound secrets that must never enter the plan-building path at all."""
    import inspect

    from proximo.pmg_identity import plan_cluster_join
    assert "password" not in inspect.signature(plan_cluster_join).parameters


# ---------------------------------------------------------------------------
# http_proxy — secret-SHAPED (embedded userinfo), masked at plan DISPLAY + ledger, forwarded RAW
# on the actual write.
# ---------------------------------------------------------------------------

_HTTP_PROXY_WITH_CREDS = "http://proxyuser:proxysecretvalue@proxy.example.com:8080"


def test_admin_update_dry_run_masks_http_proxy_in_plan(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    out = server.pmg_config_admin_update(http_proxy=_HTTP_PROXY_WITH_CREDS, confirm=False)
    assert out["status"] == "plan"
    assert "proxysecretvalue" not in json.dumps(out)


def test_admin_update_confirm_forwards_http_proxy_raw_but_masks_ledger(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(tmp_path, monkeypatch)
    out = server.pmg_config_admin_update(http_proxy=_HTTP_PROXY_WITH_CREDS, confirm=True)
    assert out["status"] == "ok"

    # weld 1: the REAL PUT carries the raw proxy credential (the update must actually work).
    _, call_data = pmg.puts[-1]
    assert call_data["http_proxy"] == _HTTP_PROXY_WITH_CREDS

    # weld 2: the on-disk ledger never carries the raw credential.
    raw = open(log, "rb").read()
    assert b"proxysecretvalue" not in raw
    assert b"proxy.example.com" in raw  # mirror-image: the host part is fine to be visible


def test_admin_get_masks_http_proxy_on_read(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch, admin_get_return={"http_proxy": _HTTP_PROXY_WITH_CREDS})
    result = server.pmg_config_admin_get()
    assert "proxysecretvalue" not in json.dumps(result)


# ---------------------------------------------------------------------------
# Direction-aware plan flags, proven at the wrapper (dry-run) level (complements the direct
# plan-factory coverage in tests/test_pmg_identity.py).
# ---------------------------------------------------------------------------

def test_admin_update_flags_demo_true_at_wrapper_level(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    out = server.pmg_config_admin_update(demo=True, confirm=False)
    assert any("STOPS THE SMTP FILTER" in b for b in out["blast_radius"])


def test_spamquar_update_flags_quarantinelink_at_wrapper_level(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    out = server.pmg_config_spamquar_update(quarantinelink=True, confirm=False)
    assert any("accessible without authentication" in b for b in out["blast_radius"])


def test_webauthn_update_flags_id_change_at_wrapper_level(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    out = server.pmg_config_tfa_webauthn_update(id_="new.example.com", confirm=False)
    assert any("WILL break" in b for b in out["blast_radius"])


# ---------------------------------------------------------------------------
# At-least-one-field guard, proven at the wrapper level.
# ---------------------------------------------------------------------------

def test_config_admin_update_raises_when_no_fields_given(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    with pytest.raises(ProximoError):
        server.pmg_config_admin_update(confirm=False)


# ---------------------------------------------------------------------------
# 9i kitchen sink — every 9i secret shape, across every 9i mutation, never survives on disk.
# ---------------------------------------------------------------------------

def test_9i_kitchen_sink_no_secret_survives_across_every_mutation_in_this_chunk(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(tmp_path, monkeypatch)

    server.pmg_config_admin_update(http_proxy=_HTTP_PROXY_WITH_CREDS, confirm=True)
    server.pmg_config_clamav_update(scriptedupdates=True, confirm=True)
    server.pmg_config_mail_update(banner="hi", confirm=True)
    server.pmg_config_spamquar_update(quarantinelink=False, confirm=True)
    server.pmg_config_virusquar_update(allowhrefs=False, confirm=True)
    server.pmg_config_tfa_webauthn_update(rp="hi", confirm=True)
    server.pmg_cluster_create(confirm=True)
    server.pmg_cluster_join(
        fingerprint="ab:cd", master_ip="10.0.0.5", password=_MASTER_PASSWORD_SENTINEL, confirm=True,
    )
    server.pmg_cluster_node_add(
        fingerprint="fp", hostrsapubkey="hostkey", ip="10.0.0.7", name="node3",
        rootrsapubkey="rootkey", confirm=True,
    )
    server.pmg_cluster_update_fingerprints(confirm=True)

    raw = open(log, "rb").read()

    # THE TWO 9i SECRETS: never survive anywhere in the on-disk ledger.
    assert b"proxysecretvalue" not in raw
    assert _MASTER_PASSWORD_SENTINEL.encode("utf-8") not in raw

    # MIRROR-IMAGE: the sweep isn't vacuous — non-secret values DO appear on disk.
    assert b"node3" in raw
    assert b"10.0.0.5" in raw
