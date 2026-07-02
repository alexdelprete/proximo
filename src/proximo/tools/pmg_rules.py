"""PMG ruledb rules engine: who/what/when/action group + object CRUD, rule CRUD, and rule<->object attach/detach.

Split out of proximo.server (2026-07-02) — see proximo/server.py's module
docstring for the funnel these wrappers depend on.
"""
from __future__ import annotations

import proximo.server as _proximo_server
from proximo.pmg import (
    action_bcc_create as pmg_action_bcc_create_op,
)
from proximo.pmg import (
    action_bcc_update as pmg_action_bcc_update_op,
)
from proximo.pmg import (
    action_delete as pmg_action_delete_op,
)
from proximo.pmg import (
    action_disclaimer_create as pmg_action_disclaimer_create_op,
)
from proximo.pmg import (
    action_disclaimer_update as pmg_action_disclaimer_update_op,
)
from proximo.pmg import (
    action_field_create as pmg_action_field_create_op,
)
from proximo.pmg import (
    action_field_update as pmg_action_field_update_op,
)
from proximo.pmg import (
    action_notification_create as pmg_action_notification_create_op,
)
from proximo.pmg import (
    action_notification_update as pmg_action_notification_update_op,
)
from proximo.pmg import (
    action_removeattachments_create as pmg_action_removeattachments_create_op,
)
from proximo.pmg import (
    action_removeattachments_update as pmg_action_removeattachments_update_op,
)
from proximo.pmg import (
    plan_action_bcc_create as pmg_plan_action_bcc_create,
)
from proximo.pmg import (
    plan_action_bcc_update as pmg_plan_action_bcc_update,
)
from proximo.pmg import (
    plan_action_delete as pmg_plan_action_delete,
)
from proximo.pmg import (
    plan_action_disclaimer_create as pmg_plan_action_disclaimer_create,
)
from proximo.pmg import (
    plan_action_disclaimer_update as pmg_plan_action_disclaimer_update,
)
from proximo.pmg import (
    plan_action_field_create as pmg_plan_action_field_create,
)
from proximo.pmg import (
    plan_action_field_update as pmg_plan_action_field_update,
)
from proximo.pmg import (
    plan_action_notification_create as pmg_plan_action_notification_create,
)
from proximo.pmg import (
    plan_action_notification_update as pmg_plan_action_notification_update,
)
from proximo.pmg import (
    plan_action_removeattachments_create as pmg_plan_action_removeattachments_create,
)
from proximo.pmg import (
    plan_action_removeattachments_update as pmg_plan_action_removeattachments_update,
)
from proximo.pmg import (
    plan_ruledb_rule_action_attach as pmg_plan_ruledb_rule_action_attach,
)
from proximo.pmg import (
    plan_ruledb_rule_action_detach as pmg_plan_ruledb_rule_action_detach,
)
from proximo.pmg import (
    plan_ruledb_rule_create as pmg_plan_ruledb_rule_create,
)
from proximo.pmg import (
    plan_ruledb_rule_delete as pmg_plan_ruledb_rule_delete,
)
from proximo.pmg import (
    plan_ruledb_rule_from_attach as pmg_plan_ruledb_rule_from_attach,
)
from proximo.pmg import (
    plan_ruledb_rule_from_detach as pmg_plan_ruledb_rule_from_detach,
)
from proximo.pmg import (
    plan_ruledb_rule_to_attach as pmg_plan_ruledb_rule_to_attach,
)
from proximo.pmg import (
    plan_ruledb_rule_to_detach as pmg_plan_ruledb_rule_to_detach,
)
from proximo.pmg import (
    plan_ruledb_rule_update as pmg_plan_ruledb_rule_update,
)
from proximo.pmg import (
    plan_ruledb_rule_what_attach as pmg_plan_ruledb_rule_what_attach,
)
from proximo.pmg import (
    plan_ruledb_rule_what_detach as pmg_plan_ruledb_rule_what_detach,
)
from proximo.pmg import (
    plan_ruledb_rule_when_attach as pmg_plan_ruledb_rule_when_attach,
)
from proximo.pmg import (
    plan_ruledb_rule_when_detach as pmg_plan_ruledb_rule_when_detach,
)
from proximo.pmg import (
    plan_what_group_create as pmg_plan_what_group_create,
)
from proximo.pmg import (
    plan_what_group_delete as pmg_plan_what_group_delete,
)
from proximo.pmg import (
    plan_what_group_update as pmg_plan_what_group_update,
)
from proximo.pmg import (
    plan_what_object_add as pmg_plan_what_object_add,
)
from proximo.pmg import (
    plan_what_object_delete as pmg_plan_what_object_delete,
)
from proximo.pmg import (
    plan_what_object_update as pmg_plan_what_object_update,
)
from proximo.pmg import (
    plan_when_group_create as pmg_plan_when_group_create,
)
from proximo.pmg import (
    plan_when_group_delete as pmg_plan_when_group_delete,
)
from proximo.pmg import (
    plan_when_group_update as pmg_plan_when_group_update,
)
from proximo.pmg import (
    plan_when_object_add as pmg_plan_when_object_add,
)
from proximo.pmg import (
    plan_when_object_delete as pmg_plan_when_object_delete,
)
from proximo.pmg import (
    plan_when_object_update as pmg_plan_when_object_update,
)
from proximo.pmg import (
    plan_who_group_create as pmg_plan_who_group_create,
)
from proximo.pmg import (
    plan_who_group_delete as pmg_plan_who_group_delete,
)
from proximo.pmg import (
    plan_who_group_update as pmg_plan_who_group_update,
)
from proximo.pmg import (
    plan_who_object_add as pmg_plan_who_object_add,
)
from proximo.pmg import (
    plan_who_object_delete as pmg_plan_who_object_delete,
)
from proximo.pmg import (
    plan_who_object_update as pmg_plan_who_object_update,
)
from proximo.pmg import (
    ruledb_rule_action_attach as pmg_ruledb_rule_action_attach_op,
)
from proximo.pmg import (
    ruledb_rule_action_detach as pmg_ruledb_rule_action_detach_op,
)
from proximo.pmg import (
    ruledb_rule_create as pmg_ruledb_rule_create_op,
)
from proximo.pmg import (
    ruledb_rule_delete as pmg_ruledb_rule_delete_op,
)
from proximo.pmg import (
    ruledb_rule_from_attach as pmg_ruledb_rule_from_attach_op,
)
from proximo.pmg import (
    ruledb_rule_from_detach as pmg_ruledb_rule_from_detach_op,
)
from proximo.pmg import (
    ruledb_rule_to_attach as pmg_ruledb_rule_to_attach_op,
)
from proximo.pmg import (
    ruledb_rule_to_detach as pmg_ruledb_rule_to_detach_op,
)
from proximo.pmg import (
    ruledb_rule_update as pmg_ruledb_rule_update_op,
)
from proximo.pmg import (
    ruledb_rule_what_attach as pmg_ruledb_rule_what_attach_op,
)
from proximo.pmg import (
    ruledb_rule_what_detach as pmg_ruledb_rule_what_detach_op,
)
from proximo.pmg import (
    ruledb_rule_when_attach as pmg_ruledb_rule_when_attach_op,
)
from proximo.pmg import (
    ruledb_rule_when_detach as pmg_ruledb_rule_when_detach_op,
)
from proximo.pmg import (
    what_group_create as pmg_what_group_create_op,
)
from proximo.pmg import (
    what_group_delete as pmg_what_group_delete_op,
)
from proximo.pmg import (
    what_group_update as pmg_what_group_update_op,
)
from proximo.pmg import (
    what_object_add as pmg_what_object_add_op,
)
from proximo.pmg import (
    what_object_delete as pmg_what_object_delete_op,
)
from proximo.pmg import (
    what_object_update as pmg_what_object_update_op,
)
from proximo.pmg import (
    when_group_create as pmg_when_group_create_op,
)
from proximo.pmg import (
    when_group_delete as pmg_when_group_delete_op,
)
from proximo.pmg import (
    when_group_update as pmg_when_group_update_op,
)
from proximo.pmg import (
    when_object_add as pmg_when_object_add_op,
)
from proximo.pmg import (
    when_object_delete as pmg_when_object_delete_op,
)
from proximo.pmg import (
    when_object_update as pmg_when_object_update_op,
)
from proximo.pmg import (
    who_group_create as pmg_who_group_create_op,
)
from proximo.pmg import (
    who_group_delete as pmg_who_group_delete_op,
)
from proximo.pmg import (
    who_group_update as pmg_who_group_update_op,
)
from proximo.pmg import (
    who_object_add as pmg_who_object_add_op,
)
from proximo.pmg import (
    who_object_delete as pmg_who_object_delete_op,
)
from proximo.pmg import (
    who_object_update as pmg_who_object_update_op,
)
from proximo.server import (
    _audited,
    _plan,
    tool,
)


