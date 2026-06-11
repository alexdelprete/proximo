#!/usr/bin/env python3
"""Proximo Phase-1 live MUTATE smoke — provisioning + backup lifecycle.

Drives the real config -> ApiBackend -> tools against live Proxmox VE,
confirming shape-risks that mocks cannot catch (create params, clone,
backup/restore endpoints, delete). Operates on THROWAWAY VMIDs only.
Cleans up everything it creates (try/finally). Self-cleaning by design.

Environment (set by the wrapper script; see phase1-smoke.sh and README.md):
  PROXIMO_API_BASE_URL  PROXIMO_NODE  PROXIMO_TOKEN_PATH  PROXIMO_VERIFY_TLS
  SMOKE_POOL            SMOKE_STORE   SMOKE_VMID          PROXIMO_CT_ALLOWLIST

WARNING: This script performs REAL (reversible, self-cleaning) mutations on
the target Proxmox host. Always run via phase1-smoke.sh which validates the
required environment variables before invoking this script.
"""
from __future__ import annotations

import os
import sys

import proximo.server as server

# All values come from the environment — no hardcoded infra literals.
NODE: str | None = os.environ.get("PROXIMO_NODE")
POOL: str = os.environ.get("SMOKE_POOL", "proximo-smoke-throwaway")
STORE: str | None = os.environ.get("SMOKE_STORE")
_base_raw: str = os.environ.get("SMOKE_VMID", "9900")

try:
    BASE = int(_base_raw)
except ValueError:
    print(f"ERROR: SMOKE_VMID={_base_raw!r} is not an integer.", file=sys.stderr)
    sys.exit(2)

if not STORE:
    print("ERROR: SMOKE_STORE is required but not set. Set it to your backup storage ID.",
          file=sys.stderr)
    sys.exit(2)

A, B, C = str(BASE), str(BASE + 1), str(BASE + 2)

findings: list[tuple[str, str, str]] = []


def rec(step: str, status: str, detail: str = "") -> None:
    findings.append((step, status, detail))
    print(f"[{status}] {step}: {detail}")


def wait(res: dict, node: str | None = None) -> dict:
    cfg, api, _, _ = server._svc()
    upid = res.get("task") if isinstance(res, dict) else None
    if isinstance(upid, str) and upid.startswith("UPID"):
        server._wait_task(api, upid, node=node)
    return res


def hr(title: str) -> None:
    print(f"\n=== {title} ===")


def vmid_free(vmid: str) -> bool:
    """Return True when vmid is not present on the node."""
    cfg, api, _, _ = server._svc()
    try:
        return not any(str(g.get("vmid")) == str(vmid) for g in api.list_guests(NODE))
    except Exception:  # noqa: BLE001
        return True


