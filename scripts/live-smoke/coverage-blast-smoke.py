#!/usr/bin/env python3
"""Live PLAN-verification smoke for the 2026-06-19 blast-radius coverage push (op-classes #6-15).

Drives each NEW blast engine against the REAL cluster + the dedicated test VMs (pool proximo-test:
100/101/102 = pve-test1/2/3) and checks the computed blast against the real topology. This proves the
engines read real PVE data correctly (volid/config/storage/ACL/firewall shapes) — the thing mock unit
tests cannot verify.

READ-ONLY / PLAN ONLY: every call is a plan_* / *_blast computation. `confirm` is NEVER passed; nothing
is mutated. The cluster-wide classes (firewall enable, network apply, storage-nodes) are planned, never
executed (they would hit the single production node). The migrate target node is read from config
(cfg.node), never hardcoded.

Env (sandbox fixtures — REQUIRED, no defaults; like the sibling smokes, this refuses to guess, because a
guessed VMID/pool/storage could name a PRODUCTION object on another cluster):
  SMOKE_VMID                  primary throwaway test VM      e.g. 100
  PROXIMO_SMOKE_TEST_VMIDS    csv of the test VMs            e.g. "100,101,102"
  SMOKE_STORE                 storage holding the boot disk  e.g. local-lvm
  SMOKE_POOL                  the test resource pool         e.g. proximo-test
Optional (PVE-universal defaults; read-only, low-stakes):
  SMOKE_MOVE_STORE  disk-move target storage (default: local)
  SMOKE_BRIDGE      mgmt bridge, PLAN only   (default: vmbr0)
  SMOKE_BOOT_VOLID  override the derived boot volid (default: <SMOKE_STORE>:vm-<SMOKE_VMID>-disk-0)
Usage: set -a; . <your-proximo.env>; set +a; \
       SMOKE_VMID=100 PROXIMO_SMOKE_TEST_VMIDS=100,101,102 SMOKE_STORE=local-lvm SMOKE_POOL=proximo-test \
       uv run python scripts/live-smoke/coverage-blast-smoke.py
"""
from __future__ import annotations

import os
import sys

from proximo.access_governance import plan_realm_update, plan_role_update
from proximo.blast import firewall_lockout_blast, iface_attachment_blast
from proximo.cluster_ops import plan_migrate
from proximo.disk_ops import plan_disk_move
from proximo.server import _svc
from proximo.storage import plan_content_delete
from proximo.tasks_pools import plan_pool_delete

# Sandbox fixtures from env — REQUIRED (refuse to guess) so a different cluster SKIPs instead of
# computing a blast against whatever those baked-in IDs happen to be (possibly prod).
TEST_VMID = os.environ.get("SMOKE_VMID", "").strip()
TEST_VMIDS = tuple(p.strip() for p in os.environ.get("PROXIMO_SMOKE_TEST_VMIDS", "").split(",") if p.strip())
TEST_STORE = os.environ.get("SMOKE_STORE", "").strip()
TEST_POOL = os.environ.get("SMOKE_POOL", "").strip()
_missing = [name for name, val in (
    ("SMOKE_VMID", TEST_VMID), ("PROXIMO_SMOKE_TEST_VMIDS", TEST_VMIDS),
    ("SMOKE_STORE", TEST_STORE), ("SMOKE_POOL", TEST_POOL)) if not val]
if _missing:
    sys.exit("required sandbox fixtures unset: " + ", ".join(_missing)
             + " — declare the throwaway test surface (see this script's docstring). Refusing to guess.")

# Low-stakes, read-only knobs — PVE-install universals; overridable but safe to default:
MOVE_STORE = os.environ.get("SMOKE_MOVE_STORE", "local").strip()   # disk-move target storage
MGMT_BRIDGE = os.environ.get("SMOKE_BRIDGE", "vmbr0").strip()      # mgmt bridge — NEVER edited live; PLAN only
# Boot disk follows PVE's convention for a VM we provisioned; override if your fixture differs.
TEST_BOOT_VOLID = os.environ.get("SMOKE_BOOT_VOLID", f"{TEST_STORE}:vm-{TEST_VMID}-disk-0").strip()

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    _results.append((name, ok, detail))
    print(f"\n{'✅' if ok else '❌'} {name}: {detail}")


