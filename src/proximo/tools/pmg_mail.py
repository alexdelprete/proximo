"""PMG (Proxmox Mail Gateway) operational tools: domains, relay, quarantine, postfix, spam config, statistics,
tracker, backup, and ruledb reads.

Split out of proximo.server (2026-07-02) — see proximo/server.py's module
docstring for the funnel these wrappers depend on.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

import proximo.server as _proximo_server
from proximo.pmg import (
    access_permissions as pmg_access_permissions_op,
)
from proximo.pmg import (
    action_objects_list as pmg_action_objects_list_op,
)
from proximo.pmg import (
    backup_create as pmg_backup_create_op,
)
from proximo.pmg import (
    domain_create as pmg_domain_create_op,
)
from proximo.pmg import (
    domain_delete as pmg_domain_delete_op,
)
from proximo.pmg import (
    domains_list as pmg_domains_list_op,
)
from proximo.pmg import (
    mynetworks_add as pmg_mynetworks_add_op,
)
from proximo.pmg import (
    mynetworks_remove as pmg_mynetworks_remove_op,
)
from proximo.pmg import (
    node_rrddata as pmg_node_rrddata_op,
)
from proximo.pmg import (
    node_status as pmg_node_status_op,
)
from proximo.pmg import (
    node_syslog as pmg_node_syslog_op,
)
from proximo.pmg import (
    node_version as pmg_node_version_op,
)
from proximo.pmg import (
    plan_backup_create as pmg_plan_backup_create,
)
from proximo.pmg import (
    plan_domain_create as pmg_plan_domain_create,
)
from proximo.pmg import (
    plan_domain_delete as pmg_plan_domain_delete,
)
from proximo.pmg import (
    plan_mynetworks_add as pmg_plan_mynetworks_add,
)
from proximo.pmg import (
    plan_mynetworks_remove as pmg_plan_mynetworks_remove,
)
from proximo.pmg import (
    plan_postfix_flush as pmg_plan_postfix_flush,
)
from proximo.pmg import (
    plan_quarantine_action as pmg_plan_quarantine_action,
)
from proximo.pmg import (
    plan_quarantine_blocklist_add as pmg_plan_quarantine_blocklist_add,
)
from proximo.pmg import (
    plan_quarantine_blocklist_remove as pmg_plan_quarantine_blocklist_remove,
)
from proximo.pmg import (
    plan_quarantine_welcomelist_add as pmg_plan_quarantine_welcomelist_add,
)
from proximo.pmg import (
    plan_quarantine_welcomelist_remove as pmg_plan_quarantine_welcomelist_remove,
)
from proximo.pmg import (
    plan_service_control as pmg_plan_service_control,
)
from proximo.pmg import (
    plan_spam_config_update as pmg_plan_spam_config_update,
)
from proximo.pmg import (
    plan_transport_create as pmg_plan_transport_create,
)
from proximo.pmg import (
    plan_transport_delete as pmg_plan_transport_delete,
)
from proximo.pmg import (
    postfix_flush as pmg_postfix_flush_op,
)
from proximo.pmg import (
    postfix_qshape as pmg_postfix_qshape_op,
)
from proximo.pmg import (
    quarantine_action as pmg_quarantine_action_op,
)
from proximo.pmg import (
    quarantine_attachment as pmg_quarantine_attachment_op,
)
from proximo.pmg import (
    quarantine_blocklist_add as pmg_quarantine_blocklist_add_op,
)
from proximo.pmg import (
    quarantine_blocklist_list as pmg_quarantine_blocklist_list_op,
)
from proximo.pmg import (
    quarantine_blocklist_remove as pmg_quarantine_blocklist_remove_op,
)
from proximo.pmg import (
    quarantine_spam as pmg_quarantine_spam_op,
)
from proximo.pmg import (
    quarantine_spamstatus as pmg_quarantine_spamstatus_op,
)
from proximo.pmg import (
    quarantine_spamusers as pmg_quarantine_spamusers_op,
)
from proximo.pmg import (
    quarantine_virus as pmg_quarantine_virus_op,
)
from proximo.pmg import (
    quarantine_virusstatus as pmg_quarantine_virusstatus_op,
)
from proximo.pmg import (
    quarantine_welcomelist_add as pmg_quarantine_welcomelist_add_op,
)
from proximo.pmg import (
    quarantine_welcomelist_list as pmg_quarantine_welcomelist_list_op,
)
from proximo.pmg import (
    quarantine_welcomelist_remove as pmg_quarantine_welcomelist_remove_op,
)
from proximo.pmg import (
    relay_config as pmg_relay_config_op,
)
from proximo.pmg import (
    ruledb_digest as pmg_ruledb_digest_op,
)
from proximo.pmg import (
    ruledb_rule_actions_list as pmg_ruledb_rule_actions_list_op,
)
from proximo.pmg import (
    ruledb_rule_from_list as pmg_ruledb_rule_from_list_op,
)
from proximo.pmg import (
    ruledb_rule_get as pmg_ruledb_rule_get_op,
)
from proximo.pmg import (
    ruledb_rule_to_list as pmg_ruledb_rule_to_list_op,
)
from proximo.pmg import (
    ruledb_rule_what_list as pmg_ruledb_rule_what_list_op,
)
from proximo.pmg import (
    ruledb_rule_when_list as pmg_ruledb_rule_when_list_op,
)
from proximo.pmg import (
    ruledb_rules_list as pmg_ruledb_rules_list_op,
)
from proximo.pmg import (
    service_control as pmg_service_control_op,
)
from proximo.pmg import (
    service_status as pmg_service_status_op,
)
from proximo.pmg import (
    spam_config as pmg_spam_config_op,
)
from proximo.pmg import (
    spam_config_update as pmg_spam_config_update_op,
)
from proximo.pmg import (
    statistics_domains as pmg_statistics_domains_op,
)
from proximo.pmg import (
    statistics_mail as pmg_statistics_mail_op,
)
from proximo.pmg import (
    statistics_mailcount as pmg_statistics_mailcount_op,
)
from proximo.pmg import (
    statistics_receiver as pmg_statistics_receiver_op,
)
from proximo.pmg import (
    statistics_recent as pmg_statistics_recent_op,
)
from proximo.pmg import (
    statistics_sender as pmg_statistics_sender_op,
)
from proximo.pmg import (
    statistics_spamscores as pmg_statistics_spamscores_op,
)
from proximo.pmg import (
    statistics_virus as pmg_statistics_virus_op,
)
from proximo.pmg import (
    tasks_list as pmg_tasks_list_op,
)
from proximo.pmg import (
    tracker_detail as pmg_tracker_detail_op,
)
from proximo.pmg import (
    tracker_list as pmg_tracker_list_op,
)
from proximo.pmg import (
    transport_create as pmg_transport_create_op,
)
from proximo.pmg import (
    transport_delete as pmg_transport_delete_op,
)
from proximo.pmg import (
    what_group_get as pmg_what_group_get_op,
)
from proximo.pmg import (
    what_group_objects as pmg_what_group_objects_op,
)
from proximo.pmg import (
    what_groups_list as pmg_what_groups_list_op,
)
from proximo.pmg import (
    when_group_get as pmg_when_group_get_op,
)
from proximo.pmg import (
    when_group_objects as pmg_when_group_objects_op,
)
from proximo.pmg import (
    when_groups_list as pmg_when_groups_list_op,
)
from proximo.pmg import (
    who_group_get as pmg_who_group_get_op,
)
from proximo.pmg import (
    who_group_objects as pmg_who_group_objects_op,
)
from proximo.pmg import (
    who_groups_list as pmg_who_groups_list_op,
)
from proximo.server import (
    _audited,
    _plan,
    tool,
)

# --- PMG (Proxmox Mail Gateway) ---

@tool()
def pmg_doctor(node: Annotated[str | None, Field(description="PMG node name; defaults to the configured node.")] = None) -> dict:
    """READ-ONLY: PMG connectivity + credential/permission preflight — checks the global /version
    endpoint and /access/users. Needs PROXIMO_PMG_* config.

    Returns a dict with "version" and "permissions" keys; a successful call proves connectivity
    and credentials together. Run this first when diagnosing PMG trouble, before other pmg_* tools.
    PMG has no /access/permissions endpoint (that is PVE-only); "permissions" here is /access/users.
    """
    cfg, pmg = _proximo_server._pmg()
    n = node or cfg.node
    return _audited("pmg_doctor", f"pmg/{n}",
                    lambda: {
                        "version": pmg_node_version_op(pmg, n),
                        "permissions": pmg_access_permissions_op(pmg),
                    })


@tool()
def pmg_node_status(node: Annotated[str | None, Field(description="PMG node name; defaults to the configured node.")] = None) -> dict:
    """READ-ONLY: get PMG node cpu/mem/disk/uptime status. Needs PROXIMO_PMG_* config.

    Returns a dict with cpu/memory/disk/uptime fields for the node. This is the PMG node
    (Proxmox Mail Gateway); for a PVE hypervisor node use pve_node_status instead.
    """
    cfg, pmg = _proximo_server._pmg()
    n = node or cfg.node
    return _audited("pmg_node_status", f"pmg/{n}/status",
                    lambda: pmg_node_status_op(pmg, n))


@tool()
def pmg_relay_config() -> dict:
    """READ-ONLY: get PMG SMTP relay/smarthost configuration. Needs PROXIMO_PMG_* config.

    Returns the full mail config section as a dict, including relay host, relay port, and other
    SMTP delivery settings. Lives at /config/mail — there is no separate /config/relay endpoint.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_relay_config", "pmg/config/mail",
                    lambda: pmg_relay_config_op(pmg))