@tool()
def pmg_who_group_create(
    name: str,
    info: str | None = None,
    and_: bool | None = None,
    invert: bool | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (LOW): create a PMG RuleDB 'who' object group. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: POST /config/ruledb/who.
    name: group name.
    info: optional description.
    and_: maps to API param 'and' (bool; AND vs OR logic for group members).
    invert: if True, the group match is inverted.
    Returns the numeric ogroup ID assigned by PMG on confirm.
    """
    _, pmg = _proximo_server._pmg()
    tgt = "pmg/config/ruledb/who"
    plan = _plan("pmg_who_group_create", tgt,
                 lambda: pmg_plan_who_group_create(name, info, and_, invert))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_who_group_create", tgt,
                    lambda: pmg_who_group_create_op(pmg, name, info, and_, invert),
                    mutation=True, outcome="ok", detail={"confirmed": True, "name": name})


@tool()
def pmg_who_group_update(
    ogroup: str,
    name: str | None = None,
    info: str | None = None,
    and_: bool | None = None,
    invert: bool | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): update a PMG RuleDB 'who' object group config. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: PUT /config/ruledb/who/{ogroup}/config.
    ogroup: numeric ID string (e.g. '2') from pmg_who_groups_list.
    Only non-None fields are sent to PMG; omitted fields keep current values.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/who/{ogroup}/config"
    plan = _plan("pmg_who_group_update", tgt,
                 lambda: pmg_plan_who_group_update(ogroup, name, info, and_, invert))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_who_group_update", tgt,
                    lambda: pmg_who_group_update_op(pmg, ogroup, name, info, and_, invert),
                    mutation=True, outcome="ok", detail={"confirmed": True, "ogroup": ogroup})


@tool()
def pmg_who_group_delete(ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): delete a PMG RuleDB 'who' object group. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/who/{ogroup}.
    ogroup: numeric ID string (e.g. '2') from pmg_who_groups_list.
    WARNING: also removes all objects within the group.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/who/{ogroup}"
    plan = _plan("pmg_who_group_delete", tgt,
                 lambda: pmg_plan_who_group_delete(ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_who_group_delete", tgt,
                    lambda: pmg_who_group_delete_op(pmg, ogroup),
                    mutation=True, outcome="ok", detail={"confirmed": True, "ogroup": ogroup})


@tool()
def pmg_what_group_create(
    name: str,
    info: str | None = None,
    and_: bool | None = None,
    invert: bool | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (LOW): create a PMG RuleDB 'what' object group. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: POST /config/ruledb/what.
    name: group name.
    info: optional description.
    and_: maps to API param 'and' (bool; AND vs OR logic for group members).
    invert: if True, the group match is inverted.
    Returns the numeric ogroup ID assigned by PMG on confirm.
    """
    _, pmg = _proximo_server._pmg()
    tgt = "pmg/config/ruledb/what"
    plan = _plan("pmg_what_group_create", tgt,
                 lambda: pmg_plan_what_group_create(name, info, and_, invert))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_what_group_create", tgt,
                    lambda: pmg_what_group_create_op(pmg, name, info, and_, invert),
                    mutation=True, outcome="ok", detail={"confirmed": True, "name": name})


