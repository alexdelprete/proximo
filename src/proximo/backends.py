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
from urllib.parse import quote

import httpx

from ._tls import httpx_verify
from .config import ProximoConfig

# NB: \Z (not $) — Python's $ matches before a trailing newline, so "valid\n" would slip through.
_VALID_KINDS = frozenset({"lxc", "qemu"})

# QEMU agent command allow-lists: CLOSED sets — no arbitrary string goes into the URL path.
# These are the canonical sets; qemu_agent.py imports them so validators stay in sync.
# Smoke-confirm: command names match PVE docs but endpoint shapes are NOT live-verified.
_VALID_AGENT_INFO_CMDS = frozenset({
    "ping", "info", "get-fsinfo", "get-host-name", "get-osinfo", "get-time",
    "get-timezone", "get-users", "get-vcpus", "network-get-interfaces",
    "get-memory-blocks", "fsfreeze-status",
    # exec-status is dispatched separately (requires pid); kept here for allowlist completeness
    # but agent_simple() does NOT accept it — route through agent_exec_status() instead.
})
_VALID_AGENT_FS_CMDS = frozenset({"fsfreeze-freeze", "fsfreeze-thaw", "fstrim"})
# Union used by agent_simple(); intentionally excludes exec-status (needs separate pid param).
_VALID_AGENT_SIMPLE_CMDS = _VALID_AGENT_INFO_CMDS | _VALID_AGENT_FS_CMDS
# PVE serves agent READ commands as GET; ACTION commands (ping + fsfreeze-* + fstrim, and counter-
# intuitively fsfreeze-status) as POST. VERIFIED live against PVE 9.2 (a POST to a get-* path 501s).
_AGENT_GET_CMDS = frozenset({
    "info", "get-host-name", "get-osinfo", "get-time", "get-timezone", "get-users",
    "get-vcpus", "network-get-interfaces", "get-memory-blocks", "get-fsinfo",
})
_NODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\Z")
# Snapshot name: PVE requires a leading letter, then letters/digits/_/- (hyphen on newer PVE).
# Also the gate against path traversal in the {snapname} URL segment (no '/', '..', spaces, newline).
_SNAPNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}\Z")
# Task UPID: "UPID:node:pid:pstart:starttime:type:id:user:" — colon-delimited, no '/'. Length-capped.
_UPID_RE = re.compile(r"^UPID:[A-Za-z0-9._:@!-]{1,256}\Z")

# --- Wave 4: node-lifecycle validators ---
# Disk device path: must start with /dev/; allow letters, digits, slash, underscore, hyphen.
# \Z anchor prevents trailing-newline bypass. Component check (split on '/') rejects '..'.
# Smoke-confirm: PVE accepts any /dev/... path; closed-ish rather than an exact allowlist.
_DISK_RE = re.compile(r"^/dev/[a-zA-Z0-9/_-]+\Z")

# Storage backend: closed set — no arbitrary string goes into the URL path.
_VALID_BACKENDS = frozenset({"lvm", "lvmthin", "zfs", "directory"})

# Storage name: alnum + underscore + hyphen; must start with alnum; max 64 chars.
_STORAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")

# Timezone: IANA tz format (Region/City, UTC, etc.). Letters, digits, underscore, plus, hyphen,
# slash allowed. \Z anchor prevents trailing-newline bypass.
# Smoke-confirm: PVE accepts any valid IANA timezone string; this is a safe superset.
_TIMEZONE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+/-]{0,63}\Z")


class ProximoError(RuntimeError):
    """Operational error surfaced to the caller (never carries secrets)."""


def _check_vmid(vmid: str) -> str:
    if not re.fullmatch(r"[0-9]+", str(vmid)):  # ASCII 0-9 only; str.isdigit() also accepts Unicode digits
        raise ProximoError(f"invalid vmid: {vmid!r} (must be numeric)")
    return str(vmid)


# Guest OS username (qemu-agent set-user-password): non-empty, no C0 control chars / DEL, <=256.
# \Z anchor rejects trailing-newline slip-through.
_USERNAME_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,256}\Z")


def _check_username(username: str) -> str:
    if not _USERNAME_RE.match(str(username)):
        raise ProximoError(f"invalid username: {username!r} (1-256 chars, no control characters)")
    return str(username)


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


def _check_disk(disk: str) -> str:
    """Validate a block device path (e.g. /dev/sdb). Rejects traversal and non-/dev/ paths."""
    s = str(disk)
    if not _DISK_RE.match(s):
        raise ProximoError(
            f"invalid disk device path: {disk!r} "
            "(must start with /dev/ then letters/digits/underscore/hyphen/slash)"
        )
    # Component-level traversal check: no '..' segment after splitting on '/'.
    if ".." in s.split("/"):
        raise ProximoError(f"path traversal not allowed in disk path: {disk!r}")
    return s