@tool()
def pmg_domains_list() -> list[dict]:
    """READ-ONLY: list PMG managed mail domains. Needs PROXIMO_PMG_* config.

    Returns a list of domain dicts (domain name + comment). Use pmg_domain_create/pmg_domain_delete
    to manage domains.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_domains_list", "pmg/config/domains",
                    lambda: pmg_domains_list_op(pmg))


@tool()
def pmg_statistics_mail() -> dict:
    """Get PMG mail delivery statistics (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified: /statistics/mail returns today's aggregate counters
    (count_in, count_out, spam, virus, bytes, …). Always returns today's totals;
    for time-ranged data use pmg_statistics_mailcount instead.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_statistics_mail", "pmg/statistics/mail",
                    lambda: pmg_statistics_mail_op(pmg))


@tool()
def pmg_quarantine_spam() -> list[dict]:
    """READ-ONLY: list PMG quarantined spam messages. Needs PROXIMO_PMG_* config.

    Returns a list of dicts, one per quarantined message. For virus quarantine use
    pmg_quarantine_virus; for attachment quarantine use pmg_quarantine_attachment. To act on
    quarantined messages (deliver/delete/mark-seen/blocklist/welcomelist) use pmg_quarantine_action.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_quarantine_spam", "pmg/quarantine/spam",
                    lambda: pmg_quarantine_spam_op(pmg))


@tool()
def pmg_statistics_domains(
    start: Annotated[int | None, Field(description="Unix epoch start of the stats window; omit for no lower bound.")] = None,
    end: Annotated[int | None, Field(description="Unix epoch end of the stats window; omit for no upper bound.")] = None,
) -> list[dict]:
    """READ-ONLY: get PMG per-domain mail statistics. Optional Unix epoch start/end timespan.
    Needs PROXIMO_PMG_* config.

    Returns a list of per-domain stat dicts. For overall totals use pmg_statistics_mail; for
    time-bucketed counts use pmg_statistics_mailcount. start/end map to starttime/endtime.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_statistics_domains", "pmg/statistics/domains",
                    lambda: pmg_statistics_domains_op(pmg, start, end))


@tool()
def pmg_statistics_virus(
    start: Annotated[int | None, Field(description="Unix epoch start of the stats window; omit for no lower bound.")] = None,
    end: Annotated[int | None, Field(description="Unix epoch end of the stats window; omit for no upper bound.")] = None,
) -> list[dict]:
    """READ-ONLY: get PMG virus statistics. Optional Unix epoch start/end timespan.
    Needs PROXIMO_PMG_* config.

    Returns a list of dicts with virus-detection counts over the window. For per-message virus
    quarantine entries use pmg_quarantine_virus instead. start/end map to starttime/endtime.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_statistics_virus", "pmg/statistics/virus",
                    lambda: pmg_statistics_virus_op(pmg, start, end))


@tool()
def pmg_statistics_spamscores(
    start: Annotated[int | None, Field(description="Unix epoch start of the stats window; omit for no lower bound.")] = None,
    end: Annotated[int | None, Field(description="Unix epoch end of the stats window; omit for no upper bound.")] = None,
) -> list[dict]:
    """READ-ONLY: get PMG spam score distribution statistics. Optional Unix epoch start/end timespan.
    Needs PROXIMO_PMG_* config.

    Returns a list of dicts bucketing message counts by spam score. For the raw quarantined spam
    messages use pmg_quarantine_spam instead. start/end map to starttime/endtime.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_statistics_spamscores", "pmg/statistics/spamscores",
                    lambda: pmg_statistics_spamscores_op(pmg, start, end))


@tool()
def pmg_statistics_recent(hours: Annotated[int, Field(description="Lookback window in hours, 1-24 (default 1).")] = 1) -> list[dict]:
    """READ-ONLY: get PMG recent mail statistics. hours: 1-24 window. Needs PROXIMO_PMG_* config.

    Returns a list of dicts covering only the last `hours`. For today's full aggregate totals use
    pmg_statistics_mail instead.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_statistics_recent", "pmg/statistics/recent",
                    lambda: pmg_statistics_recent_op(pmg, hours))


@tool()
def pmg_quarantine_blocklist_list(pmail: Annotated[str | None, Field(description="Scope the blocklist read to this user's mailbox; defaults to the authenticated PMG user.")] = None) -> list[dict]:
    """READ-ONLY: list PMG quarantine blocklist entries. Optional pmail to scope to one user.
    Needs PROXIMO_PMG_* config.

    Returns a list of blocklist-entry dicts. pmail is ALWAYS sent, defaulting to the authenticated
    PMG user when omitted — an empty result means "none for that user," not "none globally." Use
    pmg_quarantine_blocklist_add/pmg_quarantine_blocklist_remove to manage entries.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_quarantine_blocklist_list", "pmg/quarantine/blocklist",
                    lambda: pmg_quarantine_blocklist_list_op(pmg, pmail))


