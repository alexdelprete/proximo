#!/usr/bin/env python3
"""Read-only blast-radius smoke: PLAN a storage delete against a live PVE and print the computed
affected set. NEVER mutates (no confirm). Env: PROXIMO_* (see scripts/live-smoke/README.md).

Usage: PROXIMO_STORAGE=local-lvm uv run python scripts/live-smoke/blast-smoke.py
"""
import json
import os
import sys

from proximo.blast import storage_blast
from proximo.server import _svc


def main() -> int:
    storage = os.environ.get("PROXIMO_STORAGE")
    if not storage:
        print("set PROXIMO_STORAGE=<existing storage id> (read-only; no mutation)", file=sys.stderr)
        return 2
    _, api, _, _ = _svc()
    result = storage_blast(api, storage)
    print(f"storage={storage} complete={result.complete} max_severity={result.max_severity}")
    for line in result.summary_lines:
        print(line)
    print(json.dumps(result.affected_dicts(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
