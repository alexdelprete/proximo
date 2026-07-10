"""PMG (Proxmox Mail Gateway) operational tools: domains, relay, quarantine, postfix, spam config, statistics,
tracker, backup, and ruledb reads.

Split out of proximo.server (2026-07-02) — see proximo/server.py's module
docstring for the funnel these wrappers depend on.
"""
from __future__ import annotations

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
def pmg_doctor(node: str | None = None) -> dict:
    """PMG connectivity + credential/permission preflight (read). Checks /nodes/{node}/version
    and /access/users. A successful /version call means ticket login also succeeded —
    connectivity and credentials are proven together. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified: PMG has no /access/permissions endpoint (that is PVE-only);
    /access/users is the closest equivalent and returns the same user/role information.
    """
    cfg, pmg = _proximo_server._pmg()
    n = node or cfg.node
    return _audited("pmg_doctor", f"pmg/{n}",
                    lambda: {
                        "version": pmg_node_version_op(pmg, n),
                        "permissions": pmg_access_permissions_op(pmg),
                    })


@tool()
def pmg_node_status(node: str | None = None) -> dict:
    """Get PMG node cpu/mem/disk/uptime status (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified: /nodes/{node}/status path and response shape confirmed via
    pmg-smoke.py W1 round-trip (node_status PASS).
    """
    cfg, pmg = _proximo_server._pmg()
    n = node or cfg.node
    return _audited("pmg_node_status", f"pmg/{n}/status",
                    lambda: pmg_node_status_op(pmg, n))


@tool()
def pmg_relay_config() -> dict:
    """Get PMG SMTP relay/smarthost configuration (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified: relay/smarthost settings live at /config/mail (not /config/relay).
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_relay_config", "pmg/config/mail",
                    lambda: pmg_relay_config_op(pmg))


@tool()
def pmg_domains_list() -> list[dict]:
    """List PMG managed mail domains (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified: /config/domains path and response shape confirmed via
    pmg-smoke.py W1 round-trip and W3 full domain create/list/delete cycle.
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
    """List PMG quarantined spam messages (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified: endpoint is /quarantine/spam (not /quarantine/mails).
    For virus quarantine use pmg_quarantine_virus; for attachment use pmg_quarantine_attachment.
    To act on quarantined messages (deliver/delete/mark-seen/blocklist/welcomelist) use
    pmg_quarantine_action.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_quarantine_spam", "pmg/quarantine/spam",
                    lambda: pmg_quarantine_spam_op(pmg))


@tool()
def pmg_statistics_domains(start: int | None = None, end: int | None = None) -> list[dict]:
    """Get PMG per-domain mail statistics (read). Optional Unix epoch start/end timespan.
    Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: /statistics/domains.
    Maps start/end params → starttime/endtime query params.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_statistics_domains", "pmg/statistics/domains",
                    lambda: pmg_statistics_domains_op(pmg, start, end))


@tool()
def pmg_statistics_virus(start: int | None = None, end: int | None = None) -> list[dict]:
    """Get PMG virus statistics (read). Optional Unix epoch start/end timespan.
    Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: /statistics/virus.
    Maps start/end params → starttime/endtime query params.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_statistics_virus", "pmg/statistics/virus",
                    lambda: pmg_statistics_virus_op(pmg, start, end))


@tool()
def pmg_statistics_spamscores(start: int | None = None, end: int | None = None) -> list[dict]:
    """Get PMG spam score distribution statistics (read). Optional Unix epoch start/end timespan.
    Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: /statistics/spamscores.
    Maps start/end params → starttime/endtime query params.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_statistics_spamscores", "pmg/statistics/spamscores",
                    lambda: pmg_statistics_spamscores_op(pmg, start, end))


@tool()
def pmg_statistics_recent(hours: int = 1) -> list[dict]:
    """Get PMG recent mail statistics (read). hours: 1-24 window. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: /statistics/recent.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_statistics_recent", "pmg/statistics/recent",
                    lambda: pmg_statistics_recent_op(pmg, hours))


@tool()
def pmg_quarantine_blocklist_list(pmail: str | None = None) -> list[dict]:
    """List PMG quarantine blocklist entries (read). Optional pmail to scope to one user.
    Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: /quarantine/blocklist.
    pmail: scopes the read to one user's blocklist; ALWAYS sent, defaulting to the authenticated
    PMG user when omitted — so an empty result means "none for that user", not "none globally".
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_quarantine_blocklist_list", "pmg/quarantine/blocklist",
                    lambda: pmg_quarantine_blocklist_list_op(pmg, pmail))