@tool()
def pmg_quarantine_blocklist_add(
    address: Annotated[str, Field(description="Email address to add to the quarantine blocklist.")],
    pmail: Annotated[str | None, Field(description="Scope the blocklist entry to this user's mailbox; defaults to the authenticated PMG user.")] = None,
    confirm: Annotated[bool, Field(description="False (default) returns a dry-run PLAN; True executes the mutation.")] = False,
) -> dict:
    """MUTATION (LOW): add an address to the quarantine blocklist. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    Dry-run returns a PLAN; confirm=True executes and returns {"status": "ok", "result": ...}.
    Additive — reverse with pmg_quarantine_blocklist_remove. View current entries with
    pmg_quarantine_blocklist_list. pmail scopes the entry to a per-user blocklist (optional).
    """
    _, pmg = _proximo_server._pmg()
    tgt = "pmg/quarantine/blocklist"
    plan = _plan("pmg_quarantine_blocklist_add", tgt,
                 lambda: pmg_plan_quarantine_blocklist_add(address, pmail, pmg.config.username))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_quarantine_blocklist_add", tgt,
                    lambda: pmg_quarantine_blocklist_add_op(pmg, address, pmail),
                    mutation=True, outcome="ok", detail={"confirmed": True, "address": address})


@tool()
def pmg_quarantine_action(
    action: Annotated[str, Field(description="Action to apply: deliver|delete|mark-seen|mark-unseen|blocklist|welcomelist.")],
    mail_ids: Annotated[str, Field(description="Single quarantined mail ID, or a comma-separated list of IDs, to act on.")],
    confirm: Annotated[bool, Field(description="False (default) returns a dry-run PLAN; True executes the mutation.")] = False,
) -> dict:
    """MUTATION (MEDIUM; HIGH for action='delete' — permanent, irreversible). Apply an action to
    quarantined message(s). Dry-run by default; confirm=True to execute. Needs PROXIMO_PMG_* config.

    action: deliver|delete|mark-seen|mark-unseen|blocklist|welcomelist. Get mail_ids from
    pmg_quarantine_spam (or the virus/attachment quarantine lists). Dry-run returns a PLAN;
    confirm=True executes and returns {"status": "ok", "result": ...}.
    """
    _, pmg = _proximo_server._pmg()
    tgt = "pmg/quarantine/content"
    plan = _plan("pmg_quarantine_action", tgt,
                 lambda: pmg_plan_quarantine_action(action, mail_ids))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_quarantine_action", tgt,
                    lambda: pmg_quarantine_action_op(pmg, action, mail_ids),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "action": action, "mail_ids": mail_ids})


@tool()
def pmg_postfix_qshape(node: Annotated[str | None, Field(description="PMG node name; defaults to the configured node.")] = None) -> list[dict]:
    """READ-ONLY: get PMG Postfix queue shape. Needs PROXIMO_PMG_* config.

    Returns a list of dicts, one row per domain plus a TOTAL row, each with queue-age bucket
    counts. To force immediate re-delivery of the queued mail use pmg_postfix_flush.
    """
    cfg, pmg = _proximo_server._pmg()
    n = node or cfg.node
    return _audited("pmg_postfix_qshape", f"pmg/{n}/postfix/qshape",
                    lambda: pmg_postfix_qshape_op(pmg, n))


@tool()
def pmg_postfix_flush(
    node: Annotated[str | None, Field(description="PMG node name; defaults to the configured node.")] = None,
    confirm: Annotated[bool, Field(description="False (default) returns a dry-run PLAN; True executes the mutation.")] = False,
) -> dict:
    """MUTATION (LOW): flush all Postfix queues (immediate re-delivery attempt). Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    Dry-run returns a PLAN; confirm=True executes and returns {"status": "ok", "result": ...}.
    Triggers redelivery attempts only — does not clear or drop queued mail. Check queue state
    with pmg_postfix_qshape before and after.
    """
    cfg, pmg = _proximo_server._pmg()
    n = node or cfg.node
    tgt = f"pmg/{n}/postfix/flush_queues"
    plan = _plan("pmg_postfix_flush", tgt,
                 lambda: pmg_plan_postfix_flush(n))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_postfix_flush", tgt,
                    lambda: pmg_postfix_flush_op(pmg, n),
                    mutation=True, outcome="ok", detail={"confirmed": True, "node": n})


@tool()
def pmg_spam_config() -> dict:
    """READ-ONLY: get PMG spam filter configuration. Needs PROXIMO_PMG_* config.

    Returns a dict of the current spam-filter settings (score thresholds, Bayes/AWL/Razor/RBL
    toggles, etc). Use pmg_spam_config_update to change them.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_spam_config", "pmg/config/spam",
                    lambda: pmg_spam_config_op(pmg))


@tool()
def pmg_service_status(
    service: Annotated[str, Field(description="PMG service name, e.g. postfix, pmgproxy, pmgdaemon, pmgmirror, pmgtunnel, pmg-smtp-filter, clamav, spamassassin.")],
    node: Annotated[str | None, Field(description="PMG node name; defaults to the configured node.")] = None,
) -> dict:
    """READ-ONLY: get the status of a PMG system service. Needs PROXIMO_PMG_* config.

    Returns a dict with the service's state. service: e.g. 'postfix', 'pmgproxy', 'pmgdaemon',
    'clamav', 'spamassassin' — no hardcoded enum, unknown names return a PMG 404. Use
    pmg_service_control to start/stop/restart/reload the service.
    """
    cfg, pmg = _proximo_server._pmg()
    n = node or cfg.node
    return _audited("pmg_service_status", f"pmg/{n}/services/{service}",
                    lambda: pmg_service_status_op(pmg, service, n))


@tool()
def pmg_domain_create(
    domain: Annotated[str, Field(description="Domain name to add as a managed mail domain, e.g. 'example.com'.")],
    comment: Annotated[str | None, Field(description="Optional free-text comment stored with the domain.")] = None,
    confirm: Annotated[bool, Field(description="False (default) returns a dry-run PLAN; True executes the mutation.")] = False,
) -> dict:
    """MUTATION (LOW): create a managed mail domain. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    domain: domain name to add (e.g. 'example.com'). Dry-run returns a PLAN; confirm=True executes
    and returns {"status": "ok", "result": ...}. Additive — reverse with pmg_domain_delete; list
    current domains with pmg_domains_list.
    """
    _, pmg = _proximo_server._pmg()
    tgt = "pmg/config/domains"
    plan = _plan("pmg_domain_create", tgt,
                 lambda: pmg_plan_domain_create(domain, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_domain_create", tgt,
                    lambda: pmg_domain_create_op(pmg, domain, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True, "domain": domain})


@tool()
def pmg_domain_delete(
    domain: Annotated[str, Field(description="Managed mail domain name to delete, e.g. 'example.com'.")],
    confirm: Annotated[bool, Field(description="False (default) returns a dry-run PLAN; True executes the mutation.")] = False,
) -> dict:
    """MUTATION (MEDIUM): delete a managed mail domain. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    Mail routing rules referencing this domain may break — review before confirming. No UNDO
    primitive; recreate with pmg_domain_create if needed. Dry-run returns a PLAN; confirm=True
    executes and returns {"status": "ok", "result": ...}.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/domains/{domain}"
    plan = _plan("pmg_domain_delete", tgt,
                 lambda: pmg_plan_domain_delete(domain))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_domain_delete", tgt,
                    lambda: pmg_domain_delete_op(pmg, domain),
                    mutation=True, outcome="ok", detail={"confirmed": True, "domain": domain})