def _check_backend(backend: str) -> str:
    """Validate a storage backend type against the closed set {lvm, lvmthin, zfs, directory}."""
    if backend not in _VALID_BACKENDS:
        raise ProximoError(
            f"unsupported storage backend: {backend!r} "
            f"(valid: {sorted(_VALID_BACKENDS)!r})"
        )
    return backend


def _check_storage_name(name: str) -> str:
    """Validate a storage backend name (alnum + underscore/hyphen; starts with alnum)."""
    s = str(name)
    if not _STORAGE_NAME_RE.match(s):
        raise ProximoError(
            f"invalid storage name: {name!r} "
            "(must start with alnum, then alnum/underscore/hyphen, max 64 chars)"
        )
    return s


def _check_timezone(tz: str) -> str:
    """Validate a timezone string (IANA format, e.g. America/Chicago, UTC)."""
    s = str(tz)
    if not _TIMEZONE_RE.match(s):
        raise ProximoError(
            f"invalid timezone: {tz!r} "
            "(expected IANA format, e.g. 'America/Chicago', 'UTC', 'Europe/Berlin')"
        )
    return s


# Absolute-path file validator for qemu-agent file-read/file-write.
# Must start with '/'; reject ALL C0 control chars (incl. CR/LF/TAB) and DEL — these have no
# place in a path and are the header/URL-injection vectors. Printable chars (incl. space, which
# is legal in guest paths) are allowed and percent-encoded by the caller.
# \Z anchor prevents trailing-newline slip-through (same discipline as _NODE_RE).
#
# NOTE: qemu_agent.py imports backends (not the reverse), so _check_file_path is intentionally
# duplicated here. If you move it, update the import in qemu_agent.py to pull from backends
# instead of redefining it locally.
_FILE_PATH_RE = re.compile(r"^/[^\x00-\x1f\x7f]*\Z")


