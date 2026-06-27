#!/usr/bin/env python3
"""Live smoke test for the PDM (Proxmox Datacenter Manager) surface.

READ-ONLY: all operations are DIAGNOSE/GET — no mutations, no state changes.

Usage:
    PROXIMO_PDM_BASE_URL=https://pdm.example.com:8443 \
    PROXIMO_PDM_TOKEN_PATH=/etc/proximo/pdm-token \
    python scripts/live-smoke/pdm-smoke.py

Optional (for self-signed certs):
    PROXIMO_PDM_CA_BUNDLE=/etc/proximo/pdm-ca.crt

The token file must contain: TOKENID:SECRET  (e.g. proximo@pdm!mytoken:secret)
The token must have at least 'Auditor' privileges on PDM.

NOTE: C-group (pdm_pve_*) and D-group (pdm_pbs_*) tools require at least one
PVE or PBS remote registered in PDM. They are skipped if pdm_remotes_list()
returns an empty fleet.
"""

from __future__ import annotations

import os
import sys


def _require_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        print(f"[SKIP] {name} not set — skipping this smoke.", file=sys.stderr)
        sys.exit(0)
    return v


def _ok(name: str, result) -> None:
    print(f"  PASS  {name}")


def _skip(name: str, reason: str) -> None:
    print(f"  SKIP  {name}: {reason}")


def main() -> None:
    _require_env("PROXIMO_PDM_BASE_URL")
    _require_env("PROXIMO_PDM_TOKEN_PATH")

    # Import here so the module only loads when env is present
    from proximo.pdm import PdmBackend, PdmConfig

    cfg = PdmConfig.from_env()
    pdm = PdmBackend(cfg)

    print("--- PDM smoke (read-only) ---")

    # A: PDM self + topology
    pong = pdm.ping()
    assert pong == "pong", f"ping returned {pong!r}"
    _ok("ping", pong)

    ver = pdm.version()
    assert isinstance(ver, dict), f"version is not a dict: {ver!r}"
    assert "version" in ver, f"version missing 'version' key: {ver}"
    _ok("version", ver)

    status = pdm.node_status()
    assert isinstance(status, dict), f"node_status is not a dict: {status!r}"
    _ok("node_status (localhost)", status)

    remotes = pdm.remotes_list()
    assert isinstance(remotes, list), f"remotes_list is not a list: {remotes!r}"
    _ok("remotes_list", f"{len(remotes)} remote(s)")

    # B: Fleet aggregate
    resources = pdm.resources_list()
    assert isinstance(resources, list), f"resources_list is not a list: {resources!r}"
    _ok("resources_list", f"{len(resources)} resource(s)")

    fleet_status = pdm.resources_status()
    assert isinstance(fleet_status, dict), f"resources_status is not a dict: {fleet_status!r}"
    _ok("resources_status", fleet_status)

    # E: Tasks + access (always present)
    tasks = pdm.tasks_list()
    assert isinstance(tasks, list), f"tasks_list is not a list: {tasks!r}"
    _ok("tasks_list", f"{len(tasks)} task(s)")

    acls = pdm.acl_list()
    assert isinstance(acls, list), f"acl_list is not a list: {acls!r}"
    _ok("acl_list", f"{len(acls)} entry(ies)")

    roles = pdm.roles_list()
    assert isinstance(roles, list), f"roles_list is not a list: {roles!r}"
    _ok("roles_list", f"{len(roles)} role(s)")

    users = pdm.users_list()
    assert isinstance(users, list), f"users_list is not a list: {users!r}"
    _ok("users_list", f"{len(users)} user(s)")

    # C/D: Per-remote reads — only if remotes exist
    # /remotes/remote entries carry a "type" field ("pve" | "pbs") and an "id" field.
    pve_remotes = [r for r in remotes if r.get("type") == "pve"]
    pbs_remotes = [r for r in remotes if r.get("type") == "pbs"]

    if not remotes:
        _skip("pdm_pve_* / pdm_pbs_*", "no remotes registered in PDM")
    else:
        # Use first available remote for a basic path-shaping check
        first = remotes[0]
        rid = first.get("id") or first.get("name") or ""
        if not rid:
            _skip("remote probe", f"could not determine remote id from: {first}")
        else:
            ver_remote = pdm.remote_version(rid)
            assert isinstance(ver_remote, dict), f"remote_version is not a dict: {ver_remote!r}"
            _ok(f"remote_version({rid!r})", ver_remote)

            cfg_remote = pdm.remote_config_get(rid)
            assert isinstance(cfg_remote, dict), f"remote_config_get is not a dict: {cfg_remote!r}"
            _ok(f"remote_config_get({rid!r})", cfg_remote)

            # Attempt PVE-style probes (live-prove-pending: shape verified when fleet populated)
            if pve_remotes:
                pve_id = (pve_remotes[0].get("id") or pve_remotes[0].get("name") or "")
                if pve_id:
                    res_list = pdm.pve_resources(pve_id)
                    assert isinstance(res_list, list)
                    _ok(f"pve_resources({pve_id!r})", f"{len(res_list)} resource(s)")
                else:
                    _skip("pve_resources", "could not determine PVE remote id")
            else:
                _skip("pve_resources / pve_cluster_status / pve_node_list", "no PVE remotes found")

            if pbs_remotes:
                pbs_id = (pbs_remotes[0].get("id") or pbs_remotes[0].get("name") or "")
                if pbs_id:
                    pbs_status = pdm.pbs_remote_status(pbs_id)
                    assert isinstance(pbs_status, dict)
                    _ok(f"pbs_remote_status({pbs_id!r})", pbs_status)

                    ds_list = pdm.pbs_datastores_list(pbs_id)
                    assert isinstance(ds_list, list)
                    _ok(f"pbs_datastores_list({pbs_id!r})", f"{len(ds_list)} datastore(s)")

                    if ds_list:
                        ds_name = ds_list[0].get("name") or ds_list[0].get("store") or ""
                        if ds_name:
                            snaps = pdm.pbs_snapshots_list(pbs_id, ds_name)
                            assert isinstance(snaps, list)
                            _ok(f"pbs_snapshots_list({pbs_id!r}, {ds_name!r})",
                                f"{len(snaps)} snapshot(s)")
                        else:
                            _skip("pbs_snapshots_list", "could not determine datastore name")
                    else:
                        _skip("pbs_snapshots_list", "no datastores on remote")
                else:
                    _skip("pbs_remote_status / pbs_datastores_list", "could not determine PBS remote id")
            else:
                _skip("pbs_remote_status / pbs_datastores_list / pbs_snapshots_list",
                      "no PBS remotes found")

    print("--- PDM smoke complete ---")


if __name__ == "__main__":
    main()