@tool()
def pmg_what_group_update(
    ogroup: str,
    name: str | None = None,
    info: str | None = None,
    and_: bool | None = None,
    invert: bool | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): update a PMG RuleDB 'what' object group config. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: PUT /config/ruledb/what/{ogroup}/config.
    ogroup: numeric ID string (e.g. '8') from pmg_what_groups_list.
    Only non-None fields are sent to PMG; omitted fields keep current values.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/what/{ogroup}/config"
    plan = _plan("pmg_what_group_update", tgt,
                 lambda: pmg_plan_what_group_update(ogroup, name, info, and_, invert))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_what_group_update", tgt,
                    lambda: pmg_what_group_update_op(pmg, ogroup, name, info, and_, invert),
                    mutation=True, outcome="ok", detail={"confirmed": True, "ogroup": ogroup})


@tool()
def pmg_what_group_delete(ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): delete a PMG RuleDB 'what' object group. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/what/{ogroup}.
    ogroup: numeric ID string (e.g. '8') from pmg_what_groups_list.
    WARNING: also removes all objects within the group.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/what/{ogroup}"
    plan = _plan("pmg_what_group_delete", tgt,
                 lambda: pmg_plan_what_group_delete(ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_what_group_delete", tgt,
                    lambda: pmg_what_group_delete_op(pmg, ogroup),
                    mutation=True, outcome="ok", detail={"confirmed": True, "ogroup": ogroup})


@tool()
def pmg_when_group_create(
    name: str,
    info: str | None = None,
    and_: bool | None = None,
    invert: bool | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (LOW): create a PMG RuleDB 'when' object group. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: POST /config/ruledb/when.
    name: group name.
    info: optional description.
    and_: maps to API param 'and' (bool; AND vs OR logic for group members).
    invert: if True, the group match is inverted.
    Returns the numeric ogroup ID assigned by PMG on confirm.
    """
    _, pmg = _proximo_server._pmg()
    tgt = "pmg/config/ruledb/when"
    plan = _plan("pmg_when_group_create", tgt,
                 lambda: pmg_plan_when_group_create(name, info, and_, invert))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_when_group_create", tgt,
                    lambda: pmg_when_group_create_op(pmg, name, info, and_, invert),
                    mutation=True, outcome="ok", detail={"confirmed": True, "name": name})


@tool()
def pmg_when_group_update(
    ogroup: str,
    name: str | None = None,
    info: str | None = None,
    and_: bool | None = None,
    invert: bool | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): update a PMG RuleDB 'when' object group config. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: PUT /config/ruledb/when/{ogroup}/config.
    ogroup: numeric ID string (e.g. '4') from pmg_when_groups_list.
    Only non-None fields are sent to PMG; omitted fields keep current values.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/when/{ogroup}/config"
    plan = _plan("pmg_when_group_update", tgt,
                 lambda: pmg_plan_when_group_update(ogroup, name, info, and_, invert))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_when_group_update", tgt,
                    lambda: pmg_when_group_update_op(pmg, ogroup, name, info, and_, invert),
                    mutation=True, outcome="ok", detail={"confirmed": True, "ogroup": ogroup})


@tool()
def pmg_when_group_delete(ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): delete a PMG RuleDB 'when' object group. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/when/{ogroup}.
    ogroup: numeric ID string (e.g. '4') from pmg_when_groups_list.
    WARNING: also removes all objects within the group.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/when/{ogroup}"
    plan = _plan("pmg_when_group_delete", tgt,
                 lambda: pmg_plan_when_group_delete(ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_when_group_delete", tgt,
                    lambda: pmg_when_group_delete_op(pmg, ogroup),
                    mutation=True, outcome="ok", detail={"confirmed": True, "ogroup": ogroup})


@tool()
def pmg_who_object_add(
    ogroup: str,
    type_: str,
    email: str | None = None,
    domain: str | None = None,
    regex: str | None = None,
    ip: str | None = None,
    cidr: str | None = None,
    mode: str | None = None,
    profile: str | None = None,
    group: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (LOW): add an object to a PMG RuleDB 'who' object group. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: POST /config/ruledb/who/{ogroup}/{type}.
    ogroup: numeric ID string (e.g. '2') from pmg_who_groups_list.
    type_: email|domain|regex|ip|network|ldap — controls the sub-path.
    Type-specific fields: email(email), domain(domain), regex(regex), ip(ip),
    network(cidr), ldap(mode, profile, group).
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/who/{ogroup}/{type_}"
    plan = _plan("pmg_who_object_add", tgt,
                 lambda: pmg_plan_who_object_add(
                     ogroup, type_,
                     email=email, domain=domain, regex=regex, ip=ip,
                     cidr=cidr, mode=mode, profile=profile, group=group,
                 ))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_who_object_add", tgt,
                    lambda: pmg_who_object_add_op(
                        pmg, ogroup, type_,
                        email=email, domain=domain, regex=regex, ip=ip,
                        cidr=cidr, mode=mode, profile=profile, group=group,
                    ),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "ogroup": ogroup, "type": type_})


@tool()
def pmg_who_object_update(
    ogroup: str,
    type_: str,
    id_: str,
    email: str | None = None,
    domain: str | None = None,
    regex: str | None = None,
    ip: str | None = None,
    cidr: str | None = None,
    mode: str | None = None,
    profile: str | None = None,
    group: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): update an object in a PMG RuleDB 'who' object group. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: PUT /config/ruledb/who/{ogroup}/{type}/{id}.
    ogroup: numeric ID string (e.g. '2') from pmg_who_groups_list.
    type_: email|domain|regex|ip|network|ldap — controls the sub-path.
    id_: object ID (numeric string) from pmg_who_group_objects.
    All type-specific fields optional; only non-None fields are sent.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/who/{ogroup}/{type_}/{id_}"
    plan = _plan("pmg_who_object_update", tgt,
                 lambda: pmg_plan_who_object_update(
                     ogroup, type_, id_,
                     email=email, domain=domain, regex=regex, ip=ip,
                     cidr=cidr, mode=mode, profile=profile, group=group,
                 ))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_who_object_update", tgt,
                    lambda: pmg_who_object_update_op(
                        pmg, ogroup, type_, id_,
                        email=email, domain=domain, regex=regex, ip=ip,
                        cidr=cidr, mode=mode, profile=profile, group=group,
                    ),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "ogroup": ogroup, "type": type_, "id": id_})


@tool()
def pmg_who_object_delete(ogroup: str, id_: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): delete an object from a PMG RuleDB 'who' object group. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/who/{ogroup}/objects/{id}.
    ogroup: numeric ID string (e.g. '2') from pmg_who_groups_list.
    id_: object ID (numeric string) from pmg_who_group_objects.
    Object DELETE always goes through /objects/{id} regardless of type.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/who/{ogroup}/objects/{id_}"
    plan = _plan("pmg_who_object_delete", tgt,
                 lambda: pmg_plan_who_object_delete(ogroup, id_))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_who_object_delete", tgt,
                    lambda: pmg_who_object_delete_op(pmg, ogroup, id_),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "ogroup": ogroup, "id": id_})


# ---------------------------------------------------------------------------
# W5c: WHAT-object CRUD tools
# ---------------------------------------------------------------------------

@tool()
def pmg_what_object_add(
    ogroup: str,
    type_: str,
    contenttype: str | None = None,
    only_content: bool | None = None,
    field: str | None = None,
    value: str | None = None,
    top_part_only: bool | None = None,
    spamlevel: int | None = None,
    filename: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (LOW): add an object to a PMG RuleDB 'what' object group. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: POST /config/ruledb/what/{ogroup}/{type}.
    ogroup: numeric ID string (e.g. '8') from pmg_what_groups_list.
    type_: contenttype|matchfield|spamfilter|virusfilter|filenamefilter|archivefilter|archivefilenamefilter.
    Type-specific fields: contenttype+only_content (contenttype/archivefilter),
    field+value+top_part_only (matchfield), spamlevel (spamfilter), filename (filenamefilter/archivefilenamefilter).
    only_content maps to API param 'only-content'; top_part_only → 'top-part-only'.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/what/{ogroup}/{type_}"
    plan = _plan("pmg_what_object_add", tgt,
                 lambda: pmg_plan_what_object_add(
                     ogroup, type_,
                     contenttype=contenttype, only_content=only_content,
                     field=field, value=value, top_part_only=top_part_only,
                     spamlevel=spamlevel, filename=filename,
                 ))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_what_object_add", tgt,
                    lambda: pmg_what_object_add_op(
                        pmg, ogroup, type_,
                        contenttype=contenttype, only_content=only_content,
                        field=field, value=value, top_part_only=top_part_only,
                        spamlevel=spamlevel, filename=filename,
                    ),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "ogroup": ogroup, "type": type_})


@tool()
def pmg_what_object_update(
    ogroup: str,
    type_: str,
    id_: str,
    contenttype: str | None = None,
    only_content: bool | None = None,
    field: str | None = None,
    value: str | None = None,
    top_part_only: bool | None = None,
    spamlevel: int | None = None,
    filename: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): update an object in a PMG RuleDB 'what' object group. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: PUT /config/ruledb/what/{ogroup}/{type}/{id}.
    ogroup: numeric ID string (e.g. '8') from pmg_what_groups_list.
    type_: contenttype|matchfield|spamfilter|virusfilter|filenamefilter|archivefilter|archivefilenamefilter.
    id_: object ID (numeric string) from pmg_what_group_objects.
    All type-specific fields optional; only non-None fields are sent.
    only_content → 'only-content'; top_part_only → 'top-part-only'.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/what/{ogroup}/{type_}/{id_}"
    plan = _plan("pmg_what_object_update", tgt,
                 lambda: pmg_plan_what_object_update(
                     ogroup, type_, id_,
                     contenttype=contenttype, only_content=only_content,
                     field=field, value=value, top_part_only=top_part_only,
                     spamlevel=spamlevel, filename=filename,
                 ))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_what_object_update", tgt,
                    lambda: pmg_what_object_update_op(
                        pmg, ogroup, type_, id_,
                        contenttype=contenttype, only_content=only_content,
                        field=field, value=value, top_part_only=top_part_only,
                        spamlevel=spamlevel, filename=filename,
                    ),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "ogroup": ogroup, "type": type_, "id": id_})


@tool()
def pmg_what_object_delete(ogroup: str, id_: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): delete an object from a PMG RuleDB 'what' object group. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/what/{ogroup}/objects/{id}.
    ogroup: numeric ID string (e.g. '8') from pmg_what_groups_list.
    id_: object ID (numeric string) from pmg_what_group_objects.
    Object DELETE always goes through /objects/{id} regardless of type.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/what/{ogroup}/objects/{id_}"
    plan = _plan("pmg_what_object_delete", tgt,
                 lambda: pmg_plan_what_object_delete(ogroup, id_))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_what_object_delete", tgt,
                    lambda: pmg_what_object_delete_op(pmg, ogroup, id_),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "ogroup": ogroup, "id": id_})


# ---------------------------------------------------------------------------
# W5c: WHEN-object CRUD tools
# ---------------------------------------------------------------------------

@tool()
def pmg_when_object_add(
    ogroup: str,
    start: str,
    end: str,
    confirm: bool = False,
) -> dict:
    """MUTATION (LOW): add a timeframe object to a PMG RuleDB 'when' object group. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: POST /config/ruledb/when/{ogroup}/timeframe.
    ogroup: numeric ID string (e.g. '4') from pmg_when_groups_list.
    start: time in H:i format (e.g. '08:00').
    end: time in H:i format (e.g. '17:00').
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/when/{ogroup}/timeframe"
    plan = _plan("pmg_when_object_add", tgt,
                 lambda: pmg_plan_when_object_add(ogroup, start=start, end=end))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_when_object_add", tgt,
                    lambda: pmg_when_object_add_op(pmg, ogroup, start=start, end=end),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "ogroup": ogroup})


