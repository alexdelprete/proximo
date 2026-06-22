"""Shared helpers for the PBS live-smokes.

Every PBS smoke:
  * routes its management ops through proximo's PbsBackend (datastore/prune/gc/verify/snapshot/namespace);
  * is GUARDED — `connect()` calls safety.assert_test_pbs, refusing any non-allowlisted PBS host
    (default-deny) before the smoke touches it, so a destructive op can never hit the prod PBS;
  * is SELF-SEEDING — `seed_backup()` pushes a throwaway host backup via the local proxmox-backup-client
    so the smoke creates exactly the snapshots it needs and self-cleans (no external fixture);
  * the token secret is read from the token file in-process and passed to the client by env — never
    printed, never on a command line that would land in a transcript.

Run with the test-PBS env sourced (PROXIMO_PBS_BASE_URL / _TOKEN_PATH / _CA_BUNDLE / _FINGERPRINT)
plus the guard allowlist PROXIMO_SMOKE_PBS_HOSTS=<test-pbs-host>.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from safety import assert_test_pbs, load_pbs_allowlist  # noqa: E402  (sibling live-smoke module)

from proximo.pbs import PbsBackend, PbsConfig  # noqa: E402

STORE = os.environ.get("SMOKE_PBS_STORE", "test-ds")


def connect() -> tuple[PbsBackend, PbsConfig]:
    """Build the PBS backend AND assert the endpoint is an allowlisted test PBS (default-deny)."""
    cfg = PbsConfig.from_env()
    assert_test_pbs(cfg.base_url, load_pbs_allowlist(os.environ))
    return PbsBackend(cfg), cfg


def _authid_and_secret(cfg: PbsConfig) -> tuple[str, str]:
    with open(cfg.token_path, encoding="utf-8") as f:
        authid, secret = f.read().strip().split(":", 1)  # USER@REALM!TOKENID : SECRET
    return authid, secret


def seed_backup(cfg: PbsConfig, backup_id: str) -> None:
    """Create ONE throwaway host backup (backup-id=<backup_id>) in the test datastore.

    Uses the local proxmox-backup-client over the network. The token secret is passed via env,
    never echoed or placed on the command line.
    """
    authid, secret = _authid_and_secret(cfg)
    host = urlparse(cfg.base_url).hostname
    env = dict(os.environ)
    env["PBS_PASSWORD"] = secret
    if cfg.fingerprint:
        env["PBS_FINGERPRINT"] = cfg.fingerprint
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "marker"), "w", encoding="utf-8") as f:
            f.write("proximo-ci-smoke\n")
        r = subprocess.run(
            ["proxmox-backup-client", "backup", f"data.pxar:{d}",
             "--repository", f"{authid}@{host}:{STORE}",
             "--backup-id", backup_id, "--crypt-mode", "none"],
            env=env, capture_output=True, text=True,
        )
    if r.returncode != 0:
        raise RuntimeError(f"seed backup-id={backup_id} failed: {r.stderr.strip()[-300:]}")


def wait_task(api: PbsBackend, upid: str, timeout: int = 180) -> dict:
    """Poll a PBS async task (gc/verify) to completion; return its final status dict."""
    node = upid.split(":")[1] if upid.startswith("UPID:") else "localhost"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = api._get(f"/nodes/{node}/tasks/{quote(upid, safe='')}/status") or {}
        if st.get("status") == "stopped":
            return st
        time.sleep(1)
    raise TimeoutError(f"PBS task {upid} did not finish within {timeout}s")


def snap_ids(snaps: list[dict]) -> list[str]:
    """Compact 'type/id/time' labels for a snapshot list."""
    return [f"{s.get('backup-type')}/{s.get('backup-id')}/{s.get('backup-time')}" for s in snaps]
