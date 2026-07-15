"""Confirm=True sweep — pve_access wrapper welds (+ the token-secret-never-in-ledger promise).

Closes the coverage-audit gap (`.scratch/2026-07-14-tool-coverage-audit-findings.json`, module
`src/proximo/tools/pve_access.py`, 2 high confirmed findings): every mutation tool below has its
confirm=False PLAN branch tested elsewhere (test_access.py, test_access_users.py,
test_access_governance.py) but its confirm=True EXECUTE branch — the wrapper's own `_audited(...)`
call — was never invoked through the actual `server.pve_*` wrapper, only through the underlying
op/plan functions, bypassing the wrapper's own argument-forwarding and _audited() wiring.

Mirrors the `_wire()` idiom in tests/test_server_plan.py:110-131 (already re-used and
review-approved in tests/test_confirm_sweep_pve_guest.py and
tests/test_confirm_sweep_pve_cluster_node_certs.py): `proximo.server._svc` is monkeypatched to a
fake api + a REAL AuditLedger in tmp_path, so a confirm=True call proves three welds at once:
  1. return shape — status is the EXECUTED shape ("ok", these ops are all synchronous — no
     UPID), never "plan";
  2. the fake api captured the underlying call (verb + path + data) — reusing the generic
     _get/_post/_put/_delete fake idiom already established in test_access.py/
     test_access_users.py/test_access_governance.py;
  3. the ledger recorded a confirmed mutation — structural asserts only (action, mutation,
     outcome, detail.confirmed), never exact prose.

THE headline weld this task exists for — pve_token_create's docstring promise (pve_access.py:
199-201, comment lines 210-211): confirm=True executes and returns a dict whose result carries
the token secret (value) ONCE — "it is never written to the audit ledger and cannot be retrieved
again." `test_token_create_confirm_returns_secret_but_never_writes_it_to_ledger` below holds that
promise end-to-end: the fake api returns a realistic (obviously-fake) secret string, the test
asserts the secret IS in the tool's return value (the operator must receive it — that's the whole
point of the tool), then reads the ledger file in tmp_path RAW (bytes, not text-decoded) and
asserts the secret substring appears NOWHERE in it. Mirrors the same pattern already proven for
the sibling secret (TFA password) in tests/test_server_tfa_wiring.py:65-76
(test_tfa_delete_confirm_executes_and_password_never_logged) — this closes the identical gap for
the token secret, which the audit found untested despite the pattern being known in this codebase.

The fake api's `_get` is path-aware, reusing the idiom already established in the sibling test
modules: `/access/acl` and `/access/users` (exact) return [] (so plan_acl_modify's ACL-based
shadow/widen analysis, plan_user_delete's/plan_group_delete's/plan_role_delete's/
plan_role_update's/plan_realm_delete's affected-set reads all resolve cleanly with nothing to
report), and any other read (single-user/single-group lookups) returns {} (a harmless empty
dict — present-but-empty, not a 404). This lets every tool's _plan() build (which runs even on
confirm=True — no plan, no mutation) resolve without raising, while the mutation calls land in
per-verb capture lists.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig

# Obviously-fake sentinel — never a real Proxmox token secret shape, low-entropy/hyphenated per
# this repo's public-leak-audit fixture discipline (release_leak_audit.py / CLAUDE.md).
_TOKEN_SECRET_SENTINEL = "FAKE-SECRET-a1b2c3-not-a-real-token"


class _Api:
    """Path-aware fake Proxmox api: records every _get/_post/_put/_delete call. Answers _get
    reads just enough for the PLAN builders (which always run first, even on confirm=True) to
    resolve without raising — see module docstring for the exact shapes.
    """

    def __init__(self, node: str = "pve"):
        self.config = SimpleNamespace(node=node)
        self.gets: list[str] = []
        self.posts: list[tuple[str, dict | None]] = []
        self.puts: list[tuple[str, dict | None]] = []
        self.deletes: list[tuple[str, dict | None]] = []

    def _get(self, path):
        self.gets.append(path)
        if path in ("/access/acl", "/access/users"):
            return []  # ACL/user-list reads used by the affected-set plan builders
        return {}  # single-user/single-group lookups — present, empty, no exception

    def _post(self, path, data=None):
        self.posts.append((path, data))
        if "/token/" in path:
            # token_create's real response shape: {"value": <secret>, "info": {...}} — the
            # secret is shown ONCE at creation.
            return {"value": _TOKEN_SECRET_SENTINEL, "info": {"tokenid": path.rsplit("/", 1)[-1]}}
        return None

    def _put(self, path, data=None):
        self.puts.append((path, data))
        return None

    def _delete(self, path, params=None):
        self.deletes.append((path, params))
        return None


def _wire(tmp_path, monkeypatch):
    """The `_wire()` idiom from tests/test_server_plan.py:110-131."""
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        ct_allowlist=frozenset({"*"}), audit_log_path=log,
    )
    api = _Api()
    exec_ = SimpleNamespace()  # unused by pve_access's wrappers
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, exec_, ledger))
    return cfg, api, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _confirmed_entry(log: str, action: str, outcome: str) -> dict:
    entries = [e for e in _entries(log) if e["action"] == action and e["outcome"] == outcome]
    assert len(entries) == 1, f"expected exactly one {action!r}/{outcome!r} ledger entry, got {entries}"
    return entries[0]


# ---------------------------------------------------------------------------
# Homogeneous sweep — table-driven over the 11 tools with no unique weld beyond "confirm=True
# reaches the right verb/path/data and records a confirmed mutation". pve_token_create is pulled
# out below for its dedicated secret-never-in-ledger weld.
# ---------------------------------------------------------------------------

_SWEEP_CASES = [
    pytest.param(
        "pve_acl_modify",
        dict(path="/vms/100", roles="PVEVMAdmin", target="alice@pam"),
        "ok", "puts", "/access/acl",
        # acl_modify(): kind defaults "user" -> "users" key; propagate/delete always sent (int).
        {"path": "/vms/100", "roles": "PVEVMAdmin", "users": "alice@pam",
         "propagate": 1, "delete": 0},
        id="acl_modify",
    ),
    pytest.param(
        "pve_token_revoke",
        dict(userid="alice@pam", tokenid="mytoken"),
        "ok", "deletes", "/access/users/alice@pam/token/mytoken",
        # token_revoke() calls api._delete(path) with NO params arg -> captured params=None.
        None,
        id="token_revoke",
    ),
    pytest.param(
        "pve_user_create",
        dict(userid="newuser@pam", comment="test user", groups="ops"),
        "ok", "posts", "/access/users",
        # user_create(): email/enable/expire/firstname/lastname all None -> omitted.
        {"userid": "newuser@pam", "comment": "test user", "groups": "ops"},
        id="user_create",
    ),
    pytest.param(
        "pve_user_update",
        dict(userid="newuser@pam", comment="updated comment"),
        "ok", "puts", "/access/users/newuser@pam",
        # user_update(): every other field None -> omitted.
        {"comment": "updated comment"},
        id="user_update",
    ),
    pytest.param(
        "pve_user_delete",
        dict(userid="olduser@pam"),
        "ok", "deletes", "/access/users/olduser@pam",
        # user_delete() calls api._delete(path) with NO params arg -> captured params=None.
        None,
        id="user_delete",
    ),
    pytest.param(
        "pve_group_update",
        dict(groupid="ops", comment="new comment"),
        "ok", "puts", "/access/groups/ops",
        {"comment": "new comment"},
        id="group_update",
    ),
    pytest.param(
        "pve_group_delete",
        dict(groupid="ops"),
        "ok", "deletes", "/access/groups/ops",
        # group_delete() calls api._delete(path) with NO params arg -> captured params=None.
        None,
        id="group_delete",
    ),
    pytest.param(
        "pve_role_create",
        dict(roleid="CustomOpsRole", privs="VM.PowerMgmt"),
        "ok", "posts", "/access/roles",
        {"roleid": "CustomOpsRole", "privs": "VM.PowerMgmt"},
        id="role_create",
    ),
    pytest.param(
        "pve_role_update",
        dict(roleid="CustomOpsRole", privs="VM.Config.Disk"),
        "ok", "puts", "/access/roles/CustomOpsRole",
        # role_update(): append=None -> omitted.
        {"privs": "VM.Config.Disk"},
        id="role_update",
    ),
    pytest.param(
        "pve_role_delete",
        dict(roleid="CustomOpsRole"),
        "ok", "deletes", "/access/roles/CustomOpsRole",
        # role_delete() calls api._delete(path) with NO params arg -> captured params=None.
        None,
        id="role_delete",
    ),
    pytest.param(
        "pve_realm_delete",
        dict(realm="ldap1"),
        "ok", "deletes", "/access/domains/ldap1",
        # realm_delete() calls api._delete(path) with NO params arg -> captured params=None.
        None,
        id="realm_delete",
    ),
]


@pytest.mark.parametrize(
    "tool_name,kwargs,expected_status,capture,path,data_exact", _SWEEP_CASES,
)
def test_confirm_true_executes_forwards_and_records(
    tmp_path, monkeypatch, tool_name, kwargs, expected_status, capture, path, data_exact,
):
    """confirm=True executes (never 'plan'), the fake captured the forwarded call, and the
    ledger recorded a confirmed mutation — the three welds the audit found untested."""
    _, api, _, log = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)

    out = fn(confirm=True, **kwargs)

    # weld 1: return shape is the EXECUTED shape, never "plan"
    assert out["status"] == expected_status
    assert out["status"] != "plan"

    # weld 2: the fake captured the underlying call at the expected verb + path, with the
    # EXACT forwarded payload (full dict equality — an accidental extra field now fails).
    calls = getattr(api, capture)
    assert calls, f"{tool_name} confirm=True never reached api.{capture}"
    call_path, call_data = calls[-1]
    assert call_path == path
    assert call_data == data_exact

    # weld 3: ledger structural asserts — never exact prose
    entry = _confirmed_entry(log, tool_name, expected_status)
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


# ---------------------------------------------------------------------------
# pve_token_create — THE headline weld: the docstring's promise that the token secret is
# "never written to the audit ledger" but DOES surface in the tool's return value once.
# ---------------------------------------------------------------------------


def test_token_create_confirm_returns_secret_but_never_writes_it_to_ledger(tmp_path, monkeypatch):
    """pve_token_create's docstring (pve_access.py:199-201) and the wrapper's own SECRET
    HANDLING comment (lines 210-211) promise: confirm=True executes and returns a dict whose
    result carries the token secret ONCE — 'it is never written to the audit ledger and cannot
    be retrieved again... detail dict must NEVER contain the secret'.

    Hold that promise end-to-end:
      1. the operator MUST receive the secret — assert it IS in the tool's return value;
      2. read the ledger file in tmp_path RAW (bytes, not text-decoded) and assert the secret
         substring appears NOWHERE in it — not in the 'confirmed' execute entry's detail, not
         in the earlier 'planned' entry, not anywhere in the file.

    Mirrors the identical pattern already proven for the sibling secret (TFA password) in
    tests/test_server_tfa_wiring.py:65-76.
    """
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_token_create(
        userid="automation@pve", tokenid="ci-token", privsep=True,
        comment="CI pipeline token", expire=1893456000, confirm=True,
    )

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    # weld 1: the operator receives the secret — it can never be retrieved again after this.
    assert out["result"]["value"] == _TOKEN_SECRET_SENTINEL

    # weld 2: the fake captured the underlying POST with the right path + non-secret body.
    assert api.posts, "pve_token_create confirm=True never reached api._post"
    call_path, call_data = api.posts[-1]
    assert call_path == "/access/users/automation@pve/token/ci-token"
    # exact: token_create() sends privsep (int-coerced) + comment + expire — userid/tokenid stay
    # in the URL path, never duplicated into the body.
    assert call_data == {"privsep": 1, "comment": "CI pipeline token", "expire": 1893456000}

    # weld 3: ledger structural asserts — the execute entry, plus the secret absent from detail.
    entry = _confirmed_entry(log, "pve_token_create", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
    assert entry["detail"]["privsep"] is True
    assert entry["detail"]["expire"] == 1893456000
    assert "value" not in entry["detail"]
    assert _TOKEN_SECRET_SENTINEL not in json.dumps(entry)

    # THE HEADLINE WELD: read the ledger file RAW (bytes) — the secret must appear NOWHERE in
    # the on-disk ledger, across every entry (planned + confirmed), not just the one we inspected
    # above as parsed JSON.
    raw = open(log, "rb").read()
    assert _TOKEN_SECRET_SENTINEL.encode("utf-8") not in raw