@tool()
def pmg_when_object_update(
    ogroup: str,
    id_: str,
    start: str,
    end: str,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): update a timeframe object in a PMG RuleDB 'when' object group. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: PUT /config/ruledb/when/{ogroup}/timeframe/{id}.
    ogroup: numeric ID string (e.g. '4') from pmg_when_groups_list.
    id_: object ID (numeric string) from pmg_when_group_objects.
    Both start and end are required — PMG 9.1 timeframe PUT rejects partial updates (400).
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/when/{ogroup}/timeframe/{id_}"
    plan = _plan("pmg_when_object_update", tgt,
                 lambda: pmg_plan_when_object_update(ogroup, id_, start=start, end=end))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_when_object_update", tgt,
                    lambda: pmg_when_object_update_op(pmg, ogroup, id_, start=start, end=end),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "ogroup": ogroup, "id": id_})


@tool()
def pmg_when_object_delete(ogroup: str, id_: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): delete a timeframe object from a PMG RuleDB 'when' object group. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/when/{ogroup}/objects/{id}.
    ogroup: numeric ID string (e.g. '4') from pmg_when_groups_list.
    id_: object ID (numeric string) from pmg_when_group_objects.
    Object DELETE always goes through /objects/{id} regardless of type.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/when/{ogroup}/objects/{id_}"
    plan = _plan("pmg_when_object_delete", tgt,
                 lambda: pmg_plan_when_object_delete(ogroup, id_))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_when_object_delete", tgt,
                    lambda: pmg_when_object_delete_op(pmg, ogroup, id_),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "ogroup": ogroup, "id": id_})


