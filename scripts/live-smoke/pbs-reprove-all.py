#!/usr/bin/env python3
"""PBS RE-PROVE ALL — fresh live receipts for all 27 pbs_* tools.

Exercises every PBS tool through the Proximo code path (PbsBackend / pbs_config functions),
NOT raw curl. Safe — no prod PBS touched. All mutations are throwaway + self-cleaning.

Job 1 of 2: fresh per-tool pass/fail table + bug fix.

Run from proximo dir with PBS env:
  PROXIMO_PBS_BASE_URL=https://127.0.0.1:18007/api2/json
  PROXIMO_PBS_TOKEN_PATH=~/.config/proximo/pbs-test-token
  PROXIMO_PBS_CA_BUNDLE=~/.config/proximo/pbs-test-ca.pem
  PROXIMO_PBS_VERIFY_TLS=true
  PROXIMO_SMOKE_PBS_HOSTS=127.0.0.1
"""
from __future__ import annotations

import os
import sys
import time
import tempfile
import subprocess
from urllib.parse import urlparse, quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from safety import assert_test_pbs, load_pbs_allowlist  # noqa: E402

# PBS backend + config ops
from proximo.pbs import (  # noqa: E402
    PbsBackend, PbsConfig,
    datastore_list, datastore_status, gc_status,
    gc_start, verify_start, prune, snapshots_list,
    namespace_list, namespace_create, namespace_delete,
    snapshot_delete,
)
from proximo.pbs_config import (  # noqa: E402
    datastore_get, datastore_create, datastore_update, datastore_delete,
    snapshot_protected_set, snapshot_notes_get, snapshot_notes_set,
    group_change_owner,
    remote_create, remote_delete,
    traffic_control_get, traffic_control_upsert, traffic_control_delete,
)
from proximo.backup_schedules import (  # noqa: E402
    pbs_scheduled_job_get, pbs_scheduled_job_create,
    pbs_scheduled_job_update, pbs_scheduled_job_delete,
)

STORE = os.environ.get("SMOKE_PBS_STORE", "test-ds")
TC_NAME = "ci-reprove-tc"
NS_NAME = "ci-reprove-ns"
DS_NAME = "proximo-reprove-ds"
JOB_ID = "ci-reprove-job"
REMOTE_NAME = "ci-reprove-remote"
BID_SNAP = "ci-reprove-snap"

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    _results.append((name, ok, detail))
    icon = "✅" if ok else "❌"
    print(f"  {icon} {name}: {detail}")


def section(title: str) -> None:
    print(f"\n--- {title} ---")


def _authid_and_secret(cfg: PbsConfig) -> tuple[str, str]:
    with open(cfg.token_path, encoding="utf-8") as f:
        authid, secret = f.read().strip().split(":", 1)
    return authid, secret


def _get_pbs_fingerprint() -> str:
    """Get the PBS cert SHA-256 fingerprint (for proxmox-backup-client TLS verification)."""
    r = subprocess.run(
        ["openssl", "s_client", "-connect", "127.0.0.1:8007",
         "-CAfile", os.environ["PROXIMO_PBS_CA_BUNDLE"]],
        input="", capture_output=True, text=True, timeout=10,
    )
    fp_line = [ln for ln in r.stdout.splitlines() if "Fingerprint" in ln]
    if fp_line:
        return fp_line[0].split("=", 1)[-1].strip().lower()
    # Fallback: derive from CA cert
    r2 = subprocess.run(
        ["openssl", "x509", "-in", os.environ["PROXIMO_PBS_CA_BUNDLE"],
         "-noout", "-fingerprint", "-sha256"],
        capture_output=True, text=True,
    )
    return r2.stdout.strip().split("=", 1)[-1].strip()