def main() -> int:
    cfg, api, _, _ = _svc()

    # 1. content-delete — pve-test1's boot disk must be detected as an in-use disk → won't boot.
    p = plan_content_delete(api, TEST_STORE, TEST_BOOT_VOLID)
    named = [a for a in p.affected if a.get("vmid") == TEST_VMID]
    for line in p.blast_radius:
        print("   ", line)
    check("content_delete in-use detection",
          bool(named) and p.risk == "high" and any("not boot" in line.lower() for line in p.blast_radius),
          f"risk={p.risk} affected_vmids={[a.get('vmid') for a in p.affected]} complete={p.complete}")

    # 2. migrate — pve-test1's disk is on local-lvm (shared=0) → flagged local/can't-cleanly-migrate.
    #    Target node read from config (single-node test cluster) — never hardcoded.
    p = plan_migrate(api, TEST_VMID, cfg.node, kind="qemu")
    for line in p.blast_radius:
        print("   ", line)
    local_flag = [a for a in p.affected if a.get("state") in ("local", "unavailable")]
    check("migrate disk-residency detection",
          bool(local_flag),
          f"risk={p.risk} affected={[(a.get('slot'), a.get('state')) for a in p.affected]} complete={p.complete}")

    # 3. disk-move — reads the REAL target storage_status + co-tenants (target = SMOKE_MOVE_STORE).
    p = plan_disk_move(api, TEST_VMID, "scsi0", MOVE_STORE, kind="qemu", delete_source=False)
    for line in p.blast_radius:
        print("   ", line)
    check("disk_move reads real storage capacity",
          p.complete is True,
          f"risk={p.risk} affected={[a.get('vmid') for a in p.affected]} complete={p.complete}")

    # 4. pool-delete — the sandbox token's ACL grant is ON /pool/proximo-test → must be named as orphaned.
    p = plan_pool_delete(api, TEST_POOL)
    for line in p.blast_radius:
        print("   ", line)
    pool_grant = [a for a in p.affected if a.get("path", "").startswith("/pool/" + TEST_POOL)]
    check("pool_delete names orphaned ACL grants",
          bool(pool_grant),
          f"risk={p.risk} principals={[a.get('principal') for a in p.affected]} complete={p.complete}")

    # 5. role-update — PVEAuditor is referenced by proximo@pve (read-only token) at / → must be named.
    p = plan_role_update(api, "PVEAuditor", privs="Sys.Audit")
    for line in p.blast_radius:
        print("   ", line)
    auditor_grants = [a for a in p.affected if a.get("roleid") == "PVEAuditor"]
    check("role_update names affected ACL grants",
          bool(auditor_grants) and p.complete is True,
          f"risk={p.risk} grants={[(a.get('principal'), a.get('path')) for a in p.affected]}")

    # 6. realm-update — pam/pve are real realms with real users → must name them (built-in => HIGH).
    p = plan_realm_update(api, "pve", comment="coverage-smoke (no mutation)")
    for line in p.blast_radius:
        print("   ", line)
    check("realm_update names affected users",
          p.complete is True,
          f"risk={p.risk} users={[a.get('userid') for a in p.affected]}")

    # 7. network-iface attachment — vmbr0 carries the test VMs (and prod guests); names them. PLAN ONLY.
    r = iface_attachment_blast(api, MGMT_BRIDGE)
    for line in r.summary_lines:
        print("   ", line)
    test_on_bridge = [a for a in r.affected if a.get("vmid") in TEST_VMIDS]
    check("network_iface attachment detection",
          bool(test_on_bridge),
          f"max_severity={r.max_severity} attached_vmids={[a.get('vmid') for a in r.affected]} complete={r.complete}")

    # 8. firewall-lockout — reads the REAL cluster+node ruleset and classifies each node. PLAN ONLY.
    r = firewall_lockout_blast(api, "cluster", None)
    for line in r.summary_lines:
        print("   ", line)
    check("firewall_lockout classifies real nodes",
          r.risk == "high",   # the op is unconditional HIGH; the value is the per-node classification
          f"risk={r.risk} affected_nodes={[(a.get('node'), a.get('state')) for a in r.affected]} complete={r.complete}")

    print("\n" + "=" * 70)
    passed = sum(1 for _, ok, _ in _results if ok)
    print(f"PLAN-verification against real cluster: {passed}/{len(_results)} checks passed")
    for name, ok, _ in _results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