@tool()
def pmg_transport_create(
    domain: Annotated[str, Field(description="Destination domain the transport rule applies to.")],
    host: Annotated[str, Field(description="Next-hop relay hostname or IP for mail to this domain.")],
    comment: Annotated[str | None, Field(description="Optional free-text comment stored with the transport rule.")] = None,
    port: Annotated[int, Field(description="TCP port to connect to on the relay host, 1-65535 (default 25).")] = 25,
    protocol: Annotated[str, Field(description="Transport protocol: smtp|lmtp (default smtp).")] = "smtp",
    use_mx: Annotated[bool, Field(description="Whether to use MX lookup for the relay host (default True).")] = True,
    confirm: Annotated[bool, Field(description="False (default) returns a dry-run PLAN; True executes the mutation.")] = False,
) -> dict:
    """MUTATION (LOW): create a mail transport rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    Dry-run returns a PLAN; confirm=True executes and returns {"status": "ok", "result": ...}.
    Additive — reverse with pmg_transport_delete. Overrides MX-based routing for the given domain.
    """
    _, pmg = _proximo_server._pmg()
    tgt = "pmg/config/transport"
    plan = _plan("pmg_transport_create", tgt,
                 lambda: pmg_plan_transport_create(domain, host, comment, port, protocol, use_mx))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_transport_create", tgt,
                    lambda: pmg_transport_create_op(pmg, domain, host, comment, port, protocol, use_mx),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "domain": domain, "host": host})


@tool()
def pmg_transport_delete(
    domain: Annotated[str, Field(description="Destination domain whose transport rule should be deleted.")],
    confirm: Annotated[bool, Field(description="False (default) returns a dry-run PLAN; True executes the mutation.")] = False,
) -> dict:
    """MUTATION (MEDIUM): delete a mail transport rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    Mail for the domain falls back to default PMG routing (MX lookup) afterward. No UNDO
    primitive; recreate with pmg_transport_create if needed. Dry-run returns a PLAN; confirm=True
    executes and returns {"status": "ok", "result": ...}.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/transport/{domain}"
    plan = _plan("pmg_transport_delete", tgt,
                 lambda: pmg_plan_transport_delete(domain))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_transport_delete", tgt,
                    lambda: pmg_transport_delete_op(pmg, domain),
                    mutation=True, outcome="ok", detail={"confirmed": True, "domain": domain})


@tool()
def pmg_mynetworks_add(
    cidr: Annotated[str, Field(description="Network in CIDR notation to trust as an internal relay, e.g. '10.0.0.0/8'.")],
    comment: Annotated[str | None, Field(description="Optional free-text comment stored with the mynetworks entry.")] = None,
    confirm: Annotated[bool, Field(description="False (default) returns a dry-run PLAN; True executes the mutation.")] = False,
) -> dict:
    """MUTATION (LOW): add a CIDR to the PMG mynetworks trusted relay list. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    Only add CIDRs you control — trusted networks bypass spam filtering. Additive — reverse with
    pmg_mynetworks_remove. Dry-run returns a PLAN; confirm=True executes and returns
    {"status": "ok", "result": ...}.
    """
    _, pmg = _proximo_server._pmg()
    tgt = "pmg/config/mynetworks"
    plan = _plan("pmg_mynetworks_add", tgt,
                 lambda: pmg_plan_mynetworks_add(cidr, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_mynetworks_add", tgt,
                    lambda: pmg_mynetworks_add_op(pmg, cidr, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True, "cidr": cidr})


@tool()
def pmg_mynetworks_remove(
    cidr: Annotated[str, Field(description="Network in CIDR notation to remove from the trusted mynetworks list.")],
    confirm: Annotated[bool, Field(description="False (default) returns a dry-run PLAN; True executes the mutation.")] = False,
) -> dict:
    """MUTATION (MEDIUM): remove a CIDR from the PMG mynetworks trusted relay list. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    Internal senders in the range become subject to spam filtering after removal. No UNDO
    primitive; re-add with pmg_mynetworks_add if needed. Dry-run returns a PLAN; confirm=True
    executes and returns {"status": "ok", "result": ...}.
    """
    _, pmg = _proximo_server._pmg()
    tgt = f"pmg/config/mynetworks/{cidr}"
    plan = _plan("pmg_mynetworks_remove", tgt,
                 lambda: pmg_plan_mynetworks_remove(cidr))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_mynetworks_remove", tgt,
                    lambda: pmg_mynetworks_remove_op(pmg, cidr),
                    mutation=True, outcome="ok", detail={"confirmed": True, "cidr": cidr})


@tool()
def pmg_spam_config_update(
    bounce_score: Annotated[int | None, Field(description="Spam score threshold added for bounce/NDR-shaped messages; omit to leave unchanged.")] = None,
    clamav_heuristic_score: Annotated[int | None, Field(description="Spam score added when ClamAV heuristic detection fires; omit to leave unchanged.")] = None,
    extract_text: Annotated[bool | None, Field(description="Whether to extract text from attachments for spam scanning; omit to leave unchanged.")] = None,
    languages: Annotated[str | None, Field(description="Space-separated language codes used for spam language-based scoring; omit to leave unchanged.")] = None,
    maxspamsize: Annotated[int | None, Field(description="Maximum message size in bytes scanned for spam; omit to leave unchanged.")] = None,
    rbl_checks: Annotated[bool | None, Field(description="Whether to enable RBL (realtime blocklist) checks; omit to leave unchanged.")] = None,
    use_awl: Annotated[bool | None, Field(description="Whether to enable the auto-whitelist; omit to leave unchanged.")] = None,
    use_bayes: Annotated[bool | None, Field(description="Whether to enable Bayesian spam classification; omit to leave unchanged.")] = None,
    use_razor: Annotated[bool | None, Field(description="Whether to enable Razor collaborative spam filtering; omit to leave unchanged.")] = None,
    wl_bounce_relays: Annotated[str | None, Field(description="Whitelisted bounce-relay hosts, space-separated; omit to leave unchanged.")] = None,
    delete: Annotated[str | None, Field(description="Comma-separated field names to reset to their PMG defaults.")] = None,
    confirm: Annotated[bool, Field(description="False (default) returns a dry-run PLAN; True executes the mutation.")] = False,
) -> dict:
    """MUTATION (MEDIUM): update PMG spam filter configuration. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    Only non-None fields are sent — omitted fields keep their current PMG value; delete resets
    named fields to defaults, effective immediately on new inbound mail. Read current values with
    pmg_spam_config. Dry-run returns a PLAN; confirm=True executes and returns {"status": "ok",
    "result": ...}.
    """
    _, pmg = _proximo_server._pmg()
    tgt = "pmg/config/spam"
    # Build the filtered kwargs once; share between plan and execute paths.
    kwargs = {k: v for k, v in {
        "bounce_score": bounce_score,
        "clamav_heuristic_score": clamav_heuristic_score,
        "extract_text": extract_text,
        "languages": languages,
        "maxspamsize": maxspamsize,
        "rbl_checks": rbl_checks,
        "use_awl": use_awl,
        "use_bayes": use_bayes,
        "use_razor": use_razor,
        "wl_bounce_relays": wl_bounce_relays,
        "delete": delete,
    }.items() if v is not None}
    plan = _plan("pmg_spam_config_update", tgt,
                 lambda: pmg_plan_spam_config_update(**kwargs))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_spam_config_update", tgt,
                    lambda: pmg_spam_config_update_op(pmg, **kwargs),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pmg_quarantine_welcomelist_list(pmail: Annotated[str | None, Field(description="Scope the welcomelist read to this user's mailbox; defaults to the authenticated PMG user.")] = None) -> list[dict]:
    """READ-ONLY: list PMG quarantine welcomelist entries. Optional pmail to scope to one user.
    Needs PROXIMO_PMG_* config.

    Returns a list of welcomelist-entry dicts; pmail defaults to the authenticated user when
    omitted. For the blocklist use pmg_quarantine_blocklist_list. Use
    pmg_quarantine_welcomelist_add/pmg_quarantine_welcomelist_remove to manage entries.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_quarantine_welcomelist_list", "pmg/quarantine/welcomelist",
                    lambda: pmg_quarantine_welcomelist_list_op(pmg, pmail))


