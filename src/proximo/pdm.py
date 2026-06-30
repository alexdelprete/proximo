"""Proximo PDM (Proxmox Datacenter Manager) lane — read-only backend.

PDM is a fleet-management appliance that aggregates PVE and PBS remotes.
This module is a **read-only** v1: all 22 tools are DIAGNOSE (no mutations,
no PLAN/UNDO stubs).

API topology:
  - PDM base:  https://<host>:8443/api2/json  (not :8006)
  - Auth:      Authorization: PDMAPIToken <tokenid>:<secret>
               (SPACE separator — NOT '=' like PVE/PBS)
  - PDM is single-node; node defaults to "localhost"
  - PDM proxies remotes through a FLAT surface:
      PVE: /pve/remotes/<remote>/<subpath>   (no /api2/json)
      PBS: /pbs/remotes/<remote>/<subpath>   (no /api2/json)

Anti-boxing seam:
  _pve_remote_get(remote, subpath, params) and
  _pbs_remote_get(remote, subpath, params) are loop-ready primitives that
  make per-remote fan-out straightforward without implementing it here.

VERIFIED live shapes (PDM 1.1, 2026-06-27):
  GET /ping              → {"data":"pong"}
  GET /version           → {"data":{"release":"4","repoid":"...","version":"1.1"}}
  GET /remotes/remote    → {"data":[{"id":"...","type":"pbs"|"pve",...}],"digest":"..."}
  GET /remotes/remote/{id}/version → proxies to the remote's /version
  GET /remotes/remote/{id}/config  → remote config (no secrets)
  GET /resources/list    → {"data":[{"remote":"...","resources":[...]}]}
  GET /resources/status  → {"data":{"failed_remotes":N,"lxc":{...},"remotes":N,...}}
  GET /remotes/tasks/list → {"data":[]}
  GET /access/acl        → {"data":[{"path":"/","propagate":true,"roleid":"Auditor",...}],"digest":"..."}
  GET /access/roles      → {"data":[{"comment":"...","privs":[...],"roleid":"Auditor"},...]}
  GET /access/users      → {"data":[{"enable":true,"userid":"proximo@pdm"},...],"digest":"..."}
  GET /nodes/localhost/status  (live-prove-pending: probe hit empty node; shape equals PVE node status)
  D-group (PBS per-remote) — LIVE-VERIFIED (PDM 1.1 → PBS 4.2, 2026-06-27):
    GET /pbs/remotes/{remote}/status                          → PBS node status dict
    GET /pbs/remotes/{remote}/datastore                       → [{"name","path"}, ...]
    GET /pbs/remotes/{remote}/datastore/{store}/snapshots     → [...]
  C-group (PVE per-remote) — apidoc-derived; live-prove-pending (no PVE remote registered yet):
    GET /pve/remotes/{remote}/resources | cluster-status | nodes | qemu | lxc | {kind}/{vmid}/config
  GET /remotes/metric-collection/status → 403 for Auditor token — EXCLUDED from surface

Security posture mirrors pbs.py (and is stricter on TLS):
- Token read at call time from the token-path file; NEVER logged.
- TLS verification prefers ca_bundle over disabling. FAIL-CLOSED: constructing a
  PdmBackend with verify_tls=false AND no ca_bundle raises.
- Input validators use \\Z (not $) to block trailing-newline bypass.

env vars:
    PROXIMO_PDM_BASE_URL     required  https://<host>:8443
                                       (/api2/json appended automatically if absent)
    PROXIMO_PDM_TOKEN_PATH   required  file containing TOKENID:SECRET  (e.g. proximo@pdm!token:secret)
    PROXIMO_PDM_VERIFY_TLS   optional  default "true"; set "false" to skip (warn + fail-closed)
    PROXIMO_PDM_CA_BUNDLE    optional  path to CA cert bundle (preferred over disabling TLS)
"""

from __future__ import annotations

import os
import re
import warnings
from dataclasses import dataclass

import httpx

from ._tls import httpx_verify, parse_verify_tls
from .backends import ProximoError
from .pbs import _check_namespace

# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

# Remote name: path segment in /pve/remotes/<remote>/... — reject traversal.
# PDM remote names are alphanumeric + hyphen/underscore (same charset as PBS store names).
# \Z (not $) — Python's $ matches before a trailing newline, so "remote\n" would slip through.
_REMOTE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")

# VMID: numeric 100–999999999
_VMID_RE = re.compile(r"^[1-9][0-9]{2,8}\Z")

# Datastore name (PBS): alphanumeric + hyphen/underscore; no slash or control chars.
_DATASTORE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")

# Node name: hostname characters; no slash.
_NODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


