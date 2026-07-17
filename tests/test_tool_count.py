"""Pin the MCP tool surface count so doc/count drift can't recur.

History: a session once chased a phantom "145 vs 146" discrepancy. The 146 was a
`grep -c '@mcp.tool()'` artifact — it counted the prose mention of `@mcp.tool()` in
server.py's module docstring as if it were a decorator. The authoritative count is the
FastMCP registry (`mcp.list_tools()`), which dedupes by tool name. This test makes the
number machine-checked: bump EXPECTED_TOOL_COUNT *intentionally* when you add/remove a
tool (same discipline as the version), never let it drift silently.

The second test catches a real bug: if two functions register under the same tool name,
the registry silently keeps one and drops the other (a "lost tool"). That shows up as
real-decorators > registry-entries — so we count the actual decorator LINES (anchored to
line-start, which excludes docstring/comment mentions) and require them to equal the
exposed surface. The equality also proves no decorator is env-gated (e.g. an exec-mode
tool behind a flag) — a conditional one would make the unconditional source count exceed
the runtime count.

Decorator lines are counted across server.py AND every per-plane submodule under
`proximo/tools/` (2026-07-02 split): server.py keeps the mutation funnel (mcp, tool, the
5-gate wiring) plus the three manual-audit-path exec tools, while the ~348 thin per-plane
wrappers now live in `proximo/tools/*.py` and are re-imported into server.py by name for
registration + `server.<tool>` surface parity. The registry is still the single source of
truth for the exposed count; this just widens WHERE we look for the source-level decorator
count it's compared against.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import proximo.server as server

EXPECTED_TOOL_COUNT = 715  # +15 (Wave 7d — SDN fabrics, the FINAL chunk of Wave 7, new
# sdn_fabrics.py/tools/pve_sdn_fabrics.py): pve_sdn_fabrics_all, pve_sdn_fabrics_list,
# pve_sdn_fabric_get, pve_sdn_fabric_nodes_list_all, pve_sdn_fabric_nodes_list,
# pve_sdn_fabric_node_get, pve_sdn_fabric_status_interfaces, pve_sdn_fabric_status_neighbors,
# pve_sdn_fabric_status_routes (9 reads) + pve_sdn_fabric_create, pve_sdn_fabric_update,
# pve_sdn_fabric_delete, pve_sdn_fabric_node_create, pve_sdn_fabric_node_update,
# pve_sdn_fabric_node_delete (6 mutations). 3 confirmed upstream copy-paste description bugs
# on this family (GET fabric/{id} says "Update a fabric", DELETE fabric/{id} says "Add a
# fabric", DELETE node says "Add a node") — trusted verb/params/returns throughout, never the
# description string. fabric/fabric-node DELETE accept NEITHER digest NOR lock-token — the
# only delete family on the whole SDN plane with zero optimistic-lock support (schema-
# verified). fabric/fabric-node UPDATE require restating `protocol` in the body (unlike
# controller/dns/ipam's own immutable-and-absent `type`). fabric_status_interfaces is
# REVIEWED_TRUSTED (local, not peer-controlled); neighbors/routes are ADVERSARIAL
# (wire-learned FRR-reported content) — see taint.py's own entry comment. This CLOSES Wave 7
# (7a+7b+7c+7d+7e = 12+10+16+15+17 = 70 new tools + 1 signature extension, 645 -> 715).
# Was 700 after Wave 7e — SDN prefix-lists + route-maps, new
# sdn_routing.py/tools/pve_sdn_routing.py): pve_sdn_prefix_lists_list, pve_sdn_prefix_list_get,
# pve_sdn_prefix_list_entries_list, pve_sdn_prefix_list_entry_get, pve_sdn_route_maps_list,
# pve_sdn_route_map_entries_list_all, pve_sdn_route_map_entries_list, pve_sdn_route_map_entry_get
# (8 reads) + pve_sdn_prefix_list_create, pve_sdn_prefix_list_update, pve_sdn_prefix_list_delete,
# pve_sdn_prefix_list_entry_create, pve_sdn_prefix_list_entry_update,
# pve_sdn_prefix_list_entry_delete, pve_sdn_route_map_entry_create, pve_sdn_route_map_entry_update,
# pve_sdn_route_map_entry_delete (9 mutations). `url_seq` (prefix-list entry path segment) is an
# OPAQUE, schema-untyped token — never validated as an integer, unlike route-map's own `order`
# (a properly-typed required integer 0-65535 on all 3 of its methods). Route-maps have NO
# container-level create/update/delete — only entries (the first entry_create for an id
# implicitly creates the route map). No secret-shaped field on this plane (unlike Wave 7c's dns
# key/ipam token) — REVIEWED_TRUSTED throughout. Was 683 after Wave 7c — SDN controllers + DNS +
# IPAMs, new
# sdn_objects.py/tools/pve_sdn_objects.py): pve_sdn_controllers_list, pve_sdn_controller_get,
# pve_sdn_dns_list, pve_sdn_dns_get, pve_sdn_ipams_list, pve_sdn_ipam_get,
# pve_sdn_ipam_status (7 reads) + pve_sdn_controller_create, pve_sdn_controller_update,
# pve_sdn_controller_delete, pve_sdn_dns_create, pve_sdn_dns_update, pve_sdn_dns_delete,
# pve_sdn_ipam_create, pve_sdn_ipam_update, pve_sdn_ipam_delete (9 mutations). `type` is
# immutable after creation across all three families; dns `key`/ipam `token` are secrets
# (redacted in plan/ledger CAPTURE, never at the read layer — see sdn_objects.py's module
# docstring RULING). Was 667 after Wave 7b — vnet-scoped firewall + IP mappings, new
# sdn_firewall.py/tools/pve_sdn_firewall.py): pve_sdn_vnet_firewall_options_get,
# pve_sdn_vnet_firewall_rules_list, pve_sdn_vnet_firewall_rule_get (3 reads) +
# pve_sdn_vnet_firewall_options_set, pve_sdn_vnet_firewall_rule_add,
# pve_sdn_vnet_firewall_rule_update, pve_sdn_vnet_firewall_rule_remove,
# pve_sdn_vnet_ip_create, pve_sdn_vnet_ip_update, pve_sdn_vnet_ip_delete (7 mutations).
# LIVE/IMMEDIATE family — no pending/apply lifecycle, no sdn-rollback coverage. Was 657
# after Wave 7a — PVE SDN gap-fill + global control plane):
# pve_sdn_zone_get, pve_sdn_vnet_get, pve_sdn_subnet_get, pve_sdn_dry_run,
# pve_sdn_zone_status_list, pve_sdn_zone_bridges, pve_sdn_zone_content, pve_sdn_zone_ip_vrf,
# pve_sdn_vnet_mac_vrf (9 reads) + pve_sdn_lock_acquire, pve_sdn_lock_release, pve_sdn_rollback
# (3 mutations). pve_sdn_apply also gained optional lock_token/release_lock params — a
# signature extension on an EXISTING tool, not counted as a new one. Was 645 after Wave 6d —
# PVE Ceph pools + CephFS, CLOSES Wave 6):
# pve_ceph_pool_list, pve_ceph_pool_status, pve_ceph_fs_list (3 reads) + pve_ceph_pool_create,
# pve_ceph_pool_set, pve_ceph_pool_destroy, pve_ceph_fs_create, pve_ceph_fs_destroy
# (5 mutations). Was 637 after Wave 6c — PVE Ceph OSD): pve_ceph_osd_tree, pve_ceph_osd_lv_info,
# pve_ceph_osd_metadata (3 reads) + pve_ceph_osd_create, pve_ceph_osd_destroy, pve_ceph_osd_in,
# pve_ceph_osd_out, pve_ceph_osd_scrub (5 mutations). Was 629 after Wave 6b — PVE Ceph services
# lifecycle: pve_ceph_mon_list,
# pve_ceph_mgr_list, pve_ceph_mds_list (3 reads) + pve_ceph_mon_create, pve_ceph_mon_destroy,
# pve_ceph_mgr_create, pve_ceph_mgr_destroy, pve_ceph_mds_create, pve_ceph_mds_destroy,
# pve_ceph_init, pve_ceph_service_start, pve_ceph_service_stop, pve_ceph_service_restart
# (10 mutations). Was 616 after Wave 6a (PVE Ceph core observability + flags, the first Ceph
# chunk): pve_ceph_status, pve_ceph_metadata, pve_ceph_flags_list, pve_ceph_flag_get,
# pve_ceph_cfg_db, pve_ceph_cfg_raw, pve_ceph_cfg_value, pve_ceph_crush, pve_ceph_log,
# pve_ceph_rules, pve_ceph_cmd_safety (11 reads) + pve_ceph_flags_set, pve_ceph_flag_set
# (2 mutations). Was 603 after Wave 5d — the ACTUAL PBS plane closer, built from the Wave 5c
# adversarial review's Finding 1+2 missing-endpoint list): pbs_groups_list, pbs_group_delete,
# pbs_group_notes_{get,set}, pbs_group_move, pbs_snapshot_protected_get, pbs_namespace_move,
# pbs_datastore_{mount,unmount,prune,s3_refresh,rrd,active_operations}, pbs_datastores_usage,
# pbs_remote_scan, pbs_remote_scan_{groups,namespaces}. Was 586 after Wave 5c's
# +13: pbs_admin_{gc,prune,sync,verify}_jobs_list,
# pbs_admin_traffic_control_status, pbs_node_{config_get,config_set,identity,rrd,report},
# pbs_version, pbs_pull, pbs_push — PBS admin job views + node odds + pull/push, Wave 5c
# (CLOSES Wave 5 / the PBS plane). The task brief estimated ~17; 3 were dedup'd against the
# already-shipped generic pbs_job_run(job_type, job_id) (which already covers
# /admin/{prune,sync,verify}/{id}/run) and 1 (/ping) was skipped per the brief's own default —
# see pbs_admin.py module docstring's NOT BUILT section. Was 573 after Wave 5b's +12:
# pbs_metrics_servers_list, pbs_metrics_status,
# pbs_metrics_influxdb_http_{list,get,create,update,delete},
# pbs_metrics_influxdb_udp_{list,get,create,update,delete} — PBS metrics servers, Wave 5b
# (continues Wave 5, closes the PBS plane after 5c). Was 561 after Wave 5a's +12:
# pbs_s3_{client_list,client_get,client_create,client_update,client_delete,list_buckets,check,
# reset_counters} + pbs_encryption_key_{list,create,delete,toggle_archive} — PBS S3 client
# configs + client encryption keys (starts Wave 5). Was 549 after Wave 4d's +15:
# pbs_tape_media_{list,content,sets,status_get,destroy,status_set,move} +
# pbs_tape_backup_job_{list,get,create,update,delete,run} + pbs_tape_backup + pbs_tape_restore —
# PBS tape media catalog + tape-backup jobs + backup/restore (CLOSES Wave 4: PBS tape).

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "src" / "proximo" / "tools"
_SOURCE_FILES = [Path(server.__file__), *sorted(_TOOLS_DIR.glob("*.py"))]
_SERVER_SRC = "\n".join(p.read_text(encoding="utf-8") for p in _SOURCE_FILES)
# A real decorator: the line, after optional indentation, starts with `@mcp.tool(`. The
# line-start anchor (not the parens) is what excludes the backtick-wrapped mention inside
# the module docstring; matching `@mcp.tool(` rather than `@mcp.tool()` also stays correct
# if a tool is ever registered with an explicit name= argument.
# Matches both the plain FastMCP decorator (@mcp.tool(...)) and the target-aware wrapper
# (@tool(...)) that wraps it for multi-target — both register exactly one exposed tool.
_DECORATOR_RE = re.compile(r"^[ \t]*@(?:mcp\.)?tool\(", re.MULTILINE)


def _exposed_tools() -> list[str]:
    return [t.name for t in asyncio.run(server.mcp.list_tools())]


def test_exposed_tool_count_is_pinned():
    names = _exposed_tools()
    assert len(names) == EXPECTED_TOOL_COUNT, (
        f"tool surface changed: registry exposes {len(names)}, expected "
        f"{EXPECTED_TOOL_COUNT}. If intentional, bump EXPECTED_TOOL_COUNT and the count "
        f"in README.md / CHANGELOG.md / CLAUDE.md."
    )


def test_no_silently_shadowed_tools():
    """Every @mcp.tool() decorator must yield a distinct exposed tool.

    The registry is name-keyed, so a same-name collision never shows up as a *duplicate* —
    it shows up as a *missing* entry. So the meaningful guard is decorator-lines == exposed
    count; if two decorators share a name, one is dropped and this assertion fires.
    """
    names = _exposed_tools()
    decorator_count = len(_DECORATOR_RE.findall(_SERVER_SRC))
    assert decorator_count == len(names), (
        f"{decorator_count} @mcp.tool() decorators but only {len(names)} tools exposed — "
        f"a tool name collides and is being silently shadowed (lost tool)."
    )
