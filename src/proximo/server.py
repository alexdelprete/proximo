"""Proximo MCP server.

Exposes Proxmox management (REST API) and in-container exec (ssh+pct) as MCP tools.

Verified 2026-06-07 against the official `mcp` Python SDK (FastMCP): import path,
`@mcp.tool()` decorator, type-hinted params, and dict returns are current (v1.x).

Ethical spine:
- In-container exec (ct_*) is OFF by default — API-only is the safe default; enable with PROXIMO_ENABLE_EXEC.
- Every tool call is audited *with its real outcome* (errors recorded, not assumed "ok").
- Every mutating tool (pve_guest_power, ct_exec, ct_psql) is confirm-gated.
- The CTID allowlist is enforced fail-closed in the exec backend.
- Secrets are never read or logged here.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import __version__
from .access import (
    access_acl_list,
    access_overbroad_grants,
    access_roles_list,
    access_tokens_list,
    access_users_list,
    acl_modify,
    plan_acl_modify,
    plan_token_create,
    plan_token_revoke,
    token_create,
    token_revoke,
)
from .access_governance import (
    plan_realm_create,
    plan_realm_delete,
    plan_realm_update,
    plan_role_create,
    plan_role_delete,
    plan_role_update,
    plan_tfa_delete,
    realm_create,
    realm_delete,
    realm_get,
    realm_update,
    realms_list,
    role_create,
    role_delete,
    role_update,
    tfa_delete,
    tfa_get,
    tfa_list,
)
from .access_users import (
    group_create,
    group_delete,
    group_get,
    group_update,
    groups_list,
    plan_group_create,
    plan_group_delete,
    plan_group_update,
    plan_user_create,
    plan_user_delete,
    plan_user_update,
    user_create,
    user_delete,
    user_get,
    user_update,
)
from .acme_certs import (
    acme_account_create,
    acme_account_delete,
    acme_account_update,
    acme_plugin_create,
    acme_plugin_delete,
    acme_plugin_update,
    plan_acme_account_create,
    plan_acme_account_delete,
    plan_acme_account_update,
    plan_acme_plugin_create,
    plan_acme_plugin_delete,
    plan_acme_plugin_update,
)
from .audit import AuditLedger, find_rotation_archive, looks_like_head, open_ledger
from .backends import ApiBackend, ExecBackend, ProximoError
from .backup import (
    backup_delete,
    backup_list,
    plan_backup,
    plan_backup_delete,
    plan_restore,
    restore_guest,
    vzdump_backup,
)
from .backup_schedules import (
    backup_job_create,
    backup_job_delete,
    backup_job_list,
    backup_job_update,
    pbs_scheduled_job_create,
    pbs_scheduled_job_delete,
    pbs_scheduled_job_run,
    pbs_scheduled_job_update,
    pbs_scheduled_jobs_list,
    plan_backup_job_create,
    plan_backup_job_delete,
    plan_backup_job_update,
    plan_pbs_job_create,
    plan_pbs_job_delete,
    plan_pbs_job_run,
    plan_pbs_job_update,
    plan_pbs_realm_sync,
    plan_replication_create,
    plan_replication_delete,
    plan_replication_update,
    replication_create,
    replication_delete,
    replication_update,
)
from .backup_schedules import (
    pbs_realm_sync as pbs_realm_sync_op,
)
from .cloudinit import (
    capture_cloudinit_undo,
    cloudinit_get,
    cloudinit_set,
    plan_cloudinit_set,
    plan_template_convert,
    template_convert,
)
from .cluster_ops import (
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
from .config import ProximoConfig
from .config_edit import (
    guest_config_get,
    guest_config_revert,
    guest_config_set,
    plan_config_revert,
    plan_config_set,
)
from .diagnose import diagnose_container, diagnose_node
from .disk_ops import (
    disk_move,
    disk_resize,
    plan_disk_move,
    plan_disk_resize,
)
from .doctor import doctor_check
from .firewall import (
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
from .hw_mappings import (
    hardware_list,
    mapping_pci_create,
    mapping_pci_delete,
    mapping_pci_list,
    mapping_pci_update,
    mapping_usb_create,
    mapping_usb_delete,
    mapping_usb_list,
    mapping_usb_update,
    plan_mapping_pci_create,
    plan_mapping_pci_delete,
    plan_mapping_pci_update,
    plan_mapping_usb_create,
    plan_mapping_usb_delete,
    plan_mapping_usb_update,
)
from .network import (
    network_apply,
    network_iface_create,
    network_iface_update,
    network_list,
    plan_iface_create,
    plan_iface_update,
    plan_network_apply,
    plan_sdn_apply,
    plan_sdn_subnet_create,
    plan_sdn_subnet_delete,
    plan_sdn_subnet_update,
    plan_sdn_vnet_create,
    plan_sdn_vnet_delete,
    plan_sdn_vnet_update,
    plan_sdn_zone_create,
    plan_sdn_zone_delete,
    plan_sdn_zone_update,
    sdn_apply,
    sdn_subnet_create,
    sdn_subnet_delete,
    sdn_subnet_list,
    sdn_subnet_update,
    sdn_vnet_create,
    sdn_vnet_delete,
    sdn_vnet_update,
    sdn_vnets_list,
    sdn_zone_create,
    sdn_zone_delete,
    sdn_zone_update,
    sdn_zones_list,
)
from .node_lifecycle import (
    _key_fingerprint,
    plan_node_cert_delete,
    plan_node_cert_upload,
    plan_node_disk_initgpt,
    plan_node_disk_wipe,
    plan_node_dns_set,
    plan_node_hosts_set,
    plan_node_migrateall,
    plan_node_startall,
    plan_node_stopall,
    plan_node_storage_backend_create,
    plan_node_storage_backend_delete,
    plan_node_time_set,
)
from .notifications import (
    metrics_server_delete,
    metrics_server_list,
    metrics_server_set,
    notification_endpoint_create,
    notification_endpoint_delete,
    notification_endpoint_list,
    notification_endpoint_update,
    notification_matcher_delete,
    notification_matcher_set,
    plan_metrics_server_delete,
    plan_metrics_server_set,
    plan_notification_endpoint_create,
    plan_notification_endpoint_delete,
    plan_notification_endpoint_update,
    plan_notification_matcher_delete,
    plan_notification_matcher_set,
    plan_notification_test,
)
from .notifications import (
    notification_test as notification_test_op,
)
from .observability import (
    node_certificates_info,
    node_dns_get,
    node_journal,
    node_rrddata,
    node_service_control,
    node_service_status,
    node_services_list,
    node_subscription,
    node_syslog,
    plan_node_service_control,
)
from .pbs import (
    PbsBackend,
    PbsConfig,
)
from .pbs import (
    datastore_list as pbs_datastore_list_op,
)
from .pbs import (
    datastore_status as pbs_datastore_status_op,
)
from .pbs import (
    gc_start as pbs_gc_start_op,
)
from .pbs import (
    gc_status as pbs_gc_status_op,
)
from .pbs import (
    namespace_create as pbs_namespace_create_op,
)
from .pbs import (
    namespace_delete as pbs_namespace_delete_op,
)
from .pbs import (
    namespace_list as pbs_namespace_list_op,
)
from .pbs import (
    plan_gc_start as pbs_plan_gc_start,
)
from .pbs import (
    plan_namespace_create as pbs_plan_namespace_create,
)
from .pbs import (
    plan_namespace_delete as pbs_plan_namespace_delete,
)
from .pbs import (
    plan_prune as pbs_plan_prune,
)
from .pbs import (
    plan_snapshot_delete as pbs_plan_snapshot_delete,
)
from .pbs import (
    plan_verify_start as pbs_plan_verify_start,
)
from .pbs import (
    prune as pbs_prune_op,
)
from .pbs import (
    snapshot_delete as pbs_snapshot_delete_op,
)
from .pbs import (
    snapshots_list as pbs_snapshots_list_op,
)
from .pbs import (
    tasks_list as pbs_tasks_list_op,
)
from .pbs import (
    verify_start as pbs_verify_start_op,
)
from .pbs_config import (
    _remote_password_fingerprint,
)
from .pbs_config import (
    datastore_create as pbs_cfg_datastore_create,
)
from .pbs_config import (
    datastore_delete as pbs_cfg_datastore_delete,
)
from .pbs_config import (
    datastore_get as pbs_cfg_datastore_get,
)
from .pbs_config import (
    datastore_update as pbs_cfg_datastore_update,
)
from .pbs_config import (
    group_change_owner as pbs_cfg_group_change_owner,
)
from .pbs_config import (
    plan_datastore_create as pbs_plan_datastore_create,
)
from .pbs_config import (
    plan_datastore_delete as pbs_plan_datastore_delete,
)
from .pbs_config import (
    plan_datastore_update as pbs_plan_datastore_update,
)
from .pbs_config import (
    plan_group_change_owner as pbs_plan_group_change_owner,
)
from .pbs_config import (
    plan_remote_create as pbs_plan_remote_create,
)
from .pbs_config import (
    plan_remote_delete as pbs_plan_remote_delete,
)
from .pbs_config import (
    plan_remote_update as pbs_plan_remote_update,
)
from .pbs_config import (
    plan_snapshot_notes_set as pbs_plan_snapshot_notes_set,
)
from .pbs_config import (
    plan_snapshot_protected_set as pbs_plan_snapshot_protected_set,
)
from .pbs_config import (
    plan_traffic_control_delete as pbs_plan_traffic_control_delete,
)
from .pbs_config import (
    plan_traffic_control_upsert as pbs_plan_traffic_control_upsert,
)
from .pbs_config import (
    remote_create as pbs_cfg_remote_create,
)
from .pbs_config import (
    remote_delete as pbs_cfg_remote_delete,
)
from .pbs_config import (
    remote_get as pbs_cfg_remote_get,
)
from .pbs_config import (
    remote_update as pbs_cfg_remote_update,
)
from .pbs_config import (
    remotes_list as pbs_cfg_remotes_list,
)
from .pbs_config import (
    snapshot_notes_set as pbs_cfg_snapshot_notes_set,
)
from .pbs_config import (
    snapshot_protected_set as pbs_cfg_snapshot_protected_set,
)
from .pbs_config import (
    traffic_control_delete as pbs_cfg_traffic_control_delete,
)
from .pbs_config import (
    traffic_control_upsert as pbs_cfg_traffic_control_upsert,
)
from .pbs_config import (
    traffic_controls_list as pbs_cfg_traffic_controls_list,
)
from .pdm import (
    PdmBackend,
    PdmConfig,
)
from .planning import (
    Plan,
    command_fingerprint,
    plan_exec,
    plan_power,
    plan_psql,
    plan_rollback,
    plan_snapshot_create,
    plan_snapshot_delete,
    sql_fingerprint,
    undo_snapname,
)
from .pmg import (
    PmgBackend,
    PmgConfig,
)
from .pmg import (
    access_permissions as pmg_access_permissions_op,
)
from .pmg import (
    action_bcc_create as pmg_action_bcc_create_op,
)
from .pmg import (
    action_bcc_update as pmg_action_bcc_update_op,
)
from .pmg import (
    action_delete as pmg_action_delete_op,
)
from .pmg import (
    action_disclaimer_create as pmg_action_disclaimer_create_op,
)
from .pmg import (
    action_disclaimer_update as pmg_action_disclaimer_update_op,
)
from .pmg import (
    action_field_create as pmg_action_field_create_op,
)
from .pmg import (
    action_field_update as pmg_action_field_update_op,
)
from .pmg import (
    action_notification_create as pmg_action_notification_create_op,
)
from .pmg import (
    action_notification_update as pmg_action_notification_update_op,
)
from .pmg import (
    action_objects_list as pmg_action_objects_list_op,
)
from .pmg import (
    action_removeattachments_create as pmg_action_removeattachments_create_op,
)
from .pmg import (
    action_removeattachments_update as pmg_action_removeattachments_update_op,
)
from .pmg import (
    backup_create as pmg_backup_create_op,
)
from .pmg import (
    domain_create as pmg_domain_create_op,
)
from .pmg import (
    domain_delete as pmg_domain_delete_op,
)
from .pmg import (
    domains_list as pmg_domains_list_op,
)
from .pmg import (
    mynetworks_add as pmg_mynetworks_add_op,
)
from .pmg import (
    mynetworks_remove as pmg_mynetworks_remove_op,
)
from .pmg import (
    node_rrddata as pmg_node_rrddata_op,
)
from .pmg import (
    node_status as pmg_node_status_op,
)
from .pmg import (
    node_syslog as pmg_node_syslog_op,
)
from .pmg import (
    node_version as pmg_node_version_op,
)
from .pmg import (
    plan_action_bcc_create as pmg_plan_action_bcc_create,
)
from .pmg import (
    plan_action_bcc_update as pmg_plan_action_bcc_update,
)
from .pmg import (
    plan_action_delete as pmg_plan_action_delete,
)
from .pmg import (
    plan_action_disclaimer_create as pmg_plan_action_disclaimer_create,
)
from .pmg import (
    plan_action_disclaimer_update as pmg_plan_action_disclaimer_update,
)
from .pmg import (
    plan_action_field_create as pmg_plan_action_field_create,
)
from .pmg import (
    plan_action_field_update as pmg_plan_action_field_update,
)
from .pmg import (
    plan_action_notification_create as pmg_plan_action_notification_create,
)
from .pmg import (
    plan_action_notification_update as pmg_plan_action_notification_update,
)
from .pmg import (
    plan_action_removeattachments_create as pmg_plan_action_removeattachments_create,
)
from .pmg import (
    plan_action_removeattachments_update as pmg_plan_action_removeattachments_update,
)
from .pmg import (
    plan_backup_create as pmg_plan_backup_create,
)
from .pmg import (
    plan_domain_create as pmg_plan_domain_create,
)
from .pmg import (
    plan_domain_delete as pmg_plan_domain_delete,
)
from .pmg import (
    plan_mynetworks_add as pmg_plan_mynetworks_add,
)
from .pmg import (
    plan_mynetworks_remove as pmg_plan_mynetworks_remove,
)
from .pmg import (
    plan_postfix_flush as pmg_plan_postfix_flush,
)
from .pmg import (
    plan_quarantine_action as pmg_plan_quarantine_action,
)
from .pmg import (
    plan_quarantine_blocklist_add as pmg_plan_quarantine_blocklist_add,
)
from .pmg import (
    plan_quarantine_blocklist_remove as pmg_plan_quarantine_blocklist_remove,
)
from .pmg import (
    plan_quarantine_welcomelist_add as pmg_plan_quarantine_welcomelist_add,
)
from .pmg import (
    plan_quarantine_welcomelist_remove as pmg_plan_quarantine_welcomelist_remove,
)
from .pmg import (
    plan_ruledb_rule_action_attach as pmg_plan_ruledb_rule_action_attach,
)
from .pmg import (
    plan_ruledb_rule_action_detach as pmg_plan_ruledb_rule_action_detach,
)
from .pmg import (
    plan_ruledb_rule_create as pmg_plan_ruledb_rule_create,
)
from .pmg import (
    plan_ruledb_rule_delete as pmg_plan_ruledb_rule_delete,
)
from .pmg import (
    plan_ruledb_rule_from_attach as pmg_plan_ruledb_rule_from_attach,
)
from .pmg import (
    plan_ruledb_rule_from_detach as pmg_plan_ruledb_rule_from_detach,
)
from .pmg import (
    plan_ruledb_rule_to_attach as pmg_plan_ruledb_rule_to_attach,
)
from .pmg import (
    plan_ruledb_rule_to_detach as pmg_plan_ruledb_rule_to_detach,
)
from .pmg import (
    plan_ruledb_rule_update as pmg_plan_ruledb_rule_update,
)
from .pmg import (
    plan_ruledb_rule_what_attach as pmg_plan_ruledb_rule_what_attach,
)
from .pmg import (
    plan_ruledb_rule_what_detach as pmg_plan_ruledb_rule_what_detach,
)
from .pmg import (
    plan_ruledb_rule_when_attach as pmg_plan_ruledb_rule_when_attach,
)
from .pmg import (
    plan_ruledb_rule_when_detach as pmg_plan_ruledb_rule_when_detach,
)
from .pmg import (
    plan_service_control as pmg_plan_service_control,
)
from .pmg import (
    plan_spam_config_update as pmg_plan_spam_config_update,
)
from .pmg import (
    plan_transport_create as pmg_plan_transport_create,
)
from .pmg import (
    plan_transport_delete as pmg_plan_transport_delete,
)
from .pmg import (
    plan_what_group_create as pmg_plan_what_group_create,
)
from .pmg import (
    plan_what_group_delete as pmg_plan_what_group_delete,
)
from .pmg import (
    plan_what_group_update as pmg_plan_what_group_update,
)
from .pmg import (
    plan_what_object_add as pmg_plan_what_object_add,
)
from .pmg import (
    plan_what_object_delete as pmg_plan_what_object_delete,
)
from .pmg import (
    plan_what_object_update as pmg_plan_what_object_update,
)
from .pmg import (
    plan_when_group_create as pmg_plan_when_group_create,
)
from .pmg import (
    plan_when_group_delete as pmg_plan_when_group_delete,
)
from .pmg import (
    plan_when_group_update as pmg_plan_when_group_update,
)
from .pmg import (
    plan_when_object_add as pmg_plan_when_object_add,
)
from .pmg import (
    plan_when_object_delete as pmg_plan_when_object_delete,
)
from .pmg import (
    plan_when_object_update as pmg_plan_when_object_update,
)
from .pmg import (
    plan_who_group_create as pmg_plan_who_group_create,
)
from .pmg import (
    plan_who_group_delete as pmg_plan_who_group_delete,
)
from .pmg import (
    plan_who_group_update as pmg_plan_who_group_update,
)
from .pmg import (
    plan_who_object_add as pmg_plan_who_object_add,
)
from .pmg import (
    plan_who_object_delete as pmg_plan_who_object_delete,
)
from .pmg import (
    plan_who_object_update as pmg_plan_who_object_update,
)
from .pmg import (
    postfix_flush as pmg_postfix_flush_op,
)
from .pmg import (
    postfix_qshape as pmg_postfix_qshape_op,
)
from .pmg import (
    quarantine_action as pmg_quarantine_action_op,
)
from .pmg import (
    quarantine_attachment as pmg_quarantine_attachment_op,
)
from .pmg import (
    quarantine_blocklist_add as pmg_quarantine_blocklist_add_op,
)
from .pmg import (
    quarantine_blocklist_list as pmg_quarantine_blocklist_list_op,
)
from .pmg import (
    quarantine_blocklist_remove as pmg_quarantine_blocklist_remove_op,
)
from .pmg import (
    quarantine_spam as pmg_quarantine_spam_op,
)
from .pmg import (
    quarantine_spamstatus as pmg_quarantine_spamstatus_op,
)
from .pmg import (
    quarantine_spamusers as pmg_quarantine_spamusers_op,
)
from .pmg import (
    quarantine_virus as pmg_quarantine_virus_op,
)
from .pmg import (
    quarantine_virusstatus as pmg_quarantine_virusstatus_op,
)
from .pmg import (
    quarantine_welcomelist_add as pmg_quarantine_welcomelist_add_op,
)
from .pmg import (
    quarantine_welcomelist_list as pmg_quarantine_welcomelist_list_op,
)
from .pmg import (
    quarantine_welcomelist_remove as pmg_quarantine_welcomelist_remove_op,
)
from .pmg import (
    relay_config as pmg_relay_config_op,
)
from .pmg import (
    ruledb_digest as pmg_ruledb_digest_op,
)
from .pmg import (
    ruledb_rule_action_attach as pmg_ruledb_rule_action_attach_op,
)
from .pmg import (
    ruledb_rule_action_detach as pmg_ruledb_rule_action_detach_op,
)
from .pmg import (
    ruledb_rule_actions_list as pmg_ruledb_rule_actions_list_op,
)
from .pmg import (
    ruledb_rule_create as pmg_ruledb_rule_create_op,
)
from .pmg import (
    ruledb_rule_delete as pmg_ruledb_rule_delete_op,
)
from .pmg import (
    ruledb_rule_from_attach as pmg_ruledb_rule_from_attach_op,
)
from .pmg import (
    ruledb_rule_from_detach as pmg_ruledb_rule_from_detach_op,
)
from .pmg import (
    ruledb_rule_from_list as pmg_ruledb_rule_from_list_op,
)
from .pmg import (
    ruledb_rule_get as pmg_ruledb_rule_get_op,
)
from .pmg import (
    ruledb_rule_to_attach as pmg_ruledb_rule_to_attach_op,
)
from .pmg import (
    ruledb_rule_to_detach as pmg_ruledb_rule_to_detach_op,
)
from .pmg import (
    ruledb_rule_to_list as pmg_ruledb_rule_to_list_op,
)
from .pmg import (
    ruledb_rule_update as pmg_ruledb_rule_update_op,
)
from .pmg import (
    ruledb_rule_what_attach as pmg_ruledb_rule_what_attach_op,
)
from .pmg import (
    ruledb_rule_what_detach as pmg_ruledb_rule_what_detach_op,
)
from .pmg import (
    ruledb_rule_what_list as pmg_ruledb_rule_what_list_op,
)
from .pmg import (
    ruledb_rule_when_attach as pmg_ruledb_rule_when_attach_op,
)
from .pmg import (
    ruledb_rule_when_detach as pmg_ruledb_rule_when_detach_op,
)
from .pmg import (
    ruledb_rule_when_list as pmg_ruledb_rule_when_list_op,
)
from .pmg import (
    ruledb_rules_list as pmg_ruledb_rules_list_op,
)
from .pmg import (
    service_control as pmg_service_control_op,
)
from .pmg import (
    service_status as pmg_service_status_op,
)
from .pmg import (
    spam_config as pmg_spam_config_op,
)
from .pmg import (
    spam_config_update as pmg_spam_config_update_op,
)
from .pmg import (
    statistics_domains as pmg_statistics_domains_op,
)
from .pmg import (
    statistics_mail as pmg_statistics_mail_op,
)
from .pmg import (
    statistics_mailcount as pmg_statistics_mailcount_op,
)
from .pmg import (
    statistics_receiver as pmg_statistics_receiver_op,
)
from .pmg import (
    statistics_recent as pmg_statistics_recent_op,
)
from .pmg import (
    statistics_sender as pmg_statistics_sender_op,
)
from .pmg import (
    statistics_spamscores as pmg_statistics_spamscores_op,
)
from .pmg import (
    statistics_virus as pmg_statistics_virus_op,
)
from .pmg import (
    tasks_list as pmg_tasks_list_op,
)
from .pmg import (
    tracker_detail as pmg_tracker_detail_op,
)
from .pmg import (
    tracker_list as pmg_tracker_list_op,
)
from .pmg import (
    transport_create as pmg_transport_create_op,
)
from .pmg import (
    transport_delete as pmg_transport_delete_op,
)
from .pmg import (
    what_group_create as pmg_what_group_create_op,
)
from .pmg import (
    what_group_delete as pmg_what_group_delete_op,
)
from .pmg import (
    what_group_get as pmg_what_group_get_op,
)
from .pmg import (
    what_group_objects as pmg_what_group_objects_op,
)
from .pmg import (
    what_group_update as pmg_what_group_update_op,
)
from .pmg import (
    what_groups_list as pmg_what_groups_list_op,
)
from .pmg import (
    what_object_add as pmg_what_object_add_op,
)
from .pmg import (
    what_object_delete as pmg_what_object_delete_op,
)
from .pmg import (
    what_object_update as pmg_what_object_update_op,
)
from .pmg import (
    when_group_create as pmg_when_group_create_op,
)
from .pmg import (
    when_group_delete as pmg_when_group_delete_op,
)
from .pmg import (
    when_group_get as pmg_when_group_get_op,
)
from .pmg import (
    when_group_objects as pmg_when_group_objects_op,
)
from .pmg import (
    when_group_update as pmg_when_group_update_op,
)
from .pmg import (
    when_groups_list as pmg_when_groups_list_op,
)
from .pmg import (
    when_object_add as pmg_when_object_add_op,
)
from .pmg import (
    when_object_delete as pmg_when_object_delete_op,
)
from .pmg import (
    when_object_update as pmg_when_object_update_op,
)
from .pmg import (
    who_group_create as pmg_who_group_create_op,
)
from .pmg import (
    who_group_delete as pmg_who_group_delete_op,
)
from .pmg import (
    who_group_get as pmg_who_group_get_op,
)
from .pmg import (
    who_group_objects as pmg_who_group_objects_op,
)
from .pmg import (
    who_group_update as pmg_who_group_update_op,
)
from .pmg import (
    who_groups_list as pmg_who_groups_list_op,
)
from .pmg import (
    who_object_add as pmg_who_object_add_op,
)
from .pmg import (
    who_object_delete as pmg_who_object_delete_op,
)
from .pmg import (
    who_object_update as pmg_who_object_update_op,
)
from .provisioning import (
    clone_guest,
    create_container,
    create_vm,
    delete_guest,
    plan_clone,
    plan_create,
    plan_delete,
)
from .qemu_agent import (
    _check_agent_fs_command,
    _check_agent_info_command,
    _check_file_path,
    _content_fingerprint,
    _password_fingerprint,
    plan_agent_exec,
    plan_agent_file_write,
    plan_agent_fs,
    plan_agent_set_password,
)
from .storage import (
    content_delete,
    plan_content_delete,
    plan_storage_download,
    storage_content,
    storage_download_url,
    storage_status,
)
from .storage_admin import (
    plan_storage_create,
    plan_storage_delete,
    plan_storage_update,
    storage_config_get,
    storage_config_list,
    storage_create,
    storage_delete,
    storage_update,
)
from .tasks_pools import (
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

BANNER = (
    "Proximo — the ethical Proxmox MCP\n"
    '  "Win the crowd and you will win your freedom."  ·  Strength and honor.\n'
)

mcp = FastMCP("proximo")
# FastMCP leaves the low-level Server.version=None, so the `initialize` handshake would advertise the
# MCP SDK's version. Set Proximo's own version instead, so clients see the real server version.
mcp._mcp_server.version = __version__


@lru_cache(maxsize=1)
def _svc() -> tuple[ProximoConfig, ApiBackend, ExecBackend, AuditLedger]:
    """Lazily build config + backends (no import-time env dependency; testable)."""
    cfg = ProximoConfig.from_env()
    return cfg, ApiBackend(cfg), ExecBackend(cfg), open_ledger(cfg)


@lru_cache(maxsize=1)
def _pbs() -> tuple[PbsConfig, PbsBackend]:
    """Lazily build the PBS backend — only when a pbs_* tool is called.

    Separate service from the PVE host: needs PROXIMO_PBS_* env (fails loud if unset).
    PBS ops still record to the SAME tamper-evident ledger via _audited/_plan (_svc's
    AuditLedger) so PROVE remains one coherent chain across PVE and PBS actions.
    """
    cfg = PbsConfig.from_env()
    return cfg, PbsBackend(cfg)


@lru_cache(maxsize=1)
def _pmg() -> tuple[PmgConfig, PmgBackend]:
    """Lazily build the PMG backend — only when a pmg_* tool is called.

    Separate service from the PVE host: needs PROXIMO_PMG_* env (fails loud if unset).
    PMG ops still record to the SAME tamper-evident ledger via _audited/_plan (_svc's
    AuditLedger) so PROVE remains one coherent chain across PVE, PBS, and PMG actions.
    """
    cfg = PmgConfig.from_env()
    return cfg, PmgBackend(cfg)


@lru_cache(maxsize=1)
def _pdm() -> tuple[PdmConfig, PdmBackend]:
    """Lazily build the PDM backend — only when a pdm_* tool is called.

    Separate service from the PVE host: needs PROXIMO_PDM_* env (fails loud if unset).
    PDM ops still record to the SAME tamper-evident ledger via _audited (_svc's
    AuditLedger) so PROVE remains one coherent chain across PVE, PBS, PMG, and PDM actions.
    """
    cfg = PdmConfig.from_env()
    return cfg, PdmBackend(cfg)


def _audited(action: str, target: str, fn: Callable[[], Any], *,
             mutation: bool = False, outcome: str = "ok", detail: dict | None = None) -> Any:
    """Run fn, then audit the REAL outcome. On exception, record the error and re-raise.

    `outcome` defaults to "ok" (synchronous completion). Async ops that only *start* a task pass
    outcome="submitted" so the ledger never claims an in-flight task is done.

    For mutation calls (mutation=True) the return is a SYMMETRIC envelope:
        {"status": <outcome>, "result": <raw fn() return>}
    where ``status`` equals the ``outcome`` recorded to the ledger — so a caller can uniformly
    read ``resp["status"]`` and it is always honest (never "ok" for an async/submitted op).

    Read calls (mutation=False) pass the raw fn() return through unchanged — no envelope.
    """
    _, _, _, audit = _svc()
    try:
        result = fn()
    except Exception as e:
        audit.record(action, target=target, mutation=mutation, outcome="error",
                     detail={**(detail or {}), "error": type(e).__name__})
        raise
    audit.record(action, target=target, mutation=mutation, outcome=outcome, detail=detail)
    if mutation:
        return {"status": outcome, "result": result}
    return result


def _record_plan(plan: Plan) -> None:
    """Write the previewed plan (incl. the live state it was based on) to the tamper-evident ledger,
    with outcome="planned". This is the PLAN->PROVE weld: a verified chain shows the exact preview."""
    _, _, _, audit = _svc()
    audit.record(
        plan.action, target=plan.target, mutation=True, outcome="planned",
        detail={"change": plan.change, "risk": plan.risk, "risk_reasons": plan.risk_reasons,
                "blast_radius": plan.blast_radius, "current": plan.current,
                "affected": plan.affected, "complete": plan.complete},
    )


def _plan(action: str, target: str, build: Callable[[], Plan]) -> Plan:
    """Build a plan and record it — MANDATORY before any mutation (no plan, no mutation).

    Called on BOTH paths: the dry-run (confirm=False) returns it; the execute path (confirm=True)
    runs it first so every mutation is preceded by a recorded "planned" entry — a one-shot confirm
    cannot bypass the preview. If building the plan fails (e.g. plan_power's live read raises),
    audit the failed probe and re-raise; never mutate without a recorded plan.
    """
    _, _, _, audit = _svc()
    try:
        plan = build()
    except Exception as e:
        audit.record(action, target=target, mutation=True, outcome="error",
                     detail={"error": type(e).__name__, "phase": "planning"})
        raise
    # The server tool name is AUTHORITATIVE for the ledger: stamp it onto the plan so the "planned"
    # entry pairs with the later "submitted"/"ok" entry under ONE action (PROVE coherence) — a plan_*
    # helper's internal label can never drift the audit trail (and shared helpers like plan_create,
    # used by both pve_create_container and pve_create_vm, record under the right tool each time).
    plan.action = action
    _record_plan(plan)
    return plan


def _wait_task(api: ApiBackend, upid: str, node: str | None = None,
               timeout: int = 120, interval: int = 2) -> dict:
    """Poll a Proxmox task to completion. Snapshot ops are async; the auto-undo path must wait for
    the snapshot to actually finish before mutating. Raises if the task fails or times out."""
    deadline = time.monotonic() + timeout
    while True:
        st = api.task_status(upid, node)
        if st.get("status") == "stopped":
            # Strict: only an explicit "OK" passes. A stopped task that reports no exitstatus is
            # treated as failure (fail-closed), not silently assumed successful.
            exit_ = st.get("exitstatus")
            if exit_ != "OK":
                raise ProximoError(f"task {upid} did not finish OK: {exit_!r}")
            return st
        if time.monotonic() >= deadline:
            raise ProximoError(f"task {upid} timed out after {timeout}s")
        time.sleep(interval)


def _auto_undo(action: str, target: str, api: ApiBackend, vmid: str,
               detail: dict, kind: str = "lxc", node: str | None = None) -> dict:
    """Take a labeled undo snapshot and WAIT for it. On success returns the undo-point dict; on
    failure returns an {"status": "blocked:undo_unavailable"} dict (and audits it) — the caller MUST NOT
    mutate when unavailable (fail-closed: no net, no risky act)."""
    _, _, _, audit = _svc()
    snapname = undo_snapname()
    try:
        upid = api.snapshot_create(vmid, snapname, kind=kind, node=node,
                                   description="proximo auto-undo before mutation")
        _wait_task(api, upid, node=node)
    except Exception as e:
        audit.record(action, target=target, mutation=True, outcome="blocked:undo_unavailable",
                     detail={**detail, "error": type(e).__name__})
        return {
            "status": "blocked:undo_unavailable",
            "message": ("Requested an undo snapshot but it could not be created/completed (the "
                        "container's storage may not support snapshots). Command NOT run "
                        "(fail-closed). Re-run without snapshot=True to proceed unprotected."),
            "error": type(e).__name__,
        }
    audit.record(action, target=target, mutation=True, outcome="undo_point",
                 detail={"snapshot": snapname, "task": upid})
    return {"snapshot": snapname, "task": upid,
            "revert": f"pve_rollback vmid={vmid} snapname={snapname}",
            "note": ("undo points are NOT auto-pruned — they accumulate and consume storage; "
                     "delete with pve_snapshot_delete when no longer needed.")}


def _blocked_allowlist(action: str, target: str, detail: dict | None = None,
                       *, mutation: bool = True) -> dict:
    """Refuse + audit a container op whose CTID isn't on the allowlist (fail-closed), as a clean dict
    — checked at the server layer BEFORE any snapshot/exec, so a forbidden CTID never gets touched.
    `mutation` must reflect the GATED tool's true class so blocked reads don't ledger as mutations."""
    _, _, _, audit = _svc()
    audit.record(action, target=target, mutation=mutation, outcome="blocked:allowlist", detail=detail)
    return {"status": "blocked:allowlist",
            "message": f"CTID {target} is not permitted by the allowlist (fail-closed)."}


def _exec_disabled(action: str, target: str, detail: dict | None = None,
                   *, mutation: bool = True) -> dict:
    """In-container exec is off by default (safe). Refuse + audit; explain how to opt in.
    `mutation` must reflect the GATED tool's true class so blocked reads don't ledger as mutations."""
    _, _, _, audit = _svc()
    audit.record(action, target=target, mutation=mutation, outcome="blocked:exec_disabled", detail=detail)
    return {
        "status": "blocked:exec_disabled",
        "message": ("In-container exec is disabled (safe default: API-only). It grants near-root on the "
                    "PVE host; enable deliberately with PROXIMO_ENABLE_EXEC=1."),
    }


def _agent_disabled(action: str, target: str, detail: dict | None = None,
                    *, mutation: bool = True) -> dict:
    """qemu-agent ops are off by default. Refuse + audit; explain how to opt in.
    `mutation` must reflect the GATED tool's true class so blocked reads don't ledger as mutations."""
    _, _, _, audit = _svc()
    audit.record(action, target=target, mutation=mutation, outcome="blocked:agent_disabled", detail=detail)
    return {
        "status": "blocked:agent_disabled",
        "message": ("qemu-agent ops are disabled (safe default: API-only). "
                    "Enable with PROXIMO_ENABLE_AGENT=1 and set PROXIMO_AGENT_ALLOWLIST."),
    }


def _blocked_agent_allowlist(action: str, target: str, detail: dict | None = None,
                              *, mutation: bool = True) -> dict:
    """Refuse + audit a qemu-agent op whose VMID isn't on the allowlist (fail-closed).
    `mutation` must reflect the GATED tool's true class so blocked reads don't ledger as mutations."""
    _, _, _, audit = _svc()
    audit.record(action, target=target, mutation=mutation, outcome="blocked:allowlist", detail=detail)
    return {"status": "blocked:allowlist",
            "message": f"Guest {target} is not permitted by the agent allowlist (fail-closed)."}


# --- Management (REST API, read) ---

@mcp.tool()
def pve_node_status(node: str | None = None) -> dict:
    """Health and resource status of a Proxmox node."""
    cfg, api, _, _ = _svc()
    return _audited("pve_node_status", node or cfg.node, lambda: api.node_status(node))


@mcp.tool()
def pve_list_guests(node: str | None = None) -> list[dict]:
    """List all VMs and LXC containers on a node, with state."""
    cfg, api, _, _ = _svc()
    return _audited("pve_list_guests", node or cfg.node, lambda: api.list_guests(node))


@mcp.tool()
def pve_guest_status(vmid: str, kind: str = "lxc", node: str | None = None) -> dict:
    """Status/config of one guest (kind = 'lxc' or 'qemu')."""
    _, api, _, _ = _svc()
    return _audited("pve_guest_status", f"{kind}/{vmid}", lambda: api.guest_status(vmid, kind, node))


# --- Management (REST API, MUTATION — confirm-gated) ---

@mcp.tool()
def pve_guest_power(
    vmid: str, action: str, kind: str = "lxc", node: str | None = None, confirm: bool = False
) -> dict:
    """MUTATION: start/stop/reboot/shutdown a guest.

    Dry-run by default: without confirm=True you get a PLAN — the exact change, the guest's live
    state, blast radius, and risk (with no-op detection) — recorded to the ledger. Re-call with
    confirm=True to execute. The plan is recorded on BOTH paths: even a one-shot confirm=True call
    records its plan before mutating — no plan, no mutation.
    """
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}:{action}"
    plan = _plan("pve_guest_power", target, lambda: plan_power(api, vmid, action, kind, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    # PVE guest power is task-backed (POST .../status/{action} returns a UPID) — async, like the
    # identical-shape node_service_control. Record "submitted", never "ok": the ledger must not claim
    # the guest stopped/started when only the task was accepted.
    return _audited("pve_guest_power", target, lambda: api.guest_power(vmid, action, kind, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


# --- Snapshots / UNDO (REST API). Create/rollback/delete are ASYNC -> return a task UPID. ---

@mcp.tool()
def pve_snapshot_list(vmid: str, kind: str = "lxc", node: str | None = None) -> list[dict]:
    """List a guest's snapshots (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_snapshot_list", f"{kind}/{vmid}", lambda: api.snapshot_list(vmid, kind, node))


@mcp.tool()
def pve_snapshot_create(vmid: str, snapname: str, kind: str = "lxc", node: str | None = None,
                        description: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create a snapshot (a restore point). Dry-run by default; confirm=True to execute.
    Async — returns the task UPID; poll pve_task_status. Needs snapshot-capable storage (ZFS/BTRFS/LVM-thin)."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}:{snapname}"
    plan = _plan("pve_snapshot_create", target, lambda: plan_snapshot_create(vmid, snapname, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_snapshot_create", target,
                    lambda: api.snapshot_create(vmid, snapname, kind, node, description),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_rollback(vmid: str, snapname: str, kind: str = "lxc", node: str | None = None,
                 confirm: bool = False) -> dict:
    """MUTATION (DESTRUCTIVE): roll a guest back to a snapshot — discards ALL changes since it.
    Dry-run by default (the PLAN spells out the blast radius); confirm=True to execute. Async -> UPID."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}:{snapname}"
    plan = _plan("pve_rollback", target, lambda: plan_rollback(api, vmid, snapname, kind, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_rollback", target,
                    lambda: api.snapshot_rollback(vmid, snapname, kind, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_snapshot_delete(vmid: str, snapname: str, kind: str = "lxc", node: str | None = None,
                        force: bool = False, confirm: bool = False) -> dict:
    """MUTATION: delete a snapshot (removes a restore point). Dry-run by default; confirm=True to execute.
    Async -> UPID."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}:{snapname}"
    plan = _plan("pve_snapshot_delete", target, lambda: plan_snapshot_delete(vmid, snapname, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_snapshot_delete", target,
                    lambda: api.snapshot_delete(vmid, snapname, kind, node, force),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_task_status(upid: str, node: str | None = None) -> dict:
    """Status of an async Proxmox task (running/stopped + exit status) — poll snapshot/rollback ops (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_task_status", upid, lambda: api.task_status(upid, node))


# --- In-container exec (ssh -> pct) — MUTATION-CAPABLE, confirm-gated ---

@mcp.tool()
def ct_exec(ctid: str, command: list[str], snapshot: bool = False, confirm: bool = False) -> dict:
    """Run a command inside an LXC (ssh -> pct exec). MUTATION-CAPABLE.

    Dry-run by default: without confirm=True you get a PLAN — the command plus a heuristic
    read-vs-write / destructive-pattern classification (advisory only) — recorded to the ledger.
    Re-call with confirm=True to execute. Disabled unless PROXIMO_ENABLE_EXEC is set (safe default
    is API-only). Allowlist-scoped (fail-closed) and audited.

    snapshot=True (UNDO): take an auto-undo snapshot first and WAIT for it; if it can't be made
    (e.g. storage doesn't support snapshots) the command is NOT run (fail-closed). On success the
    result carries an `undo_point` you can revert with pve_rollback.
    """
    cfg, api, exec_, _ = _svc()
    # Audit completeness is the default; PROXIMO_LEDGER_REDACT records a command fingerprint instead
    # of the argv (which can carry secrets, e.g. `--password ...`) — see audit.py + README.
    detail = command_fingerprint(command) if cfg.redact_ledger else {"command": command}
    if not cfg.enable_exec:
        return _exec_disabled("ct_exec", str(ctid), detail)
    if not cfg.ct_permitted(ctid):
        return _blocked_allowlist("ct_exec", str(ctid), detail)
    plan = _plan("ct_exec", str(ctid), lambda: plan_exec(ctid, command, redact=cfg.redact_ledger))
    if not confirm:
        return {"status": "plan", "auto_snapshot": snapshot, **plan.as_dict()}

    undo_point = None
    if snapshot:
        undo = _auto_undo("ct_exec", str(ctid), api, ctid, detail)
        if undo.get("status") == "blocked:undo_unavailable":
            return undo  # fail-closed: command NOT run
        undo_point = undo

    def _do() -> dict:
        r = exec_.run(ctid, command)
        out = {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr}
        if undo_point:
            out["undo_point"] = undo_point
        return out

    return _audited("ct_exec", str(ctid), _do, mutation=True,
                    detail={**detail, "confirmed": True, "undo": bool(undo_point)})


@mcp.tool()
def ct_psql(ctid: str, sql: str, db: str = "postgres", snapshot: bool = False,
            confirm: bool = False) -> dict:
    """Run SQL via psql inside a container (as the db OS user). MUTATION-CAPABLE.

    Dry-run by default: without confirm=True you get a PLAN — the SQL plus a heuristic
    read/DML/DDL classification (advisory only) — recorded to the ledger. Re-call with
    confirm=True to execute.

    snapshot=True (UNDO): take an auto-undo snapshot first and WAIT for it; if it can't be made the
    SQL is NOT run (fail-closed). On success the result carries an `undo_point` (revert via pve_rollback).
    """
    cfg, api, exec_, _ = _svc()
    # Audit completeness is the default; PROXIMO_LEDGER_REDACT records a fingerprint instead of
    # the body (which can carry secrets/PII) — see audit.py + README.
    detail = {"db": db, **(sql_fingerprint(sql) if cfg.redact_ledger else {"sql": sql})}
    if not cfg.enable_exec:
        return _exec_disabled("ct_psql", str(ctid), detail)
    if not cfg.ct_permitted(ctid):
        return _blocked_allowlist("ct_psql", str(ctid), detail)
    plan = _plan("ct_psql", str(ctid), lambda: plan_psql(ctid, sql, db=db, redact=cfg.redact_ledger))
    if not confirm:
        return {"status": "plan", "auto_snapshot": snapshot, **plan.as_dict()}

    undo_point = None
    if snapshot:
        undo = _auto_undo("ct_psql", str(ctid), api, ctid, detail)
        if undo.get("status") == "blocked:undo_unavailable":
            return undo  # fail-closed: SQL NOT run
        undo_point = undo

    def _do() -> dict:
        r = exec_.psql(ctid, sql, db=db)
        out = {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr}
        if undo_point:
            out["undo_point"] = undo_point
        return out

    return _audited("ct_psql", str(ctid), _do, mutation=True,
                    detail={**detail, "confirmed": True, "undo": bool(undo_point)})


# --- In-container (read) ---

@mcp.tool()
def ct_logs(ctid: str, unit: str, lines: int = 50) -> dict:
    """Tail journalctl for a systemd unit inside a container (read-only)."""
    cfg, _, exec_, _ = _svc()
    detail = {"unit": unit, "lines": lines}
    if not cfg.enable_exec:
        return _exec_disabled("ct_logs", str(ctid), detail, mutation=False)
    if not cfg.ct_permitted(ctid):
        return _blocked_allowlist("ct_logs", str(ctid), detail, mutation=False)

    def _do() -> dict:
        r = exec_.logs(ctid, unit, lines=lines)
        return {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr}

    return _audited("ct_logs", str(ctid), _do, detail=detail)


@mcp.tool()
def ct_diagnose(ctid: str, kind: str = "lxc", node: str | None = None) -> dict:
    """READ-ONLY: gather 'what's broken' evidence for a container — API status + a fixed read-only
    in-container battery (failed units, disk, recent errors, memory, listening ports) + advisory flags.

    No mutation, no confirm. The in-container probes need PROXIMO_ENABLE_EXEC and the CTID allowlist
    (same as ct_logs); with exec off it returns the API-only part and discloses the skipped probes."""
    cfg, api, exec_, _ = _svc()
    target = f"{kind}/{ctid}"
    if cfg.enable_exec and not cfg.ct_permitted(ctid):
        return _blocked_allowlist("ct_diagnose", str(ctid), mutation=False)
    use_exec = exec_ if cfg.enable_exec else None
    return _audited("ct_diagnose", target, lambda: diagnose_container(api, use_exec, ctid, kind, node))


@mcp.tool()
def pve_diagnose(node: str | None = None) -> dict:
    """READ-ONLY: gather node health evidence — status + storage usage + recent failed tasks + flags."""
    _, api, _, _ = _svc()
    return _audited("pve_diagnose", node or "node", lambda: diagnose_node(api, node))


@mcp.tool()
def pve_doctor() -> dict:
    """READ-ONLY preflight: check API connectivity + the calling token's effective permissions, and
    report what this token CAN and CANNOT do — with the privilege + role to grant for each gap. Run
    this FIRST after install to verify your config/token before wiring Proximo into an MCP client."""
    _, api, _, _ = _svc()
    return _audited("pve_doctor", "preflight", lambda: doctor_check(api), mutation=False)


@mcp.tool()
def audit_verify(expected_head: str | None = None) -> dict:
    """Verify the tamper-evident audit ledger's hash chain — PROVE the log is intact.

    Pass `expected_head` (the head() value you pinned off-box) to also catch tail
    truncation, a forged tail-append, or a full file replacement — a forward walk
    alone can't see those. Falls back to PROXIMO_AUDIT_EXPECTED_HEAD when omitted.
    """
    cfg, _, _, audit = _svc()
    pin = expected_head if expected_head is not None else cfg.expected_head
    if pin is not None:
        # Normalize a copy-pasted head (case-insensitive hexdigest; strip stray spaces/newline) the
        # same way config does — a blank/whitespace value becomes "unpinned", not a caller error.
        pin = pin.strip().lower() or None
    if pin is not None and not looks_like_head(pin):
        # A genuinely malformed pin is a CALLER error, not tamper — raise clearly instead of
        # letting it fall through to a "head mismatch" that cries wolf.
        raise ProximoError(
            f"invalid expected_head: {pin!r} (must be a 64-char hex head() value)"
        )
    v = audit.verify(expected_head=pin)
    # When nothing is pinned, the forward walk can't see tail truncation / forged append / wipe —
    # nudge the operator to anchor the head off-box (the strong guarantee), so the feature isn't
    # silently unused. No nudge once a pin is in effect.
    hint = None if pin is not None else (
        "not pinned against tail attacks: set PROXIMO_AUDIT_EXPECTED_HEAD (or pass expected_head=) "
        "to the current 'head' value, stored off-box, to detect tail truncation / forged append / "
        "full wipe — the off-box anchor is the strong guarantee."
    )
    # A pinned "head mismatch" with the chain otherwise intact is byte-identical whether it's a tail
    # attack or a keyed-default upgrade that rotated the head. If a rotation archive sits beside the
    # ledger, say so — the stderr migration warning is often swallowed by MCP stdio clients.
    rotation_hint = None
    if not v.ok and v.broken_at is None and pin is not None:
        archive = find_rotation_archive(audit.path)
        if archive:
            rotation_hint = (
                "a keyed-default migration archive sits beside this ledger "
                f"({os.path.basename(archive)!r}). If you upgraded Proximo since you pinned, this "
                "'head mismatch' is the expected migration head-rotation — re-pin "
                "PROXIMO_AUDIT_EXPECTED_HEAD to the 'head' value above. If you did NOT just upgrade, "
                "treat this as a genuine tail-attack signal and investigate."
            )
    return {
        "ok": v.ok,
        "entries": v.entries,
        "broken_at_line": v.broken_at,
        "reason": v.reason,
        "head": audit.head(),
        "expected_head": pin,
        "keyed": audit.keyed,
        "hint": hint,
        "rotation_hint": rotation_hint,
    }


# --- Backup & restore (REST API, async -> UPID) ---

@mcp.tool()
def pve_backup(vmid: str, storage: str, mode: str = "snapshot", compress: str = "zstd",
               kind: str = "lxc", node: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: back up a guest with vzdump. Dry-run by default; confirm=True to execute.
    mode: snapshot (online, brief) | suspend | stop (HALTS the guest). Async — returns a task UPID."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}"
    plan = _plan("pve_backup", target, lambda: plan_backup(vmid, storage, mode, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_backup", target,
                    lambda: vzdump_backup(api, vmid, storage, mode, compress, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_backup_list(storage: str, node: str | None = None) -> list[dict]:
    """List backup archives in a storage (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_backup_list", storage, lambda: backup_list(api, storage, node))


@mcp.tool()
def pve_backup_delete(storage: str, volid: str, node: str | None = None,
                      confirm: bool = False) -> dict:
    """MUTATION: delete a backup archive (removes a recovery point). Dry-run by default; confirm=True.
    Async — may return a task UPID or null depending on storage."""
    _, api, _, _ = _svc()
    plan = _plan("pve_backup_delete", volid, lambda: plan_backup_delete(api, storage, volid))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_backup_delete", volid,
                    lambda: backup_delete(api, storage, volid, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_restore(vmid: str, archive: str, storage: str, kind: str = "lxc", node: str | None = None,
                force: bool = False, pool: str | None = None, confirm: bool = False) -> dict:
    """MUTATION (DESTRUCTIVE if it overwrites an existing guest): restore a guest from a backup
    archive. Dry-run by default — the PLAN states whether it CREATES or OVERWRITES. confirm=True to
    execute. Async — returns a task UPID. pool: place the restored guest in a resource pool."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}"
    plan = _plan("pve_restore", target, lambda: plan_restore(api, vmid, archive, kind, node, force))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_restore", target,
                    lambda: restore_guest(api, vmid, archive, storage, kind, node, force, pool),
                    mutation=True, outcome="submitted", detail={"confirmed": True, "force": force})


# --- Provisioning (REST API, async). create/clone are additive; delete is DESTRUCTIVE. ---

@mcp.tool()
def pve_create_container(vmid: str, ostemplate: str, storage: str, node: str | None = None,
                         options: dict | None = None, confirm: bool = False) -> dict:
    """MUTATION: create a new LXC container. Dry-run by default; confirm=True. Async — returns a UPID.
    `options` carries extra create params (cores, memory, net0, rootfs, password, ...)."""
    _, api, _, _ = _svc()
    target = f"lxc/{vmid}"
    plan = _plan("pve_create_container", target, lambda: plan_create(api, vmid, "lxc", node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited(
        "pve_create_container", target,
        lambda: create_container(api, vmid, ostemplate, storage, node, **(options or {})),
        mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_create_vm(vmid: str, node: str | None = None, options: dict | None = None,
                  confirm: bool = False) -> dict:
    """MUTATION: create a new QEMU VM. Dry-run by default; confirm=True. Async — returns a UPID.
    `options` carries create params (cores, memory, net0, scsi0, ostype, ...)."""
    _, api, _, _ = _svc()
    target = f"qemu/{vmid}"
    plan = _plan("pve_create_vm", target, lambda: plan_create(api, vmid, "qemu", node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_create_vm", target,
                    lambda: create_vm(api, vmid, node, **(options or {})),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_clone(vmid: str, newid: str, kind: str = "lxc", node: str | None = None,
              name: str | None = None, full: bool = False, pool: str | None = None,
              storage: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: clone a guest to a new id. Dry-run by default; confirm=True. Async — returns a UPID.
    pool: place the new guest in a resource pool (needed when the token is pool-scoped).
    storage: target storage for the full clone's disks (full=True only) — keeps a clone off the
    source storage; refused for a linked clone (PVE only honors it on a full clone)."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}->{newid}"
    plan = _plan("pve_clone", target, lambda: plan_clone(api, vmid, newid, kind, node, storage, full))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_clone", target,
                    lambda: clone_guest(api, vmid, newid, kind, node, name, full, pool, storage),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_delete_guest(vmid: str, kind: str = "lxc", node: str | None = None, purge: bool = False,
                     force: bool = False, confirm: bool = False) -> dict:
    """MUTATION (DESTRUCTIVE, IRREVERSIBLE): permanently destroy a guest and its disks. Dry-run by
    default — the PLAN names exactly what will be destroyed. confirm=True to execute. Async — UPID."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}"
    plan = _plan("pve_delete_guest", target, lambda: plan_delete(api, vmid, kind, node, purge, force))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_delete_guest", target,
                    lambda: delete_guest(api, vmid, kind, node, purge, force),
                    mutation=True, outcome="submitted", detail={"confirmed": True, "purge": purge})


# --- Storage / ISO / templates (REST API) ---

@mcp.tool()
def pve_storage_content(storage: str, node: str | None = None,
                        content: str | None = None) -> list[dict]:
    """List a storage's content, optionally filtered (content = iso | vztmpl | backup) (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_storage_content", storage,
                    lambda: storage_content(api, storage, node, content))


@mcp.tool()
def pve_storage_status(storage: str, node: str | None = None) -> dict:
    """Status of a storage — total/used/avail/enabled (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_storage_status", storage, lambda: storage_status(api, storage, node))


@mcp.tool()
def pve_storage_download(storage: str, content: str, url: str, filename: str,
                         node: str | None = None, checksum: str | None = None,
                         checksum_algorithm: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: download an ISO (content=iso) or CT template (content=vztmpl) from a URL into a
    storage. Dry-run by default; confirm=True. Async — returns a UPID."""
    _, api, _, _ = _svc()
    target = f"{storage}:{filename}"
    plan = _plan("pve_storage_download", target,
                 lambda: plan_storage_download(storage, content, url, filename))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited(
        "pve_storage_download", target,
        lambda: storage_download_url(api, storage, content, url, filename, node,
                                     checksum, checksum_algorithm),
        mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_storage_content_delete(storage: str, volid: str, node: str | None = None,
                               confirm: bool = False) -> dict:
    """MUTATION: delete a content volume (ISO / template / backup) from storage. Dry-run by default
    (HIGH risk for a backup volume); confirm=True. Async — UPID or null."""
    _, api, _, _ = _svc()
    plan = _plan("pve_storage_content_delete", volid, lambda: plan_content_delete(api, storage, volid))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_storage_content_delete", volid,
                    lambda: content_delete(api, storage, volid, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


# --- Guest config edit (REST API). Config PUT is SYNCHRONOUS -> outcome="ok". ---

@mcp.tool()
def pve_guest_config_get(vmid: str, kind: str = "lxc", node: str | None = None) -> dict:
    """Read a guest's current config (kind = 'lxc' or 'qemu') (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_guest_config_get", f"{kind}/{vmid}",
                    lambda: guest_config_get(api, vmid, kind, node))


@mcp.tool()
def pve_guest_config_set(vmid: str, changes: dict, kind: str = "lxc", node: str | None = None,
                         confirm: bool = False) -> dict:
    """MUTATION: edit a guest's config (cores/memory/net/onboot/...). Dry-run by default — the PLAN
    shows the exact per-key diff; confirm=True to execute. Captures the prior config first so the
    change is revertible via pve_guest_config_revert. Synchronous."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}"
    plan = _plan("pve_guest_config_set", target,
                 lambda: plan_config_set(api, vmid, changes, kind, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_guest_config_set", target,
                    lambda: guest_config_set(api, vmid, changes, kind, node),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_guest_config_revert(vmid: str, prior_config: dict, kind: str = "lxc",
                            node: str | None = None, confirm: bool = False) -> dict:
    """MUTATION (UNDO): re-apply a previously captured guest config (the prior_config returned by
    pve_guest_config_set). Dry-run by default; confirm=True to execute. Synchronous."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}"
    plan = _plan("pve_guest_config_revert", target,
                 lambda: plan_config_revert(api, vmid, prior_config, kind, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_guest_config_revert", target,
                    lambda: guest_config_revert(api, vmid, prior_config, kind, node),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- Disk ops (REST API). Resize/move are async -> task UPID -> outcome="submitted". ---

@mcp.tool()
def pve_disk_resize(vmid: str, disk: str, size: str, kind: str = "lxc", node: str | None = None,
                    confirm: bool = False) -> dict:
    """MUTATION: grow a guest disk (e.g. size='+10G'). GROW ONLY — a shrink is refused (destructive).
    Dry-run by default; confirm=True to execute. Async — returns a task UPID."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}:{disk}"
    plan = _plan("pve_disk_resize", target,
                 lambda: plan_disk_resize(api, vmid, disk, size, kind, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_disk_resize", target,
                    lambda: disk_resize(api, vmid, disk, size, kind, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_disk_move(vmid: str, disk: str, target_storage: str, kind: str = "lxc",
                  node: str | None = None, delete_source: bool = False,
                  confirm: bool = False) -> dict:
    """MUTATION: move a guest disk to another storage. Dry-run by default — the PLAN shows
    source->target and whether the source copy is deleted (delete_source=True is HIGH). confirm=True
    to execute. Async — returns a task UPID."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}:{disk}"
    plan = _plan("pve_disk_move", target,
                 lambda: plan_disk_move(api, vmid, disk, target_storage, kind, node, delete_source))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_disk_move", target,
                    lambda: disk_move(api, vmid, disk, target_storage, kind, node, delete_source),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


# --- Cloud-init + template (REST API, QEMU). Config POST is synchronous -> outcome="ok". ---

@mcp.tool()
def pve_cloudinit_get(vmid: str, node: str | None = None, kind: str = "qemu") -> dict:
    """Read a QEMU guest's cloud-init config (secret fields are masked) (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_cloudinit_get", f"{kind}/{vmid}",
                    lambda: cloudinit_get(api, vmid, node, kind))


@mcp.tool()
def pve_cloudinit_set(vmid: str, changes: dict, node: str | None = None, kind: str = "qemu",
                      confirm: bool = False) -> dict:
    """MUTATION: set cloud-init fields (ciuser/sshkeys/ipconfigN/...) on a QEMU guest. Dry-run by
    default — the PLAN shows the diff with secrets masked; confirm=True to execute. Synchronous.
    Secret fields (cipassword) are never echoed to results or the ledger."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}"
    plan = _plan("pve_cloudinit_set", target,
                 lambda: plan_cloudinit_set(api, vmid, changes, node, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    # Capture the prior cloud-init config (secret-stripped) BEFORE the set, so the result carries
    # a real undo_record. A config edit is not blocked on undo-capture failure (unlike exec) — but
    # the degraded UNDO must NOT be silent: surface it in the status AND the PROVE ledger (M-1).
    try:
        undo = capture_cloudinit_undo(api, vmid, node, kind)
        outcome = "ok"
    except Exception as e:
        undo = {"prior_ci_config": None,
                "secret_undo_caveat": f"undo capture failed: {type(e).__name__}"}
        outcome = "ok:undo_unavailable"  # mutation ran, but no rollback was captured — recorded, not silent
    envelope = _audited("pve_cloudinit_set", target,
                        lambda: cloudinit_set(api, vmid, changes, node, kind),
                        mutation=True, outcome=outcome, detail={"confirmed": True})
    envelope["undo_record"] = undo
    return envelope


@mcp.tool()
def pve_template_convert(vmid: str, node: str | None = None, kind: str = "qemu",
                         confirm: bool = False) -> dict:
    """MUTATION (IRREVERSIBLE): convert a guest into a template — effectively one-way. Dry-run by
    default (the PLAN flags it HIGH/irreversible); confirm=True to execute."""
    _, api, _, _ = _svc()
    target = f"{kind}/{vmid}"
    plan = _plan("pve_template_convert", target,
                 lambda: plan_template_convert(api, vmid, node, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_template_convert", target,
                    lambda: template_convert(api, vmid, node, kind),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


# --- Access governance (REST API, read) ---

@mcp.tool()
def pve_users_list() -> list[dict]:
    """List all Proxmox users (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_users_list", "access/users", lambda: access_users_list(api))


@mcp.tool()
def pve_roles_list() -> list[dict]:
    """List all Proxmox roles and their privileges (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_roles_list", "access/roles", lambda: access_roles_list(api))


@mcp.tool()
def pve_acl_list() -> list[dict]:
    """List all ACL entries on the Proxmox cluster (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_acl_list", "access/acl", lambda: access_acl_list(api))


@mcp.tool()
def pve_tokens_list(userid: str) -> list[dict]:
    """List API tokens for a specific user (read). userid: 'user@realm'."""
    _, api, _, _ = _svc()
    return _audited("pve_tokens_list", f"access/users/{userid}/token",
                    lambda: access_tokens_list(api, userid))


@mcp.tool()
def pve_overbroad_grants() -> list[dict]:
    """Surface over-broad ACL grants (Administrator role or root '/' path) as a diagnostic (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_overbroad_grants", "access/acl",
                    lambda: access_overbroad_grants(api))


# --- Access governance (REST API, MUTATION — confirm-gated) ---

@mcp.tool()
def pve_acl_modify(
    path: str, roles: str, target: str, kind: str = "user",
    propagate: bool = True, delete: bool = False, confirm: bool = False,
) -> dict:
    """MUTATION: grant or revoke an ACL entry (PUT /access/acl).

    Dry-run by default — the PLAN surfaces the critical Proxmox gotcha: a specific-path ACL
    REPLACES inherited grants (SHADOW) and revoking can RESTORE them (WIDEN). Re-call with
    confirm=True to execute. Synchronous.

    kind='user' (default) or 'token'. delete=False = grant; delete=True = revoke.
    """
    _, api, _, _ = _svc()
    tgt = f"acl:{path}:{target}"
    plan = _plan("pve_acl_modify", tgt,
                 lambda: plan_acl_modify(api, path, roles, target, kind, propagate, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_acl_modify", tgt,
                    lambda: acl_modify(api, path, roles, target, kind, propagate, delete),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_token_create(
    userid: str, tokenid: str, privsep: bool = True,
    comment: str | None = None, expire: int | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: create an API token for a user.

    Dry-run by default — the PLAN shows risk (privsep=False is HIGH: token inherits ALL owner perms).
    confirm=True to execute. The token secret (value) is returned ONCE to the caller and is NEVER
    written to the audit ledger. Synchronous.
    """
    _, api, _, _ = _svc()
    tgt = f"token:{userid}!{tokenid}"
    plan = _plan("pve_token_create", tgt,
                 lambda: plan_token_create(userid, tokenid, privsep))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    # SECRET HANDLING: return op result directly (carries the token value to caller);
    # detail dict must NEVER contain the secret — only {"confirmed": True}.
    return _audited("pve_token_create", tgt,
                    lambda: token_create(api, userid, tokenid, privsep, comment, expire),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_token_revoke(userid: str, tokenid: str, confirm: bool = False) -> dict:
    """MUTATION (IRREVERSIBLE): permanently revoke an API token.

    Dry-run by default — the PLAN flags HIGH: revocation is permanent, the secret is gone forever.
    confirm=True to execute. Synchronous.
    """
    _, api, _, _ = _svc()
    tgt = f"token:{userid}!{tokenid}"
    plan = _plan("pve_token_revoke", tgt, lambda: plan_token_revoke(userid, tokenid))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_token_revoke", tgt,
                    lambda: token_revoke(api, userid, tokenid),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- Firewall (REST API, read) ---

@mcp.tool()
def pve_firewall_rules_list(
    scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
) -> list[dict]:
    """List all firewall rules for the given scope (cluster/node/guest) (read)."""
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}"
    return _audited("pve_firewall_rules_list", tgt,
                    lambda: firewall_rules_list(api, scope, node, vmid, kind))


@mcp.tool()
def pve_firewall_options_get(
    scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
) -> dict:
    """Get firewall options (enable flag, policy, log rate, …) for the given scope (read)."""
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/options"
    return _audited("pve_firewall_options_get", tgt,
                    lambda: firewall_options_get(api, scope, node, vmid, kind))


@mcp.tool()
def pve_security_groups_list() -> list[dict]:
    """List cluster-wide firewall security groups (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_security_groups_list", "firewall/cluster/groups",
                    lambda: security_groups_list(api))


@mcp.tool()
def pve_ipset_list(
    scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
) -> list[dict]:
    """List IP sets for the given scope (read)."""
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/ipset"
    return _audited("pve_ipset_list", tgt,
                    lambda: ipset_list(api, scope, node, vmid, kind))


# --- Firewall (REST API, MUTATION — confirm-gated) ---

@mcp.tool()
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
    _, api, _, _ = _svc()
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


@mcp.tool()
def pve_firewall_rule_remove(
    pos: int, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: delete a firewall rule by position. Dry-run by default — the PLAN shows the rule
    at that position. Positions SHIFT after inserts/deletes — verify before confirming. Synchronous.
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/rules/{pos}"
    plan = _plan("pve_firewall_rule_remove", tgt,
                 lambda: plan_firewall_rule_remove(api, pos, scope, node, vmid, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_rule_remove", tgt,
                    lambda: firewall_rule_remove(api, pos, scope, node, vmid, kind),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
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
    _, api, _, _ = _svc()
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


@mcp.tool()
def pve_firewall_set_enabled(
    enabled: bool, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION (HIGH RISK): toggle the firewall on or off for the given scope. Dry-run by default.
    RISK_HIGH both directions: enabling may instantly lock you out (default-DROP, no ACCEPT for 22/8006);
    disabling strips all protection. Cluster scope = master kill-switch. Synchronous.
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/options"
    plan = _plan("pve_firewall_set_enabled", tgt,
                 lambda: plan_firewall_set_enabled(api, enabled, scope, node, vmid, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_set_enabled", tgt,
                    lambda: firewall_set_enabled(api, enabled, scope, node, vmid, kind),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_alias_list(
    scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
) -> list[dict]:
    """List firewall aliases (named CIDRs) for the given scope (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_firewall_alias_list", f"firewall/{scope}/aliases",
                    lambda: alias_list(api, scope, node, vmid, kind))


@mcp.tool()
def pve_firewall_alias_create(
    name: str, cidr: str, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None, comment: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: create a firewall alias (named CIDR). Dry-run by default — the PLAN shows the
    name, CIDR, and scope. Re-call with confirm=True to execute. Passive until a rule references it.
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/aliases/{name}"
    plan = _plan("pve_firewall_alias_create", tgt,
                 lambda: plan_alias_create(name, cidr, scope, node, vmid, kind, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_alias_create", tgt,
                    lambda: alias_create(api, name, cidr, scope, node, vmid, kind, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_alias_update(
    name: str, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
    cidr: str | None = None, comment: str | None = None,
    rename: str | None = None, digest: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: update a firewall alias. Dry-run by default — the PLAN shows the current alias and
    the fields being changed. Changing the CIDR silently alters every referencing rule's match set.
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/aliases/{name}"
    plan = _plan("pve_firewall_alias_update", tgt,
                 lambda: plan_alias_update(api, name, scope, node, vmid, kind, cidr, comment, rename))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_alias_update", tgt,
                    lambda: alias_update(api, name, scope, node, vmid, kind, cidr, comment, rename, digest),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_alias_delete(
    name: str, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
    digest: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: delete a firewall alias. Dry-run by default — the PLAN shows the current alias.
    PVE refuses while any rule still references the alias. No UNDO: re-create to revert.
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/aliases/{name}"
    plan = _plan("pve_firewall_alias_delete", tgt,
                 lambda: plan_alias_delete(api, name, scope, node, vmid, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_alias_delete", tgt,
                    lambda: alias_delete(api, name, scope, node, vmid, kind, digest),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_ipset_create(
    name: str, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None, comment: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: create an empty IP set. Dry-run by default — the PLAN shows the name and scope.
    Passive until a rule references it as '+name' and entries are added.
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/ipset/{name}"
    plan = _plan("pve_firewall_ipset_create", tgt,
                 lambda: plan_ipset_create(name, scope, node, vmid, kind, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_ipset_create", tgt,
                    lambda: ipset_create(api, name, scope, node, vmid, kind, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_ipset_delete(
    name: str, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
    force: bool = False, confirm: bool = False,
) -> dict:
    """MUTATION: delete an IP set. Dry-run by default — the PLAN shows member count and the
    force semantics. force=True WIPES all members; PVE refuses while a rule references the set.
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/ipset/{name}"
    plan = _plan("pve_firewall_ipset_delete", tgt,
                 lambda: plan_ipset_delete(api, name, scope, node, vmid, kind, force))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_ipset_delete", tgt,
                    lambda: ipset_delete(api, name, scope, node, vmid, kind, force),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_ipset_entry_add(
    name: str, cidr: str, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
    comment: str | None = None, nomatch: bool = False, confirm: bool = False,
) -> dict:
    """MUTATION: add an IP/Network entry to an IP set. Dry-run by default — the PLAN shows the
    entry and warns it changes every referencing rule's match set. nomatch=True = exclusion.
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/ipset/{name}"
    plan = _plan("pve_firewall_ipset_entry_add", tgt,
                 lambda: plan_ipset_entry_add(name, cidr, scope, node, vmid, kind, comment, nomatch))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_ipset_entry_add", tgt,
                    lambda: ipset_entry_add(api, name, cidr, scope, node, vmid, kind, comment, nomatch),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_ipset_entry_remove(
    name: str, cidr: str, scope: str = "cluster", node: str | None = None,
    vmid: str | None = None, kind: str | None = None,
    digest: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: remove an IP/Network entry from an IP set. Dry-run by default — the PLAN shows the
    entry and warns it changes every referencing rule's match set (may open or close access).
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/ipset/{name}"
    plan = _plan("pve_firewall_ipset_entry_remove", tgt,
                 lambda: plan_ipset_entry_remove(name, cidr, scope, node, vmid, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_ipset_entry_remove", tgt,
                    lambda: ipset_entry_remove(api, name, cidr, scope, node, vmid, kind, digest),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_security_group_create(
    group: str, comment: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: create an empty cluster security group. Dry-run by default — the PLAN shows the
    name. Passive until rules are added and a rule references it (type=group).
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/cluster/groups/{group}"
    plan = _plan("pve_firewall_security_group_create", tgt,
                 lambda: plan_security_group_create(group, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_security_group_create", tgt,
                    lambda: security_group_create(api, group, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_firewall_security_group_delete(group: str, confirm: bool = False) -> dict:
    """MUTATION: delete a cluster security group. Dry-run by default — the PLAN shows how many rules
    the group holds. PVE refuses while the group is non-empty or still referenced by a rule.
    """
    _, api, _, _ = _svc()
    tgt = f"firewall/cluster/groups/{group}"
    plan = _plan("pve_firewall_security_group_delete", tgt,
                 lambda: plan_security_group_delete(api, group))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_security_group_delete", tgt,
                    lambda: security_group_delete(api, group),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
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
    _, api, _, _ = _svc()
    tgt = f"firewall/{scope}/options"
    plan = _plan("pve_firewall_options_set", tgt,
                 lambda: plan_firewall_options_set(api, scope, node, vmid, kind, options, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_firewall_options_set", tgt,
                    lambda: firewall_options_set(api, scope, node, vmid, kind, options, delete, digest),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- Network & SDN (REST API, read) ---

@mcp.tool()
def pve_network_list(node: str | None = None, iface_type: str | None = None) -> list[dict]:
    """List network interfaces on a node (bridges, bonds, VLANs, etc.) (read)."""
    cfg, api, _, _ = _svc()
    tgt = f"nodes/{node or cfg.node}/network"
    return _audited("pve_network_list", tgt, lambda: network_list(api, node, iface_type))


@mcp.tool()
def pve_sdn_zones_list() -> list[dict]:
    """List SDN zones (cluster-scoped) (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_sdn_zones_list", "cluster/sdn/zones", lambda: sdn_zones_list(api))


@mcp.tool()
def pve_sdn_vnets_list() -> list[dict]:
    """List SDN virtual networks (cluster-scoped) (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_sdn_vnets_list", "cluster/sdn/vnets", lambda: sdn_vnets_list(api))


# --- Network & SDN (REST API, MUTATION — confirm-gated) ---

@mcp.tool()
def pve_sdn_subnet_list(vnet: str) -> list[dict]:
    """List subnets in an SDN vnet (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_sdn_subnet_list", f"sdn/vnets/{vnet}/subnets",
                    lambda: sdn_subnet_list(api, vnet))


@mcp.tool()
def pve_sdn_zone_create(
    zone: str, zone_type: str, options: dict | None = None,
    lock_token: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: create an SDN zone (PENDING — inert until pve_sdn_apply, NOT applied here).
    `zone_type` is simple/vlan/qinq/vxlan/evpn/faucet; `options` carries type-specific params.
    Dry-run by default. RISK_LOW (staging, no live network effect).
    """
    _, api, _, _ = _svc()
    tgt = f"sdn/zones/{zone}"
    plan = _plan("pve_sdn_zone_create", tgt, lambda: plan_sdn_zone_create(zone, zone_type, options))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_zone_create", tgt,
                    lambda: sdn_zone_create(api, zone, zone_type, options, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_sdn_zone_update(
    zone: str, options: dict | None = None, delete: list[str] | None = None,
    digest: str | None = None, lock_token: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: update an SDN zone (PENDING). `options` sets fields; `delete` unsets keys.
    Dry-run by default. RISK_LOW (staging; inert until pve_sdn_apply).
    """
    _, api, _, _ = _svc()
    tgt = f"sdn/zones/{zone}"
    plan = _plan("pve_sdn_zone_update", tgt, lambda: plan_sdn_zone_update(zone, options, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_zone_update", tgt,
                    lambda: sdn_zone_update(api, zone, options, delete, digest, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_sdn_zone_delete(zone: str, lock_token: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: delete an SDN zone (PENDING). Dry-run by default — the PLAN shows the current zone.
    PVE refuses if a vnet still references it. RISK_MEDIUM (staging a removal an apply would enact).
    """
    _, api, _, _ = _svc()
    tgt = f"sdn/zones/{zone}"
    plan = _plan("pve_sdn_zone_delete", tgt, lambda: plan_sdn_zone_delete(api, zone))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_zone_delete", tgt,
                    lambda: sdn_zone_delete(api, zone, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_sdn_vnet_create(
    vnet: str, zone: str, options: dict | None = None,
    lock_token: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: create an SDN vnet in a zone (PENDING). `options` carries tag/alias/vlanaware/etc.
    Dry-run by default. RISK_LOW (staging; inert until pve_sdn_apply).
    """
    _, api, _, _ = _svc()
    tgt = f"sdn/vnets/{vnet}"
    plan = _plan("pve_sdn_vnet_create", tgt, lambda: plan_sdn_vnet_create(vnet, zone, options))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_vnet_create", tgt,
                    lambda: sdn_vnet_create(api, vnet, zone, options, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_sdn_vnet_update(
    vnet: str, options: dict | None = None, delete: list[str] | None = None,
    digest: str | None = None, lock_token: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: update an SDN vnet (PENDING). Dry-run by default. RISK_LOW (staging)."""
    _, api, _, _ = _svc()
    tgt = f"sdn/vnets/{vnet}"
    plan = _plan("pve_sdn_vnet_update", tgt, lambda: plan_sdn_vnet_update(vnet, options, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_vnet_update", tgt,
                    lambda: sdn_vnet_update(api, vnet, options, delete, digest, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_sdn_vnet_delete(vnet: str, lock_token: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: delete an SDN vnet (PENDING). Dry-run by default — the PLAN shows the current vnet.
    PVE refuses if a subnet still references it. RISK_MEDIUM.
    """
    _, api, _, _ = _svc()
    tgt = f"sdn/vnets/{vnet}"
    plan = _plan("pve_sdn_vnet_delete", tgt, lambda: plan_sdn_vnet_delete(api, vnet))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_vnet_delete", tgt,
                    lambda: sdn_vnet_delete(api, vnet, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_sdn_subnet_create(
    vnet: str, subnet: str, options: dict | None = None,
    lock_token: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: create an SDN subnet (PENDING). `subnet` is a CIDR (e.g. 10.0.0.0/24); `options`
    carries gateway/snat/dhcp params. Dry-run by default. RISK_LOW (staging; inert until apply).
    """
    _, api, _, _ = _svc()
    tgt = f"sdn/vnets/{vnet}/subnets/{subnet}"
    plan = _plan("pve_sdn_subnet_create", tgt, lambda: plan_sdn_subnet_create(vnet, subnet, options))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_subnet_create", tgt,
                    lambda: sdn_subnet_create(api, vnet, subnet, options, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_sdn_subnet_update(
    vnet: str, subnet: str, options: dict | None = None, delete: list[str] | None = None,
    digest: str | None = None, lock_token: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: update an SDN subnet (PENDING). `subnet` is the id from pve_sdn_subnet_list.
    Dry-run by default. RISK_LOW (staging).
    """
    _, api, _, _ = _svc()
    tgt = f"sdn/vnets/{vnet}/subnets/{subnet}"
    plan = _plan("pve_sdn_subnet_update", tgt, lambda: plan_sdn_subnet_update(vnet, subnet, options, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_subnet_update", tgt,
                    lambda: sdn_subnet_update(api, vnet, subnet, options, delete, digest, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_sdn_subnet_delete(
    vnet: str, subnet: str, lock_token: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: delete an SDN subnet (PENDING). `subnet` is the id from pve_sdn_subnet_list.
    Dry-run by default. RISK_MEDIUM (staging a removal an apply would enact).
    """
    _, api, _, _ = _svc()
    tgt = f"sdn/vnets/{vnet}/subnets/{subnet}"
    plan = _plan("pve_sdn_subnet_delete", tgt, lambda: plan_sdn_subnet_delete(vnet, subnet))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_subnet_delete", tgt,
                    lambda: sdn_subnet_delete(api, vnet, subnet, lock_token),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_network_iface_create(
    iface: str, iface_type: str, node: str | None = None,
    options: dict | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: create a new network interface config (staged — not live until pve_network_apply).
    Dry-run by default; confirm=True to execute. Synchronous.
    `options` carries type-dependent fields (address, netmask, gateway, bridge_ports, …).
    """
    cfg, api, _, _ = _svc()
    tgt = f"nodes/{node or cfg.node}/network/{iface}"
    plan = _plan("pve_network_iface_create", tgt,
                 lambda: plan_iface_create(api, iface, iface_type, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_network_iface_create", tgt,
                    lambda: network_iface_create(api, iface, iface_type, node, **(options or {})),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_network_iface_update(
    iface: str, node: str | None = None,
    options: dict | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: update an existing network interface config (staged — not live until pve_network_apply).
    Dry-run by default; confirm=True to execute. Synchronous.
    `options` carries fields to update (address, netmask, bridge_ports, …).
    """
    cfg, api, _, _ = _svc()
    tgt = f"nodes/{node or cfg.node}/network/{iface}"
    plan = _plan("pve_network_iface_update", tgt,
                 lambda: plan_iface_update(api, iface, node, options or {}))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_network_iface_update", tgt,
                    lambda: network_iface_update(api, iface, node, **(options or {})),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_network_apply(node: str | None = None, confirm: bool = False) -> dict:
    """MUTATION (HIGH RISK): apply staged network config changes to the live network stack.
    Dry-run by default — the PLAN surfaces pending interfaces. confirm=True to execute.
    A misconfigured interface can lose SSH/API access; recovery requires console/physical access.
    May return a UPID (async) or None (sync) — outcome='submitted' in either case.
    """
    cfg, api, _, _ = _svc()
    tgt = f"nodes/{node or cfg.node}/network"
    plan = _plan("pve_network_apply", tgt, lambda: plan_network_apply(api, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_network_apply", tgt,
                    lambda: network_apply(api, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_sdn_apply(confirm: bool = False) -> dict:
    """MUTATION (HIGH RISK): apply pending SDN config changes (cluster-scoped).
    Dry-run by default — the PLAN surfaces pending zones/vnets. confirm=True to execute.
    A misconfigured SDN can disrupt virtual networking for ALL guests cluster-wide.
    May return a UPID (async) or None (sync) — outcome='submitted' in either case.
    """
    _, api, _, _ = _svc()
    plan = _plan("pve_sdn_apply", "cluster/sdn", lambda: plan_sdn_apply(api))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_sdn_apply", "cluster/sdn",
                    lambda: sdn_apply(api),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


# --- Cluster & HA (REST API, read) ---

@mcp.tool()
def pve_cluster_status() -> list[dict]:
    """Overall cluster status — nodes, quorum, version (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_cluster_status", "cluster/status", lambda: cluster_status(api))


@mcp.tool()
def pve_cluster_resources(resource_type: str | None = None) -> list[dict]:
    """List all resources across the cluster (VMs, nodes, storage, SDN).
    resource_type: optional filter — 'vm', 'storage', 'node', or 'sdn' (read)."""
    _, api, _, _ = _svc()
    tgt = f"cluster/resources/{resource_type or 'all'}"
    return _audited("pve_cluster_resources", tgt,
                    lambda: cluster_resources(api, resource_type))


@mcp.tool()
def pve_ha_groups_list() -> list[dict]:
    """List all HA resource groups (read). PVE-8 only — PVE 9 migrated groups to rules
    (use pve_ha_rules_list); on PVE 9 this raises a clear error pointing there."""
    _, api, _, _ = _svc()
    return _audited("pve_ha_groups_list", "cluster/ha/groups", lambda: ha_groups_list(api))


@mcp.tool()
def pve_ha_rules_list() -> list[dict]:
    """List HA rules (read) — the PVE 9 replacement for HA groups."""
    _, api, _, _ = _svc()
    return _audited("pve_ha_rules_list", "cluster/ha/rules", lambda: ha_rules_list(api))


@mcp.tool()
def pve_ha_resources_list() -> list[dict]:
    """List all HA resources (managed guests) (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_ha_resources_list", "cluster/ha/resources",
                    lambda: ha_resources_list(api))


# --- Cluster & HA (REST API, MUTATION — confirm-gated) ---

@mcp.tool()
def pve_guest_migrate(
    vmid: str, target: str, kind: str = "lxc", node: str | None = None,
    online: bool = False, confirm: bool = False,
) -> dict:
    """MUTATION: migrate a guest to a different node. Dry-run by default — the PLAN shows the
    guest's live state, the source→target, and the honest blast radius (LXC 'online' is
    stop→move→start, NOT zero-downtime; QEMU live migration requires shared storage).
    confirm=True to execute. Async — returns a task UPID.
    """
    _, api, _, _ = _svc()
    tgt = f"{kind}/{vmid}->{target}"
    plan = _plan("pve_guest_migrate", tgt,
                 lambda: plan_migrate(api, vmid, target, kind, node, online))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_guest_migrate", tgt,
                    lambda: guest_migrate(api, vmid, target, kind, node, online),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pve_ha_resource_add(
    vmid: str, kind: str = "lxc", group: str | None = None,
    state: str | None = None, max_restart: int | None = None,
    max_relocate: int | None = None, confirm: bool = False,
) -> dict:
    """MUTATION: add a guest to HA management. Dry-run by default — the PLAN shows the SID,
    group, initial state, and blast radius (state='stopped' is HIGH: CRM will stop the guest).
    confirm=True to execute. Synchronous (pmxcfs config write; CRM enforces state asynchronously).
    """
    _, api, _, _ = _svc()
    tgt = f"ha:{kind}/{vmid}"
    plan = _plan("pve_ha_resource_add", tgt,
                 lambda: plan_ha_resource_add(vmid, kind, group, state))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_ha_resource_add", tgt,
                    lambda: ha_resource_add(api, vmid, kind, group, state, max_restart, max_relocate),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_ha_resource_remove(vmid: str, kind: str = "lxc", confirm: bool = False) -> dict:
    """MUTATION: remove a guest from HA management. Dry-run by default — the PLAN shows the SID
    and that this loses automated failover protection (guest itself is NOT stopped).
    confirm=True to execute. Synchronous (pmxcfs config write).
    """
    _, api, _, _ = _svc()
    tgt = f"ha:{kind}/{vmid}"
    plan = _plan("pve_ha_resource_remove", tgt,
                 lambda: plan_ha_resource_remove(vmid, kind))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_ha_resource_remove", tgt,
                    lambda: ha_resource_remove(api, vmid, kind),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
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
    _, api, _, _ = _svc()
    tgt = f"ha/rules/{rule}"
    plan = _plan("pve_ha_rule_create", tgt,
                 lambda: plan_ha_rule_create(rule, rule_type, resources, nodes, strict, affinity, disable))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_ha_rule_create", tgt,
                    lambda: ha_rule_create(api, rule, rule_type, resources, comment, disable,
                                           nodes, strict, affinity),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
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
    _, api, _, _ = _svc()
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


@mcp.tool()
def pve_ha_rule_delete(rule: str, confirm: bool = False) -> dict:
    """MUTATION: delete an HA rule. Dry-run by default — the PLAN shows the current rule and that
    its resources lose this placement constraint (CRM may migrate them). confirm=True to execute.
    Synchronous. RISK_MEDIUM.
    """
    _, api, _, _ = _svc()
    tgt = f"ha/rules/{rule}"
    plan = _plan("pve_ha_rule_delete", tgt, lambda: plan_ha_rule_delete(api, rule))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_ha_rule_delete", tgt,
                    lambda: ha_rule_delete(api, rule),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- Observability (REST API, read) ---

@mcp.tool()
def pve_node_services_list(node: str | None = None) -> list[dict]:
    """List all services on a PVE node, with state (read)."""
    cfg, api, _, _ = _svc()
    return _audited("pve_node_services_list", node or cfg.node,
                    lambda: node_services_list(api, node))


@mcp.tool()
def pve_node_service_status(service: str, node: str | None = None) -> dict:
    """Get the current state of a single service on a PVE node (read)."""
    cfg, api, _, _ = _svc()
    return _audited("pve_node_service_status", f"{node or cfg.node}/services/{service}",
                    lambda: node_service_status(api, service, node))


@mcp.tool()
def pve_node_rrddata(node: str | None = None, timeframe: str = "hour",
                     cf: str | None = None) -> list[dict]:
    """Get RRD telemetry (time-series) for a PVE node (read). timeframe: hour/day/week/month/year."""
    cfg, api, _, _ = _svc()
    return _audited("pve_node_rrddata", node or cfg.node,
                    lambda: node_rrddata(api, node, timeframe, cf))


@mcp.tool()
def pve_node_journal(node: str | None = None, lastentries: int = 100,
                     since: str | None = None, until: str | None = None) -> list[str]:
    """Fetch journal entries from a PVE node (read; returns log-line strings). lastentries capped at 5000."""
    cfg, api, _, _ = _svc()
    return _audited("pve_node_journal", node or cfg.node,
                    lambda: node_journal(api, node, lastentries, since, until))


@mcp.tool()
def pve_node_syslog(node: str | None = None, limit: int = 100) -> list[dict]:
    """Fetch syslog entries from a PVE node (read). limit capped at 5000."""
    cfg, api, _, _ = _svc()
    return _audited("pve_node_syslog", node or cfg.node,
                    lambda: node_syslog(api, node, limit))


@mcp.tool()
def pve_node_dns(node: str | None = None) -> dict:
    """Get the DNS configuration of a PVE node (read)."""
    cfg, api, _, _ = _svc()
    return _audited("pve_node_dns", node or cfg.node, lambda: node_dns_get(api, node))


@mcp.tool()
def pve_node_subscription(node: str | None = None) -> dict:
    """Get the subscription status of a PVE node (read)."""
    cfg, api, _, _ = _svc()
    return _audited("pve_node_subscription", node or cfg.node,
                    lambda: node_subscription(api, node))


@mcp.tool()
def pve_node_certificates(node: str | None = None) -> list[dict]:
    """List TLS certificates configured on a PVE node (read)."""
    cfg, api, _, _ = _svc()
    return _audited("pve_node_certificates", node or cfg.node,
                    lambda: node_certificates_info(api, node))


# --- Observability (mutation) ---

@mcp.tool()
def pve_node_service_control(service: str, action: str, node: str | None = None,
                             confirm: bool = False) -> dict:
    """MUTATION: start/stop/restart/reload a service on a PVE node. Dry-run by default — the
    PLAN flags lockout-class services (sshd/pveproxy/pvedaemon/pve-cluster/corosync/networking/
    ...) as HIGH because stop/restart can sever the management plane or break quorum. There is
    NO auto-undo for a service control. confirm=True to execute. Async — returns a task UPID.
    """
    cfg, api, _, _ = _svc()
    tgt = f"{node or cfg.node}/services/{service}:{action}"
    plan = _plan("pve_node_service_control", tgt,
                 lambda: plan_node_service_control(service, action, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_service_control", tgt,
                    lambda: node_service_control(api, service, action, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


# --- Task control + resource pools (read) ---

@mcp.tool()
def pve_tasks_list(node: str | None = None, limit: int = 50, errors: bool = False,
                   vmid: str | None = None, typefilter: str | None = None,
                   statusfilter: str | None = None) -> list[dict]:
    """List recent tasks on a node (read). limit 1-1000 (clamped)."""
    cfg, api, _, _ = _svc()
    return _audited("pve_tasks_list", node or cfg.node,
                    lambda: tasks_list(api, node, limit, errors, vmid, typefilter, statusfilter))


@mcp.tool()
def pve_task_log(upid: str, node: str | None = None, start: int = 0,
                 limit: int = 50) -> list[dict]:
    """Retrieve the log lines for a task (read)."""
    cfg, api, _, _ = _svc()
    return _audited("pve_task_log", upid, lambda: task_log(api, upid, node, start, limit))


@mcp.tool()
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
    _, api, _, _ = _svc()
    t = max(1, min(int(timeout), 600))
    iv = max(1, min(int(interval), 60))

    def _do() -> dict:
        r = wait_for_task(lambda: api.task_status(upid, node), timeout=t, interval=iv)
        r["upid"] = upid
        return r

    return _audited("pve_task_wait", upid, _do)


@mcp.tool()
def pve_pools_list() -> list[dict]:
    """List all resource pools (cluster-scoped) (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_pools_list", "cluster/pools", lambda: pools_list(api))


@mcp.tool()
def pve_pool_get(poolid: str) -> dict:
    """Get a resource pool's config and member list (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_pool_get", f"pool/{poolid}", lambda: pool_get(api, poolid))


# --- Task control + resource pools (mutation) ---

@mcp.tool()
def pve_task_stop(upid: str, node: str | None = None, confirm: bool = False) -> dict:
    """MUTATION (HIGH): stop (cancel) a running task. Dry-run by default — the PLAN warns that
    stopping a backup/restore/migration/clone mid-flight can leave the target inconsistent, with
    NO undo. confirm=True to execute. Synchronous cancellation signal (returns null)."""
    _, api, _, _ = _svc()
    plan = _plan("pve_task_stop", upid, lambda: plan_task_stop(upid, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_task_stop", upid,
                    lambda: task_stop(api, upid, node),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_pool_create(poolid: str, comment: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create an (empty) resource pool. Dry-run by default (PLAN = additive, LOW).
    confirm=True to execute. Synchronous."""
    _, api, _, _ = _svc()
    tgt = f"pool/{poolid}"
    plan = _plan("pve_pool_create", tgt, lambda: plan_pool_create(poolid, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_pool_create", tgt,
                    lambda: pool_create(api, poolid, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_pool_update(poolid: str, vms: str | None = None, storage: str | None = None,
                    delete: bool = False, confirm: bool = False) -> dict:
    """MUTATION: add (delete=False) or remove (delete=True) pool members. Dry-run by default —
    the PLAN notes membership re-scopes ACL coverage. confirm=True to execute. Synchronous.
    delete=True with no vms/storage is refused (ambiguous)."""
    _, api, _, _ = _svc()
    tgt = f"pool/{poolid}"
    plan = _plan("pve_pool_update", tgt,
                 lambda: plan_pool_update(poolid, vms, storage, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_pool_update", tgt,
                    lambda: pool_update(api, poolid, vms, storage, delete),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_pool_delete(poolid: str, confirm: bool = False) -> dict:
    """MUTATION: delete a resource pool. Dry-run by default — the PLAN warns ACLs on /pool/{poolid}
    are orphaned and the pool must be empty first (members are NOT deleted). confirm=True to
    execute. Synchronous."""
    _, api, _, _ = _svc()
    tgt = f"pool/{poolid}"
    plan = _plan("pve_pool_delete", tgt, lambda: plan_pool_delete(api, poolid))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_pool_delete", tgt,
                    lambda: pool_delete(api, poolid),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- PBS (Proxmox Backup Server) deep (read) ---

@mcp.tool()
def pbs_datastores_list() -> list[dict]:
    """List all datastores on the PBS server (read). Needs PROXIMO_PBS_* config."""
    _, pbs = _pbs()
    return _audited("pbs_datastores_list", "pbs/datastores",
                    lambda: pbs_datastore_list_op(pbs))


@mcp.tool()
def pbs_datastore_status(store: str) -> dict:
    """Get usage statistics for a PBS datastore (read)."""
    _, pbs = _pbs()
    return _audited("pbs_datastore_status", f"pbs/{store}",
                    lambda: pbs_datastore_status_op(pbs, store))


@mcp.tool()
def pbs_gc_status(store: str) -> dict:
    """Get garbage-collection status for a PBS datastore (read)."""
    _, pbs = _pbs()
    return _audited("pbs_gc_status", f"pbs/{store}/gc", lambda: pbs_gc_status_op(pbs, store))


@mcp.tool()
def pbs_snapshots_list(store: str, ns: str | None = None, backup_type: str | None = None,
                       backup_id: str | None = None) -> list[dict]:
    """List backup snapshots in a PBS datastore, with optional filters (read)."""
    _, pbs = _pbs()
    return _audited("pbs_snapshots_list", f"pbs/{store}",
                    lambda: pbs_snapshots_list_op(pbs, store, ns, backup_type, backup_id))


@mcp.tool()
def pbs_namespaces_list(store: str, parent: str | None = None,
                        max_depth: int | None = None) -> list[dict]:
    """List namespaces within a PBS datastore (read)."""
    _, pbs = _pbs()
    return _audited("pbs_namespaces_list", f"pbs/{store}",
                    lambda: pbs_namespace_list_op(pbs, store, parent, max_depth))


@mcp.tool()
def pbs_remotes_list() -> list[dict]:
    """List all PBS remote sync-sources (read). Passwords are never returned by the PBS API.
    Needs PROXIMO_PBS_* config."""
    _, pbs = _pbs()
    return _audited("pbs_remotes_list", "pbs/config/remote",
                    lambda: pbs_cfg_remotes_list(pbs))


@mcp.tool()
def pbs_remote_get(name: str) -> dict:
    """Get the config of one PBS remote sync-source by name (read). No password returned.
    Needs PROXIMO_PBS_* config."""
    _, pbs = _pbs()
    return _audited("pbs_remote_get", f"pbs/config/remote/{name}",
                    lambda: pbs_cfg_remote_get(pbs, name))


@mcp.tool()
def pbs_traffic_controls_list() -> list[dict]:
    """List all PBS traffic-control bandwidth rules (read). Needs PROXIMO_PBS_* config."""
    _, pbs = _pbs()
    return _audited("pbs_traffic_controls_list", "pbs/config/traffic-control",
                    lambda: pbs_cfg_traffic_controls_list(pbs))


@mcp.tool()
def pbs_jobs_list(job_type: str) -> list[dict]:
    """List all PBS scheduled jobs of the given type (read). job_type = sync|verify|prune.
    Returns all jobs with their configs. Raises on invalid job_type. Needs PROXIMO_PBS_* config."""
    _, pbs = _pbs()
    return _audited("pbs_jobs_list", f"pbs/config/{job_type}",
                    lambda: pbs_scheduled_jobs_list(pbs, job_type))


@mcp.tool()
def pbs_tasks_list(node: str = "localhost", limit: int | None = None,
                   running: bool | None = None, errors: bool | None = None) -> list[dict]:
    """List PBS tasks on a node (read). Defaults to 'localhost' (standard single-node PBS name).
    Optionally filter: running=True for active tasks, errors=True for failed tasks.
    Needs PROXIMO_PBS_* config."""
    _, pbs = _pbs()
    return _audited("pbs_tasks_list", f"pbs/nodes/{node}/tasks",
                    lambda: pbs_tasks_list_op(pbs, node, limit, running, errors))


@mcp.tool()
def pbs_datastore_get(name: str) -> dict:
    """Get full config of one PBS datastore by name (read). Returns path, gc-schedule, etc.
    For runtime usage stats use pbs_datastore_status instead. Needs PROXIMO_PBS_* config."""
    _, pbs = _pbs()
    return _audited("pbs_datastore_get", f"pbs/config/datastore/{name}",
                    lambda: pbs_cfg_datastore_get(pbs, name))


# --- PBS deep (mutation) ---

@mcp.tool()
def pbs_gc_start(store: str, confirm: bool = False) -> dict:
    """MUTATION (HIGH): start garbage collection on a PBS datastore. Dry-run by default — GC
    permanently removes unreferenced chunks (no undo). confirm=True to execute. Async — UPID."""
    _, pbs = _pbs()
    tgt = f"pbs/{store}/gc"
    plan = _plan("pbs_gc_start", tgt, lambda: pbs_plan_gc_start(store))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_gc_start", tgt, lambda: pbs_gc_start_op(pbs, store),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pbs_verify_start(store: str, ns: str | None = None, backup_type: str | None = None,
                     backup_id: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: start an integrity verification run on a PBS datastore. Dry-run by default —
    non-destructive (read-only check) but heavy I/O. confirm=True to execute. Async — UPID."""
    _, pbs = _pbs()
    tgt = f"pbs/{store}/verify"
    plan = _plan("pbs_verify_start", tgt,
                 lambda: pbs_plan_verify_start(store, ns, backup_type, backup_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_verify_start", tgt,
                    lambda: pbs_verify_start_op(pbs, store, ns, backup_type, backup_id),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pbs_prune(store: str, keep_last: int | None = None, keep_daily: int | None = None,
              keep_weekly: int | None = None, keep_monthly: int | None = None,
              keep_yearly: int | None = None, ns: str | None = None,
              backup_type: str | None = None, backup_id: str | None = None,
              dry_run: bool = True, confirm: bool = False) -> dict:
    """MUTATION: prune backup snapshots per a retention policy. TWO safety gates: confirm
    (Proximo dry-run vs execute) AND dry_run (PBS-side preview). dry_run=True (default) only
    previews; dry_run=False DELETES recovery points (PLAN is HIGH, no undo). confirm=True to
    execute. Synchronous — returns prune decisions."""
    _, pbs = _pbs()
    tgt = f"pbs/{store}/prune"
    plan = _plan("pbs_prune", tgt,
                 lambda: pbs_plan_prune(store, keep_last, keep_daily, keep_weekly,
                                        keep_monthly, keep_yearly, ns, backup_type,
                                        backup_id, dry_run))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_prune", tgt,
                    lambda: pbs_prune_op(pbs, store, keep_last, keep_daily,
                                        keep_weekly, keep_monthly, keep_yearly,
                                        ns, backup_type, backup_id, dry_run),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "dry_run": dry_run})


@mcp.tool()
def pbs_snapshot_delete(store: str, backup_type: str, backup_id: str, backup_time: int,
                        ns: str | None = None, confirm: bool = False) -> dict:
    """MUTATION (HIGH): delete a specific backup snapshot (a recovery point) from a PBS
    datastore. Dry-run by default. Permanent — no undo. confirm=True to execute. Synchronous."""
    _, pbs = _pbs()
    tgt = f"pbs/{store}/{backup_type}/{backup_id}"
    plan = _plan("pbs_snapshot_delete", tgt,
                 lambda: pbs_plan_snapshot_delete(store, backup_type, backup_id, backup_time, ns))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_snapshot_delete", tgt,
                    lambda: pbs_snapshot_delete_op(pbs, store, backup_type, backup_id, backup_time, ns),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pbs_namespace_create(store: str, name: str, parent: str | None = None,
                         confirm: bool = False) -> dict:
    """MUTATION: create a namespace within a PBS datastore. Dry-run by default (additive, LOW).
    confirm=True to execute. Synchronous."""
    _, pbs = _pbs()
    tgt = f"pbs/{store}/namespace/{name}"
    plan = _plan("pbs_namespace_create", tgt,
                 lambda: pbs_plan_namespace_create(store, name, parent))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_namespace_create", tgt,
                    lambda: pbs_namespace_create_op(pbs, store, name, parent),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pbs_namespace_delete(store: str, ns: str, delete_groups: bool = False,
                         confirm: bool = False) -> dict:
    """MUTATION: delete a namespace from a PBS datastore. Dry-run by default — delete_groups=True
    is HIGH (it deletes all backup groups/snapshots inside the namespace, no undo). confirm=True
    to execute. Synchronous."""
    _, pbs = _pbs()
    tgt = f"pbs/{store}/namespace/{ns}"
    plan = _plan("pbs_namespace_delete", tgt,
                 lambda: pbs_plan_namespace_delete(store, ns, delete_groups))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_namespace_delete", tgt,
                    lambda: pbs_namespace_delete_op(pbs, store, ns, delete_groups),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- PBS config + safety plane (Wave 5) ---

@mcp.tool()
def pbs_datastore_create(
    name: str,
    path: str,
    gc_schedule: str | None = None,
    prune_schedule: str | None = None,
    notification_mode: str | None = None,
    comment: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): create a new PBS datastore at the given path.

    Dry-run by default — additive, but a misconfigured path can conflict with existing storage.
    PBS datastore creation is an async worker task (UPID) → outcome='submitted' (not 'ok').
    No rollback primitive. confirm=True to execute.

    POST /config/datastore
    Smoke-confirm: gc-schedule / prune-schedule / notification-mode param names; sync-vs-async.
    """
    _, pbs = _pbs()
    tgt = f"pbs/datastore/{name}"
    plan = _plan("pbs_datastore_create", tgt,
                 lambda: pbs_plan_datastore_create(
                     name, path, gc_schedule=gc_schedule,
                     prune_schedule=prune_schedule,
                     notification_mode=notification_mode, comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_datastore_create", tgt,
                    lambda: pbs_cfg_datastore_create(
                        pbs, name, path, gc_schedule=gc_schedule,
                        prune_schedule=prune_schedule,
                        notification_mode=notification_mode, comment=comment),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pbs_datastore_update(
    name: str,
    gc_schedule: str | None = None,
    prune_schedule: str | None = None,
    notification_mode: str | None = None,
    comment: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): update PBS datastore configuration. Dry-run by default.

    CAPTURE: reads current config before planning; on read failure the plan is marked incomplete.
    Changing gc-schedule / prune-schedule affects data retention cluster-wide.
    No rollback primitive — revert by re-applying the captured config. confirm=True to execute.

    PUT /config/datastore/{name}
    Smoke-confirm: accepted param names (hyphenated vs underscored).
    """
    _, pbs = _pbs()
    tgt = f"pbs/datastore/{name}"
    plan = _plan("pbs_datastore_update", tgt,
                 lambda: pbs_plan_datastore_update(
                     pbs, name, gc_schedule=gc_schedule,
                     prune_schedule=prune_schedule,
                     notification_mode=notification_mode, comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_datastore_update", tgt,
                    lambda: pbs_cfg_datastore_update(
                        pbs, name, gc_schedule=gc_schedule,
                        prune_schedule=prune_schedule,
                        notification_mode=notification_mode, comment=comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pbs_datastore_delete(
    name: str,
    destroy_data: bool = False,
    keep_job_configs: bool = False,
    confirm: bool = False,
) -> dict:
    """MUTATION: delete a PBS datastore. Dry-run by default. RISK IS CONDITIONAL:

    destroy_data=False (default) → MEDIUM: detaches the datastore config; backup CHUNKS
      REMAIN ON DISK and the datastore is re-addable to recover.
    destroy_data=True → HIGH, IRREVERSIBLE: PERMANENTLY DESTROYS ALL backup data in the
      named datastore — no recovery possible.

    PBS deletion is an async worker task (UPID) → outcome='submitted'. confirm=True to execute.

    DELETE /config/datastore/{name}
    Smoke-confirm: destroy-data / keep-job-configs param names; sync-vs-async.
    """
    _, pbs = _pbs()
    tgt = f"pbs/datastore/{name}"
    plan = _plan("pbs_datastore_delete", tgt,
                 lambda: pbs_plan_datastore_delete(
                     name, destroy_data=destroy_data, keep_job_configs=keep_job_configs))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_datastore_delete", tgt,
                    lambda: pbs_cfg_datastore_delete(
                        pbs, name, destroy_data=destroy_data,
                        keep_job_configs=keep_job_configs),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pbs_snapshot_protected_set(
    store: str,
    backup_type: str,
    backup_id: str,
    backup_time: int,
    protected: bool,
    ns: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: set or clear the protected flag on a PBS snapshot. RISK IS CONDITIONAL:

    protected=True  → LOW:  shields the snapshot from pruning and GC (protective).
    protected=False → HIGH: SILENTLY re-enables pruning/GC — this recovery point can now
      be auto-deleted by the next prune job or GC run. No undo once auto-deleted.

    No PBS snapshot primitive for rollback. Dry-run by default. confirm=True to execute.

    PUT /admin/datastore/{store}/protected
    Smoke-confirm: exact path + param names (backup-type, backup-id, backup-time, protected).
    """
    _, pbs = _pbs()
    tgt = f"pbs/{store}/{backup_type}/{backup_id}@{backup_time}/protected"
    plan = _plan("pbs_snapshot_protected_set", tgt,
                 lambda: pbs_plan_snapshot_protected_set(
                     store, backup_type, backup_id, backup_time, protected, ns))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_snapshot_protected_set", tgt,
                    lambda: pbs_cfg_snapshot_protected_set(
                        pbs, store, backup_type, backup_id, backup_time, protected, ns),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pbs_snapshot_notes_set(
    store: str,
    backup_type: str,
    backup_id: str,
    backup_time: int,
    notes: str,
    ns: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (LOW): annotate a PBS snapshot with notes. Dry-run by default.

    CAPTURE: reads current notes before planning; on failure the plan is marked incomplete.
    Does not affect backup data, retention, or protection.
    No PBS snapshot primitive — revert by re-applying the captured notes. confirm=True to execute.

    PUT /admin/datastore/{store}/notes
    Smoke-confirm: exact endpoint path + param names (backup-type, backup-id, backup-time).
    """
    _, pbs = _pbs()
    tgt = f"pbs/{store}/{backup_type}/{backup_id}@{backup_time}/notes"
    plan = _plan("pbs_snapshot_notes_set", tgt,
                 lambda: pbs_plan_snapshot_notes_set(
                     pbs, store, backup_type, backup_id, backup_time, notes, ns))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_snapshot_notes_set", tgt,
                    lambda: pbs_cfg_snapshot_notes_set(
                        pbs, store, backup_type, backup_id, backup_time, notes, ns),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pbs_group_change_owner(
    store: str,
    backup_type: str,
    backup_id: str,
    new_owner: str,
    ns: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): reassign the owner of a PBS backup group. Dry-run by default.

    The new owner controls deletion and prune of this backup group.
    The previous owner loses those permissions immediately.
    No PBS snapshot primitive — revert by re-assigning the owner back. confirm=True to execute.

    PUT /admin/datastore/{store}/change-owner
    Smoke-confirm: exact path + new-owner vs owner param name.
    """
    _, pbs = _pbs()
    tgt = f"pbs/{store}/{backup_type}/{backup_id}/owner"
    plan = _plan("pbs_group_change_owner", tgt,
                 lambda: pbs_plan_group_change_owner(
                     store, backup_type, backup_id, new_owner, ns))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_group_change_owner", tgt,
                    lambda: pbs_cfg_group_change_owner(
                        pbs, store, backup_type, backup_id, new_owner, ns),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pbs_remote_create(
    name: str,
    host: str,
    auth_id: str,
    password: str,
    fingerprint: str | None = None,
    port: int | None = None,
    comment: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): create a PBS remote sync-source. Dry-run by default.

    PRIVATE PASSWORD REDACTION: 'password' is a remote user credential. It is
    UNCONDITIONALLY redacted — NEVER appears in the plan, change, current state, detail,
    or audit ledger. Only {"password":"[redacted]"} is recorded.
    The TLS cert 'fingerprint' is PUBLIC data — it is NOT redacted.

    No rollback primitive — revert by deleting the remote (pbs_remote_delete). confirm=True to execute.

    POST /config/remote
    Smoke-confirm: auth-id vs authid param name; port param name.
    """
    _, pbs = _pbs()
    tgt = f"pbs/remote/{name}"
    # UNCONDITIONAL: password never passes through the plan factory or into the ledger.
    pw_detail = _remote_password_fingerprint()
    plan = _plan("pbs_remote_create", tgt,
                 lambda: pbs_plan_remote_create(
                     name, host, auth_id, fingerprint=fingerprint,
                     port=port, comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict(), **pw_detail}
    return _audited("pbs_remote_create", tgt,
                    lambda: pbs_cfg_remote_create(
                        pbs, name, host, auth_id, password,
                        fingerprint=fingerprint, port=port, comment=comment),
                    mutation=True, outcome="ok",
                    detail={**pw_detail, "confirmed": True})


@mcp.tool()
def pbs_remote_update(
    name: str,
    host: str | None = None,
    auth_id: str | None = None,
    password: str | None = None,
    fingerprint: str | None = None,
    port: int | None = None,
    comment: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): update an existing PBS remote. Dry-run by default.

    CAPTURE: reads current (non-secret) config before planning; on failure plan is marked incomplete.
    PRIVATE PASSWORD REDACTION: if 'password' is provided it is UNCONDITIONALLY redacted.
    The TLS cert 'fingerprint' is PUBLIC and appears in plans/logs for audit.
    No rollback primitive — revert by re-applying captured config. confirm=True to execute.

    PUT /config/remote/{name}
    Smoke-confirm: auth-id param name; whether partial PUT is accepted.
    """
    _, pbs = _pbs()
    tgt = f"pbs/remote/{name}"
    # UNCONDITIONAL if password provided: never into plan factory or ledger.
    pw_detail = _remote_password_fingerprint() if password is not None else {}
    plan = _plan("pbs_remote_update", tgt,
                 lambda: pbs_plan_remote_update(
                     pbs, name, host=host, auth_id=auth_id,
                     fingerprint=fingerprint, port=port, comment=comment))
    if not confirm:
        resp = {"status": "plan", **plan.as_dict()}
        if pw_detail:
            resp.update(pw_detail)
        return resp
    return _audited("pbs_remote_update", tgt,
                    lambda: pbs_cfg_remote_update(
                        pbs, name, host=host, auth_id=auth_id,
                        password=password, fingerprint=fingerprint,
                        port=port, comment=comment),
                    mutation=True, outcome="ok",
                    detail={**pw_detail, "confirmed": True})


@mcp.tool()
def pbs_remote_delete(
    name: str,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): remove a PBS remote and its stored credentials. Dry-run by default.

    After deletion: any sync jobs referencing this remote break; re-add needs the password
    re-supplied. No rollback primitive — re-create with pbs_remote_create to recover.
    confirm=True to execute.

    DELETE /config/remote/{name}
    Smoke-confirm: response shape on success.
    """
    _, pbs = _pbs()
    tgt = f"pbs/remote/{name}"
    plan = _plan("pbs_remote_delete", tgt,
                 lambda: pbs_plan_remote_delete(name))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_remote_delete", tgt,
                    lambda: pbs_cfg_remote_delete(pbs, name),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pbs_traffic_control_upsert(
    name: str,
    rate_in: int | None = None,
    rate_out: int | None = None,
    network: str | None = None,
    burst_in: int | None = None,
    burst_out: int | None = None,
    timeframe: str | None = None,
    comment: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: create or update a PBS traffic-control (bandwidth-limit) rule. Dry-run by default.

    Detects create-vs-update by reading the existing rule config (CAPTURE on update path):
      create → LOW:    additive, no existing rule changed.
      update → MEDIUM: changing rate limits can throttle backups or saturate the network.

    A too-low rate-in or rate-out throttles PBS backups to a crawl.
    No rollback primitive. confirm=True to execute.

    POST (create) or PUT (update) /config/traffic-control[/{name}]
    Smoke-confirm: create-vs-update dispatch; rate-in/rate-out/burst-in/burst-out/timeframe param names.
    """
    _, pbs = _pbs()
    tgt = f"pbs/traffic-control/{name}"
    plan = _plan("pbs_traffic_control_upsert", tgt,
                 lambda: pbs_plan_traffic_control_upsert(
                     pbs, name, rate_in=rate_in, rate_out=rate_out, network=network,
                     burst_in=burst_in, burst_out=burst_out, timeframe=timeframe,
                     comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_traffic_control_upsert", tgt,
                    lambda: pbs_cfg_traffic_control_upsert(
                        pbs, name, rate_in=rate_in, rate_out=rate_out, network=network,
                        burst_in=burst_in, burst_out=burst_out, timeframe=timeframe,
                        comment=comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pbs_traffic_control_delete(
    name: str,
    confirm: bool = False,
) -> dict:
    """MUTATION (LOW): remove a PBS traffic-control (bandwidth-limit) rule. Dry-run by default.

    After deletion: backups run unthrottled on the matched network.
    Recoverable by re-creating the rule with pbs_traffic_control_upsert. confirm=True to execute.

    DELETE /config/traffic-control/{name}
    Smoke-confirm: response shape on success.
    """
    _, pbs = _pbs()
    tgt = f"pbs/traffic-control/{name}"
    plan = _plan("pbs_traffic_control_delete", tgt,
                 lambda: pbs_plan_traffic_control_delete(name))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_traffic_control_delete", tgt,
                    lambda: pbs_cfg_traffic_control_delete(pbs, name),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- Storage administration (storage.cfg CRUD) ---

@mcp.tool()
def pve_storage_config_list() -> list[dict]:
    """List the cluster storage definitions (storage.cfg) (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_storage_config_list", "cluster/storage",
                    lambda: storage_config_list(api))


@mcp.tool()
def pve_storage_config_get(storage: str) -> dict:
    """Get one storage definition (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_storage_config_get", f"storage/{storage}",
                    lambda: storage_config_get(api, storage))


@mcp.tool()
def pve_storage_create(storage: str, storage_type: str, content: str | None = None,
                       path: str | None = None, server: str | None = None,
                       export: str | None = None, nodes: str | None = None,
                       disable: bool = False, shared: bool = False,
                       confirm: bool = False) -> dict:
    """MUTATION: define a new storage (storage.cfg). Dry-run by default. confirm=True to execute."""
    _, api, _, _ = _svc()
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


@mcp.tool()
def pve_storage_update(storage: str, content: str | None = None, nodes: str | None = None,
                       disable: bool | None = None, shared: bool | None = None,
                       delete: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: update a storage definition. Dry-run by default (disable=True warns guests lose
    disk access). confirm=True to execute."""
    _, api, _, _ = _svc()
    tgt = f"storage/{storage}"
    plan = _plan("pve_storage_update", tgt,
                 lambda: plan_storage_update(api, storage, content, nodes, disable, shared, delete))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_storage_update", tgt,
                    lambda: storage_update(api, storage, content, nodes, disable, shared, delete),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_storage_delete(storage: str, confirm: bool = False) -> dict:
    """MUTATION (HIGH): remove a storage definition cluster-wide. Dry-run by default — the PLAN
    warns guest disks/backups living only there become inaccessible (data not erased). confirm=True."""
    _, api, _, _ = _svc()
    tgt = f"storage/{storage}"
    plan = _plan("pve_storage_delete", tgt, lambda: plan_storage_delete(api, storage))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_storage_delete", tgt,
                    lambda: storage_delete(api, storage),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- Access governance: users & groups ---

@mcp.tool()
def pve_user_get(userid: str) -> dict:
    """Get a user's config, groups, and tokens (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_user_get", f"user/{userid}", lambda: user_get(api, userid))


@mcp.tool()
def pve_groups_list() -> list[dict]:
    """List all groups (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_groups_list", "access/groups", lambda: groups_list(api))


@mcp.tool()
def pve_group_get(groupid: str) -> dict:
    """Get a group's config and members (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_group_get", f"group/{groupid}", lambda: group_get(api, groupid))


@mcp.tool()
def pve_user_create(userid: str, comment: str | None = None, email: str | None = None,
                    enable: bool | None = None, expire: int | None = None,
                    groups: str | None = None, firstname: str | None = None,
                    lastname: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create a user. Dry-run by default (note: password is set separately — the user
    cannot log in until then). confirm=True to execute."""
    _, api, _, _ = _svc()
    tgt = f"user/{userid}"
    plan = _plan("pve_user_create", tgt,
                 lambda: plan_user_create(userid, comment, email, enable, expire, groups,
                                          firstname, lastname))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_user_create", tgt,
                    lambda: user_create(api, userid, comment, email, enable, expire,
                                       groups, firstname, lastname),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_user_update(userid: str, comment: str | None = None, email: str | None = None,
                    enable: bool | None = None, expire: int | None = None,
                    groups: str | None = None, firstname: str | None = None,
                    lastname: str | None = None, append: bool | None = None,
                    confirm: bool = False) -> dict:
    """MUTATION: update a user (enable=False stops login; group changes re-scope access).
    Dry-run by default. confirm=True to execute."""
    _, api, _, _ = _svc()
    tgt = f"user/{userid}"
    plan = _plan("pve_user_update", tgt,
                 lambda: plan_user_update(userid, comment, email, enable, expire, groups,
                                          firstname, lastname, append))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_user_update", tgt,
                    lambda: user_update(api, userid, comment, email, enable, expire,
                                       groups, firstname, lastname, append),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_user_delete(userid: str, confirm: bool = False) -> dict:
    """MUTATION (HIGH): delete a user. Dry-run by default — the PLAN reads the user's ACLs/tokens
    to show what access vanishes (permanent, no undo; admin = lockout risk). confirm=True."""
    _, api, _, _ = _svc()
    tgt = f"user/{userid}"
    plan = _plan("pve_user_delete", tgt, lambda: plan_user_delete(api, userid))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_user_delete", tgt,
                    lambda: user_delete(api, userid),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_group_create(groupid: str, comment: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create an (empty) group. Dry-run by default (additive, LOW). confirm=True."""
    _, api, _, _ = _svc()
    tgt = f"group/{groupid}"
    plan = _plan("pve_group_create", tgt, lambda: plan_group_create(groupid, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_group_create", tgt,
                    lambda: group_create(api, groupid, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_group_update(groupid: str, comment: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: update a group's comment. Dry-run by default. confirm=True."""
    _, api, _, _ = _svc()
    tgt = f"group/{groupid}"
    plan = _plan("pve_group_update", tgt, lambda: plan_group_update(groupid, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_group_update", tgt,
                    lambda: group_update(api, groupid, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_group_delete(groupid: str, confirm: bool = False) -> dict:
    """MUTATION (HIGH): delete a group. Dry-run by default — the PLAN reads members and warns ACLs
    granted to/on the group are orphaned. confirm=True."""
    _, api, _, _ = _svc()
    tgt = f"group/{groupid}"
    plan = _plan("pve_group_delete", tgt, lambda: plan_group_delete(api, groupid))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_group_delete", tgt,
                    lambda: group_delete(api, groupid),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- Access governance: roles, realms, TFA ---

@mcp.tool()
def pve_realms_list() -> list[dict]:
    """List authentication realms/domains (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_realms_list", "access/domains", lambda: realms_list(api))


@mcp.tool()
def pve_realm_get(realm: str) -> dict:
    """Get a realm's config (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_realm_get", f"realm/{realm}", lambda: realm_get(api, realm))


@mcp.tool()
def pve_tfa_list() -> list[dict]:
    """List per-user TFA (two-factor) entries across the cluster (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_tfa_list", "access/tfa", lambda: tfa_list(api))


@mcp.tool()
def pve_tfa_get(userid: str, tfa_id: str | None = None) -> object:
    """Read a user's TFA entries, or one entry (read). GET /access/tfa/{userid}[/{tfa_id}]."""
    _, api, _, _ = _svc()
    return _audited("pve_tfa_get", f"access/tfa/{userid}", lambda: tfa_get(api, userid, tfa_id))


@mcp.tool()
def pve_tfa_delete(
    userid: str, tfa_id: str, password: str | None = None, confirm: bool = False,
) -> dict:
    """MUTATION (HIGH RISK): delete a user's TFA factor. Dry-run by default — the PLAN shows how many
    factors remain and warns this WEAKENS the account (and can lock the user out if it's the last
    factor on a TFA-required realm). `password` (if PVE requires it) is passed through but never
    logged. confirm=True to execute.

    NOTE (live-verified PVE 9.1.7): PVE requires a ticket-based login session — NOT an API token —
    to mutate TFA, returning `403 ... need proper ticket` under token auth. Proximo is token-authed,
    so this delete will 403 on PVE; the read tools (pve_tfa_get/pve_tfa_list) work normally.
    """
    _, api, _, _ = _svc()
    tgt = f"access/tfa/{userid}/{tfa_id}"
    plan = _plan("pve_tfa_delete", tgt, lambda: plan_tfa_delete(api, userid, tfa_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_tfa_delete", tgt,
                    lambda: tfa_delete(api, userid, tfa_id, password),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_role_create(roleid: str, privs: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create a custom role. Dry-run by default. confirm=True to execute."""
    _, api, _, _ = _svc()
    tgt = f"role/{roleid}"
    plan = _plan("pve_role_create", tgt, lambda: plan_role_create(roleid, privs))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_role_create", tgt,
                    lambda: role_create(api, roleid, privs),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_role_update(roleid: str, privs: str | None = None, append: bool | None = None,
                    confirm: bool = False) -> dict:
    """MUTATION: change a role's privileges. Dry-run by default — built-in roles (Administrator,
    PVEAdmin, …) are flagged HIGH (changing them re-scopes every ACL using them). confirm=True."""
    _, api, _, _ = _svc()
    tgt = f"role/{roleid}"
    plan = _plan("pve_role_update", tgt, lambda: plan_role_update(api, roleid, privs, append))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_role_update", tgt,
                    lambda: role_update(api, roleid, privs, append),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_role_delete(roleid: str, confirm: bool = False) -> dict:
    """MUTATION (HIGH): delete a role. Dry-run by default — the PLAN reads ACLs to count grants
    that will break, and refuses built-in roles. confirm=True."""
    _, api, _, _ = _svc()
    tgt = f"role/{roleid}"
    plan = _plan("pve_role_delete", tgt, lambda: plan_role_delete(api, roleid))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_role_delete", tgt,
                    lambda: role_delete(api, roleid),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_realm_create(realm: str, realm_type: str, comment: str | None = None,
                     options: dict | None = None, confirm: bool = False) -> dict:
    """MUTATION: create an auth realm. Dry-run by default; confirm=True to execute.
    `options` carries the type-specific fields PVE requires (ldap: server1/base_dn/user_attr;
    ad: domain/server1; openid: issuer-url/client-id) — passed verbatim; PVE validates them."""
    _, api, _, _ = _svc()
    tgt = f"realm/{realm}"
    plan = _plan("pve_realm_create", tgt,
                 lambda: plan_realm_create(realm, realm_type, comment, options))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_realm_create", tgt,
                    lambda: realm_create(api, realm, realm_type, comment, options),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_realm_update(realm: str, comment: str | None = None,
                     options: dict | None = None, confirm: bool = False) -> dict:
    """MUTATION: update a realm. Dry-run by default — built-in pam/pve realms are flagged HIGH
    (changing them risks breaking logins). confirm=True. `options` carries type-specific fields
    (server1/base_dn/etc.) passed verbatim; PVE validates them."""
    _, api, _, _ = _svc()
    tgt = f"realm/{realm}"
    plan = _plan("pve_realm_update", tgt, lambda: plan_realm_update(api, realm, comment, options))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_realm_update", tgt,
                    lambda: realm_update(api, realm, comment, options),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_realm_delete(realm: str, confirm: bool = False) -> dict:
    """MUTATION (HIGH, lockout-class): delete an auth realm. Dry-run by default — the PLAN reads
    users to count who can no longer log in, and refuses built-in pam/pve. confirm=True."""
    _, api, _, _ = _svc()
    tgt = f"realm/{realm}"
    plan = _plan("pve_realm_delete", tgt, lambda: plan_realm_delete(api, realm))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_realm_delete", tgt,
                    lambda: realm_delete(api, realm),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# --- Backup Schedules (Plane B) — PVE backup jobs, replication, PBS scheduled jobs ---

@mcp.tool()
def pve_backup_job_list() -> dict:
    """List all PVE cluster backup jobs and guests not covered by any job (read).
    Returns {jobs: [...], unprotected_guests: [...]}."""
    _, api, _, _ = _svc()
    return _audited("pve_backup_job_list", "cluster/backup",
                    lambda: backup_job_list(api))


@mcp.tool()
def pve_backup_job_create(job_id: str, schedule: str, storage: str,
                          mode: str | None = None, compress: str | None = None,
                          vmid: str | None = None, enabled: bool | None = None,
                          comment: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create a PVE cluster backup job. Dry-run by default — shows the plan.
    confirm=True to execute. Config-only; existing backups are NOT affected."""
    _, api, _, _ = _svc()
    tgt = f"cluster/backup/{job_id}"
    plan = _plan("pve_backup_job_create", tgt,
                 lambda: plan_backup_job_create(job_id, schedule, storage,
                                                mode=mode, compress=compress,
                                                vmid=vmid, enabled=enabled,
                                                comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_backup_job_create", tgt,
                    lambda: backup_job_create(api, job_id, schedule, storage,
                                             mode=mode, compress=compress,
                                             vmid=vmid, enabled=enabled, comment=comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_backup_job_update(job_id: str, schedule: str | None = None,
                          storage: str | None = None, mode: str | None = None,
                          compress: str | None = None, vmid: str | None = None,
                          enabled: bool | None = None, comment: str | None = None,
                          confirm: bool = False) -> dict:
    """MUTATION: update a PVE cluster backup job. Dry-run by default — captures current config.
    confirm=True to execute. Config-only; no impact on existing backups."""
    _, api, _, _ = _svc()
    tgt = f"cluster/backup/{job_id}"
    plan = _plan("pve_backup_job_update", tgt,
                 lambda: plan_backup_job_update(api, job_id, schedule=schedule,
                                                storage=storage, mode=mode,
                                                compress=compress, vmid=vmid,
                                                enabled=enabled, comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_backup_job_update", tgt,
                    lambda: backup_job_update(api, job_id, schedule=schedule,
                                             storage=storage, mode=mode, compress=compress,
                                             vmid=vmid, enabled=enabled, comment=comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_backup_job_delete(job_id: str, confirm: bool = False) -> dict:
    """MUTATION: delete a PVE cluster backup job. Dry-run by default — captures current config.
    confirm=True to execute. Schedule removed; existing backups are NOT deleted."""
    _, api, _, _ = _svc()
    tgt = f"cluster/backup/{job_id}"
    plan = _plan("pve_backup_job_delete", tgt,
                 lambda: plan_backup_job_delete(api, job_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_backup_job_delete", tgt,
                    lambda: backup_job_delete(api, job_id),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_replication_create(rep_id: str, rep_type: str, target: str,
                           schedule: str | None = None, rate: float | None = None,
                           disable: bool | None = None, comment: str | None = None,
                           confirm: bool = False) -> dict:
    """MUTATION: create a PVE replication job. Dry-run by default.
    rep_type is typically 'local'. confirm=True to execute."""
    _, api, _, _ = _svc()
    tgt = f"cluster/replication/{rep_id}"
    plan = _plan("pve_replication_create", tgt,
                 lambda: plan_replication_create(rep_id, rep_type, target,
                                                 schedule=schedule, rate=rate,
                                                 disable=disable, comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_replication_create", tgt,
                    lambda: replication_create(api, rep_id, rep_type, target,
                                              schedule=schedule, rate=rate,
                                              disable=disable, comment=comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_replication_update(rep_id: str, schedule: str | None = None,
                           rate: float | None = None, disable: bool | None = None,
                           comment: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: update a PVE replication job. Dry-run by default — captures current config.
    confirm=True to execute. Config-only; in-flight replication is not immediately disrupted."""
    _, api, _, _ = _svc()
    tgt = f"cluster/replication/{rep_id}"
    plan = _plan("pve_replication_update", tgt,
                 lambda: plan_replication_update(api, rep_id, schedule=schedule,
                                                 rate=rate, disable=disable,
                                                 comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_replication_update", tgt,
                    lambda: replication_update(api, rep_id, schedule=schedule,
                                              rate=rate, disable=disable, comment=comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_replication_delete(rep_id: str, confirm: bool = False) -> dict:
    """MUTATION: delete a PVE replication job. Dry-run by default — captures current config.
    confirm=True to execute. Replication ceases; existing replicated data is NOT removed."""
    _, api, _, _ = _svc()
    tgt = f"cluster/replication/{rep_id}"
    plan = _plan("pve_replication_delete", tgt,
                 lambda: plan_replication_delete(api, rep_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_replication_delete", tgt,
                    lambda: replication_delete(api, rep_id),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pbs_job_create(job_type: str, job_id: str, store: str | None = None,
                   schedule: str | None = None, ns: str | None = None,
                   comment: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create a PBS scheduled job. job_type = sync|verify|prune. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PBS_* config. Config-only; no existing data affected."""
    _, pbs = _pbs()
    tgt = f"pbs/config/{job_type}/{job_id}"
    plan = _plan("pbs_job_create", tgt,
                 lambda: plan_pbs_job_create(job_type, job_id, store=store,
                                             schedule=schedule, ns=ns, comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_job_create", tgt,
                    lambda: pbs_scheduled_job_create(pbs, job_type, job_id, store=store,
                                                     schedule=schedule, ns=ns,
                                                     comment=comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pbs_job_update(job_type: str, job_id: str, schedule: str | None = None,
                   ns: str | None = None, comment: str | None = None,
                   confirm: bool = False) -> dict:
    """MUTATION: update a PBS scheduled job. job_type = sync|verify|prune. Dry-run by default —
    captures current config. confirm=True to execute. Needs PROXIMO_PBS_* config."""
    _, pbs = _pbs()
    tgt = f"pbs/config/{job_type}/{job_id}"
    plan = _plan("pbs_job_update", tgt,
                 lambda: plan_pbs_job_update(pbs, job_type, job_id, schedule=schedule,
                                             ns=ns, comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_job_update", tgt,
                    lambda: pbs_scheduled_job_update(pbs, job_type, job_id,
                                                     schedule=schedule, ns=ns,
                                                     comment=comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pbs_job_delete(job_type: str, job_id: str, confirm: bool = False) -> dict:
    """MUTATION: delete a PBS scheduled job. job_type = sync|verify|prune. Dry-run by default —
    captures current config. confirm=True to execute. Schedule removed; backup data NOT deleted.
    Needs PROXIMO_PBS_* config."""
    _, pbs = _pbs()
    tgt = f"pbs/config/{job_type}/{job_id}"
    plan = _plan("pbs_job_delete", tgt,
                 lambda: plan_pbs_job_delete(pbs, job_type, job_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_job_delete", tgt,
                    lambda: pbs_scheduled_job_delete(pbs, job_type, job_id),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pbs_job_run(job_type: str, job_id: str, confirm: bool = False) -> dict:
    """MUTATION: trigger a PBS scheduled job immediately. job_type = sync|verify|prune.
    Dry-run by default. confirm=True to execute. Async — returns UPID.
    Needs PROXIMO_PBS_* config. Prune runs may delete snapshots per the retention policy."""
    _, pbs = _pbs()
    tgt = f"pbs/admin/{job_type}/{job_id}"
    plan = _plan("pbs_job_run", tgt,
                 lambda: plan_pbs_job_run(job_type, job_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_job_run", tgt,
                    lambda: pbs_scheduled_job_run(pbs, job_type, job_id),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


@mcp.tool()
def pbs_realm_sync(realm: str, remove_vanished: bool | None = None,
                   dry_run: bool | None = None, scope: str | None = None,
                   confirm: bool = False) -> dict:
    """MUTATION: sync PBS auth realm (LDAP/AD) users. Dry-run by default.
    confirm=True to execute. Async — returns UPID. Needs PROXIMO_PBS_* config.
    remove_vanished=True also removes PBS users no longer in the directory."""
    _, pbs = _pbs()
    tgt = f"pbs/access/domains/{realm}"
    plan = _plan("pbs_realm_sync", tgt,
                 lambda: plan_pbs_realm_sync(realm,
                                             remove_vanished=remove_vanished,
                                             dry_run=dry_run, scope=scope))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pbs_realm_sync", tgt,
                    lambda: pbs_realm_sync_op(pbs, realm,
                                              remove_vanished=remove_vanished,
                                              dry_run=dry_run, scope=scope),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


# --- Notifications & Metrics (Plane E) — PVE notification endpoints, matchers, metrics ---

@mcp.tool()
def pve_notification_endpoint_list() -> list[dict]:
    """List all PVE notification endpoints (gotify/smtp/sendmail/webhook) (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_notification_endpoint_list", "cluster/notifications/endpoints",
                    lambda: notification_endpoint_list(api))


@mcp.tool()
def pve_notification_endpoint_create(ep_type: str, name: str,
                                     comment: str | None = None,
                                     options: dict | None = None,
                                     confirm: bool = False) -> dict:
    """MUTATION: create a PVE notification endpoint. ep_type = gotify|smtp|sendmail|webhook.
    Dry-run by default. confirm=True to execute. `options` carries the endpoint-specific config
    (sendmail: {"mailto-user":"root@pam"}; gotify: {"server":..,"token":..}; webhook: {"url":..})."""
    _, api, _, _ = _svc()
    tgt = f"cluster/notifications/endpoints/{ep_type}/{name}"
    plan = _plan("pve_notification_endpoint_create", tgt,
                 lambda: plan_notification_endpoint_create(ep_type, name, comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_notification_endpoint_create", tgt,
                    lambda: notification_endpoint_create(api, ep_type, name,
                                                         **{"comment": comment, **(options or {})}),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_notification_endpoint_update(ep_type: str, name: str,
                                     comment: str | None = None,
                                     options: dict | None = None,
                                     confirm: bool = False) -> dict:
    """MUTATION: update a PVE notification endpoint. ep_type = gotify|smtp|sendmail|webhook.
    Dry-run by default — captures current config. confirm=True to execute. `options` carries the
    endpoint-specific fields to change (same shape as create)."""
    _, api, _, _ = _svc()
    tgt = f"cluster/notifications/endpoints/{ep_type}/{name}"
    plan = _plan("pve_notification_endpoint_update", tgt,
                 lambda: plan_notification_endpoint_update(api, ep_type, name,
                                                           comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_notification_endpoint_update", tgt,
                    lambda: notification_endpoint_update(api, ep_type, name,
                                                         **{"comment": comment, **(options or {})}),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_notification_endpoint_delete(ep_type: str, name: str, confirm: bool = False) -> dict:
    """MUTATION: delete a PVE notification endpoint. ep_type = gotify|smtp|sendmail|webhook.
    Dry-run by default — captures current config. confirm=True to execute.
    WARN: matchers referencing this endpoint will silently fail until it is restored."""
    _, api, _, _ = _svc()
    tgt = f"cluster/notifications/endpoints/{ep_type}/{name}"
    plan = _plan("pve_notification_endpoint_delete", tgt,
                 lambda: plan_notification_endpoint_delete(api, ep_type, name))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_notification_endpoint_delete", tgt,
                    lambda: notification_endpoint_delete(api, ep_type, name),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_notification_matcher_set(name: str, comment: str | None = None,
                                 confirm: bool = False) -> dict:
    """MUTATION: create-or-update a PVE notification matcher (alert routing rule).
    Dry-run by default. confirm=True to execute."""
    _, api, _, _ = _svc()
    tgt = f"cluster/notifications/matchers/{name}"
    plan = _plan("pve_notification_matcher_set", tgt,
                 lambda: plan_notification_matcher_set(name, comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_notification_matcher_set", tgt,
                    lambda: notification_matcher_set(api, name, comment=comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_notification_matcher_delete(name: str, confirm: bool = False) -> dict:
    """MUTATION: delete a PVE notification matcher. Dry-run by default.
    confirm=True to execute. WARN: alerts matching this filter go un-routed after deletion."""
    _, api, _, _ = _svc()
    tgt = f"cluster/notifications/matchers/{name}"
    plan = _plan("pve_notification_matcher_delete", tgt,
                 lambda: plan_notification_matcher_delete(name))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_notification_matcher_delete", tgt,
                    lambda: notification_matcher_delete(api, name),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_notification_test(name: str, confirm: bool = False) -> dict:
    """MUTATION: send a test notification to a PVE notification target. Dry-run by default.
    confirm=True to execute. SENDS A REAL NOTIFICATION — recipients will receive it."""
    _, api, _, _ = _svc()
    tgt = f"cluster/notifications/targets/{name}"
    plan = _plan("pve_notification_test", tgt,
                 lambda: plan_notification_test(name))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_notification_test", tgt,
                    lambda: notification_test_op(api, name),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_metrics_server_list() -> list[dict]:
    """List all PVE metrics server definitions (influxdb, graphite, etc.) (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_metrics_server_list", "cluster/metrics/server",
                    lambda: metrics_server_list(api))


@mcp.tool()
def pve_metrics_server_set(metrics_id: str, metrics_type: str | None = None,
                           server: str | None = None, port: int | None = None,
                           disable: bool | None = None, comment: str | None = None,
                           confirm: bool = False) -> dict:
    """MUTATION: create-or-update a PVE metrics server definition. Dry-run by default.
    confirm=True to execute. Config-only; metrics forwarding adjusts to new settings."""
    _, api, _, _ = _svc()
    tgt = f"cluster/metrics/server/{metrics_id}"
    plan = _plan("pve_metrics_server_set", tgt,
                 lambda: plan_metrics_server_set(metrics_id, type=metrics_type,
                                                 server=server, port=port,
                                                 disable=disable, comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_metrics_server_set", tgt,
                    lambda: metrics_server_set(api, metrics_id, type=metrics_type,
                                              server=server, port=port,
                                              disable=disable, comment=comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_metrics_server_delete(metrics_id: str, confirm: bool = False) -> dict:
    """MUTATION: delete a PVE metrics server definition. Dry-run by default.
    confirm=True to execute. Metrics forwarding to this server ceases; no data loss."""
    _, api, _, _ = _svc()
    tgt = f"cluster/metrics/server/{metrics_id}"
    plan = _plan("pve_metrics_server_delete", tgt,
                 lambda: plan_metrics_server_delete(metrics_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_metrics_server_delete", tgt,
                    lambda: metrics_server_delete(api, metrics_id),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# ============================================================================
# Plane F — Hardware PCI/USB Mappings
# ============================================================================

@mcp.tool()
def pve_hardware_list(node: str, hw_type: str = "pci") -> dict:
    """List physical PCI or USB devices on a PVE node (read).
    hw_type: 'pci' (default) or 'usb'."""
    _, api, _, _ = _svc()
    return _audited("pve_hardware_list", f"nodes/{node}/hardware/{hw_type}",
                    lambda: hardware_list(api, node, hw_type))


@mcp.tool()
def pve_mapping_pci_list() -> list[dict]:
    """List all PCI cluster hardware mappings (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_mapping_pci_list", "cluster/mapping/pci",
                    lambda: mapping_pci_list(api))


@mcp.tool()
def pve_mapping_usb_list() -> list[dict]:
    """List all USB cluster hardware mappings (read)."""
    _, api, _, _ = _svc()
    return _audited("pve_mapping_usb_list", "cluster/mapping/usb",
                    lambda: mapping_usb_list(api))


@mcp.tool()
def pve_mapping_pci_create(mapping_id: str, description: str | None = None,
                           map: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create a PCI cluster passthrough mapping. Dry-run by default.
    confirm=True to execute. Smoke-confirm: POST body shape (id in body) against a live PVE instance."""
    _, api, _, _ = _svc()
    tgt = f"cluster/mapping/pci/{mapping_id}"
    plan = _plan("pve_mapping_pci_create", tgt,
                 lambda: plan_mapping_pci_create(mapping_id, description=description, map=map))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_mapping_pci_create", tgt,
                    lambda: mapping_pci_create(api, mapping_id, description=description, map=map),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_mapping_pci_update(mapping_id: str, description: str | None = None,
                           map: str | None = None, digest: str | None = None,
                           confirm: bool = False) -> dict:
    """MUTATION: update a PCI cluster mapping. Dry-run by default.
    confirm=True to execute. Reads current config for plan honesty."""
    _, api, _, _ = _svc()
    tgt = f"cluster/mapping/pci/{mapping_id}"
    plan = _plan("pve_mapping_pci_update", tgt,
                 lambda: plan_mapping_pci_update(api, mapping_id,
                                                  description=description, map=map, digest=digest))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_mapping_pci_update", tgt,
                    lambda: mapping_pci_update(api, mapping_id,
                                               description=description, map=map, digest=digest),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_mapping_pci_delete(mapping_id: str, confirm: bool = False) -> dict:
    """MUTATION: delete a PCI cluster mapping. Dry-run by default.
    confirm=True to execute. VMs referencing this mapping lose the device path."""
    _, api, _, _ = _svc()
    tgt = f"cluster/mapping/pci/{mapping_id}"
    plan = _plan("pve_mapping_pci_delete", tgt,
                 lambda: plan_mapping_pci_delete(api, mapping_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_mapping_pci_delete", tgt,
                    lambda: mapping_pci_delete(api, mapping_id),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_mapping_usb_create(mapping_id: str, description: str | None = None,
                           map: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create a USB cluster passthrough mapping. Dry-run by default.
    confirm=True to execute. Smoke-confirm: POST body shape (id in body) against a live PVE instance."""
    _, api, _, _ = _svc()
    tgt = f"cluster/mapping/usb/{mapping_id}"
    plan = _plan("pve_mapping_usb_create", tgt,
                 lambda: plan_mapping_usb_create(mapping_id, description=description, map=map))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_mapping_usb_create", tgt,
                    lambda: mapping_usb_create(api, mapping_id, description=description, map=map),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_mapping_usb_update(mapping_id: str, description: str | None = None,
                           map: str | None = None, digest: str | None = None,
                           confirm: bool = False) -> dict:
    """MUTATION: update a USB cluster mapping. Dry-run by default.
    confirm=True to execute. Reads current config for plan honesty."""
    _, api, _, _ = _svc()
    tgt = f"cluster/mapping/usb/{mapping_id}"
    plan = _plan("pve_mapping_usb_update", tgt,
                 lambda: plan_mapping_usb_update(api, mapping_id,
                                                  description=description, map=map, digest=digest))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_mapping_usb_update", tgt,
                    lambda: mapping_usb_update(api, mapping_id,
                                               description=description, map=map, digest=digest),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_mapping_usb_delete(mapping_id: str, confirm: bool = False) -> dict:
    """MUTATION: delete a USB cluster mapping. Dry-run by default.
    confirm=True to execute. VMs referencing this mapping lose the USB device path."""
    _, api, _, _ = _svc()
    tgt = f"cluster/mapping/usb/{mapping_id}"
    plan = _plan("pve_mapping_usb_delete", tgt,
                 lambda: plan_mapping_usb_delete(api, mapping_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_mapping_usb_delete", tgt,
                    lambda: mapping_usb_delete(api, mapping_id),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# ============================================================================
# Plane G — ACME & TLS Certs
# ============================================================================

@mcp.tool()
def pve_acme_account_create(name: str, contact: str, tos_url: str | None = None,
                            directory: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: register a new ACME account with the CA. Dry-run by default.
    confirm=True to execute. Smoke-confirm: POST body shape (name in body) against a live PVE instance."""
    _, api, _, _ = _svc()
    tgt = f"cluster/acme/account/{name}"
    plan = _plan("pve_acme_account_create", tgt,
                 lambda: plan_acme_account_create(name, contact,
                                                   tos_url=tos_url, directory=directory))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_acme_account_create", tgt,
                    lambda: acme_account_create(api, name, contact,
                                                tos_url=tos_url, directory=directory),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_acme_account_update(name: str, contact: str | None = None,
                            confirm: bool = False) -> dict:
    """MUTATION: update ACME account contact info. Dry-run by default.
    confirm=True to execute. LOW risk — metadata update only, no cert impact."""
    _, api, _, _ = _svc()
    tgt = f"cluster/acme/account/{name}"
    plan = _plan("pve_acme_account_update", tgt,
                 lambda: plan_acme_account_update(api, name, contact=contact))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_acme_account_update", tgt,
                    lambda: acme_account_update(api, name, contact=contact),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_acme_account_delete(name: str, confirm: bool = False) -> dict:
    """MUTATION: IRREVERSIBLE — deactivate and delete an ACME account from the CA. Dry-run by default.
    confirm=True to execute. HIGH risk: TLS lockout at cert expiry if this is the only account."""
    _, api, _, _ = _svc()
    tgt = f"cluster/acme/account/{name}"
    plan = _plan("pve_acme_account_delete", tgt,
                 lambda: plan_acme_account_delete(api, name))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_acme_account_delete", tgt,
                    lambda: acme_account_delete(api, name),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_acme_plugin_create(plugin_id: str, plugin_type: str, dns_api: str | None = None,
                           data: str | None = None, disable: bool | None = None,
                           confirm: bool = False) -> dict:
    """MUTATION: create an ACME DNS challenge plugin. Dry-run by default.
    confirm=True to execute. dns_api = DNS provider name (e.g. 'cf', 'route53').
    Smoke-confirm: POST body shape (id in body) against a live PVE instance."""
    _, api, _, _ = _svc()
    tgt = f"cluster/acme/plugins/{plugin_id}"
    # dns_api maps to PVE's 'api' field (avoids name collision with the backend 'api' param)
    kw: dict = {}
    if dns_api is not None:
        kw["api"] = dns_api
    if data is not None:
        kw["data"] = data
    if disable is not None:
        kw["disable"] = disable
    plan = _plan("pve_acme_plugin_create", tgt,
                 lambda: plan_acme_plugin_create(plugin_id, plugin_type, **kw))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_acme_plugin_create", tgt,
                    lambda: acme_plugin_create(api, plugin_id, plugin_type, **kw),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_acme_plugin_update(plugin_id: str, dns_api: str | None = None,
                           data: str | None = None, disable: bool | None = None,
                           digest: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: update an ACME DNS challenge plugin. Dry-run by default.
    confirm=True to execute. MEDIUM risk — invalid credentials break renewal at next attempt."""
    _, api, _, _ = _svc()
    tgt = f"cluster/acme/plugins/{plugin_id}"
    # dns_api maps to PVE's 'api' field
    kw: dict = {}
    if dns_api is not None:
        kw["api"] = dns_api
    if data is not None:
        kw["data"] = data
    if disable is not None:
        kw["disable"] = disable
    if digest is not None:
        kw["digest"] = digest
    plan = _plan("pve_acme_plugin_update", tgt,
                 lambda: plan_acme_plugin_update(api, plugin_id, **kw))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_acme_plugin_update", tgt,
                    lambda: acme_plugin_update(api, plugin_id, **kw),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@mcp.tool()
def pve_acme_plugin_delete(plugin_id: str, confirm: bool = False) -> dict:
    """MUTATION: delete an ACME DNS challenge plugin. Dry-run by default.
    confirm=True to execute. HIGH risk: cert auto-renewal breaks — TLS lockout at cert expiry."""
    _, api, _, _ = _svc()
    tgt = f"cluster/acme/plugins/{plugin_id}"
    plan = _plan("pve_acme_plugin_delete", tgt,
                 lambda: plan_acme_plugin_delete(api, plugin_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_acme_plugin_delete", tgt,
                    lambda: acme_plugin_delete(api, plugin_id),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# ---------------------------------------------------------------------------
# qemu-agent plane (Wave 3) — in-guest ops via the QEMU Guest Agent
# ---------------------------------------------------------------------------

# Pace the exec-status poll loop so it never busy-waits the PVE API (mirrors _wait_task's sleep).
_AGENT_POLL_INTERVAL = 1.0


@mcp.tool()
def pve_agent_exec(
    vmid: str,
    command: list[str],
    node: str | None = None,
    timeout: int = 30,
    confirm: bool = False,
) -> dict:
    """MUTATION: run a command inside a guest via the qemu-agent (async, polls for result).

    Dry-run by default: without confirm=True you get a PLAN recorded to the ledger.
    Re-call with confirm=True to execute.

    Requires PROXIMO_ENABLE_AGENT=1 and the VMID in PROXIMO_AGENT_ALLOWLIST.
    The command runs INSIDE the guest OS — no undo primitive on this plane.

    Returns status="ok" only when the agent reports the process exited.
    Returns status="running" with pid when the poll deadline is reached before exit.
    """
    cfg, api, _, audit = _svc()
    if not cfg.enable_agent:
        return _agent_disabled("pve_agent_exec", f"qemu/{vmid}", mutation=True)
    if not cfg.agent_permitted(vmid):
        return _blocked_agent_allowlist("pve_agent_exec", f"qemu/{vmid}", mutation=True)

    # Ledger redaction parity with ct_exec: a guest exec argv can carry a secret (e.g. `mysql -pPW`).
    # When PROXIMO_LEDGER_REDACT is set, store a fingerprint instead of the argv — in BOTH the plan's
    # change line (via redact=) and the execute-path audit detail.
    detail = command_fingerprint(command) if cfg.redact_ledger else {"command": command}
    plan = _plan("pve_agent_exec", f"qemu/{vmid}",
                 lambda: plan_agent_exec(vmid, command, node, redact=cfg.redact_ledger))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}

    # Execute: POST exec, then poll exec-status until exited or deadline.
    # Manual audit path so we can record honest outcome ("ok" vs "running").
    try:
        exec_result = api.agent_exec(vmid, node, command)
        pid = exec_result.get("pid")
        if pid is None:
            raise ValueError("agent exec returned no pid")  # noqa: TRY301

        # VERIFIED live (PVE 9.2): exec-status returns exited/exitcode/out-data/err-data.
        deadline = time.monotonic() + timeout
        while True:
            status = api.agent_exec_status(vmid, node, pid)
            # 'exited' arrives as a JSON bool; accept int 1 too defensively, and NEVER treat a
            # falsy/missing value as completion (that would fake an "ok" for a still-running cmd).
            if status.get("exited") in (True, 1):
                # Process completed — honest "ok" outcome. out-data/err-data are plain text (not base64).
                out_data = status.get("out-data", "")
                err_data = status.get("err-data", "")
                result = {
                    "pid": pid,
                    "exitcode": status.get("exitcode"),
                    "out-data": out_data,
                    "err-data": err_data,
                }
                audit.record("pve_agent_exec", target=f"qemu/{vmid}", mutation=True,
                             outcome="ok", detail={**detail, "confirmed": True, "pid": pid})
                return {"status": "ok", "result": result}
            if time.monotonic() >= deadline:
                # Timeout BEFORE exit observed — honest "running" outcome, never "ok".
                audit.record("pve_agent_exec", target=f"qemu/{vmid}", mutation=True,
                             outcome="running",
                             detail={**detail, "confirmed": True, "pid": pid, "timeout": timeout})
                return {"status": "running", "pid": pid,
                        "message": f"command is still running (pid={pid}) — did not exit within {timeout}s; "
                                   "poll pve_agent_info with command='exec-status' and the returned pid."}
            time.sleep(_AGENT_POLL_INTERVAL)  # pace polls — do not hammer the PVE API
    except Exception as e:
        audit.record("pve_agent_exec", target=f"qemu/{vmid}", mutation=True,
                     outcome="error", detail={"error": type(e).__name__, "confirmed": True})
        raise


@mcp.tool()
def pve_agent_info(
    vmid: str,
    command: str = "info",
    pid: int | None = None,
    node: str | None = None,
) -> dict:
    """READ-ONLY: query the qemu-agent on a guest (ping, osinfo, hostname, users, exec-status, …).

    Requires PROXIMO_ENABLE_AGENT=1 and the VMID in PROXIMO_AGENT_ALLOWLIST.
    No confirm needed — read-only.

    command: one of ping, info, get-fsinfo, get-host-name, get-osinfo, get-time,
             get-timezone, get-users, get-vcpus, network-get-interfaces,
             get-memory-blocks, fsfreeze-status, exec-status.
    pid: required when command='exec-status' (the pid returned by pve_agent_exec).
    """
    cfg, api, _, _ = _svc()
    if not cfg.enable_agent:
        return _agent_disabled("pve_agent_info", f"qemu/{vmid}", mutation=False)
    if not cfg.agent_permitted(vmid):
        return _blocked_agent_allowlist("pve_agent_info", f"qemu/{vmid}", mutation=False)

    _check_agent_info_command(command)

    if command == "exec-status":
        if pid is None:
            raise ProximoError("exec-status requires pid")
        return _audited("pve_agent_info", f"qemu/{vmid}",
                        lambda: api.agent_exec_status(vmid, node, pid))
    return _audited("pve_agent_info", f"qemu/{vmid}",
                    lambda: api.agent_simple(vmid, node, command))


@mcp.tool()
def pve_agent_file_read(
    vmid: str,
    file: str,
    node: str | None = None,
) -> dict:
    """READ-ONLY: read a file from inside the guest via the qemu-agent.

    Requires PROXIMO_ENABLE_AGENT=1 and the VMID in PROXIMO_AGENT_ALLOWLIST.
    No confirm needed — read-only.  File path must be absolute.

    Ledger records only the file path (never the content); the returned dict carries content.
    Smoke-confirm: PVE file-read response shape is unverified.
    """
    cfg, api, _, _ = _svc()
    if not cfg.enable_agent:
        return _agent_disabled("pve_agent_file_read", f"qemu/{vmid}", mutation=False)
    if not cfg.agent_permitted(vmid):
        return _blocked_agent_allowlist("pve_agent_file_read", f"qemu/{vmid}", mutation=False)

    _check_file_path(file)
    return _audited("pve_agent_file_read", f"qemu/{vmid}",
                    lambda: api.agent_file_read(vmid, node, file),
                    detail={"file": file})


@mcp.tool()
def pve_agent_file_write(
    vmid: str,
    file: str,
    content: str,
    node: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: write a file inside the guest via the qemu-agent.

    Dry-run by default: without confirm=True you get a PLAN recorded to the ledger.
    Re-call with confirm=True to execute.

    Requires PROXIMO_ENABLE_AGENT=1 and the VMID in PROXIMO_AGENT_ALLOWLIST.
    File path must be absolute.  Content is UNCONDITIONALLY redacted from the ledger.
    No undo primitive on this plane.
    Smoke-confirm: PVE file-write endpoint and content encoding are unverified.
    """
    cfg, api, _, _ = _svc()
    if not cfg.enable_agent:
        return _agent_disabled("pve_agent_file_write", f"qemu/{vmid}", mutation=True)
    if not cfg.agent_permitted(vmid):
        return _blocked_agent_allowlist("pve_agent_file_write", f"qemu/{vmid}", mutation=True)

    # UNCONDITIONAL: content fingerprint only, never the body.
    detail = {"file": file, **_content_fingerprint(content)}
    plan = _plan("pve_agent_file_write", f"qemu/{vmid}:{file}",
                 lambda: plan_agent_file_write(vmid, file, content, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}

    return _audited("pve_agent_file_write", f"qemu/{vmid}:{file}",
                    lambda: api.agent_file_write(vmid, node, file, content),
                    mutation=True, outcome="ok", detail={**detail, "confirmed": True})


@mcp.tool()
def pve_agent_fs(
    vmid: str,
    command: str,
    node: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: fsfreeze-freeze, fsfreeze-thaw, or fstrim inside the guest via the qemu-agent.

    Dry-run by default: without confirm=True you get a PLAN recorded to the ledger.
    Re-call with confirm=True to execute.

    Requires PROXIMO_ENABLE_AGENT=1 and the VMID in PROXIMO_AGENT_ALLOWLIST.
    command: fsfreeze-freeze | fsfreeze-thaw | fstrim
    No undo primitive on this plane; always pair freeze with thaw.
    """
    cfg, api, _, _ = _svc()
    if not cfg.enable_agent:
        return _agent_disabled("pve_agent_fs", f"qemu/{vmid}", mutation=True)
    if not cfg.agent_permitted(vmid):
        return _blocked_agent_allowlist("pve_agent_fs", f"qemu/{vmid}", mutation=True)

    _check_agent_fs_command(command)
    plan = _plan("pve_agent_fs", f"qemu/{vmid}:{command}",
                 lambda: plan_agent_fs(vmid, command, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}

    return _audited("pve_agent_fs", f"qemu/{vmid}:{command}",
                    lambda: api.agent_simple(vmid, node, command),
                    mutation=True, outcome="ok",
                    detail={"command": command, "confirmed": True})


@mcp.tool()
def pve_agent_set_password(
    vmid: str,
    username: str,
    password: str,
    node: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: set a guest OS user's password via the qemu-agent.

    Dry-run by default: without confirm=True you get a PLAN recorded to the ledger.
    Re-call with confirm=True to execute.

    Requires PROXIMO_ENABLE_AGENT=1 and the VMID in PROXIMO_AGENT_ALLOWLIST.
    Password is UNCONDITIONALLY redacted from the ledger (fingerprint only — "[redacted]").
    No undo primitive on this plane.
    Smoke-confirm: PVE set-user-password endpoint and body fields are unverified.
    """
    cfg, api, _, _ = _svc()
    if not cfg.enable_agent:
        return _agent_disabled("pve_agent_set_password", f"qemu/{vmid}", mutation=True)
    if not cfg.agent_permitted(vmid):
        return _blocked_agent_allowlist("pve_agent_set_password", f"qemu/{vmid}", mutation=True)

    # UNCONDITIONAL: password redacted always, regardless of cfg.redact_ledger.
    detail = {"username": username, **_password_fingerprint()}
    plan = _plan("pve_agent_set_password", f"qemu/{vmid}:{username}",
                 lambda: plan_agent_set_password(vmid, username, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}

    return _audited("pve_agent_set_password", f"qemu/{vmid}:{username}",
                    lambda: api.agent_set_password(vmid, node, username, password),
                    mutation=True, outcome="ok", detail={**detail, "confirmed": True})


# --- node-lifecycle plane (Wave 4) ---

# --- Disks (reads) ---

@mcp.tool()
def pve_node_disks_list(node: str | None = None) -> list:
    """List physical disks on a PVE node (read).

    GET /nodes/{node}/disks/list — physical disk inventory and health info.
    Smoke-confirm: response shape not live-verified.
    """
    cfg, api, _, _ = _svc()
    return _audited("pve_node_disks_list", node or cfg.node,
                    lambda: api.node_disks_list(node))


@mcp.tool()
def pve_node_disk_smart(disk: str, node: str | None = None) -> dict:
    """Get SMART health data for a disk on a PVE node (read).

    GET /nodes/{node}/disks/smart?disk=… — SMART attributes and health status.
    Smoke-confirm: GET (read) only — this tool does NOT trigger a self-test.
    """
    cfg, api, _, _ = _svc()
    return _audited("pve_node_disk_smart", f"{node or cfg.node}:{disk}",
                    lambda: api.node_disk_smart(disk, node))


# --- Disks (mutations) ---

@mcp.tool()
def pve_node_disk_wipe(disk: str, node: str | None = None,
                       confirm: bool = False) -> dict:
    """MUTATION: wipe ALL data and the partition table on a node disk.

    RISK_HIGH, NO UNDO: DESTROYS all data, partitions, and filesystems on the named disk.
    This is irreversible — all data is permanently erased. confirm=True to execute.

    PUT /nodes/{node}/disks/wipedisk
    Smoke-confirm: endpoint and body shape not live-verified.
    """
    cfg, api, _, _ = _svc()
    tgt = f"{node or cfg.node}/disks/{disk}"
    plan = _plan("pve_node_disk_wipe", tgt,
                 lambda: plan_node_disk_wipe(disk, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    # Async (worker UPID) like the sibling disk/storage ops — record "submitted", not "ok": the
    # ledger must not claim the wipe finished when only the task was accepted.
    return _audited("pve_node_disk_wipe", tgt,
                    lambda: api.node_disk_wipe(disk, node),
                    mutation=True, outcome="submitted",
                    detail={"disk": disk, "confirmed": True})


@mcp.tool()
def pve_node_disk_initgpt(disk: str, node: str | None = None,
                          confirm: bool = False) -> dict:
    """MUTATION: initialize a GPT partition table on a node disk.

    RISK_HIGH: overwrites the existing partition table on the named disk; irreversible.
    confirm=True to execute.

    POST /nodes/{node}/disks/initgpt
    Smoke-confirm: endpoint and body shape not live-verified.
    """
    cfg, api, _, _ = _svc()
    tgt = f"{node or cfg.node}/disks/{disk}"
    plan = _plan("pve_node_disk_initgpt", tgt,
                 lambda: plan_node_disk_initgpt(disk, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_disk_initgpt", tgt,
                    lambda: api.node_disk_initgpt(disk, node),
                    mutation=True, outcome="submitted",
                    detail={"disk": disk, "confirmed": True})


# --- Storage backends (reads + mutations) ---

@mcp.tool()
def pve_node_storage_backend_list(backend: str, node: str | None = None) -> list:
    """List storage backends of a type on a PVE node (read).

    backend ∈ {lvm, lvmthin, zfs, directory}.
    GET /nodes/{node}/disks/{backend}
    Smoke-confirm: response shape not live-verified.
    """
    cfg, api, _, _ = _svc()
    return _audited("pve_node_storage_backend_list", f"{node or cfg.node}/disks/{backend}",
                    lambda: api.node_storage_backend_list(backend, node))


@mcp.tool()
def pve_node_storage_backend_create(
    backend: str,
    name: str,
    devices: str | None = None,
    node: str | None = None,
    confirm: bool = False,
    **kw: Any,
) -> dict:
    """MUTATION: create a storage backend on the node (lvm/lvmthin/zfs/directory).

    Per-backend required params:
      zfs:       devices (comma-sep disk list) + raidlevel
      lvm/lvmthin: devices (single disk)
      directory: devices (disk path) + filesystem (e.g. ext4)

    The named disk(s) are consumed by the new backend. confirm=True to execute.

    POST /nodes/{node}/disks/{backend}
    Smoke-confirm: endpoint and body shape not live-verified. May return a task UPID (async).
    """
    cfg, api, _, _ = _svc()
    tgt = f"{node or cfg.node}/disks/{backend}/{name}"
    plan = _plan("pve_node_storage_backend_create", tgt,
                 lambda: plan_node_storage_backend_create(backend, name, devices, node, **kw))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_storage_backend_create", tgt,
                    lambda: api.node_storage_backend_create(backend, name, node,
                                                            **({"devices": devices} if devices else {}),
                                                            **kw),
                    mutation=True, outcome="submitted",
                    detail={"backend": backend, "name": name, "confirmed": True})


@mcp.tool()
def pve_node_storage_backend_delete(
    backend: str,
    name: str,
    node: str | None = None,
    cleanup: bool = False,
    confirm: bool = False,
) -> dict:
    """MUTATION: destroy a storage backend on the node.

    RISK_HIGH, NO UNDO — backend-specific blast:
      zfs:        destroys the zpool and ALL data on it
      lvm/lvmthin: removes the VG — any storage built on it breaks
      directory:  removes the directory mapping (data on disk may persist)

    confirm=True to execute.

    DELETE /nodes/{node}/disks/{backend}/{name}
    Smoke-confirm: endpoint and params shape not live-verified.
    """
    cfg, api, _, _ = _svc()
    tgt = f"{node or cfg.node}/disks/{backend}/{name}"
    plan = _plan("pve_node_storage_backend_delete", tgt,
                 lambda: plan_node_storage_backend_delete(backend, name, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    # Async (worker UPID) like backend_create — record "submitted", not "ok".
    return _audited("pve_node_storage_backend_delete", tgt,
                    lambda: api.node_storage_backend_delete(backend, name, node, cleanup),
                    mutation=True, outcome="submitted",
                    detail={"backend": backend, "name": name, "confirmed": True})


# --- Node config (reads) ---

@mcp.tool()
def pve_node_time_get(node: str | None = None) -> dict:
    """Get the current time and timezone of a PVE node (read).

    GET /nodes/{node}/time — returns {localtime, time, timezone}.
    Smoke-confirm: response shape not live-verified.
    """
    cfg, api, _, _ = _svc()
    return _audited("pve_node_time_get", node or cfg.node,
                    lambda: api.node_time_get(node))


@mcp.tool()
def pve_node_hosts_get(node: str | None = None) -> dict:
    """Get the /etc/hosts content of a PVE node (read).

    GET /nodes/{node}/hosts — returns {data, digest}.
    Smoke-confirm: response shape not live-verified.
    """
    cfg, api, _, _ = _svc()
    return _audited("pve_node_hosts_get", node or cfg.node,
                    lambda: api.node_hosts_get(node))


# --- Node config (mutations) ---

@mcp.tool()
def pve_node_time_set(timezone: str, node: str | None = None,
                      confirm: bool = False) -> dict:
    """MUTATION: set the timezone on a PVE node.

    RISK_LOW. CAPTURE: reads the current timezone before planning; if unreadable → complete=False.
    Revert by re-applying the captured timezone. confirm=True to execute.

    PUT /nodes/{node}/time
    Smoke-confirm: endpoint and body shape not live-verified.
    """
    cfg, api, _, _ = _svc()
    tgt = f"{node or cfg.node}/time"
    plan = _plan("pve_node_time_set", tgt,
                 lambda: plan_node_time_set(api, timezone, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_time_set", tgt,
                    lambda: api.node_time_set(timezone, node),
                    mutation=True, outcome="ok",
                    detail={"timezone": timezone, "confirmed": True})


@mcp.tool()
def pve_node_hosts_set(
    data: str,
    node: str | None = None,
    digest: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: replace the /etc/hosts file on a PVE node.

    RISK_MEDIUM. CAPTURE: reads current /etc/hosts before planning (revert by re-applying captured
    content); if unreadable → complete=False. A bad /etc/hosts can break name resolution.
    confirm=True to execute.

    POST /nodes/{node}/hosts
    Smoke-confirm: endpoint and body shape not live-verified.
    """
    cfg, api, _, _ = _svc()
    tgt = f"{node or cfg.node}/hosts"
    plan = _plan("pve_node_hosts_set", tgt,
                 lambda: plan_node_hosts_set(api, data, node, digest))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_hosts_set", tgt,
                    lambda: api.node_hosts_set(data, node, digest),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True})


@mcp.tool()
def pve_node_dns_set(
    search: str | None = None,
    dns1: str | None = None,
    dns2: str | None = None,
    dns3: str | None = None,
    node: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: update DNS resolver configuration on a PVE node.

    RISK_LOW. CAPTURE: reads current DNS config before planning (reuse pve_node_dns read);
    if unreadable → complete=False. confirm=True to execute.

    PUT /nodes/{node}/dns
    Smoke-confirm: endpoint and body shape not live-verified.
    """
    cfg, api, _, _ = _svc()
    tgt = f"{node or cfg.node}/dns"
    plan = _plan("pve_node_dns_set", tgt,
                 lambda: plan_node_dns_set(api, search, dns1, dns2, dns3, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_dns_set", tgt,
                    lambda: api.node_dns_set(node, search, dns1, dns2, dns3),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True})


@mcp.tool()
def pve_node_cert_upload(
    certificates: str,
    key: str | None = None,
    node: str | None = None,
    force: bool = False,
    restart: bool = False,
    confirm: bool = False,
) -> dict:
    """MUTATION: upload a custom TLS certificate to a PVE node.

    RISK_HIGH, NO UNDO. A malformed cert/key can lock you out of the PVE web UI and API.
    restart=True reloads pveproxy after upload (brief service interruption).

    PRIVATE KEY REDACTION: the 'key' param is a TLS private key (secret). It is
    UNCONDITIONALLY redacted — it NEVER appears in the plan, change, current state,
    detail, or ledger (regardless of redact_ledger setting). Only {"key": "[redacted]"}
    is recorded. The cert body (certificates) is public and may appear in plans/logs.

    Revert: re-upload a correct cert, or use pve_node_cert_delete to revert to self-signed.
    confirm=True to execute.

    POST /nodes/{node}/certificates/custom
    Smoke-confirm: endpoint and body shape not live-verified.
    """
    cfg, api, _, _ = _svc()
    tgt = f"{node or cfg.node}/certificates/custom"

    # UNCONDITIONAL: key redacted always; never passes through plan factory or ledger.
    key_detail = _key_fingerprint()

    plan = _plan("pve_node_cert_upload", tgt,
                 lambda: plan_node_cert_upload(certificates, node, force, restart))
    if not confirm:
        # key_detail injected into return (but not into the Plan itself — plan factory has no key).
        return {"status": "plan", **plan.as_dict(), **key_detail}
    return _audited("pve_node_cert_upload", tgt,
                    lambda: api.node_cert_upload(certificates, node, key, force, restart),
                    mutation=True, outcome="ok",
                    detail={**key_detail, "confirmed": True})


@mcp.tool()
def pve_node_cert_delete(
    node: str | None = None,
    restart: bool = False,
    confirm: bool = False,
) -> dict:
    """MUTATION: delete the custom TLS certificate from a PVE node.

    RISK_MEDIUM: PVE reverts to its self-signed certificate (recoverable by re-uploading).
    restart=True reloads pveproxy after deletion. confirm=True to execute.

    DELETE /nodes/{node}/certificates/custom
    Smoke-confirm: endpoint and params shape not live-verified.
    """
    cfg, api, _, _ = _svc()
    tgt = f"{node or cfg.node}/certificates/custom"
    plan = _plan("pve_node_cert_delete", tgt,
                 lambda: plan_node_cert_delete(node, restart))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_cert_delete", tgt,
                    lambda: api.node_cert_delete(node, restart),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True})


# --- Bulk power (mutations) ---

@mcp.tool()
def pve_node_startall(
    node: str | None = None,
    vms: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: start all (or filtered) guests on a PVE node.

    RISK_MEDIUM. Reversible — the inverse of pve_node_stopall. vms = optional CSV of VMIDs
    to filter the scope. confirm=True to execute.

    POST /nodes/{node}/startall
    Smoke-confirm: endpoint and vms param format not live-verified. May return task UPID.
    """
    cfg, api, _, _ = _svc()
    tgt = f"{node or cfg.node}/startall"
    plan = _plan("pve_node_startall", tgt,
                 lambda: plan_node_startall(node, vms))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_startall", tgt,
                    lambda: api.node_startall(node, vms),
                    mutation=True, outcome="submitted",
                    detail={"confirmed": True, **({"vms": vms} if vms else {})})


@mcp.tool()
def pve_node_stopall(
    node: str | None = None,
    vms: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: stop ALL (or filtered) running guests on a PVE node.

    RISK_HIGH — fleet-wide service outage unless vms filters the scope.
    Reversible via pve_node_startall, but guests must be restarted inside. confirm=True to execute.

    POST /nodes/{node}/stopall
    Smoke-confirm: endpoint and vms param format not live-verified. May return task UPID.
    """
    cfg, api, _, _ = _svc()
    tgt = f"{node or cfg.node}/stopall"
    plan = _plan("pve_node_stopall", tgt,
                 lambda: plan_node_stopall(node, vms))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_stopall", tgt,
                    lambda: api.node_stopall(node, vms),
                    mutation=True, outcome="submitted",
                    detail={"confirmed": True, **({"vms": vms} if vms else {})})


@mcp.tool()
def pve_node_migrateall(
    target: str,
    node: str | None = None,
    vms: str | None = None,
    maxworkers: int | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: migrate all (or filtered) guests from a node to a target node.

    RISK_HIGH, NOT auto-reversible: reversal requires a second pve_node_migrateall back,
    which may not restore the original state. target = destination node name (required).
    confirm=True to execute.

    POST /nodes/{node}/migrateall
    Smoke-confirm: endpoint and body shape not live-verified. May return task UPID.
    """
    cfg, api, _, _ = _svc()
    tgt = f"{node or cfg.node}/migrateall->{target}"
    plan = _plan("pve_node_migrateall", tgt,
                 lambda: plan_node_migrateall(target, node, vms, maxworkers))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_migrateall", tgt,
                    lambda: api.node_migrateall(target, node, vms, maxworkers),
                    mutation=True, outcome="submitted",
                    detail={"target": target, "confirmed": True})


# --- PMG (Proxmox Mail Gateway) ---

@mcp.tool()
def pmg_doctor(node: str | None = None) -> dict:
    """PMG connectivity + credential/permission preflight (read). Checks /nodes/{node}/version
    and /access/users. A successful /version call means ticket login also succeeded —
    connectivity and credentials are proven together. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified: PMG has no /access/permissions endpoint (that is PVE-only);
    /access/users is the closest equivalent and returns the same user/role information.
    """
    cfg, pmg = _pmg()
    n = node or cfg.node
    return _audited("pmg_doctor", f"pmg/{n}",
                    lambda: {
                        "version": pmg_node_version_op(pmg, n),
                        "permissions": pmg_access_permissions_op(pmg),
                    })


@mcp.tool()
def pmg_node_status(node: str | None = None) -> dict:
    """Get PMG node cpu/mem/disk/uptime status (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified: /nodes/{node}/status path and response shape confirmed via
    pmg-smoke.py W1 round-trip (node_status PASS).
    """
    cfg, pmg = _pmg()
    n = node or cfg.node
    return _audited("pmg_node_status", f"pmg/{n}/status",
                    lambda: pmg_node_status_op(pmg, n))


@mcp.tool()
def pmg_relay_config() -> dict:
    """Get PMG SMTP relay/smarthost configuration (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified: relay/smarthost settings live at /config/mail (not /config/relay).
    """
    _, pmg = _pmg()
    return _audited("pmg_relay_config", "pmg/config/mail",
                    lambda: pmg_relay_config_op(pmg))


@mcp.tool()
def pmg_domains_list() -> list[dict]:
    """List PMG managed mail domains (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified: /config/domains path and response shape confirmed via
    pmg-smoke.py W1 round-trip and W3 full domain create/list/delete cycle.
    """
    _, pmg = _pmg()
    return _audited("pmg_domains_list", "pmg/config/domains",
                    lambda: pmg_domains_list_op(pmg))


@mcp.tool()
def pmg_statistics_mail() -> dict:
    """Get PMG mail delivery statistics (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified: /statistics/mail returns today's aggregate counters
    (count_in, count_out, spam, virus, bytes, …). Always returns today's totals;
    for time-ranged data use pmg_statistics_mailcount instead.
    """
    _, pmg = _pmg()
    return _audited("pmg_statistics_mail", "pmg/statistics/mail",
                    lambda: pmg_statistics_mail_op(pmg))


@mcp.tool()
def pmg_quarantine_spam() -> list[dict]:
    """List PMG quarantined spam messages (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified: endpoint is /quarantine/spam (not /quarantine/mails).
    For virus quarantine use pmg_quarantine_virus; for attachment use pmg_quarantine_attachment.
    To act on quarantined messages (deliver/delete/mark-seen/blocklist/welcomelist) use
    pmg_quarantine_action.
    """
    _, pmg = _pmg()
    return _audited("pmg_quarantine_spam", "pmg/quarantine/spam",
                    lambda: pmg_quarantine_spam_op(pmg))


@mcp.tool()
def pmg_statistics_domains(start: int | None = None, end: int | None = None) -> list[dict]:
    """Get PMG per-domain mail statistics (read). Optional Unix epoch start/end timespan.
    Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: /statistics/domains.
    Maps start/end params → starttime/endtime query params.
    """
    _, pmg = _pmg()
    return _audited("pmg_statistics_domains", "pmg/statistics/domains",
                    lambda: pmg_statistics_domains_op(pmg, start, end))


@mcp.tool()
def pmg_statistics_virus(start: int | None = None, end: int | None = None) -> list[dict]:
    """Get PMG virus statistics (read). Optional Unix epoch start/end timespan.
    Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: /statistics/virus.
    Maps start/end params → starttime/endtime query params.
    """
    _, pmg = _pmg()
    return _audited("pmg_statistics_virus", "pmg/statistics/virus",
                    lambda: pmg_statistics_virus_op(pmg, start, end))


@mcp.tool()
def pmg_statistics_spamscores(start: int | None = None, end: int | None = None) -> list[dict]:
    """Get PMG spam score distribution statistics (read). Optional Unix epoch start/end timespan.
    Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: /statistics/spamscores.
    Maps start/end params → starttime/endtime query params.
    """
    _, pmg = _pmg()
    return _audited("pmg_statistics_spamscores", "pmg/statistics/spamscores",
                    lambda: pmg_statistics_spamscores_op(pmg, start, end))


@mcp.tool()
def pmg_statistics_recent(hours: int = 1) -> list[dict]:
    """Get PMG recent mail statistics (read). hours: 1-24 window. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: /statistics/recent.
    """
    _, pmg = _pmg()
    return _audited("pmg_statistics_recent", "pmg/statistics/recent",
                    lambda: pmg_statistics_recent_op(pmg, hours))


@mcp.tool()
def pmg_quarantine_blocklist_list(pmail: str | None = None) -> list[dict]:
    """List PMG quarantine blocklist entries (read). Optional pmail to scope to one user.
    Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: /quarantine/blocklist.
    pmail is passed to the API only if provided.
    """
    _, pmg = _pmg()
    return _audited("pmg_quarantine_blocklist_list", "pmg/quarantine/blocklist",
                    lambda: pmg_quarantine_blocklist_list_op(pmg, pmail))


@mcp.tool()
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
    _, pmg = _pmg()
    tgt = "pmg/quarantine/blocklist"
    plan = _plan("pmg_quarantine_blocklist_add", tgt,
                 lambda: pmg_plan_quarantine_blocklist_add(address, pmail))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_quarantine_blocklist_add", tgt,
                    lambda: pmg_quarantine_blocklist_add_op(pmg, address, pmail),
                    mutation=True, outcome="ok", detail={"confirmed": True, "address": address})


@mcp.tool()
def pmg_quarantine_action(
    action: str,
    mail_ids: str,
    confirm: bool = False,
) -> dict:
    """MUTATION (MEDIUM): apply an action to quarantined message(s). Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    action: one of deliver|delete|mark-seen|mark-unseen|blocklist|welcomelist.
    mail_ids: single mail ID or comma-separated list.
    PMG 9.1 live-proven 2026-06-26: POST /quarantine/content — delete and deliver
    both confirmed against real quarantined GTUBE messages.
    """
    _, pmg = _pmg()
    tgt = "pmg/quarantine/content"
    plan = _plan("pmg_quarantine_action", tgt,
                 lambda: pmg_plan_quarantine_action(action, mail_ids))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_quarantine_action", tgt,
                    lambda: pmg_quarantine_action_op(pmg, action, mail_ids),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "action": action, "mail_ids": mail_ids})


@mcp.tool()
def pmg_postfix_qshape(node: str | None = None) -> list[dict]:
    """Get PMG Postfix queue shape (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified: /nodes/{node}/postfix/qshape returns a list of
    dicts (one row per domain + a TOTAL row with queue-age bucket counts).
    """
    cfg, pmg = _pmg()
    n = node or cfg.node
    return _audited("pmg_postfix_qshape", f"pmg/{n}/postfix/qshape",
                    lambda: pmg_postfix_qshape_op(pmg, n))


@mcp.tool()
def pmg_postfix_flush(node: str | None = None, confirm: bool = False) -> dict:
    """MUTATION (LOW): flush all Postfix queues (immediate re-delivery attempt). Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: POST /nodes/{node}/postfix/flush_queues.
    """
    cfg, pmg = _pmg()
    n = node or cfg.node
    tgt = f"pmg/{n}/postfix/flush_queues"
    plan = _plan("pmg_postfix_flush", tgt,
                 lambda: pmg_plan_postfix_flush(n))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_postfix_flush", tgt,
                    lambda: pmg_postfix_flush_op(pmg, n),
                    mutation=True, outcome="ok", detail={"confirmed": True, "node": n})


@mcp.tool()
def pmg_spam_config() -> dict:
    """Get PMG spam filter configuration (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: /config/spam.
    """
    _, pmg = _pmg()
    return _audited("pmg_spam_config", "pmg/config/spam",
                    lambda: pmg_spam_config_op(pmg))


@mcp.tool()
def pmg_service_status(service: str, node: str | None = None) -> dict:
    """Get the status of a PMG system service (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: /nodes/{node}/services/{service}/state.
    service: e.g. 'postfix', 'pmgproxy', 'pmgdaemon', 'pmgmirror', 'pmgtunnel',
             'pmg-smtp-filter', 'clamav', 'spamassassin'. No hardcoded enum —
             pass any valid service name; unknown names return a PMG 404.
    """
    cfg, pmg = _pmg()
    n = node or cfg.node
    return _audited("pmg_service_status", f"pmg/{n}/services/{service}",
                    lambda: pmg_service_status_op(pmg, service, n))


@mcp.tool()
def pmg_domain_create(domain: str, comment: str | None = None, confirm: bool = False) -> dict:
    """MUTATION (LOW): create a managed mail domain. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: POST /config/domains.
    domain: domain name to add (e.g. 'example.com').
    """
    _, pmg = _pmg()
    tgt = "pmg/config/domains"
    plan = _plan("pmg_domain_create", tgt,
                 lambda: pmg_plan_domain_create(domain, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_domain_create", tgt,
                    lambda: pmg_domain_create_op(pmg, domain, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True, "domain": domain})


@mcp.tool()
def pmg_domain_delete(domain: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): delete a managed mail domain. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: DELETE /config/domains/{domain}.
    Mail routing rules referencing this domain may break — review before confirming.
    """
    _, pmg = _pmg()
    tgt = f"pmg/config/domains/{domain}"
    plan = _plan("pmg_domain_delete", tgt,
                 lambda: pmg_plan_domain_delete(domain))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_domain_delete", tgt,
                    lambda: pmg_domain_delete_op(pmg, domain),
                    mutation=True, outcome="ok", detail={"confirmed": True, "domain": domain})


@mcp.tool()
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
    _, pmg = _pmg()
    tgt = "pmg/config/transport"
    plan = _plan("pmg_transport_create", tgt,
                 lambda: pmg_plan_transport_create(domain, host, comment, port, protocol, use_mx))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_transport_create", tgt,
                    lambda: pmg_transport_create_op(pmg, domain, host, comment, port, protocol, use_mx),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "domain": domain, "host": host})


@mcp.tool()
def pmg_transport_delete(domain: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): delete a mail transport rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: DELETE /config/transport/{domain}.
    Mail for the domain will fall back to default PMG routing (MX lookup).
    """
    _, pmg = _pmg()
    tgt = f"pmg/config/transport/{domain}"
    plan = _plan("pmg_transport_delete", tgt,
                 lambda: pmg_plan_transport_delete(domain))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_transport_delete", tgt,
                    lambda: pmg_transport_delete_op(pmg, domain),
                    mutation=True, outcome="ok", detail={"confirmed": True, "domain": domain})


@mcp.tool()
def pmg_mynetworks_add(cidr: str, comment: str | None = None, confirm: bool = False) -> dict:
    """MUTATION (LOW): add a CIDR to the PMG mynetworks trusted relay list. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: POST /config/mynetworks.
    cidr: network in CIDR notation (e.g. '10.0.0.0/8'). Only add CIDRs you control.
    """
    _, pmg = _pmg()
    tgt = "pmg/config/mynetworks"
    plan = _plan("pmg_mynetworks_add", tgt,
                 lambda: pmg_plan_mynetworks_add(cidr, comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_mynetworks_add", tgt,
                    lambda: pmg_mynetworks_add_op(pmg, cidr, comment),
                    mutation=True, outcome="ok", detail={"confirmed": True, "cidr": cidr})


@mcp.tool()
def pmg_mynetworks_remove(cidr: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): remove a CIDR from the PMG mynetworks trusted relay list. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: DELETE /config/mynetworks/{cidr} (CIDR URL-encoded).
    Internal senders in the range will be subject to spam filtering after removal.
    """
    _, pmg = _pmg()
    tgt = f"pmg/config/mynetworks/{cidr}"
    plan = _plan("pmg_mynetworks_remove", tgt,
                 lambda: pmg_plan_mynetworks_remove(cidr))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_mynetworks_remove", tgt,
                    lambda: pmg_mynetworks_remove_op(pmg, cidr),
                    mutation=True, outcome="ok", detail={"confirmed": True, "cidr": cidr})


@mcp.tool()
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
    _, pmg = _pmg()
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


@mcp.tool()
def pmg_quarantine_welcomelist_list(pmail: str | None = None) -> list[dict]:
    """List PMG quarantine welcomelist entries (read). Optional pmail to scope to one user.
    Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: GET /quarantine/welcomelist.
    pmail defaults to the authenticated user when not provided.
    """
    _, pmg = _pmg()
    return _audited("pmg_quarantine_welcomelist_list", "pmg/quarantine/welcomelist",
                    lambda: pmg_quarantine_welcomelist_list_op(pmg, pmail))


@mcp.tool()
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
    _, pmg = _pmg()
    tgt = "pmg/quarantine/welcomelist"
    plan = _plan("pmg_quarantine_welcomelist_add", tgt,
                 lambda: pmg_plan_quarantine_welcomelist_add(address, pmail))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_quarantine_welcomelist_add", tgt,
                    lambda: pmg_quarantine_welcomelist_add_op(pmg, address, pmail),
                    mutation=True, outcome="ok", detail={"confirmed": True, "address": address})


@mcp.tool()
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
    _, pmg = _pmg()
    tgt = "pmg/quarantine/welcomelist"
    plan = _plan("pmg_quarantine_welcomelist_remove", tgt,
                 lambda: pmg_plan_quarantine_welcomelist_remove(address, pmail))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_quarantine_welcomelist_remove", tgt,
                    lambda: pmg_quarantine_welcomelist_remove_op(pmg, address, pmail),
                    mutation=True, outcome="ok", detail={"confirmed": True, "address": address})


@mcp.tool()
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
    _, pmg = _pmg()
    tgt = "pmg/quarantine/blocklist"
    plan = _plan("pmg_quarantine_blocklist_remove", tgt,
                 lambda: pmg_plan_quarantine_blocklist_remove(address, pmail))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_quarantine_blocklist_remove", tgt,
                    lambda: pmg_quarantine_blocklist_remove_op(pmg, address, pmail),
                    mutation=True, outcome="ok", detail={"confirmed": True, "address": address})


@mcp.tool()
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
    cfg, pmg = _pmg()
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


@mcp.tool()
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
    cfg, pmg = _pmg()
    n = node or cfg.node
    return _audited("pmg_tracker_list", f"pmg/{n}/tracker",
                    lambda: pmg_tracker_list_op(pmg, n, start, end, from_,
                                                target, xfilter, ndr, greylist, limit))


@mcp.tool()
def pmg_tracker_detail(
    id_: str,
    node: str | None = None,
    start: int | None = None,
    end: int | None = None,
) -> list[dict]:
    """Get tracking detail for a specific mail ID (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: GET /nodes/{node}/tracker/{id}.
    id_: raw mail tracking ID (passed as URL path segment, no sanitisation).
    Maps start/end Unix epoch → starttime/endtime query params.
    """
    cfg, pmg = _pmg()
    n = node or cfg.node
    return _audited("pmg_tracker_detail", f"pmg/{n}/tracker/{id_}",
                    lambda: pmg_tracker_detail_op(pmg, n, id_, start, end))


@mcp.tool()
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
    _, pmg = _pmg()
    return _audited("pmg_quarantine_virus", "pmg/quarantine/virus",
                    lambda: pmg_quarantine_virus_op(pmg, pmail, start, end))


@mcp.tool()
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
    _, pmg = _pmg()
    return _audited("pmg_quarantine_attachment", "pmg/quarantine/attachment",
                    lambda: pmg_quarantine_attachment_op(pmg, pmail, start, end))


@mcp.tool()
def pmg_quarantine_virusstatus() -> dict:
    """Get virus quarantine status summary (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: GET /quarantine/virusstatus.
    """
    _, pmg = _pmg()
    return _audited("pmg_quarantine_virusstatus", "pmg/quarantine/virusstatus",
                    lambda: pmg_quarantine_virusstatus_op(pmg))


@mcp.tool()
def pmg_quarantine_spamstatus() -> dict:
    """Get spam quarantine status summary (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: GET /quarantine/spamstatus.
    """
    _, pmg = _pmg()
    return _audited("pmg_quarantine_spamstatus", "pmg/quarantine/spamstatus",
                    lambda: pmg_quarantine_spamstatus_op(pmg))


@mcp.tool()
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
    _, pmg = _pmg()
    return _audited("pmg_quarantine_spamusers", "pmg/quarantine/spamusers",
                    lambda: pmg_quarantine_spamusers_op(pmg, start, end, quarantine_type))


@mcp.tool()
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
    _, pmg = _pmg()
    return _audited("pmg_statistics_mailcount", "pmg/statistics/mailcount",
                    lambda: pmg_statistics_mailcount_op(pmg, start, end, timespan))


@mcp.tool()
def pmg_statistics_sender(
    start: int | None = None,
    end: int | None = None,
    filter_: str | None = None,
    orderby: str | None = None,
) -> list[dict]:
    """Get per-sender mail statistics (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 live-verified path via pmgsh ls: GET /statistics/sender.
    filter_: optional search string; orderby: raw sort spec passthrough.
    Maps start/end Unix epoch → starttime/endtime query params.
    """
    _, pmg = _pmg()
    return _audited("pmg_statistics_sender", "pmg/statistics/sender",
                    lambda: pmg_statistics_sender_op(pmg, start, end, filter_, orderby))


@mcp.tool()
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
    _, pmg = _pmg()
    return _audited("pmg_statistics_receiver", "pmg/statistics/receiver",
                    lambda: pmg_statistics_receiver_op(pmg, start, end, filter_, orderby))


@mcp.tool()
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
    cfg, pmg = _pmg()
    n = node or cfg.node
    return _audited("pmg_node_syslog", f"pmg/{n}/syslog",
                    lambda: pmg_node_syslog_op(pmg, n, limit, service, since, until, start))


@mcp.tool()
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
    cfg, pmg = _pmg()
    n = node or cfg.node
    return _audited("pmg_node_rrddata", f"pmg/{n}/rrddata",
                    lambda: pmg_node_rrddata_op(pmg, n, timeframe, cf))


@mcp.tool()
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
    cfg, pmg = _pmg()
    n = node or cfg.node
    return _audited("pmg_tasks_list", f"pmg/{n}/tasks",
                    lambda: pmg_tasks_list_op(pmg, n, start, limit, userfilter,
                                              errors, typefilter, since, until, statusfilter))


@mcp.tool()
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
    cfg, pmg = _pmg()
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


@mcp.tool()
def pmg_ruledb_rules_list() -> list[dict]:
    """List all PMG RuleDB rules (hydrated rule list) (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules.
    Returns the full hydrated rule list including from/to/what/when/actions for each rule.
    """
    _, pmg = _pmg()
    return _audited("pmg_ruledb_rules_list", "pmg/config/ruledb/rules",
                    lambda: pmg_ruledb_rules_list_op(pmg))


@mcp.tool()
def pmg_ruledb_rule_get(id_: str) -> dict:
    """Get a PMG RuleDB rule's configuration (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules/{id}/config.
    id_: rule ID (positive integer string, e.g. '100').
    """
    _, pmg = _pmg()
    return _audited("pmg_ruledb_rule_get", f"pmg/config/ruledb/rules/{id_}/config",
                    lambda: pmg_ruledb_rule_get_op(pmg, id_))


@mcp.tool()
def pmg_ruledb_rule_from_list(id_: str) -> list[dict]:
    """List the 'from' objects attached to a PMG RuleDB rule (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules/{id}/from.
    id_: rule ID (positive integer string, e.g. '100').
    """
    _, pmg = _pmg()
    return _audited("pmg_ruledb_rule_from_list", f"pmg/config/ruledb/rules/{id_}/from",
                    lambda: pmg_ruledb_rule_from_list_op(pmg, id_))


@mcp.tool()
def pmg_ruledb_rule_to_list(id_: str) -> list[dict]:
    """List the 'to' objects attached to a PMG RuleDB rule (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules/{id}/to.
    id_: rule ID (positive integer string, e.g. '100').
    """
    _, pmg = _pmg()
    return _audited("pmg_ruledb_rule_to_list", f"pmg/config/ruledb/rules/{id_}/to",
                    lambda: pmg_ruledb_rule_to_list_op(pmg, id_))


@mcp.tool()
def pmg_ruledb_rule_what_list(id_: str) -> list[dict]:
    """List the 'what' objects attached to a PMG RuleDB rule (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules/{id}/what.
    id_: rule ID (positive integer string, e.g. '100').
    """
    _, pmg = _pmg()
    return _audited("pmg_ruledb_rule_what_list", f"pmg/config/ruledb/rules/{id_}/what",
                    lambda: pmg_ruledb_rule_what_list_op(pmg, id_))


@mcp.tool()
def pmg_ruledb_rule_when_list(id_: str) -> list[dict]:
    """List the 'when' objects attached to a PMG RuleDB rule (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules/{id}/when.
    id_: rule ID (positive integer string, e.g. '100').
    """
    _, pmg = _pmg()
    return _audited("pmg_ruledb_rule_when_list", f"pmg/config/ruledb/rules/{id_}/when",
                    lambda: pmg_ruledb_rule_when_list_op(pmg, id_))


@mcp.tool()
def pmg_ruledb_rule_actions_list(id_: str) -> list[dict]:
    """List the 'actions' objects attached to a PMG RuleDB rule (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/rules/{id}/actions.
    id_: rule ID (positive integer string, e.g. '100').
    """
    _, pmg = _pmg()
    return _audited("pmg_ruledb_rule_actions_list", f"pmg/config/ruledb/rules/{id_}/actions",
                    lambda: pmg_ruledb_rule_actions_list_op(pmg, id_))


@mcp.tool()
def pmg_who_groups_list() -> list[dict]:
    """List all PMG RuleDB 'who' object groups (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/who.
    """
    _, pmg = _pmg()
    return _audited("pmg_who_groups_list", "pmg/config/ruledb/who",
                    lambda: pmg_who_groups_list_op(pmg))


@mcp.tool()
def pmg_who_group_get(ogroup: str) -> dict:
    """Get a PMG RuleDB 'who' object group's configuration (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/who/{ogroup}/config.
    ogroup: object group name.
    """
    _, pmg = _pmg()
    return _audited("pmg_who_group_get", f"pmg/config/ruledb/who/{ogroup}/config",
                    lambda: pmg_who_group_get_op(pmg, ogroup))


@mcp.tool()
def pmg_who_group_objects(ogroup: str) -> list[dict]:
    """List the objects in a PMG RuleDB 'who' object group (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/who/{ogroup}/objects.
    ogroup: object group name.
    """
    _, pmg = _pmg()
    return _audited("pmg_who_group_objects", f"pmg/config/ruledb/who/{ogroup}/objects",
                    lambda: pmg_who_group_objects_op(pmg, ogroup))


@mcp.tool()
def pmg_what_groups_list() -> list[dict]:
    """List all PMG RuleDB 'what' object groups (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/what.
    """
    _, pmg = _pmg()
    return _audited("pmg_what_groups_list", "pmg/config/ruledb/what",
                    lambda: pmg_what_groups_list_op(pmg))


@mcp.tool()
def pmg_what_group_get(ogroup: str) -> dict:
    """Get a PMG RuleDB 'what' object group's configuration (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/what/{ogroup}/config.
    ogroup: object group name.
    """
    _, pmg = _pmg()
    return _audited("pmg_what_group_get", f"pmg/config/ruledb/what/{ogroup}/config",
                    lambda: pmg_what_group_get_op(pmg, ogroup))


@mcp.tool()
def pmg_what_group_objects(ogroup: str) -> list[dict]:
    """List the objects in a PMG RuleDB 'what' object group (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/what/{ogroup}/objects.
    ogroup: object group name.
    """
    _, pmg = _pmg()
    return _audited("pmg_what_group_objects", f"pmg/config/ruledb/what/{ogroup}/objects",
                    lambda: pmg_what_group_objects_op(pmg, ogroup))


@mcp.tool()
def pmg_when_groups_list() -> list[dict]:
    """List all PMG RuleDB 'when' object groups (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/when.
    """
    _, pmg = _pmg()
    return _audited("pmg_when_groups_list", "pmg/config/ruledb/when",
                    lambda: pmg_when_groups_list_op(pmg))


@mcp.tool()
def pmg_when_group_get(ogroup: str) -> dict:
    """Get a PMG RuleDB 'when' object group's configuration (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/when/{ogroup}/config.
    ogroup: object group name.
    """
    _, pmg = _pmg()
    return _audited("pmg_when_group_get", f"pmg/config/ruledb/when/{ogroup}/config",
                    lambda: pmg_when_group_get_op(pmg, ogroup))


@mcp.tool()
def pmg_when_group_objects(ogroup: str) -> list[dict]:
    """List the objects in a PMG RuleDB 'when' object group (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/when/{ogroup}/objects.
    ogroup: object group name.
    """
    _, pmg = _pmg()
    return _audited("pmg_when_group_objects", f"pmg/config/ruledb/when/{ogroup}/objects",
                    lambda: pmg_when_group_objects_op(pmg, ogroup))


@mcp.tool()
def pmg_action_objects_list() -> list[dict]:
    """List all PMG RuleDB action objects including non-editable (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/action/objects.
    Returns all action objects; each entry carries an 'editable' flag.
    Non-editable action objects are built-in and cannot be modified via the API.
    """
    _, pmg = _pmg()
    return _audited("pmg_action_objects_list", "pmg/config/ruledb/action/objects",
                    lambda: pmg_action_objects_list_op(pmg))


@mcp.tool()
def pmg_ruledb_digest() -> dict:
    """Get the PMG RuleDB digest (change-detection hash) (read). Needs PROXIMO_PMG_* config.

    PMG 9.1 pmgsh-verified path: GET /config/ruledb/digest.
    The digest changes whenever any ruledb configuration is modified.
    Use to detect configuration drift without fetching the full rule list.
    """
    _, pmg = _pmg()
    return _audited("pmg_ruledb_digest", "pmg/config/ruledb/digest",
                    lambda: pmg_ruledb_digest_op(pmg))


@mcp.tool()
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
    _, pmg = _pmg()
    tgt = "pmg/config/ruledb/who"
    plan = _plan("pmg_who_group_create", tgt,
                 lambda: pmg_plan_who_group_create(name, info, and_, invert))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_who_group_create", tgt,
                    lambda: pmg_who_group_create_op(pmg, name, info, and_, invert),
                    mutation=True, outcome="ok", detail={"confirmed": True, "name": name})


@mcp.tool()
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
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/who/{ogroup}/config"
    plan = _plan("pmg_who_group_update", tgt,
                 lambda: pmg_plan_who_group_update(ogroup, name, info, and_, invert))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_who_group_update", tgt,
                    lambda: pmg_who_group_update_op(pmg, ogroup, name, info, and_, invert),
                    mutation=True, outcome="ok", detail={"confirmed": True, "ogroup": ogroup})


@mcp.tool()
def pmg_who_group_delete(ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): delete a PMG RuleDB 'who' object group. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/who/{ogroup}.
    ogroup: numeric ID string (e.g. '2') from pmg_who_groups_list.
    WARNING: also removes all objects within the group.
    """
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/who/{ogroup}"
    plan = _plan("pmg_who_group_delete", tgt,
                 lambda: pmg_plan_who_group_delete(ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_who_group_delete", tgt,
                    lambda: pmg_who_group_delete_op(pmg, ogroup),
                    mutation=True, outcome="ok", detail={"confirmed": True, "ogroup": ogroup})


@mcp.tool()
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
    _, pmg = _pmg()
    tgt = "pmg/config/ruledb/what"
    plan = _plan("pmg_what_group_create", tgt,
                 lambda: pmg_plan_what_group_create(name, info, and_, invert))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_what_group_create", tgt,
                    lambda: pmg_what_group_create_op(pmg, name, info, and_, invert),
                    mutation=True, outcome="ok", detail={"confirmed": True, "name": name})


@mcp.tool()
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
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/what/{ogroup}/config"
    plan = _plan("pmg_what_group_update", tgt,
                 lambda: pmg_plan_what_group_update(ogroup, name, info, and_, invert))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_what_group_update", tgt,
                    lambda: pmg_what_group_update_op(pmg, ogroup, name, info, and_, invert),
                    mutation=True, outcome="ok", detail={"confirmed": True, "ogroup": ogroup})


@mcp.tool()
def pmg_what_group_delete(ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): delete a PMG RuleDB 'what' object group. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/what/{ogroup}.
    ogroup: numeric ID string (e.g. '8') from pmg_what_groups_list.
    WARNING: also removes all objects within the group.
    """
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/what/{ogroup}"
    plan = _plan("pmg_what_group_delete", tgt,
                 lambda: pmg_plan_what_group_delete(ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_what_group_delete", tgt,
                    lambda: pmg_what_group_delete_op(pmg, ogroup),
                    mutation=True, outcome="ok", detail={"confirmed": True, "ogroup": ogroup})


@mcp.tool()
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
    _, pmg = _pmg()
    tgt = "pmg/config/ruledb/when"
    plan = _plan("pmg_when_group_create", tgt,
                 lambda: pmg_plan_when_group_create(name, info, and_, invert))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_when_group_create", tgt,
                    lambda: pmg_when_group_create_op(pmg, name, info, and_, invert),
                    mutation=True, outcome="ok", detail={"confirmed": True, "name": name})


@mcp.tool()
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
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/when/{ogroup}/config"
    plan = _plan("pmg_when_group_update", tgt,
                 lambda: pmg_plan_when_group_update(ogroup, name, info, and_, invert))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_when_group_update", tgt,
                    lambda: pmg_when_group_update_op(pmg, ogroup, name, info, and_, invert),
                    mutation=True, outcome="ok", detail={"confirmed": True, "ogroup": ogroup})


@mcp.tool()
def pmg_when_group_delete(ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): delete a PMG RuleDB 'when' object group. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/when/{ogroup}.
    ogroup: numeric ID string (e.g. '4') from pmg_when_groups_list.
    WARNING: also removes all objects within the group.
    """
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/when/{ogroup}"
    plan = _plan("pmg_when_group_delete", tgt,
                 lambda: pmg_plan_when_group_delete(ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_when_group_delete", tgt,
                    lambda: pmg_when_group_delete_op(pmg, ogroup),
                    mutation=True, outcome="ok", detail={"confirmed": True, "ogroup": ogroup})


@mcp.tool()
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
    _, pmg = _pmg()
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


@mcp.tool()
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
    _, pmg = _pmg()
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


@mcp.tool()
def pmg_who_object_delete(ogroup: str, id_: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): delete an object from a PMG RuleDB 'who' object group. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/who/{ogroup}/objects/{id}.
    ogroup: numeric ID string (e.g. '2') from pmg_who_groups_list.
    id_: object ID (numeric string) from pmg_who_group_objects.
    Object DELETE always goes through /objects/{id} regardless of type.
    """
    _, pmg = _pmg()
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

@mcp.tool()
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
    _, pmg = _pmg()
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


@mcp.tool()
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
    _, pmg = _pmg()
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


@mcp.tool()
def pmg_what_object_delete(ogroup: str, id_: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): delete an object from a PMG RuleDB 'what' object group. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/what/{ogroup}/objects/{id}.
    ogroup: numeric ID string (e.g. '8') from pmg_what_groups_list.
    id_: object ID (numeric string) from pmg_what_group_objects.
    Object DELETE always goes through /objects/{id} regardless of type.
    """
    _, pmg = _pmg()
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

@mcp.tool()
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
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/when/{ogroup}/timeframe"
    plan = _plan("pmg_when_object_add", tgt,
                 lambda: pmg_plan_when_object_add(ogroup, start=start, end=end))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_when_object_add", tgt,
                    lambda: pmg_when_object_add_op(pmg, ogroup, start=start, end=end),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "ogroup": ogroup})


@mcp.tool()
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
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/when/{ogroup}/timeframe/{id_}"
    plan = _plan("pmg_when_object_update", tgt,
                 lambda: pmg_plan_when_object_update(ogroup, id_, start=start, end=end))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_when_object_update", tgt,
                    lambda: pmg_when_object_update_op(pmg, ogroup, id_, start=start, end=end),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "ogroup": ogroup, "id": id_})


@mcp.tool()
def pmg_when_object_delete(ogroup: str, id_: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): delete a timeframe object from a PMG RuleDB 'when' object group. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/when/{ogroup}/objects/{id}.
    ogroup: numeric ID string (e.g. '4') from pmg_when_groups_list.
    id_: object ID (numeric string) from pmg_when_group_objects.
    Object DELETE always goes through /objects/{id} regardless of type.
    """
    _, pmg = _pmg()
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

@mcp.tool()
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
    _, pmg = _pmg()
    tgt = "pmg/config/ruledb/action/bcc"
    plan = _plan("pmg_action_bcc_create", tgt,
                 lambda: pmg_plan_action_bcc_create(name, target))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_action_bcc_create", tgt,
                    lambda: pmg_action_bcc_create_op(pmg, name=name, target=target,
                                                     info=info, original=original),
                    mutation=True, outcome="ok", detail={"confirmed": True, "name": name})


@mcp.tool()
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
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/action/bcc/{id_}"
    plan = _plan("pmg_action_bcc_update", tgt,
                 lambda: pmg_plan_action_bcc_update(id_))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_action_bcc_update", tgt,
                    lambda: pmg_action_bcc_update_op(pmg, id_, name=name, target=target,
                                                     info=info, original=original),
                    mutation=True, outcome="ok", detail={"confirmed": True, "id": id_})


@mcp.tool()
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
    _, pmg = _pmg()
    tgt = "pmg/config/ruledb/action/field"
    plan = _plan("pmg_action_field_create", tgt,
                 lambda: pmg_plan_action_field_create(name, field, value))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_action_field_create", tgt,
                    lambda: pmg_action_field_create_op(pmg, name=name, field=field,
                                                       value=value, info=info),
                    mutation=True, outcome="ok", detail={"confirmed": True, "name": name})


@mcp.tool()
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
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/action/field/{id_}"
    plan = _plan("pmg_action_field_update", tgt,
                 lambda: pmg_plan_action_field_update(id_))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_action_field_update", tgt,
                    lambda: pmg_action_field_update_op(pmg, id_, name=name, field=field,
                                                       value=value, info=info),
                    mutation=True, outcome="ok", detail={"confirmed": True, "id": id_})


@mcp.tool()
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
    _, pmg = _pmg()
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


@mcp.tool()
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
    _, pmg = _pmg()
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


@mcp.tool()
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
    _, pmg = _pmg()
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


@mcp.tool()
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
    _, pmg = _pmg()
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


@mcp.tool()
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
    _, pmg = _pmg()
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


@mcp.tool()
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
    _, pmg = _pmg()
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


@mcp.tool()
def pmg_action_delete(id_: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): delete an action object from the PMG RuleDB. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/action/objects/{id}.
    id_: compound action object ID (e.g. '13_26') from pmg_action_objects_list.
    NOTE: PMG rejects deletion of non-editable (built-in) system action objects.
    Check 'editable' flag in pmg_action_objects_list before confirming.
    """
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/action/objects/{id_}"
    plan = _plan("pmg_action_delete", tgt,
                 lambda: pmg_plan_action_delete(id_))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_action_delete", tgt,
                    lambda: pmg_action_delete_op(pmg, id_),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_})


@mcp.tool()
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
    _, pmg = _pmg()
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


@mcp.tool()
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
    _, pmg = _pmg()
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


@mcp.tool()
def pmg_ruledb_rule_delete(id_: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): delete a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/rules/{id}.
    id_: rule ID (positive integer string, e.g. '100').
    WARNING: permanently removes the rule and all its group bindings.
    """
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}"
    plan = _plan("pmg_ruledb_rule_delete", tgt,
                 lambda: pmg_plan_ruledb_rule_delete(id_))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_delete", tgt,
                    lambda: pmg_ruledb_rule_delete_op(pmg, id_),
                    mutation=True, outcome="ok", detail={"confirmed": True, "id": id_})


@mcp.tool()
def pmg_ruledb_rule_from_attach(id_: str, ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): attach a 'from' (sender/who) group to a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: POST /config/ruledb/rules/{id}/from.
    id_: rule ID. ogroup: numeric who-group ID from pmg_who_groups_list.
    Only affects mail flow if the rule is active.
    """
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}/from"
    plan = _plan("pmg_ruledb_rule_from_attach", tgt,
                 lambda: pmg_plan_ruledb_rule_from_attach(id_, ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_from_attach", tgt,
                    lambda: pmg_ruledb_rule_from_attach_op(pmg, id_, ogroup),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_, "ogroup": ogroup})


@mcp.tool()
def pmg_ruledb_rule_from_detach(id_: str, ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): detach a 'from' (sender/who) group from a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/rules/{id}/from/{ogroup}.
    id_: rule ID. ogroup: numeric who-group ID to detach.
    Only affects mail flow if the rule is active.
    """
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}/from/{ogroup}"
    plan = _plan("pmg_ruledb_rule_from_detach", tgt,
                 lambda: pmg_plan_ruledb_rule_from_detach(id_, ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_from_detach", tgt,
                    lambda: pmg_ruledb_rule_from_detach_op(pmg, id_, ogroup),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_, "ogroup": ogroup})


@mcp.tool()
def pmg_ruledb_rule_to_attach(id_: str, ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): attach a 'to' (recipient/who) group to a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: POST /config/ruledb/rules/{id}/to.
    id_: rule ID. ogroup: numeric who-group ID from pmg_who_groups_list.
    Only affects mail flow if the rule is active.
    """
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}/to"
    plan = _plan("pmg_ruledb_rule_to_attach", tgt,
                 lambda: pmg_plan_ruledb_rule_to_attach(id_, ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_to_attach", tgt,
                    lambda: pmg_ruledb_rule_to_attach_op(pmg, id_, ogroup),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_, "ogroup": ogroup})


@mcp.tool()
def pmg_ruledb_rule_to_detach(id_: str, ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): detach a 'to' (recipient/who) group from a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/rules/{id}/to/{ogroup}.
    id_: rule ID. ogroup: numeric who-group ID to detach.
    Only affects mail flow if the rule is active.
    """
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}/to/{ogroup}"
    plan = _plan("pmg_ruledb_rule_to_detach", tgt,
                 lambda: pmg_plan_ruledb_rule_to_detach(id_, ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_to_detach", tgt,
                    lambda: pmg_ruledb_rule_to_detach_op(pmg, id_, ogroup),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_, "ogroup": ogroup})


@mcp.tool()
def pmg_ruledb_rule_what_attach(id_: str, ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): attach a 'what' (content) group to a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: POST /config/ruledb/rules/{id}/what.
    id_: rule ID. ogroup: numeric what-group ID from pmg_what_groups_list.
    Only affects mail flow if the rule is active.
    """
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}/what"
    plan = _plan("pmg_ruledb_rule_what_attach", tgt,
                 lambda: pmg_plan_ruledb_rule_what_attach(id_, ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_what_attach", tgt,
                    lambda: pmg_ruledb_rule_what_attach_op(pmg, id_, ogroup),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_, "ogroup": ogroup})


@mcp.tool()
def pmg_ruledb_rule_what_detach(id_: str, ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): detach a 'what' (content) group from a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/rules/{id}/what/{ogroup}.
    id_: rule ID. ogroup: numeric what-group ID to detach.
    Only affects mail flow if the rule is active.
    """
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}/what/{ogroup}"
    plan = _plan("pmg_ruledb_rule_what_detach", tgt,
                 lambda: pmg_plan_ruledb_rule_what_detach(id_, ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_what_detach", tgt,
                    lambda: pmg_ruledb_rule_what_detach_op(pmg, id_, ogroup),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_, "ogroup": ogroup})


@mcp.tool()
def pmg_ruledb_rule_when_attach(id_: str, ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): attach a 'when' (timeframe) group to a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: POST /config/ruledb/rules/{id}/when.
    id_: rule ID. ogroup: numeric when-group ID from pmg_when_groups_list.
    Only affects mail flow if the rule is active.
    """
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}/when"
    plan = _plan("pmg_ruledb_rule_when_attach", tgt,
                 lambda: pmg_plan_ruledb_rule_when_attach(id_, ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_when_attach", tgt,
                    lambda: pmg_ruledb_rule_when_attach_op(pmg, id_, ogroup),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_, "ogroup": ogroup})


@mcp.tool()
def pmg_ruledb_rule_when_detach(id_: str, ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): detach a 'when' (timeframe) group from a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/rules/{id}/when/{ogroup}.
    id_: rule ID. ogroup: numeric when-group ID to detach.
    Only affects mail flow if the rule is active.
    """
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}/when/{ogroup}"
    plan = _plan("pmg_ruledb_rule_when_detach", tgt,
                 lambda: pmg_plan_ruledb_rule_when_detach(id_, ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_when_detach", tgt,
                    lambda: pmg_ruledb_rule_when_detach_op(pmg, id_, ogroup),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_, "ogroup": ogroup})


@mcp.tool()
def pmg_ruledb_rule_action_attach(id_: str, ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): attach an action group to a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 live-verified path: POST /config/ruledb/rules/{id}/action (singular; /actions returns 501).
    id_: rule ID. ogroup: numeric action group ID from pmg_action_objects_list.
    Only affects mail flow if the rule is active.
    """
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}/action"
    plan = _plan("pmg_ruledb_rule_action_attach", tgt,
                 lambda: pmg_plan_ruledb_rule_action_attach(id_, ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_action_attach", tgt,
                    lambda: pmg_ruledb_rule_action_attach_op(pmg, id_, ogroup),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_, "ogroup": ogroup})


@mcp.tool()
def pmg_ruledb_rule_action_detach(id_: str, ogroup: str, confirm: bool = False) -> dict:
    """MUTATION (MEDIUM): detach an action group from a PMG RuleDB rule. Dry-run by default.
    confirm=True to execute. Needs PROXIMO_PMG_* config.
    PMG 9.1 live-verified path: DELETE /config/ruledb/rules/{id}/action/{ogroup} (singular; /actions returns 501).
    id_: rule ID. ogroup: numeric action group ID to detach.
    Only affects mail flow if the rule is active.
    """
    _, pmg = _pmg()
    tgt = f"pmg/config/ruledb/rules/{id_}/action/{ogroup}"
    plan = _plan("pmg_ruledb_rule_action_detach", tgt,
                 lambda: pmg_plan_ruledb_rule_action_detach(id_, ogroup))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pmg_ruledb_rule_action_detach", tgt,
                    lambda: pmg_ruledb_rule_action_detach_op(pmg, id_, ogroup),
                    mutation=True, outcome="ok",
                    detail={"confirmed": True, "id": id_, "ogroup": ogroup})


# --- PDM (Proxmox Datacenter Manager) read-only ---

@mcp.tool()
def pdm_ping() -> str:
    """DIAGNOSE (LOW): health check the PDM appliance. Returns 'pong' on success.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_ping", "pdm/ping", lambda: pdm.ping())


@mcp.tool()
def pdm_version() -> dict:
    """DIAGNOSE (LOW): get PDM appliance version (release, repoid, version).
    Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_version", "pdm/version", lambda: pdm.version())


@mcp.tool()
def pdm_node_status(node: str = "localhost") -> dict:
    """DIAGNOSE (LOW): get resource stats for a PDM node. Defaults to 'localhost'
    (PDM is a single-node appliance). Shape equals PVE node status;
    live-prove-pending. Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_node_status", f"pdm/nodes/{node}", lambda: pdm.node_status(node))


@mcp.tool()
def pdm_remotes_list() -> list[dict]:
    """DIAGNOSE (LOW): list all PVE/PBS remotes registered in PDM.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_remotes_list", "pdm/remotes", lambda: pdm.remotes_list())


@mcp.tool()
def pdm_remote_version(remote_id: str) -> dict:
    """DIAGNOSE (LOW): get version info for one PDM-registered remote.
    remote_id: the remote name as shown in pdm_remotes_list.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_remote_version", f"pdm/remotes/{remote_id}",
                    lambda: pdm.remote_version(remote_id))


@mcp.tool()
def pdm_remote_config_get(remote_id: str) -> dict:
    """DIAGNOSE (LOW): get configuration for one PDM-registered remote (no secrets returned).
    remote_id: the remote name as shown in pdm_remotes_list.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_remote_config_get", f"pdm/remotes/{remote_id}",
                    lambda: pdm.remote_config_get(remote_id))


@mcp.tool()
def pdm_resources_list() -> list[dict]:
    """DIAGNOSE (LOW): list all fleet resources (VMs, LXCs, storage, etc.) across all remotes.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_resources_list", "pdm/resources/list", lambda: pdm.resources_list())


@mcp.tool()
def pdm_resources_status() -> dict:
    """DIAGNOSE (LOW): aggregated fleet status counters (running VMs, LXCs, failed remotes, etc.).
    Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_resources_status", "pdm/resources/status",
                    lambda: pdm.resources_status())


@mcp.tool()
def pdm_pve_resources(remote: str, kind: str | None = None) -> list[dict]:
    """DIAGNOSE (LOW): list resources on a PDM-registered PVE remote.
    remote: remote name from pdm_remotes_list.
    kind: optional filter (vm, storage, node, sdn, ...).
    Shape equals PVE cluster/resources; live-proven 2026-06-27 against a registered PVE remote.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_pve_resources", f"pdm/pve/{remote}/resources",
                    lambda: pdm.pve_resources(remote, kind))


@mcp.tool()
def pdm_pve_cluster_status(remote: str) -> list[dict]:
    """DIAGNOSE (LOW): get cluster status for a PDM-registered PVE remote.
    remote: remote name from pdm_remotes_list.
    Shape equals PVE cluster/status; live-proven 2026-06-27 against a registered PVE remote.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_pve_cluster_status", f"pdm/pve/{remote}/cluster-status",
                    lambda: pdm.pve_cluster_status(remote))


@mcp.tool()
def pdm_pve_node_list(remote: str) -> list[dict]:
    """DIAGNOSE (LOW): list nodes in a PDM-registered PVE remote.
    remote: remote name from pdm_remotes_list.
    Shape equals PVE /nodes; live-proven 2026-06-27 against a registered PVE remote.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_pve_node_list", f"pdm/pve/{remote}/nodes",
                    lambda: pdm.pve_node_list(remote))


@mcp.tool()
def pdm_pve_qemu_list(remote: str, node: str | None = None) -> list[dict]:
    """DIAGNOSE (LOW): list VMs across a PDM-registered PVE remote (cluster-wide).
    remote: remote name. node: OPTIONAL filter to one PVE node.
    Shape equals PVE qemu list; live-proven 2026-06-27 against a registered PVE remote.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_pve_qemu_list", f"pdm/pve/{remote}/qemu",
                    lambda: pdm.pve_qemu_list(remote, node))


@mcp.tool()
def pdm_pve_qemu_config(remote: str, vmid: str, node: str | None = None,
                        snapshot: str | None = None, state: str = "active") -> dict:
    """DIAGNOSE (LOW): get VM config from a PDM-registered PVE remote.
    remote: remote name. vmid: numeric VM ID.
    node, snapshot: optional query params (node is NOT required).
    state: REQUIRED by PDM ("active" = current config) — defaults to "active"; PDM 400s if omitted.
    Live-proven 2026-06-27 against a registered PVE remote. Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_pve_qemu_config", f"pdm/pve/{remote}/qemu/{vmid}",
                    lambda: pdm.pve_qemu_config(remote, vmid, node, snapshot, state))


@mcp.tool()
def pdm_pve_lxc_list(remote: str, node: str | None = None) -> list[dict]:
    """DIAGNOSE (LOW): list LXC containers across a PDM-registered PVE remote (cluster-wide).
    remote: remote name. node: OPTIONAL filter to one PVE node.
    Shape equals PVE lxc list; live-proven 2026-06-27 against a registered PVE remote.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_pve_lxc_list", f"pdm/pve/{remote}/lxc",
                    lambda: pdm.pve_lxc_list(remote, node))


@mcp.tool()
def pdm_pve_lxc_config(remote: str, vmid: str, node: str | None = None,
                       snapshot: str | None = None, state: str = "active") -> dict:
    """DIAGNOSE (LOW): get LXC config from a PDM-registered PVE remote.
    remote: remote name. vmid: numeric CT ID.
    node, snapshot: optional query params (node is NOT required).
    state: REQUIRED by PDM ("active" = current config) — defaults to "active"; PDM 400s if omitted.
    Live-proven 2026-06-27 against a registered PVE remote. Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_pve_lxc_config", f"pdm/pve/{remote}/lxc/{vmid}",
                    lambda: pdm.pve_lxc_config(remote, vmid, node, snapshot, state))


@mcp.tool()
def pdm_pbs_remote_status(remote: str) -> dict:
    """DIAGNOSE (LOW): get node status for a PDM-registered PBS remote.
    remote: remote name from pdm_remotes_list.
    Live-verified (PDM 1.1 -> PBS 4.2).
    Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_pbs_remote_status", f"pdm/pbs/{remote}/status",
                    lambda: pdm.pbs_remote_status(remote))


@mcp.tool()
def pdm_pbs_datastores_list(remote: str) -> list[dict]:
    """DIAGNOSE (LOW): list datastores on a PDM-registered PBS remote.
    remote: remote name from pdm_remotes_list.
    Live-verified shape: [{"name","path"}, ...] (PDM 1.1 -> PBS 4.2).
    Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_pbs_datastores_list", f"pdm/pbs/{remote}/datastore",
                    lambda: pdm.pbs_datastores_list(remote))


@mcp.tool()
def pdm_pbs_snapshots_list(remote: str, datastore: str,
                           ns: str | None = None) -> list[dict]:
    """DIAGNOSE (LOW): list backup snapshots in a datastore on a PDM-registered PBS remote.
    remote: remote name. datastore: PBS datastore name. ns: optional namespace filter.
    Live-verified path (PDM 1.1 -> PBS 4.2); empty datastore returns [].
    Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_pbs_snapshots_list",
                    f"pdm/pbs/{remote}/datastore/{datastore}/snapshots",
                    lambda: pdm.pbs_snapshots_list(remote, datastore, ns))


@mcp.tool()
def pdm_tasks_list() -> list[dict]:
    """DIAGNOSE (LOW): list recent PDM tasks across all remotes.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_tasks_list", "pdm/remotes/tasks", lambda: pdm.tasks_list())


@mcp.tool()
def pdm_acl_list(path: str | None = None, exact: bool = False) -> list[dict]:
    """DIAGNOSE (LOW): list PDM access control entries.
    path: optional ACL path filter (e.g. '/'). exact: if True, exact path only.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_acl_list", "pdm/access/acl",
                    lambda: pdm.acl_list(path, exact))


@mcp.tool()
def pdm_roles_list() -> list[dict]:
    """DIAGNOSE (LOW): list all roles and their privileges defined in PDM.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_roles_list", "pdm/access/roles", lambda: pdm.roles_list())


@mcp.tool()
def pdm_users_list(include_tokens: bool = False) -> list[dict]:
    """DIAGNOSE (LOW): list all PDM users.
    include_tokens: if True, include API token entries.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _pdm()
    return _audited("pdm_users_list", "pdm/access/users",
                    lambda: pdm.users_list(include_tokens))


def main() -> None:
    # `proximo doctor` — verify your token/config (read-only preflight) BEFORE wiring Proximo into
    # an AI client. Prints what THIS token can and cannot do; never starts the server.
    if len(sys.argv) > 1 and sys.argv[1] == "doctor":
        import json
        try:
            result = pve_doctor()
        except Exception as e:  # config/token/connectivity problem — give a plain message, not a trace
            print(f"proximo doctor: {e}", file=sys.stderr)
            raise SystemExit(1) from None
        print(json.dumps(result, indent=2))
        return
    print(BANNER, file=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    main()