@tool()
def pmg_quarantine_welcomelist_add(
    address: Annotated[str, Field(description="Email address to add to the quarantine welcomelist.")],
    pmail: Annotated[str | None, Field(description="Scope the welcomelist entry to this user's mailbox; defaults to the authenticated PMG user.")] = None,
    confirm: Annotated[bool, Field(description="False (default) returns a dry-run PLAN; True executes the mutation.")] = False,
) -> dict:
    """MUTATION (LOW): add an address to the quarantine welcomelist. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    pmail: optional per-user scope (defaults to authenticated user). Additive — reverse with
    pmg_quarantine_welcomelist_remove. Dry-run returns a PLAN; confirm=True executes and returns
    {"status": "ok", "result": ...}.
    """
    _, pmg = _proximo_server._pmg()
    tgt = "pmg/quarantine/welcomelist"
    plan = _plan("pmg_quarantine_welcomelist_add", tgt,
                 lambda: pmg_plan_quarantine_welcomelist_add(address, pmail, pmg.config.username))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_quarantine_welcomelist_add", tgt,
                    lambda: pmg_quarantine_welcomelist_add_op(pmg, address, pmail),
                    mutation=True, outcome="ok", detail={"confirmed": True, "address": address})


@tool()
def pmg_quarantine_welcomelist_remove(
    address: Annotated[str, Field(description="Email address to remove from the quarantine welcomelist.")],
    pmail: Annotated[str | None, Field(description="Scope the welcomelist removal to this user's mailbox; defaults to the authenticated PMG user.")] = None,
    confirm: Annotated[bool, Field(description="False (default) returns a dry-run PLAN; True executes the mutation.")] = False,
) -> dict:
    """MUTATION (LOW): remove an address from the quarantine welcomelist. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    pmail: optional per-user scope (defaults to authenticated user). No UNDO primitive; re-add
    with pmg_quarantine_welcomelist_add if needed. Dry-run returns a PLAN; confirm=True executes
    and returns {"status": "ok", "result": ...}.
    """
    _, pmg = _proximo_server._pmg()
    tgt = "pmg/quarantine/welcomelist"
    plan = _plan("pmg_quarantine_welcomelist_remove", tgt,
                 lambda: pmg_plan_quarantine_welcomelist_remove(address, pmail, pmg.config.username))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_quarantine_welcomelist_remove", tgt,
                    lambda: pmg_quarantine_welcomelist_remove_op(pmg, address, pmail),
                    mutation=True, outcome="ok", detail={"confirmed": True, "address": address})


@tool()
def pmg_quarantine_blocklist_remove(
    address: Annotated[str, Field(description="Email address to remove from the quarantine blocklist.")],
    pmail: Annotated[str | None, Field(description="Scope the blocklist removal to this user's mailbox; defaults to the authenticated PMG user.")] = None,
    confirm: Annotated[bool, Field(description="False (default) returns a dry-run PLAN; True executes the mutation.")] = False,
) -> dict:
    """MUTATION (LOW): remove an address from the quarantine blocklist. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    pmail: optional per-user scope (defaults to authenticated user). No UNDO primitive; re-add
    with pmg_quarantine_blocklist_add if needed. Dry-run returns a PLAN; confirm=True executes
    and returns {"status": "ok", "result": ...}.
    """
    _, pmg = _proximo_server._pmg()
    tgt = "pmg/quarantine/blocklist"
    plan = _plan("pmg_quarantine_blocklist_remove", tgt,
                 lambda: pmg_plan_quarantine_blocklist_remove(address, pmail, pmg.config.username))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_quarantine_blocklist_remove", tgt,
                    lambda: pmg_quarantine_blocklist_remove_op(pmg, address, pmail),
                    mutation=True, outcome="ok", detail={"confirmed": True, "address": address})


@tool()
def pmg_service_control(
    service: Annotated[str, Field(description="PMG service name, e.g. postfix, pmgproxy, pmgdaemon, clamav, spamassassin.")],
    action: Annotated[str, Field(description="Control action: start|stop|restart|reload.")],
    node: Annotated[str | None, Field(description="PMG node name; defaults to the configured node.")] = None,
    confirm: Annotated[bool, Field(description="False (default) returns a dry-run PLAN; True executes the mutation.")] = False,
) -> dict:
    """MUTATION (MEDIUM): start, stop, restart, or reload a PMG service. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    WARNING: stop on postfix/pmgproxy/pmgdaemon interrupts mail delivery until manually restarted.
    Check current state first with pmg_service_status. Dry-run returns a PLAN; confirm=True
    executes and returns {"status": "ok", "result": ...}.
    """
    cfg, pmg = _proximo_server._pmg()
    n = node or cfg.node
    tgt = f"pmg/{n}/services/{service}/{action}"
    plan = _plan("pmg_service_control", tgt,
                 lambda: pmg_plan_service_control(service, action, n))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_service_control", tgt,
                    lambda: pmg_service_control_op(pmg, service, action, n),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "service": service, "action": action, "node": n})


@tool()
def pmg_tracker_list(
    node: Annotated[str | None, Field(description="PMG node name; defaults to the configured node.")] = None,
    start: Annotated[int | None, Field(description="Unix epoch start of the tracker window; omit for no lower bound.")] = None,
    end: Annotated[int | None, Field(description="Unix epoch end of the tracker window; omit for no upper bound.")] = None,
    from_: Annotated[str | None, Field(description="Filter by envelope sender address.")] = None,
    target: Annotated[str | None, Field(description="Filter by recipient address.")] = None,
    xfilter: Annotated[str | None, Field(description="Free-text filter applied to tracker entries.")] = None,
    ndr: Annotated[bool | None, Field(description="If set, filter to (or exclude) non-delivery-report entries.")] = None,
    greylist: Annotated[bool | None, Field(description="If set, filter to (or exclude) greylisted entries.")] = None,
    limit: Annotated[int, Field(description="Maximum entries to return, 0-100000 (default 2000).")] = 2000,
) -> list[dict]:
    """READ-ONLY: list mail tracking entries. Needs PROXIMO_PMG_* config.

    Returns a list of dicts, one per tracked message (up to `limit`, default 2000). Use
    pmg_tracker_detail for the full delivery trace of one message ID from this list.
    """
    cfg, pmg = _proximo_server._pmg()
    n = node or cfg.node
    return _audited("pmg_tracker_list", f"pmg/{n}/tracker",
                    lambda: pmg_tracker_list_op(pmg, n, start, end, from_,
                                                target, xfilter, ndr, greylist, limit))


@tool()
def pmg_tracker_detail(
    id_: Annotated[str, Field(description="Mail/queue tracker ID to fetch detail for.")],
    node: Annotated[str | None, Field(description="PMG node name; defaults to the configured node.")] = None,
    start: Annotated[int | None, Field(description="Unix epoch start of the tracker window; omit for no lower bound.")] = None,
    end: Annotated[int | None, Field(description="Unix epoch end of the tracker window; omit for no upper bound.")] = None,
) -> list[dict]:
    """READ-ONLY: get tracking detail for a specific mail ID. Needs PROXIMO_PMG_* config.

    Returns a list of delivery-hop dicts for that message. Get id_ from pmg_tracker_list first;
    it is validated path-segment-safe (rejects '..', '/', control/whitespace chars).
    """
    cfg, pmg = _proximo_server._pmg()
    n = node or cfg.node
    return _audited("pmg_tracker_detail", f"pmg/{n}/tracker/{id_}",
                    lambda: pmg_tracker_detail_op(pmg, n, id_, start, end))


