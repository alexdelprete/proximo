"""PDM (Proxmox Datacenter Manager) read-only tools.

Split out of proximo.server (2026-07-02) — see proximo/server.py's module
docstring for the funnel these wrappers depend on.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

import proximo.server as _proximo_server
from proximo.server import (
    _audited,
    tool,
)

# --- PDM (Proxmox Datacenter Manager) read-only ---

@tool()
def pdm_ping() -> str:
    """DIAGNOSE (LOW): health check the PDM appliance. Returns 'pong' on success.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_ping", "pdm/ping", lambda: pdm.ping())


@tool()
def pdm_version() -> dict:
    """DIAGNOSE (LOW): get PDM appliance version (release, repoid, version).
    Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_version", "pdm/version", lambda: pdm.version())


@tool()
def pdm_node_status(
    node: Annotated[str, Field(description="PDM node name; PDM is single-node so this defaults to 'localhost'.")] = "localhost",
) -> dict:
    """DIAGNOSE (LOW): get resource stats for a PDM node. Defaults to 'localhost'
    (PDM is a single-node appliance). Shape equals PVE node status;
    live-prove-pending. Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_node_status", f"pdm/nodes/{node}", lambda: pdm.node_status(node))


@tool()
def pdm_remotes_list() -> list[dict]:
    """DIAGNOSE (LOW): list all PVE/PBS remotes registered in PDM.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_remotes_list", "pdm/remotes", lambda: pdm.remotes_list())


@tool()
def pdm_remote_version(
    remote_id: Annotated[str, Field(description="Remote name as shown in pdm_remotes_list.")],
) -> dict:
    """DIAGNOSE (LOW): get version info for one PDM-registered remote.
    remote_id: the remote name as shown in pdm_remotes_list.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_remote_version", f"pdm/remotes/{remote_id}",
                    lambda: pdm.remote_version(remote_id))


@tool()
def pdm_remote_config_get(
    remote_id: Annotated[str, Field(description="Remote name as shown in pdm_remotes_list.")],
) -> dict:
    """DIAGNOSE (LOW): get configuration for one PDM-registered remote (no secrets returned).
    remote_id: the remote name as shown in pdm_remotes_list.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_remote_config_get", f"pdm/remotes/{remote_id}",
                    lambda: pdm.remote_config_get(remote_id))


@tool()
def pdm_resources_list() -> list[dict]:
    """DIAGNOSE (LOW): list all fleet resources (VMs, LXCs, storage, etc.) across all remotes.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_resources_list", "pdm/resources/list", lambda: pdm.resources_list())


@tool()
def pdm_resources_status() -> dict:
    """DIAGNOSE (LOW): aggregated fleet status counters (running VMs, LXCs, failed remotes, etc.).
    Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_resources_status", "pdm/resources/status",
                    lambda: pdm.resources_status())


@tool()
def pdm_pve_resources(
    remote: Annotated[str, Field(description="PDM-registered PVE remote name, from pdm_remotes_list.")],
    kind: Annotated[str | None, Field(description="Optional resource-type filter, e.g. 'vm', 'storage', 'node', 'sdn'.")] = None,
) -> list[dict]:
    """DIAGNOSE (LOW): list resources on a PDM-registered PVE remote.
    remote: remote name from pdm_remotes_list.
    kind: optional filter (vm, storage, node, sdn, ...).
    Shape equals PVE cluster/resources; live-proven 2026-06-27 against a registered PVE remote.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_pve_resources", f"pdm/pve/{remote}/resources",
                    lambda: pdm.pve_resources(remote, kind))


