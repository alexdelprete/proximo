#!/usr/bin/env python3
"""Read-only capture of REAL Proxmox response shapes for the characterization fixtures.

These shapes feed ``tests/test_live_shapes.py`` (Track A of the live-CI tier): they lock the blast
engine's API-shape assumptions against ground truth so a wrong assumption fails the fast suite
instead of silently producing a confidently-wrong blast against a live cluster.

READ-ONLY — only issues GETs. Run with the same ``PROXIMO_*`` env the live smokes use (see this
directory's README). Dumps RAW JSON to stdout (or ``--out FILE``). **The raw dump is UNSCRUBBED** —
it contains real node names, guest names, ACL principals, etc. Scrub it (genericize node/guest
names, MACs, principals; drop high-entropy noise) before committing anything under
``tests/live_shapes/fixtures/``. Re-run after a PVE major upgrade and diff the shapes.

Usage:
    PROXIMO_API_BASE_URL=... PROXIMO_NODE=... PROXIMO_TOKEN_PATH=... PROXIMO_VERIFY_TLS=false \\
        python scripts/live-smoke/capture-shapes.py --out raw-shapes.json
"""
from __future__ import annotations

import argparse
import json
import sys

from proximo.backends import ApiBackend
from proximo.config import ProximoConfig


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="-", help="output file ('-' = stdout)")
    args = ap.parse_args()

    cfg = ProximoConfig.from_env()
    api = ApiBackend(cfg)
    node = cfg.node

    def grab(path: str):
        try:
            return api._get(path)
        except Exception as e:  # noqa: BLE001 — capture diagnostic, not control flow
            return {"__error__": f"{type(e).__name__}: {e}"}

    out: dict = {
        "backup_jobs": grab("/cluster/backup"),            # selection-mode serialization (riskiest)
        "cluster_vms": grab("/cluster/resources?type=vm"),
        "storage_node": grab(f"/nodes/{node}/storage"),
        "pools": grab("/pools"),
        "ha_resources": grab("/cluster/ha/resources"),
        "acl": grab("/access/acl"),
        "fw_rules_cluster": grab("/cluster/firewall/rules"),
        "guest_configs": {},
        "guest_snapshots": {},
    }

    qemu = [v for v in (out["cluster_vms"] or []) if isinstance(v, dict) and v.get("type") == "qemu"][:2]
    for v in qemu:
        vmid, n = v.get("vmid"), v.get("node", node)
        out["guest_configs"][str(vmid)] = grab(f"/nodes/{n}/qemu/{vmid}/config")
        out["guest_snapshots"][str(vmid)] = grab(f"/nodes/{n}/qemu/{vmid}/snapshot")

    pools = out.get("pools") or []
    if pools and isinstance(pools[0], dict) and pools[0].get("poolid"):
        pid = pools[0]["poolid"]
        out["pool_members"] = {pid: grab(f"/pools/{pid}")}

    text = json.dumps(out, indent=2, default=str)
    if args.out == "-":
        print(text)
    else:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"wrote {args.out} (UNSCRUBBED — scrub before committing as a fixture)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