# ---------------------------------------------------------------------------
# W5c: ACTION CRUD tools
# ---------------------------------------------------------------------------

@tool()
def pmg_action_bcc_create(
    name: str,
    target: str,
    info: str | None = None,
    original: bool | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (LOW): create a BCC action object in the PMG RuleDB. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: POST /config/ruledb/action/bcc.
    name: action object name. target: BCC recipient email address.
    info: optional description. original: if True, BCC the original sender.
    """
    _, pmg = _proximo_server._pmg()
    tgt = "pmg/config/ruledb/action/bcc"
    plan = _plan("pmg_action_bcc_create", tgt,
                 lambda: pmg_plan_action_bcc_create(name, target))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_action_bcc_create", tgt,
                    lambda: pmg_action_bcc_create_op(pmg, name=name, target=target,
                                                     info=info, original=original),
                    mutation=True, outcome="ok", detail={"confirmed": True, "name": name})


@tool()
def pmg_action_bcc_update(
    id_: str,
    name: str | None = None,
    target: str | None = None,
    info: str | None = None,
    original: bool | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): update a BCC action object in the PMG RuleDB. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: PUT /config/ruledb/action/bcc/{id}.
    id_: compound action object ID (e.g. '13_26') from pmg_action_objects_list.
    Only non-None fields are sent; omitted fields keep current values.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/action/bcc/{id_}"
    plan = _plan("pmg_action_bcc_update", tgt,
                 lambda: pmg_plan_action_bcc_update(id_))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_action_bcc_update", tgt,
                    lambda: pmg_action_bcc_update_op(pmg, id_, name=name, target=target,
                                                     info=info, original=original),
                    mutation=True, outcome="ok", detail={"confirmed": True, "id": id_})


@tool()
def pmg_action_field_create(
    name: str,
    field: str,
    value: str,
    info: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (LOW): create a field-modification action object in the PMG RuleDB. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: POST /config/ruledb/action/field.
    name: action object name. field: mail header field to set. value: value to assign.
    info: optional description.
    """
    _, pmg = _proximo_server._pmg()
    tgt = "pmg/config/ruledb/action/field"
    plan = _plan("pmg_action_field_create", tgt,
                 lambda: pmg_plan_action_field_create(name, field, value))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_action_field_create", tgt,
                    lambda: pmg_action_field_create_op(pmg, name=name, field=field,
                                                       value=value, info=info),
                    mutation=True, outcome="ok", detail={"confirmed": True, "name": name})