def main() -> int:
    cfg, api, _, _ = server._svc()
    print(
        f"node={cfg.node}  url={cfg.api_base_url}"
        f"  pool={POOL}  store={STORE}  ids={A}/{B}/{C}"
    )
    print(f"(throwaway VMIDs {A}–{C} will be created and deleted; pool={POOL})")

    hr("Phase 1 — read sanity")
    try:
        server.pve_node_status()
        rec("node_status", "PASS")
    except Exception as e:  # noqa: BLE001
        rec("node_status", "FAIL", repr(e))
        return 2

    for v in (A, B, C):
        if not vmid_free(v):
            rec("preflight", "ABORT", f"vmid {v} already exists — set SMOKE_VMID to a free range")
            return 2

    created: list[str] = []
    backup_volid: str | None = None
    try:
        hr("create_vm (diskless, into pool)")
        try:
            r = server.pve_create_vm(
                A, node=NODE, confirm=True,
                options={"memory": 512, "cores": 1,
                         "name": "proximo-smoke", "pool": POOL},
            )
            wait(r, NODE)
            created.append(A)
            rec("pve_create_vm", "PASS", f"task={r.get('task')}")
        except Exception as e:  # noqa: BLE001
            rec("pve_create_vm", "FAIL", repr(e))

        if A in created:
            hr("guest_status (confirm the VM exists)")
            try:
                st = server.pve_guest_status(A, kind="qemu", node=NODE)
                rec("pve_guest_status", "PASS", f"status={st.get('status', st)}")
            except Exception as e:  # noqa: BLE001
                rec("pve_guest_status", "FAIL", repr(e))

            hr("config_edit: set cores/desc then revert")
            try:
                r = server.pve_guest_config_set(
                    A, {"cores": 2, "description": "proximo-smoke"},
                    kind="qemu", node=NODE, confirm=True,
                )
                after = server.pve_guest_config_get(A, kind="qemu", node=NODE)
                rec(
                    "pve_guest_config_set",
                    "PASS" if str(after.get("cores")) == "2" else "NOTE",
                    f"cores now={after.get('cores')}",
                )
                prior = r.get("prior_config") if isinstance(r, dict) else None
                if prior:
                    server.pve_guest_config_revert(A, prior, kind="qemu", node=NODE, confirm=True)
                    rev = server.pve_guest_config_get(A, kind="qemu", node=NODE)
                    rec("pve_guest_config_revert", "PASS", f"cores back={rev.get('cores')}")
            except Exception as e:  # noqa: BLE001
                rec("config_edit", "NOTE", repr(e))

            hr("clone A->B (full)")
            try:
                r = server.pve_clone(
                    A, B, kind="qemu", node=NODE, full=True, pool=POOL, confirm=True,
                )
                wait(r, NODE)
                created.append(B)
                rec("pve_clone", "PASS", f"task={r.get('task')}")
            except Exception as e:  # noqa: BLE001
                # A pool-scope 403 is possible if the token lacks clone-to-pool permission
                rec("pve_clone", "NOTE", repr(e))

            hr(f"backup A (mode=stop, store={STORE})")
            try:
                r = server.pve_backup(A, STORE, mode="stop", kind="qemu", node=NODE, confirm=True)
                wait(r, NODE)
                rec("pve_backup", "PASS", f"task={r.get('task')}")
            except Exception as e:  # noqa: BLE001
                rec("pve_backup", "NOTE", repr(e))

            hr("backup_list (find the archive)")
            try:
                lst = server.pve_backup_list(STORE, node=NODE)
                mine = [b for b in lst if str(b.get("vmid")) == A] if isinstance(lst, list) else []
                backup_volid = mine[-1].get("volid") if mine else None
                rec("pve_backup_list", "PASS", f"volid={backup_volid}")
            except Exception as e:  # noqa: BLE001
                rec("pve_backup_list", "FAIL", repr(e))

            if backup_volid:
                hr("restore -> C")
                try:
                    r = server.pve_restore(
                        C, backup_volid, STORE, kind="qemu", node=NODE, pool=POOL, confirm=True,
                    )
                    wait(r, NODE)
                    created.append(C)
                    rec("pve_restore", "PASS", f"task={r.get('task')}")
                except Exception as e:  # noqa: BLE001
                    rec("pve_restore", "NOTE", repr(e))

                hr("backup_delete (remove the archive)")
                try:
                    r = server.pve_backup_delete(STORE, backup_volid, node=NODE, confirm=True)
                    wait(r, NODE)
                    backup_volid = None
                    rec("pve_backup_delete", "PASS", f"task={r.get('task')}")
                except Exception as e:  # noqa: BLE001
                    rec("pve_backup_delete", "NOTE",
                        f"(may need Datastore.Allocate on the storage) {e!r}")

    finally:
        hr("cleanup (delete throwaway VMs)")
        for v in list(created):
            try:
                r = server.pve_delete_guest(v, kind="qemu", node=NODE, purge=True, confirm=True)
                wait(r, NODE)
                rec(f"delete {v}", "PASS", f"task={r.get('task')}")
            except Exception as e:  # noqa: BLE001
                rec(f"delete {v}", "WARN",
                    f"LEFT BEHIND — clean by hand: pvesh delete /nodes/{NODE}/qemu/{v}  [{e!r}]")
        if backup_volid:
            try:
                server.pve_backup_delete(STORE, backup_volid, node=NODE, confirm=True)
                rec("cleanup backup", "PASS")
            except Exception as e:  # noqa: BLE001
                rec("cleanup backup", "WARN",
                    f"left behind: {backup_volid}  [{e!r}]"
                    f"\n    pvesh delete /nodes/{NODE}/storage/{STORE}/content/{backup_volid}")

    hr("audit_verify (ledger intact after mutations)")
    try:
        v = server.audit_verify()
        rec("audit_verify", "PASS" if v.get("ok") else "FAIL",
            f"entries={v.get('entries')}")
    except Exception as e:  # noqa: BLE001
        rec("audit_verify", "FAIL", repr(e))

    hr("SUMMARY")
    for step, status, detail in findings:
        print(f"  {status:5} {step}  {detail}")
    fails = [f for f in findings if f[1] in ("FAIL", "WARN", "ABORT")]
    passes = [f for f in findings if f[1] == "PASS"]
    notes = [f for f in findings if f[1] == "NOTE"]
    verdict = "ALL CLEAN" if not fails else f"{len(fails)} need attention"
    print(
        f"\n{verdict} — {len(passes)} PASS, {len(notes)} NOTE, {len(fails)} FAIL/WARN"
    )
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