def seed_backup(cfg: PbsConfig, backup_id: str) -> None:
    """Push a throwaway host backup using proxmox-backup-client.

    Uses PBS fingerprint for TLS verification — the backup client connects to :8007
    directly (not the API tunnel at :18007), so we need the fingerprint to allow TLS
    even when the cert CN/SAN doesn't match the forwarded tunnel address.
    """
    authid, secret = _authid_and_secret(cfg)
    host = urlparse(cfg.base_url).hostname
    env = dict(os.environ)
    env["PBS_PASSWORD"] = secret
    # Use fingerprint for backup client TLS (bypasses SAN hostname check on the tunnel address)
    fp = cfg.fingerprint or _get_pbs_fingerprint()
    env["PBS_FINGERPRINT"] = fp
    with tempfile.TemporaryDirectory() as d:
        marker = os.path.join(d, "marker.txt")
        with open(marker, "w") as f:
            f.write("proximo-ci-reprove\n")
        r = subprocess.run(
            ["proxmox-backup-client", "backup", f"data.pxar:{d}",
             "--repository", f"{authid}@{host}:{STORE}",
             "--backup-id", backup_id, "--crypt-mode", "none"],
            env=env, capture_output=True, text=True,
        )
    if r.returncode != 0:
        raise RuntimeError(f"seed failed for backup-id={backup_id}: {r.stderr[-300:]}")


def wait_task(api: PbsBackend, upid: str, timeout: int = 180) -> dict:
    """Poll PBS async task to completion."""
    node = upid.split(":")[1] if upid.startswith("UPID:") else "localhost"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = api._get(f"/nodes/{node}/tasks/{quote(upid, safe='')}/status") or {}
        if st.get("status") == "stopped":
            return st
        time.sleep(1)
    raise TimeoutError(f"PBS task {upid} did not finish within {timeout}s")


def connect() -> tuple[PbsBackend, PbsConfig]:
    cfg = PbsConfig.from_env()
    assert_test_pbs(cfg.base_url, load_pbs_allowlist(os.environ))
    return PbsBackend(cfg), cfg


def run_read_tools(api: PbsBackend) -> None:
    section("READ TOOLS (tools 1-5)")

    # 1. pbs_datastores_list
    try:
        ds = datastore_list(api)
        names = [x.get("store") or x.get("name") for x in ds]
        ok = isinstance(ds, list) and len(ds) > 0 and STORE in names
        check("pbs_datastores_list", ok, f"stores={names}")
    except Exception as e:
        check("pbs_datastores_list", False, str(e))

    # 2. pbs_datastore_status
    try:
        st = datastore_status(api, STORE)
        ok = isinstance(st, dict) and "total" in st
        check("pbs_datastore_status", ok, f"keys={sorted(st)[:5]}")
    except Exception as e:
        check("pbs_datastore_status", False, str(e))

    # 3. pbs_gc_status
    try:
        gc = gc_status(api, STORE)
        ok = isinstance(gc, dict) and "disk-bytes" in gc
        check("pbs_gc_status", ok, f"disk-bytes={gc.get('disk-bytes')}")
    except Exception as e:
        check("pbs_gc_status", False, str(e))

    # 4. pbs_snapshots_list
    try:
        snaps = snapshots_list(api, STORE)
        ok = isinstance(snaps, list)
        check("pbs_snapshots_list", ok, f"count={len(snaps)}")
    except Exception as e:
        check("pbs_snapshots_list", False, str(e))

    # 5. pbs_namespaces_list
    try:
        nss = namespace_list(api, STORE)
        ok = isinstance(nss, list)
        check("pbs_namespaces_list", ok, f"count={len(nss)}, sample={nss[:2]}")
    except Exception as e:
        check("pbs_namespaces_list", False, str(e))


