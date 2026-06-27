"""Proximo qemu-agent plane — in-guest operations via the QEMU Guest Agent protocol.

VERIFIED live (PVE 9.2 + qemu-guest-agent, 2026-06-25): the enable+allowlist gate, exec (POST exec
→ poll GET exec-status; out-data plain text), file-read/file-write text round-trip, set-user-password,
fstrim, fsfreeze-status, and the GET-for-reads / POST-for-actions method split (a POST to a get-*
path 501s). Remaining Smoke-confirm: binary file content (base64/encode param), fsfreeze-freeze/thaw
on a live guest (not exercised — freezing a real FS in a smoke run is reckless).

Six tools:
  pve_agent_exec        — run a command inside the guest (async, poll for result)
  pve_agent_info        — read-only guest-agent queries (ping, osinfo, hostname, …)
  pve_agent_file_read   — read a file from inside the guest
  pve_agent_file_write  — write a file inside the guest (content unconditionally redacted)
  pve_agent_fs          — fsfreeze-freeze / fsfreeze-thaw / fstrim
  pve_agent_set_password — set a guest OS user password (password unconditionally redacted)

Security posture:
- Opt-in gate: PROXIMO_ENABLE_AGENT=1 required (off by default).
- VMID allowlist: PROXIMO_AGENT_ALLOWLIST (CSV); empty = deny all (fail-closed).
- Defense-in-depth: gate also enforced at ApiBackend layer.
- Unconditional redaction: password and file content NEVER appear in plan, change,
  ledger, or detail — not even with redact_ledger=False.  Only a fingerprint is stored.
- No UNDO: PVE has no in-guest snapshot primitive; all mutations declare irreversible.
"""

from __future__ import annotations

import hashlib
import re
import shlex

# Canonical agent command sets + shared validators live in backends (avoids circular imports).
from .backends import (
    _VALID_AGENT_FS_CMDS,
    _VALID_AGENT_INFO_CMDS,
    ProximoError,
    _check_node,
    _check_username,
    _check_vmid,
)
from .planning import RISK_HIGH, RISK_MEDIUM, Plan, command_fingerprint

# Absolute-path file validator: must start with '/'; reject ALL C0 control chars (incl. CR/LF/TAB) and
# DEL — these have no place in a path and are the header/URL-injection vectors. Printable chars
# (incl. space, which is legal in guest paths) are allowed and percent-encoded by the backend.
# \Z anchor prevents trailing-newline slip-through (same discipline as _NODE_RE).
_FILE_PATH_RE = re.compile(r"^/[^\x00-\x1f\x7f]*\Z")


def _check_file_path(path: str) -> str:
    if not _FILE_PATH_RE.match(path):
        raise ProximoError(
            f"invalid file path: {path!r} (must be an absolute path starting with '/')"
        )
    if ".." in path.split("/"):
        raise ProximoError(f"path traversal not allowed: {path!r}")
    return path


def _check_agent_info_command(command: str) -> str:
    # exec-status is handled separately (requires pid); include it in the info set for pve_agent_info
    # so callers can check pid status via the unified read tool.
    valid = _VALID_AGENT_INFO_CMDS | frozenset({"exec-status"})
    if command not in valid:
        raise ProximoError(
            f"unsupported agent info command: {command!r} "
            f"(valid: {sorted(valid)!r})"
        )
    return command


def _check_agent_fs_command(command: str) -> str:
    if command not in _VALID_AGENT_FS_CMDS:
        raise ProximoError(
            f"unsupported agent fs command: {command!r} "
            f"(valid: {sorted(_VALID_AGENT_FS_CMDS)!r})"
        )
    return command


def _content_fingerprint(content: str) -> dict:
    """Unconditional redaction for file content — returns length + sha256, never the body."""
    digest = hashlib.sha256(content.encode()).hexdigest()
    return {"content_sha256": digest, "content_len": len(content)}


def _password_fingerprint() -> dict:
    """Unconditional redaction for passwords — never store even a hash of the password."""
    return {"password": "[redacted]"}


# ---------------------------------------------------------------------------
# Plan factories
# ---------------------------------------------------------------------------