@tool()
def pmg_action_field_update(
    id_: str,
    name: str,
    field: str,
    value: str,
    info: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): update a field-modification action object in the PMG RuleDB. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: PUT /config/ruledb/action/field/{id}.
    id_: compound action object ID (e.g. '13_26') from pmg_action_objects_list.
    name, field, value all required — PMG 9.1 field action PUT rejects partial updates (400).
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/action/field/{id_}"
    plan = _plan("pmg_action_field_update", tgt,
                 lambda: pmg_plan_action_field_update(id_))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_action_field_update", tgt,
                    lambda: pmg_action_field_update_op(pmg, id_, name=name, field=field,
                                                       value=value, info=info),
                    mutation=True, outcome="ok", detail={"confirmed": True, "id": id_})


@tool()
def pmg_action_notification_create(
    name: str,
    to: str,
    subject: str,
    body_text: str,
    info: str | None = None,
    attach: bool | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (LOW): create a notification action object in the PMG RuleDB. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: POST /config/ruledb/action/notification.
    name: action name. to: notification recipient. subject: notification subject.
    body_text: notification body (maps to API param 'body'). attach: attach original message.
    """
    _, pmg = _proximo_server._pmg()
    tgt = "pmg/config/ruledb/action/notification"
    plan = _plan("pmg_action_notification_create", tgt,
                 lambda: pmg_plan_action_notification_create(name, to))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_action_notification_create", tgt,
                    lambda: pmg_action_notification_create_op(
                        pmg, name=name, to=to, subject=subject,
                        body_text=body_text, info=info, attach=attach,
                    ),
                    mutation=True, outcome="ok", detail={"confirmed": True, "name": name})


@tool()
def pmg_action_notification_update(
    id_: str,
    name: str,
    to: str,
    subject: str,
    body_text: str,
    info: str | None = None,
    attach: bool | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): update a notification action object in the PMG RuleDB. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: PUT /config/ruledb/action/notification/{id}.
    id_: compound action object ID (e.g. '13_26') from pmg_action_objects_list.
    name, to, subject, body_text all required — PMG 9.1 notification PUT rejects partial updates (400).
    body_text maps to API param 'body'.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/action/notification/{id_}"
    plan = _plan("pmg_action_notification_update", tgt,
                 lambda: pmg_plan_action_notification_update(id_))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_action_notification_update", tgt,
                    lambda: pmg_action_notification_update_op(
                        pmg, id_, name=name, to=to, subject=subject,
                        body_text=body_text, info=info, attach=attach,
                    ),
                    mutation=True, outcome="ok", detail={"confirmed": True, "id": id_})


@tool()
def pmg_action_disclaimer_create(
    name: str,
    disclaimer: str,
    info: str | None = None,
    position: str | None = None,
    add_separator: bool | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (LOW): create a disclaimer action object in the PMG RuleDB. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: POST /config/ruledb/action/disclaimer.
    name: action name. disclaimer: disclaimer text. position: start|end.
    add_separator: maps to API param 'add-separator' (bool).
    """
    _, pmg = _proximo_server._pmg()
    tgt = "pmg/config/ruledb/action/disclaimer"
    plan = _plan("pmg_action_disclaimer_create", tgt,
                 lambda: pmg_plan_action_disclaimer_create(name))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_action_disclaimer_create", tgt,
                    lambda: pmg_action_disclaimer_create_op(
                        pmg, name=name, disclaimer=disclaimer,
                        info=info, position=position, add_separator=add_separator,
                    ),
                    mutation=True, outcome="ok", detail={"confirmed": True, "name": name})


@tool()
def pmg_action_disclaimer_update(
    id_: str,
    name: str | None = None,
    disclaimer: str | None = None,
    info: str | None = None,
    position: str | None = None,
    add_separator: bool | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): update a disclaimer action object in the PMG RuleDB. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: PUT /config/ruledb/action/disclaimer/{id}.
    id_: compound action object ID (e.g. '13_26') from pmg_action_objects_list.
    position: start|end (validated). add_separator → 'add-separator'. Only non-None fields sent.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/action/disclaimer/{id_}"
    plan = _plan("pmg_action_disclaimer_update", tgt,
                 lambda: pmg_plan_action_disclaimer_update(id_))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_action_disclaimer_update", tgt,
                    lambda: pmg_action_disclaimer_update_op(
                        pmg, id_, name=name, disclaimer=disclaimer,
                        info=info, position=position, add_separator=add_separator,
                    ),
                    mutation=True, outcome="ok", detail={"confirmed": True, "id": id_})