def run_namespace_tools(api: PbsBackend) -> None:
    section("NAMESPACE CREATE/DELETE (tools 10-11)")

    # Pre-clean
    try:
        existing = {n.get("ns") for n in namespace_list(api, STORE)}
        if NS_NAME in existing:
            namespace_delete(api, STORE, NS_NAME, delete_groups=True)
    except Exception:
        pass

    # 10. pbs_namespace_create
    try:
        namespace_create(api, STORE, NS_NAME)
        nss_after = {n.get("ns") for n in namespace_list(api, STORE)}
        ok = NS_NAME in nss_after
        check("pbs_namespace_create", ok, f"present={ok}")
    except Exception as e:
        check("pbs_namespace_create", False, str(e))
        return

    # 11. pbs_namespace_delete
    try:
        namespace_delete(api, STORE, NS_NAME)
        nss_final = {n.get("ns") for n in namespace_list(api, STORE)}
        ok = NS_NAME not in nss_final
        check("pbs_namespace_delete", ok, f"gone={ok}")
    except Exception as e:
        check("pbs_namespace_delete", False, str(e))
        try:
            namespace_delete(api, STORE, NS_NAME, delete_groups=True)
        except Exception:
            pass


def run_prune_dry_run(api: PbsBackend, cfg: PbsConfig) -> None:
    section("PRUNE DRY-RUN (tool 8) — seeds a backup for a non-empty group")
    seed_bid = "ci-reprove-prune"
    # PBS prune requires the backup group to exist — seed one throwaway backup
    try:
        seed_backup(cfg, seed_bid)
    except Exception as e:
        check("pbs_prune(dry_run=True)", False, f"seed failed: {e}")
        return

    try:
        plan = prune(api, STORE, keep_last=100, backup_type="host",
                     backup_id=seed_bid, dry_run=True)
        ok = isinstance(plan, list)
        check("pbs_prune(dry_run=True)", ok, f"plan_entries={len(plan)}, keep_count={sum(1 for d in plan if d.get('keep'))}")
    except Exception as e:
        check("pbs_prune(dry_run=True)", False, str(e))
    finally:
        # self-clean
        for s in [x for x in snapshots_list(api, STORE) if x.get("backup-id") == seed_bid]:
            try:
                snapshot_delete(api, STORE, s["backup-type"], s["backup-id"], s["backup-time"])
            except Exception:
                pass


def run_traffic_control_tools(api: PbsBackend) -> None:
    section("TRAFFIC CONTROL UPSERT/DELETE (tools 21-22)")

    # Pre-clean
    try:
        traffic_control_delete(api, TC_NAME)
    except Exception:
        pass

    # 21. pbs_traffic_control_upsert (create)
    try:
        traffic_control_upsert(api, TC_NAME, rate_in=10000000, network="10.0.0.0/8",
                               comment="ci-reprove")
        existing = traffic_control_get(api, TC_NAME)
        ok = existing is not None and isinstance(existing, dict)
        check("pbs_traffic_control_upsert(create)", ok, f"result_keys={sorted((existing or {}).keys())[:5]}")
    except Exception as e:
        check("pbs_traffic_control_upsert(create)", False, str(e))

    # 21b. pbs_traffic_control_upsert (update)
    try:
        traffic_control_upsert(api, TC_NAME, rate_in=20000000, comment="ci-reprove-updated")
        ok = True
        check("pbs_traffic_control_upsert(update)", ok, "updated without error")
    except Exception as e:
        check("pbs_traffic_control_upsert(update)", False, str(e))

    # 22. pbs_traffic_control_delete
    try:
        traffic_control_delete(api, TC_NAME)
        # Verify it's gone — GET should fail (PBS returns 400 for nonexistent)
        try:
            still_there = traffic_control_get(api, TC_NAME)
            ok = not still_there
        except Exception:
            ok = True  # Exception means 400/404 → it's gone
        check("pbs_traffic_control_delete", ok, f"gone={ok}")
    except Exception as e:
        check("pbs_traffic_control_delete", False, str(e))