def _check_remote(remote: str) -> str:
    """Validate a PDM remote name (path segment for /pve/remotes or /pbs/remotes/<remote>/...)."""
    s = str(remote)
    if not _REMOTE_RE.match(s):
        raise ProximoError(
            f"invalid PDM remote name: {remote!r} "
            "(must start with alnum, then alnum/_/-, <=64 chars, no slash or control chars)"
        )
    return s


def _check_vmid(vmid: int | str) -> str:
    """Validate a VMID (100–999999999); returns as string for URL use."""
    s = str(vmid)
    if not _VMID_RE.match(s):
        raise ProximoError(
            f"invalid VMID: {vmid!r} (must be 100–999999999)"
        )
    return s


def _check_datastore(datastore: str) -> str:
    """Validate a PBS datastore name (path segment for remote PBS proxy calls)."""
    s = str(datastore)
    if not _DATASTORE_RE.match(s):
        raise ProximoError(
            f"invalid datastore name: {datastore!r} "
            "(must start with alnum, then alnum/_/-, <=64 chars, no slash or control chars)"
        )
    return s


def _check_node(node: str) -> str:
    """Validate a PDM node name (hostname characters)."""
    s = str(node)
    if not _NODE_RE.match(s):
        raise ProximoError(
            f"invalid PDM node name: {node!r} "
            "(must start with alnum, then alnum/._/-, <=64 chars)"
        )
    return s


def _check_opt(val: str, name: str) -> str:
    """Reject control chars and over-long values in optional query params (defence-in-depth).

    Free-form query values (kind/snapshot/state/path) don't get a tight charset like the
    path-segment validators, but they must never carry control chars (header/log injection,
    newline bypass) or unbounded length. \\x00-\\x1f covers NUL + newline + the C0 set.
    """
    s = str(val)
    if len(s) > 256 or re.search(r"[\x00-\x1f]", s):
        raise ProximoError(f"invalid {name}: control chars or >256 chars")
    return s


# Credential-shaped keys stripped from any config/user/remote dict before it leaves the backend.
# Defence-in-depth: the PDM Auditor token should never see a secret, but a future PDM regression
# must not be able to hand one to the caller through this read surface.
# frozenset + lowercase for O(1) case-insensitive look-ups.
_SECRET_KEYS_LOWER = frozenset(("token", "password", "secret", "key", "tokensecret"))


def _strip_secret_value(v: object) -> object:
    """Recursively sanitise a value — descends into nested dicts and lists."""
    if isinstance(v, dict):
        return _strip_secrets(v)
    if isinstance(v, list):
        return [_strip_secret_value(i) for i in v]
    return v


def _strip_secrets(d: dict) -> dict:
    """Return a COPY of d with credential-shaped keys removed (case-insensitive, recursive).

    Handles nested dicts and lists so a credential-shaped key cannot survive
    in any casing (Token, PASSWORD, TokenSecret, ...) or nesting depth.
    Returns a new dict — the caller's dict is never mutated.
    Defence-in-depth: the PDM Auditor token should never see a secret, but a
    future PDM regression must not be able to hand one to the caller through
    this read surface.
    """
    return {
        k: _strip_secret_value(v)
        for k, v in d.items()
        if k.lower() not in _SECRET_KEYS_LOWER
    }


