"""PVE firewall: rules, options, aliases, IPSets, and security groups (read+mutation).

Split out of proximo.server (2026-07-02) — see proximo/server.py's module
docstring for the funnel these wrappers depend on.
"""
from __future__ import annotations

import proximo.server as _proximo_server
from proximo.firewall import (
    alias_create,
    alias_delete,
    alias_list,
    alias_update,
    firewall_options_get,
    firewall_options_set,
    firewall_rule_add,
    firewall_rule_remove,
    firewall_rule_update,
    firewall_rules_list,
    firewall_set_enabled,
    ipset_create,
    ipset_delete,
    ipset_entry_add,
    ipset_entry_remove,
    ipset_list,
    plan_alias_create,
    plan_alias_delete,
    plan_alias_update,
    plan_firewall_options_set,
    plan_firewall_rule_add,
    plan_firewall_rule_remove,
    plan_firewall_rule_update,
    plan_firewall_set_enabled,
    plan_ipset_create,
    plan_ipset_delete,
    plan_ipset_entry_add,
    plan_ipset_entry_remove,
    plan_security_group_create,
    plan_security_group_delete,
    security_group_create,
    security_group_delete,
    security_groups_list,
)
from proximo.server import (
    _audited,
    _plan,
    tool,
)

# --- Firewall (REST API, read) ---

@tool()
def pve_firewall_rules_list(
    scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
) -> list[dict]:
    """List all firewall rules for the given scope (cluster/node/guest) (read)."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"firewall/{scope}"
    return _audited("pve_firewall_rules_list", tgt,
                    lambda: firewall_rules_list(api, scope, node, vmid, kind))


@tool()
def pve_firewall_options_get(
    scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
) -> dict:
    """Get firewall options (enable flag, policy, log rate, …) for the given scope (read)."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"firewall/{scope}/options"
    return _audited("pve_firewall_options_get", tgt,
                    lambda: firewall_options_get(api, scope, node, vmid, kind))


@tool()
def pve_security_groups_list() -> list[dict]:
    """List cluster-wide firewall security groups (read)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_security_groups_list", "firewall/cluster/groups",
                    lambda: security_groups_list(api))


@tool()
def pve_ipset_list(
    scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
) -> list[dict]:
    """List IP sets for the given scope (read). Scope = cluster or guest only —
    the PVE API has no node-scope ipsets (node firewall = options/rules/log)."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"firewall/{scope}/ipset"
    return _audited("pve_ipset_list", tgt,
                    lambda: ipset_list(api, scope, node, vmid, kind))


# --- Firewall (REST API, MUTATION — confirm-gated) ---

