"""Proximo backends: the two halves of Proxmox control.

ApiBackend  -> management via the Proxmox REST API + scoped token.
ExecBackend -> in-container work via ssh -> pct exec (the API has no LXC-exec endpoint).

Security posture:
- The token is read from disk at call time and NEVER logged.
- ExecBackend shells out to the operator's existing `ssh` host alias; no password handling.
- The CTID allowlist is enforced (fail-closed) before any exec.
- API path components (vmid/kind/node) are validated, not trusted.
- TLS verification prefers a CA bundle over disabling verification.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass

import httpx

from ._tls import httpx_verify
from .config import ProximoConfig

# NB: \Z (not $) — Python's $ matches before a trailing newline, so "valid\n" would slip through.
_VALID_KINDS = frozenset({"lxc", "qemu"})
_NODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\Z")
# Snapshot name: PVE requires a leading letter, then letters/digits/_/- (hyphen on newer PVE).
# Also the gate against path traversal in the {snapname} URL segment (no '/', '..', spaces, newline).
_SNAPNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}\Z")
# Task UPID: "UPID:node:pid:pstart:starttime:type:id:user:" — colon-delimited, no '/'. Length-capped.
_UPID_RE = re.compile(r"^UPID:[A-Za-z0-9._:@!-]{1,256}\Z")


class ProximoError(RuntimeError):
    """Operational error surfaced to the caller (never carries secrets)."""


def _check_vmid(vmid: str) -> str:
    if not re.fullmatch(r"[0-9]+", str(vmid)):  # ASCII 0-9 only; str.isdigit() also accepts Unicode digits
        raise ProximoError(f"invalid vmid: {vmid!r} (must be numeric)")
    return str(vmid)


def _check_kind(kind: str) -> str:
    if kind not in _VALID_KINDS:
        raise ProximoError(f"unsupported guest kind: {kind!r} (expected lxc|qemu)")
    return kind


def _check_node(node: str | None) -> None:
    if node is not None and not _NODE_RE.match(node):
        raise ProximoError(f"invalid node name: {node!r}")


def _check_snapname(snapname: str) -> str:
    s = str(snapname)
    if s == "current":
        raise ProximoError("'current' is reserved by Proxmox (the live state); choose another name")
    if not _SNAPNAME_RE.match(s):
        raise ProximoError(
            f"invalid snapshot name: {snapname!r} (start with a letter, then letters/digits/_/-, <=40)"
        )
    return s


def _check_upid(upid: str) -> str:
    if not _UPID_RE.match(str(upid)):
        raise ProximoError(f"invalid task upid: {upid!r}")
    return str(upid)


@dataclass
class ExecResult:
    ctid: str
    command: str
    returncode: int
    stdout: str
    stderr: str


class ExecBackend:
    """Runs commands inside an LXC via `ssh <target> pct exec <ctid> -- ...` (or local `pct`).

    This path is irreducible: Proxmox has no REST endpoint for container exec
    (it uses lxc-attach / kernel namespaces). Verified 2026-06-07.
    """

    def __init__(self, config: ProximoConfig):
        self.config = config

    def run(self, ctid: str, command: list[str], *, timeout: int = 60) -> ExecResult:
        # Defense-in-depth: enforce the opt-in gate AT the backend, not only at the server
        # layer. A future caller reaching ExecBackend.run() directly must not bypass the
        # PROXIMO_ENABLE_EXEC opt-in and ride on the allowlist alone.
        if not self.config.enable_exec:
            raise ProximoError("in-container exec is disabled (set PROXIMO_ENABLE_EXEC=1 to enable)")
        _check_vmid(ctid)  # defense-in-depth: validate before allowlist/quoting, like ApiBackend
        if not self.config.ct_permitted(ctid):
            raise ProximoError(f"CTID {ctid} not permitted by allowlist (fail-closed)")
        if self.config.is_local:
            # On the PVE host: call pct directly — no ssh, no quote layer.
            argv = ["pct", "exec", str(ctid), "--", *command]
        else:
            remote = "pct exec " + shlex.quote(str(ctid)) + " -- " + shlex.join(command)
            argv = ["ssh", self.config.ssh_target, remote]
        # S603/S607: we intentionally invoke PATH-resolved `ssh`/`pct` with non-shell argv.
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)  # noqa: S603, S607
        return ExecResult(str(ctid), shlex.join(command), proc.returncode, proc.stdout, proc.stderr)

    def psql(self, ctid: str, sql: str, *, db: str = "postgres", user: str = "postgres",
             timeout: int = 60) -> ExecResult:
        """psql convenience: runs as the db OS user, no shell-quote gymnastics for the caller."""
        inner = f"psql -d {shlex.quote(db)} -v ON_ERROR_STOP=1 -c {shlex.quote(sql)}"
        return self.run(ctid, ["su", user, "-c", inner], timeout=timeout)

    def logs(self, ctid: str, unit: str, *, lines: int = 50) -> ExecResult:
        return self.run(ctid, ["journalctl", "-u", unit, "-n", str(lines), "--no-pager"])


class ApiBackend:
    """Management via the Proxmox REST API using a scoped API token."""

    def __init__(self, config: ProximoConfig):
        self.config = config
        verify: bool | str = config.ca_bundle if config.ca_bundle else config.verify_tls
        # FAIL-CLOSED: every request carries the PVE API-token secret. Refuse to construct
        # this client over a completely unverified channel (verify_tls=false AND no
        # ca_bundle) — same rule PbsBackend already enforces for the PBS token, for the
        # same reason: the token could be intercepted in transit.
        if verify is False:
            raise ProximoError(
                "refusing to send the PVE token over unverified TLS: set PROXIMO_CA_BUNDLE "
                "to the PVE CA cert (preferred) or PROXIMO_VERIFY_TLS=true. A read-only token "
                "is still a credential — it must not cross an unverified channel."
            )
        self._client = httpx.Client(base_url=config.api_base_url, verify=httpx_verify(verify), timeout=30)

    def _auth_header(self) -> dict[str, str]:
        # Token file holds: USER@REALM!TOKENID=SECRET  (e.g. root@pam!proximo=<uuid>).
        # Header format verified vs PVE docs 2026-06-07: PVEAPIToken=..., no Bearer, no CSRF.
        # Read at call time; never logged.
        with open(self.config.token_path, encoding="utf-8") as f:
            token = f.read().strip()
        return {"Authorization": f"PVEAPIToken={token}"}

    def _get(self, path: str):
        r = self._client.get(path, headers=self._auth_header())
        r.raise_for_status()
        return r.json().get("data")

    def _post(self, path: str, data: dict | None = None):
        r = self._client.post(path, headers=self._auth_header(), data=data or {})
        r.raise_for_status()
        return r.json().get("data")

    def _delete(self, path: str, params: dict | None = None):
        r = self._client.request("DELETE", path, headers=self._auth_header(), params=params or {})
        r.raise_for_status()
        return r.json().get("data")

    def _put(self, path: str, data: dict | None = None):
        r = self._client.request("PUT", path, headers=self._auth_header(), data=data or {})
        r.raise_for_status()
        return r.json().get("data")

    def version(self) -> dict:
        """GET /version — Proxmox version/release. A successful call also proves the token can
        reach + authenticate to the API (used by the DOCTOR preflight)."""
        return self._get("/version") or {}

    def access_permissions(self, path: str | None = None) -> dict:
        """GET /access/permissions — the CALLING token's effective privileges, as {path: {priv: 1}}.
        No `path` => the full map across every path, so scoped (e.g. pool-only) grants stay visible."""
        q = f"?path={path}" if path else ""
        return self._get(f"/access/permissions{q}") or {}

    def node_status(self, node: str | None = None) -> dict:
        _check_node(node)
        return self._get(f"/nodes/{node or self.config.node}/status")

    def list_guests(self, node: str | None = None) -> list[dict]:
        _check_node(node)
        n = node or self.config.node
        lxc = self._get(f"/nodes/{n}/lxc") or []
        qemu = self._get(f"/nodes/{n}/qemu") or []
        return [{**g, "type": "lxc"} for g in lxc] + [{**g, "type": "qemu"} for g in qemu]

    def guest_status(self, vmid: str, kind: str = "lxc", node: str | None = None) -> dict:
        vmid, kind = _check_vmid(vmid), _check_kind(kind)
        _check_node(node)
        return self._get(f"/nodes/{node or self.config.node}/{kind}/{vmid}/status/current")

    def guest_power(self, vmid: str, action: str, kind: str = "lxc", node: str | None = None) -> dict:
        vmid, kind = _check_vmid(vmid), _check_kind(kind)
        _check_node(node)
        if action not in {"start", "stop", "reboot", "shutdown"}:
            raise ProximoError(f"unsupported power action: {action}")
        # MUTATION — the server layer must confirm-gate + audit before calling this.
        return self._post(f"/nodes/{node or self.config.node}/{kind}/{vmid}/status/{action}")

    # --- snapshots (UNDO pillar). Create/rollback/delete are ASYNC — they return a task UPID. ---

    def _snap_base(self, vmid: str, kind: str, node: str | None) -> str:
        vmid, kind = _check_vmid(vmid), _check_kind(kind)
        _check_node(node)
        return f"/nodes/{node or self.config.node}/{kind}/{vmid}/snapshot"

    def snapshot_list(self, vmid: str, kind: str = "lxc", node: str | None = None) -> list[dict]:
        return self._get(self._snap_base(vmid, kind, node)) or []

    def snapshot_create(self, vmid: str, snapname: str, kind: str = "lxc", node: str | None = None,
                        description: str | None = None) -> str:
        snapname = _check_snapname(snapname)
        data = {"snapname": snapname}
        if description:
            data["description"] = description
        # MUTATION — confirm-gated + audited at the server layer.
        return self._post(self._snap_base(vmid, kind, node), data)

    def snapshot_rollback(self, vmid: str, snapname: str, kind: str = "lxc",
                          node: str | None = None) -> str:
        snapname = _check_snapname(snapname)
        # DESTRUCTIVE — discards changes since the snapshot. Confirm-gated + audited at the server layer.
        return self._post(f"{self._snap_base(vmid, kind, node)}/{snapname}/rollback")

    def snapshot_delete(self, vmid: str, snapname: str, kind: str = "lxc", node: str | None = None,
                        force: bool = False) -> str:
        snapname = _check_snapname(snapname)
        params = {"force": 1} if force else None
        return self._delete(f"{self._snap_base(vmid, kind, node)}/{snapname}", params)

    def task_status(self, upid: str, node: str | None = None) -> dict:
        _check_node(node)
        upid = _check_upid(upid)
        return self._get(f"/nodes/{node or self.config.node}/tasks/{upid}/status")

    # --- node reads (DIAGNOSE pillar) ---

    def node_storage(self, node: str | None = None) -> list[dict]:
        _check_node(node)
        return self._get(f"/nodes/{node or self.config.node}/storage") or []

    def node_tasks(self, node: str | None = None, limit: int = 50) -> list[dict]:
        _check_node(node)
        limit = int(limit)  # int-cast: never let an arbitrary string into the query string
        if limit <= 0:
            limit = 50
        return self._get(f"/nodes/{node or self.config.node}/tasks?limit={limit}") or []