@tool()
def pdm_pve_cluster_status(
    remote: Annotated[str, Field(description="PDM-registered PVE remote name, from pdm_remotes_list.")],
) -> list[dict]:
    """DIAGNOSE (LOW): get cluster status for a PDM-registered PVE remote.
    remote: remote name from pdm_remotes_list.
    Shape equals PVE cluster/status; live-proven 2026-06-27 against a registered PVE remote.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_pve_cluster_status", f"pdm/pve/{remote}/cluster-status",
                    lambda: pdm.pve_cluster_status(remote))


@tool()
def pdm_pve_node_list(
    remote: Annotated[str, Field(description="PDM-registered PVE remote name, from pdm_remotes_list.")],
) -> list[dict]:
    """DIAGNOSE (LOW): list nodes in a PDM-registered PVE remote.
    remote: remote name from pdm_remotes_list.
    Shape equals PVE /nodes; live-proven 2026-06-27 against a registered PVE remote.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_pve_node_list", f"pdm/pve/{remote}/nodes",
                    lambda: pdm.pve_node_list(remote))


@tool()
def pdm_pve_qemu_list(
    remote: Annotated[str, Field(description="PDM-registered PVE remote name, from pdm_remotes_list.")],
    node: Annotated[str | None, Field(description="Optional PVE node name to restrict the listing to; omit to list cluster-wide.")] = None,
) -> list[dict]:
    """DIAGNOSE (LOW): list VMs across a PDM-registered PVE remote (cluster-wide).
    remote: remote name. node: OPTIONAL filter to one PVE node.
    Shape equals PVE qemu list; live-proven 2026-06-27 against a registered PVE remote.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_pve_qemu_list", f"pdm/pve/{remote}/qemu",
                    lambda: pdm.pve_qemu_list(remote, node))


@tool()
def pdm_pve_qemu_config(
    remote: Annotated[str, Field(description="PDM-registered PVE remote name, from pdm_remotes_list.")],
    vmid: Annotated[str, Field(description="Numeric VM ID on the remote.")],
    node: Annotated[str | None, Field(description="Optional PVE node name; not required for PDM to resolve the VM.")] = None,
    snapshot: Annotated[str | None, Field(description="Optional snapshot name to read config from instead of the live config.")] = None,
    state: Annotated[str, Field(description="PDM config-state selector, required by the PDM API; 'active' returns the current config.")] = "active",
) -> dict:
    """DIAGNOSE (LOW): get VM config from a PDM-registered PVE remote.
    remote: remote name. vmid: numeric VM ID.
    node, snapshot: optional query params (node is NOT required).
    state: REQUIRED by PDM ("active" = current config) — defaults to "active"; PDM 400s if omitted.
    Live-proven 2026-06-27 against a registered PVE remote. Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_pve_qemu_config", f"pdm/pve/{remote}/qemu/{vmid}",
                    lambda: pdm.pve_qemu_config(remote, vmid, node, snapshot, state))


@tool()
def pdm_pve_lxc_list(
    remote: Annotated[str, Field(description="PDM-registered PVE remote name, from pdm_remotes_list.")],
    node: Annotated[str | None, Field(description="Optional PVE node name to restrict the listing to; omit to list cluster-wide.")] = None,
) -> list[dict]:
    """DIAGNOSE (LOW): list LXC containers across a PDM-registered PVE remote (cluster-wide).
    remote: remote name. node: OPTIONAL filter to one PVE node.
    Shape equals PVE lxc list; live-proven 2026-06-27 against a registered PVE remote.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_pve_lxc_list", f"pdm/pve/{remote}/lxc",
                    lambda: pdm.pve_lxc_list(remote, node))


@tool()
def pdm_pve_lxc_config(
    remote: Annotated[str, Field(description="PDM-registered PVE remote name, from pdm_remotes_list.")],
    vmid: Annotated[str, Field(description="Numeric CT ID on the remote.")],
    node: Annotated[str | None, Field(description="Optional PVE node name; not required for PDM to resolve the container.")] = None,
    snapshot: Annotated[str | None, Field(description="Optional snapshot name to read config from instead of the live config.")] = None,
    state: Annotated[str, Field(description="PDM config-state selector, required by the PDM API; 'active' returns the current config.")] = "active",
) -> dict:
    """DIAGNOSE (LOW): get LXC config from a PDM-registered PVE remote.
    remote: remote name. vmid: numeric CT ID.
    node, snapshot: optional query params (node is NOT required).
    state: REQUIRED by PDM ("active" = current config) — defaults to "active"; PDM 400s if omitted.
    Live-proven 2026-06-27 against a registered PVE remote. Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_pve_lxc_config", f"pdm/pve/{remote}/lxc/{vmid}",
                    lambda: pdm.pve_lxc_config(remote, vmid, node, snapshot, state))