@tool()
def pve_firewall_rule_add(
    action: str, direction: str = "in", scope: str = "cluster",
    node: str | None = None, vmid: str | None = None, kind: str | None = None,
    source: str | None = None, dest: str | None = None, proto: str | None = None,
    dport: str | None = None, sport: str | None = None, comment: str | None = None,
    enable: bool = True, confirm: bool = False,
) -> dict:
    """MUTATION: add a new firewall rule. Dry-run by default — the PLAN shows scope, direction,
    action, and key address/port fields. Re-call with confirm=True to execute. Synchronous.

    WARNING: a misplaced DROP/REJECT can cause a connectivity lockout.
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"firewall/{scope}/rules"
    plan = _plan("pve_firewall_rule_add", tgt,
                 lambda: plan_firewall_rule_add(action, direction, scope, node, vmid, kind,
                                                source, dest, dport, proto))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_rule_add", tgt,
                    lambda: firewall_rule_add(api, action, direction, scope, node,
                                             vmid, kind, source, dest, proto, dport,
                                             sport, comment, enable),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_firewall_rule_remove(
    pos: int, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: delete a firewall rule by position. Dry-run by default — the PLAN shows the rule
    at that position. Positions SHIFT after inserts/deletes — verify before confirming. Synchronous.
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"firewall/{scope}/rules/{pos}"
    plan = _plan("pve_firewall_rule_remove", tgt,
                 lambda: plan_firewall_rule_remove(api, pos, scope, node, vmid, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_rule_remove", tgt,
                    lambda: firewall_rule_remove(api, pos, scope, node, vmid, kind),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_firewall_rule_update(
    pos: int, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
    action: str | None = None, direction: str | None = None,
    source: str | None = None, dest: str | None = None, proto: str | None = None,
    dport: str | None = None, sport: str | None = None, comment: str | None = None,
    enable: bool | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: update an existing firewall rule at position `pos`. Dry-run by default — the PLAN
    shows the rule's current state and the fields being changed. Synchronous.
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"firewall/{scope}/rules/{pos}"
    # Build a dict of only the non-None update fields (matches plan_firewall_rule_update **new_fields).
    changes: dict = {}
    if action is not None:
        changes["action"] = action
    if direction is not None:
        changes["direction"] = direction
    if source is not None:
        changes["source"] = source
    if dest is not None:
        changes["dest"] = dest
    if proto is not None:
        changes["proto"] = proto
    if dport is not None:
        changes["dport"] = dport
    if sport is not None:
        changes["sport"] = sport
    if comment is not None:
        changes["comment"] = comment
    if enable is not None:
        changes["enable"] = enable
    plan = _plan("pve_firewall_rule_update", tgt,
                 lambda: plan_firewall_rule_update(api, pos, scope, node, vmid, kind, **changes))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_rule_update", tgt,
                    lambda: firewall_rule_update(api, pos, scope, node, vmid, kind, **changes),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_firewall_set_enabled(
    enabled: bool, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION (HIGH RISK): toggle the firewall on or off for the given scope. Dry-run by default.
    RISK_HIGH both directions: enabling may instantly lock you out (default-DROP, no ACCEPT for 22/8006);
    disabling strips all protection. Cluster scope = master kill-switch. Synchronous.
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"firewall/{scope}/options"
    plan = _plan("pve_firewall_set_enabled", tgt,
                 lambda: plan_firewall_set_enabled(api, enabled, scope, node, vmid, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_set_enabled", tgt,
                    lambda: firewall_set_enabled(api, enabled, scope, node, vmid, kind),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_firewall_alias_list(
    scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
) -> list[dict]:
    """List firewall aliases (named CIDRs) for the given scope (read). Scope = cluster
    or guest only — the PVE API has no node-scope aliases (node firewall = options/rules/log)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_firewall_alias_list", f"firewall/{scope}/aliases",
                    lambda: alias_list(api, scope, node, vmid, kind))