@tool()
def pmg_quarantine_virus(
    pmail: Annotated[str | None, Field(description="Scope the virus quarantine read to this user's mailbox; defaults to the authenticated PMG user.")] = None,
    start: Annotated[int | None, Field(description="Unix epoch start of the window; omit for no lower bound.")] = None,
    end: Annotated[int | None, Field(description="Unix epoch end of the window; omit for no upper bound.")] = None,
) -> list[dict]:
    """READ-ONLY: list virus quarantine entries. Needs PROXIMO_PMG_* config.

    Returns a list of dicts, one per quarantined virus message. pmail defaults to the
    authenticated user when omitted. For spam quarantine use pmg_quarantine_spam; to act on
    entries use pmg_quarantine_action.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_quarantine_virus", "pmg/quarantine/virus",
                    lambda: pmg_quarantine_virus_op(pmg, pmail, start, end))


@tool()
def pmg_quarantine_attachment(
    pmail: Annotated[str | None, Field(description="Scope the attachment quarantine read to this user's mailbox; defaults to the authenticated PMG user.")] = None,
    start: Annotated[int | None, Field(description="Unix epoch start of the window; omit for no lower bound.")] = None,
    end: Annotated[int | None, Field(description="Unix epoch end of the window; omit for no upper bound.")] = None,
) -> list[dict]:
    """READ-ONLY: list attachment quarantine entries. Needs PROXIMO_PMG_* config.

    Returns a list of dicts, one per quarantined attachment. pmail defaults to the authenticated
    user when omitted. For spam quarantine use pmg_quarantine_spam; to act on entries use
    pmg_quarantine_action.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_quarantine_attachment", "pmg/quarantine/attachment",
                    lambda: pmg_quarantine_attachment_op(pmg, pmail, start, end))


@tool()
def pmg_quarantine_virusstatus() -> dict:
    """READ-ONLY: get virus quarantine status summary. Needs PROXIMO_PMG_* config.

    Returns a dict of summary counts. For the individual quarantined messages use
    pmg_quarantine_virus instead.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_quarantine_virusstatus", "pmg/quarantine/virusstatus",
                    lambda: pmg_quarantine_virusstatus_op(pmg))


@tool()
def pmg_quarantine_spamstatus() -> dict:
    """READ-ONLY: get spam quarantine status summary. Needs PROXIMO_PMG_* config.

    Returns a dict of summary counts. For the individual quarantined messages use
    pmg_quarantine_spam instead.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_quarantine_spamstatus", "pmg/quarantine/spamstatus",
                    lambda: pmg_quarantine_spamstatus_op(pmg))


@tool()
def pmg_quarantine_spamusers(
    start: Annotated[int | None, Field(description="Unix epoch start of the window; omit for no lower bound.")] = None,
    end: Annotated[int | None, Field(description="Unix epoch end of the window; omit for no upper bound.")] = None,
    quarantine_type: Annotated[str, Field(description="Quarantine type to list users for: spam|virus|attachment (default spam).")] = "spam",
) -> list[dict]:
    """READ-ONLY: list users with quarantined mail entries. Needs PROXIMO_PMG_* config.

    Returns a list of per-user dicts. quarantine_type: spam|virus|attachment (default spam) —
    sent to the PMG API as 'quarantine-type'. To list one user's messages use pmg_quarantine_spam
    (pmail scope) or the matching virus/attachment tool.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_quarantine_spamusers", "pmg/quarantine/spamusers",
                    lambda: pmg_quarantine_spamusers_op(pmg, start, end, quarantine_type))


@tool()
def pmg_statistics_mailcount(
    start: Annotated[int | None, Field(description="Unix epoch start of the window; omit for no lower bound.")] = None,
    end: Annotated[int | None, Field(description="Unix epoch end of the window; omit for no upper bound.")] = None,
    timespan: Annotated[int, Field(description="Histogram bucket size in seconds, 3600-31622400 (default 3600 = 1 hour).")] = 3600,
) -> list[dict]:
    """READ-ONLY: get per-bucket mail count statistics. Needs PROXIMO_PMG_* config.

    Returns a list of time-bucketed count dicts (bucket size set by timespan, default 1 hour).
    For today's single aggregate total use pmg_statistics_mail instead.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_statistics_mailcount", "pmg/statistics/mailcount",
                    lambda: pmg_statistics_mailcount_op(pmg, start, end, timespan))


@tool()
def pmg_statistics_sender(
    start: Annotated[int | None, Field(description="Unix epoch start of the window; omit for no lower bound.")] = None,
    end: Annotated[int | None, Field(description="Unix epoch end of the window; omit for no upper bound.")] = None,
    filter_: Annotated[str | None, Field(description="Optional search string to filter senders.")] = None,
    orderby: Annotated[str | None, Field(description="Accepted for compatibility but ignored — PMG 9.1 rejects orderby on this endpoint.")] = None,
) -> list[dict]:
    """READ-ONLY: get per-sender mail statistics. Needs PROXIMO_PMG_* config.

    Returns a list of per-sender stat dicts. orderby is accepted for compatibility but IGNORED —
    PMG rejects it here (HTTP 400) unlike pmg_statistics_receiver, which does honor it. For
    per-recipient stats use pmg_statistics_receiver.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_statistics_sender", "pmg/statistics/sender",
                    lambda: pmg_statistics_sender_op(pmg, start, end, filter_, orderby))


@tool()
def pmg_statistics_receiver(
    start: Annotated[int | None, Field(description="Unix epoch start of the window; omit for no lower bound.")] = None,
    end: Annotated[int | None, Field(description="Unix epoch end of the window; omit for no upper bound.")] = None,
    filter_: Annotated[str | None, Field(description="Optional search string to filter recipients.")] = None,
    orderby: Annotated[str | None, Field(description="Raw sort spec passed through to the PMG API.")] = None,
) -> list[dict]:
    """READ-ONLY: get per-recipient mail statistics. Needs PROXIMO_PMG_* config.

    Returns a list of per-recipient stat dicts. orderby is a raw sort-spec passthrough here
    (unlike pmg_statistics_sender, which ignores it). For per-sender stats use
    pmg_statistics_sender.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_statistics_receiver", "pmg/statistics/receiver",
                    lambda: pmg_statistics_receiver_op(pmg, start, end, filter_, orderby))


@tool()
def pmg_node_syslog(
    node: Annotated[str | None, Field(description="PMG node name; defaults to the configured node.")] = None,
    limit: Annotated[int | None, Field(description="Maximum syslog entries to return.")] = None,
    service: Annotated[str | None, Field(description="Filter syslog entries by service name.")] = None,
    since: Annotated[str | None, Field(description="Only return entries at or after this time (journalctl-style time spec).")] = None,
    until: Annotated[str | None, Field(description="Only return entries at or before this time (journalctl-style time spec).")] = None,
    start: Annotated[int | None, Field(description="Pagination offset into the syslog entries.")] = None,
) -> list[dict]:
    """READ-ONLY: get PMG node syslog entries. Needs PROXIMO_PMG_* config.

    Returns a list of log-entry dicts. For a PVE hypervisor node's syslog use pve_node_syslog
    instead; for RRD performance data use pmg_node_rrddata.
    """
    cfg, pmg = _proximo_server._pmg()
    n = node or cfg.node
    return _audited("pmg_node_syslog", f"pmg/{n}/syslog",
                    lambda: pmg_node_syslog_op(pmg, n, limit, service, since, until, start))


