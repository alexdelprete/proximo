"""Completeness guard: EVERY tool registered on the live MCP surface is classified one way or
the other — adversarial (`taint.ADVERSARIAL_TOOLS`) or explicitly reviewed-trusted
(`REVIEWED_TRUSTED` below). This is the anti-fail-open backstop the design doc calls for
(`.scratch/taint-design-v2-2026-07-02.md` §Component 0): classification is a curated set, so an
adversarial channel added later and never classified is a real gap — this test makes an
UNCLASSIFIED/UNREVIEWED tool fail CI, not fail-open at runtime.

`REVIEWED_TRUSTED` was generated once from the live registry (`set(names) - ADVERSARIAL_TOOLS`)
and hand-spot-checked: it contains only structured-return / operator-authored-content tools
(status/config-CRUD/list-of-ids surfaces), no free-text guest/external channel. Notably absent
from it (because they're correctly in `taint.ADVERSARIAL_TOOLS` instead): `ct_exec`, `ct_psql`,
`ct_logs`, `ct_diagnose`, `pve_agent_exec`, `pve_agent_info`, `pve_agent_file_read`, and the
`pmg_quarantine_*`/`pmg_tracker_*` email-content tools.

When this test fails after adding a tool: classify it. Guest/log/quarantine/free-text-external
content -> add to `taint.ADVERSARIAL_TOOLS`. Structured, operator-authored, no attacker-shapeable
free text -> add to `REVIEWED_TRUSTED` below. Do not add to `REVIEWED_TRUSTED` just to make the
test pass — that's exactly the fail-open path this test exists to block.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import proximo.server as server
from proximo import taint

# Generated once via `set(names) - taint.ADVERSARIAL_TOOLS` against the live registry
# (352 tools, 2026-07-02), then hand-reviewed. Keep sorted for readable diffs.
REVIEWED_TRUSTED: frozenset[str] = frozenset({
    'audit_verify', 'pbs_acl_get', 'pbs_acl_update',
    'pbs_acme_account_create', 'pbs_acme_account_delete', 'pbs_acme_account_get',
    'pbs_acme_account_list', 'pbs_acme_account_update', 'pbs_acme_cert_order',
    'pbs_acme_cert_renew', 'pbs_acme_challenge_schema', 'pbs_acme_directories',
    'pbs_acme_plugin_create', 'pbs_acme_plugin_delete', 'pbs_acme_plugin_get',
    'pbs_acme_plugin_update', 'pbs_acme_plugins_list',
    # NOT 'pbs_acme_tos' — Wave 3b review reclassified it ADVERSARIAL (caller-chosen URL
    # fetched by the PBS host; response text is attacker-shapeable).
    'pbs_apt_repositories_get', 'pbs_apt_repository_add',
    'pbs_apt_repository_set', 'pbs_apt_update_refresh', 'pbs_apt_updates_list', 'pbs_apt_versions',
    'pbs_datastore_create', 'pbs_datastore_delete', 'pbs_datastore_get', 'pbs_datastore_status',
    'pbs_datastore_update', 'pbs_datastores_list', 'pbs_gc_start', 'pbs_gc_status', 'pbs_group_change_owner',
    'pbs_job_create', 'pbs_job_delete', 'pbs_job_run', 'pbs_job_update', 'pbs_jobs_list', 'pbs_namespace_create',
    'pbs_namespace_delete', 'pbs_namespaces_list',
    'pbs_node_cert_delete', 'pbs_node_cert_upload', 'pbs_node_certificates_list',
    'pbs_node_disk_directory_create', 'pbs_node_disk_directory_delete', 'pbs_node_disk_directory_list',
    'pbs_node_disk_initgpt', 'pbs_node_disk_smart', 'pbs_node_disk_wipe',
    'pbs_node_disk_zfs_create', 'pbs_node_disk_zfs_get', 'pbs_node_disk_zfs_list', 'pbs_node_disks_list',
    'pbs_node_dns_get', 'pbs_node_dns_set', 'pbs_node_network_iface_create',
    'pbs_node_network_iface_delete', 'pbs_node_network_iface_get', 'pbs_node_network_iface_update',
    'pbs_node_network_list', 'pbs_node_network_reload', 'pbs_node_network_revert',
    'pbs_node_service_control', 'pbs_node_service_status', 'pbs_node_services_list',
    'pbs_node_status', 'pbs_node_subscription_check', 'pbs_node_subscription_delete',
    'pbs_node_subscription_get', 'pbs_node_subscription_set', 'pbs_node_task_status',
    'pbs_node_task_stop', 'pbs_node_time_get', 'pbs_node_time_set',
    'pbs_notification_endpoint_create', 'pbs_notification_endpoint_delete',
    'pbs_notification_endpoint_get', 'pbs_notification_endpoint_list',
    'pbs_notification_endpoint_update',
    'pbs_notification_matcher_delete', 'pbs_notification_matcher_field_values',
    'pbs_notification_matcher_fields', 'pbs_notification_matcher_get',
    'pbs_notification_matcher_set', 'pbs_notification_matchers_list',
    'pbs_notification_target_test', 'pbs_notification_targets_list',
    'pbs_permissions_get', 'pbs_prune',
    'pbs_realm_ad_create', 'pbs_realm_ad_delete', 'pbs_realm_ad_get', 'pbs_realm_ad_list',
    'pbs_realm_ad_update', 'pbs_realm_ldap_create', 'pbs_realm_ldap_delete', 'pbs_realm_ldap_get',
    'pbs_realm_ldap_list', 'pbs_realm_ldap_update', 'pbs_realm_openid_create',
    'pbs_realm_openid_delete', 'pbs_realm_openid_get', 'pbs_realm_openid_list',
    'pbs_realm_openid_update', 'pbs_realm_pam_get', 'pbs_realm_pam_set', 'pbs_realm_pbs_get',
    'pbs_realm_pbs_set', 'pbs_realm_sync',
    'pbs_remote_create', 'pbs_remote_delete', 'pbs_remote_get', 'pbs_remote_update', 'pbs_remotes_list',
    'pbs_roles_list', 'pbs_snapshot_delete',
    'pbs_snapshot_notes_set', 'pbs_snapshot_protected_set',
    # Wave 4a (2026-07-15): PBS tape hardware config (drive/changer CRUD) — structured,
    # operator-authored config, no attacker-shapeable free text. The two scan reads carry
    # device-reported vendor/model/serial strings — hardware-authored, matching the precedent
    # already set by pve_hardware_list / pbs_node_disks_list / pbs_node_disk_smart (all three
    # also REVIEWED_TRUSTED despite carrying autodetected hardware fields).
    'pbs_tape_changer_create', 'pbs_tape_changer_delete', 'pbs_tape_changer_get',
    'pbs_tape_changer_list', 'pbs_tape_changer_update',
    'pbs_tape_drive_create', 'pbs_tape_drive_delete', 'pbs_tape_drive_get',
    'pbs_tape_drive_list', 'pbs_tape_drive_update',
    'pbs_tape_scan_changers', 'pbs_tape_scan_drives',
    # Wave 4b (2026-07-15): PBS tape media-pool + encryption-key config — same rationale as
    # Wave 4a above: structured, operator-authored config, no attacker-shapeable free text.
    # comment/hint/template are operator-authored free-text fields, same category as
    # pbs_notifications.py's own comment fields (already REVIEWED_TRUSTED), not an external/
    # guest-authored channel. Encryption-key reads return PUBLIC metadata only (never key
    # material/password — schema-verified, pbs_tape_media.py module docstring fact #9).
    'pbs_tape_key_create', 'pbs_tape_key_delete', 'pbs_tape_key_get', 'pbs_tape_key_list',
    'pbs_tape_key_update_password',
    'pbs_tape_pool_create', 'pbs_tape_pool_delete', 'pbs_tape_pool_get', 'pbs_tape_pool_list',
    'pbs_tape_pool_update',
    # Wave 4c (2026-07-15): PBS tape drive/changer OPERATIONS. Reads: drive status/
    # volume-statistics are pure device telemetry — no label-text field in either response
    # (unlike read-label/inventory/cartridge-memory/changer_status, which ARE in
    # taint.ADVERSARIAL_TOOLS instead — see pbs_tape_ops.py module docstring's Taint section).
    # Mutations: all 13 return either an opaque UPID (task identifier, PBS-generated) or null —
    # none echo back media-authored free text, so all are REVIEWED_TRUSTED regardless of their
    # real-world physical/robotics side effects (taint classifies the RETURN channel, not the
    # mutation's physical consequences).
    'pbs_tape_drive_status', 'pbs_tape_drive_volume_statistics',
    'pbs_tape_drive_load_media', 'pbs_tape_drive_load_slot', 'pbs_tape_drive_unload',
    'pbs_tape_drive_eject', 'pbs_tape_drive_rewind', 'pbs_tape_drive_clean',
    'pbs_tape_drive_inventory_update', 'pbs_tape_drive_label_media',
    'pbs_tape_drive_barcode_label_media', 'pbs_tape_drive_format', 'pbs_tape_drive_catalog',
    'pbs_tape_drive_restore_key', 'pbs_tape_changer_transfer',
    # Wave 4d (2026-07-15): PBS tape media CATALOG + tape-backup JOBS + backup/restore — CLOSES
    # Wave 4 (PBS tape). Reads: pbs_tape_media_sets carries NO label-text field at all (confirmed
    # field-by-field against the live schema — media-set-name is PBS-generated from the pool's
    # operator-authored template, not physical-media content; a deliberate divergence from the
    # campaign brief's own premise, argued in pbs_tape_jobs.py's module docstring). NOT here:
    # pbs_tape_media_list/pbs_tape_media_content/pbs_tape_media_status_get — all three are in
    # taint.ADVERSARIAL_TOOLS instead. pbs_tape_backup_job_list/get are operator-authored
    # scheduled-job config, matching pve_backup_job_list/create's existing REVIEWED_TRUSTED
    # classification. Mutations: all 9 return either an opaque UPID or null — none echo back
    # media/guest-authored free text, including pbs_tape_media_destroy (a GET-verb mutation —
    # taint classifies the RETURN channel, not the HTTP verb or the mutation's consequences,
    # same rule Wave 4c's 13 mutations already established).
    'pbs_tape_media_sets', 'pbs_tape_backup_job_list', 'pbs_tape_backup_job_get',
    'pbs_tape_media_destroy', 'pbs_tape_media_status_set', 'pbs_tape_media_move',
    'pbs_tape_backup_job_create', 'pbs_tape_backup_job_update', 'pbs_tape_backup_job_delete',
    'pbs_tape_backup_job_run', 'pbs_tape_backup', 'pbs_tape_restore',
    # Wave 5a (2026-07-15): PBS S3 client configs + client encryption keys — starts Wave 5
    # (closes the PBS plane after 5c). Reads: pbs_s3_client_list/get are operator-authored config
    # ("without secret" per the live schema — access-key is a non-secret identifier, secret-key
    # never returned); pbs_encryption_key_list is operator/import-authored metadata, no key
    # material ever returned. NOT here: pbs_s3_list_buckets — in taint.ADVERSARIAL_TOOLS instead
    # (externally-authored bucket-name content). Mutations: all 8 return null (opaque, no
    # content) — pbs_s3_check/pbs_s3_reset_counters are confirm-gated PUT-verb tools with a real
    # (check) or observability-only (reset_counters) effect but carry no return content either.
    'pbs_s3_client_list', 'pbs_s3_client_get', 'pbs_s3_client_create', 'pbs_s3_client_update',
    'pbs_s3_client_delete', 'pbs_s3_check', 'pbs_s3_reset_counters',
    'pbs_encryption_key_list', 'pbs_encryption_key_create', 'pbs_encryption_key_delete',
    'pbs_encryption_key_toggle_archive',
    # Wave 5b (2026-07-15): PBS metrics servers — operator-authored config on both influxdb-http
    # and influxdb-udp sub-planes; all mutations return null (opaque, no content).
    # pbs_metrics_influxdb_http_list/get strip `token` at the read layer (a REQUIRED strip — the
    # live schema's response shape DOES carry it, unlike pbs_s3's documented-secret-free reads) —
    # once stripped, the remaining shape is the same operator-authored config category as every
    # other PBS config-CRUD read. pbs_metrics_servers_list is schema-enforced secret-free
    # (additionalProperties: false, 5 fields, no token property can appear at all).
    # pbs_metrics_status is server-authored numeric telemetry (host/datastore performance
    # metrics) — matches the pve_node_rrddata/pmg_node_rrddata REVIEWED_TRUSTED precedent, argued
    # explicitly in pbs_metrics.py's module docstring (NOT the externally-authored-content
    # precedent that landed pbs_s3_list_buckets in taint.ADVERSARIAL_TOOLS instead).
    'pbs_metrics_servers_list', 'pbs_metrics_status',
    'pbs_metrics_influxdb_http_list', 'pbs_metrics_influxdb_http_get',
    'pbs_metrics_influxdb_http_create', 'pbs_metrics_influxdb_http_update',
    'pbs_metrics_influxdb_http_delete',
    'pbs_metrics_influxdb_udp_list', 'pbs_metrics_influxdb_udp_get',
    'pbs_metrics_influxdb_udp_create', 'pbs_metrics_influxdb_udp_update',
    'pbs_metrics_influxdb_udp_delete',
    # Wave 5c (2026-07-15): PBS admin job views + node odds + pull/push — CLOSES the PBS plane.
    # Admin job-view LISTs carry job comment/schedule (operator-authored config), matching
    # pbs_jobs_list's existing REVIEWED_TRUSTED precedent — argued explicitly in pbs_admin.py's
    # module docstring Taint section, not defaulted. traffic-control status = live counters
    # (cur-rate-in/cur-rate-out) + operator rule config, no attacker-shapeable free text.
    # node_config_get/set = structured operator config (http-proxy is defensively masked for any
    # embedded userinfo credential before it can reach a Plan/ledger surface — see pbs_admin.py
    # module docstring fact #10 — so even that genuinely-ambiguous field never lands unredacted).
    # node_identity = a single machine-derived identifier. node_rrd = server-authored numeric
    # telemetry, matches the pve_node_rrddata/pmg_node_rrddata/pbs_metrics_status precedent.
    # version = fixed version-identity strings. pull/push both declare returns:null (no content
    # channel to classify) — matches pbs_s3_check/pbs_s3_reset_counters's identical reasoning.
    # NOT here: pbs_node_report — in taint.ADVERSARIAL_TOOLS instead (free-text diagnostic
    # bundle, same category as pve_node_syslog/pbs_node_journal/pbs_node_task_log).
    'pbs_admin_gc_jobs_list', 'pbs_admin_prune_jobs_list', 'pbs_admin_sync_jobs_list',
    'pbs_admin_verify_jobs_list', 'pbs_admin_traffic_control_status',
    'pbs_node_config_get', 'pbs_node_config_set', 'pbs_node_identity', 'pbs_node_rrd',
    'pbs_version', 'pbs_pull', 'pbs_push',
    # Wave 5d (2026-07-15): PBS datastore-admin remainder — the ACTUAL plane closer.
    # snapshot_protected_get: argued via its paired write-half's schema-typed boolean (against
    # the media_status_get conservative default — see pbs_datastore_admin.py fact #7).
    # datastore_rrd/active_operations/datastores_usage: numeric/typed server telemetry
    # (rrddata + datastore_status precedents). Mutations: group_delete returns a closed-shape
    # counter object; group_notes_set returns null; the other six return opaque UPIDs — no
    # content channel. NOT here: pbs_groups_list, pbs_group_notes_get, pbs_remote_scan,
    # pbs_remote_scan_groups, pbs_remote_scan_namespaces — all in taint.ADVERSARIAL_TOOLS
    # (guest-influenced ids/notes; remote-authored scan content).
    'pbs_snapshot_protected_get', 'pbs_datastore_rrd', 'pbs_datastore_active_operations',
    'pbs_datastores_usage',
    'pbs_group_delete', 'pbs_group_notes_set', 'pbs_group_move', 'pbs_namespace_move',
    'pbs_datastore_mount', 'pbs_datastore_unmount', 'pbs_datastore_prune',
    'pbs_datastore_s3_refresh',
    'pbs_tasks_list',
    'pbs_tfa_add', 'pbs_tfa_delete', 'pbs_tfa_entry_get', 'pbs_tfa_list', 'pbs_tfa_unlock',
    'pbs_tfa_update', 'pbs_tfa_user_get', 'pbs_tfa_webauthn_get', 'pbs_tfa_webauthn_set',
    'pbs_token_create',
    'pbs_token_delete', 'pbs_token_update', 'pbs_traffic_control_delete',
    'pbs_traffic_control_upsert', 'pbs_traffic_controls_list', 'pbs_user_create', 'pbs_user_delete',
    'pbs_user_get', 'pbs_user_token_get', 'pbs_user_tokens_list', 'pbs_user_update', 'pbs_users_list',
    'pbs_verify_start', 'pdm_acl_list',
    'pdm_node_status', 'pdm_pbs_datastores_list', 'pdm_pbs_remote_status', 'pdm_pbs_snapshots_list', 'pdm_ping',
    'pdm_pve_cluster_status', 'pdm_pve_lxc_migrate', 'pdm_pve_lxc_power',
    'pdm_pve_lxc_remote_migrate', 'pdm_pve_lxc_snapshot_create', 'pdm_pve_lxc_snapshot_delete',
    'pdm_pve_lxc_snapshot_rollback', 'pdm_pve_node_list', 'pdm_pve_qemu_migrate',
    'pdm_pve_qemu_power', 'pdm_pve_qemu_remote_migrate', 'pdm_pve_qemu_snapshot_create',
    'pdm_pve_qemu_snapshot_delete', 'pdm_pve_qemu_snapshot_rollback', 'pdm_remote_config_get',
    'pdm_remote_version', 'pdm_remotes_list', 'pdm_resources_list', 'pdm_resources_status', 'pdm_roles_list',
    'pdm_tasks_list', 'pdm_users_list', 'pdm_version', 'pmg_action_bcc_create', 'pmg_action_bcc_update',
    'pmg_action_delete', 'pmg_action_disclaimer_create', 'pmg_action_disclaimer_update', 'pmg_action_field_create',
    'pmg_action_field_update', 'pmg_action_notification_create', 'pmg_action_notification_update',
    'pmg_action_objects_list', 'pmg_action_removeattachments_create', 'pmg_action_removeattachments_update',
    'pmg_apt_repositories_get', 'pmg_apt_repository_add', 'pmg_apt_repository_set',
    'pmg_apt_update_refresh', 'pmg_apt_updates_list', 'pmg_apt_versions',
    'pmg_backup_create', 'pmg_doctor', 'pmg_domain_create', 'pmg_domain_delete', 'pmg_domains_list',
    'pmg_mynetworks_add', 'pmg_mynetworks_remove', 'pmg_node_rrddata', 'pmg_node_status', 'pmg_postfix_flush',
    'pmg_postfix_qshape', 'pmg_quarantine_action', 'pmg_quarantine_blocklist_add',
    'pmg_quarantine_blocklist_remove', 'pmg_quarantine_welcomelist_add', 'pmg_quarantine_welcomelist_remove',
    'pmg_relay_config', 'pmg_ruledb_digest', 'pmg_ruledb_rule_action_attach', 'pmg_ruledb_rule_action_detach',
    'pmg_ruledb_rule_actions_list', 'pmg_ruledb_rule_create', 'pmg_ruledb_rule_delete',
    'pmg_ruledb_rule_from_attach', 'pmg_ruledb_rule_from_detach', 'pmg_ruledb_rule_from_list',
    'pmg_ruledb_rule_get', 'pmg_ruledb_rule_to_attach', 'pmg_ruledb_rule_to_detach', 'pmg_ruledb_rule_to_list',
    'pmg_ruledb_rule_update', 'pmg_ruledb_rule_what_attach', 'pmg_ruledb_rule_what_detach',
    'pmg_ruledb_rule_what_list', 'pmg_ruledb_rule_when_attach', 'pmg_ruledb_rule_when_detach',
    'pmg_ruledb_rule_when_list', 'pmg_ruledb_rules_list', 'pmg_service_control', 'pmg_service_status',
    'pmg_spam_config', 'pmg_spam_config_update', 'pmg_statistics_mail',
    'pmg_statistics_mailcount', 'pmg_statistics_recent', 'pmg_statistics_spamscores', 'pmg_statistics_virus',
    'pmg_tasks_list', 'pmg_transport_create', 'pmg_transport_delete', 'pmg_what_group_create',
    'pmg_what_group_delete', 'pmg_what_group_get', 'pmg_what_group_objects', 'pmg_what_group_update',
    'pmg_what_groups_list', 'pmg_what_object_add', 'pmg_what_object_delete', 'pmg_what_object_update',
    'pmg_when_group_create', 'pmg_when_group_delete', 'pmg_when_group_get', 'pmg_when_group_objects',
    'pmg_when_group_update', 'pmg_when_groups_list', 'pmg_when_object_add', 'pmg_when_object_delete',
    'pmg_when_object_update', 'pmg_who_group_create', 'pmg_who_group_delete', 'pmg_who_group_get',
    'pmg_who_group_objects', 'pmg_who_group_update', 'pmg_who_groups_list', 'pmg_who_object_add',
    'pmg_who_object_delete', 'pmg_who_object_update', 'pve_acl_list', 'pve_acl_modify', 'pve_acl_prune',
    'pve_acme_account_create', 'pve_acme_account_delete', 'pve_acme_account_update', 'pve_acme_cert_order',
    'pve_acme_cert_renew', 'pve_acme_cert_revoke', 'pve_acme_plugin_create', 'pve_acme_plugin_delete',
    'pve_acme_plugin_update', 'pve_agent_file_write', 'pve_agent_fs', 'pve_agent_set_password',
    'pve_apt_repositories_get', 'pve_apt_repository_add', 'pve_apt_repository_set',
    'pve_apt_update_refresh', 'pve_apt_updates_list', 'pve_apt_versions', 'pve_backup',
    'pve_backup_delete', 'pve_backup_job_create', 'pve_backup_job_delete', 'pve_backup_job_list',
    'pve_backup_job_update', 'pve_backup_list', 'pve_clone', 'pve_cloudinit_get', 'pve_cloudinit_set',
    'pve_cluster_status', 'pve_create_container', 'pve_create_vm', 'pve_delete_guest', 'pve_diagnose',
    'pve_disk_move', 'pve_disk_resize', 'pve_doctor', 'pve_firewall_alias_create', 'pve_firewall_alias_delete',
    'pve_firewall_alias_list', 'pve_firewall_alias_update', 'pve_firewall_ipset_create',
    'pve_firewall_ipset_delete', 'pve_firewall_ipset_entry_add', 'pve_firewall_ipset_entry_remove',
    'pve_firewall_options_get', 'pve_firewall_options_set', 'pve_firewall_rule_add', 'pve_firewall_rule_remove',
    'pve_firewall_rule_update', 'pve_firewall_rules_list', 'pve_firewall_security_group_create',
    'pve_firewall_security_group_delete', 'pve_firewall_set_enabled', 'pve_group_create', 'pve_group_delete',
    'pve_group_get', 'pve_group_update', 'pve_groups_list', 'pve_guest_config_revert', 'pve_guest_config_set',
    'pve_guest_migrate', 'pve_guest_power', 'pve_guest_status', 'pve_ha_groups_list', 'pve_ha_resource_add',
    'pve_ha_resource_remove', 'pve_ha_resources_list', 'pve_ha_rule_create', 'pve_ha_rule_delete',
    'pve_ha_rule_update', 'pve_ha_rules_list', 'pve_hardware_list', 'pve_ipset_list', 'pve_mapping_pci_create',
    'pve_mapping_pci_delete', 'pve_mapping_pci_list', 'pve_mapping_pci_update', 'pve_mapping_usb_create',
    'pve_mapping_usb_delete', 'pve_mapping_usb_list', 'pve_mapping_usb_update', 'pve_metrics_server_delete',
    'pve_metrics_server_list', 'pve_metrics_server_set', 'pve_network_apply', 'pve_network_iface_create',
    'pve_network_iface_update', 'pve_network_list', 'pve_node_acme_domains_set', 'pve_node_cert_delete',
    'pve_node_cert_upload', 'pve_node_certificates', 'pve_node_disk_initgpt', 'pve_node_disk_smart',
    'pve_node_disk_wipe', 'pve_node_disks_list', 'pve_node_dns', 'pve_node_dns_set', 'pve_node_hosts_get',
    'pve_node_hosts_set', 'pve_node_migrateall', 'pve_node_rrddata', 'pve_node_service_control',
    'pve_node_service_status', 'pve_node_services_list', 'pve_node_startall', 'pve_node_status',
    'pve_node_stopall', 'pve_node_storage_backend_create', 'pve_node_storage_backend_delete',
    'pve_node_storage_backend_list', 'pve_node_subscription', 'pve_node_time_get', 'pve_node_time_set',
    'pve_notification_endpoint_create', 'pve_notification_endpoint_delete', 'pve_notification_endpoint_list',
    'pve_notification_endpoint_update', 'pve_notification_matcher_delete', 'pve_notification_matcher_set',
    'pve_notification_test', 'pve_overbroad_grants', 'pve_pool_create', 'pve_pool_delete', 'pve_pool_get',
    'pve_pool_update', 'pve_pools_list', 'pve_realm_create', 'pve_realm_delete', 'pve_realm_get',
    'pve_realm_update', 'pve_realms_list', 'pve_replication_create', 'pve_replication_delete',
    'pve_replication_update', 'pve_restore', 'pve_role_create', 'pve_role_delete', 'pve_role_update',
    'pve_roles_list', 'pve_rollback', 'pve_sdn_apply', 'pve_sdn_subnet_create', 'pve_sdn_subnet_delete',
    'pve_sdn_subnet_list', 'pve_sdn_subnet_update', 'pve_sdn_vnet_create', 'pve_sdn_vnet_delete',
    'pve_sdn_vnet_update', 'pve_sdn_vnets_list', 'pve_sdn_zone_create', 'pve_sdn_zone_delete',
    'pve_sdn_zone_update', 'pve_sdn_zones_list', 'pve_security_groups_list', 'pve_snapshot_create',
    'pve_snapshot_delete', 'pve_storage_config_get', 'pve_storage_config_list', 'pve_storage_content_delete',
    'pve_storage_create', 'pve_storage_delete', 'pve_storage_download', 'pve_storage_status', 'pve_storage_update',
    'pve_task_status', 'pve_task_stop', 'pve_task_wait', 'pve_tasks_list', 'pve_template_convert',
    'pve_tfa_delete', 'pve_tfa_get', 'pve_tfa_list', 'pve_token_create', 'pve_token_revoke', 'pve_tokens_list',
    'pve_user_create', 'pve_user_delete', 'pve_user_get', 'pve_user_update', 'pve_users_list',
})


def _registered_names() -> list[str]:
    return [t.name for t in asyncio.run(server.mcp.list_tools())]


def test_no_obviously_adversarial_tool_hides_in_reviewed_trusted():
    """Spot-check: a handful of tools that clearly carry guest/external bytes must NOT be in
    REVIEWED_TRUSTED (they belong in taint.ADVERSARIAL_TOOLS instead)."""
    obviously_adversarial = {
        "ct_exec", "ct_psql", "ct_logs", "ct_diagnose",
        "pve_agent_exec", "pve_agent_info", "pve_agent_file_read",
        "pmg_quarantine_spam", "pmg_quarantine_virus",
    }
    assert obviously_adversarial.isdisjoint(REVIEWED_TRUSTED)
    assert obviously_adversarial <= taint.ADVERSARIAL_TOOLS


def test_adversarial_tools_are_all_really_registered():
    """Every name in taint.ADVERSARIAL_TOOLS must be a REAL tool on the live registry — catches a
    typo or a renamed/removed tool that would otherwise silently ride as "classified" while not
    actually being gated by anything."""
    names = set(_registered_names())
    missing = taint.ADVERSARIAL_TOOLS - names
    assert not missing, (
        f"taint.ADVERSARIAL_TOOLS names not found on the live registry (typo, or the tool was "
        f"renamed/removed and the classification wasn't updated): {sorted(missing)}"
    )
    assert taint.ADVERSARIAL_TOOLS <= names


def test_every_registered_tool_is_classified():
    """The completeness guard: every tool the server actually exposes must be EITHER
    adversarial-classified OR explicitly reviewed-trusted. If this fails after adding a tool,
    it means a new tool shipped unclassified — classify it (see module docstring) rather than
    silencing this test."""
    names = set(_registered_names())
    known = taint.ADVERSARIAL_TOOLS | REVIEWED_TRUSTED
    unclassified = names - known
    stale = known - names
    assert names == known, (
        "Tool classification is out of sync with the live registry.\n"
        f"Unclassified (registered but neither adversarial nor reviewed-trusted): {sorted(unclassified)}\n"
        f"Stale (classified but no longer registered): {sorted(stale)}\n"
        "Fix: classify a new tool as adversarial (guest/log/quarantine/free-text-external content) "
        "in taint.ADVERSARIAL_TOOLS, or as REVIEWED_TRUSTED in this test file (structured, "
        "operator-authored, no attacker-shapeable free text). Never add to REVIEWED_TRUSTED just "
        "to silence this test — that reintroduces the fail-open gap this test exists to close."
    )


def test_no_tool_can_clear_taint():
    """Structural invariant taint.py's docstring promises (and design-doc invariant #5): NO
    @mcp.tool clears taint — the clear is out-of-band only, the same trust boundary as CONTAIN's
    re-arm. Mirrors test_envelope.py's/test_consent.py's structural guards. `clear_taint` must never
    be referenced from the tool surface (server.py + tools/*.py); it lives only in taint.py + the
    operator-side out-of-band path. A source scan is the right shape: a tool wiring it in would be
    the exact regression this guards, and it wouldn't show up in the registry signature.
    """
    src_dir = Path(server.__file__).resolve().parent
    surface = [src_dir / "server.py", *sorted((src_dir / "tools").glob("*.py"))]
    offenders = [p.name for p in surface if "clear_taint" in p.read_text(encoding="utf-8")]
    assert not offenders, (
        f"clear_taint is referenced from the tool surface {offenders} — taint must only be cleared "
        "out-of-band (no @mcp.tool clears it). Remove the reference; the clear is an operator act."
    )
