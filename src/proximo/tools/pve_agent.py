"""qemu-agent read/mutation tools (pve_agent_exec itself stays in server.py — it gates before its own auto-undo).

Split out of proximo.server (2026-07-02) — see proximo/server.py's module
docstring for the funnel these wrappers depend on.
"""
from __future__ import annotations

import proximo.server as _proximo_server
from proximo.backends import ProximoError
from proximo.qemu_agent import (
    _check_agent_fs_command,
    _check_agent_info_command,
    _check_file_path,
    _content_fingerprint,
    _password_fingerprint,
    plan_agent_file_write,
    plan_agent_fs,
    plan_agent_set_password,
)
from proximo.server import (
    _agent_gate,
    _audited,
    _plan,
    tool,
)


@tool()
def pve_agent_info(
    vmid: str,
    command: str = "info",
    pid: int | None = None,
    node: str | None = None,
) -> dict:
    """READ-ONLY: query the qemu-agent on a guest (ping, osinfo, hostname, users, exec-status, …).

    Requires PROXIMO_ENABLE_AGENT=1 and the VMID in PROXIMO_AGENT_ALLOWLIST.
    No confirm needed — read-only.

    command: one of ping, info, get-fsinfo, get-host-name, get-osinfo, get-time,
             get-timezone, get-users, get-vcpus, network-get-interfaces,
             get-memory-blocks, fsfreeze-status, exec-status.
    pid: required when command='exec-status' (the pid returned by pve_agent_exec).
    """
    cfg, api, _, _ = _proximo_server._svc()
    blocked = _agent_gate(cfg, "pve_agent_info", vmid, mutation=False)
    if blocked:
        return blocked

    _check_agent_info_command(command)

    if command == "exec-status":
        if pid is None:
            raise ProximoError("exec-status requires pid")
        return _audited("pve_agent_info", f"qemu/{vmid}",
                        lambda: api.agent_exec_status(vmid, node, pid))
    return _audited("pve_agent_info", f"qemu/{vmid}",
                    lambda: api.agent_simple(vmid, node, command))


@tool()
def pve_agent_file_read(
    vmid: str,
    file: str,
    node: str | None = None,
) -> dict:
    """READ-ONLY: read a file from inside the guest via the qemu-agent.

    Requires PROXIMO_ENABLE_AGENT=1 and the VMID in PROXIMO_AGENT_ALLOWLIST.
    No confirm needed — read-only.  File path must be absolute.

    Ledger records only the file path (never the content); the returned dict carries content.
    Smoke-confirm: PVE file-read response shape is unverified.
    """
    cfg, api, _, _ = _proximo_server._svc()
    blocked = _agent_gate(cfg, "pve_agent_file_read", vmid, mutation=False)
    if blocked:
        return blocked

    _check_file_path(file)
    return _audited("pve_agent_file_read", f"qemu/{vmid}",
                    lambda: api.agent_file_read(vmid, node, file),
                    detail={"file": file})


@tool()
def pve_agent_file_write(
    vmid: str,
    file: str,
    content: str,
    node: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: write a file inside the guest via the qemu-agent.

    Dry-run by default: without confirm=True you get a PLAN recorded to the ledger.
    Re-call with confirm=True to execute.

    Requires PROXIMO_ENABLE_AGENT=1 and the VMID in PROXIMO_AGENT_ALLOWLIST.
    File path must be absolute.  Content is UNCONDITIONALLY redacted from the ledger.
    No undo primitive on this plane.
    Smoke-confirm: PVE file-write endpoint and content encoding are unverified.
    """
    cfg, api, _, _ = _proximo_server._svc()
    blocked = _agent_gate(cfg, "pve_agent_file_write", vmid, mutation=True)
    if blocked:
        return blocked

    # UNCONDITIONAL: content fingerprint only, never the body.
    detail = {"file": file, **_content_fingerprint(content)}
    plan = _plan("pve_agent_file_write", f"qemu/{vmid}:{file}",
                 lambda: plan_agent_file_write(vmid, file, content, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}

    return _audited("pve_agent_file_write", f"qemu/{vmid}:{file}",
                    lambda: api.agent_file_write(vmid, node, file, content),
                    mutation=True, outcome="ok", detail={**detail, "confirmed": True})


@tool()
def pve_agent_fs(
    vmid: str,
    command: str,
    node: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: fsfreeze-freeze, fsfreeze-thaw, or fstrim inside the guest via the qemu-agent.

    Dry-run by default: without confirm=True you get a PLAN recorded to the ledger.
    Re-call with confirm=True to execute.

    Requires PROXIMO_ENABLE_AGENT=1 and the VMID in PROXIMO_AGENT_ALLOWLIST.
    command: fsfreeze-freeze | fsfreeze-thaw | fstrim
    No undo primitive on this plane; always pair freeze with thaw.
    """
    cfg, api, _, _ = _proximo_server._svc()
    blocked = _agent_gate(cfg, "pve_agent_fs", vmid, mutation=True)
    if blocked:
        return blocked

    _check_agent_fs_command(command)
    plan = _plan("pve_agent_fs", f"qemu/{vmid}:{command}",
                 lambda: plan_agent_fs(vmid, command, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}

    return _audited("pve_agent_fs", f"qemu/{vmid}:{command}",
                    lambda: api.agent_simple(vmid, node, command),
                    mutation=True, outcome="ok",
                    detail={"command": command, "confirmed": True})


@tool()
def pve_agent_set_password(
    vmid: str,
    username: str,
    password: str,
    node: str | None = None,
    confirm: bool = False,
) -> dict:
    """MUTATION: set a guest OS user's password via the qemu-agent.

    Dry-run by default: without confirm=True you get a PLAN recorded to the ledger.
    Re-call with confirm=True to execute.

    Requires PROXIMO_ENABLE_AGENT=1 and the VMID in PROXIMO_AGENT_ALLOWLIST.
    Password is UNCONDITIONALLY redacted from the ledger (fingerprint only — "[redacted]").
    No undo primitive on this plane.
    Smoke-confirm: PVE set-user-password endpoint and body fields are unverified.
    """
    cfg, api, _, _ = _proximo_server._svc()
    blocked = _agent_gate(cfg, "pve_agent_set_password", vmid, mutation=True)
    if blocked:
        return blocked

    # UNCONDITIONAL: password redacted always, regardless of cfg.redact_ledger.
    detail = {"username": username, **_password_fingerprint()}
    plan = _plan("pve_agent_set_password", f"qemu/{vmid}:{username}",
                 lambda: plan_agent_set_password(vmid, username, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}

    return _audited("pve_agent_set_password", f"qemu/{vmid}:{username}",
                    lambda: api.agent_set_password(vmid, node, username, password),
                    mutation=True, outcome="ok", detail={**detail, "confirmed": True})