@tool()
def pmg_node_rrddata(
    timeframe: Annotated[str, Field(description="RRD timeframe: hour|day|week|month|year.")],
    node: Annotated[str | None, Field(description="PMG node name; defaults to the configured node.")] = None,
    cf: Annotated[str | None, Field(description="RRD consolidation function: AVERAGE|MAX.")] = None,
) -> list[dict]:
    """READ-ONLY: get PMG node RRD performance data. Needs PROXIMO_PMG_* config.

    Returns a list of time-series dicts over the given timeframe (hour|day|week|month|year). For
    a PVE hypervisor node's RRD data use pve_node_rrddata instead.
    """
    cfg, pmg = _proximo_server._pmg()
    n = node or cfg.node
    return _audited("pmg_node_rrddata", f"pmg/{n}/rrddata",
                    lambda: pmg_node_rrddata_op(pmg, n, timeframe, cf))


@tool()
def pmg_tasks_list(
    node: Annotated[str | None, Field(description="PMG node name; defaults to the configured node.")] = None,
    start: Annotated[int | None, Field(description="Pagination offset into the task list.")] = None,
    limit: Annotated[int | None, Field(description="Maximum tasks to return.")] = None,
    userfilter: Annotated[str | None, Field(description="Filter tasks by the user that started them.")] = None,
    errors: Annotated[bool | None, Field(description="If True, return only failed tasks.")] = None,
    typefilter: Annotated[str | None, Field(description="Filter tasks by task type.")] = None,
    since: Annotated[int | None, Field(description="Unix epoch: only tasks started at or after this time.")] = None,
    until: Annotated[int | None, Field(description="Unix epoch: only tasks started at or before this time.")] = None,
    statusfilter: Annotated[str | None, Field(description="Filter tasks by status text.")] = None,
) -> list[dict]:
    """READ-ONLY: list PMG tasks on a node. Needs PROXIMO_PMG_* config.

    Returns a list of task dicts. errors=True returns only failed tasks. For a PVE hypervisor
    node's tasks use pve_tasks_list instead.
    """
    cfg, pmg = _proximo_server._pmg()
    n = node or cfg.node
    return _audited("pmg_tasks_list", f"pmg/{n}/tasks",
                    lambda: pmg_tasks_list_op(pmg, n, start, limit, userfilter,
                                              errors, typefilter, since, until, statusfilter))


@tool()
def pmg_backup_create(
    node: Annotated[str | None, Field(description="PMG node name; defaults to the configured node.")] = None,
    notify: Annotated[str, Field(description="Notification mode: always|error|never (default never).")] = "never",
    statistic: Annotated[bool, Field(description="Whether to include mail statistics in the backup (default True).")] = True,
    confirm: Annotated[bool, Field(description="False (default) returns a dry-run PLAN; True executes the mutation.")] = False,
) -> dict:
    """MUTATION (LOW): create a PMG configuration backup. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    Additive — writes a new backup .tar.gz to /var/lib/pmg/backup/ on the target node; does not
    touch existing backups or live config. Dry-run returns a PLAN; confirm=True executes and
    returns {"status": "ok", "result": ...}.
    """
    cfg, pmg = _proximo_server._pmg()
    n = node or cfg.node
    tgt = f"pmg/{n}/backup"
    plan = _plan("pmg_backup_create", tgt,
                 lambda: pmg_plan_backup_create(n, notify, statistic))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_backup_create", tgt,
                    lambda: pmg_backup_create_op(pmg, n, notify, statistic),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "node": n, "notify": notify})


@tool()
def pmg_ruledb_rules_list() -> list[dict]:
    """READ-ONLY: list all PMG RuleDB rules (hydrated rule list). Needs PROXIMO_PMG_* config.

    Returns the full hydrated rule list as dicts, including from/to/what/when/actions for each
    rule. For one rule use pmg_ruledb_rule_get; to detect drift without the full fetch use
    pmg_ruledb_digest.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_ruledb_rules_list", "pmg/config/ruledb/rules",
                    lambda: pmg_ruledb_rules_list_op(pmg))


@tool()
def pmg_ruledb_rule_get(id_: Annotated[str, Field(description="RuleDB rule ID (positive integer string, e.g. '100').")]) -> dict:
    """READ-ONLY: get a PMG RuleDB rule's configuration. Needs PROXIMO_PMG_* config.

    Returns a dict of the rule's config. id_: rule ID (e.g. '100') from pmg_ruledb_rules_list.
    For the rule's individual from/to/what/when object lists use pmg_ruledb_rule_from_list and
    its to/what/when/actions siblings.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_ruledb_rule_get", f"pmg/config/ruledb/rules/{id_}/config",
                    lambda: pmg_ruledb_rule_get_op(pmg, id_))


@tool()
def pmg_ruledb_rule_from_list(id_: Annotated[str, Field(description="RuleDB rule ID (positive integer string, e.g. '100').")]) -> list[dict]:
    """READ-ONLY: list the 'from' objects attached to a PMG RuleDB rule. Needs PROXIMO_PMG_* config.

    Returns a list of object dicts. id_: rule ID (e.g. '100') from pmg_ruledb_rules_list. Use
    pmg_ruledb_rule_to_list for the 'to' side, and the what/when/actions counterparts for the rest.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_ruledb_rule_from_list", f"pmg/config/ruledb/rules/{id_}/from",
                    lambda: pmg_ruledb_rule_from_list_op(pmg, id_))


@tool()
def pmg_ruledb_rule_to_list(id_: Annotated[str, Field(description="RuleDB rule ID (positive integer string, e.g. '100').")]) -> list[dict]:
    """READ-ONLY: list the 'to' objects attached to a PMG RuleDB rule. Needs PROXIMO_PMG_* config.

    Returns a list of object dicts. id_: rule ID (e.g. '100') from pmg_ruledb_rules_list. Use
    pmg_ruledb_rule_from_list for the 'from' side, and the what/when/actions counterparts for the rest.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_ruledb_rule_to_list", f"pmg/config/ruledb/rules/{id_}/to",
                    lambda: pmg_ruledb_rule_to_list_op(pmg, id_))


@tool()
def pmg_ruledb_rule_what_list(id_: Annotated[str, Field(description="RuleDB rule ID (positive integer string, e.g. '100').")]) -> list[dict]:
    """READ-ONLY: list the 'what' objects attached to a PMG RuleDB rule. Needs PROXIMO_PMG_* config.

    Returns a list of object dicts. id_: rule ID (e.g. '100') from pmg_ruledb_rules_list. Use
    pmg_ruledb_rule_when_list for the 'when' side, and the from/to/actions counterparts for the rest.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_ruledb_rule_what_list", f"pmg/config/ruledb/rules/{id_}/what",
                    lambda: pmg_ruledb_rule_what_list_op(pmg, id_))


@tool()
def pmg_ruledb_rule_when_list(id_: Annotated[str, Field(description="RuleDB rule ID (positive integer string, e.g. '100').")]) -> list[dict]:
    """READ-ONLY: list the 'when' objects attached to a PMG RuleDB rule. Needs PROXIMO_PMG_* config.

    Returns a list of object dicts. id_: rule ID (e.g. '100') from pmg_ruledb_rules_list. Use
    pmg_ruledb_rule_what_list for the 'what' side, and the from/to/actions counterparts for the rest.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_ruledb_rule_when_list", f"pmg/config/ruledb/rules/{id_}/when",
                    lambda: pmg_ruledb_rule_when_list_op(pmg, id_))


