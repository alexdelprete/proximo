"""Proximo configuration.

Loaded from the environment. The PVE token is referenced by *path*, never inlined —
Proximo reads it at call time and never logs it, so the credential stays
"run-but-not-read" (the operator's secrets vault is never echoed).
"""

from __future__ import annotations

import os
import re
import warnings
from dataclasses import dataclass

from .audit import looks_like_head

# Charset for PROXIMO_SSH_TARGET: hostname, SSH alias, or user@host.
# Must start with alphanumeric to block option-injection (e.g. -oProxyCommand=...).
# Empty string is allowed separately (local/on-host mode via is_local).
_SSH_TARGET_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@-]*\Z")

# PROXIMO_VERIFY_TLS — full falsy/truthy sets (matching audit_keyed's pattern).
# Unrecognized values keep TLS on (safe default) and emit a diagnostic warning.
_VTLS_FALSY = frozenset({"0", "false", "off", "no"})
_VTLS_TRUTHY = frozenset({"1", "true", "on", "yes"})


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
    enable_agent: bool = False  # OFF by default (API-only, safe). True enables qemu-agent ops on VMs.
    agent_allowlist: frozenset[str] = frozenset()  # empty=DENY all; "*"=allow all; else exact VMIDs
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
        return cls._build(
            api_base_url=api_base_url,
            node=node,
            token_path=token_path,
            ssh_target=os.environ.get("PROXIMO_SSH_TARGET", "pve"),
            ct_allow_raw=os.environ.get("PROXIMO_CT_ALLOWLIST", ""),
            agent_allow_raw=os.environ.get("PROXIMO_AGENT_ALLOWLIST", ""),
            vtls_raw=os.environ.get("PROXIMO_VERIFY_TLS", "true"),
            ca_bundle=os.environ.get("PROXIMO_CA_BUNDLE") or None,
            enable_exec=os.environ.get("PROXIMO_ENABLE_EXEC", "false").lower() in ("1", "true", "yes", "on"),
            enable_agent=os.environ.get("PROXIMO_ENABLE_AGENT", "false").lower() in ("1", "true", "yes", "on"),
            audit_key_path=os.environ.get("PROXIMO_AUDIT_KEY_PATH") or None,
            audit_keyed_raw=os.environ.get("PROXIMO_AUDIT_KEYED", "true"),
            redact_ledger=os.environ.get("PROXIMO_LEDGER_REDACT", "false").lower() in ("1", "true", "yes", "on"),
            expected_head_raw=os.environ.get("PROXIMO_AUDIT_EXPECTED_HEAD") or "",
            audit_log_path=os.environ.get("PROXIMO_AUDIT_LOG", cls.audit_log_path),
        )

    @classmethod
    def from_target(cls, fields: dict) -> ProximoConfig:
        """Build a config for a named registry remote (see proximo.targets).

        Same validation, defaults, and fail-closed warnings as from_env — they share _build.
        Secrets stay by reference (token_path), never inlined in the registry.
        """
        try:
            api_base_url = fields["base_url"]
            node = fields["node"]
            token_path = fields["token_path"]
        except KeyError as e:  # fail loud, never guess
            raise RuntimeError(f"target missing required field: {e.args[0]}") from e

        def _csv(key: str) -> str:
            # Accept a TOML list OR a comma string for allowlists; _build splits on commas.
            v = fields.get(key, "")
            return ",".join(str(x) for x in v) if isinstance(v, list) else str(v)

        return cls._build(
            api_base_url=api_base_url,
            node=node,
            token_path=token_path,
            ssh_target=fields.get("ssh_target", "pve"),
            ct_allow_raw=_csv("ct_allowlist"),
            agent_allow_raw=_csv("agent_allowlist"),
            vtls_raw=str(fields.get("verify_tls", "true")),
            ca_bundle=fields.get("ca_bundle") or None,
            enable_exec=bool(fields.get("enable_exec", False)),
            enable_agent=bool(fields.get("enable_agent", False)),
            audit_key_path=fields.get("audit_key_path") or None,
            audit_keyed_raw=str(fields.get("audit_keyed", "true")),
            redact_ledger=bool(fields.get("redact_ledger", False)),
            expected_head_raw=str(fields.get("audit_expected_head") or ""),
            audit_log_path=fields.get("audit_log", cls.audit_log_path),
        )

    @classmethod
    def _build(
        cls,
        *,
        api_base_url: str,
        node: str,
        token_path: str,
        ssh_target: str,
        ct_allow_raw: str,
        agent_allow_raw: str,
        vtls_raw: str,
        ca_bundle: str | None,
        enable_exec: bool,
        enable_agent: bool,
        audit_key_path: str | None,
        audit_keyed_raw: str,
        redact_ledger: bool,
        expected_head_raw: str,
        audit_log_path: str,
    ) -> ProximoConfig:
        """Shared validation/normalization/warnings for from_env and from_target.

        Both heads extract their required fields, then converge here so an env-configured box
        and a registry target get IDENTICAL fail-closed treatment.
        """
        ct_allowlist = frozenset(c.strip() for c in ct_allow_raw.strip().split(",") if c.strip())
        agent_allowlist = frozenset(c.strip() for c in agent_allow_raw.strip().split(",") if c.strip())

        _vtls_raw = vtls_raw.strip().lower()
        verify_tls = _vtls_raw not in _VTLS_FALSY
        audit_keyed = audit_keyed_raw.strip().lower() not in ("0", "false", "off", "no")

        # Normalize the pin before validating: a head() hexdigest is case-insensitive, and a copy-paste
        # from the migration warning often carries a trailing newline / surrounding spaces. Without this,
        # an uppercased/whitespaced pin raises here — and since _svc() runs from_env() for EVERY tool,
        # that bricks all of them, not just audit_verify. Genuinely-malformed values still raise.
        expected_head = expected_head_raw.strip().lower() or None
        if expected_head is not None and not looks_like_head(expected_head):
            raise RuntimeError(
                "PROXIMO_AUDIT_EXPECTED_HEAD must be a 64-char hex head() value "
                "(a sha256/hmac-sha256 hexdigest); got a malformed value"
            )

        # Validate the ssh target charset: empty string is the on-host sentinel (is_local);
        # any non-empty value must be a safe hostname/alias/user@host — a leading '-' would be
        # parsed by ssh as an option flag, enabling option-injection (e.g. -oProxyCommand=...).
        if ssh_target and not _SSH_TARGET_RE.match(ssh_target):
            raise RuntimeError(
                f"PROXIMO_SSH_TARGET must be a hostname or SSH alias "
                f"(characters: A-Z a-z 0-9 . _ @ -); got: {ssh_target!r}"
            )

        # Honest warnings (no phantom comments): least-privilege and TLS are load-bearing.
        if "*" in ct_allowlist:
            warnings.warn(
                "PROXIMO_CT_ALLOWLIST='*' — Proximo can reach ALL containers (least-privilege disabled).",
                stacklevel=2,
            )
        if _vtls_raw not in _VTLS_FALSY | _VTLS_TRUTHY:
            warnings.warn(
                f"PROXIMO_VERIFY_TLS={_vtls_raw!r} is not a recognized boolean value; "
                "TLS verification stays ON. Use 'false', '0', 'no', or 'off' to disable.",
                stacklevel=2,
            )
        if not verify_tls and not ca_bundle:
            # ApiBackend refuses to construct when verify_tls=False and no ca_bundle is set —
            # this warning fires immediately before that hard failure so operators can act.
            warnings.warn(
                "PROXIMO_VERIFY_TLS=false with no CA bundle — the backend will refuse to "
                "start (fail-closed). Set PROXIMO_CA_BUNDLE to a PEM CA file or use "
                "PROXIMO_VERIFY_TLS=true.",
                stacklevel=2,
            )
        if enable_exec:
            warnings.warn(
                "PROXIMO_ENABLE_EXEC is on — ssh->pct in-container exec enabled. This grants near-root on the "
                "PVE host; scope the ssh user and set a CTID allowlist.",
                stacklevel=2,
            )
        if enable_agent:
            warnings.warn(
                "PROXIMO_ENABLE_AGENT is on — qemu-agent ops enabled. Set a VMID allowlist "
                "(PROXIMO_AGENT_ALLOWLIST) to restrict which guests can be reached.",
                stacklevel=2,
            )
        if enable_agent and "*" in agent_allowlist:
            warnings.warn(
                "PROXIMO_AGENT_ALLOWLIST='*' — qemu-agent can reach ALL VMs (least-privilege disabled).",
                stacklevel=2,
            )
        if not audit_keyed:
            warnings.warn(
                "PROXIMO_AUDIT_KEYED is off — the PROVE ledger is running unkeyed (bare "
                "SHA-256, not HMAC-SHA256). Anyone with write access to the log file can "
                "forge entries without detection. Set PROXIMO_AUDIT_KEYED=true (the default) "
                "to restore HMAC-SHA256 tamper-evidence.",
                stacklevel=2,
            )

        return cls(
            api_base_url=api_base_url.rstrip("/"),
            node=node,
            token_path=token_path,
            ssh_target=ssh_target,
            ct_allowlist=ct_allowlist,
            audit_log_path=audit_log_path,
            verify_tls=verify_tls,
            ca_bundle=ca_bundle,
            enable_exec=enable_exec,
            audit_key_path=audit_key_path,
            audit_keyed=audit_keyed,
            redact_ledger=redact_ledger,
            expected_head=expected_head,
            enable_agent=enable_agent,
            agent_allowlist=agent_allowlist,
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

    def agent_permitted(self, vmid: str) -> bool:
        """Least-privilege gate for qemu-agent ops — fails CLOSED.

        Empty allowlist => deny everything (you must opt in).
        "*" => allow all VMIDs (warned about at load time).
        Otherwise => exact VMID match only.
        """
        if not self.agent_allowlist:
            return False
        if "*" in self.agent_allowlist:
            return True
        return str(vmid) in self.agent_allowlist

    @property
    def is_local(self) -> bool:
        """True when Proximo runs ON the PVE host itself.

        On-host: call `pct`/`pvesh` directly — no ssh hop, no quote layer.
        Off-host (default): reach the node via API token + ssh -> pct.
        Set ssh_target to "local"/"localhost"/"" for on-host mode.
        """
        return self.ssh_target.strip().lower() in ("", "local", "localhost")