@tool()
def pmg_quarantine_blocklist_add(
    address: str,
    pmail: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (LOW): add an address to the quarantine blocklist. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: POST /quarantine/blocklist.
    pmail: scope to a per-user blocklist (optional).
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
    action: str,
    mail_ids: str,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM; HIGH for action='delete' — permanent, irreversible). Apply an action to
    quarantined message(s). Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    action: one of deliver|delete|mark-seen|mark-unseen|blocklist|welcomelist.
    mail_ids: single mail ID or comma-separated list.
    PMG 9.1 live-proven 2026-06-26: POST /quarantine/content — delete and deliver
    both confirmed against real quarantined GTUBE messages.
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
def pmg_postfix_qshape(node: str | None = None) -> list[dict]:
    """Get PMG Postfix queue shape (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified: /nodes/{node}/postfix/qshape returns a list of
    dicts (one row per domain + a TOTAL row with queue-age bucket counts).
    """
    cfg, pmg = _proximo_server._pmg()
    n = node or cfg.node
    return _audited("pmg_postfix_qshape", f"pmg/{n}/postfix/qshape",
                    lambda: pmg_postfix_qshape_op(pmg, n))


@tool()
def pmg_postfix_flush(node: str | None = None, confirm: bool = False) -> dict:
    """MUTATION (LOW): flush all Postfix queues (immediate re-delivery attempt). Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: POST /nodes/{node}/postfix/flush_queues.
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
    """Get PMG spam filter configuration (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: /config/spam.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_spam_config", "pmg/config/spam",
                    lambda: pmg_spam_config_op(pmg))


@tool()
def pmg_service_status(service: str, node: str | None = None) -> dict:
    """Get the status of a PMG system service (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: /nodes/{node}/services/{service}/state.
    service: e.g. 'postfix', 'pmgproxy', 'pmgdaemon', 'pmgmirror', 'pmgtunnel',
             'pmg-smtp-filter', 'clamav', 'spamassassin'. No hardcoded enum —
             pass any valid service name; unknown names return a PMG 404.
    """
    cfg, pmg = _proximo_server._pmg()
    n = node or cfg.node
    return _audited("pmg_service_status", f"pmg/{n}/services/{service}",
                    lambda: pmg_service_status_op(pmg, service, n))


@tool()
def pmg_domain_create(domain: str, comment: str | None = None, confirm: bool = False) -> dict:
    """MUTATION (LOW): create a managed mail domain. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: POST /config/domains.
    domain: domain name to add (e.g. 'example.com').
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
def pmg_domain_delete(domain: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): delete a managed mail domain. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: DELETE /config/domains/{domain}.
    Mail routing rules referencing this domain may break — review before confirming.
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
    domain: str,
    host: str,
    comment: str | None = None,
    port: int = 25,
    protocol: str = "smtp",
    use_mx: bool = True,
    confirm: bool = False,
) -> dict:
    """MUTATION (LOW): create a mail transport rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: POST /config/transport.
    domain: destination domain. host: next-hop relay host.
    port: TCP port 1-65535 (default 25). protocol: smtp|lmtp (default smtp).
    use_mx: use MX lookup for the host (default True).
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
def pmg_transport_delete(domain: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): delete a mail transport rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: DELETE /config/transport/{domain}.
    Mail for the domain will fall back to default PMG routing (MX lookup).
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
def pmg_mynetworks_add(cidr: str, comment: str | None = None, confirm: bool = False) -> dict:
    """MUTATION (LOW): add a CIDR to the PMG mynetworks trusted relay list. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: POST /config/mynetworks.
    cidr: network in CIDR notation (e.g. '10.0.0.0/8'). Only add CIDRs you control.
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
def pmg_mynetworks_remove(cidr: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): remove a CIDR from the PMG mynetworks trusted relay list. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: DELETE /config/mynetworks/{cidr} (CIDR URL-encoded).
    Internal senders in the range will be subject to spam filtering after removal.
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
    bounce_score: int | None = None,
    clamav_heuristic_score: int | None = None,
    extract_text: bool | None = None,
    languages: str | None = None,
    maxspamsize: int | None = None,
    rbl_checks: bool | None = None,
    use_awl: bool | None = None,
    use_bayes: bool | None = None,
    use_razor: bool | None = None,
    wl_bounce_relays: str | None = None,
    delete: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): update PMG spam filter configuration. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: PUT /config/spam.
    Only non-None fields are sent — omitted fields keep their current PMG values.
    delete: comma-separated list of field names to reset to defaults.
    Changes take effect immediately on new inbound mail.
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
def pmg_quarantine_welcomelist_list(pmail: str | None = None) -> list[dict]:
    """List PMG quarantine welcomelist entries (read). Optional pmail to scope to one user.
    Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: GET /quarantine/welcomelist.
    pmail defaults to the authenticated user when not provided.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_quarantine_welcomelist_list", "pmg/quarantine/welcomelist",
                    lambda: pmg_quarantine_welcomelist_list_op(pmg, pmail))


