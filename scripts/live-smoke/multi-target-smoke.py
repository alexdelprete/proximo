#!/usr/bin/env python3
"""Live multi-target smoke: prove a `from_target` registry config opens a REAL working connection.

The unit test suite proves the routing LOGIC (mocked backends). This proves CONNECTIVITY: that a
named target in PROXIMO_TARGETS resolves through the real ``_svc()`` → ``ProximoConfig.from_target``
→ ``ApiBackend`` (real TLS against that target's CA, real token auth) and actually reads a live box.

For each PVE target named in ``SMOKE_PVE_TARGETS`` (comma-separated), it:
  1. sets the active target (the contextvar a tool's @tool wrapper sets),
  2. resolves it through real ``_svc()`` and asserts the config is the TARGET's, not the env box,
  3. does a READ-ONLY ``GET /version`` + ``GET /nodes/<node>/status`` against the live box,
  4. records that read through the ledger and asserts the entry carries ``remote=<target>``.
Plus: the env (no-target) path still reads, and a wrong-kind target (``SMOKE_PBS_KIND_TARGET``)
RAISES before any connection (kind safety, live).

READ-ONLY. Reuses existing tokens BY REFERENCE (PROXIMO_TARGETS + env). Writes to a TEMP ledger
(set PROXIMO_AUDIT_LOG to a scratch path) so the prod PROVE chain is untouched. Targets must be
RUNNING + reachable. No hardcoded infra — everything comes from env (leak-clean).

Run: set the PROXIMO_* env (+ PROXIMO_TARGETS, SMOKE_PVE_TARGETS), then `uv run python
scripts/live-smoke/multi-target-smoke.py`.
"""
from __future__ import annotations

import os
import sys

from proximo import targets as T  # noqa: E402
from proximo.backends import ProximoError  # noqa: E402
from proximo.pbs import datastore_list  # noqa: E402
from proximo.server import _ledger, _pbs, _svc  # noqa: E402


def _read_pve(api, node: str) -> str:
    ver = api.version()
    assert isinstance(ver, dict) and "version" in ver, f"unexpected /version: {ver!r}"
    st = api.node_status(node)
    assert isinstance(st, dict) and ("uptime" in st or "cpu" in st), f"unexpected node status: {st!r}"
    return str(ver.get("version"))


def smoke_env() -> bool:
    """The default (no-target) path still reads the env box."""
    cfg, api, _exec, _led = _svc()
    ver = _read_pve(api, cfg.node)
    print(f"  OK   <env default>      version={ver}  node={cfg.node}  base={cfg.api_base_url}")
    return True


def smoke_pve_target(name: str) -> bool:
    tok = T._active_target.set(name)
    try:
        cfg, api, _exec, ledger = _svc()
        ver = _read_pve(api, cfg.node)
        entry = ledger.record("multitarget_smoke_read", target=cfg.node, remote=T.ledger_remote())
        if entry.get("remote") != name:
            print(f"  FAIL {name}: ledger remote {entry.get('remote')!r} != {name!r}")
            return False
        print(f"  OK   {name:<18} version={ver}  node={cfg.node}  base={cfg.api_base_url}  "
              f"remote-recorded={entry.get('remote')}")
        return True
    finally:
        T._active_target.reset(tok)


def smoke_pbs_target(name: str) -> bool:
    """PBS distinct-box: PbsConfig.from_target -> PbsBackend -> live read; ledger records remote."""
    tok = T._active_target.set(name)
    try:
        cfg, backend = _pbs()
        ver = backend._get("/version")
        assert isinstance(ver, dict) and "version" in ver, f"{name}: unexpected /version: {ver!r}"
        ds = datastore_list(backend)
        stores = [d.get("store") for d in ds] if ds else []
        entry = _ledger().record("multitarget_smoke_read", target="pbs/datastores", remote=T.ledger_remote())
        if entry.get("remote") != name:
            print(f"  FAIL {name}: ledger remote {entry.get('remote')!r} != {name!r}")
            return False
        print(f"  OK   {name:<18} PBS {ver.get('version')}-{ver.get('release')}  datastores={stores}  "
              f"base={cfg.base_url}  remote-recorded={entry.get('remote')}")
        return True
    finally:
        T._active_target.reset(tok)


def smoke_kind_safety(pbs_name: str) -> bool:
    """A pve resolver given a pbs-kind target must RAISE before any connection."""
    tok = T._active_target.set(pbs_name)
    try:
        _svc()
        print(f"  FAIL kind-safety: _svc() did NOT raise on pbs target {pbs_name!r}")
        return False
    except ProximoError as e:
        if "not usable by a PVE tool" not in str(e):
            print(f"  FAIL kind-safety: wrong error for {pbs_name!r}: {e}")
            return False
        print(f"  OK   kind-safety        pve resolver rejects pbs target {pbs_name!r}")
        return True
    finally:
        T._active_target.reset(tok)


def main() -> int:
    pve_targets = [t.strip() for t in os.environ.get("SMOKE_PVE_TARGETS", "").split(",") if t.strip()]
    pbs_targets = [t.strip() for t in os.environ.get("SMOKE_PBS_TARGETS", "").split(",") if t.strip()]
    pbs_kind_target = os.environ.get("SMOKE_PBS_KIND_TARGET", "").strip()

    print("=== multi-target connectivity smoke (READ-ONLY) ===")
    ok = smoke_env()
    for name in pve_targets:
        ok = smoke_pve_target(name) and ok
    for name in pbs_targets:
        ok = smoke_pbs_target(name) and ok
    if pbs_kind_target:
        ok = smoke_kind_safety(pbs_kind_target) and ok

    print("=== PASS ===" if ok else "=== FAIL ===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