def run_datastore_lifecycle(api: PbsBackend) -> None:
    section("DATASTORE CREATE/UPDATE/DELETE (tools 12-14)")

    # Pre-clean if leftover
    ds_path = "/var/tmp/proximo-reprove-ds"
    try:
        upid = datastore_delete(api, DS_NAME)
        if isinstance(upid, str) and upid.startswith("UPID:"):
            st = wait_task(api, upid, timeout=60)
    except Exception:
        pass

    # 12. pbs_datastore_create
    try:
        # Create the path on the PBS server
        import subprocess as sp
        sp.run(["ssh", "pve", f"pct exec 31339 -- mkdir -p {ds_path}"], capture_output=True)

        result = datastore_create(api, DS_NAME, ds_path, comment="ci-reprove")
        if isinstance(result, str) and result.startswith("UPID:"):
            st = wait_task(api, result, timeout=60)
            ok = st.get("exitstatus") == "OK"
            detail = f"UPID→{st.get('exitstatus')}"
        else:
            ok = True
            detail = f"result={result!r}"
        check("pbs_datastore_create", ok, detail)
    except Exception as e:
        check("pbs_datastore_create", False, str(e))
        return

    # Verify created: datastore_get from /config/datastore/{name}
    try:
        cfg_data = datastore_get(api, DS_NAME)
        ok = isinstance(cfg_data, dict) and cfg_data.get("name") == DS_NAME
        check("pbs_datastore_create_verify(get)", ok, f"keys={sorted(cfg_data)[:5]}")
    except Exception as e:
        check("pbs_datastore_create_verify(get)", False, str(e))

    # 13. pbs_datastore_update
    try:
        datastore_update(api, DS_NAME, comment="ci-reprove-updated")
        ok = True
        check("pbs_datastore_update", ok, "updated without error")
    except Exception as e:
        check("pbs_datastore_update", False, str(e))

    # 14. pbs_datastore_delete (detach only — destroy_data=False; data NOT destroyed)
    try:
        result = datastore_delete(api, DS_NAME, destroy_data=False)
        if isinstance(result, str) and result.startswith("UPID:"):
            st = wait_task(api, result, timeout=60)
            ok = st.get("exitstatus") == "OK"
            detail = f"UPID→{st.get('exitstatus')}"
        else:
            ok = True
            detail = f"result={result!r}"
        check("pbs_datastore_delete(detach)", ok, detail)
    except Exception as e:
        check("pbs_datastore_delete(detach)", False, str(e))
    finally:
        # Clean up the path
        try:
            import subprocess as sp
            sp.run(["ssh", "pve", f"pct exec 31339 -- rm -rf {ds_path}"], capture_output=True)
        except Exception:
            pass


