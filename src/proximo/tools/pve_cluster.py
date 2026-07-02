"""PVE cluster & HA, task control + resource pools, and storage administration (storage.cfg CRUD).

Split out of proximo.server (2026-07-02) — see proximo/server.py's module
docstring for the funnel these wrappers depend on.
"""
from __future__ import annotations

import proximo.server as _proximo_server
from proximo.cluster_ops import (
    cluster_resources,
    cluster_status,
    guest_migrate,
    ha_groups_list,
    ha_resource_add,
    ha_resource_remove,
    ha_resources_list,
    ha_rule_create,
    ha_rule_delete,
    ha_rule_update,
    ha_rules_list,
    plan_ha_resource_add,
    plan_ha_resource_remove,
    plan_ha_rule_create,
    plan_ha_rule_delete,
    plan_ha_rule_update,
    plan_migrate,
)
from proximo.server import (
    _audited,
    _plan,
    tool,
)
from proximo.storage_admin import (
    plan_storage_create,
    plan_storage_delete,
    plan_storage_update,
    storage_config_get,
    storage_config_list,
    storage_create,
    storage_delete,
    storage_update,
)
from proximo.tasks_pools import (
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
    wait_for_task,
)

# --- Cluster & HA (REST API, read) ---

@tool()
def pve_cluster_status() -> list[dict]:
    """Overall cluster status — nodes, quorum, version (read)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_cluster_status", "cluster/status", lambda: cluster_status(api))


@tool()
def pve_cluster_resources(resource_type: str | None = None) -> list[dict]:
    """List all resources across the cluster (VMs, nodes, storage, SDN).
    resource_type: optional filter — 'vm', 'storage', 'node', or 'sdn' (read)."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/resources/{resource_type or 'all'}"
    return _audited("pve_cluster_resources", tgt,
                    lambda: cluster_resources(api, resource_type))


@tool()
def pve_ha_groups_list() -> list[dict]:
    """List all HA resource groups (read). PVE-8 only — PVE 9 migrated groups to rules
    (use pve_ha_rules_list); on PVE 9 this raises a clear error pointing there."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_ha_groups_list", "cluster/ha/groups", lambda: ha_groups_list(api))


@tool()
def pve_ha_rules_list() -> list[dict]:
    """List HA rules (read) — the PVE 9 replacement for HA groups."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_ha_rules_list", "cluster/ha/rules", lambda: ha_rules_list(api))


@tool()
def pve_ha_resources_list() -> list[dict]:
    """List all HA resources (managed guests) (read)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_ha_resources_list", "cluster/ha/resources",
                    lambda: ha_resources_list(api))


# --- Cluster & HA (REST API, MUTATION — confirm-gated) ---

@tool()
def pve_guest_migrate(
    vmid: str, target: str, kind: str = "lxc", node: str | None = None,
    online: bool = False, confirm: bool = False,
) -> dict:
    """MUTATION: migrate a guest to a different node. Dry-run by default — the PLAN shows the
    guest's live state, the source→target, and the honest blast radius (LXC 'online' is
    stop→move→start, NOT zero-downtime; QEMU live migration requires shared storage).
    confirm=True to execute. Async — returns a task UPID.
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"{kind}/{vmid}->{target}"
    plan = _plan("pve_guest_migrate", tgt,
                 lambda: plan_migrate(api, vmid, target, kind, node, online))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_guest_migrate", tgt,
                    lambda: guest_migrate(api, vmid, target, kind, node, online),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@tool()