@tool()
def pmg_quarantine_welcomelist_add(
    address: str,
    pmail: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (LOW): add an address to the quarantine welcomelist. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: POST /quarantine/welcomelist.
    pmail: optional per-user scope (defaults to authenticated user).
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
    address: str,
    pmail: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (LOW): remove an address from the quarantine welcomelist. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: DELETE /quarantine/welcomelist.
    pmail: optional per-user scope (defaults to authenticated user).
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
    address: str,
    pmail: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (LOW): remove an address from the quarantine blocklist. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: DELETE /quarantine/blocklist.
    pmail: optional per-user scope (defaults to authenticated user).
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
    service: str,
    action: str,
    node: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): start, stop, restart, or reload a PMG service. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: POST /nodes/{node}/services/{service}/{action}.
    service: e.g. 'postfix', 'pmgproxy', 'pmgdaemon', 'clamav', 'spamassassin'.
    action: start|stop|restart|reload.

    WARNING: stop on postfix/pmgproxy/pmgdaemon interrupts mail delivery until manually restarted.
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
    node: str | None = None,
    start: int | None = None,
    end: int | None = None,
    from_: str | None = None,
    target: str | None = None,
    xfilter: str | None = None,
    ndr: bool | None = None,
    greylist: bool | None = None,
    limit: int = 2000,
) -> list[dict]:
    """List mail tracking entries (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: GET /nodes/{node}/tracker.
    Maps start/end Unix epoch → starttime/endtime query params.
    from_: filter by envelope sender; target: filter by recipient.
    ndr: NDR filter; greylist: greylisting filter.
    limit: max results 0–100000 (default 2000).
    """
    cfg, pmg = _proximo_server._pmg()
    n = node or cfg.node
    return _audited("pmg_tracker_list", f"pmg/{n}/tracker",
                    lambda: pmg_tracker_list_op(pmg, n, start, end, from_,
                                                target, xfilter, ndr, greylist, limit))


@tool()
def pmg_tracker_detail(
    id_: str,
    node: str | None = None,
    start: int | None = None,
    end: int | None = None,
) -> list[dict]:
    """Get tracking detail for a specific mail ID (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: GET /nodes/{node}/tracker/{id}.
    id_: mail/queue tracker ID, validated path-segment-safe (rejects '..', '/',
    control/whitespace chars) before use — see _check_tracker_id.
    Maps start/end Unix epoch → starttime/endtime query params.
    """
    cfg, pmg = _proximo_server._pmg()
    n = node or cfg.node
    return _audited("pmg_tracker_detail", f"pmg/{n}/tracker/{id_}",
                    lambda: pmg_tracker_detail_op(pmg, n, id_, start, end))


@tool()
def pmg_quarantine_virus(
    pmail: str | None = None,
    start: int | None = None,
    end: int | None = None,
) -> list[dict]:
    """List virus quarantine entries (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: GET /quarantine/virus.
    pmail: per-user scope — defaults to authenticated user (api.config.username).
    Maps start/end Unix epoch → starttime/endtime query params.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_quarantine_virus", "pmg/quarantine/virus",
                    lambda: pmg_quarantine_virus_op(pmg, pmail, start, end))


@tool()
def pmg_quarantine_attachment(
    pmail: str | None = None,
    start: int | None = None,
    end: int | None = None,
) -> list[dict]:
    """List attachment quarantine entries (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: GET /quarantine/attachment.
    pmail: per-user scope — defaults to authenticated user (api.config.username).
    Maps start/end Unix epoch → starttime/endtime query params.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_quarantine_attachment", "pmg/quarantine/attachment",
                    lambda: pmg_quarantine_attachment_op(pmg, pmail, start, end))