@tool()
def pmg_action_removeattachments_create(
    name: str,
    text: str,
    info: str | None = None,
    all_: bool | None = None,
    quarantine: bool | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (LOW): create a remove-attachments action object in the PMG RuleDB. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: POST /config/ruledb/action/removeattachments.
    name: action name. text: replacement text for removed attachments.
    all_: maps to API param 'all' (bool; remove all attachments).
    quarantine: if True, quarantine removed attachments.
    """
    _, pmg = _proximo_server._pmg()
    tgt = "pmg/config/ruledb/action/removeattachments"
    plan = _plan("pmg_action_removeattachments_create", tgt,
                 lambda: pmg_plan_action_removeattachments_create(name))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_action_removeattachments_create", tgt,
                    lambda: pmg_action_removeattachments_create_op(
                        pmg, name=name, text=text, info=info,
                        all_=all_, quarantine=quarantine,
                    ),
                    mutation=True, outcome="ok", detail={"confirmed": True, "name": name})


@tool()
def pmg_action_removeattachments_update(
    id_: str,
    name: str | None = None,
    text: str | None = None,
    info: str | None = None,
    all_: bool | None = None,
    quarantine: bool | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): update a remove-attachments action object in the PMG RuleDB. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: PUT /config/ruledb/action/removeattachments/{id}.
    id_: compound action object ID (e.g. '13_26') from pmg_action_objects_list.
    all_: maps to API param 'all' (bool). Only non-None fields are sent.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/action/removeattachments/{id_}"
    plan = _plan("pmg_action_removeattachments_update", tgt,
                 lambda: pmg_plan_action_removeattachments_update(id_))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_action_removeattachments_update", tgt,
                    lambda: pmg_action_removeattachments_update_op(
                        pmg, id_, name=name, text=text, info=info,
                        all_=all_, quarantine=quarantine,
                    ),
                    mutation=True, outcome="ok", detail={"confirmed": True, "id": id_})


@tool()
def pmg_action_delete(id_: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): delete an action object from the PMG RuleDB. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/action/objects/{id}.
    id_: compound action object ID (e.g. '13_26') from pmg_action_objects_list.
    NOTE: PMG rejects deletion of non-editable (built-in) system action objects.
    Check 'editable' flag in pmg_action_objects_list before confirming.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/action/objects/{id_}"
    plan = _plan("pmg_action_delete", tgt,
                 lambda: pmg_plan_action_delete(id_))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_action_delete", tgt,
                    lambda: pmg_action_delete_op(pmg, id_),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_})


@tool()
def pmg_ruledb_rule_create(
    name: str,
    priority: int,
    active: bool = False,
    direction: int | None = None,
    from_and: bool | None = None,
    from_invert: bool | None = None,
    to_and: bool | None = None,
    to_invert: bool | None = None,
    what_and: bool | None = None,
    what_invert: bool | None = None,
    when_and: bool | None = None,
    when_invert: bool | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): create a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: POST /config/ruledb/rules.
    name: rule name. priority: 0-100 (lower = higher priority).
    active: DEFAULTS TO FALSE — rules control live mail processing; only activate
    when the rule configuration and group attachments have been verified.
    direction: 0=inbound, 1=outbound, 2=both.
    from_and/from_invert/to_and/to_invert/what_and/what_invert/when_and/when_invert:
        optional bool flags for AND/invert logic (map to hyphen-param API names).
    Returns the numeric rule ID assigned by PMG on confirm.
    """
    _, pmg = _proximo_server._pmg()
    tgt = "pmg/config/ruledb/rules"
    plan = _plan("pmg_ruledb_rule_create", tgt,
                 lambda: pmg_plan_ruledb_rule_create(
                     name, priority, active, direction,
                     from_and, from_invert, to_and, to_invert,
                     what_and, what_invert, when_and, when_invert,
                 ))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_create", tgt,
                    lambda: pmg_ruledb_rule_create_op(
                        pmg, name, priority, active, direction,
                        from_and, from_invert, to_and, to_invert,
                        what_and, what_invert, when_and, when_invert,
                    ),
                    mutation=True, outcome="ok", detail={"confirmed": True, "name": name})


@tool()
def pmg_ruledb_rule_update(
    id_: str,
    name: str | None = None,
    priority: int | None = None,
    active: bool | None = None,
    direction: int | None = None,
    from_and: bool | None = None,
    from_invert: bool | None = None,
    to_and: bool | None = None,
    to_invert: bool | None = None,
    what_and: bool | None = None,
    what_invert: bool | None = None,
    when_and: bool | None = None,
    when_invert: bool | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): update a PMG RuleDB rule configuration. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: PUT /config/ruledb/rules/{id}/config.
    id_: rule ID (positive integer string, e.g. '100').
    All other fields are optional; only non-None values are sent.
    WARNING: setting active=True activates the rule and begins live mail processing.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}/config"
    plan = _plan("pmg_ruledb_rule_update", tgt,
                 lambda: pmg_plan_ruledb_rule_update(
                     id_, name, priority, active, direction,
                     from_and, from_invert, to_and, to_invert,
                     what_and, what_invert, when_and, when_invert,
                 ))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_update", tgt,
                    lambda: pmg_ruledb_rule_update_op(
                        pmg, id_, name, priority, active, direction,
                        from_and, from_invert, to_and, to_invert,
                        what_and, what_invert, when_and, when_invert,
                    ),
                    mutation=True, outcome="ok", detail={"confirmed": True, "id": id_})


@tool()
def pmg_ruledb_rule_delete(id_: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): delete a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/rules/{id}.
    id_: rule ID (positive integer string, e.g. '100').
    WARNING: permanently removes the rule and all its group bindings.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}"
    plan = _plan("pmg_ruledb_rule_delete", tgt,
                 lambda: pmg_plan_ruledb_rule_delete(id_))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_delete", tgt,
                    lambda: pmg_ruledb_rule_delete_op(pmg, id_),
                    mutation=True, outcome="ok", detail={"confirmed": True, "id": id_})


@tool()
def pmg_ruledb_rule_from_attach(id_: str, ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): attach a 'from' (sender/who) group to a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: POST /config/ruledb/rules/{id}/from.
    id_: rule ID. ogroup: numeric who-group ID from pmg_who_groups_list.
    Only affects mail flow if the rule is active.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}/from"
    plan = _plan("pmg_ruledb_rule_from_attach", tgt,
                 lambda: pmg_plan_ruledb_rule_from_attach(id_, ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_from_attach", tgt,
                    lambda: pmg_ruledb_rule_from_attach_op(pmg, id_, ogroup),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_, "ogroup": ogroup})