# ---------------------------------------------------------------------------
# PdmConfig
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PdmConfig:
    """Configuration for the PDM API backend.

    All credentials are referenced by PATH — values are read at call time
    and never logged, so the secrets vault is never echoed.

    env vars:
        PROXIMO_PDM_BASE_URL     required  https://<host>:8443
                                           (/api2/json appended automatically if absent)
        PROXIMO_PDM_TOKEN_PATH   required  file containing TOKENID:SECRET
        PROXIMO_PDM_VERIFY_TLS   optional  default "true"; set "false" to skip (warn + fail-closed)
        PROXIMO_PDM_CA_BUNDLE    optional  path to CA cert bundle (preferred over disabling TLS)
    """

    base_url: str          # e.g. "https://pdm.example.com:8443/api2/json"
    token_path: str        # file containing: TOKENID:SECRET  (run-but-not-read)
    verify_tls: bool = True
    ca_bundle: str | None = None

    @classmethod
    def from_env(cls) -> PdmConfig:
        try:
            base_url = os.environ["PROXIMO_PDM_BASE_URL"]
            token_path = os.environ["PROXIMO_PDM_TOKEN_PATH"]
        except KeyError as e:
            raise RuntimeError(
                f"Missing required PDM env var: {e.args[0]}. "
                "Set PROXIMO_PDM_BASE_URL and PROXIMO_PDM_TOKEN_PATH to use pdm_* tools."
            ) from e

        # Normalise: append /api2/json if the URL has no path (common PDM usage is just the host:port)
        url = base_url.rstrip("/")
        if not url.endswith("/api2/json"):
            url = url + "/api2/json"

        verify_tls = parse_verify_tls(os.environ.get("PROXIMO_PDM_VERIFY_TLS", "true"))
        ca_bundle = os.environ.get("PROXIMO_PDM_CA_BUNDLE") or None

        if not verify_tls and not ca_bundle:
            warnings.warn(
                "PROXIMO_PDM_VERIFY_TLS=false with no CA bundle — "
                "talking to the PDM API without cert validation.",
                stacklevel=2,
            )

        return cls(
            base_url=url,
            token_path=token_path,
            verify_tls=verify_tls,
            ca_bundle=ca_bundle,
        )



    @classmethod
    def from_target(cls, fields: dict) -> PdmConfig:
        """Build a PDM config from a named registry remote (see proximo.targets)."""
        try:
            base_url = fields["base_url"]
            token_path = fields["token_path"]
        except KeyError as e:
            raise RuntimeError(f"target missing required field: {e.args[0]}") from e
        url = base_url.rstrip("/")
        if not url.endswith("/api2/json"):
            url = url + "/api2/json"
        verify_tls = parse_verify_tls(fields.get("verify_tls", "true"))
        ca_bundle = fields.get("ca_bundle") or None
        if not verify_tls and not ca_bundle:
            warnings.warn(
                "PDM target verify_tls=false with no CA bundle — "
                "talking to the PDM API without cert validation.",
                stacklevel=2,
            )
        return cls(
            base_url=url,
            token_path=token_path,
            verify_tls=verify_tls,
            ca_bundle=ca_bundle,
        )


# ---------------------------------------------------------------------------
# PdmBackend
# ---------------------------------------------------------------------------