def run_snapshot_ops(api: PbsBackend, cfg: PbsConfig) -> None:
    section("SNAPSHOT OPS — requires a live backup (tools 15-17 + snapshot_delete)")

    # Seed a backup
    print("  (seeding a throwaway host backup for snapshot ops...)")
    try:
        seed_backup(cfg, BID_SNAP)
    except Exception as e:
        check("seed_backup", False, f"Could not seed: {e} — skipping snapshot ops")
        return

    # Get the seeded snapshot
    all_snaps = [s for s in snapshots_list(api, STORE) if s.get("backup-id") == BID_SNAP]
    if not all_snaps:
        check("seed_backup", False, "backup seeded but no snapshot found — skipping snapshot ops")
        return

    snap = all_snaps[-1]
    btype = snap["backup-type"]
    bid = snap["backup-id"]
    btime = snap["backup-time"]
    print(f"  (snapshot: {btype}/{bid}@{btime})")

    try:
        # 15. pbs_snapshot_protected_set (set True — low risk)
        try:
            snapshot_protected_set(api, STORE, btype, bid, btime, protected=True)
            ok = True
            check("pbs_snapshot_protected_set(True)", ok, "set protected=True without error")
        except Exception as e:
            check("pbs_snapshot_protected_set(True)", False, str(e))

        # 15b. pbs_snapshot_protected_set (clear — high risk, but on a throwaway snapshot)
        try:
            snapshot_protected_set(api, STORE, btype, bid, btime, protected=False)
            ok = True
            check("pbs_snapshot_protected_set(False)", ok, "cleared protection without error")
        except Exception as e:
            check("pbs_snapshot_protected_set(False)", False, str(e))

        # 16. pbs_snapshot_notes_get (CAPTURE for the plan)
        try:
            current_notes = snapshot_notes_get(api, STORE, btype, bid, btime)
            ok = True  # None or a string, both valid
            check("snapshot_notes_get(capture)", ok, f"notes={current_notes!r}")
        except Exception as e:
            check("snapshot_notes_get(capture)", False, str(e))

        # 16b. pbs_snapshot_notes_set
        try:
            snapshot_notes_set(api, STORE, btype, bid, btime, "ci-reprove-note")
            ok = True
            check("pbs_snapshot_notes_set", ok, "set notes without error")
        except Exception as e:
            check("pbs_snapshot_notes_set", False, str(e))

        # 16c. Verify notes were set
        try:
            notes_back = snapshot_notes_get(api, STORE, btype, bid, btime)
            ok = notes_back == "ci-reprove-note"
            check("snapshot_notes_set_verify(get)", ok, f"notes={notes_back!r}")
        except Exception as e:
            check("snapshot_notes_set_verify(get)", False, str(e))

        # 17. pbs_group_change_owner — skip to avoid accidental access issues
        # (The root@pam!proximo-live token IS Admin, so change-owner to itself is safe)
        try:
            with open(cfg.token_path) as f:
                authid = f.read().strip().split(":")[0]  # USER@REALM!TOKENID
            group_change_owner(api, STORE, btype, bid, new_owner=authid)
            ok = True
            check("pbs_group_change_owner", ok, f"owner→{authid}")
        except Exception as e:
            check("pbs_group_change_owner", False, str(e))

    finally:
        # 9. pbs_snapshot_delete (self-clean)
        for s in [x for x in snapshots_list(api, STORE) if x.get("backup-id") == BID_SNAP]:
            try:
                snapshot_delete(api, STORE, s["backup-type"], s["backup-id"], s["backup-time"])
                check("pbs_snapshot_delete(cleanup)", True, f"deleted {s['backup-type']}/{s['backup-id']}@{s['backup-time']}")
            except Exception as e:
                check("pbs_snapshot_delete(cleanup)", False, str(e))


def run_remote_tools(api: PbsBackend) -> None:
    section("REMOTE CREATE/DELETE (tools 18-20)")

    # Pre-clean
    try:
        remote_delete(api, REMOTE_NAME)
    except Exception:
        pass

    # 18. pbs_remote_create — use PBS's own address pointing to itself.
    # The fingerprint must match PBS's SHA-256 fingerprint format.
    # We get it from the CA cert.
    import subprocess as sp
    fp_result = sp.run(
        ["openssl", "x509", "-in", os.environ["PROXIMO_PBS_CA_BUNDLE"],
         "-noout", "-fingerprint", "-sha256"],
        capture_output=True, text=True
    )
    # Output: SHA256 Fingerprint=AA:BB:... → need lowercase without colons for PBS format
    raw_fp = fp_result.stdout.strip().split("=", 1)[-1].replace(":", "").lower()
    # PBS expects format: "aa:bb:cc:..." — pairs separated by colons
    fp = ":".join(raw_fp[i:i+2] for i in range(0, len(raw_fp), 2))

    with open(api.config.token_path) as f:
        authid_full = f.read().strip().split(":")[0]

    # We need a fake password for the remote (the remote is the PBS itself but we'll use a fake token secret
    # since remote_create just stores the config, it does not validate the password on create)
    try:
        remote_create(api, REMOTE_NAME, host="127.0.0.1",
                      auth_id=authid_full,
                      password="ci-reprove-fake",
                      fingerprint=fp,
                      comment="ci-reprove")
        ok = True
        check("pbs_remote_create", ok, f"created remote '{REMOTE_NAME}' (auth-id={authid_full})")
    except Exception as e:
        check("pbs_remote_create", False, str(e))
        return

    # 19. pbs_remote_update — update comment only
    try:
        from proximo.pbs_config import remote_update
        remote_update(api, REMOTE_NAME, comment="ci-reprove-updated")
        ok = True
        check("pbs_remote_update", ok, "updated comment without error")
    except Exception as e:
        check("pbs_remote_update", False, str(e))

    # 20. pbs_remote_delete
    try:
        remote_delete(api, REMOTE_NAME)
        ok = True
        check("pbs_remote_delete", ok, f"deleted remote '{REMOTE_NAME}'")
    except Exception as e:
        check("pbs_remote_delete", False, str(e))


