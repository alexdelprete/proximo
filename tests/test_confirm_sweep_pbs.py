"""Confirm=True sweep — PBS wrapper welds (src/proximo/tools/pbs.py).

Closes the coverage-audit gap (`.scratch/2026-07-14-tool-coverage-audit-findings.json`, module
`src/proximo/tools/pbs.py`, 3 high + 2 med findings): every tool below has its confirm=False
PLAN branch tested elsewhere (tests/test_server_new_wiring.py, tests/test_pbs_config.py's
TestMutationGating), but its confirm=True EXECUTE branch -- the wrapper's own `_audited(...)`
call -- was never invoked through the actual `server.<tool>` wrapper. tests/test_pbs.py exercises
the underlying op functions directly (URL/param shape), bypassing the wrapper's own
argument-forwarding and `_audited()` wiring entirely.

Mirrors the `_wire()` idiom in tests/test_server_plan.py:110-131 (re-used and review-approved in
tests/test_confirm_sweep_pve_backup.py, tests/test_confirm_sweep_pve_guest.py, and
tests/test_confirm_sweep_pve_firewall_network.py) -- but this plane patches `proximo.server._pbs`
(not `_svc`, which PBS tools never touch for their backend) with a fake `PbsBackend`, matching
how tests/test_pbs_config.py and tests/test_server_new_wiring.py wire PBS-only tests. `_svc` is
still monkeypatched too, minimally -- `_ledger()` reads `_svc()[3]` for the ONE shared audit
chain (src/proximo/server.py:133-147), so PBS mutations still need a wired `_svc` even though
they never touch its ApiBackend.

Each confirm=True call proves the three welds the audit found untested:
  1. return shape -- status is the EXECUTED shape ("ok"/"submitted"), never "plan";
  2. the fake PbsBackend captured the underlying call (verb + path + data/params);
  3. the ledger recorded a confirmed mutation -- structural asserts only (mutation, detail.confirmed),
     never exact prose.

Two tools get dedicated tests instead of the generic table, per the audit-fixes plan (Task 7):
  - pbs_prune: the docstring's "TWO safety gates" tool (Proximo's confirm gate + PBS's own
    dry_run gate). Both dedicated tests call the REAL prune() op through confirm=True --
    neither gate is stubbed out -- proving each gate's own effect on the posted body
    (dry-run=1 present vs absent) and on the ledger's detail.dry_run field.
  - pbs_namespace_delete: the table covers the default (delete_groups=False, namespace-must-be-
    empty) branch; a dedicated test covers the delete_groups=True RISK_HIGH bulk-deletion branch,
    which takes a different params shape (adds "delete-groups": 1) and deserves its own weld.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig

# Obviously-fake sentinel — never a real PBS token secret shape, low-entropy/hyphenated per this
# repo's public-leak-audit fixture discipline (release_leak_audit.py / CLAUDE.md).
_TOKEN_SECRET_SENTINEL = "FAKE-PBS-SECRET-d4e5f6-not-a-real-token"
_REGENERATED_SECRET_SENTINEL = "FAKE-PBS-REGEN-SECRET-g7h8i9-not-a-real-token"
# Wave 2b: pbs_tfa_add's type='recovery' response carries server-generated one-time recovery
# codes. Low-entropy sentinel integers (not a string secret shape) per this repo's public-leak-
# audit fixture discipline.
_RECOVERY_CODES_SENTINEL = [13371337, 42424242, 90909090]


class _Pbs:
    """Path-aware fake PbsBackend: records every _get/_post/_put/_delete call. `_get` answers
    every CAPTURE-before-plan read (pbs_datastore_update, pbs_snapshot_notes_set,
    pbs_traffic_control_upsert's create-vs-update dispatch, Wave 2a's pbs_user_update/
    pbs_user_delete/pbs_acl_update CAPTURE reads, and Wave 2b's realm-update/delete + TFA-update/
    webauthn-set CAPTURE reads) with a fixed truthy dict -- enough for every CAPTURE branch to
    resolve without raising, and for traffic_control_upsert's dispatch to consistently take its
    update (PUT) path on both the plan-phase read and the execute-phase read. `_post` and `_put`
    are path-aware for '/token/' paths (Wave 2a): token_create's real response shape is
    {"tokenid": ..., "value": <secret>} shown ONCE; a regenerate=True token update's real response
    shape is {"secret": <new secret>}. `_post` is also path-aware for '/access/tfa/' paths (Wave
    2b): type='recovery' returns {"recovery": [<one-time codes>]}, any other type returns
    {"id": "totp-0"} (mirrors PBS's real POST /access/tfa/{userid} response shapes)."""

    def __init__(self):
        self.gets: list[tuple[str, dict | None]] = []
        self.posts: list[tuple[str, dict | None]] = []
        self.puts: list[tuple[str, dict | None]] = []
        self.deletes: list[tuple[str, dict | None]] = []

    def _get(self, path, params=None):
        self.gets.append((path, params))
        return {"comment": "pre-existing", "name": "existing"}

    def _post(self, path, data=None):
        self.posts.append((path, data))
        if "/token/" in path:
            return {"tokenid": path.rsplit("/", 1)[-1], "value": _TOKEN_SECRET_SENTINEL}
        if path.startswith("/access/tfa/"):
            if (data or {}).get("type") == "recovery":
                return {"recovery": _RECOVERY_CODES_SENTINEL}
            return {"id": "totp-0"}
        return "UPID:pbs:00001:0:0:0:task:100:root@pam:"

    def _put(self, path, data=None):
        self.puts.append((path, data))
        if "/token/" in path and (data or {}).get("regenerate"):
            return {"secret": _REGENERATED_SECRET_SENTINEL}
        return None

    def _delete(self, path, params=None):
        self.deletes.append((path, params))
        return None


class _Api:
    """Minimal PVE API stub -- only needed so server._svc() resolves (the ONE shared ledger
    lives behind it, per _ledger()'s _svc()[3] read); PBS tools never touch this backend."""

    def __init__(self):
        self.config = SimpleNamespace(node="pve")


def _wire(tmp_path, monkeypatch):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log,
    )
    api = _Api()
    pbs = _Pbs()
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
# PbsBackend and records a confirmed mutation".
# ---------------------------------------------------------------------------