@tool()
def pve_firewall_alias_create(
    name: str, cidr: str, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None, comment: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: create a firewall alias (named CIDR). Dry-run by default — the PLAN shows the
    name, CIDR, and scope. Re-call with confirm=True to execute. Passive until a rule references it.
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"firewall/{scope}/aliases/{name}"
    plan = _plan("pve_firewall_alias_create", tgt,
                 lambda: plan_alias_create(name, cidr, scope, node, vmid, kind, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_alias_create", tgt,
                    lambda: alias_create(api, name, cidr, scope, node, vmid, kind, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_firewall_alias_update(
    name: str, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
    cidr: str | None = None, comment: str | None = None,
    rename: str | None = None, digest: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: update a firewall alias. Dry-run by default — the PLAN shows the current alias and
    the fields being changed. Changing the CIDR silently alters every referencing rule's match set.
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"firewall/{scope}/aliases/{name}"
    plan = _plan("pve_firewall_alias_update", tgt,
                 lambda: plan_alias_update(api, name, scope, node, vmid, kind, cidr, comment, rename))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_alias_update", tgt,
                    lambda: alias_update(api, name, scope, node, vmid, kind, cidr, comment, rename, digest),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_firewall_alias_delete(
    name: str, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
    digest: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: delete a firewall alias. Dry-run by default — the PLAN shows the current alias.
    PVE refuses while any rule still references the alias. No UNDO: re-create to revert.
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"firewall/{scope}/aliases/{name}"
    plan = _plan("pve_firewall_alias_delete", tgt,
                 lambda: plan_alias_delete(api, name, scope, node, vmid, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_alias_delete", tgt,
                    lambda: alias_delete(api, name, scope, node, vmid, kind, digest),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_firewall_ipset_create(
    name: str, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None, comment: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: create an empty IP set. Dry-run by default — the PLAN shows the name and scope.
    Passive until a rule references it as '+name' and entries are added.
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"firewall/{scope}/ipset/{name}"
    plan = _plan("pve_firewall_ipset_create", tgt,
                 lambda: plan_ipset_create(name, scope, node, vmid, kind, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_ipset_create", tgt,
                    lambda: ipset_create(api, name, scope, node, vmid, kind, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_firewall_ipset_delete(
    name: str, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
    force: bool = False, confirm: bool = False,
) -> dict:
    """MUTATION: delete an IP set. Dry-run by default — the PLAN shows member count and the
    force semantics. force=True WIPES all members; PVE refuses while a rule references the set.
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"firewall/{scope}/ipset/{name}"
    plan = _plan("pve_firewall_ipset_delete", tgt,
                 lambda: plan_ipset_delete(api, name, scope, node, vmid, kind, force))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_ipset_delete", tgt,
                    lambda: ipset_delete(api, name, scope, node, vmid, kind, force),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_firewall_ipset_entry_add(
    name: str, cidr: str, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
    comment: str | None = None, nomatch: bool = False, confirm: bool = False,
) -> dict:
    """MUTATION: add an IP/Network entry to an IP set. Dry-run by default — the PLAN shows the
    entry and warns it changes every referencing rule's match set. nomatch=True = exclusion.
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"firewall/{scope}/ipset/{name}"
    plan = _plan("pve_firewall_ipset_entry_add", tgt,
                 lambda: plan_ipset_entry_add(name, cidr, scope, node, vmid, kind, comment, nomatch))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_ipset_entry_add", tgt,
                    lambda: ipset_entry_add(api, name, cidr, scope, node, vmid, kind, comment, nomatch),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_firewall_ipset_entry_remove(
    name: str, cidr: str, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
    digest: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: remove an IP/Network entry from an IP set. Dry-run by default — the PLAN shows the
    entry and warns it changes every referencing rule's match set (may open or close access).
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"firewall/{scope}/ipset/{name}"
    plan = _plan("pve_firewall_ipset_entry_remove", tgt,
                 lambda: plan_ipset_entry_remove(name, cidr, scope, node, vmid, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_ipset_entry_remove", tgt,
                    lambda: ipset_entry_remove(api, name, cidr, scope, node, vmid, kind, digest),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_firewall_security_group_create(
    group: str, comment: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: create an empty cluster security group. Dry-run by default — the PLAN shows the
    name. Passive until rules are added and a rule references it (type=group).
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"firewall/cluster/groups/{group}"
    plan = _plan("pve_firewall_security_group_create", tgt,
                 lambda: plan_security_group_create(group, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_security_group_create", tgt,
                    lambda: security_group_create(api, group, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_firewall_security_group_delete(group: str, confirm: bool = False) -> dict:
    """MUTATION: delete a cluster security group. Dry-run by default — the PLAN shows how many rules
    the group holds. PVE refuses while the group is non-empty or still referenced by a rule.
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"firewall/cluster/groups/{group}"
    plan = _plan("pve_firewall_security_group_delete", tgt,
                 lambda: plan_security_group_delete(api, group))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_security_group_delete", tgt,
                    lambda: security_group_delete(api, group),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_firewall_options_set(
    scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
    options: dict | None = None, delete: list[str] | None = None,
    digest: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: set firewall options for a scope (policy_in/out, log levels, ebtables, log_ratelimit,
    ...). `options` is a key->value bag; `delete` unsets keys. Dry-run by default — the PLAN shows the
    current values and flags lockout risk. RISK_HIGH when enabling the firewall or changing a policy.
    """
    _, api, _, _ = _proximo_server._svc()
    tgt = f"firewall/{scope}/options"
    plan = _plan("pve_firewall_options_set", tgt,
                 lambda: plan_firewall_options_set(api, scope, node, vmid, kind, options, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_options_set", tgt,
                    lambda: firewall_options_set(api, scope, node, vmid, kind, options, delete, digest),
                    mutation=True, outcome="ok", detail={"confirmed": True})
