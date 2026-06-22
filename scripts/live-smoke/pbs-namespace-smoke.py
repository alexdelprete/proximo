#!/usr/bin/env python3
"""Live MUTATE->verify of proximo's PBS namespace create + delete (self-cleaning).

  1. create namespace SMOKE_PBS_NS in the test datastore -> assert it appears in namespace_list
  2. delete it -> assert it is gone

GUARDED via pbs_smoke_lib.connect() (refuses any non-allowlisted PBS host). No seed needed.
Run with the PBS env sourced + PROXIMO_SMOKE_PBS_HOSTS=<test-pbs-host>.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pbs_smoke_lib import STORE, connect  # noqa: E402  (sibling live-smoke module)

from proximo.pbs import namespace_create, namespace_delete, namespace_list  # noqa: E402

NS = os.environ.get("SMOKE_PBS_NS", "ci-smoke-ns")
_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str) -> None:
    _results.append((name, ok))
    print(f"{'✅' if ok else '❌'} {name}: {detail}")


def _names(api) -> set[str]:
    return {n.get("ns") for n in namespace_list(api, STORE)}


def main() -> int:
    api, _ = connect()
    if NS in _names(api):                       # clean start
        namespace_delete(api, STORE, NS, delete_groups=True)
    before = _names(api)
    namespace_create(api, STORE, NS)
    after = _names(api)
    check("namespace_created", NS in after and NS not in before, f"ns={NS!r} present={NS in after}")
    try:
        namespace_delete(api, STORE, NS)
        check("namespace_deleted", NS not in _names(api), f"gone={NS not in _names(api)}")
    finally:
        if NS in _names(api):                   # self-clean on any failure
            namespace_delete(api, STORE, NS, delete_groups=True)

    passed = sum(1 for _, ok in _results if ok)
    ok = passed == len(_results)
    print(f"\nPBS namespace MUTATE->verify ({STORE}): {'PASS' if ok else 'FAIL'}  {passed}/{len(_results)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