def plan_agent_exec(vmid: str, command: list[str], node: str | None = None,
                    redact: bool = False) -> Plan:
    """Plan for pve_agent_exec — run a command inside the guest via the agent.

    Risk heuristic: any exec inside a guest is at least MEDIUM.
    redact=True (PROXIMO_LEDGER_REDACT) records an argv fingerprint, not the argv — a guest exec
    command can carry a secret (e.g. `mysql -pPW`), exactly like ct_exec.
    No UNDO: PVE has no in-guest snapshot primitive for this plane.
    """
    _check_vmid(vmid)
    _check_node(node)
    if redact:
        fp = command_fingerprint(command)
        cmd_display = f"[redacted {fp['cmd_kind']}, {fp['cmd_len']} chars, sha256:{fp['cmd_sha256'][:12]}]"
    else:
        cmd_display = shlex.join(command)
    return Plan(
        action="pve_agent_exec",
        target=f"qemu/{vmid}",
        change=f"execute guest command via qemu-agent: {cmd_display}",
        current={},
        blast_radius=[f"guest/{vmid} process tree"],
        risk=RISK_MEDIUM,
        risk_reasons=["runs arbitrary command inside the guest OS"],
        note=(
            "No UNDO: qemu-agent exec has no in-guest snapshot primitive on this plane. "
            "The command runs INSIDE the guest OS. Irreversible."
        ),
    )


def plan_agent_file_write(
    vmid: str, file: str, content: str, node: str | None = None
) -> Plan:
    """Plan for pve_agent_file_write — write a file inside the guest.

    Content is UNCONDITIONALLY redacted: only a fingerprint appears in the plan.
    No UNDO: no in-guest snapshot primitive on this plane.
    """
    _check_vmid(vmid)
    _check_file_path(file)
    _check_node(node)
    fingerprint = _content_fingerprint(content)
    return Plan(
        action="pve_agent_file_write",
        target=f"qemu/{vmid}:{file}",
        change=(
            f"write file {file!r} inside guest {vmid} via qemu-agent "
            f"(content_len={fingerprint['content_len']}, sha256={fingerprint['content_sha256'][:16]}…)"
        ),
        # UNCONDITIONAL: content never appears in current or any plan field.
        current={"file": file, **fingerprint},
        blast_radius=[f"guest/{vmid}:{file}"],
        risk=RISK_HIGH,
        risk_reasons=[
            "overwrites an arbitrary file inside the guest OS — the path is caller-supplied "
            "(could be /etc/shadow, sshd_config, a binary); irreversible, no in-guest snapshot"
        ],
        note=(
            "No UNDO: qemu-agent file-write has no in-guest snapshot primitive on this plane. "
            "Content is unconditionally redacted from the ledger (fingerprint only). Irreversible."
        ),
    )


def plan_agent_fs(vmid: str, command: str, node: str | None = None) -> Plan:
    """Plan for pve_agent_fs — fsfreeze-freeze, fsfreeze-thaw, or fstrim.

    Risk level varies by command:
      fsfreeze-freeze → HIGH  (freezes guest I/O; can stall if not thawed)
      fsfreeze-thaw   → HIGH  (restores I/O; paired with freeze)
      fstrim          → MEDIUM (trims thin-provisioned disk; low risk but irreversible)
    No UNDO on this plane.
    """
    _check_vmid(vmid)
    _check_agent_fs_command(command)
    _check_node(node)
    if command in ("fsfreeze-freeze", "fsfreeze-thaw"):
        risk = RISK_HIGH
        risk_reasons = [
            f"agent {command} freezes/unfreezes guest I/O — stall risk if freeze is not paired with thaw"
        ]
    else:
        risk = RISK_MEDIUM
        risk_reasons = ["fstrim reclaims thin-provisioned blocks inside the guest; irreversible but safe"]
    return Plan(
        action="pve_agent_fs",
        target=f"qemu/{vmid}:{command}",
        change=f"agent fs command {command!r} on guest {vmid}",
        current={},
        blast_radius=[f"guest/{vmid} filesystem I/O"],
        risk=risk,
        risk_reasons=risk_reasons,
        note=(
            f"No UNDO: agent {command} has no in-guest snapshot primitive on this plane. "
            "Irreversible; ensure freeze and thaw are always paired."
        ),
    )


def plan_agent_set_password(
    vmid: str, username: str, node: str | None = None
) -> Plan:
    """Plan for pve_agent_set_password — set a guest OS user password.

    Password is UNCONDITIONALLY redacted from plan, ledger, and all detail fields.
    No UNDO on this plane.
    """
    _check_vmid(vmid)
    _check_username(username)
    _check_node(node)
    return Plan(
        action="pve_agent_set_password",
        target=f"qemu/{vmid}:{username}",
        change=f"set password for guest OS user {username!r} via qemu-agent on guest {vmid}",
        # UNCONDITIONAL: password never appears in current or any plan field.
        current={"username": username, "password": "[redacted]"},
        blast_radius=[f"guest/{vmid} user {username!r} credentials"],
        risk=RISK_HIGH,
        risk_reasons=["changes a guest OS user password; irreversible without knowledge of old password"],
        note=(
            "No UNDO: set-user-password has no in-guest snapshot primitive on this plane. "
            "Password is unconditionally redacted from the ledger. Irreversible."
        ),
    )
