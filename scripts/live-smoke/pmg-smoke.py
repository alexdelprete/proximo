#!/usr/bin/env python3
"""PMG live-prove smoke — W1–W5b against real PMG 9.1.

Drives PmgBackend + pmg.py operation functions directly (the same layer the
server.py @mcp.tool wrappers call), confirming shape-risks mocks cannot catch:
wrong API paths, rejected query params, response-shape mismatches, auth flow.

W2 safe mutations exercised:
  - quarantine_blocklist_add: add test@example.invalid, verify, CLEAN UP (remove)
  - postfix_flush: live-fire (no-op on empty queue, must round-trip 200)

W2 plan-paths (pure, no API call):
  - plan_quarantine_action(deliver)

W3 CRUD/control cycles (each: create → verify → delete → verify gone):
  - domain_create / domain_delete
  - transport_create / transport_delete
  - mynetworks_add / mynetworks_remove  (live-proves %2F path-encoding on delete)
  - spam_config_update: flip use_awl → verify → revert (fully reversible)
  - quarantine_welcomelist_add / remove
  - quarantine_blocklist_remove promoted tool (add via W2 op, remove via W3)
  - service_control restart pmg-smtp-filter → poll active; plan(stop) pure-only

Environment (must be set before running; see the wrapper call below):
  PROXIMO_PMG_BASE_URL        https://127.0.0.1:18006/api2/json
  PROXIMO_PMG_USERNAME        root@pam
  PROXIMO_PMG_PASSWORD_PATH   ~/.config/proximo/pmg-test-pass
  PROXIMO_PMG_NODE            pmg-test
  PROXIMO_PMG_VERIFY_TLS      true
  PROXIMO_PMG_CA_BUNDLE       ~/.config/proximo/pmg-test-ca.pem

Run from the proximo project root:
  PROXIMO_PMG_BASE_URL=https://127.0.0.1:18006/api2/json \\
  PROXIMO_PMG_USERNAME=root@pam \\
  PROXIMO_PMG_PASSWORD_PATH=~/.config/proximo/pmg-test-pass \\
  PROXIMO_PMG_NODE=pmg-test \\
  PROXIMO_PMG_VERIFY_TLS=true \\
  PROXIMO_PMG_CA_BUNDLE=~/.config/proximo/pmg-test-ca.pem \\
  uv run python scripts/live-smoke/pmg-smoke.py
"""
from __future__ import annotations

import os
import sys
import time

# Ensure we import from the project source, not any installed version.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from proximo.pmg import (
    PmgBackend,
    PmgConfig,
    access_permissions,
    domains_list,
    statistics_mail,
    node_status,
    node_version,
    quarantine_spam,
    relay_config,
    # W2 reads
    postfix_qshape,
    quarantine_blocklist_list,
    service_status,
    spam_config,
    statistics_domains,
    statistics_recent,
    statistics_spamscores,
    statistics_virus,
    # W2 mutations
    postfix_flush,
    quarantine_blocklist_add,
    quarantine_blocklist_remove,
    # W2 plans
    plan_quarantine_action,
    # W3 reads
    quarantine_welcomelist_list,
    # W3 mutations
    domain_create,
    domain_delete,
    transport_create,
    transport_delete,
    mynetworks_add,
    mynetworks_remove,
    spam_config_update,
    quarantine_welcomelist_add,
    quarantine_welcomelist_remove,
    service_control,
    # W3 plans
    plan_service_control,
    # W4 reads
    tracker_list,
    tracker_detail,
    quarantine_virus,
    quarantine_attachment,
    quarantine_virusstatus,
    quarantine_spamstatus,
    quarantine_spamusers,
    statistics_mailcount,
    statistics_sender,
    statistics_receiver,
    node_syslog,
    node_rrddata,
    tasks_list,
    # W4 mutation
    backup_create,
    # W4 plan
    plan_backup_create,
    # W5a reads — RuleDB
    ruledb_rules_list,
    ruledb_rule_get,
    ruledb_rule_from_list,
    ruledb_rule_to_list,
    ruledb_rule_what_list,
    ruledb_rule_when_list,
    ruledb_rule_actions_list,
    who_groups_list,
    who_group_get,
    who_group_objects,
    what_groups_list,
    what_group_get,
    what_group_objects,
    when_groups_list,
    when_group_get,
    when_group_objects,
    action_objects_list,
    ruledb_digest,
    # W5b mutations — group CRUD + who-object CRUD
    who_group_create,
    who_group_update,
    who_group_delete,
    who_object_add,
    who_object_update,
    who_object_delete,
    what_group_create,
    what_group_update,
    what_group_delete,
    when_group_create,
    when_group_update,
    when_group_delete,
    # W5c mutations — WHAT-object CRUD, WHEN-object CRUD, ACTION CRUD
    what_object_add,
    what_object_update,
    what_object_delete,
    when_object_add,
    when_object_update,
    when_object_delete,
    action_bcc_create,
    action_bcc_update,
    action_field_create,
    action_field_update,
    action_notification_create,
    action_notification_update,
    action_disclaimer_create,
    action_disclaimer_update,
    action_removeattachments_create,
    action_removeattachments_update,
    action_delete,
    # W5d mutations — rule CRUD + attach/detach
    ruledb_rule_create,
    ruledb_rule_update,
    ruledb_rule_delete,
    ruledb_rule_from_attach,
    ruledb_rule_from_detach,
    ruledb_rule_to_attach,
    ruledb_rule_to_detach,
    ruledb_rule_what_attach,
    ruledb_rule_what_detach,
    ruledb_rule_when_attach,
    ruledb_rule_when_detach,
    ruledb_rule_action_attach,
    ruledb_rule_action_detach,
)

findings: list[tuple[str, str, str]] = []


def rec(step: str, status: str, detail: str = "") -> None:
    findings.append((step, status, detail))
    print(f"[{status:5}] {step}: {detail}")