_SWEEP_CASES = [
    pytest.param(
        "pbs_snapshot_delete",
        dict(store="ds1", backup_type="ct", backup_id="102", backup_time=1700000000),
        "ok", "deletes", "/admin/datastore/ds1/snapshots",
        {"backup-type": "ct", "backup-id": "102", "backup-time": 1700000000},
        id="snapshot_delete",
    ),
    pytest.param(
        "pbs_namespace_delete",
        dict(store="ds1", ns="team"),  # delete_groups defaults False — the empty-namespace branch
        "ok", "deletes", "/admin/datastore/ds1/namespace",
        {"ns": "team"},
        id="namespace_delete_empty_branch",
    ),
    pytest.param(
        "pbs_verify_start",
        dict(store="ds1", ns="team"),
        "submitted", "posts", "/admin/datastore/ds1/verify",
        {"ns": "team"},
        id="verify_start",
    ),
    pytest.param(
        "pbs_datastore_update",
        dict(name="ds1", gc_schedule="daily"),
        "ok", "puts", "/config/datastore/ds1",
        {"gc-schedule": "daily"},
        id="datastore_update",
    ),
    pytest.param(
        "pbs_group_change_owner",
        dict(store="ds1", backup_type="ct", backup_id="102", new_owner="alice@pbs"),
        "ok", "posts", "/admin/datastore/ds1/change-owner",
        {"backup-type": "ct", "backup-id": "102", "new-owner": "alice@pbs"},
        id="group_change_owner",
    ),
    pytest.param(
        "pbs_snapshot_notes_set",
        dict(store="ds1", backup_type="ct", backup_id="102", backup_time=1700000000, notes="annotated"),
        "ok", "puts", "/admin/datastore/ds1/notes",
        # snapshot_notes_set() always builds the full identifying dict, not just notes= --
        # backup-type/backup-id/backup-time are unconditional, ns is omitted (not passed).
        {"backup-type": "ct", "backup-id": "102", "backup-time": 1700000000, "notes": "annotated"},
        id="snapshot_notes_set",
    ),
    pytest.param(
        "pbs_traffic_control_upsert",
        dict(name="rule1", rate_in=1000),
        "ok", "puts", "/config/traffic-control/rule1",
        {"rate-in": 1000},
        id="traffic_control_upsert",
    ),
    # --- PBS APT plane (Wave 1b, 2026-07-15 full-surface campaign) ---
    pytest.param(
        "pbs_apt_update_refresh",
        dict(node="pbs1", notify=True, quiet=False),
        "submitted", "posts", "/nodes/pbs1/apt/update",
        {"notify": True, "quiet": False},
        id="apt_update_refresh",
    ),
    pytest.param(
        "pbs_apt_repository_set",
        dict(path="/etc/apt/sources.list", index=0, node="pbs1", enabled=False, digest="a" * 64),
        "ok", "posts", "/nodes/pbs1/apt/repositories",
        {"path": "/etc/apt/sources.list", "index": 0, "enabled": False, "digest": "a" * 64},
        id="apt_repository_set",
    ),
    pytest.param(
        "pbs_apt_repository_add",
        dict(handle="no-subscription", node="pbs1", digest="b" * 64),
        "ok", "puts", "/nodes/pbs1/apt/repositories",
        {"handle": "no-subscription", "digest": "b" * 64},
        id="apt_repository_add",
    ),
    # --- PBS access plane (Wave 2a, 2026-07-15 full-surface campaign) — 6 of the 7 mutations;
    # pbs_token_create gets its own dedicated secret-never-in-ledger test below, mirroring
    # pve_token_create's headline weld in test_confirm_sweep_pve_access.py.
    pytest.param(
        "pbs_user_create",
        dict(userid="newuser@pbs", comment="test user"),
        "ok", "posts", "/access/users",
        {"userid": "newuser@pbs", "comment": "test user"},
        id="user_create",
    ),
    pytest.param(
        "pbs_user_update",
        dict(userid="u@pbs", comment="updated comment"),
        "ok", "puts", "/access/users/u@pbs",
        {"comment": "updated comment"},
        id="user_update",
    ),
    pytest.param(
        "pbs_user_delete",
        dict(userid="olduser@pbs"),
        "ok", "deletes", "/access/users/olduser@pbs",
        None,
        id="user_delete",
    ),
    pytest.param(
        "pbs_token_update",
        dict(userid="u@pbs", token_name="tok1", comment="updated token comment"),
        "ok", "puts", "/access/users/u@pbs/token/tok1",
        # regenerate defaults False -> the metadata-only branch; the regenerate=True HIGH branch
        # gets its own dedicated test below (it also returns a secret).
        {"comment": "updated token comment"},
        id="token_update_metadata_only",
    ),
    pytest.param(
        "pbs_token_delete",
        dict(userid="u@pbs", token_name="tok1"),
        "ok", "deletes", "/access/users/u@pbs/token/tok1",
        None,
        id="token_delete",
    ),
    pytest.param(
        "pbs_acl_update",
        dict(path="/datastore/ds1", role="DatastoreAdmin", auth_id="alice@pbs"),
        "ok", "puts", "/access/acl",
        {"path": "/datastore/ds1", "role": "DatastoreAdmin", "auth-id": "alice@pbs"},
        id="acl_update_grant",
    ),
    # --- PBS realms + TFA (Wave 2b, 2026-07-15 full-surface campaign) — 15 of the 16 new
    # mutations; pbs_tfa_add gets its own dedicated secret-never-in-ledger test below (its
    # type='recovery' response carries server-generated one-time codes), mirroring
    # pbs_token_create's identical exclusion from this table above.
    pytest.param(
        "pbs_realm_ad_create",
        dict(realm="corp", server1="ad1.example.com"),
        "ok", "posts", "/config/access/ad",
        {"realm": "corp", "server1": "ad1.example.com"},
        id="realm_ad_create",
    ),
    pytest.param(
        "pbs_realm_ad_update",
        dict(realm="corp", comment="updated"),
        "ok", "puts", "/config/access/ad/corp",
        {"comment": "updated"},
        id="realm_ad_update",
    ),
    pytest.param(
        "pbs_realm_ad_delete",
        dict(realm="corp"),
        "ok", "deletes", "/config/access/ad/corp",
        None,
        id="realm_ad_delete",
    ),
    pytest.param(
        "pbs_realm_ldap_create",
        dict(realm="corp", server1="ldap1.example.com", base_dn="dc=corp", user_attr="uid"),
        "ok", "posts", "/config/access/ldap",
        {"realm": "corp", "server1": "ldap1.example.com", "user-attr": "uid", "base-dn": "dc=corp"},
        id="realm_ldap_create",
    ),
    pytest.param(
        "pbs_realm_ldap_update",
        dict(realm="corp", comment="updated"),
        "ok", "puts", "/config/access/ldap/corp",
        {"comment": "updated"},
        id="realm_ldap_update",
    ),
    pytest.param(
        "pbs_realm_ldap_delete",
        dict(realm="corp"),
        "ok", "deletes", "/config/access/ldap/corp",
        None,
        id="realm_ldap_delete",
    ),
    pytest.param(
        "pbs_realm_openid_create",
        dict(realm="sso", issuer_url="https://issuer.example.com", client_id="client-abc"),
        "ok", "posts", "/config/access/openid",
        {"realm": "sso", "issuer-url": "https://issuer.example.com", "client-id": "client-abc"},
        id="realm_openid_create",
    ),
    pytest.param(
        "pbs_realm_openid_update",
        dict(realm="sso", comment="updated"),
        "ok", "puts", "/config/access/openid/sso",
        {"comment": "updated"},
        id="realm_openid_update",
    ),
    pytest.param(
        "pbs_realm_openid_delete",
        dict(realm="sso"),
        "ok", "deletes", "/config/access/openid/sso",
        None,
        id="realm_openid_delete",
    ),
    pytest.param(
        "pbs_realm_pam_set",
        dict(comment="updated"),
        "ok", "puts", "/config/access/pam",
        {"comment": "updated"},
        id="realm_pam_set",
    ),
    pytest.param(
        "pbs_realm_pbs_set",
        dict(comment="updated"),
        "ok", "puts", "/config/access/pbs",
        {"comment": "updated"},
        id="realm_pbs_set",
    ),
    pytest.param(
        "pbs_tfa_update",
        dict(userid="u@pbs", tfa_id="totp-0", description="updated"),
        "ok", "puts", "/access/tfa/u@pbs/totp-0",
        {"description": "updated"},
        id="tfa_update",
    ),
    pytest.param(
        "pbs_tfa_delete",
        dict(userid="u@pbs", tfa_id="totp-0"),
        "ok", "deletes", "/access/tfa/u@pbs/totp-0",
        None,
        id="tfa_delete",
    ),
    pytest.param(
        "pbs_tfa_unlock",
        dict(userid="u@pbs"),
        "ok", "puts", "/access/users/u@pbs/unlock-tfa",
        None,
        id="tfa_unlock",
    ),
    pytest.param(
        "pbs_tfa_webauthn_set",
        dict(rp_id="new.example.com"),
        "ok", "puts", "/config/access/tfa/webauthn",
        {"id": "new.example.com"},
        id="tfa_webauthn_set",
    ),
]


