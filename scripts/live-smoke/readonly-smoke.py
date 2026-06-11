#!/usr/bin/env python3
"""Proximo READ-ONLY live-smoke.

Verifies the read-only tool endpoint shapes against a real Proxmox VE host.
No mutations. Exercises:
  pve_node_status · pve_storage_status · pve_storage_content · pve_backup_list
  (each on every storage discovered via pve_diagnose) + audit_verify (ledger).

A per-storage ERR (e.g. a storage that does not support 'backup' content) is
informative, not a failure — the summary asks only that each tool succeeded on
at least one storage, proving the endpoint shape Proximo builds is correct.

Environment (set by the wrapper script; see readonly-smoke.sh and README.md):
  PROXIMO_API_BASE_URL  PROXIMO_NODE  PROXIMO_TOKEN_PATH  PROXIMO_VERIFY_TLS
"""
from __future__ import annotations

import proximo.server as server


def hr(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    cfg, api, exec_, audit = server._svc()
    print(f"target  node={cfg.node}  url={cfg.api_base_url}")

    hr("sanity — node status (known-good read)")
    st = server.pve_node_status()
    print("node_status ok; mem keys:", sorted((st.get("memory") or {}).keys()))

    hr("discover storages (via pve_diagnose)")
    nd = server.pve_diagnose(cfg.node)
    storages = [s.get("storage") for s in (nd.get("storage") or []) if s.get("storage")]
    print("storages found:", storages)
    if not storages:
        print("no storages discovered — cannot exercise the storage tools; aborting.")
        return 1

    results: dict[str, list[tuple[str, str, str]]] = {
        "pve_storage_status": [],
        "pve_storage_content": [],
        "pve_backup_list": [],
    }
    for s in storages:
        try:
            ss = server.pve_storage_status(s)
            detail = sorted(ss.keys()) if isinstance(ss, dict) else type(ss).__name__
            results["pve_storage_status"].append((s, "OK", str(detail)))
        except Exception as e:  # noqa: BLE001 — smoke records the real outcome
            results["pve_storage_status"].append((s, "ERR", f"{type(e).__name__}: {e}"))

        try:
            cont = server.pve_storage_content(s)
            results["pve_storage_content"].append((s, "OK", f"{len(cont)} items"))
        except Exception as e:  # noqa: BLE001
            results["pve_storage_content"].append((s, "ERR", f"{type(e).__name__}: {e}"))

        try:
            bl = server.pve_backup_list(s)
            results["pve_backup_list"].append((s, "OK", f"{len(bl)} backups"))
        except Exception as e:  # noqa: BLE001
            results["pve_backup_list"].append((s, "ERR", f"{type(e).__name__}: {e}"))

    for tool, rows in results.items():
        hr(tool)
        for name, status, detail in rows:
            print(f"  {status:3} {name:20} {detail}")

    hr("PROVE — ledger")
    v = server.audit_verify()
    print("ledger verify:", {"ok": v.get("ok"), "entries": v.get("entries")})

    def any_ok(rows: list[tuple[str, str, str]]) -> bool:
        return any(status == "OK" for _, status, _ in rows)

    hr("RESULT")
    passed = all(any_ok(results[t]) for t in results) and bool(v.get("ok"))
    for t in results:
        label = "OK on >=1 storage" if any_ok(results[t]) else "NO OK — endpoint shape suspect"
        print(f"  {t}: {label}")
    print("\nREAD-ONLY SMOKE", "PASSED" if passed else "INCOMPLETE — review above")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
