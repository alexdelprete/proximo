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

EXPECTED_TOOL_COUNT = 603  # +17 (Wave 5d — the ACTUAL PBS plane closer, built from the Wave 5c
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