@pytest.mark.parametrize(
    "tool_name,kwargs,expected_status,capture,path,data_exact", _SWEEP_CASES,
)
def test_confirm_true_executes_forwards_and_records(
    tmp_path, monkeypatch, tool_name, kwargs, expected_status, capture, path, data_exact,
):
    """confirm=True executes (never 'plan'), the fake PbsBackend captured the forwarded call,
    and the ledger recorded a confirmed mutation -- the three welds the audit found untested."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)

    out = fn(confirm=True, **kwargs)

    # weld 1: return shape is the EXECUTED shape, never "plan"
    assert out["status"] == expected_status
    assert out["status"] != "plan"

    # weld 2: the fake PbsBackend captured the underlying call at the expected verb + path, with
    # the EXACT forwarded payload (full dict equality -- an accidental extra field now fails).
    calls = getattr(pbs, capture)
    assert calls, f"{tool_name} confirm=True never reached pbs.{capture}"
    call_path, call_data = calls[-1]
    assert call_path == path
    assert call_data == data_exact

    # weld 3: ledger structural asserts — never exact prose
    entry = _confirmed_entry(log, tool_name, expected_status)
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


# ---------------------------------------------------------------------------
# pbs_prune — the "TWO safety gates" tool (docstring: Proximo's confirm gate AND PBS's own
# dry_run gate). Both tests run the real prune() op through confirm=True -- no gate is stubbed
# out -- proving each gate's actual effect on the posted body and the ledger detail.
# ---------------------------------------------------------------------------

def test_pbs_prune_confirm_true_dry_run_default_previews_via_pbs(tmp_path, monkeypatch):
    """Gate 1 (confirm) open, gate 2 (dry_run) shut (its default, True): the wrapper still
    executes -- status is the executed shape "ok", not "plan" -- but the posted body carries
    PBS's own dry-run=1, so the underlying prune() only asks PBS to preview, not delete."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch)

    out = server.pbs_prune("ds1", keep_last=3, confirm=True)  # dry_run left at its default True

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    assert pbs.posts, "pbs_prune confirm=True never reached pbs.posts"
    path, data = pbs.posts[-1]
    assert path == "/admin/datastore/ds1/prune"
    # exact: prune() builds only the retention knobs actually passed plus dry-run when set --
    # keep_last is the only retention kwarg given, so keep-daily/weekly/monthly/yearly/ns/
    # backup-type/backup-id stay OUT of the body entirely (omitted, not None-valued).
    assert data == {"keep-last": 3, "dry-run": 1}

    entry = _confirmed_entry(log, "pbs_prune", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
    assert entry["detail"]["dry_run"] is True


def test_pbs_prune_confirm_true_dry_run_false_executes_real_delete(tmp_path, monkeypatch):
    """Both gates open (confirm=True AND dry_run=False): the real, permanent-delete PBS call
    fires -- no 'dry-run' key in the posted body -- and the ledger's detail.dry_run is honestly
    False, distinguishing this from the preview-only call above."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch)

    out = server.pbs_prune("ds1", keep_last=3, dry_run=False, confirm=True)

    assert out["status"] == "ok"

    path, data = pbs.posts[-1]
    assert path == "/admin/datastore/ds1/prune"
    # exact: dry_run=False drops the "dry-run" key entirely (never sent as 0/false).
    assert data == {"keep-last": 3}

    entry = _confirmed_entry(log, "pbs_prune", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
    assert entry["detail"]["dry_run"] is False


# ---------------------------------------------------------------------------
# pbs_namespace_delete, delete_groups=True — the RISK_HIGH bulk-deletion branch. The sweep
# table above covers the default (delete_groups=False, namespace-must-be-empty) branch; this
# is the "deletes all backup groups/snapshots inside the namespace, no undo" branch named
# explicitly by the audit-fixes plan.
# ---------------------------------------------------------------------------

def test_pbs_namespace_delete_confirm_true_delete_groups_high_branch(tmp_path, monkeypatch):
    _, pbs, _, log = _wire(tmp_path, monkeypatch)

    out = server.pbs_namespace_delete("ds1", "team/prod", delete_groups=True, confirm=True)

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    assert pbs.deletes, "pbs_namespace_delete confirm=True never reached pbs.deletes"
    path, params = pbs.deletes[-1]
    assert path == "/admin/datastore/ds1/namespace"
    # exact: namespace_delete() builds {"ns": ...} then adds "delete-groups": 1 only when the
    # flag is True -- nothing else.
    assert params == {"ns": "team/prod", "delete-groups": 1}

    entry = _confirmed_entry(log, "pbs_namespace_delete", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


# ---------------------------------------------------------------------------
# pbs_token_create — THE headline weld for Wave 2a (PBS access plane): the docstring's promise
# that the token secret is never written to the audit ledger but DOES surface in the tool's
# return value once. Mirrors test_confirm_sweep_pve_access.py's identical PVE-plane test.
# ---------------------------------------------------------------------------

def test_pbs_token_create_confirm_returns_secret_but_never_writes_it_to_ledger(tmp_path, monkeypatch):
    """pbs_token_create's docstring and the wrapper's own SECRET HANDLING comment promise:
    confirm=True executes and returns a dict whose result carries the token secret (value) ONCE
    -- it is never written to the audit ledger and cannot be retrieved again.

    Hold that promise end-to-end:
      1. the operator MUST receive the secret -- assert it IS in the tool's return value;
      2. read the ledger file in tmp_path RAW (bytes, not text-decoded) and assert the secret
         substring appears NOWHERE in it -- not in the 'confirmed' execute entry's detail, not
         in the earlier 'planned' entry, not anywhere in the file.
    """
    _, pbs, _, log = _wire(tmp_path, monkeypatch)

    out = server.pbs_token_create(
        userid="automation@pbs", token_name="ci-token", comment="CI pipeline token",
        expire=1893456000, confirm=True,
    )

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    # weld 1: the operator receives the secret -- it can never be retrieved again after this.
    assert out["result"]["value"] == _TOKEN_SECRET_SENTINEL

    # weld 2: the fake captured the underlying POST with the right path + non-secret body.
    assert pbs.posts, "pbs_token_create confirm=True never reached pbs._post"
    call_path, call_data = pbs.posts[-1]
    assert call_path == "/access/users/automation@pbs/token/ci-token"
    assert call_data == {"comment": "CI pipeline token", "expire": 1893456000}

    # weld 3: ledger structural asserts -- the execute entry, plus the secret absent from detail.
    entry = _confirmed_entry(log, "pbs_token_create", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
    assert entry["detail"]["expire"] == 1893456000
    assert "value" not in entry["detail"]
    assert _TOKEN_SECRET_SENTINEL not in json.dumps(entry)

    # THE HEADLINE WELD: read the ledger file RAW (bytes) -- the secret must appear NOWHERE in
    # the on-disk ledger, across every entry (planned + confirmed).
    raw = open(log, "rb").read()
    assert _TOKEN_SECRET_SENTINEL.encode("utf-8") not in raw


# ---------------------------------------------------------------------------
# pbs_token_update, regenerate=True — the RISK_HIGH branch, and its OWN secret-never-in-ledger
# weld: a regenerated token's new secret is a SECOND secret-bearing shape on this plane distinct
# from token_create's, and must be held to the identical never-in-ledger promise.
# ---------------------------------------------------------------------------

def test_pbs_token_update_regenerate_true_returns_new_secret_never_writes_it_to_ledger(tmp_path, monkeypatch):
    _, pbs, _, log = _wire(tmp_path, monkeypatch)

    out = server.pbs_token_update(
        userid="automation@pbs", token_name="ci-token", regenerate=True, confirm=True,
    )

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    # weld 1: the operator receives the NEW secret.
    assert out["result"]["secret"] == _REGENERATED_SECRET_SENTINEL

    # weld 2: the fake captured the underlying PUT with regenerate=True.
    call_path, call_data = pbs.puts[-1]
    assert call_path == "/access/users/automation@pbs/token/ci-token"
    assert call_data == {"regenerate": True}

    # weld 3: ledger structural asserts -- the secret is absent from detail, and never on disk.
    entry = _confirmed_entry(log, "pbs_token_update", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
    assert entry["detail"]["regenerate"] is True
    assert "secret" not in entry["detail"]
    assert _REGENERATED_SECRET_SENTINEL not in json.dumps(entry)

    raw = open(log, "rb").read()
    assert _REGENERATED_SECRET_SENTINEL.encode("utf-8") not in raw


# ---------------------------------------------------------------------------
# pbs_tfa_add, type='recovery' -- THE headline weld for Wave 2b's TFA plane: PBS's own
# POST /access/tfa/{userid} response schema carries `{"recovery": [<one-time codes>], ...}` for
# this type -- SERVER-GENERATED secret material, shown ONCE and never retrievable again. Holds
# the identical never-in-ledger promise as pbs_token_create's headline weld above.
# ---------------------------------------------------------------------------

def test_pbs_tfa_add_recovery_type_returns_codes_but_never_writes_them_to_ledger(tmp_path, monkeypatch):
    """pbs_tfa_add's docstring and the wrapper's own SECRET HANDLING comment promise: for
    type='recovery', confirm=True's result carries the one-time recovery codes -- they are never
    written to the audit ledger and cannot be retrieved again.

    Hold that promise end-to-end:
      1. the operator MUST receive the codes -- assert they ARE in the tool's return value;
      2. read the ledger file in tmp_path RAW (bytes, not text-decoded) and assert every code
         appears NOWHERE in it -- not in the 'confirmed' execute entry's detail, not in the
         earlier 'planned' entry, not anywhere in the file.
    """
    _, pbs, _, log = _wire(tmp_path, monkeypatch)

    out = server.pbs_tfa_add(userid="automation@pbs", tfa_type="recovery", confirm=True)

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    # weld 1: the operator receives the codes -- they can never be retrieved again after this.
    assert out["result"]["recovery"] == _RECOVERY_CODES_SENTINEL

    # weld 2: the fake captured the underlying POST with the right path + non-secret body.
    assert pbs.posts, "pbs_tfa_add confirm=True never reached pbs._post"
    call_path, call_data = pbs.posts[-1]
    assert call_path == "/access/tfa/automation@pbs"
    assert call_data == {"type": "recovery"}

    # weld 3: ledger structural asserts -- the codes absent from detail, and never on disk.
    entry = _confirmed_entry(log, "pbs_tfa_add", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
    assert entry["detail"]["type"] == "recovery"
    assert "recovery" not in entry["detail"]
    entry_json = json.dumps(entry)
    for code in _RECOVERY_CODES_SENTINEL:
        assert str(code) not in entry_json

    # THE HEADLINE WELD: read the ledger file RAW (bytes) -- every code must appear NOWHERE in
    # the on-disk ledger, across every entry (planned + confirmed).
    raw = open(log, "rb").read()
    for code in _RECOVERY_CODES_SENTINEL:
        assert str(code).encode("utf-8") not in raw


def test_pbs_tfa_add_totp_type_metadata_only_no_secret_generated(tmp_path, monkeypatch):
    """Contrast case: for type='totp', PBS does not generate a secret server-side (the caller
    already supplied one via `totp`) -- the response is metadata-only ({"id": ...}), and the
    confirm=True weld still holds the exact-payload + ledger discipline like any other mutation."""
    _, pbs, _, log = _wire(tmp_path, monkeypatch)

    out = server.pbs_tfa_add(
        userid="automation@pbs", tfa_type="totp", totp="otpauth://totp/x", value="123456",
        confirm=True,
    )

    assert out["status"] == "ok"
    assert out["result"] == {"id": "totp-0"}

    call_path, call_data = pbs.posts[-1]
    assert call_path == "/access/tfa/automation@pbs"
    assert call_data == {"type": "totp", "totp": "otpauth://totp/x", "value": "123456"}

    entry = _confirmed_entry(log, "pbs_tfa_add", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
    assert entry["detail"]["type"] == "totp"