class PdmBackend:
    """Management via the Proxmox Datacenter Manager REST API using a PDM API token.

    Self-contained: does NOT depend on ProximoConfig.  Use PdmConfig.from_env()
    or construct PdmConfig directly for tests.

    PDM auth header: Authorization: PDMAPIToken TOKENID:SECRET
    (SPACE separator — NOT '=' like PVE/PBS)
    """

    def __init__(self, config: PdmConfig):
        self.config = config
        verify: bool | str = config.ca_bundle if config.ca_bundle else config.verify_tls
        # FAIL-CLOSED: this backend sends a real API-token secret on every request. Refuse
        # to construct it over a completely unverified channel (verify_tls=false AND no
        # ca_bundle).
        if verify is False:
            raise ProximoError(
                "refusing to send the PDM token over unverified TLS: set PROXIMO_PDM_CA_BUNDLE "
                "to the PDM CA cert (preferred) or PROXIMO_PDM_VERIFY_TLS=true."
            )
        self._client = httpx.Client(base_url=config.base_url, verify=httpx_verify(verify), timeout=60)

    def _auth_header(self) -> dict[str, str]:
        # Token file holds: TOKENID:SECRET  (e.g. proximo@pdm!token:secret)
        # Header: Authorization: PDMAPIToken TOKENID:SECRET
        # NOTE: SPACE separator (not '=' like PBSAPIToken= / PVEAPIToken=)
        # Read at call time; NEVER logged.
        with open(self.config.token_path, encoding="utf-8") as f:
            token = f.read().strip()
        return {"Authorization": f"PDMAPIToken {token}"}

    def _get(self, path: str, params: dict | None = None):
        r = self._client.get(path, headers=self._auth_header(), params=params or {})
        r.raise_for_status()
        return r.json().get("data")

    # --- Anti-boxing seam: remote-proxy primitives ---

    def _pve_remote_get(self, remote: str, subpath: str, params: dict | None = None):
        """Proxy a read to a PVE remote registered in PDM.

        PDM exposes a FLAT proxy surface under /pve/remotes/<remote>/<subpath>
        (no /api2/json — PDM re-shapes the PVE API into its own endpoints).
        This primitive is the loop-ready hook for future per-remote fan-out.
        """
        r = _check_remote(remote)
        path = f"/pve/remotes/{r}/{subpath.lstrip('/')}"
        return self._get(path, params)

    def _pbs_remote_get(self, remote: str, subpath: str, params: dict | None = None):
        """Proxy a read to a PBS remote registered in PDM.

        PDM exposes a FLAT proxy surface under /pbs/remotes/<remote>/<subpath>
        (no /api2/json — PDM re-shapes the PBS API into its own endpoints).
        This primitive is the loop-ready hook for future per-remote fan-out.
        """
        r = _check_remote(remote)
        path = f"/pbs/remotes/{r}/{subpath.lstrip('/')}"
        return self._get(path, params)

    # ---------------------------------------------------------------------------
    # A: PDM self + topology
    # ---------------------------------------------------------------------------

    def ping(self) -> str:
        """GET /ping → "pong" (health check)."""
        return self._get("/ping") or ""

    def version(self) -> dict:
        """GET /version → {release, repoid, version}."""
        return self._get("/version") or {}

    def node_status(self, node: str = "localhost") -> dict:
        """GET /nodes/{node}/status → node resource stats.

        PDM is a single-node appliance; node defaults to "localhost".
        Shape equals PVE node status; live-prove-pending (probe hit empty-node path).
        """
        n = _check_node(node)
        return self._get(f"/nodes/{n}/status") or {}

    def remotes_list(self) -> list[dict]:
        """GET /remotes/remote → list of registered PVE/PBS remotes.

        Each entry carries a (normally empty) 'token' field; credential-shaped keys are
        stripped before returning (defence-in-depth — the read surface never emits a secret).
        """
        result = self._get("/remotes/remote") or []
        return [_strip_secrets(r) for r in result if isinstance(r, dict)]

    def remote_version(self, remote_id: str) -> dict:
        """GET /remotes/remote/{id}/version → remote version info.

        Smoke-confirm: exact response shape (PDM proxies to the remote's /version).
        """
        rid = _check_remote(remote_id)
        return self._get(f"/remotes/remote/{rid}/version") or {}

    def remote_config_get(self, remote_id: str) -> dict:
        """GET /remotes/remote/{id}/config → remote configuration.

        Credential-shaped keys are stripped before returning (defence-in-depth):
        a PDM regression must not be able to hand a secret to the caller.
        """
        rid = _check_remote(remote_id)
        return _strip_secrets(self._get(f"/remotes/remote/{rid}/config") or {})

    # ---------------------------------------------------------------------------
    # B: Fleet aggregate
    # ---------------------------------------------------------------------------

    def resources_list(self, params: dict | None = None) -> list[dict]:
        """GET /resources/list → flat list of all fleet resources (VMs, LXCs, etc.)."""
        return self._get("/resources/list", params) or []

    def resources_status(self, params: dict | None = None) -> dict:
        """GET /resources/status → aggregated fleet status counters."""
        return self._get("/resources/status", params) or {}

    # ---------------------------------------------------------------------------
    # C: PVE per-remote reads (proxied)
    # ---------------------------------------------------------------------------

    def pve_resources(self, remote: str, kind: str | None = None) -> list[dict]:
        """GET /pve/remotes/{remote}/resources → resource list.

        kind: optional filter (vm, storage, node, sdn, ...) — passed as query 'kind'.
        Shape equals PVE cluster/resources; live-proven 2026-06-27 against a registered PVE remote.
        """
        params = {}
        if kind is not None:
            params["kind"] = _check_opt(kind, "kind")
        return self._pve_remote_get(remote, "resources", params or None) or []

    def pve_cluster_status(self, remote: str) -> list[dict]:
        """GET /pve/remotes/{remote}/cluster-status → cluster nodes.

        Shape equals PVE cluster/status; live-proven 2026-06-27 against a registered PVE remote.
        """
        return self._pve_remote_get(remote, "cluster-status") or []

    def pve_node_list(self, remote: str) -> list[dict]:
        """GET /pve/remotes/{remote}/nodes → list of PVE nodes.

        Shape equals PVE /nodes; live-proven 2026-06-27 against a registered PVE remote.
        """
        return self._pve_remote_get(remote, "nodes") or []

    def pve_qemu_list(self, remote: str, node: str | None = None) -> list[dict]:
        """GET /pve/remotes/{remote}/qemu → VM list (cluster-wide).

        node: OPTIONAL filter, passed as query 'node' (PDM's qemu list is cluster-wide).
        Shape equals PVE qemu list; live-proven 2026-06-27 against a registered PVE remote.
        """
        params = {}
        if node is not None:
            params["node"] = _check_node(node)
        return self._pve_remote_get(remote, "qemu", params or None) or []

    def pve_qemu_config(self, remote: str, vmid: int | str, node: str | None = None,
                        snapshot: str | None = None, state: str = "active") -> dict:
        """GET /pve/remotes/{remote}/qemu/{vmid}/config → VM config.

        node, snapshot: OPTIONAL query params (node is NOT required).
        state: REQUIRED by PDM (enum; "active" = current config) — defaults to "active".
               PDM rejects the request with 400 if it is omitted.
        Live-proven 2026-06-27 against a registered PVE remote.
        """
        v = _check_vmid(vmid)
        params = {"state": _check_opt(state, "state")}
        if node is not None:
            params["node"] = _check_node(node)
        if snapshot is not None:
            params["snapshot"] = _check_opt(snapshot, "snapshot")
        return self._pve_remote_get(remote, f"qemu/{v}/config", params) or {}

    def pve_lxc_list(self, remote: str, node: str | None = None) -> list[dict]:
        """GET /pve/remotes/{remote}/lxc → LXC list (cluster-wide).

        node: OPTIONAL filter, passed as query 'node' (PDM's lxc list is cluster-wide).
        Shape equals PVE lxc list; live-proven 2026-06-27 against a registered PVE remote.
        """
        params = {}
        if node is not None:
            params["node"] = _check_node(node)
        return self._pve_remote_get(remote, "lxc", params or None) or []

    def pve_lxc_config(self, remote: str, vmid: int | str, node: str | None = None,
                       snapshot: str | None = None, state: str = "active") -> dict:
        """GET /pve/remotes/{remote}/lxc/{vmid}/config → LXC config.

        node, snapshot: OPTIONAL query params (node is NOT required).
        state: REQUIRED by PDM (enum; "active" = current config) — defaults to "active".
               PDM rejects the request with 400 if it is omitted.
        Live-proven 2026-06-27 against a registered PVE remote.
        """
        v = _check_vmid(vmid)
        params = {"state": _check_opt(state, "state")}
        if node is not None:
            params["node"] = _check_node(node)
        if snapshot is not None:
            params["snapshot"] = _check_opt(snapshot, "snapshot")
        return self._pve_remote_get(remote, f"lxc/{v}/config", params) or {}

    # ---------------------------------------------------------------------------
    # D: PBS per-remote reads (proxied)
    # ---------------------------------------------------------------------------

    def pbs_remote_status(self, remote: str) -> dict:
        """GET /pbs/remotes/{remote}/status → PBS node status (cpu/memory/uptime/etc.).

        Live-verified (PDM 1.1 → PBS 4.2, 2026-06-27).
        """
        return self._pbs_remote_get(remote, "status") or {}

    def pbs_datastores_list(self, remote: str) -> list[dict]:
        """GET /pbs/remotes/{remote}/datastore → datastore list.

        Live-verified shape: [{"name": <store>, "path": <fs-path>}, ...]
        (PDM 1.1 → PBS 4.2, 2026-06-27).
        """
        return self._pbs_remote_get(remote, "datastore") or []

    def pbs_snapshots_list(self, remote: str, datastore: str,
                           ns: str | None = None) -> list[dict]:
        """GET /pbs/remotes/{remote}/datastore/{datastore}/snapshots → snapshot list.

        ns: optional namespace filter (query 'ns').
        Live-verified path (PDM 1.1 → PBS 4.2, 2026-06-27; empty datastore returned []).
        """
        ds = _check_datastore(datastore)
        params = {}
        if ns is not None:
            ns = _check_namespace(ns)
            params["ns"] = ns
        return self._pbs_remote_get(remote, f"datastore/{ds}/snapshots",
                                    params or None) or []

    # ---------------------------------------------------------------------------
    # E: Tasks + access
    # ---------------------------------------------------------------------------

    def tasks_list(self, params: dict | None = None) -> list[dict]:
        """GET /remotes/tasks/list → recent PDM tasks across all remotes."""
        return self._get("/remotes/tasks/list", params) or []

    def acl_list(self, path: str | None = None, exact: bool | None = None) -> list[dict]:
        """GET /access/acl → access control entries.

        path: optional ACL path filter (e.g. "/").
        exact: if True, return only the exact path, not inherited entries.
        """
        params: dict = {}
        if path is not None:
            params["path"] = _check_opt(path, "path")
        if exact is not None:
            params["exact"] = 1 if exact else 0
        return self._get("/access/acl", params or None) or []

    def roles_list(self) -> list[dict]:
        """GET /access/roles → all defined roles and their privileges."""
        return self._get("/access/roles") or []

    def users_list(self, include_tokens: bool | None = None) -> list[dict]:
        """GET /access/users → all PDM users.

        include_tokens: if True, include API token entries.
        Credential-shaped keys are stripped from each entry before returning
        (defence-in-depth — the read surface never emits a secret).
        """
        params: dict = {}
        if include_tokens is not None:
            params["include_tokens"] = 1 if include_tokens else 0
        result = self._get("/access/users", params or None) or []
        return [_strip_secrets(u) for u in result if isinstance(u, dict)]