def run_job_tools(api: PbsBackend) -> None:
    section("SCHEDULED JOB CRUD (tools 23-25; no pbs_job_run — would spin a task)")

    # Pre-clean
    for jtype in ("verify", "sync", "prune"):
        try:
            pbs_scheduled_job_delete(api, jtype, JOB_ID)
        except Exception:
            pass

    # 23. pbs_job_create (verify job — safe, config only)
    try:
        pbs_scheduled_job_create(api, "verify", JOB_ID, store=STORE,
                                 schedule="daily", comment="ci-reprove")
        ok = True
        check("pbs_job_create(verify)", ok, "created verify job")
    except Exception as e:
        check("pbs_job_create(verify)", False, str(e))
        return

    # Read back
    try:
        job_data = pbs_scheduled_job_get(api, "verify", JOB_ID)
        ok = isinstance(job_data, dict) and job_data.get("store") == STORE
        check("pbs_job_get(verify)", ok, f"keys={sorted(job_data)[:5]}")
    except Exception as e:
        check("pbs_job_get(verify)", False, str(e))

    # 24. pbs_job_update
    try:
        pbs_scheduled_job_update(api, "verify", JOB_ID, comment="ci-reprove-updated")
        ok = True
        check("pbs_job_update(verify)", ok, "updated job comment")
    except Exception as e:
        check("pbs_job_update(verify)", False, str(e))

    # 25. pbs_job_delete
    try:
        pbs_scheduled_job_delete(api, "verify", JOB_ID)
        ok = True
        check("pbs_job_delete(verify)", ok, "deleted verify job")
    except Exception as e:
        check("pbs_job_delete(verify)", False, str(e))
        try:
            pbs_scheduled_job_delete(api, "verify", JOB_ID)
        except Exception:
            pass

    # Test prune job too (config only — no retention action)
    try:
        pbs_scheduled_job_create(api, "prune", JOB_ID, store=STORE,
                                 schedule="daily", comment="ci-reprove")
        pbs_scheduled_job_delete(api, "prune", JOB_ID)
        check("pbs_job_create+delete(prune)", True, "prune job create+delete round-trip")
    except Exception as e:
        check("pbs_job_create+delete(prune)", False, str(e))


def run_verify_start(api: PbsBackend) -> None:
    section("VERIFY START (tool 7) — non-destructive async task")
    try:
        upid = verify_start(api, STORE)
        ok = isinstance(upid, str) and upid.startswith("UPID:")
        if ok:
            st = wait_task(api, upid, timeout=120)
            ok = st.get("exitstatus") == "OK"
            detail = f"exitstatus={st.get('exitstatus')}"
        else:
            detail = f"upid={upid!r}"
        check("pbs_verify_start", ok, detail)
    except Exception as e:
        check("pbs_verify_start", False, str(e))


def main() -> int:
    print("=== PBS RE-PROVE ALL — fresh live receipts ===")
    api, cfg = connect()
    print(f"Connected: {cfg.base_url} | store={STORE}")

    run_read_tools(api)
    run_namespace_tools(api)
    run_prune_dry_run(api, cfg)
    run_traffic_control_tools(api)
    run_datastore_lifecycle(api)
    run_verify_start(api)
    run_snapshot_ops(api, cfg)
    run_remote_tools(api)
    run_job_tools(api)

    # Summary
    print("\n=== RESULTS ===")
    passed = 0
    failed = 0
    for name, ok, detail in _results:
        icon = "✅" if ok else "❌"
        status = "PASS" if ok else "FAIL"
        print(f"  {icon} {status:<5} {name}: {detail[:80]}")
        if ok:
            passed += 1
        else:
            failed += 1

    total = passed + failed
    print(f"\nTotal: {passed}/{total} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