@tool()
def pmg_ruledb_rule_from_detach(id_: str, ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): detach a 'from' (sender/who) group from a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/rules/{id}/from/{ogroup}.
    id_: rule ID. ogroup: numeric who-group ID to detach.
    Only affects mail flow if the rule is active.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}/from/{ogroup}"
    plan = _plan("pmg_ruledb_rule_from_detach", tgt,
                 lambda: pmg_plan_ruledb_rule_from_detach(id_, ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_from_detach", tgt,
                    lambda: pmg_ruledb_rule_from_detach_op(pmg, id_, ogroup),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_, "ogroup": ogroup})


@tool()
def pmg_ruledb_rule_to_attach(id_: str, ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): attach a 'to' (recipient/who) group to a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: POST /config/ruledb/rules/{id}/to.
    id_: rule ID. ogroup: numeric who-group ID from pmg_who_groups_list.
    Only affects mail flow if the rule is active.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}/to"
    plan = _plan("pmg_ruledb_rule_to_attach", tgt,
                 lambda: pmg_plan_ruledb_rule_to_attach(id_, ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_to_attach", tgt,
                    lambda: pmg_ruledb_rule_to_attach_op(pmg, id_, ogroup),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_, "ogroup": ogroup})


@tool()
def pmg_ruledb_rule_to_detach(id_: str, ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): detach a 'to' (recipient/who) group from a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/rules/{id}/to/{ogroup}.
    id_: rule ID. ogroup: numeric who-group ID to detach.
    Only affects mail flow if the rule is active.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}/to/{ogroup}"
    plan = _plan("pmg_ruledb_rule_to_detach", tgt,
                 lambda: pmg_plan_ruledb_rule_to_detach(id_, ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_to_detach", tgt,
                    lambda: pmg_ruledb_rule_to_detach_op(pmg, id_, ogroup),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_, "ogroup": ogroup})


@tool()
def pmg_ruledb_rule_what_attach(id_: str, ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): attach a 'what' (content) group to a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: POST /config/ruledb/rules/{id}/what.
    id_: rule ID. ogroup: numeric what-group ID from pmg_what_groups_list.
    Only affects mail flow if the rule is active.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}/what"
    plan = _plan("pmg_ruledb_rule_what_attach", tgt,
                 lambda: pmg_plan_ruledb_rule_what_attach(id_, ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_what_attach", tgt,
                    lambda: pmg_ruledb_rule_what_attach_op(pmg, id_, ogroup),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_, "ogroup": ogroup})


@tool()
def pmg_ruledb_rule_what_detach(id_: str, ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): detach a 'what' (content) group from a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/rules/{id}/what/{ogroup}.
    id_: rule ID. ogroup: numeric what-group ID to detach.
    Only affects mail flow if the rule is active.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}/what/{ogroup}"
    plan = _plan("pmg_ruledb_rule_what_detach", tgt,
                 lambda: pmg_plan_ruledb_rule_what_detach(id_, ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_what_detach", tgt,
                    lambda: pmg_ruledb_rule_what_detach_op(pmg, id_, ogroup),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_, "ogroup": ogroup})


@tool()
def pmg_ruledb_rule_when_attach(id_: str, ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): attach a 'when' (timeframe) group to a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: POST /config/ruledb/rules/{id}/when.
    id_: rule ID. ogroup: numeric when-group ID from pmg_when_groups_list.
    Only affects mail flow if the rule is active.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}/when"
    plan = _plan("pmg_ruledb_rule_when_attach", tgt,
                 lambda: pmg_plan_ruledb_rule_when_attach(id_, ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_when_attach", tgt,
                    lambda: pmg_ruledb_rule_when_attach_op(pmg, id_, ogroup),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_, "ogroup": ogroup})


@tool()
def pmg_ruledb_rule_when_detach(id_: str, ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): detach a 'when' (timeframe) group from a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/rules/{id}/when/{ogroup}.
    id_: rule ID. ogroup: numeric when-group ID to detach.
    Only affects mail flow if the rule is active.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}/when/{ogroup}"
    plan = _plan("pmg_ruledb_rule_when_detach", tgt,
                 lambda: pmg_plan_ruledb_rule_when_detach(id_, ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_when_detach", tgt,
                    lambda: pmg_ruledb_rule_when_detach_op(pmg, id_, ogroup),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_, "ogroup": ogroup})


@tool()
def pmg_ruledb_rule_action_attach(id_: str, ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): attach an action group to a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 live-verified path: POST /config/ruledb/rules/{id}/action (singular; /actions returns 501).
    id_: rule ID. ogroup: numeric action group ID from pmg_action_objects_list.
    Only affects mail flow if the rule is active.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}/action"
    plan = _plan("pmg_ruledb_rule_action_attach", tgt,
                 lambda: pmg_plan_ruledb_rule_action_attach(id_, ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_action_attach", tgt,
                    lambda: pmg_ruledb_rule_action_attach_op(pmg, id_, ogroup),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_, "ogroup": ogroup})


@tool()
def pmg_ruledb_rule_action_detach(id_: str, ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): detach an action group from a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 live-verified path: DELETE /config/ruledb/rules/{id}/action/{ogroup} (singular; /actions returns 501).
    id_: rule ID. ogroup: numeric action group ID to detach.
    Only affects mail flow if the rule is active.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}/action/{ogroup}"
    plan = _plan("pmg_ruledb_rule_action_detach", tgt,
                 lambda: pmg_plan_ruledb_rule_action_detach(id_, ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_action_detach", tgt,
                    lambda: pmg_ruledb_rule_action_detach_op(pmg, id_, ogroup),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_, "ogroup": ogroup})
