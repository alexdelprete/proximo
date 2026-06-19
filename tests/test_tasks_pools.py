"""TASK CONTROL + RESOURCE POOLS pillar tests.

Fully mocked, no live Proxmox.  Mirrors test_cluster_ops.py style:
- _api() records _get / _post / _put / _delete calls; assertions verify URL + param shapes.
- Validator-rejection tests use pytest.raises(ProximoError).
- PLAN tests verify risk classification, blast radius honesty, and action strings.
- NOTE: api._get(path) takes NO params kwarg — query params are always in the path string.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from proximo.backends import ProximoError
from proximo.planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM
from proximo.tasks_pools import (
    _check_poolid,
    plan_pool_create,
    plan_pool_delete,
    plan_pool_update,
    plan_task_stop,
    pool_create,
    pool_delete,
    pool_get,
    pool_update,
    pools_list,
    task_log,
    task_stop,
    tasks_list,
)

# ---------------------------------------------------------------------------
# Shared fake API
# ---------------------------------------------------------------------------

FAKE_UPID = "UPID:pve:00001234:00000001:66A1B2C3:vzstart:100:root@pam:"


def _api(node: str = "pve") -> SimpleNamespace:
    """Minimal API fake that records _get / _post / _put / _delete calls."""
    seen: dict = {}

    def fake_get(path):
        seen["method"] = "GET"
        seen["path"] = path
        return []

    def fake_post(path, data=None):
        seen["method"] = "POST"
        seen["path"] = path
        seen["data"] = data or {}
        return None

    def fake_put(path, data=None):
        seen["method"] = "PUT"
        seen["path"] = path
        seen["data"] = data or {}
        return None

    def fake_delete(path, params=None):
        seen["method"] = "DELETE"
        seen["path"] = path
        seen["params"] = params
        return None

    return SimpleNamespace(
        config=SimpleNamespace(node=node),
        _get=fake_get,
        _post=fake_post,
        _put=fake_put,
        _delete=fake_delete,
        seen=seen,
    )


# ---------------------------------------------------------------------------
# _check_poolid — validator
# ---------------------------------------------------------------------------

def test_check_poolid_accepts_simple_alphanum():
    assert _check_poolid("mypool") == "mypool"


def test_check_poolid_accepts_hyphen():
    assert _check_poolid("my-pool") == "my-pool"


def test_check_poolid_accepts_underscore():
    assert _check_poolid("my_pool") == "my_pool"


def test_check_poolid_accepts_mixed():
    assert _check_poolid("Dev-Pool_01") == "Dev-Pool_01"


def test_check_poolid_rejects_empty():
    with pytest.raises(ProximoError):
        _check_poolid("")


def test_check_poolid_rejects_leading_hyphen():
    with pytest.raises(ProximoError):
        _check_poolid("-pool")


def test_check_poolid_rejects_leading_underscore():
    with pytest.raises(ProximoError):
        _check_poolid("_pool")


def test_check_poolid_rejects_slash():
    with pytest.raises(ProximoError):
        _check_poolid("my/pool")


def test_check_poolid_rejects_colon():
    with pytest.raises(ProximoError):
        _check_poolid("my:pool")


def test_check_poolid_rejects_dot():
    with pytest.raises(ProximoError):
        _check_poolid("my.pool")


def test_check_poolid_rejects_newline():
    """\\Z anchor prevents embedded newline bypass."""
    with pytest.raises(ProximoError):
        _check_poolid("pool\ninjection")


def test_check_poolid_rejects_over_40_chars():
    # 41 chars: 'a' * 41
    with pytest.raises(ProximoError):
        _check_poolid("a" * 41)


def test_check_poolid_accepts_exactly_40_chars():
    # 'a' + 39 more = 40 total (1 start char + 39 continuation chars = matches {0,39})
    assert _check_poolid("a" * 40) == "a" * 40


def test_check_poolid_rejects_whitespace_only():
    with pytest.raises(ProximoError):
        _check_poolid("   ")


# ---------------------------------------------------------------------------
# tasks_list — URL + param shapes
# ---------------------------------------------------------------------------

def test_tasks_list_uses_correct_node_path():
    api = _api()
    tasks_list(api)
    assert "/nodes/pve/tasks" in api.seen["path"]
    assert api.seen["method"] == "GET"


def test_tasks_list_uses_config_node_when_none():
    api = _api(node="pve2")
    tasks_list(api)
    assert "/nodes/pve2/tasks" in api.seen["path"]


def test_tasks_list_uses_explicit_node():
    api = _api(node="pve")
    tasks_list(api, node="node1")
    assert "/nodes/node1/tasks" in api.seen["path"]


def test_tasks_list_includes_limit_in_query():
    api = _api()
    tasks_list(api, limit=25)
    assert "limit=25" in api.seen["path"]


def test_tasks_list_default_limit_is_50():
    api = _api()
    tasks_list(api)
    assert "limit=50" in api.seen["path"]


def test_tasks_list_errors_false_omits_errors_param():
    api = _api()
    tasks_list(api, errors=False)
    assert "errors" not in api.seen["path"]


def test_tasks_list_errors_true_sends_errors_1():
    api = _api()
    tasks_list(api, errors=True)
    assert "errors=1" in api.seen["path"]


def test_tasks_list_vmid_filter_included_when_set():
    api = _api()
    tasks_list(api, vmid="100")
    assert "vmid=100" in api.seen["path"]


def test_tasks_list_vmid_omitted_when_not_set():
    api = _api()
    tasks_list(api)
    assert "vmid" not in api.seen["path"]


def test_tasks_list_typefilter_included_when_set():
    api = _api()
    tasks_list(api, typefilter="vzstart")
    assert "typefilter=vzstart" in api.seen["path"]


def test_tasks_list_statusfilter_included_when_set():
    api = _api()
    tasks_list(api, statusfilter="error")
    assert "statusfilter=error" in api.seen["path"]


def test_tasks_list_is_node_scoped():
    api = _api()
    tasks_list(api)
    assert "/nodes/" in api.seen["path"]


def test_tasks_list_returns_list():
    api = _api()
    result = tasks_list(api)
    assert isinstance(result, list)


def test_tasks_list_rejects_zero_limit():
    api = _api()
    with pytest.raises(ProximoError):
        tasks_list(api, limit=0)


def test_tasks_list_rejects_negative_limit():
    api = _api()
    with pytest.raises(ProximoError):
        tasks_list(api, limit=-1)


def test_tasks_list_clamps_limit_at_1000():
    api = _api()
    tasks_list(api, limit=9999)
    assert "limit=1000" in api.seen["path"]


def test_tasks_list_accepts_limit_1000():
    api = _api()
    tasks_list(api, limit=1000)
    assert "limit=1000" in api.seen["path"]


def test_tasks_list_rejects_invalid_node():
    api = _api()
    with pytest.raises(ProximoError):
        tasks_list(api, node="bad/node")


# ---------------------------------------------------------------------------
# task_log — URL + param shapes
# ---------------------------------------------------------------------------

def test_task_log_uses_correct_path():
    api = _api()
    task_log(api, FAKE_UPID)
    assert "/nodes/pve/tasks/" in api.seen["path"]
    assert "/log" in api.seen["path"]
    assert api.seen["method"] == "GET"


def test_task_log_includes_upid_raw_in_path():
    """UPID contains colons — must NOT be percent-encoded in the path."""
    api = _api()
    task_log(api, FAKE_UPID)
    assert FAKE_UPID in api.seen["path"]
    assert "%3A" not in api.seen["path"]


def test_task_log_colons_not_percent_encoded():
    """Explicit: raw colon (pchar-valid per RFC 3986) must appear, not %3A."""
    api = _api()
    task_log(api, FAKE_UPID)
    path = api.seen["path"]
    assert ":" in path
    assert "UPID:pve" in path


def test_task_log_includes_start_and_limit():
    api = _api()
    task_log(api, FAKE_UPID, start=10, limit=20)
    assert "start=10" in api.seen["path"]
    assert "limit=20" in api.seen["path"]


def test_task_log_default_start_is_0():
    api = _api()
    task_log(api, FAKE_UPID)
    assert "start=0" in api.seen["path"]


def test_task_log_default_limit_is_50():
    api = _api()
    task_log(api, FAKE_UPID)
    assert "limit=50" in api.seen["path"]


def test_task_log_uses_config_node_when_none():
    api = _api(node="pve2")
    task_log(api, FAKE_UPID)
    assert "/nodes/pve2/tasks/" in api.seen["path"]


def test_task_log_uses_explicit_node():
    api = _api(node="pve")
    task_log(api, FAKE_UPID, node="pve3")
    assert "/nodes/pve3/tasks/" in api.seen["path"]


def test_task_log_is_node_scoped():
    api = _api()
    task_log(api, FAKE_UPID)
    assert "/nodes/" in api.seen["path"]


def test_task_log_returns_list():
    api = _api()
    result = task_log(api, FAKE_UPID)
    assert isinstance(result, list)


def test_task_log_rejects_invalid_upid():
    api = _api()
    with pytest.raises(ProximoError):
        task_log(api, "not-a-valid-upid")


def test_task_log_rejects_zero_limit():
    api = _api()
    with pytest.raises(ProximoError):
        task_log(api, FAKE_UPID, limit=0)


def test_task_log_clamps_limit_at_1000():
    api = _api()
    task_log(api, FAKE_UPID, limit=5000)
    assert "limit=1000" in api.seen["path"]


def test_task_log_rejects_invalid_node():
    api = _api()
    with pytest.raises(ProximoError):
        task_log(api, FAKE_UPID, node="bad node!")


# ---------------------------------------------------------------------------
# pools_list — cluster-scoped, no node prefix
# ---------------------------------------------------------------------------

def test_pools_list_uses_correct_path():
    api = _api()
    pools_list(api)
    assert api.seen["path"] == "/pools"
    assert api.seen["method"] == "GET"


def test_pools_list_is_not_node_scoped():
    api = _api()
    pools_list(api)
    assert "/nodes/" not in api.seen["path"]


def test_pools_list_returns_list():
    api = _api()
    result = pools_list(api)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# pool_get — cluster-scoped with poolid in path
# ---------------------------------------------------------------------------

def test_pool_get_uses_correct_path():
    api = _api()
    pool_get(api, "mypool")
    assert api.seen["path"] == "/pools/mypool"
    assert api.seen["method"] == "GET"


def test_pool_get_is_not_node_scoped():
    api = _api()
    pool_get(api, "mypool")
    assert "/nodes/" not in api.seen["path"]


def test_pool_get_returns_dict():
    """pool_get returns a dict (or {}) even when fake returns []."""
    api = _api()
    # Override _get to return a dict
    api._get = lambda path: {"poolid": "mypool", "members": []}
    result = pool_get(api, "mypool")
    assert isinstance(result, dict)


def test_pool_get_rejects_invalid_poolid():
    api = _api()
    with pytest.raises(ProximoError):
        pool_get(api, "bad/pool")


def test_pool_get_rejects_empty_poolid():
    api = _api()
    with pytest.raises(ProximoError):
        pool_get(api, "")


# ---------------------------------------------------------------------------
# task_stop — DELETE URL shape
# ---------------------------------------------------------------------------

def test_task_stop_uses_correct_method():
    api = _api()
    task_stop(api, FAKE_UPID)
    assert api.seen["method"] == "DELETE"


def test_task_stop_uses_correct_path():
    api = _api()
    task_stop(api, FAKE_UPID)
    assert f"/nodes/pve/tasks/{FAKE_UPID}" == api.seen["path"]


def test_task_stop_upid_raw_in_path_not_encoded():
    """UPID colons must NOT be percent-encoded in the DELETE path."""
    api = _api()
    task_stop(api, FAKE_UPID)
    assert FAKE_UPID in api.seen["path"]
    assert "%3A" not in api.seen["path"]


def test_task_stop_uses_config_node_when_none():
    api = _api(node="pve2")
    task_stop(api, FAKE_UPID)
    assert "/nodes/pve2/tasks/" in api.seen["path"]


def test_task_stop_uses_explicit_node():
    api = _api(node="pve")
    task_stop(api, FAKE_UPID, node="pve3")
    assert "/nodes/pve3/tasks/" in api.seen["path"]


def test_task_stop_is_node_scoped():
    api = _api()
    task_stop(api, FAKE_UPID)
    assert "/nodes/" in api.seen["path"]


def test_task_stop_returns_none():
    """task_stop DELETE returns null — synchronous cancellation signal, not a UPID."""
    api = _api()
    result = task_stop(api, FAKE_UPID)
    assert result is None


def test_task_stop_rejects_invalid_upid():
    api = _api()
    with pytest.raises(ProximoError):
        task_stop(api, "not-a-valid-upid")


def test_task_stop_rejects_invalid_node():
    api = _api()
    with pytest.raises(ProximoError):
        task_stop(api, FAKE_UPID, node="bad/node")


# ---------------------------------------------------------------------------
# pool_create — POST /pools with body
# ---------------------------------------------------------------------------

def test_pool_create_uses_post_to_pools():
    api = _api()
    pool_create(api, "mypool")
    assert api.seen["path"] == "/pools"
    assert api.seen["method"] == "POST"


def test_pool_create_is_not_node_scoped():
    api = _api()
    pool_create(api, "mypool")
    assert "/nodes/" not in api.seen["path"]


def test_pool_create_sends_poolid_in_body():
    """poolid is in the POST body (not the path) for the create endpoint."""
    api = _api()
    pool_create(api, "mypool")
    assert api.seen["data"]["poolid"] == "mypool"


def test_pool_create_poolid_not_in_path():
    """For create, the poolid is in the body — the path stays /pools, no /{poolid}."""
    api = _api()
    pool_create(api, "mypool")
    assert api.seen["path"] == "/pools"  # not /pools/mypool


def test_pool_create_sends_comment_when_provided():
    api = _api()
    pool_create(api, "mypool", comment="test pool")
    assert api.seen["data"]["comment"] == "test pool"


def test_pool_create_omits_comment_when_not_provided():
    api = _api()
    pool_create(api, "mypool")
    assert "comment" not in api.seen["data"]


def test_pool_create_returns_none():
    api = _api()
    result = pool_create(api, "mypool")
    assert result is None


def test_pool_create_rejects_invalid_poolid():
    api = _api()
    with pytest.raises(ProximoError):
        pool_create(api, "bad:pool")


# ---------------------------------------------------------------------------
# pool_update — PUT /pools/{poolid} body
# ---------------------------------------------------------------------------

def test_pool_update_uses_put():
    api = _api()
    pool_update(api, "mypool", vms="100")
    assert api.seen["method"] == "PUT"


def test_pool_update_uses_correct_path():
    api = _api()
    pool_update(api, "mypool", vms="100")
    assert api.seen["path"] == "/pools/mypool"


def test_pool_update_is_not_node_scoped():
    api = _api()
    pool_update(api, "mypool", vms="100")
    assert "/nodes/" not in api.seen["path"]


def test_pool_update_sends_vms_when_provided():
    api = _api()
    pool_update(api, "mypool", vms="100,200")
    assert api.seen["data"]["vms"] == "100,200"


def test_pool_update_sends_storage_when_provided():
    api = _api()
    pool_update(api, "mypool", storage="local,nfs")
    assert api.seen["data"]["storage"] == "local,nfs"


def test_pool_update_omits_vms_when_not_provided():
    api = _api()
    pool_update(api, "mypool", storage="local")
    assert "vms" not in api.seen["data"]


def test_pool_update_omits_storage_when_not_provided():
    api = _api()
    pool_update(api, "mypool", vms="100")
    assert "storage" not in api.seen["data"]


def test_pool_update_delete_false_omits_delete():
    api = _api()
    pool_update(api, "mypool", vms="100", delete=False)
    assert "delete" not in api.seen["data"]


def test_pool_update_delete_true_sends_delete_1():
    """delete=True must send integer 1, not boolean True."""
    api = _api()
    pool_update(api, "mypool", vms="100", delete=True)
    assert api.seen["data"]["delete"] == 1


def test_pool_update_returns_none():
    api = _api()
    result = pool_update(api, "mypool", vms="100")
    assert result is None


def test_pool_update_rejects_invalid_poolid():
    api = _api()
    with pytest.raises(ProximoError):
        pool_update(api, "bad/pool", vms="100")


# ---------------------------------------------------------------------------
# pool_delete — DELETE /pools/{poolid}
# ---------------------------------------------------------------------------

def test_pool_delete_uses_delete():
    api = _api()
    pool_delete(api, "mypool")
    assert api.seen["method"] == "DELETE"


def test_pool_delete_uses_correct_path():
    api = _api()
    pool_delete(api, "mypool")
    assert api.seen["path"] == "/pools/mypool"


def test_pool_delete_is_not_node_scoped():
    api = _api()
    pool_delete(api, "mypool")
    assert "/nodes/" not in api.seen["path"]


def test_pool_delete_returns_none():
    api = _api()
    result = pool_delete(api, "mypool")
    assert result is None


def test_pool_delete_rejects_invalid_poolid():
    api = _api()
    with pytest.raises(ProximoError):
        pool_delete(api, "")


def test_pool_delete_rejects_slash_in_poolid():
    api = _api()
    with pytest.raises(ProximoError):
        pool_delete(api, "my/pool")


# ---------------------------------------------------------------------------
# plan_task_stop — RISK_HIGH, blast radius honesty
# ---------------------------------------------------------------------------

def test_plan_task_stop_is_risk_high():
    p = plan_task_stop(FAKE_UPID)
    assert p.risk == RISK_HIGH


def test_plan_task_stop_action_string():
    p = plan_task_stop(FAKE_UPID)
    assert p.action == "pve_task_stop"


def test_plan_task_stop_target_is_upid():
    p = plan_task_stop(FAKE_UPID)
    assert p.target == FAKE_UPID


def test_plan_task_stop_blast_mentions_mid_flight():
    """Headline honesty: must call out mid-flight interruption."""
    p = plan_task_stop(FAKE_UPID)
    text = " ".join(p.blast_radius).lower()
    assert "mid-flight" in text or "mid flight" in text


def test_plan_task_stop_blast_mentions_backup_or_restore_or_migration():
    """Must name the operations that are most at risk."""
    p = plan_task_stop(FAKE_UPID)
    text = " ".join(p.blast_radius).lower()
    assert any(word in text for word in ("backup", "restore", "migration", "clone"))


def test_plan_task_stop_blast_mentions_inconsistent_state():
    """Must warn about inconsistent/partial state after interruption."""
    p = plan_task_stop(FAKE_UPID)
    text = " ".join(p.blast_radius).lower()
    assert "inconsistent" in text or "partial" in text


def test_plan_task_stop_blast_says_no_undo():
    """There is NO undo for an interrupted task — must say so."""
    p = plan_task_stop(FAKE_UPID)
    text = " ".join(p.blast_radius + [p.note]).lower()
    assert "no undo" in text or "cannot" in text or "not" in text


def test_plan_task_stop_risk_reasons_mention_mid_flight():
    p = plan_task_stop(FAKE_UPID)
    text = " ".join(p.risk_reasons).lower()
    assert "mid-flight" in text or "interrupt" in text or "backup" in text


def test_plan_task_stop_rejects_invalid_upid():
    with pytest.raises(ProximoError):
        plan_task_stop("not-a-upid")


def test_plan_task_stop_rejects_invalid_node():
    with pytest.raises(ProximoError):
        plan_task_stop(FAKE_UPID, node="bad node")


def test_plan_task_stop_accepts_explicit_node():
    p = plan_task_stop(FAKE_UPID, node="pve1")
    assert "pve1" in p.change


def test_plan_task_stop_includes_upid_in_change():
    p = plan_task_stop(FAKE_UPID)
    assert FAKE_UPID in p.change


# ---------------------------------------------------------------------------
# plan_pool_create — RISK_LOW, additive
# ---------------------------------------------------------------------------

def test_plan_pool_create_is_risk_low():
    p = plan_pool_create("mypool")
    assert p.risk == RISK_LOW


def test_plan_pool_create_action_string():
    p = plan_pool_create("mypool")
    assert p.action == "pve_pool_create"


def test_plan_pool_create_target_is_poolid():
    p = plan_pool_create("mypool")
    assert p.target == "mypool"


def test_plan_pool_create_blast_mentions_additive():
    p = plan_pool_create("mypool")
    text = " ".join(p.blast_radius).lower()
    assert "additive" in text or "empty" in text


def test_plan_pool_create_blast_mentions_undo_path():
    p = plan_pool_create("mypool")
    text = " ".join(p.blast_radius).lower()
    assert "pool_delete" in text or "delete" in text


def test_plan_pool_create_sends_comment_in_change_when_provided():
    p = plan_pool_create("mypool", comment="test pool")
    assert "test pool" in p.change


def test_plan_pool_create_rejects_invalid_poolid():
    with pytest.raises(ProximoError):
        plan_pool_create("bad:pool")


# ---------------------------------------------------------------------------
# plan_pool_update — RISK_MEDIUM, ACL scope
# ---------------------------------------------------------------------------

def test_plan_pool_update_is_risk_medium():
    p = plan_pool_update("mypool", vms="100")
    assert p.risk == RISK_MEDIUM


def test_plan_pool_update_action_string():
    p = plan_pool_update("mypool", vms="100")
    assert p.action == "pve_pool_update"


def test_plan_pool_update_target_is_poolid():
    p = plan_pool_update("mypool", vms="100")
    assert p.target == "mypool"


def test_plan_pool_update_blast_mentions_acl_scope():
    """Must warn about ACL scope change — who has access changes."""
    p = plan_pool_update("mypool", vms="100")
    text = " ".join(p.blast_radius).lower()
    assert "acl" in text or "access" in text or "permission" in text


def test_plan_pool_update_blast_says_guests_not_deleted():
    """Membership change ≠ guest deletion — must say so."""
    p = plan_pool_update("mypool", vms="100")
    text = " ".join(p.blast_radius).lower()
    assert "not deleted" in text or "not modified" in text or "only" in text


def test_plan_pool_update_delete_true_says_remove_in_change():
    p = plan_pool_update("mypool", vms="100", delete=True)
    assert "REMOVE" in p.change or "remove" in p.change.lower()


def test_plan_pool_update_delete_false_says_add_in_change():
    p = plan_pool_update("mypool", vms="100", delete=False)
    assert "ADD" in p.change or "add" in p.change.lower()


def test_plan_pool_update_rejects_invalid_poolid():
    with pytest.raises(ProximoError):
        plan_pool_update("bad/pool", vms="100")


# ---------------------------------------------------------------------------
# plan_pool_delete — RISK_MEDIUM, ACL orphan, empty-first requirement
# ---------------------------------------------------------------------------

def _pool_api():
    """Fake api for plan_pool_delete: empty ACL + empty pool → base RISK_MEDIUM, blast text intact."""
    from types import SimpleNamespace

    def _get(path):
        if path == "/access/acl":
            return []
        if path.startswith("/pools/"):
            return {"members": []}
        return {}

    return SimpleNamespace(config=SimpleNamespace(node="pve"), _get=_get)


def test_plan_pool_delete_is_risk_medium():
    p = plan_pool_delete(_pool_api(), "mypool")
    assert p.risk == RISK_MEDIUM


def test_plan_pool_delete_action_string():
    p = plan_pool_delete(_pool_api(), "mypool")
    assert p.action == "pve_pool_delete"


def test_plan_pool_delete_target_is_poolid():
    p = plan_pool_delete(_pool_api(), "mypool")
    assert p.target == "mypool"


def test_plan_pool_delete_blast_mentions_acl_orphan():
    """ACL grants on /pool/{poolid} are orphaned — must be explicit."""
    p = plan_pool_delete(_pool_api(), "mypool")
    text = " ".join(p.blast_radius).lower()
    assert "acl" in text or "orphan" in text or "permission" in text


def test_plan_pool_delete_blast_says_not_deletes_guests():
    """pool_delete does NOT delete member guests/storage — must not claim it does."""
    p = plan_pool_delete(_pool_api(), "mypool")
    text = " ".join(p.blast_radius).lower()
    assert "not delete" in text or "not deleted" in text or "does not delete" in text


def test_plan_pool_delete_blast_mentions_empty_prerequisite():
    """PVE requires pool to be empty first — must be noted."""
    p = plan_pool_delete(_pool_api(), "mypool")
    text = " ".join(p.blast_radius).lower()
    assert "empty" in text or "prerequisite" in text or "remove" in text


def test_plan_pool_delete_poolid_appears_in_blast():
    p = plan_pool_delete(_pool_api(), "mypool")
    text = " ".join(p.blast_radius)
    assert "mypool" in text


def test_plan_pool_delete_rejects_invalid_poolid():
    with pytest.raises(ProximoError):
        plan_pool_delete(None, "bad:pool")


def test_plan_pool_delete_rejects_empty_poolid():
    with pytest.raises(ProximoError):
        plan_pool_delete(None, "")


# ---------------------------------------------------------------------------
# Redteam-hardening regression tests (2026-06-08)
# ---------------------------------------------------------------------------

def test_pool_update_delete_with_no_members_is_refused():
    """delete=True with neither vms nor storage is an ambiguous footgun — must raise."""
    api = _api()
    with pytest.raises(ProximoError):
        pool_update(api, "mypool", delete=True)


def test_pool_update_add_with_no_members_is_allowed():
    """delete=False with no members is a harmless no-op add — not the footgun."""
    api = _api()
    pool_update(api, "mypool")  # should not raise
    assert api.seen["method"] == "PUT"


def test_plan_pool_update_delete_with_no_members_is_refused():
    """The dry-run must surface the footgun too, before any mutation."""
    with pytest.raises(ProximoError):
        plan_pool_update("mypool", delete=True)


def test_plan_pool_create_does_not_claim_fully_reversible():
    """Honesty: reversibility is conditional on a successful new-pool create."""
    plan = plan_pool_create("mypool")
    joined = " ".join(plan.risk_reasons).lower()
    assert "fully reversible" not in joined


def test_task_log_rejects_negative_start():
    api = _api()
    with pytest.raises(ProximoError):
        task_log(api, FAKE_UPID, start=-1)


def test_task_log_accepts_zero_start():
    api = _api()
    task_log(api, FAKE_UPID, start=0)
    assert "start=0" in api.seen["path"]


# ---------------------------------------------------------------------------
# Blast-radius coverage (rank 5): pool_delete reads the ACL and names the
# principals that lose access when /pool/<id> grants orphan. (Was PURE, zero reads.)
# ---------------------------------------------------------------------------

def test_plan_pool_delete_names_orphaned_acl_grants():
    from types import SimpleNamespace

    from proximo.planning import RISK_HIGH
    from proximo.tasks_pools import plan_pool_delete

    def _get(path):
        if path == "/access/acl":
            return [{"ugid": "alice@pve", "path": "/pool/web", "roleid": "PVEVMUser"},
                    {"ugid": "bob@pve", "path": "/", "roleid": "X"}]
        if path == "/pools/web":
            return {"members": []}
        return {}

    api = SimpleNamespace(config=SimpleNamespace(node="pve"), _get=_get)
    p = plan_pool_delete(api, "web")
    assert any(a["principal"] == "alice@pve" and a["path"] == "/pool/web" for a in p.affected)
    assert all(a["path"].startswith("/pool/web") for a in p.affected)   # only pool-path grants
    assert p.risk == RISK_HIGH                                          # real access break → escalated
    assert p.complete is True


def test_plan_pool_delete_empty_no_grants_is_medium():
    from types import SimpleNamespace

    from proximo.planning import RISK_MEDIUM
    from proximo.tasks_pools import plan_pool_delete

    def _get(path):
        if path == "/access/acl":
            return []
        if path == "/pools/web":
            return {"members": []}
        return {}

    api = SimpleNamespace(config=SimpleNamespace(node="pve"), _get=_get)
    p = plan_pool_delete(api, "web")
    assert p.affected == []
    assert p.risk == RISK_MEDIUM


def test_plan_pool_delete_acl_read_failure_is_high_and_incomplete():
    from types import SimpleNamespace

    from proximo.planning import RISK_HIGH
    from proximo.tasks_pools import plan_pool_delete

    def _get(path):
        if path == "/access/acl":
            raise RuntimeError("acl unavailable")
        if path == "/pools/web":
            return {"members": []}
        return {}

    api = SimpleNamespace(config=SimpleNamespace(node="pve"), _get=_get)
    p = plan_pool_delete(api, "web")
    assert p.complete is False
    assert p.risk == RISK_HIGH


def test_plan_pool_delete_member_read_failure_is_high_and_incomplete():
    """The SEPARATE member read failing (ACL read OK) must still escalate to HIGH + incomplete."""
    from types import SimpleNamespace

    from proximo.planning import RISK_HIGH
    from proximo.tasks_pools import plan_pool_delete

    def _get(path):
        if path == "/access/acl":
            return []                       # ACL read succeeds, empty
        if path == "/pools/web":
            raise RuntimeError("pools unavailable")
        return {}

    api = SimpleNamespace(config=SimpleNamespace(node="pve"), _get=_get)
    p = plan_pool_delete(api, "web")
    assert p.complete is False
    assert p.risk == RISK_HIGH