def _check_file_path(path: str) -> str:
    """Validate an absolute guest file path (defense-in-depth: called at the backend layer)."""
    if not _FILE_PATH_RE.match(path):
        raise ProximoError(
            f"invalid file path: {path!r} (must be an absolute path starting with '/')"
        )
    if ".." in path.split("/"):
        raise ProximoError(f"path traversal not allowed: {path!r}")
    return path


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

    @staticmethod
    def _form(d: dict | None) -> dict:
        # PVE's API type-checker wants booleans as 1/0 — Python's bool serializes to 'true'/'false',
        # which PVE rejects ("type check ('boolean') failed - got 'false'"). Coerce so any tool may
        # pass a native bool and get the wire form PVE accepts. Ints pass through (1 is True == False).
        # None is DROPPED, not sent: an unset optional must be omitted, never serialized as "None".
        return {k: (1 if v is True else 0 if v is False else v)
                for k, v in (d or {}).items() if v is not None}

    def _post(self, path: str, data: dict | None = None):
        r = self._client.post(path, headers=self._auth_header(), data=self._form(data))
        r.raise_for_status()
        return r.json().get("data")

    def _delete(self, path: str, params: dict | None = None):
        r = self._client.request("DELETE", path, headers=self._auth_header(), params=self._form(params))
        r.raise_for_status()
        return r.json().get("data")

    def _put(self, path: str, data: dict | None = None):
        r = self._client.request("PUT", path, headers=self._auth_header(), data=self._form(data))
        r.raise_for_status()
        return r.json().get("data")

    def version(self) -> dict:
        """GET /version — Proxmox version/release. A successful call also proves the token can
        reach + authenticate to the API (used by the DOCTOR preflight)."""
        return self._get("/version") or {}

    def access_permissions(self, path: str | None = None) -> dict:
        """GET /access/permissions — the CALLING token's effective privileges, as {path: {priv: 1}}.
        No `path` => the full map across every path, so scoped (e.g. pool-only) grants stay visible."""
        # url-encode the caller-supplied path so '&'/'#'/space cannot inject extra query params
        q = f"?path={quote(path, safe='/')}" if path else ""
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

    # --- qemu-agent plane (Wave 3) ---
    # Defense-in-depth: gate enforced HERE so a future caller reaching these methods directly
    # cannot bypass the PROXIMO_ENABLE_AGENT opt-in + VMID allowlist.
    # Gate order mirrors ExecBackend.run(): enable → vmid → permitted → node.

    def _agent_gate(self, vmid: str, node: str | None) -> tuple[str, str]:
        """Enforce the agent gate and return (checked_vmid, resolved_node)."""
        if not self.config.enable_agent:
            raise ProximoError(
                "qemu-agent ops are disabled (set PROXIMO_ENABLE_AGENT=1 to enable)"
            )
        vmid = _check_vmid(vmid)
        if not self.config.agent_permitted(vmid):
            raise ProximoError(
                f"VMID {vmid} not permitted by agent allowlist (fail-closed)"
            )
        _check_node(node)
        return vmid, (node or self.config.node)

    def agent_simple(self, vmid: str, node: str | None, command: str) -> dict:
        """Issue a no-parameter agent command (ping / info / get-* / fsfreeze-* / fstrim).

        VERIFIED live (PVE 9.2): read commands are GET, action commands are POST — routed by
        _AGENT_GET_CMDS. A POST to a get-* path returns 501 (method not implemented).
        """
        if command not in _VALID_AGENT_SIMPLE_CMDS:
            raise ProximoError(
                f"unsupported agent command: {command!r} "
                f"(valid: {sorted(_VALID_AGENT_SIMPLE_CMDS)!r})"
            )
        vmid, n = self._agent_gate(vmid, node)
        path = f"/nodes/{n}/qemu/{vmid}/agent/{command}"
        if command in _AGENT_GET_CMDS:
            return self._get(path) or {}
        return self._post(path) or {}

    def agent_exec(self, vmid: str, node: str | None, command: list[str]) -> dict:
        """POST an exec command to the guest agent and return the pid immediately.

        VERIFIED live (PVE 9.2): body={'command': [argv list]} is accepted; returns {"pid": <int>}.
        Poll agent_exec_status for completion.
        """
        vmid, n = self._agent_gate(vmid, node)
        return self._post(f"/nodes/{n}/qemu/{vmid}/agent/exec", {"command": command}) or {}

    def agent_exec_status(self, vmid: str, node: str | None, pid: int) -> dict:
        """GET the status of a running guest-agent exec by pid.

        VERIFIED live (PVE 9.2): GET .../agent/exec-status?pid=<n> returns
        {'exited': bool, 'exitcode': int, 'out-data': str, 'err-data': str} — out-data is plain
        text (NOT base64) for a normal exec.
        """
        vmid, n = self._agent_gate(vmid, node)
        return self._get(f"/nodes/{n}/qemu/{vmid}/agent/exec-status?pid={int(pid)}") or {}

    def agent_file_read(self, vmid: str, node: str | None, file: str) -> dict:
        """GET file content from the guest via the agent.

        VERIFIED live (PVE 9.2): GET .../agent/file-read?file=<path> returns
        {'bytes-read': int, 'content': str} (plain text round-trips exactly).
        """
        vmid, n = self._agent_gate(vmid, node)
        _check_file_path(file)  # defense-in-depth: validate even on a direct backend call
        # Percent-encode the validated path so '&'/'?'/'#'/space cannot inject query params or
        # break the request; _check_file_path already rejects control chars and traversal.
        return self._get(f"/nodes/{n}/qemu/{vmid}/agent/file-read?file={quote(file, safe='/')}") or {}

    def agent_file_write(self, vmid: str, node: str | None, file: str, content: str) -> None:
        """POST file content to the guest via the agent.

        VERIFIED live (PVE 9.2): POST .../agent/file-write with body {'file', 'content'} writes the
        file; text content round-trips byte-identical via file-read. Smoke-confirm: binary content
        (whether an 'encode'/base64 param is needed) is not yet exercised.
        """
        vmid, n = self._agent_gate(vmid, node)
        _check_file_path(file)  # defense-in-depth: validate even on a direct backend call
        self._post(f"/nodes/{n}/qemu/{vmid}/agent/file-write", {"file": file, "content": content})

    def agent_set_password(self, vmid: str, node: str | None, username: str, password: str) -> None:
        """POST to set a guest user's password via the agent.

        VERIFIED live (PVE 9.2): POST .../agent/set-user-password with body {'username', 'password'}
        succeeds. Password is NEVER logged; only a redaction marker reaches the ledger.
        """
        vmid, n = self._agent_gate(vmid, node)
        _check_username(username)  # defense-in-depth: validate even on a direct backend call
        self._post(
            f"/nodes/{n}/qemu/{vmid}/agent/set-user-password",
            {"username": username, "password": password},
        )

    # --- node-lifecycle plane (Wave 4) ---

    def node_disks_list(self, node: str | None = None) -> list:
        """GET /nodes/{node}/disks/list — physical disk inventory.

        VERIFIED live (PVE 9.2): GET; entries carry devpath/health/size/model/serial/used.
        """
        _check_node(node)
        n = node or self.config.node
        return self._get(f"/nodes/{n}/disks/list") or []

    def node_disk_smart(self, disk: str, node: str | None = None) -> dict:
        """GET /nodes/{node}/disks/smart?disk=… — SMART health data.

        VERIFIED live (PVE 9.2): GET is the READ form (returns {health, type, text/attributes}) —
        it does NOT trigger a self-test.
        """
        _check_disk(disk)
        _check_node(node)
        n = node or self.config.node
        return self._get(f"/nodes/{n}/disks/smart?disk={quote(disk, safe='/')}") or {}

    def node_disk_wipe(self, disk: str, node: str | None = None) -> str | None:
        """PUT /nodes/{node}/disks/wipedisk — wipe all data/partition table on a disk.

        Smoke-confirm: PUT /disks/wipedisk with body {disk: …} — shape not live-verified.
        Returns the worker UPID (async, like the sibling disk/storage ops). IRREVERSIBLE.
        """
        _check_disk(disk)
        _check_node(node)
        n = node or self.config.node
        return self._put(f"/nodes/{n}/disks/wipedisk", {"disk": disk})  # Smoke-confirm: PUT, async UPID

    def node_disk_initgpt(self, disk: str, node: str | None = None) -> str | None:
        """POST /nodes/{node}/disks/initgpt — write a new GPT partition table.

        Smoke-confirm: POST /disks/initgpt with body {disk: …} — shape not live-verified.
        IRREVERSIBLE — existing partition table is overwritten.
        """
        _check_disk(disk)
        _check_node(node)
        n = node or self.config.node
        return self._post(f"/nodes/{n}/disks/initgpt", {"disk": disk})  # Smoke-confirm: POST

    def node_storage_backend_list(self, backend: str, node: str | None = None) -> list | dict:
        """GET /nodes/{node}/disks/{backend} — list storage backends of a type.

        VERIFIED live (PVE 9.2): GET. Shape is heterogeneous — lvm returns a VG TREE (dict with
        nested children); lvmthin/zfs/directory return a list. Returned raw.
        """
        _check_backend(backend)
        _check_node(node)
        n = node or self.config.node
        return self._get(f"/nodes/{n}/disks/{backend}") or []

    def node_storage_backend_create(
        self, backend: str, name: str, node: str | None = None, **kw: object
    ) -> str | None:
        """POST /nodes/{node}/disks/{backend} — create a storage backend.

        Smoke-confirm: POST /disks/{backend} with body including name + backend-specific params
        — shape not live-verified. Returns a task UPID (async).
        """
        _check_backend(backend)
        _check_storage_name(name)
        _check_node(node)
        n = node or self.config.node
        body = {"name": name, **kw}
        return self._post(f"/nodes/{n}/disks/{backend}", body)  # Smoke-confirm: POST

    def node_storage_backend_delete(
        self, backend: str, name: str, node: str | None = None, cleanup: bool = False
    ) -> str | None:
        """DELETE /nodes/{node}/disks/{backend}/{name} — destroy a storage backend.

        Smoke-confirm: DELETE /disks/{backend}/{name} — shape not live-verified.
        IRREVERSIBLE for zfs/lvm/lvmthin backends.
        """
        _check_backend(backend)
        _check_storage_name(name)
        _check_node(node)
        n = node or self.config.node
        params = {"cleanup-disks": 1} if cleanup else None
        return self._delete(  # Smoke-confirm: DELETE
            f"/nodes/{n}/disks/{backend}/{name}", params=params
        )

    def node_time_get(self, node: str | None = None) -> dict:
        """GET /nodes/{node}/time — current time and timezone of the node.

        VERIFIED live (PVE 9.2): GET returns {localtime, time, timezone}. (CAPTURE source for time_set.)
        """
        _check_node(node)
        n = node or self.config.node
        return self._get(f"/nodes/{n}/time") or {}

    def node_time_set(self, timezone: str, node: str | None = None) -> None:
        """PUT /nodes/{node}/time — set the node timezone.

        Smoke-confirm: PUT /nodes/{node}/time with body {timezone: …} — shape not live-verified.
        """
        _check_timezone(timezone)
        _check_node(node)
        n = node or self.config.node
        self._put(f"/nodes/{n}/time", {"timezone": timezone})  # Smoke-confirm: PUT

    def node_hosts_get(self, node: str | None = None) -> dict:
        """GET /nodes/{node}/hosts — current /etc/hosts content.

        VERIFIED live (PVE 9.2): GET returns {data, digest}. (CAPTURE source for hosts_set.)
        """
        _check_node(node)
        n = node or self.config.node
        return self._get(f"/nodes/{n}/hosts") or {}

    def node_hosts_set(
        self, data: str, node: str | None = None, digest: str | None = None
    ) -> None:
        """POST /nodes/{node}/hosts — replace /etc/hosts.

        Smoke-confirm: POST /nodes/{node}/hosts with body {data, [digest]} — shape not live-verified.
        """
        _check_node(node)
        n = node or self.config.node
        body: dict = {"data": data}
        if digest is not None:
            body["digest"] = digest
        self._post(f"/nodes/{n}/hosts", body)  # Smoke-confirm: POST

    def node_dns_set(
        self,
        node: str | None = None,
        search: str | None = None,
        dns1: str | None = None,
        dns2: str | None = None,
        dns3: str | None = None,
    ) -> None:
        """PUT /nodes/{node}/dns — update DNS resolver config.

        Smoke-confirm: PUT /nodes/{node}/dns with body {search?, dns1?, dns2?, dns3?}
        — shape not live-verified.
        """
        _check_node(node)
        n = node or self.config.node
        body = {
            k: v for k, v in
            {"search": search, "dns1": dns1, "dns2": dns2, "dns3": dns3}.items()
            if v is not None
        }
        self._put(f"/nodes/{n}/dns", body)  # Smoke-confirm: PUT

    def node_cert_upload(
        self,
        certificates: str,
        node: str | None = None,
        key: str | None = None,
        force: bool = False,
        restart: bool = False,
    ) -> dict | None:
        """POST /nodes/{node}/certificates/custom — upload a custom TLS certificate.

        Smoke-confirm: POST /certificates/custom with body {certificates, [key], force, restart}
        — shape not live-verified.
        Private key (key) is NEVER logged by the caller — only {"key": "[redacted]"} reaches the ledger.
        """
        _check_node(node)
        n = node or self.config.node
        body: dict = {
            "certificates": certificates,
            "force": int(force),
            "restart": int(restart),
        }
        if key is not None:
            body["key"] = key
        return self._post(f"/nodes/{n}/certificates/custom", body)  # Smoke-confirm: POST

    def node_cert_delete(self, node: str | None = None, restart: bool = False) -> None:
        """DELETE /nodes/{node}/certificates/custom — remove the custom TLS cert.

        Smoke-confirm: DELETE /certificates/custom [?restart=1] — shape not live-verified.
        """
        _check_node(node)
        n = node or self.config.node
        params = {"restart": 1} if restart else None
        self._delete(f"/nodes/{n}/certificates/custom", params=params)  # Smoke-confirm: DELETE

    def node_startall(self, node: str | None = None, vms: str | None = None) -> str | None:
        """POST /nodes/{node}/startall — start all (or filtered) guests.

        Smoke-confirm: POST /startall [body {vms: CSV}] — shape not live-verified.
        Returns a task UPID or None.
        """
        _check_node(node)
        n = node or self.config.node
        body: dict | None = {"vms": vms} if vms is not None else None
        return self._post(f"/nodes/{n}/startall", body)  # Smoke-confirm: POST

    def node_stopall(self, node: str | None = None, vms: str | None = None) -> str | None:
        """POST /nodes/{node}/stopall — stop all (or filtered) guests.

        Smoke-confirm: POST /stopall [body {vms: CSV}] — shape not live-verified.
        Returns a task UPID or None.
        """
        _check_node(node)
        n = node or self.config.node
        body: dict | None = {"vms": vms} if vms is not None else None
        return self._post(f"/nodes/{n}/stopall", body)  # Smoke-confirm: POST

    def node_migrateall(
        self,
        target: str,
        node: str | None = None,
        vms: str | None = None,
        maxworkers: int | None = None,
    ) -> str | None:
        """POST /nodes/{node}/migrateall — migrate all (or filtered) guests to another node.

        Smoke-confirm: POST /migrateall with body {target, [vms], [maxworkers]}
        — shape not live-verified.
        Returns a task UPID or None.
        """
        _check_node(target)
        _check_node(node)
        n = node or self.config.node
        body: dict = {"target": target}
        if vms is not None:
            body["vms"] = vms
        if maxworkers is not None:
            body["maxworkers"] = int(maxworkers)
        return self._post(f"/nodes/{n}/migrateall", body)  # Smoke-confirm: POST