def pve_ha_resource_add(
    vmid: str, kind: str = "lxc", group: str | None = None,
    state: str | None = None, max_restart: int | None = None,
    max_relocate: int | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: add a guest to HA management. Dry-run by default — the PLAN shows the SID,
    group, initial state, and blast radius (state='stopped' is HIGH: CRM will stop the guest).
    confirm=True to execute. Synchronous (pmxcfs config write; CRM enforces state asynchronously).
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"ha:{kind}/{vmid}"
    plan = _plan("pve_ha_resource_add", tgt,
                 lambda: plan_ha_resource_add(vmid, kind, group, state, max_restart, max_relocate))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_ha_resource_add", tgt,
                    lambda: ha_resource_add(api, vmid, kind, group, state, max_restart, max_relocate),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_ha_resource_remove(vmid: str, kind: str = "lxc", confirm: bool = False) -> dict:
    """MUTATION: remove a guest from HA management. Dry-run by default — the PLAN shows the SID
    and that this loses automated failover protection (guest itself is NOT stopped).
    confirm=True to execute. Synchronous (pmxcfs config write).
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"ha:{kind}/{vmid}"
    plan = _plan("pve_ha_resource_remove", tgt,
                 lambda: plan_ha_resource_remove(vmid, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_ha_resource_remove", tgt,
                    lambda: ha_resource_remove(api, vmid, kind),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_ha_rule_create(
    rule: str, rule_type: str, resources: str, comment: str | None = None,
    disable: bool = False, nodes: str | None = None, strict: bool = False,
    affinity: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: create an HA rule (the PVE 9 replacement for HA groups). Dry-run by default — the
    PLAN shows the rule type, resources, and placement effect. `rule_type` is 'node-affinity'
    (needs `nodes`; optional `strict`) or 'resource-affinity' (needs `affinity` positive|negative).
    confirm=True to execute. Synchronous (pmxcfs config write). RISK_MEDIUM — constrains CRM placement.
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"ha/rules/{rule}"
    plan = _plan("pve_ha_rule_create", tgt,
                 lambda: plan_ha_rule_create(rule, rule_type, resources, nodes, strict, affinity, disable))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_ha_rule_create", tgt,
                    lambda: ha_rule_create(api, rule, rule_type, resources, comment, disable,
                                           nodes, strict, affinity),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_ha_rule_update(
    rule: str, comment: str | None = None, disable: bool | None = None,
    resources: str | None = None, rule_type: str | None = None, nodes: str | None = None,
    strict: bool | None = None, affinity: str | None = None,
    delete: list[str] | None = None, digest: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: update an HA rule. Dry-run by default — the PLAN shows the current rule and the
    fields being changed. `delete` unsets keys. confirm=True to execute. Synchronous.
    RISK_MEDIUM — may trigger CRM migration of affected resources.
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"ha/rules/{rule}"
    plan = _plan("pve_ha_rule_update", tgt,
                 lambda: plan_ha_rule_update(api, rule, comment, disable, resources, rule_type,
                                             nodes, strict, affinity, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_ha_rule_update", tgt,
                    lambda: ha_rule_update(api, rule, comment, disable, resources, rule_type,
                                           nodes, strict, affinity, delete, digest),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_ha_rule_delete(rule: str, confirm: bool = False) -> dict:
    """MUTATION: delete an HA rule. Dry-run by default — the PLAN shows the current rule and that
    its resources lose this placement constraint (CRM may migrate them). confirm=True to execute.
    Synchronous. RISK_MEDIUM.
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"ha/rules/{rule}"
    plan = _plan("pve_ha_rule_delete", tgt, lambda: plan_ha_rule_delete(api, rule))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_ha_rule_delete", tgt,
                    lambda: ha_rule_delete(api, rule),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- Task control + resource pools (read) ---

@tool()
def pve_tasks_list(node: str | None = None, limit: int = 50, errors: bool = False,
                   vmid: str | None = None, typefilter: str | None = None,
                   statusfilter: str | None = None) -> list[dict]:
    """List recent tasks on a node (read). limit 1-1000 (clamped)."""
    cfg, api, _, _ = _proximo_server._svc()
    return _audited("pve_tasks_list", node or cfg.node,
                    lambda: tasks_list(api, node, limit, errors, vmid, typefilter, statusfilter))


@tool()
def pve_task_log(upid: str, node: str | None = None, start: int = 0,
                 limit: int = 50) -> list[dict]:
    """Retrieve the log lines for a task (read)."""
    cfg, api, _, _ = _proximo_server._svc()
    return _audited("pve_task_log", upid, lambda: task_log(api, upid, node, start, limit))


@tool()
def pve_task_wait(upid: str, node: str | None = None, timeout: int = 120,
                  interval: int = 2) -> dict:
    """Block until an async Proxmox task reaches a terminal state — or the timeout — then report the
    outcome (read). The ergonomic complement to the submit-an-async-op tools (migrate / backup /
    restore / clone / rollback / snapshot + guest create) that return a UPID: wait for completion
    without hand-rolling a pve_task_status poll loop.

    Returns {upid, finished, succeeded, status, exitstatus, timed_out, polls}. `succeeded` is
    fail-closed (finished AND exitstatus == "OK"); a failed or timed-out task is reported, not raised.
    timeout is clamped 1..600s, interval 1..60s. Use pve_task_log for the full log.

    (Proximo's native UPID model — NOT the MCP Tasks protocol, which was removed from the spec.)"""
    _, api, _, _ = _proximo_server._svc()
    t = max(1, min(int(timeout), 600))
    iv = max(1, min(int(interval), 60))

    def _do() -> dict:
        r = wait_for_task(lambda: api.task_status(upid, node), timeout=t, interval=iv)
        r["upid"] = upid
        return r

    return _audited("pve_task_wait", upid, _do)


@tool()
def pve_pools_list() -> list[dict]:
    """List all resource pools (cluster-scoped) (read)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_pools_list", "cluster/pools", lambda: pools_list(api))


@tool()
def pve_pool_get(poolid: str) -> dict:
    """Get a resource pool's config and member list (read)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_pool_get", f"pool/{poolid}", lambda: pool_get(api, poolid))


# --- Task control + resource pools (mutation) ---

@tool()
def pve_task_stop(upid: str, node: str | None = None, confirm: bool = False) -> dict:
    """MUTATION (HIGH): stop (cancel) a running task. Dry-run by default — the PLAN warns that
    stopping a backup/restore/migration/clone mid-flight can leave the target inconsistent, with
    NO undo. confirm=True to execute. Synchronous cancellation signal (returns null)."""
    _, api, _, _ = _proximo_server._svc()
    plan = _plan("pve_task_stop", upid, lambda: plan_task_stop(upid, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_task_stop", upid,
                    lambda: task_stop(api, upid, node),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_pool_create(poolid: str, comment: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create an (empty) resource pool. Dry-run by default (PLAN = additive, LOW).
    confirm=True to execute. Synchronous."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"pool/{poolid}"
    plan = _plan("pve_pool_create", tgt, lambda: plan_pool_create(poolid, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_pool_create", tgt,
                    lambda: pool_create(api, poolid, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_pool_update(poolid: str, vms: str | None = None, storage: str | None = None,
                    delete: bool = False, confirm: bool = False) -> dict:
    """MUTATION: add (delete=False) or remove (delete=True) pool members. Dry-run by default —
    the PLAN notes membership re-scopes ACL coverage. confirm=True to execute. Synchronous.
    delete=True with no vms/storage is refused (ambiguous)."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"pool/{poolid}"
    plan = _plan("pve_pool_update", tgt,
                 lambda: plan_pool_update(poolid, vms, storage, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_pool_update", tgt,
                    lambda: pool_update(api, poolid, vms, storage, delete),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_pool_delete(poolid: str, confirm: bool = False) -> dict:
    """MUTATION: delete a resource pool. Dry-run by default — the PLAN warns ACLs on /pool/{poolid}
    are orphaned and the pool must be empty first (members are NOT deleted). confirm=True to
    execute. Synchronous."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"pool/{poolid}"
    plan = _plan("pve_pool_delete", tgt, lambda: plan_pool_delete(api, poolid))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_pool_delete", tgt,
                    lambda: pool_delete(api, poolid),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- Storage administration (storage.cfg CRUD) ---

@tool()
def pve_storage_config_list() -> list[dict]:
    """List the cluster storage definitions (storage.cfg) (read)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_storage_config_list", "cluster/storage",
                    lambda: storage_config_list(api))


@tool()
def pve_storage_config_get(storage: str) -> dict:
    """Get one storage definition (read)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_storage_config_get", f"storage/{storage}",
                    lambda: storage_config_get(api, storage))


@tool()
def pve_storage_create(storage: str, storage_type: str, content: str | None = None,
                       path: str | None = None, server: str | None = None,
                       export: str | None = None, nodes: str | None = None,
                       disable: bool = False, shared: bool = False,
                       confirm: bool = False) -> dict:
    """MUTATION: define a new storage (storage.cfg). Dry-run by default. confirm=True to execute."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"storage/{storage}"
    plan = _plan("pve_storage_create", tgt,
                 lambda: plan_storage_create(storage, storage_type, content, path, server,
                                             export, nodes, disable, shared))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_storage_create", tgt,
                    lambda: storage_create(api, storage, storage_type, content, path,
                                          server, export, nodes, disable, shared),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_storage_update(storage: str, content: str | None = None, nodes: str | None = None,
                       disable: bool | None = None, shared: bool | None = None,
                       delete: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: update a storage definition. Dry-run by default (disable=True warns guests lose
    disk access). confirm=True to execute."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"storage/{storage}"
    plan = _plan("pve_storage_update", tgt,
                 lambda: plan_storage_update(api, storage, content, nodes, disable, shared, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_storage_update", tgt,
                    lambda: storage_update(api, storage, content, nodes, disable, shared, delete),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_storage_delete(storage: str, confirm: bool = False) -> dict:
    """MUTATION (HIGH): remove a storage definition cluster-wide. Dry-run by default — the PLAN
    warns guest disks/backups living only there become inaccessible (data not erased). confirm=True."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"storage/{storage}"
    plan = _plan("pve_storage_delete", tgt, lambda: plan_storage_delete(api, storage))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_storage_delete", tgt,
                    lambda: storage_delete(api, storage),
                    mutation=True, outcome="ok", detail={"confirmed": True})