@tool()
def pmg_quarantine_virusstatus() -> dict:
    """Get virus quarantine status summary (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: GET /quarantine/virusstatus.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_quarantine_virusstatus", "pmg/quarantine/virusstatus",
                    lambda: pmg_quarantine_virusstatus_op(pmg))


@tool()
def pmg_quarantine_spamstatus() -> dict:
    """Get spam quarantine status summary (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: GET /quarantine/spamstatus.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_quarantine_spamstatus", "pmg/quarantine/spamstatus",
                    lambda: pmg_quarantine_spamstatus_op(pmg))


@tool()
def pmg_quarantine_spamusers(
    start: int | None = None,
    end: int | None = None,
    quarantine_type: str = "spam",
) -> list[dict]:
    """List users with quarantined mail entries (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: GET /quarantine/spamusers.
    quarantine_type: spam|virus|attachment (default spam) — sent to API as 'quarantine-type'.
    Maps start/end Unix epoch → starttime/endtime query params.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_quarantine_spamusers", "pmg/quarantine/spamusers",
                    lambda: pmg_quarantine_spamusers_op(pmg, start, end, quarantine_type))


@tool()
def pmg_statistics_mailcount(
    start: int | None = None,
    end: int | None = None,
    timespan: int = 3600,
) -> list[dict]:
    """Get per-bucket mail count statistics (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: GET /statistics/mailcount.
    timespan: histogram bucket size in seconds, 3600–31622400 (default 3600 = 1 hour).
    Maps start/end Unix epoch → starttime/endtime query params.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_statistics_mailcount", "pmg/statistics/mailcount",
                    lambda: pmg_statistics_mailcount_op(pmg, start, end, timespan))


@tool()
def pmg_statistics_sender(
    start: int | None = None,
    end: int | None = None,
    filter_: str | None = None,
    orderby: str | None = None,
) -> list[dict]:
    """Get per-sender mail statistics (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: GET /statistics/sender.
    filter_: optional search string. orderby: accepted for compatibility but IGNORED —
    PMG 9.1 rejects orderby on /statistics/sender (HTTP 400), so rows come back in PMG's
    default order (unlike pmg_statistics_receiver, which does pass orderby through).
    Maps start/end Unix epoch → starttime/endtime query params.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_statistics_sender", "pmg/statistics/sender",
                    lambda: pmg_statistics_sender_op(pmg, start, end, filter_, orderby))


@tool()
def pmg_statistics_receiver(
    start: int | None = None,
    end: int | None = None,
    filter_: str | None = None,
    orderby: str | None = None,
) -> list[dict]:
    """Get per-recipient mail statistics (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: GET /statistics/receiver.
    filter_: optional search string; orderby: raw sort spec passthrough.
    Maps start/end Unix epoch → starttime/endtime query params.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_statistics_receiver", "pmg/statistics/receiver",
                    lambda: pmg_statistics_receiver_op(pmg, start, end, filter_, orderby))


@tool()
def pmg_node_syslog(
    node: str | None = None,
    limit: int | None = None,
    service: str | None = None,
    since: str | None = None,
    until: str | None = None,
    start: int | None = None,
) -> list[dict]:
    """Get PMG node syslog entries (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: GET /nodes/{node}/syslog.
    limit: max entries; service: filter by service name.
    since/until: time range; start: pagination offset.
    """
    cfg, pmg = _proximo_server._pmg()
    n = node or cfg.node
    return _audited("pmg_node_syslog", f"pmg/{n}/syslog",
                    lambda: pmg_node_syslog_op(pmg, n, limit, service, since, until, start))


@tool()
def pmg_node_rrddata(
    timeframe: str,
    node: str | None = None,
    cf: str | None = None,
) -> list[dict]:
    """Get PMG node RRD performance data (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: GET /nodes/{node}/rrddata.
    timeframe: REQUIRED — hour|day|week|month|year.
    cf: consolidation function AVERAGE|MAX (optional).
    """
    cfg, pmg = _proximo_server._pmg()
    n = node or cfg.node
    return _audited("pmg_node_rrddata", f"pmg/{n}/rrddata",
                    lambda: pmg_node_rrddata_op(pmg, n, timeframe, cf))


