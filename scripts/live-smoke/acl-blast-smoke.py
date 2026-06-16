#!/usr/bin/env python3
"""Read-only ACL blast-radius smoke: PLAN an ACL grant against a live PVE and print the computed
impact (shadow/widen + who-else-can-reach). NEVER mutates (no confirm). Env: PROXIMO_* (see
scripts/live-smoke/README.md).

Usage:
  PROXIMO_ACL_PATH=/vms PROXIMO_ACL_TARGET=user@pam PROXIMO_ACL_ROLES=PVEVMUser \\
    uv run python scripts/live-smoke/acl-blast-smoke.py
"""
import json
import os
import sys

from proximo.access import plan_acl_modify
from proximo.server import _svc


def main() -> int:
    path = os.environ.get("PROXIMO_ACL_PATH")
    target = os.environ.get("PROXIMO_ACL_TARGET")
    roles = os.environ.get("PROXIMO_ACL_ROLES", "PVEVMUser")
    if not path or not target:
        print("set PROXIMO_ACL_PATH and PROXIMO_ACL_TARGET (read-only PLAN; no mutation)", file=sys.stderr)
        return 2
    _, api, _, _ = _svc()
    plan = plan_acl_modify(api, path, roles, target, kind="user")  # PLAN only — never confirm
    print(f"acl grant {roles} -> {target} at {path}: risk={plan.risk}")
    for line in plan.blast_radius:
        print(f"  {line}")
    print(json.dumps(plan.affected, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
