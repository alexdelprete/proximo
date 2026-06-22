#!/usr/bin/env python3
"""Live storage-admin smoke: create + delete a throwaway storage definition (self-cleaning).

  1. storage_create a throwaway `dir` backup storage -> assert it appears in the storage config
  2. plan_storage_delete it -> assert a blast/plan is computed (empty storage => nothing stranded)
  3. storage_delete it -> assert it is GONE from the config

SAFETY: storage create/delete mutates CLUSTER-WIDE config — deleting a prod storage (local-lvm/pbs/pve)
strands every guest on it. The Datastore.Allocate priv needed to create storage lives at the /storage
ROOT and CANNOT be scoped to "test storages only", so the SOLE guard is the in-smoke name allowlist
(assert_test_identity, default-deny): it refuses any storage whose name lacks an allowlisted test prefix
(so local-lvm/pbs/pve/test are all refused). Needs a storage-admin token (Datastore.Allocate at /storage)
— provisioned by John. Run with the PVE env + PROXIMO_SMOKE_IDENTITY_PREFIXES.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from safety import assert_test_identity, load_identity_allowlist  # noqa: E402  (sibling live-smoke module)

from proximo.server import _svc  # noqa: E402
from proximo.storage_admin import (  # noqa: E402
    plan_storage_delete,
    storage_config_list,
    storage_create,
    storage_delete,
)

NAME = os.environ.get("SMOKE_STORAGE_NAME", "proximo-cismoke-store").strip()
PATH = os.environ.get("SMOKE_STORAGE_PATH", "/tmp/proximo-cismoke-store").strip()  # noqa: S108  (throwaway test dir storage; override via env)

# SOLE safety layer: refuse any storage whose name is not an allowlisted test name BEFORE any
# create/delete (default-deny) — so a prod storage (local-lvm/pbs/pve/test) can never be touched.
assert_test_identity(NAME, load_identity_allowlist(os.environ), "storage")

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str) -> None:
    _results.append((name, ok))
    print(f"{'✅' if ok else '❌'} {name}: {detail}")


def _names(api) -> set[str]:
    return {s.get("storage") for s in storage_config_list(api)}


def main() -> int:
    _, api, _, _ = _svc()
    if NAME in _names(api):                      # idempotent clean start (guard proved NAME is test)
        storage_delete(api, NAME)
    try:
        storage_create(api, NAME, "dir", content="backup", path=PATH)
        check("storage_created", NAME in _names(api), f"storage={NAME}")

        p = plan_storage_delete(api, NAME)
        check("plan_delete_computed", getattr(p, "complete", None) is True,
              f"risk={getattr(p, 'risk', None)} affected={[a.get('vmid') for a in getattr(p, 'affected', [])]}")

        storage_delete(api, NAME)
        check("storage_deleted", NAME not in _names(api), f"gone={NAME not in _names(api)}")
    finally:
        if NAME in _names(api):                  # self-clean on any failure
            storage_delete(api, NAME)

    passed = sum(1 for _, ok in _results if ok)
    ok = passed == len(_results)
    label = "storage-admin live-verify (create/plan-delete/delete)"
    print(f"\n{label}: {'PASS' if ok else 'FAIL'}  {passed}/{len(_results)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