@tool()
def pdm_pbs_remote_status(
    remote: Annotated[str, Field(description="PDM-registered PBS remote name, from pdm_remotes_list.")],
) -> dict:
    """DIAGNOSE (LOW): get node status for a PDM-registered PBS remote.
    remote: remote name from pdm_remotes_list.
    Live-verified (PDM 1.1 -> PBS 4.2).
    Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_pbs_remote_status", f"pdm/pbs/{remote}/status",
                    lambda: pdm.pbs_remote_status(remote))


@tool()
def pdm_pbs_datastores_list(
    remote: Annotated[str, Field(description="PDM-registered PBS remote name, from pdm_remotes_list.")],
) -> list[dict]:
    """DIAGNOSE (LOW): list datastores on a PDM-registered PBS remote.
    remote: remote name from pdm_remotes_list.
    Live-verified shape: [{"name","path"}, ...] (PDM 1.1 -> PBS 4.2).
    Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_pbs_datastores_list", f"pdm/pbs/{remote}/datastore",
                    lambda: pdm.pbs_datastores_list(remote))


@tool()
def pdm_pbs_snapshots_list(
    remote: Annotated[str, Field(description="PDM-registered PBS remote name, from pdm_remotes_list.")],
    datastore: Annotated[str, Field(description="PBS datastore name on the remote to list snapshots from.")],
    ns: Annotated[str | None, Field(description="Optional PBS namespace filter; omit to use the default namespace.")] = None,
) -> list[dict]:
    """DIAGNOSE (LOW): list backup snapshots in a datastore on a PDM-registered PBS remote.
    remote: remote name. datastore: PBS datastore name. ns: optional namespace filter.
    Live-verified path (PDM 1.1 -> PBS 4.2); empty datastore returns [].
    Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_pbs_snapshots_list",
                    f"pdm/pbs/{remote}/datastore/{datastore}/snapshots",
                    lambda: pdm.pbs_snapshots_list(remote, datastore, ns))


@tool()
def pdm_tasks_list() -> list[dict]:
    """DIAGNOSE (LOW): list recent PDM tasks across all remotes.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_tasks_list", "pdm/remotes/tasks", lambda: pdm.tasks_list())


@tool()
def pdm_acl_list(
    path: Annotated[str | None, Field(description="Optional ACL path filter, e.g. '/'; omit to list all entries.")] = None,
    exact: Annotated[bool, Field(description="If true, match the given path exactly rather than including sub-paths.")] = False,
) -> list[dict]:
    """DIAGNOSE (LOW): list PDM access control entries.
    path: optional ACL path filter (e.g. '/'). exact: if True, exact path only.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_acl_list", "pdm/access/acl",
                    lambda: pdm.acl_list(path, exact))


@tool()
def pdm_roles_list() -> list[dict]:
    """DIAGNOSE (LOW): list all roles and their privileges defined in PDM.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_roles_list", "pdm/access/roles", lambda: pdm.roles_list())


@tool()
def pdm_users_list(
    include_tokens: Annotated[bool, Field(description="If true, include API token entries alongside user accounts.")] = False,
) -> list[dict]:
    """DIAGNOSE (LOW): list all PDM users.
    include_tokens: if True, include API token entries.
    Needs PROXIMO_PDM_* config."""
    _, pdm = _proximo_server._pdm()
    return _audited("pdm_users_list", "pdm/access/users",
                    lambda: pdm.users_list(include_tokens))
