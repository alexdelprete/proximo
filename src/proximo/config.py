"""Proximo configuration.

Loaded from the environment. The PVE token is referenced by *path*, never inlined —
Proximo reads it at call time and never logs it, so the credential stays
"run-but-not-read" (the operator's secrets vault is never echoed).
"""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass

from .audit import looks_like_head


@dataclass(frozen=True)
class ProximoConfig:
    # --- Management half (Proxmox REST API) ---
    api_base_url: str          # e.g. "https://pve.example.lan:8006/api2/json"
    node: str                  # default node name, e.g. "pve"
    token_path: str            # file containing: USER@REALM!TOKENID=SECRET  (run-but-not-read)

    # --- Exec half (ssh -> pct) ---
    ssh_target: str = "pve"    # ssh host alias; or "local"/"localhost"/"" to run ON the host (direct pct)

    # --- Safety ---
    ct_allowlist: frozenset[str] = frozenset()  # empty=DENY all (fail-closed); "*"=allow all; else exact CTIDs
    audit_log_path: str = os.path.expanduser("~/.local/state/proximo/audit.log")
    verify_tls: bool = True
    ca_bundle: str | None = None  # path to the internal/Caddy CA bundle; preferred over disabling TLS verify
    enable_exec: bool = False  # OFF by default (API-only, safe). True enables ssh->pct exec (root-grant tradeoff).
    audit_key_path: str | None = None  # opt-in: path to an HMAC key file → keyed (tamper-resistant) PROVE ledger
    audit_keyed: bool = True  # PROXIMO_AUDIT_KEYED — keyed (HMAC) PROVE by default; "off"/"0"/"false"/"no" disables
    redact_ledger: bool = False  # opt-in: store a fingerprint of ct_psql SQL / ct_exec argv, not the body
    expected_head: str | None = None  # PROXIMO_AUDIT_EXPECTED_HEAD — off-box-pinned head() for tail-attack detection

    @classmethod
    def from_env(cls) -> ProximoConfig:
        try:
            api_base_url = os.environ["PROXIMO_API_BASE_URL"]
            node = os.environ["PROXIMO_NODE"]
            token_path = os.environ["PROXIMO_TOKEN_PATH"]
        except KeyError as e:  # fail loud, never guess
            raise RuntimeError(f"Missing required Proximo env var: {e.args[0]}") from e

        allow = os.environ.get("PROXIMO_CT_ALLOWLIST", "").strip()
        ct_allowlist = frozenset(c.strip() for c in allow.split(",") if c.strip())

        verify_tls = os.environ.get("PROXIMO_VERIFY_TLS", "true").lower() != "false"
        ca_bundle = os.environ.get("PROXIMO_CA_BUNDLE") or None
        enable_exec = os.environ.get("PROXIMO_ENABLE_EXEC", "false").lower() in ("1", "true", "yes", "on")
        audit_key_path = os.environ.get("PROXIMO_AUDIT_KEY_PATH") or None
        audit_keyed = os.environ.get("PROXIMO_AUDIT_KEYED", "true").lower() not in ("0", "false", "off", "no")
        redact_ledger = os.environ.get("PROXIMO_LEDGER_REDACT", "false").lower() in ("1", "true", "yes", "on")

        expected_head = os.environ.get("PROXIMO_AUDIT_EXPECTED_HEAD") or None
        if expected_head is not None and not looks_like_head(expected_head):
            raise RuntimeError(
                "PROXIMO_AUDIT_EXPECTED_HEAD must be a 64-char lowercase hex head() value "
                "(a sha256/hmac-sha256 hexdigest); got a malformed value"
            )

        # Honest warnings (no phantom comments): least-privilege and TLS are load-bearing.
        if "*" in ct_allowlist:
            warnings.warn(
                "PROXIMO_CT_ALLOWLIST='*' — Proximo can reach ALL containers (least-privilege disabled).",
                stacklevel=2,
            )
        if not verify_tls and not ca_bundle:
            warnings.warn(
                "PROXIMO_VERIFY_TLS=false with no CA bundle — talking to the PVE API without cert validation.",
                stacklevel=2,
            )
        if enable_exec:
            warnings.warn(
                "PROXIMO_ENABLE_EXEC is on — ssh->pct in-container exec enabled. This grants near-root on the "
                "PVE host; scope the ssh user and set a CTID allowlist.",
                stacklevel=2,
            )

        return cls(
            api_base_url=api_base_url.rstrip("/"),
            node=node,
            token_path=token_path,
            ssh_target=os.environ.get("PROXIMO_SSH_TARGET", "pve"),
            ct_allowlist=ct_allowlist,
            audit_log_path=os.environ.get("PROXIMO_AUDIT_LOG", cls.audit_log_path),
            verify_tls=verify_tls,
            ca_bundle=ca_bundle,
            enable_exec=enable_exec,
            audit_key_path=audit_key_path,
            audit_keyed=audit_keyed,
            redact_ledger=redact_ledger,
            expected_head=expected_head,
        )

    def ct_permitted(self, ctid: str) -> bool:
        """Least-privilege gate — fails CLOSED.

        Empty allowlist => deny everything (you must opt in).
        "*" => allow all CTIDs (warned about at load time).
        Otherwise => exact CTID match only.
        """
        if not self.ct_allowlist:
            return False
        if "*" in self.ct_allowlist:
            return True
        return str(ctid) in self.ct_allowlist

    @property
    def is_local(self) -> bool:
        """True when Proximo runs ON the PVE host itself.

        On-host: call `pct`/`pvesh` directly — no ssh hop, no quote layer.
        Off-host (default): reach the node via API token + ssh -> pct.
        Set ssh_target to "local"/"localhost"/"" for on-host mode.
        """
        return self.ssh_target.strip().lower() in ("", "local", "localhost")