@tool()
def pmg_ruledb_rule_actions_list(id_: Annotated[str, Field(description="RuleDB rule ID (positive integer string, e.g. '100').")]) -> list[dict]:
    """READ-ONLY: list the 'actions' objects attached to a PMG RuleDB rule. Needs PROXIMO_PMG_* config.

    Returns a list of action-object dicts, extracted from the same config pmg_ruledb_rule_get
    returns — the dedicated .../actions endpoint 501s on PMG 9.1, so this reads /config instead.
    id_: rule ID (e.g. '100') from pmg_ruledb_rules_list.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_ruledb_rule_actions_list", f"pmg/config/ruledb/rules/{id_}/config",
                    lambda: pmg_ruledb_rule_actions_list_op(pmg, id_))


@tool()
def pmg_who_groups_list() -> list[dict]:
    """READ-ONLY: list all PMG RuleDB 'who' object groups. Needs PROXIMO_PMG_* config.

    Returns a list of group dicts (id/name/comment). For 'what' or 'when' groups use
    pmg_what_groups_list / pmg_when_groups_list. Use pmg_who_group_get for one group's config.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_who_groups_list", "pmg/config/ruledb/who",
                    lambda: pmg_who_groups_list_op(pmg))


@tool()
def pmg_who_group_get(ogroup: Annotated[str, Field(description="'who' object group numeric ID (e.g. '2') from pmg_who_groups_list — not the group name.")]) -> dict:
    """READ-ONLY: get a PMG RuleDB 'who' object group's configuration. Needs PROXIMO_PMG_* config.

    Returns a dict of the group's config. ogroup: numeric ID (e.g. '2') from pmg_who_groups_list —
    NOT the group name. Use pmg_who_group_objects to list the objects inside the group.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_who_group_get", f"pmg/config/ruledb/who/{ogroup}/config",
                    lambda: pmg_who_group_get_op(pmg, ogroup))


@tool()
def pmg_who_group_objects(ogroup: Annotated[str, Field(description="'who' object group numeric ID (e.g. '2') from pmg_who_groups_list — not the group name.")]) -> list[dict]:
    """READ-ONLY: list the objects in a PMG RuleDB 'who' object group. Needs PROXIMO_PMG_* config.

    Returns a list of object dicts. ogroup: numeric ID (e.g. '2') from pmg_who_groups_list — NOT
    the group name. Use pmg_who_group_get for the group's own config (not its member objects).
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_who_group_objects", f"pmg/config/ruledb/who/{ogroup}/objects",
                    lambda: pmg_who_group_objects_op(pmg, ogroup))


@tool()
def pmg_what_groups_list() -> list[dict]:
    """READ-ONLY: list all PMG RuleDB 'what' object groups. Needs PROXIMO_PMG_* config.

    Returns a list of group dicts (id/name/comment). For 'who' or 'when' groups use
    pmg_who_groups_list / pmg_when_groups_list. Use pmg_what_group_get for one group's config.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_what_groups_list", "pmg/config/ruledb/what",
                    lambda: pmg_what_groups_list_op(pmg))


@tool()
def pmg_what_group_get(ogroup: Annotated[str, Field(description="'what' object group numeric ID (e.g. '2') from pmg_what_groups_list — not the group name.")]) -> dict:
    """READ-ONLY: get a PMG RuleDB 'what' object group's configuration. Needs PROXIMO_PMG_* config.

    Returns a dict of the group's config. ogroup: numeric ID (e.g. '2') from pmg_what_groups_list —
    NOT the group name. Use pmg_what_group_objects to list the objects inside the group.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_what_group_get", f"pmg/config/ruledb/what/{ogroup}/config",
                    lambda: pmg_what_group_get_op(pmg, ogroup))


@tool()
def pmg_what_group_objects(ogroup: Annotated[str, Field(description="'what' object group numeric ID (e.g. '2') from pmg_what_groups_list — not the group name.")]) -> list[dict]:
    """READ-ONLY: list the objects in a PMG RuleDB 'what' object group. Needs PROXIMO_PMG_* config.

    Returns a list of object dicts. ogroup: numeric ID (e.g. '2') from pmg_what_groups_list — NOT
    the group name. Use pmg_what_group_get for the group's own config (not its member objects).
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_what_group_objects", f"pmg/config/ruledb/what/{ogroup}/objects",
                    lambda: pmg_what_group_objects_op(pmg, ogroup))


@tool()
def pmg_when_groups_list() -> list[dict]:
    """READ-ONLY: list all PMG RuleDB 'when' object groups. Needs PROXIMO_PMG_* config.

    Returns a list of group dicts (id/name/comment). For 'who' or 'what' groups use
    pmg_who_groups_list / pmg_what_groups_list. Use pmg_when_group_get for one group's config.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_when_groups_list", "pmg/config/ruledb/when",
                    lambda: pmg_when_groups_list_op(pmg))


@tool()
def pmg_when_group_get(ogroup: Annotated[str, Field(description="'when' object group numeric ID (e.g. '2') from pmg_when_groups_list — not the group name.")]) -> dict:
    """READ-ONLY: get a PMG RuleDB 'when' object group's configuration. Needs PROXIMO_PMG_* config.

    Returns a dict of the group's config. ogroup: numeric ID (e.g. '2') from pmg_when_groups_list —
    NOT the group name. Use pmg_when_group_objects to list the objects inside the group.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_when_group_get", f"pmg/config/ruledb/when/{ogroup}/config",
                    lambda: pmg_when_group_get_op(pmg, ogroup))


@tool()
def pmg_when_group_objects(ogroup: Annotated[str, Field(description="'when' object group numeric ID (e.g. '2') from pmg_when_groups_list — not the group name.")]) -> list[dict]:
    """READ-ONLY: list the objects in a PMG RuleDB 'when' object group. Needs PROXIMO_PMG_* config.

    Returns a list of object dicts. ogroup: numeric ID (e.g. '2') from pmg_when_groups_list — NOT
    the group name. Use pmg_when_group_get for the group's own config (not its member objects).
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_when_group_objects", f"pmg/config/ruledb/when/{ogroup}/objects",
                    lambda: pmg_when_group_objects_op(pmg, ogroup))


@tool()
def pmg_action_objects_list() -> list[dict]:
    """READ-ONLY: list all PMG RuleDB action objects, including non-editable. Needs PROXIMO_PMG_* config.

    Returns a list of dicts; each carries an 'editable' flag — non-editable ones are PMG built-ins
    and cannot be modified via the API. For one rule's attached actions use
    pmg_ruledb_rule_actions_list instead.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_action_objects_list", "pmg/config/ruledb/action/objects",
                    lambda: pmg_action_objects_list_op(pmg))


@tool()
def pmg_ruledb_digest() -> dict:
    """READ-ONLY: get the PMG RuleDB digest (change-detection hash). Needs PROXIMO_PMG_* config.

    Returns a dict with the current hash. The digest changes whenever any ruledb configuration is
    modified — poll it to detect drift cheaply instead of re-fetching pmg_ruledb_rules_list.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_ruledb_digest", "pmg/config/ruledb/digest",
                    lambda: pmg_ruledb_digest_op(pmg))
