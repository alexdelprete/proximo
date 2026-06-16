#!/usr/bin/env python3
"""Read-only firewall/network blast-radius smoke.

PLAN a firewall rule add and print the computed PER-RULE REACH (what the rule permits/blocks, to
whom, at what sensitivity) + the structured `affected`. Optionally, if PROXIMO_NODE is set, also
PLAN a network apply against the live node and print the best-effort management-interface lockout
naming. NEVER mutates (no confirm is ever passed). Env: PROXIMO_* (see scripts/live-smoke/README.md).

The reach PLAN is PURE (no API call) — it classifies the rule fields you supply. The network-apply
PLAN performs a single safe read (network_list) and parses the management host from the configured
API base URL; it never applies.

Usage:
  PROXIMO_FW_ACTION=ACCEPT PROXIMO_FW_DIRECTION=in PROXIMO_FW_SOURCE=0.0.0.0/0 \\
    PROXIMO_FW_DPORT=22 uv run python scripts/live-smoke/fw-reach-smoke.py

  # also exercise network-apply lockout naming (read-only) against a live node:
  PROXIMO_NODE=pve PROXIMO_FW_ACTION=DROP PROXIMO_FW_DPORT=8006 \\
    uv run python scripts/live-smoke/fw-reach-smoke.py
"""
import json
import os

from proximo.firewall import plan_firewall_rule_add
from proximo.network import plan_network_apply
from proximo.server import _svc


def main() -> int:
    action = os.environ.get("PROXIMO_FW_ACTION", "ACCEPT")
    direction = os.environ.get("PROXIMO_FW_DIRECTION", "in")
    scope = os.environ.get("PROXIMO_FW_SCOPE", "cluster")
    source = os.environ.get("PROXIMO_FW_SOURCE") or None
    dport = os.environ.get("PROXIMO_FW_DPORT") or None

    # PLAN only — never confirm. plan_firewall_rule_add is PURE (no API).
    plan = plan_firewall_rule_add(action, direction, scope, source=source, dport=dport)
    print(f"firewall rule add {action}/{direction} source={source!r} dport={dport!r} "
          f"scope={scope}: risk={plan.risk} complete={plan.complete}")
    for line in plan.blast_radius:
        print(f"  {line}")
    print(json.dumps(plan.affected, indent=2))

    node = os.environ.get("PROXIMO_NODE")
    if node:
        _, api, _, _ = _svc()
        napply = plan_network_apply(api, node)  # PLAN only — one safe read, never applies
        print(f"\nnetwork apply on {node}: risk={napply.risk} complete={napply.complete}")
        for line in napply.blast_radius:
            print(f"  {line}")
        print(json.dumps(napply.affected, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