@tool()
def pmg_tasks_list(
    node: str | None = None,
    start: int | None = None,
    limit: int | None = None,
    userfilter: str | None = None,
    errors: bool | None = None,
    typefilter: str | None = None,
    since: int | None = None,
    until: int | None = None,
    statusfilter: str | None = None,
) -> list[dict]:
    """List PMG tasks on a node (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: GET /nodes/{node}/tasks.
    start: pagination offset; limit: max entries.
    errors: True = only failed tasks; userfilter/typefilter/statusfilter: text filters.
    """
    cfg, pmg = _proximo_server._pmg()
    n = node or cfg.node
    return _audited("pmg_tasks_list", f"pmg/{n}/tasks",
                    lambda: pmg_tasks_list_op(pmg, n, start, limit, userfilter,
                                              errors, typefilter, since, until, statusfilter))


@tool()
def pmg_backup_create(
    node: str | None = None,
    notify: str = "never",
    statistic: bool = True,
    confirm: bool = False,
) -> dict:
    """MUTATION (LOW): create a PMG configuration backup. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: POST /nodes/{node}/backup.
    notify: always|error|never (default never).
    statistic: include mail statistics in backup (default True).
    Backup is written to /var/lib/pmg/backup/ on the target node.
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
    """List all PMG RuleDB rules (hydrated rule list) (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules.
    Returns the full hydrated rule list including from/to/what/when/actions for each rule.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_ruledb_rules_list", "pmg/config/ruledb/rules",
                    lambda: pmg_ruledb_rules_list_op(pmg))


@tool()
def pmg_ruledb_rule_get(id_: str) -> dict:
    """Get a PMG RuleDB rule's configuration (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules/{id}/config.
    id_: rule ID (positive integer string, e.g. '100').
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_ruledb_rule_get", f"pmg/config/ruledb/rules/{id_}/config",
                    lambda: pmg_ruledb_rule_get_op(pmg, id_))


@tool()
def pmg_ruledb_rule_from_list(id_: str) -> list[dict]:
    """List the 'from' objects attached to a PMG RuleDB rule (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules/{id}/from.
    id_: rule ID (positive integer string, e.g. '100').
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_ruledb_rule_from_list", f"pmg/config/ruledb/rules/{id_}/from",
                    lambda: pmg_ruledb_rule_from_list_op(pmg, id_))


@tool()
def pmg_ruledb_rule_to_list(id_: str) -> list[dict]:
    """List the 'to' objects attached to a PMG RuleDB rule (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules/{id}/to.
    id_: rule ID (positive integer string, e.g. '100').
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_ruledb_rule_to_list", f"pmg/config/ruledb/rules/{id_}/to",
                    lambda: pmg_ruledb_rule_to_list_op(pmg, id_))


@tool()
def pmg_ruledb_rule_what_list(id_: str) -> list[dict]:
    """List the 'what' objects attached to a PMG RuleDB rule (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules/{id}/what.
    id_: rule ID (positive integer string, e.g. '100').
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_ruledb_rule_what_list", f"pmg/config/ruledb/rules/{id_}/what",
                    lambda: pmg_ruledb_rule_what_list_op(pmg, id_))


@tool()
def pmg_ruledb_rule_when_list(id_: str) -> list[dict]:
    """List the 'when' objects attached to a PMG RuleDB rule (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules/{id}/when.
    id_: rule ID (positive integer string, e.g. '100').
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_ruledb_rule_when_list", f"pmg/config/ruledb/rules/{id_}/when",
                    lambda: pmg_ruledb_rule_when_list_op(pmg, id_))


@tool()
def pmg_ruledb_rule_actions_list(id_: str) -> list[dict]:
    """List the 'actions' objects attached to a PMG RuleDB rule (read). Needs PROXIMO_PMG_* config.

    PMG 9.1: reads GET /config/ruledb/rules/{id}/config and extracts the embedded 'action' list —
    the dedicated .../actions path returns HTTP 501 (not implemented), so it is NOT used.
    id_: rule ID (positive integer string, e.g. '100').
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_ruledb_rule_actions_list", f"pmg/config/ruledb/rules/{id_}/config",
                    lambda: pmg_ruledb_rule_actions_list_op(pmg, id_))