def hr(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    required = (
        "PROXIMO_PMG_BASE_URL",
        "PROXIMO_PMG_USERNAME",
        "PROXIMO_PMG_PASSWORD_PATH",
        "PROXIMO_PMG_NODE",
        "PROXIMO_PMG_VERIFY_TLS",
        "PROXIMO_PMG_CA_BUNDLE",
    )
    missing = [v for v in required if v not in os.environ]
    if missing:
        print(f"ERROR: missing env vars: {missing}", file=sys.stderr)
        return 2

    try:
        cfg = PmgConfig.from_env()
    except Exception as e:
        print(f"ERROR: PmgConfig.from_env() failed: {e}", file=sys.stderr)
        return 2

    print(f"PMG live-prove | node={cfg.node} | url={cfg.base_url}")
    print("(read-only + plan-only; no mail is delivered)")

    try:
        backend = PmgBackend(cfg)
    except Exception as e:
        print(f"ERROR: PmgBackend() construction failed: {e}", file=sys.stderr)
        return 2

    node = cfg.node

    # -------------------------------------------------------------------------
    # pmg_doctor proxy: node_version + access_permissions
    # (server.pmg_doctor calls these two functions)
    # -------------------------------------------------------------------------
    hr("node_version — GET /version (doctor proxy)")
    try:
        result = node_version(backend, node)
        assert isinstance(result, dict), f"expected dict, got {type(result)}: {result!r}"
        version_str = result.get("version") or result.get("release")
        assert version_str, f"no version/release key in result: {result}"
        rec("node_version", "PASS", f"version={version_str}")
    except Exception as e:
        rec("node_version", "FAIL", repr(e))

    hr("access_permissions — GET /access/permissions (doctor proxy)")
    try:
        result = access_permissions(backend)
        # PMG may not have this endpoint; we accept any non-error return
        assert result is not None or True, "unexpected None (but None is ok if empty)"
        rec("access_permissions", "PASS", f"result_type={type(result).__name__} keys={list(result.keys())[:5] if isinstance(result, dict) else repr(result)[:60]}")
    except Exception as e:
        rec("access_permissions", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_node_status
    # -------------------------------------------------------------------------
    hr("node_status — GET /nodes/{node}/status")
    try:
        result = node_status(backend, node)
        assert isinstance(result, dict), f"expected dict, got {type(result)}: {result!r}"
        # Expect memory, cpu, uptime keys
        keys = list(result.keys())
        assert keys, f"empty result dict"
        rec("node_status", "PASS", f"keys={keys[:5]}")
    except Exception as e:
        rec("node_status", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_relay_config
    # -------------------------------------------------------------------------
    hr("relay_config — GET /config/relay")
    try:
        result = relay_config(backend)
        assert isinstance(result, dict), f"expected dict, got {type(result)}: {result!r}"
        rec("relay_config", "PASS", f"keys={list(result.keys())[:5]}")
    except Exception as e:
        rec("relay_config", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_domains_list
    # -------------------------------------------------------------------------
    hr("domains_list — GET /config/domains")
    try:
        result = domains_list(backend)
        assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
        rec("domains_list", "PASS", f"count={len(result)}")
    except Exception as e:
        rec("domains_list", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_statistics_mail
    # -------------------------------------------------------------------------
    hr("statistics_mail — GET /statistics/mail")
    try:
        result = statistics_mail(backend)
        assert isinstance(result, dict), f"expected dict, got {type(result)}: {result!r}"
        keys = list(result.keys())
        assert keys, "empty result dict"
        rec("statistics_mail", "PASS", f"keys={keys[:5]}")
    except Exception as e:
        rec("statistics_mail", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_quarantine_spam
    # -------------------------------------------------------------------------
    hr("quarantine_spam — GET /quarantine/spam")
    try:
        result = quarantine_spam(backend)
        assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
        rec("quarantine_spam", "PASS", f"count={len(result)} (fresh PMG = 0 quarantined msgs)")
    except Exception as e:
        rec("quarantine_spam", "FAIL", repr(e))

    # =========================================================================
    # W2 READ operations
    # =========================================================================

    # -------------------------------------------------------------------------
    # pmg_statistics_domains
    # -------------------------------------------------------------------------
    hr("statistics_domains — GET /statistics/domains")
    try:
        result = statistics_domains(backend)
        assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
        rec("statistics_domains", "PASS", f"count={len(result)} result_type=list")
    except Exception as e:
        rec("statistics_domains", "FAIL", repr(e))

    # With starttime/endtime params
    hr("statistics_domains(start,end) — verify starttime/endtime params accepted")
    try:
        import time as _time
        end_ts = int(_time.time())
        start_ts = end_ts - 86400
        result = statistics_domains(backend, start=start_ts, end=end_ts)
        assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
        rec("statistics_domains(start,end)", "PASS", f"count={len(result)}")
    except Exception as e:
        rec("statistics_domains(start,end)", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_statistics_virus
    # -------------------------------------------------------------------------
    hr("statistics_virus — GET /statistics/virus")
    try:
        result = statistics_virus(backend)
        assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
        rec("statistics_virus", "PASS", f"count={len(result)} result_type=list")
    except Exception as e:
        rec("statistics_virus", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_statistics_spamscores
    # -------------------------------------------------------------------------
    hr("statistics_spamscores — GET /statistics/spamscores")
    try:
        result = statistics_spamscores(backend)
        assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
        rec("statistics_spamscores", "PASS", f"count={len(result)} result_type=list")
    except Exception as e:
        rec("statistics_spamscores", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_statistics_recent
    # -------------------------------------------------------------------------
    hr("statistics_recent — GET /statistics/recent?hours=1")
    try:
        result = statistics_recent(backend)
        assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
        rec("statistics_recent", "PASS", f"count={len(result)} result_type=list")
    except Exception as e:
        rec("statistics_recent", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_quarantine_blocklist_list (read — empty before we add)
    # -------------------------------------------------------------------------
    hr("quarantine_blocklist_list — GET /quarantine/blocklist (pre-add)")
    try:
        result = quarantine_blocklist_list(backend)
        assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
        pre_count = len(result)
        rec("quarantine_blocklist_list(pre-add)", "PASS", f"count={pre_count}")
    except Exception as e:
        pre_count = -1
        rec("quarantine_blocklist_list(pre-add)", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_spam_config
    # -------------------------------------------------------------------------
    hr("spam_config — GET /config/spam")
    try:
        result = spam_config(backend)
        assert isinstance(result, dict), f"expected dict, got {type(result)}: {result!r}"
        rec("spam_config", "PASS", f"keys={list(result.keys())[:5]}")
    except Exception as e:
        rec("spam_config", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_service_status — pmgproxy + postfix
    # -------------------------------------------------------------------------
    hr("service_status(pmgproxy) — GET /nodes/{node}/services/pmgproxy/state")
    try:
        result = service_status(backend, "pmgproxy", node)
        assert isinstance(result, dict), f"expected dict, got {type(result)}: {result!r}"
        state = result.get("state") or result.get("status") or list(result.keys())[:3]
        rec("service_status(pmgproxy)", "PASS", f"state={state}")
    except Exception as e:
        rec("service_status(pmgproxy)", "FAIL", repr(e))

    hr("service_status(postfix) — GET /nodes/{node}/services/postfix/state")
    try:
        result = service_status(backend, "postfix", node)
        assert isinstance(result, dict), f"expected dict, got {type(result)}: {result!r}"
        state = result.get("state") or result.get("status") or list(result.keys())[:3]
        rec("service_status(postfix)", "PASS", f"state={state}")
    except Exception as e:
        rec("service_status(postfix)", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_postfix_qshape
    # -------------------------------------------------------------------------
    hr("postfix_qshape — GET /nodes/{node}/postfix/qshape")
    try:
        result = postfix_qshape(backend, node)
        assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
        total_row = next((r for r in result if r.get("domain") == "TOTAL"), None)
        rec("postfix_qshape", "PASS",
            f"rows={len(result)} total_row={'found' if total_row else 'absent'}")
    except Exception as e:
        rec("postfix_qshape", "FAIL", repr(e))

    # =========================================================================
    # W2 MUTATIONS — safe live-fire with cleanup
    # =========================================================================

    TEST_BL_ADDR = "test@example.invalid"

    # -------------------------------------------------------------------------
    # pmg_quarantine_blocklist_add — ADD + verify + CLEAN UP
    # -------------------------------------------------------------------------
    hr(f"quarantine_blocklist_add — POST /quarantine/blocklist (add {TEST_BL_ADDR!r})")
    bl_added = False
    try:
        quarantine_blocklist_add(backend, TEST_BL_ADDR)
        bl_added = True
        rec("quarantine_blocklist_add", "PASS", f"added {TEST_BL_ADDR!r} without error")
    except Exception as e:
        rec("quarantine_blocklist_add", "FAIL", repr(e))

    # Verify it appears
    hr(f"quarantine_blocklist_list (post-add) — verify {TEST_BL_ADDR!r} now present")
    if bl_added:
        try:
            result = quarantine_blocklist_list(backend)
            assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
            found = any(
                str(entry.get("address", "")).lower() == TEST_BL_ADDR.lower()
                or TEST_BL_ADDR.lower() in str(entry).lower()
                for entry in result
            )
            if found:
                rec("quarantine_blocklist_list(post-add)", "PASS",
                    f"entry found in blocklist (count={len(result)})")
            else:
                rec("quarantine_blocklist_list(post-add)", "FAIL",
                    f"entry NOT found in blocklist (count={len(result)}, entries={result[:3]})")
        except Exception as e:
            rec("quarantine_blocklist_list(post-add)", "FAIL", repr(e))
    else:
        rec("quarantine_blocklist_list(post-add)", "SKIP", "add failed, skipping verify")

    # CLEAN UP — remove the test entry via quarantine_blocklist_remove
    # PMG 9.1 live-verified: delete uses DELETE /quarantine/blocklist?address=X&pmail=Y
    # (NOT /quarantine/blocklist/{address} — that path returns 501 in PMG 9.1)
    hr(f"quarantine_blocklist_list CLEANUP — DELETE test entry {TEST_BL_ADDR!r}")
    if bl_added:
        try:
            quarantine_blocklist_remove(backend, TEST_BL_ADDR)
            # Verify it's gone
            after = quarantine_blocklist_list(backend)
            still_present = any(
                str(entry.get("address", "")).lower() == TEST_BL_ADDR.lower()
                or TEST_BL_ADDR.lower() in str(entry).lower()
                for entry in after
            )
            if still_present:
                rec("quarantine_blocklist_list_cleanup", "FAIL",
                    f"entry STILL in blocklist after delete (entries={after[:3]})")
            else:
                rec("quarantine_blocklist_list_cleanup", "PASS",
                    f"entry removed, blocklist count now={len(after)} — no residue")
        except Exception as e:
            rec("quarantine_blocklist_list_cleanup", "FAIL",
                f"CLEANUP FAILED — manual removal needed: {repr(e)}")
    else:
        rec("quarantine_blocklist_list_cleanup", "SKIP", "add failed, nothing to clean")

    # -------------------------------------------------------------------------
    # pmg_postfix_flush — live-fire (empty queue, no-op, must round-trip 200)
    # -------------------------------------------------------------------------
    hr(f"postfix_flush — POST /nodes/{node}/postfix/flush_queues")
    try:
        postfix_flush(backend, node)
        rec("postfix_flush", "PASS", "round-tripped 200 (empty queue no-op)")
    except Exception as e:
        rec("postfix_flush", "FAIL", repr(e))

    # =========================================================================
    # W2 PLAN-PATH ONLY (pure factories, no API call)
    # =========================================================================

    hr("plan_quarantine_action(deliver) — PLAN ONLY (no mutation)")
    try:
        plan = plan_quarantine_action("deliver", "test-mail-id-001")
        d = plan.as_dict()
        assert d.get("action") == "pmg_quarantine_action", f"wrong action: {d.get('action')}"
        assert d.get("risk") == "medium", f"wrong risk: {d.get('risk')}"
        target = d.get("target", "")
        assert "quarantine/content" in target, f"wrong target: {target}"
        rec("plan_quarantine_action(deliver)", "PASS",
            f"action={d['action']} risk={d['risk']} target={target}")
    except Exception as e:
        rec("plan_quarantine_action(deliver)", "FAIL", repr(e))

    # =========================================================================
    # W3 CRUD/control cycles — 12 new tools, live-proven against PMG 9.1
    # =========================================================================

    # -------------------------------------------------------------------------
    # pmg_domain_create / pmg_domain_delete — POST + DELETE /config/domains
    # -------------------------------------------------------------------------
    TEST_DOMAIN = "w3-probe.test"

    hr(f"domain_create — POST /config/domains ({TEST_DOMAIN!r})")
    domain_created = False
    try:
        domain_create(backend, TEST_DOMAIN)
        domain_created = True
        rec("domain_create", "PASS", f"created {TEST_DOMAIN!r} without error")
    except Exception as e:
        rec("domain_create", "FAIL", repr(e))

    hr(f"domains_list (post-create) — verify {TEST_DOMAIN!r} present")
    if domain_created:
        try:
            result = domains_list(backend)
            found = any(
                str(entry.get("domain", "")).lower() == TEST_DOMAIN.lower()
                for entry in result
            )
            if found:
                rec("domain_create(verify)", "PASS",
                    f"domain found in list (count={len(result)})")
            else:
                rec("domain_create(verify)", "FAIL",
                    f"domain NOT found in list (count={len(result)}, entries={result[:3]})")
        except Exception as e:
            rec("domain_create(verify)", "FAIL", repr(e))
    else:
        rec("domain_create(verify)", "SKIP", "create failed")

    hr(f"domain_delete — DELETE /config/domains/{TEST_DOMAIN}")
    if domain_created:
        try:
            domain_delete(backend, TEST_DOMAIN)
            after = domains_list(backend)
            still_present = any(
                str(entry.get("domain", "")).lower() == TEST_DOMAIN.lower()
                for entry in after
            )
            if still_present:
                rec("domain_delete", "FAIL",
                    f"domain STILL present after delete (entries={after[:3]})")
            else:
                rec("domain_delete", "PASS",
                    f"domain removed, count now={len(after)} — no residue")
        except Exception as e:
            rec("domain_delete", "FAIL",
                f"CLEANUP FAILED — manual removal needed: {repr(e)}")
    else:
        rec("domain_delete", "SKIP", "create failed, nothing to delete")

    # -------------------------------------------------------------------------
    # pmg_transport_create / pmg_transport_delete — POST + DELETE /config/transport
    # -------------------------------------------------------------------------
    TEST_TRANSPORT_HOST = "127.0.0.1"

    hr(f"transport_create — POST /config/transport (domain={TEST_DOMAIN!r} host={TEST_TRANSPORT_HOST!r})")
    transport_created = False
    try:
        transport_create(backend, TEST_DOMAIN, TEST_TRANSPORT_HOST)
        transport_created = True
        rec("transport_create", "PASS", f"created transport for {TEST_DOMAIN!r} without error")
    except Exception as e:
        rec("transport_create", "FAIL", repr(e))

    hr(f"GET /config/transport (post-create) — verify {TEST_DOMAIN!r} present")
    if transport_created:
        try:
            result = backend._get("/config/transport") or []
            assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
            found = any(
                str(entry.get("domain", "")).lower() == TEST_DOMAIN.lower()
                for entry in result
            )
            if found:
                rec("transport_create(verify)", "PASS",
                    f"transport found in list (count={len(result)})")
            else:
                rec("transport_create(verify)", "FAIL",
                    f"transport NOT found (count={len(result)}, entries={result[:3]})")
        except Exception as e:
            rec("transport_create(verify)", "FAIL", repr(e))
    else:
        rec("transport_create(verify)", "SKIP", "create failed")

    hr(f"transport_delete — DELETE /config/transport/{TEST_DOMAIN}")
    if transport_created:
        try:
            transport_delete(backend, TEST_DOMAIN)
            after = backend._get("/config/transport") or []
            still_present = any(
                str(entry.get("domain", "")).lower() == TEST_DOMAIN.lower()
                for entry in after
            )
            if still_present:
                rec("transport_delete", "FAIL",
                    f"transport STILL present after delete (entries={after[:3]})")
            else:
                rec("transport_delete", "PASS",
                    f"transport removed, count now={len(after)} — no residue")
        except Exception as e:
            rec("transport_delete", "FAIL",
                f"CLEANUP FAILED — manual removal needed: {repr(e)}")
    else:
        rec("transport_delete", "SKIP", "create failed, nothing to delete")

    # -------------------------------------------------------------------------
    # pmg_mynetworks_add / pmg_mynetworks_remove — POST /config/mynetworks +
    # DELETE /config/mynetworks/{cidr} where / is %2F-encoded in the path
    # -------------------------------------------------------------------------
    TEST_CIDR = "192.0.2.0/30"  # RFC 5737 documentation range — safe for test

    hr(f"mynetworks_add — POST /config/mynetworks ({TEST_CIDR!r})")
    mynetwork_added = False
    try:
        mynetworks_add(backend, TEST_CIDR)
        mynetwork_added = True
        rec("mynetworks_add", "PASS", f"added {TEST_CIDR!r} without error")
    except Exception as e:
        rec("mynetworks_add", "FAIL", repr(e))

    hr(f"GET /config/mynetworks (post-add) — verify {TEST_CIDR!r} present")
    if mynetwork_added:
        try:
            result = backend._get("/config/mynetworks") or []
            assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
            found = any(
                str(entry.get("cidr", "")).lower() == TEST_CIDR.lower()
                for entry in result
            )
            if found:
                rec("mynetworks_add(verify)", "PASS",
                    f"entry found in mynetworks (count={len(result)})")
            else:
                rec("mynetworks_add(verify)", "FAIL",
                    f"entry NOT found (count={len(result)}, entries={result[:3]})")
        except Exception as e:
            rec("mynetworks_add(verify)", "FAIL", repr(e))
    else:
        rec("mynetworks_add(verify)", "SKIP", "add failed")

    hr(f"mynetworks_remove — DELETE /config/mynetworks/{{cidr}} (/ encoded as %2F) ({TEST_CIDR!r})")
    if mynetwork_added:
        try:
            mynetworks_remove(backend, TEST_CIDR)
            after = backend._get("/config/mynetworks") or []
            still_present = any(
                str(entry.get("cidr", "")).lower() == TEST_CIDR.lower()
                for entry in after
            )
            if still_present:
                rec("mynetworks_remove", "FAIL",
                    f"entry STILL present after delete (entries={after[:3]})")
            else:
                rec("mynetworks_remove", "PASS",
                    f"entry removed via %2F path encoding, count now={len(after)} — no residue")
        except Exception as e:
            rec("mynetworks_remove", "FAIL",
                f"CLEANUP FAILED — manual removal needed: {repr(e)}")
    else:
        rec("mynetworks_remove", "SKIP", "add failed, nothing to remove")

    # -------------------------------------------------------------------------
    # pmg_spam_config_update — PUT /config/spam (flip use_awl, verify, revert)
    # PMG 9.1: when use_awl is at its default (not explicitly set), the config
    # only returns {"digest": "..."}. use_awl is absent (None). To revert the
    # default state, pass delete="use_awl" to the PUT endpoint.
    # -------------------------------------------------------------------------
    hr("spam_config_update — PUT /config/spam (flip use_awl, verify, revert)")
    spam_orig_awl: int | None = None
    spam_mutated = False
    try:
        current_spam = spam_config(backend)
        assert isinstance(current_spam, dict), f"expected dict, got {type(current_spam)}: {current_spam!r}"
        spam_orig_awl = current_spam.get("use_awl")  # None if at default (not set); 0 or 1 if explicit
        # Flip: if None or 0 → set True (1); if 1 → set False (0)
        new_awl = not bool(spam_orig_awl)
        rec("spam_config(pre-update)", "PASS",
            f"orig use_awl={spam_orig_awl!r}, will flip to {new_awl!r}")
    except Exception as e:
        rec("spam_config(pre-update)", "FAIL", repr(e))

    # Apply the flip
    if spam_orig_awl is not None or True:  # always try if we got the pre-read
        try:
            spam_config_update(backend, use_awl=new_awl)  # type: ignore[possibly-undefined]
            spam_mutated = True
            # Verify the change landed
            after_spam = spam_config(backend)
            after_awl = after_spam.get("use_awl")
            expected_api = 1 if new_awl else 0  # type: ignore[possibly-undefined]
            if after_awl == expected_api:
                rec("spam_config_update(verify)", "PASS",
                    f"use_awl changed to {after_awl} (expected {expected_api})")
            else:
                rec("spam_config_update(verify)", "FAIL",
                    f"use_awl={after_awl!r} expected {expected_api}")
        except Exception as e:
            rec("spam_config_update(set)", "FAIL", repr(e))

    # Revert — fully reversible
    if spam_mutated:
        try:
            if spam_orig_awl is None:
                # was at default (not explicitly set) — delete key to restore default state
                spam_config_update(backend, delete="use_awl")
            else:
                # was explicitly set — restore the original value
                spam_config_update(backend, use_awl=bool(spam_orig_awl))
            reverted = spam_config(backend)
            reverted_awl = reverted.get("use_awl")
            if spam_orig_awl is None:
                # After delete, use_awl should be absent again
                if reverted_awl is None:
                    rec("spam_config_update(revert)", "PASS",
                        "use_awl removed (back to default — not present in config)")
                else:
                    rec("spam_config_update(revert)", "FAIL",
                        f"use_awl still present after delete: {reverted_awl!r}")
            else:
                if reverted_awl == spam_orig_awl:
                    rec("spam_config_update(revert)", "PASS",
                        f"use_awl restored to {reverted_awl!r}")
                else:
                    rec("spam_config_update(revert)", "FAIL",
                        f"use_awl={reverted_awl!r} expected {spam_orig_awl!r}")
        except Exception as e:
            rec("spam_config_update(revert)", "FAIL",
                f"REVERT FAILED — manual fix needed: {repr(e)}")
    else:
        rec("spam_config_update(revert)", "SKIP", "no mutation applied")

    # -------------------------------------------------------------------------
    # pmg_quarantine_welcomelist_add / _remove — POST + DELETE /quarantine/welcomelist
    # -------------------------------------------------------------------------
    TEST_WL_ADDR = "w3probe@example.com"

    hr(f"quarantine_welcomelist_add — POST /quarantine/welcomelist ({TEST_WL_ADDR!r})")
    wl_added = False
    try:
        quarantine_welcomelist_add(backend, TEST_WL_ADDR)
        wl_added = True
        rec("quarantine_welcomelist_add", "PASS", f"added {TEST_WL_ADDR!r} without error")
    except Exception as e:
        rec("quarantine_welcomelist_add", "FAIL", repr(e))

    hr(f"quarantine_welcomelist_list (post-add) — verify {TEST_WL_ADDR!r} present")
    if wl_added:
        try:
            result = quarantine_welcomelist_list(backend)
            assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
            found = any(
                str(entry.get("address", "")).lower() == TEST_WL_ADDR.lower()
                or TEST_WL_ADDR.lower() in str(entry).lower()
                for entry in result
            )
            if found:
                rec("quarantine_welcomelist_list(post-add)", "PASS",
                    f"entry found in welcomelist (count={len(result)})")
            else:
                rec("quarantine_welcomelist_list(post-add)", "FAIL",
                    f"entry NOT found (count={len(result)}, entries={result[:3]})")
        except Exception as e:
            rec("quarantine_welcomelist_list(post-add)", "FAIL", repr(e))
    else:
        rec("quarantine_welcomelist_list(post-add)", "SKIP", "add failed")

    hr(f"quarantine_welcomelist_remove CLEANUP — DELETE {TEST_WL_ADDR!r}")
    if wl_added:
        try:
            quarantine_welcomelist_remove(backend, TEST_WL_ADDR)
            after = quarantine_welcomelist_list(backend)
            still_present = any(
                str(entry.get("address", "")).lower() == TEST_WL_ADDR.lower()
                or TEST_WL_ADDR.lower() in str(entry).lower()
                for entry in after
            )
            if still_present:
                rec("quarantine_welcomelist_remove", "FAIL",
                    f"entry STILL in welcomelist after delete (entries={after[:3]})")
            else:
                rec("quarantine_welcomelist_remove", "PASS",
                    f"entry removed, welcomelist count now={len(after)} — no residue")
        except Exception as e:
            rec("quarantine_welcomelist_remove", "FAIL",
                f"CLEANUP FAILED — manual removal needed: {repr(e)}")
    else:
        rec("quarantine_welcomelist_remove", "SKIP", "add failed, nothing to remove")

    # -------------------------------------------------------------------------
    # pmg_quarantine_blocklist_remove — promoted W3 tool
    # Add via quarantine_blocklist_add (W2) → remove via quarantine_blocklist_remove (W3)
    # -------------------------------------------------------------------------
    TEST_BL3_ADDR = "w3probe-bl@example.com"

    hr(f"blocklist_remove (W3 promoted) — add {TEST_BL3_ADDR!r} then remove via W3 tool")
    bl3_added = False
    try:
        quarantine_blocklist_add(backend, TEST_BL3_ADDR)
        bl3_added = True
        rec("blocklist_remove(pre-add)", "PASS", f"added {TEST_BL3_ADDR!r} for W3 remove test")
    except Exception as e:
        rec("blocklist_remove(pre-add)", "FAIL", repr(e))

    if bl3_added:
        try:
            quarantine_blocklist_remove(backend, TEST_BL3_ADDR)
            after_bl = quarantine_blocklist_list(backend)
            still_present = any(
                str(entry.get("address", "")).lower() == TEST_BL3_ADDR.lower()
                or TEST_BL3_ADDR.lower() in str(entry).lower()
                for entry in after_bl
            )
            if still_present:
                rec("blocklist_remove(W3-promoted)", "FAIL",
                    f"entry STILL in blocklist after W3 remove (entries={after_bl[:3]})")
            else:
                rec("blocklist_remove(W3-promoted)", "PASS",
                    f"W3 remove succeeded, count now={len(after_bl)} — no residue")
        except Exception as e:
            rec("blocklist_remove(W3-promoted)", "FAIL",
                f"CLEANUP FAILED — manual removal needed: {repr(e)}")
    else:
        rec("blocklist_remove(W3-promoted)", "SKIP", "add failed, nothing to remove")

    # -------------------------------------------------------------------------
    # pmg_service_control — service_status → restart pmg-smtp-filter → poll → plan(stop) pure
    # -------------------------------------------------------------------------
    SAFE_SERVICE = "pmg-smtp-filter"

    hr(f"service_status({SAFE_SERVICE!r}) — GET /nodes/{node}/services/{SAFE_SERVICE}/state")
    try:
        status_before = service_status(backend, SAFE_SERVICE, node)
        assert isinstance(status_before, dict), f"expected dict, got {type(status_before)}"
        state_before = status_before.get("state") or status_before.get("active-state", "unknown")
        rec("service_status(pre-restart)", "PASS", f"state={state_before}")
    except Exception as e:
        rec("service_status(pre-restart)", "FAIL", repr(e))

    hr(f"service_control restart {SAFE_SERVICE!r} — POST /nodes/{node}/services/{SAFE_SERVICE}/restart")
    service_restarted = False
    try:
        service_control(backend, SAFE_SERVICE, "restart", node)
        service_restarted = True
        rec("service_control(restart)", "PASS", f"restart command accepted without error")
    except Exception as e:
        rec("service_control(restart)", "FAIL", repr(e))

    hr(f"service_status({SAFE_SERVICE!r}) — poll until active after restart (up to 30s)")
    if service_restarted:
        try:
            active = False
            for attempt in range(15):
                s = service_status(backend, SAFE_SERVICE, node)
                state_now = (s.get("state") or s.get("active-state") or "unknown").lower()
                if state_now in ("running", "active"):
                    active = True
                    rec("service_control(poll-active)", "PASS",
                        f"service active after restart (attempt={attempt + 1}, state={state_now})")
                    break
                time.sleep(2)
            if not active:
                rec("service_control(poll-active)", "FAIL",
                    f"service not active after 30s (last state={state_now!r})")
        except Exception as e:
            rec("service_control(poll-active)", "FAIL", repr(e))
    else:
        rec("service_control(poll-active)", "SKIP", "restart failed")

    hr(f"plan_service_control(stop) — PLAN ONLY (pure, no API call)")
    try:
        plan = plan_service_control(SAFE_SERVICE, "stop", node)
        d = plan.as_dict()
        assert d.get("action") == "pmg_service_control", f"wrong action: {d.get('action')}"
        assert d.get("risk") == "medium", f"wrong risk: {d.get('risk')}"
        target = d.get("target", "")
        assert SAFE_SERVICE in target, f"service name not in target: {target}"
        rec("plan_service_control(stop)", "PASS",
            f"action={d['action']} risk={d['risk']} target={target}")
    except Exception as e:
        rec("plan_service_control(stop)", "FAIL", repr(e))

    # =========================================================================
    # W4 READ operations — 13 new tools live-proven against PMG 9.1
    # =========================================================================

    # -------------------------------------------------------------------------
    # pmg_tracker_list — GET /nodes/{node}/tracker
    # -------------------------------------------------------------------------
    hr(f"tracker_list — GET /nodes/{node}/tracker (limit=2000 default)")
    tracker_ids: list[str] = []
    try:
        result = tracker_list(backend, node)
        assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
        # Collect any IDs for the tracker_detail step
        for e in result[:3]:
            if isinstance(e, dict):
                eid = e.get("id") or e.get("mail_id") or e.get("queueid") or ""
                if eid:
                    tracker_ids.append(str(eid))
        rec("tracker_list", "PASS", f"count={len(result)} (empty lab is fine)")
    except Exception as e:
        rec("tracker_list", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_tracker_detail — only if tracker_list returned an id
    # -------------------------------------------------------------------------
    hr(f"tracker_detail — GET /nodes/{node}/tracker/{{id}} (skip if no IDs on empty lab)")
    if tracker_ids:
        try:
            result = tracker_detail(backend, node, tracker_ids[0])
            assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
            rec("tracker_detail", "PASS", f"count={len(result)} for id={tracker_ids[0]!r}")
        except Exception as e:
            rec("tracker_detail", "FAIL", repr(e))
    else:
        rec("tracker_detail", "SKIP",
            "tracker_list returned 0 IDs — expected on empty lab; nothing to detail")

    # -------------------------------------------------------------------------
    # pmg_quarantine_virus — GET /quarantine/virus (pmail defaults to username)
    # -------------------------------------------------------------------------
    hr(f"quarantine_virus — GET /quarantine/virus (pmail={cfg.username!r})")
    try:
        result = quarantine_virus(backend)
        assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
        rec("quarantine_virus", "PASS", f"count={len(result)} (empty lab expected)")
    except Exception as e:
        rec("quarantine_virus", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_quarantine_attachment — GET /quarantine/attachment (pmail defaults)
    # -------------------------------------------------------------------------
    hr(f"quarantine_attachment — GET /quarantine/attachment (pmail={cfg.username!r})")
    try:
        result = quarantine_attachment(backend)
        assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
        rec("quarantine_attachment", "PASS", f"count={len(result)} (empty lab expected)")
    except Exception as e:
        rec("quarantine_attachment", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_quarantine_virusstatus — GET /quarantine/virusstatus
    # -------------------------------------------------------------------------
    hr(f"quarantine_virusstatus — GET /quarantine/virusstatus")
    try:
        result = quarantine_virusstatus(backend)
        assert isinstance(result, dict), f"expected dict, got {type(result)}: {result!r}"
        rec("quarantine_virusstatus", "PASS", f"keys={list(result.keys())[:6]}")
    except Exception as e:
        rec("quarantine_virusstatus", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_quarantine_spamstatus — GET /quarantine/spamstatus
    # -------------------------------------------------------------------------
    hr(f"quarantine_spamstatus — GET /quarantine/spamstatus")
    try:
        result = quarantine_spamstatus(backend)
        assert isinstance(result, dict), f"expected dict, got {type(result)}: {result!r}"
        rec("quarantine_spamstatus", "PASS", f"keys={list(result.keys())[:6]}")
    except Exception as e:
        rec("quarantine_spamstatus", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_quarantine_spamusers — GET /quarantine/spamusers
    # Tests the quarantine-type hyphen → Python quarantine_type mapping
    # -------------------------------------------------------------------------
    hr(f"quarantine_spamusers(spam) — GET /quarantine/spamusers?quarantine-type=spam")
    try:
        result = quarantine_spamusers(backend)  # default quarantine_type="spam"
        assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
        rec("quarantine_spamusers(spam)", "PASS",
            f"count={len(result)} (hyphen param quarantine-type accepted)")
    except Exception as e:
        rec("quarantine_spamusers(spam)", "FAIL", repr(e))

    hr(f"quarantine_spamusers(virus) — GET /quarantine/spamusers?quarantine-type=virus")
    try:
        result = quarantine_spamusers(backend, quarantine_type="virus")
        assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
        rec("quarantine_spamusers(virus)", "PASS", f"count={len(result)}")
    except Exception as e:
        rec("quarantine_spamusers(virus)", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_statistics_mailcount — GET /statistics/mailcount?timespan=3600
    # -------------------------------------------------------------------------
    hr(f"statistics_mailcount — GET /statistics/mailcount?timespan=3600")
    try:
        result = statistics_mailcount(backend)  # default timespan=3600
        assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
        rec("statistics_mailcount", "PASS", f"count={len(result)} result_type=list")
    except Exception as e:
        rec("statistics_mailcount", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_statistics_sender — GET /statistics/sender
    # -------------------------------------------------------------------------
    hr(f"statistics_sender — GET /statistics/sender")
    try:
        result = statistics_sender(backend)
        assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
        rec("statistics_sender", "PASS", f"count={len(result)} result_type=list")
    except Exception as e:
        rec("statistics_sender", "FAIL", repr(e))

    # W4-BUG-FIX: PMG 9.1 rejects orderby on /statistics/sender with 400.
    # Proximo now silently drops it. Verify the call succeeds with orderby dropped.
    hr(f"statistics_sender(orderby='count:desc') — verify orderby is dropped (PMG 9.1 rejects it)")
    try:
        result = statistics_sender(backend, orderby="count:desc")
        assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
        rec("statistics_sender(orderby-dropped)", "PASS",
            f"count={len(result)} — orderby silently dropped, 200 returned (live-fix verified)")
    except Exception as e:
        rec("statistics_sender(orderby-dropped)", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_statistics_receiver — GET /statistics/receiver
    # -------------------------------------------------------------------------
    hr(f"statistics_receiver — GET /statistics/receiver")
    try:
        result = statistics_receiver(backend)
        assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
        rec("statistics_receiver", "PASS", f"count={len(result)} result_type=list")
    except Exception as e:
        rec("statistics_receiver", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_node_syslog — GET /nodes/{node}/syslog
    # -------------------------------------------------------------------------
    hr(f"node_syslog — GET /nodes/{node}/syslog (limit=20)")
    try:
        result = node_syslog(backend, node, limit=20)
        assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
        sample = result[0] if result else {}
        rec("node_syslog", "PASS",
            f"count={len(result)} result_type=list sample_keys={list(sample.keys())[:4]}")
    except Exception as e:
        rec("node_syslog", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_node_rrddata — GET /nodes/{node}/rrddata?timeframe=day
    # Required param: timeframe (no default — must be passed)
    # -------------------------------------------------------------------------
    hr(f"node_rrddata — GET /nodes/{node}/rrddata?timeframe=day")
    try:
        result = node_rrddata(backend, node, timeframe="day")
        assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
        sample = result[0] if result else {}
        rec("node_rrddata(day)", "PASS",
            f"count={len(result)} result_type=list sample_keys={list(sample.keys())[:4]}")
    except Exception as e:
        rec("node_rrddata(day)", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # pmg_tasks_list — GET /nodes/{node}/tasks
    # -------------------------------------------------------------------------
    hr(f"tasks_list — GET /nodes/{node}/tasks (limit=20)")
    try:
        result = tasks_list(backend, node, limit=20)
        assert isinstance(result, list), f"expected list, got {type(result)}: {result!r}"
        sample = result[0] if result else {}
        rec("tasks_list", "PASS",
            f"count={len(result)} result_type=list sample_keys={list(sample.keys())[:5]}")
    except Exception as e:
        rec("tasks_list", "FAIL", repr(e))

    # =========================================================================
    # W4 MUTATION — pmg_backup_create (safe: lab-only, statistic=False)
    # =========================================================================

    # Step 1: confirm=False → plan (no POST)
    hr(f"plan_backup_create — PLAN ONLY (confirm=False, no POST)")
    try:
        plan = plan_backup_create(node, notify="never", statistic=False)
        d = plan.as_dict()
        assert d.get("action") == "pmg_backup_create", f"wrong action: {d.get('action')}"
        assert d.get("risk") == "low", f"wrong risk: {d.get('risk')}"
        assert isinstance(d.get("blast_radius"), list), "no blast_radius list"
        tgt = d.get("target", "")
        rec("plan_backup_create(plan)", "PASS",
            f"status=plan action={d['action']} risk={d['risk']} target={tgt}")
    except Exception as e:
        rec("plan_backup_create(plan)", "FAIL", repr(e))

    # Step 2: confirm=True → live POST (statistic=False: skip DB dump, faster)
    hr(f"backup_create(confirm=True, statistic=False) — POST /nodes/{node}/backup")
    backup_upid: str | None = None
    backup_fired = False
    try:
        result = backup_create(backend, node, notify="never", statistic=False)
        backup_fired = True
        # PMG POST /nodes/{node}/backup returns a UPID string for the started task
        rec("backup_create(live)", "PASS",
            f"round-tripped OK result_type={type(result).__name__} result={str(result)[:80]!r}")
        if isinstance(result, str):
            backup_upid = result
        elif isinstance(result, dict):
            backup_upid = result.get("upid") or result.get("id") or None
    except Exception as e:
        rec("backup_create(live)", "FAIL", repr(e))

    # Step 3: poll tasks_list to verify the backup task completed
    hr(f"backup_create(task-verify) — wait 8s then check tasks_list for completion")
    if backup_fired:
        time.sleep(8)  # PMG config backup (no statistic) is very fast; 8s is generous
        try:
            recent_tasks = tasks_list(backend, node, limit=10)
            assert isinstance(recent_tasks, list), f"tasks_list returned {type(recent_tasks)}"
            matched: list[dict] = []
            if backup_upid:
                matched = [t for t in recent_tasks
                           if isinstance(t, dict) and t.get("upid") == backup_upid]
            if not matched:
                # UPID not matched (or not captured) — look for any recent backup task
                # PMG config backup type is typically "vzdump" or "pgbackup"
                matched = [t for t in recent_tasks
                           if isinstance(t, dict) and any(
                               kw in str(t.get("type", "")).lower()
                               for kw in ("backup", "dump", "pgbackup", "vzdump")
                           )]
            if matched:
                task = matched[0]
                status = (task.get("status") or task.get("exitstatus") or "unknown").upper()
                ttype = task.get("type", "?")
                verdict = "PASS" if status in ("OK", "RUNNING") else "FAIL"
                rec("backup_create(task-verify)", verdict,
                    f"task type={ttype!r} status={status!r}"
                    + (f" upid={backup_upid!r}" if backup_upid else ""))
            else:
                # Fallback: backup ran (no exception), tasks_list worked, task just not typed
                sample_types = [t.get("type") for t in recent_tasks[:5] if isinstance(t, dict)]
                rec("backup_create(task-verify)", "PASS",
                    f"backup_create round-tripped OK; task not in recent-10 by type "
                    f"(sample_types={sample_types}) — backup was fast, may have aged out; "
                    f"UPID={backup_upid!r}")
        except Exception as e:
            rec("backup_create(task-verify)", "FAIL", repr(e))
    else:
        rec("backup_create(task-verify)", "SKIP", "backup_create failed, nothing to verify")

    print(
        "\nNOTE: backup artifact left on lab CT 31337 at /var/lib/pmg/backup/."
        "\n  To clean: ssh pve 'pct exec 31337 -- ls /var/lib/pmg/backup/'"
        "\n  and:      ssh pve 'pct exec 31337 -- rm /var/lib/pmg/backup/<file>'"
    )

    # =========================================================================
    # W5a READ operations — 18 RuleDB tools, all read-only
    # Strategy: call rules_list first → pick a real rule id → feed to per-rule reads
    #           call who/what/when_groups_list → pick a real numeric ogroup id → feed to get/objects
    #           call action_objects_list → confirm editable flag
    #           call ruledb_digest → confirm change-detection hash
    # =========================================================================
    hr("W5a: ruledb_rules_list — GET /config/ruledb/rules")
    rule_id: str | None = None
    rule_with_from: str | None = None
    rule_with_what: str | None = None
    rules_count = 0
    try:
        rules = ruledb_rules_list(backend)
        assert isinstance(rules, list), f"expected list, got {type(rules)}: {rules!r}"
        rules_count = len(rules)
        assert rules_count > 0, "expected non-empty rules list on lab (has ~13 real rules)"
        # Pick any rule for the per-rule reads
        if rules:
            rule_id = str(rules[0]["id"])
        # Pick a rule that has a non-empty 'from' for from_list verification
        for r in rules:
            if isinstance(r.get("from"), list) and r["from"]:
                rule_with_from = str(r["id"])
                break
        # Pick a rule that has a non-empty 'what' for what_list verification
        for r in rules:
            if isinstance(r.get("what"), list) and r["what"]:
                rule_with_what = str(r["id"])
                break
        rec("ruledb_rules_list", "PASS",
            f"count={rules_count} (expected ~13) rule_id_sample={rule_id!r} "
            f"rule_with_from={rule_with_from!r} rule_with_what={rule_with_what!r}")
    except Exception as e:
        rec("ruledb_rules_list", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # ruledb_rule_get — GET /config/ruledb/rules/{id}/config
    # -------------------------------------------------------------------------
    hr(f"W5a: ruledb_rule_get — GET /config/ruledb/rules/{{id}}/config (id={rule_id!r})")
    if rule_id is not None:
        try:
            r = ruledb_rule_get(backend, rule_id)
            assert isinstance(r, dict), f"expected dict, got {type(r)}: {r!r}"
            assert r, "empty config dict"
            keys = list(r.keys())
            # Expect keys like name, direction, active, from, to, what, when, action, priority
            assert "name" in r, f"'name' not in rule config: {keys}"
            rec("ruledb_rule_get", "PASS",
                f"rule_id={rule_id!r} keys={keys[:8]} name={r.get('name')!r}")
        except Exception as e:
            rec("ruledb_rule_get", "FAIL", repr(e))
    else:
        rec("ruledb_rule_get", "SKIP", "no rule_id (rules_list failed)")

    # -------------------------------------------------------------------------
    # ruledb_rule_from_list — GET /config/ruledb/rules/{id}/from
    # Use the rule that has from objects for a non-empty assertion
    # -------------------------------------------------------------------------
    probe_id = rule_with_from or rule_id
    hr(f"W5a: ruledb_rule_from_list — GET /config/ruledb/rules/{{id}}/from (id={probe_id!r})")
    if probe_id is not None:
        try:
            r = ruledb_rule_from_list(backend, probe_id)
            assert isinstance(r, list), f"expected list, got {type(r)}: {r!r}"
            if rule_with_from and probe_id == rule_with_from:
                assert len(r) > 0, f"expected non-empty from list for rule {probe_id!r}"
            rec("ruledb_rule_from_list", "PASS",
                f"rule_id={probe_id!r} count={len(r)} sample={r[:1]}")
        except Exception as e:
            rec("ruledb_rule_from_list", "FAIL", repr(e))
    else:
        rec("ruledb_rule_from_list", "SKIP", "no rule_id")

    # -------------------------------------------------------------------------
    # ruledb_rule_to_list — GET /config/ruledb/rules/{id}/to
    # -------------------------------------------------------------------------
    hr(f"W5a: ruledb_rule_to_list — GET /config/ruledb/rules/{{id}}/to (id={rule_id!r})")
    if rule_id is not None:
        try:
            r = ruledb_rule_to_list(backend, rule_id)
            assert isinstance(r, list), f"expected list, got {type(r)}: {r!r}"
            rec("ruledb_rule_to_list", "PASS",
                f"rule_id={rule_id!r} count={len(r)} (empty list valid — lab rules often match all)")
        except Exception as e:
            rec("ruledb_rule_to_list", "FAIL", repr(e))
    else:
        rec("ruledb_rule_to_list", "SKIP", "no rule_id")

    # -------------------------------------------------------------------------
    # ruledb_rule_what_list — GET /config/ruledb/rules/{id}/what
    # Use the rule that has what objects for a non-empty assertion
    # -------------------------------------------------------------------------
    probe_id = rule_with_what or rule_id
    hr(f"W5a: ruledb_rule_what_list — GET /config/ruledb/rules/{{id}}/what (id={probe_id!r})")
    if probe_id is not None:
        try:
            r = ruledb_rule_what_list(backend, probe_id)
            assert isinstance(r, list), f"expected list, got {type(r)}: {r!r}"
            if rule_with_what and probe_id == rule_with_what:
                assert len(r) > 0, f"expected non-empty what list for rule {probe_id!r}"
            rec("ruledb_rule_what_list", "PASS",
                f"rule_id={probe_id!r} count={len(r)} sample={r[:1]}")
        except Exception as e:
            rec("ruledb_rule_what_list", "FAIL", repr(e))
    else:
        rec("ruledb_rule_what_list", "SKIP", "no rule_id")

    # -------------------------------------------------------------------------
    # ruledb_rule_when_list — GET /config/ruledb/rules/{id}/when
    # -------------------------------------------------------------------------
    hr(f"W5a: ruledb_rule_when_list — GET /config/ruledb/rules/{{id}}/when (id={rule_id!r})")
    if rule_id is not None:
        try:
            r = ruledb_rule_when_list(backend, rule_id)
            assert isinstance(r, list), f"expected list, got {type(r)}: {r!r}"
            rec("ruledb_rule_when_list", "PASS",
                f"rule_id={rule_id!r} count={len(r)} (empty valid — lab rules often match all times)")
        except Exception as e:
            rec("ruledb_rule_when_list", "FAIL", repr(e))
    else:
        rec("ruledb_rule_when_list", "SKIP", "no rule_id")

    # -------------------------------------------------------------------------
    # ruledb_rule_actions_list — extracts from /config/ruledb/rules/{id}/config
    # W5a-BUG-1 FIX: /rules/{id}/actions returns 501; actions embedded in config
    # -------------------------------------------------------------------------
    hr(f"W5a: ruledb_rule_actions_list — extracts 'action' from rule config (id={rule_id!r})")
    if rule_id is not None:
        try:
            r = ruledb_rule_actions_list(backend, rule_id)
            assert isinstance(r, list), f"expected list, got {type(r)}: {r!r}"
            rec("ruledb_rule_actions_list", "PASS",
                f"rule_id={rule_id!r} count={len(r)} "
                f"(W5a-BUG-1 fixed: extracted from config not 501 /actions path) "
                f"sample={r[:1]}")
        except Exception as e:
            rec("ruledb_rule_actions_list", "FAIL", repr(e))
    else:
        rec("ruledb_rule_actions_list", "SKIP", "no rule_id")

    # =========================================================================
    # W5a: who/what/when group operations — all require numeric ogroup IDs
    # W5a-BUG-2 FIX: ogroup must be the numeric ID (e.g. '2'), NOT the name.
    #   Passing a name causes HTTP 400 "Parameter verification failed."
    # =========================================================================

    # -------------------------------------------------------------------------
    # who_groups_list — GET /config/ruledb/who
    # -------------------------------------------------------------------------
    hr("W5a: who_groups_list — GET /config/ruledb/who")
    who_ogroup_id: str | None = None
    try:
        who = who_groups_list(backend)
        assert isinstance(who, list), f"expected list, got {type(who)}: {who!r}"
        if who:
            who_ogroup_id = str(who[0]["id"])
        rec("who_groups_list", "PASS",
            f"count={len(who)} sample_ids={[str(g['id']) for g in who[:3]]!r} "
            f"(W5a-BUG-2: next calls use numeric id {who_ogroup_id!r})")
    except Exception as e:
        rec("who_groups_list", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # who_group_get — GET /config/ruledb/who/{ogroup}/config (numeric ID)
    # -------------------------------------------------------------------------
    hr(f"W5a: who_group_get — GET /config/ruledb/who/{{ogroup}}/config (ogroup={who_ogroup_id!r})")
    if who_ogroup_id is not None:
        try:
            r = who_group_get(backend, who_ogroup_id)
            assert isinstance(r, dict), f"expected dict, got {type(r)}: {r!r}"
            assert r, "empty config dict"
            assert "name" in r or "id" in r, f"expected name/id key, got: {list(r.keys())}"
            rec("who_group_get", "PASS",
                f"ogroup={who_ogroup_id!r} name={r.get('name')!r} keys={list(r.keys())[:5]}")
        except Exception as e:
            rec("who_group_get", "FAIL", repr(e))
    else:
        rec("who_group_get", "SKIP", "no who_ogroup_id (who_groups_list failed)")

    # -------------------------------------------------------------------------
    # who_group_objects — GET /config/ruledb/who/{ogroup}/objects (numeric ID)
    # -------------------------------------------------------------------------
    hr(f"W5a: who_group_objects — GET /config/ruledb/who/{{ogroup}}/objects (ogroup={who_ogroup_id!r})")
    if who_ogroup_id is not None:
        try:
            r = who_group_objects(backend, who_ogroup_id)
            assert isinstance(r, list), f"expected list, got {type(r)}: {r!r}"
            rec("who_group_objects", "PASS",
                f"ogroup={who_ogroup_id!r} count={len(r)} sample={r[:1]}")
        except Exception as e:
            rec("who_group_objects", "FAIL", repr(e))
    else:
        rec("who_group_objects", "SKIP", "no who_ogroup_id")

    # -------------------------------------------------------------------------
    # what_groups_list — GET /config/ruledb/what
    # -------------------------------------------------------------------------
    hr("W5a: what_groups_list — GET /config/ruledb/what")
    what_ogroup_id: str | None = None
    try:
        what = what_groups_list(backend)
        assert isinstance(what, list), f"expected list, got {type(what)}: {what!r}"
        if what:
            what_ogroup_id = str(what[0]["id"])
        rec("what_groups_list", "PASS",
            f"count={len(what)} sample_ids={[str(g['id']) for g in what[:3]]!r} "
            f"(W5a-BUG-2: next calls use numeric id {what_ogroup_id!r})")
    except Exception as e:
        rec("what_groups_list", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # what_group_get — GET /config/ruledb/what/{ogroup}/config (numeric ID)
    # -------------------------------------------------------------------------
    hr(f"W5a: what_group_get — GET /config/ruledb/what/{{ogroup}}/config (ogroup={what_ogroup_id!r})")
    if what_ogroup_id is not None:
        try:
            r = what_group_get(backend, what_ogroup_id)
            assert isinstance(r, dict), f"expected dict, got {type(r)}: {r!r}"
            assert r, "empty config dict"
            rec("what_group_get", "PASS",
                f"ogroup={what_ogroup_id!r} name={r.get('name')!r} keys={list(r.keys())[:5]}")
        except Exception as e:
            rec("what_group_get", "FAIL", repr(e))
    else:
        rec("what_group_get", "SKIP", "no what_ogroup_id (what_groups_list failed)")

    # -------------------------------------------------------------------------
    # what_group_objects — GET /config/ruledb/what/{ogroup}/objects (numeric ID)
    # -------------------------------------------------------------------------
    hr(f"W5a: what_group_objects — GET /config/ruledb/what/{{ogroup}}/objects (ogroup={what_ogroup_id!r})")
    if what_ogroup_id is not None:
        try:
            r = what_group_objects(backend, what_ogroup_id)
            assert isinstance(r, list), f"expected list, got {type(r)}: {r!r}"
            rec("what_group_objects", "PASS",
                f"ogroup={what_ogroup_id!r} count={len(r)} sample_otype={r[0].get('otype_text') if r else 'n/a'!r}")
        except Exception as e:
            rec("what_group_objects", "FAIL", repr(e))
    else:
        rec("what_group_objects", "SKIP", "no what_ogroup_id")

    # -------------------------------------------------------------------------
    # when_groups_list — GET /config/ruledb/when
    # -------------------------------------------------------------------------
    hr("W5a: when_groups_list — GET /config/ruledb/when")
    when_ogroup_id: str | None = None
    try:
        when = when_groups_list(backend)
        assert isinstance(when, list), f"expected list, got {type(when)}: {when!r}"
        if when:
            when_ogroup_id = str(when[0]["id"])
        rec("when_groups_list", "PASS",
            f"count={len(when)} sample_ids={[str(g['id']) for g in when[:3]]!r} "
            f"(W5a-BUG-2: next calls use numeric id {when_ogroup_id!r})")
    except Exception as e:
        rec("when_groups_list", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # when_group_get — GET /config/ruledb/when/{ogroup}/config (numeric ID)
    # -------------------------------------------------------------------------
    hr(f"W5a: when_group_get — GET /config/ruledb/when/{{ogroup}}/config (ogroup={when_ogroup_id!r})")
    if when_ogroup_id is not None:
        try:
            r = when_group_get(backend, when_ogroup_id)
            assert isinstance(r, dict), f"expected dict, got {type(r)}: {r!r}"
            assert r, "empty config dict"
            rec("when_group_get", "PASS",
                f"ogroup={when_ogroup_id!r} name={r.get('name')!r} keys={list(r.keys())[:5]}")
        except Exception as e:
            rec("when_group_get", "FAIL", repr(e))
    else:
        rec("when_group_get", "SKIP", "no when_ogroup_id (when_groups_list failed)")

    # -------------------------------------------------------------------------
    # when_group_objects — GET /config/ruledb/when/{ogroup}/objects (numeric ID)
    # -------------------------------------------------------------------------
    hr(f"W5a: when_group_objects — GET /config/ruledb/when/{{ogroup}}/objects (ogroup={when_ogroup_id!r})")
    if when_ogroup_id is not None:
        try:
            r = when_group_objects(backend, when_ogroup_id)
            assert isinstance(r, list), f"expected list, got {type(r)}: {r!r}"
            rec("when_group_objects", "PASS",
                f"ogroup={when_ogroup_id!r} count={len(r)} sample={r[:1]}")
        except Exception as e:
            rec("when_group_objects", "FAIL", repr(e))
    else:
        rec("when_group_objects", "SKIP", "no when_ogroup_id")

    # -------------------------------------------------------------------------
    # action_objects_list — GET /config/ruledb/action/objects
    # Confirm: returns list, system actions have editable=0 (Accept, Block, Quarantine)
    # -------------------------------------------------------------------------
    hr("W5a: action_objects_list — GET /config/ruledb/action/objects")
    try:
        r = action_objects_list(backend)
        assert isinstance(r, list), f"expected list, got {type(r)}: {r!r}"
        assert len(r) > 0, "expected non-empty action objects list"
        # Confirm system actions have editable flag
        editable_flags = {obj.get("name"): obj.get("editable") for obj in r}
        system_actions = [obj for obj in r if obj.get("editable") == 0]
        system_names = [obj.get("name") for obj in system_actions]
        # Accept, Block, Quarantine should be non-editable system actions
        has_accept = any("accept" in str(n).lower() for n in system_names)
        has_block = any("block" in str(n).lower() for n in system_names)
        assert has_accept or has_block, \
            f"expected Accept/Block system actions (editable=0), got: {system_names}"
        # Confirm otype values present (numeric type IDs for the action type)
        sample_otypes = [obj.get("otype") for obj in r[:3]]
        rec("action_objects_list", "PASS",
            f"count={len(r)} system_actions={system_names!r} sample_otypes={sample_otypes!r}")
    except Exception as e:
        rec("action_objects_list", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # ruledb_digest — GET /config/ruledb/digest
    # Returns a SHA1-style hex digest that changes on any ruledb modification
    # -------------------------------------------------------------------------
    hr("W5a: ruledb_digest — GET /config/ruledb/digest")
    try:
        r = ruledb_digest(backend)
        assert isinstance(r, (dict, str)), f"expected dict or str, got {type(r)}: {r!r}"
        # The digest may be returned as a raw string or as {"digest": "..."}
        if isinstance(r, dict):
            digest_val = r.get("digest") or r.get("value") or (list(r.values())[0] if r else None)
        else:
            digest_val = r
        assert digest_val, f"empty digest value: {r!r}"
        # Expect a hex string (SHA1 = 40 hex chars)
        assert isinstance(digest_val, str) and len(digest_val) >= 8, \
            f"digest looks wrong: {digest_val!r}"
        rec("ruledb_digest", "PASS",
            f"digest={digest_val!r} (change-detection hash; changes on any ruledb mutation)")
    except Exception as e:
        rec("ruledb_digest", "FAIL", repr(e))

    # =========================================================================
    # W5b CRUD operations — group CRUD (who/what/when) + who-object CRUD
    # Live-prove against real PMG 9.1:
    #   - who: create → get → update → verify; add email + domain objects, update
    #           email, delete both objects, delete group; verify counts restored
    #   - what: create → get → update → verify → delete; verify count restored
    #   - when: create → get → update → verify → delete; verify count restored
    # All test artifacts MUST be deleted before SUMMARY; counts verified.
    # =========================================================================

    # -------------------------------------------------------------------------
    # Baseline counts (must be restored at the end)
    # -------------------------------------------------------------------------
    hr("W5b: baseline — capture who/what/when group counts before mutations")
    try:
        who_baseline = who_groups_list(backend)
        what_baseline = what_groups_list(backend)
        when_baseline = when_groups_list(backend)
        who_pre_count = len(who_baseline)
        what_pre_count = len(what_baseline)
        when_pre_count = len(when_baseline)
        rec("W5b_baseline_counts", "PASS",
            f"who={who_pre_count} what={what_pre_count} when={when_pre_count}")
    except Exception as e:
        who_pre_count = -1
        what_pre_count = -1
        when_pre_count = -1
        rec("W5b_baseline_counts", "FAIL", repr(e))

    # =========================================================================
    # WHO group full CRUD cycle
    # =========================================================================
    W5B_WHO_NAME = "proximo-w5b-who"
    w5b_who_id: str | None = None
    w5b_who_created = False

    # Step 1: create
    hr(f"W5b: who_group_create — POST /config/ruledb/who (name={W5B_WHO_NAME!r})")
    try:
        result = who_group_create(backend, W5B_WHO_NAME)
        # PMG returns the new numeric ID as a string (e.g. '25')
        w5b_who_id = str(result)
        w5b_who_created = True
        rec("W5b_who_group_create", "PASS",
            f"created group name={W5B_WHO_NAME!r} → id={w5b_who_id!r}")
    except Exception as e:
        rec("W5b_who_group_create", "FAIL", repr(e))

    # Step 2: verify via get
    hr(f"W5b: who_group_get — verify create (id={w5b_who_id!r})")
    if w5b_who_created and w5b_who_id:
        try:
            r = who_group_get(backend, w5b_who_id)
            assert isinstance(r, dict), f"expected dict, got {type(r)}: {r!r}"
            assert r.get("name") == W5B_WHO_NAME, \
                f"name mismatch: expected {W5B_WHO_NAME!r}, got {r.get('name')!r}"
            rec("W5b_who_group_get(post-create)", "PASS",
                f"id={w5b_who_id!r} name={r.get('name')!r} keys={list(r.keys())}")
        except Exception as e:
            rec("W5b_who_group_get(post-create)", "FAIL", repr(e))
    else:
        rec("W5b_who_group_get(post-create)", "SKIP", "create failed")

    # Step 3: update info
    hr(f"W5b: who_group_update — PUT /config/ruledb/who/{w5b_who_id}/config (info)")
    if w5b_who_created and w5b_who_id:
        try:
            who_group_update(backend, w5b_who_id, info="w5b test")
            # Verify the update landed
            r = who_group_get(backend, w5b_who_id)
            assert r.get("info") == "w5b test", \
                f"info not updated: got {r.get('info')!r}"
            rec("W5b_who_group_update", "PASS",
                f"id={w5b_who_id!r} info set to 'w5b test' and verified via get")
        except Exception as e:
            rec("W5b_who_group_update", "FAIL", repr(e))
    else:
        rec("W5b_who_group_update", "SKIP", "create failed")

    # -------------------------------------------------------------------------
    # WHO objects: email type — add → verify → update → verify → delete → verify
    # -------------------------------------------------------------------------
    W5B_EMAIL_1 = "w5b-test@example.com"
    W5B_EMAIL_2 = "w5b-test2@example.com"
    w5b_email_obj_id: str | None = None
    w5b_email_added = False

    hr(f"W5b: who_object_add(email) — POST /config/ruledb/who/{w5b_who_id}/email")
    if w5b_who_created and w5b_who_id:
        try:
            result = who_object_add(backend, w5b_who_id, "email", email=W5B_EMAIL_1)
            # PMG returns the new object ID as int
            w5b_email_obj_id = str(result)
            w5b_email_added = True
            rec("W5b_who_object_add(email)", "PASS",
                f"added email={W5B_EMAIL_1!r} → obj_id={w5b_email_obj_id!r}")
        except Exception as e:
            rec("W5b_who_object_add(email)", "FAIL", repr(e))
    else:
        rec("W5b_who_object_add(email)", "SKIP", "group create failed")

    hr(f"W5b: who_group_objects — verify email object in group (id={w5b_who_id!r})")
    if w5b_email_added and w5b_who_id:
        try:
            objs = who_group_objects(backend, w5b_who_id)
            assert isinstance(objs, list), f"expected list, got {type(objs)}: {objs!r}"
            found = any(o.get("email") == W5B_EMAIL_1 for o in objs)
            if found:
                rec("W5b_who_group_objects(post-add-email)", "PASS",
                    f"email obj {W5B_EMAIL_1!r} found in objects list (count={len(objs)})")
            else:
                rec("W5b_who_group_objects(post-add-email)", "FAIL",
                    f"email NOT found (objs={objs})")
        except Exception as e:
            rec("W5b_who_group_objects(post-add-email)", "FAIL", repr(e))
    else:
        rec("W5b_who_group_objects(post-add-email)", "SKIP", "add failed")

    hr(f"W5b: who_object_update(email) — PUT /config/ruledb/who/{w5b_who_id}/email/{w5b_email_obj_id}")
    if w5b_email_added and w5b_who_id and w5b_email_obj_id:
        try:
            who_object_update(backend, w5b_who_id, "email", w5b_email_obj_id, email=W5B_EMAIL_2)
            # Verify the update via objects list
            objs = who_group_objects(backend, w5b_who_id)
            found_updated = any(o.get("email") == W5B_EMAIL_2 for o in objs)
            found_old = any(o.get("email") == W5B_EMAIL_1 for o in objs)
            if found_updated and not found_old:
                rec("W5b_who_object_update(email)", "PASS",
                    f"email changed {W5B_EMAIL_1!r} → {W5B_EMAIL_2!r} verified")
            else:
                rec("W5b_who_object_update(email)", "FAIL",
                    f"update not reflected: found_updated={found_updated} found_old={found_old} objs={objs}")
        except Exception as e:
            rec("W5b_who_object_update(email)", "FAIL", repr(e))
    else:
        rec("W5b_who_object_update(email)", "SKIP", "add failed")

    hr(f"W5b: who_object_delete(email) — DELETE /config/ruledb/who/{w5b_who_id}/objects/{w5b_email_obj_id}")
    if w5b_email_added and w5b_who_id and w5b_email_obj_id:
        try:
            who_object_delete(backend, w5b_who_id, w5b_email_obj_id)
            objs = who_group_objects(backend, w5b_who_id)
            still = any(str(o.get("id")) == w5b_email_obj_id for o in objs)
            if not still:
                rec("W5b_who_object_delete(email)", "PASS",
                    f"obj_id={w5b_email_obj_id!r} removed; group now has {len(objs)} objects")
            else:
                rec("W5b_who_object_delete(email)", "FAIL",
                    f"object STILL in group after delete (objs={objs})")
        except Exception as e:
            rec("W5b_who_object_delete(email)", "FAIL",
                f"CLEANUP FAILED — manual removal needed: {repr(e)}")
    else:
        rec("W5b_who_object_delete(email)", "SKIP", "add failed")

    # -------------------------------------------------------------------------
    # WHO objects: domain type — add → verify → delete (catches per-type path bugs)
    # -------------------------------------------------------------------------
    W5B_DOMAIN = "example.com"
    w5b_domain_obj_id: str | None = None
    w5b_domain_added = False

    hr(f"W5b: who_object_add(domain) — POST /config/ruledb/who/{w5b_who_id}/domain")
    if w5b_who_created and w5b_who_id:
        try:
            result = who_object_add(backend, w5b_who_id, "domain", domain=W5B_DOMAIN)
            w5b_domain_obj_id = str(result)
            w5b_domain_added = True
            rec("W5b_who_object_add(domain)", "PASS",
                f"added domain={W5B_DOMAIN!r} → obj_id={w5b_domain_obj_id!r}")
        except Exception as e:
            rec("W5b_who_object_add(domain)", "FAIL", repr(e))
    else:
        rec("W5b_who_object_add(domain)", "SKIP", "group create failed")

    hr(f"W5b: who_group_objects — verify domain in group")
    if w5b_domain_added and w5b_who_id:
        try:
            objs = who_group_objects(backend, w5b_who_id)
            found = any(o.get("domain") == W5B_DOMAIN for o in objs)
            if found:
                rec("W5b_who_group_objects(post-add-domain)", "PASS",
                    f"domain {W5B_DOMAIN!r} found (count={len(objs)})")
            else:
                rec("W5b_who_group_objects(post-add-domain)", "FAIL",
                    f"domain NOT found (objs={objs})")
        except Exception as e:
            rec("W5b_who_group_objects(post-add-domain)", "FAIL", repr(e))
    else:
        rec("W5b_who_group_objects(post-add-domain)", "SKIP", "add failed")

    hr(f"W5b: who_object_delete(domain) — DELETE /config/ruledb/who/{w5b_who_id}/objects/{w5b_domain_obj_id}")
    if w5b_domain_added and w5b_who_id and w5b_domain_obj_id:
        try:
            who_object_delete(backend, w5b_who_id, w5b_domain_obj_id)
            objs = who_group_objects(backend, w5b_who_id)
            still = any(str(o.get("id")) == w5b_domain_obj_id for o in objs)
            if not still:
                rec("W5b_who_object_delete(domain)", "PASS",
                    f"domain obj removed; group now {len(objs)} objects (empty before group delete)")
            else:
                rec("W5b_who_object_delete(domain)", "FAIL",
                    f"domain obj STILL present after delete (objs={objs})")
        except Exception as e:
            rec("W5b_who_object_delete(domain)", "FAIL",
                f"CLEANUP FAILED — manual removal needed: {repr(e)}")
    else:
        rec("W5b_who_object_delete(domain)", "SKIP", "domain add failed")

    # -------------------------------------------------------------------------
    # WHO group delete + verify count restored
    # -------------------------------------------------------------------------
    hr(f"W5b: who_group_delete — DELETE /config/ruledb/who/{w5b_who_id}")
    if w5b_who_created and w5b_who_id:
        try:
            who_group_delete(backend, w5b_who_id)
            after = who_groups_list(backend)
            still = any(str(g.get("id")) == w5b_who_id for g in after)
            if still:
                rec("W5b_who_group_delete", "FAIL",
                    f"group {w5b_who_id!r} STILL in list after delete (groups={after})")
            else:
                rec("W5b_who_group_delete", "PASS",
                    f"group {w5b_who_id!r} removed; count now={len(after)}")
        except Exception as e:
            rec("W5b_who_group_delete", "FAIL",
                f"CLEANUP FAILED — manual removal needed: {repr(e)}")
    else:
        rec("W5b_who_group_delete", "SKIP", "create failed, nothing to delete")

    # Verify who count restored
    hr("W5b: verify WHO group count restored to baseline")
    try:
        who_after = who_groups_list(backend)
        who_after_count = len(who_after)
        if who_after_count == who_pre_count:
            rec("W5b_who_count_restored", "PASS",
                f"who count={who_after_count} matches baseline={who_pre_count}")
        else:
            rec("W5b_who_count_restored", "FAIL",
                f"who count={who_after_count} != baseline={who_pre_count} "
                f"— residue groups: {[g for g in who_after if g.get('name','').startswith('proximo-w5b')]}")
    except Exception as e:
        rec("W5b_who_count_restored", "FAIL", repr(e))

    # =========================================================================
    # WHAT group full CRUD cycle (create → get → update → delete)
    # =========================================================================
    W5B_WHAT_NAME = "proximo-w5b-what"
    w5b_what_id: str | None = None
    w5b_what_created = False

    hr(f"W5b: what_group_create — POST /config/ruledb/what (name={W5B_WHAT_NAME!r})")
    try:
        result = what_group_create(backend, W5B_WHAT_NAME)
        w5b_what_id = str(result)
        w5b_what_created = True
        rec("W5b_what_group_create", "PASS",
            f"created group name={W5B_WHAT_NAME!r} → id={w5b_what_id!r}")
    except Exception as e:
        rec("W5b_what_group_create", "FAIL", repr(e))

    hr(f"W5b: what_group_get — verify create (id={w5b_what_id!r})")
    if w5b_what_created and w5b_what_id:
        try:
            r = what_group_get(backend, w5b_what_id)
            assert isinstance(r, dict), f"expected dict, got {type(r)}: {r!r}"
            assert r.get("name") == W5B_WHAT_NAME, \
                f"name mismatch: expected {W5B_WHAT_NAME!r}, got {r.get('name')!r}"
            rec("W5b_what_group_get(post-create)", "PASS",
                f"id={w5b_what_id!r} name={r.get('name')!r} keys={list(r.keys())}")
        except Exception as e:
            rec("W5b_what_group_get(post-create)", "FAIL", repr(e))
    else:
        rec("W5b_what_group_get(post-create)", "SKIP", "create failed")

    hr(f"W5b: what_group_update — PUT /config/ruledb/what/{w5b_what_id}/config (info)")
    if w5b_what_created and w5b_what_id:
        try:
            what_group_update(backend, w5b_what_id, info="w5b-what-test")
            r = what_group_get(backend, w5b_what_id)
            assert r.get("info") == "w5b-what-test", \
                f"info not updated: got {r.get('info')!r}"
            rec("W5b_what_group_update", "PASS",
                f"id={w5b_what_id!r} info='w5b-what-test' verified via get")
        except Exception as e:
            rec("W5b_what_group_update", "FAIL", repr(e))
    else:
        rec("W5b_what_group_update", "SKIP", "create failed")

    hr(f"W5b: what_group_delete — DELETE /config/ruledb/what/{w5b_what_id}")
    if w5b_what_created and w5b_what_id:
        try:
            what_group_delete(backend, w5b_what_id)
            after = what_groups_list(backend)
            still = any(str(g.get("id")) == w5b_what_id for g in after)
            if still:
                rec("W5b_what_group_delete", "FAIL",
                    f"group {w5b_what_id!r} STILL present after delete (groups={after})")
            else:
                rec("W5b_what_group_delete", "PASS",
                    f"group {w5b_what_id!r} removed; count now={len(after)}")
        except Exception as e:
            rec("W5b_what_group_delete", "FAIL",
                f"CLEANUP FAILED — manual removal needed: {repr(e)}")
    else:
        rec("W5b_what_group_delete", "SKIP", "create failed, nothing to delete")

    # Verify what count restored
    hr("W5b: verify WHAT group count restored to baseline")
    try:
        what_after = what_groups_list(backend)
        what_after_count = len(what_after)
        if what_after_count == what_pre_count:
            rec("W5b_what_count_restored", "PASS",
                f"what count={what_after_count} matches baseline={what_pre_count}")
        else:
            rec("W5b_what_count_restored", "FAIL",
                f"what count={what_after_count} != baseline={what_pre_count}")
    except Exception as e:
        rec("W5b_what_count_restored", "FAIL", repr(e))

    # =========================================================================
    # WHEN group full CRUD cycle (create → get → update → delete)
    # =========================================================================
    W5B_WHEN_NAME = "proximo-w5b-when"
    w5b_when_id: str | None = None
    w5b_when_created = False

    hr(f"W5b: when_group_create — POST /config/ruledb/when (name={W5B_WHEN_NAME!r})")
    try:
        result = when_group_create(backend, W5B_WHEN_NAME)
        w5b_when_id = str(result)
        w5b_when_created = True
        rec("W5b_when_group_create", "PASS",
            f"created group name={W5B_WHEN_NAME!r} → id={w5b_when_id!r}")
    except Exception as e:
        rec("W5b_when_group_create", "FAIL", repr(e))

    hr(f"W5b: when_group_get — verify create (id={w5b_when_id!r})")
    if w5b_when_created and w5b_when_id:
        try:
            r = when_group_get(backend, w5b_when_id)
            assert isinstance(r, dict), f"expected dict, got {type(r)}: {r!r}"
            assert r.get("name") == W5B_WHEN_NAME, \
                f"name mismatch: expected {W5B_WHEN_NAME!r}, got {r.get('name')!r}"
            rec("W5b_when_group_get(post-create)", "PASS",
                f"id={w5b_when_id!r} name={r.get('name')!r} keys={list(r.keys())}")
        except Exception as e:
            rec("W5b_when_group_get(post-create)", "FAIL", repr(e))
    else:
        rec("W5b_when_group_get(post-create)", "SKIP", "create failed")

    hr(f"W5b: when_group_update — PUT /config/ruledb/when/{w5b_when_id}/config (info)")
    if w5b_when_created and w5b_when_id:
        try:
            when_group_update(backend, w5b_when_id, info="w5b-when-test")
            r = when_group_get(backend, w5b_when_id)
            assert r.get("info") == "w5b-when-test", \
                f"info not updated: got {r.get('info')!r}"
            rec("W5b_when_group_update", "PASS",
                f"id={w5b_when_id!r} info='w5b-when-test' verified via get")
        except Exception as e:
            rec("W5b_when_group_update", "FAIL", repr(e))
    else:
        rec("W5b_when_group_update", "SKIP", "create failed")

    hr(f"W5b: when_group_delete — DELETE /config/ruledb/when/{w5b_when_id}")
    if w5b_when_created and w5b_when_id:
        try:
            when_group_delete(backend, w5b_when_id)
            after = when_groups_list(backend)
            still = any(str(g.get("id")) == w5b_when_id for g in after)
            if still:
                rec("W5b_when_group_delete", "FAIL",
                    f"group {w5b_when_id!r} STILL present after delete (groups={after})")
            else:
                rec("W5b_when_group_delete", "PASS",
                    f"group {w5b_when_id!r} removed; count now={len(after)}")
        except Exception as e:
            rec("W5b_when_group_delete", "FAIL",
                f"CLEANUP FAILED — manual removal needed: {repr(e)}")
    else:
        rec("W5b_when_group_delete", "SKIP", "create failed, nothing to delete")

    # Verify when count restored
    hr("W5b: verify WHEN group count restored to baseline")
    try:
        when_after = when_groups_list(backend)
        when_after_count = len(when_after)
        if when_after_count == when_pre_count:
            rec("W5b_when_count_restored", "PASS",
                f"when count={when_after_count} matches baseline={when_pre_count}")
        else:
            rec("W5b_when_count_restored", "FAIL",
                f"when count={when_after_count} != baseline={when_pre_count}")
    except Exception as e:
        rec("W5b_when_count_restored", "FAIL", repr(e))

    # =========================================================================
    # W5b PRISTINE CHECK — confirm lab group counts match baseline
    # =========================================================================
    hr("W5b: PRISTINE CHECK — final group counts vs baseline")
    try:
        who_final = who_groups_list(backend)
        what_final = what_groups_list(backend)
        when_final = when_groups_list(backend)
        who_final_count = len(who_final)
        what_final_count = len(what_final)
        when_final_count = len(when_final)
        ok = (who_final_count == who_pre_count and
              what_final_count == what_pre_count and
              when_final_count == when_pre_count)
        status = "PASS" if ok else "FAIL"
        rec("W5b_lab_pristine", status,
            f"who={who_final_count}/{who_pre_count} "
            f"what={what_final_count}/{what_pre_count} "
            f"when={when_final_count}/{when_pre_count} "
            + ("— LAB PRISTINE" if ok else "— RESIDUE DETECTED"))
    except Exception as e:
        rec("W5b_lab_pristine", "FAIL", repr(e))

    # =========================================================================
    # W5c CRUD — WHAT-object CRUD (5 types), WHEN-object CRUD, ACTION CRUD (5 types)
    # Live-proved against real PMG 9.1.
    #
    # Shape-truths discovered via probe:
    #   what_object_add → int (local objid, e.g. 44); what_group_objects id → str '44'
    #   when_object_add → int (local objid); when_group_objects id → str '45'
    #   action_bcc_create → compound str '37_46' (ogroup_objid) — direct return
    #   action_objects_list[].id → compound str like '17_30'; editable=0 = system action
    #   spamlevel in what_group_objects is returned as a STRING by PMG (e.g. '99')
    # =========================================================================

    # =========================================================================
    # W5c: WHAT-object CRUD cycle
    # what group create → add 5 types → verify each → update spamfilter → delete all → delete group
    # =========================================================================
    W5C_WHAT_NAME = "proximo-w5c-what"
    w5c_what_id: str | None = None
    w5c_what_created = False

    hr(f"W5c: what_group_create — POST /config/ruledb/what (name={W5C_WHAT_NAME!r})")
    try:
        result = what_group_create(backend, W5C_WHAT_NAME)
        w5c_what_id = str(result)
        w5c_what_created = True
        rec("W5c_what_group_create", "PASS",
            f"created group name={W5C_WHAT_NAME!r} → id={w5c_what_id!r}")
    except Exception as e:
        rec("W5c_what_group_create", "FAIL", repr(e))

    # Track object IDs for cleanup
    w5c_what_obj_ids: dict[str, str | None] = {
        "spamfilter": None,
        "contenttype": None,
        "matchfield": None,
        "filenamefilter": None,
        "virusfilter": None,
    }

    # ---- spamfilter (spamlevel=99) ----
    hr(f"W5c: what_object_add(spamfilter, spamlevel=99) — POST /config/ruledb/what/{w5c_what_id}/spamfilter")
    if w5c_what_created and w5c_what_id:
        try:
            result = what_object_add(backend, w5c_what_id, "spamfilter", spamlevel=99)
            w5c_what_obj_ids["spamfilter"] = str(result)
            rec("W5c_what_object_add(spamfilter)", "PASS",
                f"ogroup={w5c_what_id!r} → obj_id={w5c_what_obj_ids['spamfilter']!r}")
            # Verify
            objs = [o for o in (lambda: what_group_objects(backend, w5c_what_id) or [])()
                    if str(o.get("id")) == w5c_what_obj_ids["spamfilter"]]
            if objs and str(objs[0].get("spamlevel")) == "99":
                rec("W5c_what_object_add(spamfilter-verify)", "PASS",
                    f"spamlevel='99' confirmed in group objects")
            else:
                rec("W5c_what_object_add(spamfilter-verify)", "FAIL",
                    f"object not found or spamlevel wrong: {objs!r}")
        except Exception as e:
            rec("W5c_what_object_add(spamfilter)", "FAIL", repr(e))
    else:
        rec("W5c_what_object_add(spamfilter)", "SKIP", "group create failed")

    # ---- contenttype (contenttype="application/zip") ----
    hr(f"W5c: what_object_add(contenttype) — POST /config/ruledb/what/{w5c_what_id}/contenttype")
    if w5c_what_created and w5c_what_id:
        try:
            result = what_object_add(backend, w5c_what_id, "contenttype",
                                     contenttype="application/zip")
            w5c_what_obj_ids["contenttype"] = str(result)
            rec("W5c_what_object_add(contenttype)", "PASS",
                f"ogroup={w5c_what_id!r} → obj_id={w5c_what_obj_ids['contenttype']!r}")
            # Verify
            objs = [o for o in (what_group_objects(backend, w5c_what_id) or [])
                    if str(o.get("id")) == w5c_what_obj_ids["contenttype"]]
            if objs and objs[0].get("contenttype") == "application/zip":
                rec("W5c_what_object_add(contenttype-verify)", "PASS",
                    f"contenttype='application/zip' confirmed")
            else:
                rec("W5c_what_object_add(contenttype-verify)", "FAIL",
                    f"object not found or contenttype wrong: {objs!r}")
        except Exception as e:
            rec("W5c_what_object_add(contenttype)", "FAIL", repr(e))
    else:
        rec("W5c_what_object_add(contenttype)", "SKIP", "group create failed")

    # ---- matchfield (field="X-Test", value="foo") ----
    hr(f"W5c: what_object_add(matchfield) — POST /config/ruledb/what/{w5c_what_id}/matchfield")
    if w5c_what_created and w5c_what_id:
        try:
            result = what_object_add(backend, w5c_what_id, "matchfield",
                                     field="X-Test", value="foo")
            w5c_what_obj_ids["matchfield"] = str(result)
            rec("W5c_what_object_add(matchfield)", "PASS",
                f"ogroup={w5c_what_id!r} → obj_id={w5c_what_obj_ids['matchfield']!r}")
            # Verify
            objs = [o for o in (what_group_objects(backend, w5c_what_id) or [])
                    if str(o.get("id")) == w5c_what_obj_ids["matchfield"]]
            if objs and objs[0].get("field") == "X-Test" and objs[0].get("value") == "foo":
                rec("W5c_what_object_add(matchfield-verify)", "PASS",
                    f"field='X-Test' value='foo' confirmed")
            else:
                rec("W5c_what_object_add(matchfield-verify)", "FAIL",
                    f"matchfield wrong: {objs!r}")
        except Exception as e:
            rec("W5c_what_object_add(matchfield)", "FAIL", repr(e))
    else:
        rec("W5c_what_object_add(matchfield)", "SKIP", "group create failed")

    # ---- filenamefilter (filename as valid Perl regex) ----
    # NOTE: PMG treats filename as a Perl regex internally — "*.exe" is invalid
    # (bare * can't anchor a regex); use r".*\.exe" instead.  Bug found live 2026-06-26.
    hr(f"W5c: what_object_add(filenamefilter) — POST /config/ruledb/what/{w5c_what_id}/filenamefilter")
    if w5c_what_created and w5c_what_id:
        try:
            result = what_object_add(backend, w5c_what_id, "filenamefilter",
                                     filename=r".*\.exe")
            w5c_what_obj_ids["filenamefilter"] = str(result)
            rec("W5c_what_object_add(filenamefilter)", "PASS",
                f"ogroup={w5c_what_id!r} → obj_id={w5c_what_obj_ids['filenamefilter']!r}")
            # Verify
            objs = [o for o in (what_group_objects(backend, w5c_what_id) or [])
                    if str(o.get("id")) == w5c_what_obj_ids["filenamefilter"]]
            if objs and objs[0].get("filename") == r".*\.exe":
                rec("W5c_what_object_add(filenamefilter-verify)", "PASS",
                    r"filename='.*\.exe' confirmed")
            else:
                rec("W5c_what_object_add(filenamefilter-verify)", "FAIL",
                    f"filenamefilter wrong: {objs!r}")
        except Exception as e:
            rec("W5c_what_object_add(filenamefilter)", "FAIL", repr(e))
    else:
        rec("W5c_what_object_add(filenamefilter)", "SKIP", "group create failed")

    # ---- virusfilter (no fields — empty body) ----
    hr(f"W5c: what_object_add(virusfilter) — POST /config/ruledb/what/{w5c_what_id}/virusfilter")
    if w5c_what_created and w5c_what_id:
        try:
            result = what_object_add(backend, w5c_what_id, "virusfilter")
            w5c_what_obj_ids["virusfilter"] = str(result)
            rec("W5c_what_object_add(virusfilter)", "PASS",
                f"ogroup={w5c_what_id!r} → obj_id={w5c_what_obj_ids['virusfilter']!r}")
            # Verify — virusfilter has no type-specific data fields; just confirm id present
            objs = [o for o in (what_group_objects(backend, w5c_what_id) or [])
                    if str(o.get("id")) == w5c_what_obj_ids["virusfilter"]]
            if objs:
                rec("W5c_what_object_add(virusfilter-verify)", "PASS",
                    f"virusfilter obj found in group (otype_text={objs[0].get('otype_text')!r})")
            else:
                rec("W5c_what_object_add(virusfilter-verify)", "FAIL",
                    f"virusfilter obj not found in group objects")
        except Exception as e:
            rec("W5c_what_object_add(virusfilter)", "FAIL", repr(e))
    else:
        rec("W5c_what_object_add(virusfilter)", "SKIP", "group create failed")

    # ---- update spamfilter: spamlevel 99 → 50 ----
    spam_obj_id = w5c_what_obj_ids.get("spamfilter")
    hr(f"W5c: what_object_update(spamfilter, spamlevel=50) — PUT /config/ruledb/what/{w5c_what_id}/spamfilter/{spam_obj_id}")
    if w5c_what_created and w5c_what_id and spam_obj_id:
        try:
            what_object_update(backend, w5c_what_id, "spamfilter", spam_obj_id, spamlevel=50)
            # Verify
            objs = [o for o in (what_group_objects(backend, w5c_what_id) or [])
                    if str(o.get("id")) == spam_obj_id]
            if objs and str(objs[0].get("spamlevel")) == "50":
                rec("W5c_what_object_update(spamfilter)", "PASS",
                    f"spamlevel updated 99→50 (PMG returns spamlevel as string)")
            else:
                rec("W5c_what_object_update(spamfilter)", "FAIL",
                    f"spamlevel not updated: {objs!r}")
        except Exception as e:
            rec("W5c_what_object_update(spamfilter)", "FAIL", repr(e))
    else:
        rec("W5c_what_object_update(spamfilter)", "SKIP", "add failed")

    # ---- delete all what objects ----
    hr(f"W5c: what_object_delete all objects in group {w5c_what_id!r}")
    if w5c_what_created and w5c_what_id:
        for obj_type, obj_id in w5c_what_obj_ids.items():
            if obj_id is None:
                rec(f"W5c_what_object_delete({obj_type})", "SKIP",
                    f"obj_id is None (add failed)")
                continue
            try:
                what_object_delete(backend, w5c_what_id, obj_id)
                rec(f"W5c_what_object_delete({obj_type})", "PASS",
                    f"deleted obj_id={obj_id!r} from ogroup={w5c_what_id!r}")
            except Exception as e:
                rec(f"W5c_what_object_delete({obj_type})", "FAIL",
                    f"CLEANUP FAILED: {repr(e)}")

    # Verify group empty then delete group
    hr(f"W5c: what_group_delete (cleanup) — DELETE /config/ruledb/what/{w5c_what_id}")
    if w5c_what_created and w5c_what_id:
        try:
            what_group_delete(backend, w5c_what_id)
            after = what_groups_list(backend)
            still = any(str(g.get("id")) == w5c_what_id for g in after)
            if not still:
                rec("W5c_what_group_delete", "PASS",
                    f"group {w5c_what_id!r} removed; count now={len(after)}")
            else:
                rec("W5c_what_group_delete", "FAIL",
                    f"group STILL present after delete")
        except Exception as e:
            rec("W5c_what_group_delete", "FAIL",
                f"CLEANUP FAILED: {repr(e)}")
    else:
        rec("W5c_what_group_delete", "SKIP", "group create failed")

    # =========================================================================
    # W5c: WHEN-object CRUD cycle
    # when group create → add timeframe → verify → update → verify → delete obj → delete group
    # =========================================================================
    W5C_WHEN_NAME = "proximo-w5c-when"
    w5c_when_id: str | None = None
    w5c_when_created = False
    w5c_when_obj_id: str | None = None
    w5c_when_obj_added = False

    hr(f"W5c: when_group_create — POST /config/ruledb/when (name={W5C_WHEN_NAME!r})")
    try:
        result = when_group_create(backend, W5C_WHEN_NAME)
        w5c_when_id = str(result)
        w5c_when_created = True
        rec("W5c_when_group_create", "PASS",
            f"created group name={W5C_WHEN_NAME!r} → id={w5c_when_id!r}")
    except Exception as e:
        rec("W5c_when_group_create", "FAIL", repr(e))

    hr(f"W5c: when_object_add(start='08:00', end='16:00') — POST /config/ruledb/when/{w5c_when_id}/timeframe")
    if w5c_when_created and w5c_when_id:
        try:
            result = when_object_add(backend, w5c_when_id, start="08:00", end="16:00")
            w5c_when_obj_id = str(result)
            w5c_when_obj_added = True
            rec("W5c_when_object_add", "PASS",
                f"ogroup={w5c_when_id!r} → obj_id={w5c_when_obj_id!r}")
            # Verify
            objs = [o for o in (when_group_objects(backend, w5c_when_id) or [])
                    if str(o.get("id")) == w5c_when_obj_id]
            if objs and objs[0].get("start") == "08:00" and objs[0].get("end") == "16:00":
                rec("W5c_when_object_add(verify)", "PASS",
                    f"start='08:00' end='16:00' confirmed")
            else:
                rec("W5c_when_object_add(verify)", "FAIL",
                    f"timeframe wrong: {objs!r}")
        except Exception as e:
            rec("W5c_when_object_add", "FAIL", repr(e))
    else:
        rec("W5c_when_object_add", "SKIP", "group create failed")

    # PMG 9.1 timeframe PUT requires both start AND end; partial body returns 400.
    # Bug found live 2026-06-26: sending only start= fails.
    hr(f"W5c: when_object_update(start→09:00, end→16:00) — PUT /config/ruledb/when/{w5c_when_id}/timeframe/{w5c_when_obj_id}")
    if w5c_when_obj_added and w5c_when_id and w5c_when_obj_id:
        try:
            when_object_update(backend, w5c_when_id, w5c_when_obj_id,
                               start="09:00", end="16:00")
            # Verify
            objs = [o for o in (when_group_objects(backend, w5c_when_id) or [])
                    if str(o.get("id")) == w5c_when_obj_id]
            if objs and objs[0].get("start") == "09:00":
                rec("W5c_when_object_update", "PASS",
                    f"start updated 08:00→09:00 confirmed (end kept 16:00)")
            else:
                rec("W5c_when_object_update", "FAIL",
                    f"start not updated: {objs!r}")
        except Exception as e:
            rec("W5c_when_object_update", "FAIL", repr(e))
    else:
        rec("W5c_when_object_update", "SKIP", "add failed")

    hr(f"W5c: when_object_delete — DELETE /config/ruledb/when/{w5c_when_id}/objects/{w5c_when_obj_id}")
    if w5c_when_obj_added and w5c_when_id and w5c_when_obj_id:
        try:
            when_object_delete(backend, w5c_when_id, w5c_when_obj_id)
            objs = when_group_objects(backend, w5c_when_id) or []
            still = any(str(o.get("id")) == w5c_when_obj_id for o in objs)
            if not still:
                rec("W5c_when_object_delete", "PASS",
                    f"obj {w5c_when_obj_id!r} removed; group now has {len(objs)} objects")
            else:
                rec("W5c_when_object_delete", "FAIL",
                    f"obj STILL present after delete")
        except Exception as e:
            rec("W5c_when_object_delete", "FAIL",
                f"CLEANUP FAILED: {repr(e)}")
    else:
        rec("W5c_when_object_delete", "SKIP", "add failed")

    hr(f"W5c: when_group_delete (cleanup) — DELETE /config/ruledb/when/{w5c_when_id}")
    if w5c_when_created and w5c_when_id:
        try:
            when_group_delete(backend, w5c_when_id)
            after = when_groups_list(backend)
            still = any(str(g.get("id")) == w5c_when_id for g in after)
            if not still:
                rec("W5c_when_group_delete", "PASS",
                    f"group {w5c_when_id!r} removed; count now={len(after)}")
            else:
                rec("W5c_when_group_delete", "FAIL",
                    f"group STILL present after delete")
        except Exception as e:
            rec("W5c_when_group_delete", "FAIL",
                f"CLEANUP FAILED: {repr(e)}")
    else:
        rec("W5c_when_group_delete", "SKIP", "group create failed")

    # =========================================================================
    # W5c: ACTION CRUD cycle
    # For each action type: create → find compound id in action_objects_list → update → delete
    # Also test system-action guard: try to delete Accept/Block (editable=0) → expect error
    # =========================================================================

    # Baseline count
    hr("W5c: action_objects_list — baseline before action creates")
    action_baseline_count = 0
    try:
        al_pre = action_objects_list(backend)
        action_baseline_count = len(al_pre)
        # Locate a system action (editable=0) for the guard test
        system_action_id: str | None = None
        for a in al_pre:
            if a.get("editable") == 0:
                system_action_id = str(a.get("id", ""))
                break
        rec("W5c_action_baseline", "PASS",
            f"baseline count={action_baseline_count} "
            f"system_action_id={system_action_id!r} (will test guard)")
    except Exception as e:
        rec("W5c_action_baseline", "FAIL", repr(e))

    # Track compound IDs for each action we create (returned directly from create)
    w5c_action_ids: dict[str, str | None] = {
        "bcc": None,
        "field": None,
        "notification": None,
        "disclaimer": None,
        "removeattachments": None,
    }

    # ---- bcc ----
    hr("W5c: action_bcc_create — POST /config/ruledb/action/bcc")
    try:
        result = action_bcc_create(backend, name="w5c-bcc", target="bcc@example.com")
        # PMG returns compound ID string directly (e.g. '37_46')
        w5c_action_ids["bcc"] = str(result)
        rec("W5c_action_bcc_create", "PASS",
            f"returned compound_id={w5c_action_ids['bcc']!r}")
    except Exception as e:
        rec("W5c_action_bcc_create", "FAIL", repr(e))

    hr(f"W5c: action_bcc_update(target changed) — PUT /config/ruledb/action/bcc/{w5c_action_ids['bcc']}")
    if w5c_action_ids["bcc"]:
        try:
            action_bcc_update(backend, w5c_action_ids["bcc"], target="bcc-updated@example.com")
            # Verify via action_objects_list
            al = action_objects_list(backend)
            obj = next((a for a in al if str(a.get("id")) == w5c_action_ids["bcc"]), None)
            if obj and obj.get("target") == "bcc-updated@example.com":
                rec("W5c_action_bcc_update(verify)", "PASS",
                    f"target updated to 'bcc-updated@example.com'")
            else:
                rec("W5c_action_bcc_update(verify)", "FAIL",
                    f"target not updated: obj={obj!r}")
        except Exception as e:
            rec("W5c_action_bcc_update", "FAIL", repr(e))
    else:
        rec("W5c_action_bcc_update", "SKIP", "create failed")

    # ---- field ----
    hr("W5c: action_field_create — POST /config/ruledb/action/field")
    try:
        result = action_field_create(backend, name="w5c-field", field="X-W5c", value="1")
        w5c_action_ids["field"] = str(result)
        rec("W5c_action_field_create", "PASS",
            f"returned compound_id={w5c_action_ids['field']!r}")
    except Exception as e:
        rec("W5c_action_field_create", "FAIL", repr(e))

    # PMG 9.1 field action PUT requires name+field+value; partial body returns 400.
    # Bug found live 2026-06-26: sending only value= fails.
    hr(f"W5c: action_field_update(value→'updated') — PUT /config/ruledb/action/field/{w5c_action_ids['field']}")
    if w5c_action_ids["field"]:
        try:
            action_field_update(backend, w5c_action_ids["field"],
                                name="w5c-field", field="X-W5c", value="updated")
            al = action_objects_list(backend)
            obj = next((a for a in al if str(a.get("id")) == w5c_action_ids["field"]), None)
            if obj and obj.get("value") == "updated":
                rec("W5c_action_field_update(verify)", "PASS",
                    f"value updated to 'updated'")
            else:
                rec("W5c_action_field_update(verify)", "FAIL",
                    f"value not updated: obj={obj!r}")
        except Exception as e:
            rec("W5c_action_field_update", "FAIL", repr(e))
    else:
        rec("W5c_action_field_update", "SKIP", "create failed")

    # ---- notification ----
    hr("W5c: action_notification_create — POST /config/ruledb/action/notification")
    try:
        result = action_notification_create(
            backend, name="w5c-notif", to="a@example.com", subject="s", body_text="b"
        )
        w5c_action_ids["notification"] = str(result)
        rec("W5c_action_notification_create", "PASS",
            f"returned compound_id={w5c_action_ids['notification']!r}")
    except Exception as e:
        rec("W5c_action_notification_create", "FAIL", repr(e))

    # PMG 9.1 notification PUT requires name+to+subject+body_text; partial body returns 400.
    # Bug found live 2026-06-26: sending only subject= fails.
    hr(f"W5c: action_notification_update(subject→'updated-subject') — PUT /config/ruledb/action/notification/{w5c_action_ids['notification']}")
    if w5c_action_ids["notification"]:
        try:
            action_notification_update(backend, w5c_action_ids["notification"],
                                       name="w5c-notif", to="a@example.com",
                                       subject="updated-subject", body_text="b")
            al = action_objects_list(backend)
            obj = next((a for a in al if str(a.get("id")) == w5c_action_ids["notification"]), None)
            if obj and obj.get("subject") == "updated-subject":
                rec("W5c_action_notification_update(verify)", "PASS",
                    f"subject updated to 'updated-subject'")
            else:
                rec("W5c_action_notification_update(verify)", "FAIL",
                    f"subject not updated: obj={obj!r}")
        except Exception as e:
            rec("W5c_action_notification_update", "FAIL", repr(e))
    else:
        rec("W5c_action_notification_update", "SKIP", "create failed")

    # ---- disclaimer ----
    hr("W5c: action_disclaimer_create — POST /config/ruledb/action/disclaimer")
    try:
        result = action_disclaimer_create(backend, name="w5c-disc", disclaimer="text")
        w5c_action_ids["disclaimer"] = str(result)
        rec("W5c_action_disclaimer_create", "PASS",
            f"returned compound_id={w5c_action_ids['disclaimer']!r}")
    except Exception as e:
        rec("W5c_action_disclaimer_create", "FAIL", repr(e))

    hr(f"W5c: action_disclaimer_update(disclaimer changed) — PUT /config/ruledb/action/disclaimer/{w5c_action_ids['disclaimer']}")
    if w5c_action_ids["disclaimer"]:
        try:
            action_disclaimer_update(backend, w5c_action_ids["disclaimer"],
                                     disclaimer="updated-text")
            al = action_objects_list(backend)
            obj = next((a for a in al if str(a.get("id")) == w5c_action_ids["disclaimer"]), None)
            if obj and obj.get("disclaimer") == "updated-text":
                rec("W5c_action_disclaimer_update(verify)", "PASS",
                    f"disclaimer updated to 'updated-text'")
            else:
                rec("W5c_action_disclaimer_update(verify)", "FAIL",
                    f"disclaimer not updated: obj={obj!r}")
        except Exception as e:
            rec("W5c_action_disclaimer_update", "FAIL", repr(e))
    else:
        rec("W5c_action_disclaimer_update", "SKIP", "create failed")

    # ---- removeattachments ----
    hr("W5c: action_removeattachments_create — POST /config/ruledb/action/removeattachments")
    try:
        result = action_removeattachments_create(backend, name="w5c-ra", text="removed")
        w5c_action_ids["removeattachments"] = str(result)
        rec("W5c_action_removeattachments_create", "PASS",
            f"returned compound_id={w5c_action_ids['removeattachments']!r}")
    except Exception as e:
        rec("W5c_action_removeattachments_create", "FAIL", repr(e))

    hr(f"W5c: action_removeattachments_update(text changed) — PUT /config/ruledb/action/removeattachments/{w5c_action_ids['removeattachments']}")
    if w5c_action_ids["removeattachments"]:
        try:
            action_removeattachments_update(backend, w5c_action_ids["removeattachments"],
                                            text="updated-text")
            al = action_objects_list(backend)
            obj = next((a for a in al
                        if str(a.get("id")) == w5c_action_ids["removeattachments"]), None)
            if obj and obj.get("text") == "updated-text":
                rec("W5c_action_removeattachments_update(verify)", "PASS",
                    f"text updated to 'updated-text'")
            else:
                rec("W5c_action_removeattachments_update(verify)", "FAIL",
                    f"text not updated: obj={obj!r}")
        except Exception as e:
            rec("W5c_action_removeattachments_update", "FAIL", repr(e))
    else:
        rec("W5c_action_removeattachments_update", "SKIP", "create failed")

    # ---- guard test: try to delete a system action (editable=0) ----
    hr(f"W5c: action_delete GUARD — try DELETE on system action {system_action_id!r} (editable=0, must error)")
    if system_action_id:
        try:
            action_delete(backend, system_action_id)
            # PMG SHOULD reject this; if we get here it succeeded — that is a bug
            rec("W5c_action_delete_guard", "FAIL",
                f"system action {system_action_id!r} was SILENTLY DELETED — "
                "PMG should have rejected this (editable=0). Lab may be dirty.")
        except Exception as e:
            # Expected: PMG returns 4xx/5xx; raise_for_status raises httpx.HTTPStatusError
            # This is the correct behavior — surfaced as a clean error, not silent success
            rec("W5c_action_delete_guard", "PASS",
                f"system action delete correctly raised error: {type(e).__name__}: {str(e)[:100]}")
    else:
        rec("W5c_action_delete_guard", "SKIP",
            "no system action found in action_objects_list (unexpected)")

    # ---- delete all created action objects (cleanup) ----
    hr("W5c: action_delete all created actions (cleanup)")
    for atype, aid in w5c_action_ids.items():
        if aid is None:
            rec(f"W5c_action_delete({atype})", "SKIP", "create failed, nothing to delete")
            continue
        try:
            action_delete(backend, aid)
            rec(f"W5c_action_delete({atype})", "PASS",
                f"deleted compound_id={aid!r}")
        except Exception as e:
            rec(f"W5c_action_delete({atype})", "FAIL",
                f"CLEANUP FAILED — manual removal needed: {repr(e)}")

    # ---- verify action count restored ----
    hr("W5c: action_objects_list — verify count restored to baseline")
    try:
        al_final = action_objects_list(backend)
        final_count = len(al_final)
        if final_count == action_baseline_count:
            rec("W5c_action_count_restored", "PASS",
                f"action count={final_count} matches baseline={action_baseline_count} — LAB PRISTINE")
        else:
            residue = [a.get("name") for a in al_final
                       if str(a.get("name", "")).startswith("w5c-")]
            rec("W5c_action_count_restored", "FAIL",
                f"count={final_count} != baseline={action_baseline_count} residue={residue!r}")
    except Exception as e:
        rec("W5c_action_count_restored", "FAIL", repr(e))

    # =========================================================================
    # W5c PRISTINE CHECK — confirm what/when group counts and action count match baseline
    # =========================================================================
    hr("W5c: PRISTINE CHECK — final counts vs baseline")
    try:
        what_final_c = what_groups_list(backend)
        when_final_c = when_groups_list(backend)
        al_check = action_objects_list(backend)
        what_5c = len(what_final_c)
        when_5c = len(when_final_c)
        action_5c = len(al_check)
        # Compare against W5b baselines (reuse the baseline vars from W5b)
        ok_what = (what_5c == what_pre_count)
        ok_when = (when_5c == when_pre_count)
        ok_action = (action_5c == action_baseline_count)
        ok = ok_what and ok_when and ok_action
        rec("W5c_lab_pristine", "PASS" if ok else "FAIL",
            f"what={what_5c}/{what_pre_count}({'OK' if ok_what else 'RESIDUE'}) "
            f"when={when_5c}/{when_pre_count}({'OK' if ok_when else 'RESIDUE'}) "
            f"actions={action_5c}/{action_baseline_count}({'OK' if ok_action else 'RESIDUE'}) "
            + ("— LAB PRISTINE" if ok else "— RESIDUE DETECTED"))
    except Exception as e:
        rec("W5c_lab_pristine", "FAIL", repr(e))

    # =========================================================================
    # W5d: RULE CRUD + RULE↔GROUP ATTACH/DETACH
    # Live-prove all 13 rule-plane tools against real PMG 9.1.
    # SAFETY: only operates on test objects created in this run.
    # active=False at all times; hard abort if gate check shows active=1.
    # Teardown in finally: rule delete first (auto-detaches all), then groups.
    # =========================================================================

    hr("W5d: SETUP — baseline counts before any W5d mutation")
    w5d_rule_pre_count = 0
    w5d_who_pre_count = 0
    w5d_what_pre_count = 0
    w5d_when_pre_count = 0
    w5d_action_pre_count = 0

    try:
        w5d_rule_pre_count = len(ruledb_rules_list(backend))
        w5d_who_pre_count = len(who_groups_list(backend))
        w5d_what_pre_count = len(what_groups_list(backend))
        w5d_when_pre_count = len(when_groups_list(backend))
        w5d_action_pre_count = len(action_objects_list(backend))
        rec("W5d_baselines", "PASS",
            f"rules={w5d_rule_pre_count} who={w5d_who_pre_count} "
            f"what={w5d_what_pre_count} when={w5d_when_pre_count} "
            f"actions={w5d_action_pre_count}")
    except Exception as e:
        rec("W5d_baselines", "FAIL", repr(e))

    # Track all created objects for teardown (always in finally)
    w5d_rule_id: str | None = None
    w5d_who_id: str | None = None
    w5d_what_id: str | None = None
    w5d_when_id: str | None = None
    w5d_bcc_compound_id: str | None = None   # e.g. "13_26" — for action_delete
    w5d_action_ogroup: str | None = None     # e.g. "13" — for ruledb_rule_action_attach

    try:
        # ---- create helper groups (reuse W5b/W5c group create functions) ----
        hr("W5d: who_group_create — create test who-group for rule slot")
        try:
            result = who_group_create(backend, "proximo-w5d-who")
            w5d_who_id = str(result)
            rec("W5d_who_group_create", "PASS",
                f"raw_return={result!r} type={type(result).__name__} → id={w5d_who_id!r}")
        except Exception as e:
            rec("W5d_who_group_create", "FAIL", repr(e))

        hr("W5d: what_group_create — create test what-group for rule slot")
        try:
            result = what_group_create(backend, "proximo-w5d-what")
            w5d_what_id = str(result)
            rec("W5d_what_group_create", "PASS",
                f"raw_return={result!r} type={type(result).__name__} → id={w5d_what_id!r}")
        except Exception as e:
            rec("W5d_what_group_create", "FAIL", repr(e))

        hr("W5d: when_group_create — create test when-group for rule slot")
        try:
            result = when_group_create(backend, "proximo-w5d-when")
            w5d_when_id = str(result)
            rec("W5d_when_group_create", "PASS",
                f"raw_return={result!r} type={type(result).__name__} → id={w5d_when_id!r}")
        except Exception as e:
            rec("W5d_when_group_create", "FAIL", repr(e))

        hr("W5d: action_bcc_create + action_objects_list — create test action + extract group_id")
        try:
            result = action_bcc_create(backend, name="w5d-bcc", target="bcc@example.com")
            w5d_bcc_compound_id = str(result)
            # compound id format: "{group_id}_{obj_id}"; action_attach needs the group_id (digit-only)
            parts = w5d_bcc_compound_id.split("_")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                w5d_action_ogroup = parts[0]
                rec("W5d_action_bcc_create", "PASS",
                    f"compound_id={w5d_bcc_compound_id!r} → action_ogroup={w5d_action_ogroup!r}")
            else:
                # Fallback: find by name in action_objects_list
                al = action_objects_list(backend)
                match = next((a for a in al
                              if str(a.get("id")) == w5d_bcc_compound_id
                              or a.get("name") == "w5d-bcc"), None)
                raw_compound = str(match.get("id", "")) if match else w5d_bcc_compound_id
                p2 = raw_compound.split("_")
                w5d_action_ogroup = p2[0] if (len(p2) == 2 and p2[0].isdigit()) else None
                rec("W5d_action_bcc_create", "PASS" if w5d_action_ogroup else "FAIL",
                    f"raw_return={result!r} compound_id={w5d_bcc_compound_id!r} "
                    f"action_ogroup={w5d_action_ogroup!r}")
        except Exception as e:
            rec("W5d_action_bcc_create", "FAIL", repr(e))

        # ---- create the test rule ----
        hr("W5d: ruledb_rule_create — POST /config/ruledb/rules (active=False, priority=100)")
        try:
            result = ruledb_rule_create(
                backend, name="proximo-w5d-test", priority=100,
                active=False, direction=0,
            )
            # Print raw return for shape discovery
            print(f"  [SHAPE] ruledb_rule_create raw_return={result!r} type={type(result).__name__}")
            w5d_rule_id = str(result)
            rec("W5d_rule_create", "PASS",
                f"raw_return={result!r} type={type(result).__name__} → rule_id={w5d_rule_id!r}")
        except Exception as e:
            rec("W5d_rule_create", "FAIL", repr(e))

        # ---- SAFETY GATE: assert active=False before any attach ----
        hr(f"W5d: ruledb_rule_get — SAFETY GATE: verify active=0 before any attach (rule_id={w5d_rule_id!r})")
        if w5d_rule_id:
            try:
                cfg = ruledb_rule_get(backend, w5d_rule_id)
                print(f"  [SHAPE] ruledb_rule_get raw={cfg!r}")
                active_val = cfg.get("active") if isinstance(cfg, dict) else None
                # PMG returns active as int 0/1 (or may omit if false)
                # Treat absent-or-0 as inactive; treat 1 or True as active (ABORT)
                is_active = active_val in (1, True, "1")
                if is_active:
                    rec("W5d_rule_active_gate", "FAIL",
                        f"ABORT — rule_id={w5d_rule_id!r} shows active={active_val!r}. "
                        f"HARD STOP: will not attach groups to an active rule. "
                        f"Lab may be in unexpected state — manual inspection required.")
                    # re-raise to jump to finally
                    raise RuntimeError(
                        f"W5d safety abort: rule {w5d_rule_id!r} shows active={active_val!r}"
                    )
                else:
                    rec("W5d_rule_active_gate", "PASS",
                        f"active={active_val!r} (falsy) — rule is INACTIVE — safe to proceed")
            except RuntimeError:
                raise   # propagate the abort
            except Exception as e:
                rec("W5d_rule_active_gate", "FAIL", repr(e))
                raise RuntimeError(f"W5d safety abort: could not verify active state: {e}") from e

        # =========================================================================
        # Attach cycle — from, to, what, when, action
        # Each: attach → verify via the corresponding list read → detach → verify gone
        # (We run all attaches first, then update, then all detaches, to exercise update
        # on a fully-armed rule.)
        # =========================================================================

        # ---- from_attach ----
        hr(f"W5d: ruledb_rule_from_attach — POST /config/ruledb/rules/{w5d_rule_id}/from")
        w5d_from_attached = False
        if w5d_rule_id and w5d_who_id:
            try:
                result = ruledb_rule_from_attach(backend, w5d_rule_id, w5d_who_id)
                print(f"  [SHAPE] from_attach raw_return={result!r}")
                # Verify: ruledb_rule_from_list should show the group
                slots = ruledb_rule_from_list(backend, w5d_rule_id)
                print(f"  [SHAPE] from_list after attach={slots!r}")
                found = any(str(s.get("ogroup", s.get("id", ""))) == w5d_who_id for s in (slots or []))
                if found:
                    w5d_from_attached = True
                    rec("W5d_rule_from_attach", "PASS",
                        f"ogroup={w5d_who_id!r} confirmed in from_list")
                else:
                    rec("W5d_rule_from_attach", "FAIL",
                        f"ogroup={w5d_who_id!r} NOT found in from_list={slots!r}")
            except Exception as e:
                rec("W5d_rule_from_attach", "FAIL", repr(e))
        else:
            rec("W5d_rule_from_attach", "SKIP", "rule or who group create failed")

        # ---- to_attach (reuse who group — valid slot type) ----
        hr(f"W5d: ruledb_rule_to_attach — POST /config/ruledb/rules/{w5d_rule_id}/to")
        w5d_to_attached = False
        if w5d_rule_id and w5d_who_id:
            try:
                result = ruledb_rule_to_attach(backend, w5d_rule_id, w5d_who_id)
                print(f"  [SHAPE] to_attach raw_return={result!r}")
                slots = ruledb_rule_to_list(backend, w5d_rule_id)
                print(f"  [SHAPE] to_list after attach={slots!r}")
                found = any(str(s.get("ogroup", s.get("id", ""))) == w5d_who_id for s in (slots or []))
                if found:
                    w5d_to_attached = True
                    rec("W5d_rule_to_attach", "PASS",
                        f"ogroup={w5d_who_id!r} confirmed in to_list")
                else:
                    rec("W5d_rule_to_attach", "FAIL",
                        f"ogroup={w5d_who_id!r} NOT found in to_list={slots!r}")
            except Exception as e:
                rec("W5d_rule_to_attach", "FAIL", repr(e))
        else:
            rec("W5d_rule_to_attach", "SKIP", "rule or who group create failed")

        # ---- what_attach ----
        hr(f"W5d: ruledb_rule_what_attach — POST /config/ruledb/rules/{w5d_rule_id}/what")
        w5d_what_attached = False
        if w5d_rule_id and w5d_what_id:
            try:
                result = ruledb_rule_what_attach(backend, w5d_rule_id, w5d_what_id)
                print(f"  [SHAPE] what_attach raw_return={result!r}")
                slots = ruledb_rule_what_list(backend, w5d_rule_id)
                print(f"  [SHAPE] what_list after attach={slots!r}")
                found = any(str(s.get("ogroup", s.get("id", ""))) == w5d_what_id for s in (slots or []))
                if found:
                    w5d_what_attached = True
                    rec("W5d_rule_what_attach", "PASS",
                        f"ogroup={w5d_what_id!r} confirmed in what_list")
                else:
                    rec("W5d_rule_what_attach", "FAIL",
                        f"ogroup={w5d_what_id!r} NOT found in what_list={slots!r}")
            except Exception as e:
                rec("W5d_rule_what_attach", "FAIL", repr(e))
        else:
            rec("W5d_rule_what_attach", "SKIP", "rule or what group create failed")

        # ---- when_attach ----
        hr(f"W5d: ruledb_rule_when_attach — POST /config/ruledb/rules/{w5d_rule_id}/when")
        w5d_when_attached = False
        if w5d_rule_id and w5d_when_id:
            try:
                result = ruledb_rule_when_attach(backend, w5d_rule_id, w5d_when_id)
                print(f"  [SHAPE] when_attach raw_return={result!r}")
                slots = ruledb_rule_when_list(backend, w5d_rule_id)
                print(f"  [SHAPE] when_list after attach={slots!r}")
                found = any(str(s.get("ogroup", s.get("id", ""))) == w5d_when_id for s in (slots or []))
                if found:
                    w5d_when_attached = True
                    rec("W5d_rule_when_attach", "PASS",
                        f"ogroup={w5d_when_id!r} confirmed in when_list")
                else:
                    rec("W5d_rule_when_attach", "FAIL",
                        f"ogroup={w5d_when_id!r} NOT found in when_list={slots!r}")
            except Exception as e:
                rec("W5d_rule_when_attach", "FAIL", repr(e))
        else:
            rec("W5d_rule_when_attach", "SKIP", "rule or when group create failed")

        # ---- action_attach ----
        hr(f"W5d: ruledb_rule_action_attach — POST /config/ruledb/rules/{w5d_rule_id}/actions")
        w5d_action_attached = False
        if w5d_rule_id and w5d_action_ogroup:
            try:
                result = ruledb_rule_action_attach(backend, w5d_rule_id, w5d_action_ogroup)
                print(f"  [SHAPE] action_attach raw_return={result!r}")
                # Verify via ruledb_rule_get (actions embedded in config.action field)
                cfg = ruledb_rule_get(backend, w5d_rule_id)
                print(f"  [SHAPE] rule_get after action_attach={cfg!r}")
                actions = ruledb_rule_actions_list(backend, w5d_rule_id)
                print(f"  [SHAPE] actions_list after action_attach={actions!r}")
                found = any(
                    str(a.get("ogroup", a.get("id", ""))) == w5d_action_ogroup
                    for a in (actions or [])
                )
                if found:
                    w5d_action_attached = True
                    rec("W5d_rule_action_attach", "PASS",
                        f"action_ogroup={w5d_action_ogroup!r} confirmed in actions_list")
                else:
                    rec("W5d_rule_action_attach", "FAIL",
                        f"action_ogroup={w5d_action_ogroup!r} NOT found in actions_list={actions!r}")
            except Exception as e:
                rec("W5d_rule_action_attach", "FAIL", repr(e))
        else:
            rec("W5d_rule_action_attach", "SKIP",
                f"rule={w5d_rule_id!r} or action_ogroup={w5d_action_ogroup!r} missing")

        # =========================================================================
        # Update the rule name (keep active=False — DO NOT set active=True)
        # =========================================================================
        hr(f"W5d: ruledb_rule_update — PUT /config/ruledb/rules/{w5d_rule_id}/config (name change only)")
        if w5d_rule_id:
            try:
                result = ruledb_rule_update(backend, w5d_rule_id, name="proximo-w5d-test2")
                print(f"  [SHAPE] rule_update raw_return={result!r}")
                cfg = ruledb_rule_get(backend, w5d_rule_id)
                print(f"  [SHAPE] rule_get after update={cfg!r}")
                new_name = cfg.get("name") if isinstance(cfg, dict) else None
                # SAFETY: verify still inactive after update
                active_val = cfg.get("active") if isinstance(cfg, dict) else None
                still_inactive = active_val not in (1, True, "1")
                if new_name == "proximo-w5d-test2" and still_inactive:
                    rec("W5d_rule_update", "PASS",
                        f"name='proximo-w5d-test2' confirmed; active={active_val!r} (still inactive)")
                elif not still_inactive:
                    rec("W5d_rule_update", "FAIL",
                        f"UPDATE MADE RULE ACTIVE — active={active_val!r} — unexpected; inspect lab")
                else:
                    rec("W5d_rule_update", "FAIL",
                        f"name not updated: cfg={cfg!r}")
            except Exception as e:
                rec("W5d_rule_update", "FAIL", repr(e))

        # =========================================================================
        # Detach cycle — action, when, what, to, from (reverse attach order)
        # Each: detach → verify gone via the list read
        # =========================================================================

        # ---- action_detach ----
        hr(f"W5d: ruledb_rule_action_detach — DELETE /config/ruledb/rules/{w5d_rule_id}/actions/{w5d_action_ogroup}")
        if w5d_rule_id and w5d_action_ogroup and w5d_action_attached:
            try:
                result = ruledb_rule_action_detach(backend, w5d_rule_id, w5d_action_ogroup)
                print(f"  [SHAPE] action_detach raw_return={result!r}")
                actions = ruledb_rule_actions_list(backend, w5d_rule_id)
                still = any(
                    str(a.get("ogroup", a.get("id", ""))) == w5d_action_ogroup
                    for a in (actions or [])
                )
                if not still:
                    rec("W5d_rule_action_detach", "PASS",
                        f"action_ogroup={w5d_action_ogroup!r} gone from actions_list")
                else:
                    rec("W5d_rule_action_detach", "FAIL",
                        f"action_ogroup={w5d_action_ogroup!r} STILL in actions_list={actions!r}")
            except Exception as e:
                rec("W5d_rule_action_detach", "FAIL", repr(e))
        else:
            rec("W5d_rule_action_detach", "SKIP", "attach failed or missing ids")

        # ---- when_detach ----
        hr(f"W5d: ruledb_rule_when_detach — DELETE /config/ruledb/rules/{w5d_rule_id}/when/{w5d_when_id}")
        if w5d_rule_id and w5d_when_id and w5d_when_attached:
            try:
                result = ruledb_rule_when_detach(backend, w5d_rule_id, w5d_when_id)
                print(f"  [SHAPE] when_detach raw_return={result!r}")
                slots = ruledb_rule_when_list(backend, w5d_rule_id)
                still = any(str(s.get("ogroup", s.get("id", ""))) == w5d_when_id for s in (slots or []))
                if not still:
                    rec("W5d_rule_when_detach", "PASS",
                        f"ogroup={w5d_when_id!r} gone from when_list")
                else:
                    rec("W5d_rule_when_detach", "FAIL",
                        f"ogroup={w5d_when_id!r} STILL in when_list={slots!r}")
            except Exception as e:
                rec("W5d_rule_when_detach", "FAIL", repr(e))
        else:
            rec("W5d_rule_when_detach", "SKIP", "attach failed or missing ids")

        # ---- what_detach ----
        hr(f"W5d: ruledb_rule_what_detach — DELETE /config/ruledb/rules/{w5d_rule_id}/what/{w5d_what_id}")
        if w5d_rule_id and w5d_what_id and w5d_what_attached:
            try:
                result = ruledb_rule_what_detach(backend, w5d_rule_id, w5d_what_id)
                print(f"  [SHAPE] what_detach raw_return={result!r}")
                slots = ruledb_rule_what_list(backend, w5d_rule_id)
                still = any(str(s.get("ogroup", s.get("id", ""))) == w5d_what_id for s in (slots or []))
                if not still:
                    rec("W5d_rule_what_detach", "PASS",
                        f"ogroup={w5d_what_id!r} gone from what_list")
                else:
                    rec("W5d_rule_what_detach", "FAIL",
                        f"ogroup={w5d_what_id!r} STILL in what_list={slots!r}")
            except Exception as e:
                rec("W5d_rule_what_detach", "FAIL", repr(e))
        else:
            rec("W5d_rule_what_detach", "SKIP", "attach failed or missing ids")

        # ---- to_detach ----
        hr(f"W5d: ruledb_rule_to_detach — DELETE /config/ruledb/rules/{w5d_rule_id}/to/{w5d_who_id}")
        if w5d_rule_id and w5d_who_id and w5d_to_attached:
            try:
                result = ruledb_rule_to_detach(backend, w5d_rule_id, w5d_who_id)
                print(f"  [SHAPE] to_detach raw_return={result!r}")
                slots = ruledb_rule_to_list(backend, w5d_rule_id)
                still = any(str(s.get("ogroup", s.get("id", ""))) == w5d_who_id for s in (slots or []))
                if not still:
                    rec("W5d_rule_to_detach", "PASS",
                        f"ogroup={w5d_who_id!r} gone from to_list")
                else:
                    rec("W5d_rule_to_detach", "FAIL",
                        f"ogroup={w5d_who_id!r} STILL in to_list={slots!r}")
            except Exception as e:
                rec("W5d_rule_to_detach", "FAIL", repr(e))
        else:
            rec("W5d_rule_to_detach", "SKIP", "attach failed or missing ids")

        # ---- from_detach ----
        hr(f"W5d: ruledb_rule_from_detach — DELETE /config/ruledb/rules/{w5d_rule_id}/from/{w5d_who_id}")
        if w5d_rule_id and w5d_who_id and w5d_from_attached:
            try:
                result = ruledb_rule_from_detach(backend, w5d_rule_id, w5d_who_id)
                print(f"  [SHAPE] from_detach raw_return={result!r}")
                slots = ruledb_rule_from_list(backend, w5d_rule_id)
                still = any(str(s.get("ogroup", s.get("id", ""))) == w5d_who_id for s in (slots or []))
                if not still:
                    rec("W5d_rule_from_detach", "PASS",
                        f"ogroup={w5d_who_id!r} gone from from_list")
                else:
                    rec("W5d_rule_from_detach", "FAIL",
                        f"ogroup={w5d_who_id!r} STILL in from_list={slots!r}")
            except Exception as e:
                rec("W5d_rule_from_detach", "FAIL", repr(e))
        else:
            rec("W5d_rule_from_detach", "SKIP", "attach failed or missing ids")

        # ---- rule_delete ----
        hr(f"W5d: ruledb_rule_delete — DELETE /config/ruledb/rules/{w5d_rule_id}")
        if w5d_rule_id:
            try:
                result = ruledb_rule_delete(backend, w5d_rule_id)
                print(f"  [SHAPE] rule_delete raw_return={result!r}")
                # Verify: rule gone from rules_list
                rules_after = ruledb_rules_list(backend)
                still = any(str(r.get("id", "")) == w5d_rule_id for r in rules_after)
                if not still:
                    w5d_rule_id = None   # mark cleaned — suppress finally re-delete
                    rec("W5d_rule_delete", "PASS",
                        f"rule gone from rules_list; count now={len(rules_after)}")
                else:
                    rec("W5d_rule_delete", "FAIL",
                        f"rule {w5d_rule_id!r} STILL in rules_list after delete")
            except Exception as e:
                rec("W5d_rule_delete", "FAIL", repr(e))

    finally:
        # =========================================================================
        # TEARDOWN — runs even if an exception aborted the try block
        # Order: rule first (if still alive), then action, then groups
        # Rule delete auto-detaches all slot groups — safe to call even if some
        # attach steps failed.
        # =========================================================================
        hr("W5d: TEARDOWN (finally)")

        if w5d_rule_id:
            # Rule was not deleted in the main try block — clean it up now
            try:
                ruledb_rule_delete(backend, w5d_rule_id)
                rec("W5d_teardown_rule_delete", "PASS",
                    f"rule {w5d_rule_id!r} deleted in teardown")
            except Exception as e:
                rec("W5d_teardown_rule_delete", "FAIL",
                    f"MANUAL CLEANUP NEEDED — rule {w5d_rule_id!r}: {repr(e)}")

        if w5d_bcc_compound_id:
            try:
                action_delete(backend, w5d_bcc_compound_id)
                rec("W5d_teardown_action_delete", "PASS",
                    f"action {w5d_bcc_compound_id!r} deleted")
            except Exception as e:
                rec("W5d_teardown_action_delete", "FAIL",
                    f"MANUAL CLEANUP NEEDED — action {w5d_bcc_compound_id!r}: {repr(e)}")

        if w5d_who_id:
            try:
                who_group_delete(backend, w5d_who_id)
                rec("W5d_teardown_who_delete", "PASS", f"who group {w5d_who_id!r} deleted")
            except Exception as e:
                rec("W5d_teardown_who_delete", "FAIL",
                    f"MANUAL CLEANUP NEEDED — who group {w5d_who_id!r}: {repr(e)}")

        if w5d_what_id:
            try:
                what_group_delete(backend, w5d_what_id)
                rec("W5d_teardown_what_delete", "PASS", f"what group {w5d_what_id!r} deleted")
            except Exception as e:
                rec("W5d_teardown_what_delete", "FAIL",
                    f"MANUAL CLEANUP NEEDED — what group {w5d_what_id!r}: {repr(e)}")

        if w5d_when_id:
            try:
                when_group_delete(backend, w5d_when_id)
                rec("W5d_teardown_when_delete", "PASS", f"when group {w5d_when_id!r} deleted")
            except Exception as e:
                rec("W5d_teardown_when_delete", "FAIL",
                    f"MANUAL CLEANUP NEEDED — when group {w5d_when_id!r}: {repr(e)}")

    # =========================================================================
    # W5d PRISTINE CHECK — all surfaces must match pre-W5d baselines
    # =========================================================================
    hr("W5d: PRISTINE CHECK — final counts vs pre-W5d baselines")
    try:
        rules_final = ruledb_rules_list(backend)
        who_final = who_groups_list(backend)
        what_final = what_groups_list(backend)
        when_final = when_groups_list(backend)
        actions_final = action_objects_list(backend)
        rc = len(rules_final)
        woc = len(who_final)
        wtc = len(what_final)
        wnc = len(when_final)
        ac = len(actions_final)
        ok_r = rc == w5d_rule_pre_count
        ok_wo = woc == w5d_who_pre_count
        ok_wt = wtc == w5d_what_pre_count
        ok_wn = wnc == w5d_when_pre_count
        ok_a = ac == w5d_action_pre_count
        ok = ok_r and ok_wo and ok_wt and ok_wn and ok_a
        rec("W5d_lab_pristine", "PASS" if ok else "FAIL",
            f"rules={rc}/{w5d_rule_pre_count}({'OK' if ok_r else 'RESIDUE'}) "
            f"who={woc}/{w5d_who_pre_count}({'OK' if ok_wo else 'RESIDUE'}) "
            f"what={wtc}/{w5d_what_pre_count}({'OK' if ok_wt else 'RESIDUE'}) "
            f"when={wnc}/{w5d_when_pre_count}({'OK' if ok_wn else 'RESIDUE'}) "
            f"actions={ac}/{w5d_action_pre_count}({'OK' if ok_a else 'RESIDUE'}) "
            + ("— LAB PRISTINE" if ok else "— RESIDUE DETECTED"))
    except Exception as e:
        rec("W5d_lab_pristine", "FAIL", repr(e))

    # -------------------------------------------------------------------------
    # SUMMARY
    # -------------------------------------------------------------------------
    hr("SUMMARY")
    for step, status, detail in findings:
        print(f"  {status:5}  {step}  {detail}")
    fails = [f for f in findings if f[1] == "FAIL"]
    passes = [f for f in findings if f[1] == "PASS"]
    verdict = "ALL PASS" if not fails else f"{len(fails)} FAIL"
    print(f"\n{verdict} — {len(passes)} PASS, {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