@tool()
def pmg_who_groups_list() -> list[dict]:
    """List all PMG RuleDB 'who' object groups (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/who.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_who_groups_list", "pmg/config/ruledb/who",
                    lambda: pmg_who_groups_list_op(pmg))


@tool()
def pmg_who_group_get(ogroup: str) -> dict:
    """Get a PMG RuleDB 'who' object group's configuration (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/who/{ogroup}/config.
    ogroup: numeric ID string (e.g. '2') from the matching pmg_*_groups_list — NOT the group name.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_who_group_get", f"pmg/config/ruledb/who/{ogroup}/config",
                    lambda: pmg_who_group_get_op(pmg, ogroup))


@tool()
def pmg_who_group_objects(ogroup: str) -> list[dict]:
    """List the objects in a PMG RuleDB 'who' object group (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/who/{ogroup}/objects.
    ogroup: numeric ID string (e.g. '2') from the matching pmg_*_groups_list — NOT the group name.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_who_group_objects", f"pmg/config/ruledb/who/{ogroup}/objects",
                    lambda: pmg_who_group_objects_op(pmg, ogroup))


@tool()
def pmg_what_groups_list() -> list[dict]:
    """List all PMG RuleDB 'what' object groups (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/what.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_what_groups_list", "pmg/config/ruledb/what",
                    lambda: pmg_what_groups_list_op(pmg))


@tool()
def pmg_what_group_get(ogroup: str) -> dict:
    """Get a PMG RuleDB 'what' object group's configuration (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/what/{ogroup}/config.
    ogroup: numeric ID string (e.g. '2') from the matching pmg_*_groups_list — NOT the group name.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_what_group_get", f"pmg/config/ruledb/what/{ogroup}/config",
                    lambda: pmg_what_group_get_op(pmg, ogroup))


@tool()
def pmg_what_group_objects(ogroup: str) -> list[dict]:
    """List the objects in a PMG RuleDB 'what' object group (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/what/{ogroup}/objects.
    ogroup: numeric ID string (e.g. '2') from the matching pmg_*_groups_list — NOT the group name.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_what_group_objects", f"pmg/config/ruledb/what/{ogroup}/objects",
                    lambda: pmg_what_group_objects_op(pmg, ogroup))


@tool()
def pmg_when_groups_list() -> list[dict]:
    """List all PMG RuleDB 'when' object groups (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/when.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_when_groups_list", "pmg/config/ruledb/when",
                    lambda: pmg_when_groups_list_op(pmg))


@tool()
def pmg_when_group_get(ogroup: str) -> dict:
    """Get a PMG RuleDB 'when' object group's configuration (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/when/{ogroup}/config.
    ogroup: numeric ID string (e.g. '2') from the matching pmg_*_groups_list — NOT the group name.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_when_group_get", f"pmg/config/ruledb/when/{ogroup}/config",
                    lambda: pmg_when_group_get_op(pmg, ogroup))


@tool()
def pmg_when_group_objects(ogroup: str) -> list[dict]:
    """List the objects in a PMG RuleDB 'when' object group (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/when/{ogroup}/objects.
    ogroup: numeric ID string (e.g. '2') from the matching pmg_*_groups_list — NOT the group name.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_when_group_objects", f"pmg/config/ruledb/when/{ogroup}/objects",
                    lambda: pmg_when_group_objects_op(pmg, ogroup))


@tool()
def pmg_action_objects_list() -> list[dict]:
    """List all PMG RuleDB action objects including non-editable (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/action/objects.
    Returns all action objects; each entry carries an 'editable' flag.
    Non-editable action objects are built-in and cannot be modified via the API.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_action_objects_list", "pmg/config/ruledb/action/objects",
                    lambda: pmg_action_objects_list_op(pmg))


@tool()
def pmg_ruledb_digest() -> dict:
    """Get the PMG RuleDB digest (change-detection hash) (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/digest.
    The digest changes whenever any ruledb configuration is modified.
    Use to detect configuration drift without fetching the full rule list.
    """
    _, pmg = _proximo_server._pmg()
    return _audited("pmg_ruledb_digest", "pmg/config/ruledb/digest",
                    lambda: pmg_ruledb_digest_op(pmg))
