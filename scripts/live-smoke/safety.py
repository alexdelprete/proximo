"""Prod-target guard for the mutate/destroy live-smoke tier — the code-level second layer.

The live-smoke mutate/destroy scripts operate on a real Proxmox cluster. Their *primary*
safety is a scoped CI token (granted only on the test pool/storage, so it cannot reach
production by construction). This module is the INDEPENDENT second layer: a default-deny
allowlist that refuses any VMID/storage that is not explicitly named as a test target —
so even if a smoke is ever run with a broad/wrong token, it still cannot point at prod.

Design: ALLOWLIST, not denylist. The allowlist names only the test surface (specific test
VMIDs, an optional throwaway VMID range, the test storage names). Production is refused by
*omission* and is never named here — which also keeps this public-shipping file leak-free.

Config (env, read by `load_allowlist`):
  PROXIMO_SMOKE_TEST_VMIDS     csv of explicit test VMIDs        e.g. "100,101,102"
  PROXIMO_SMOKE_VMID_RANGE     inclusive throwaway range "lo-hi" e.g. "90000-90099"
  PROXIMO_SMOKE_TEST_STORAGES  csv of test storage names         (default: "test")

Usage in a smoke (defense in depth — call before any mutation):
    from safety import assert_test_target, load_allowlist   # sibling import
    _AL = load_allowlist(os.environ)
    assert_test_target(_AL, vmid=VMID, storage=STORE)
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


class SmokeSafetyError(RuntimeError):
    """Raised when a smoke target is not an allowlisted test target (fail-closed)."""


def parse_vmid_range(spec: str) -> tuple[int, int] | None:
    """Parse an inclusive 'lo-hi' VMID range. Empty/whitespace -> None. Malformed -> raise."""
    spec = (spec or "").strip()
    if not spec:
        return None
    parts = spec.split("-")
    if len(parts) != 2:
        raise SmokeSafetyError(f"malformed VMID range {spec!r} — expected 'lo-hi'")
    try:
        lo, hi = int(parts[0]), int(parts[1])
    except ValueError as e:
        raise SmokeSafetyError(f"malformed VMID range {spec!r} — bounds must be integers") from e
    if lo > hi:
        raise SmokeSafetyError(f"inverted VMID range {spec!r} — lo ({lo}) > hi ({hi})")
    return (lo, hi)


def _coerce_vmid(vmid: object) -> int:
    try:
        return int(str(vmid).strip())
    except (ValueError, TypeError) as e:
        raise SmokeSafetyError(f"non-numeric VMID {vmid!r} — refusing (fail-closed)") from e


@dataclass(frozen=True)
class Allowlist:
    """The explicit test surface. Anything not covered here is refused."""

    vmids: frozenset[int]
    vmid_range: tuple[int, int] | None
    storages: frozenset[str]

    def permits_vmid(self, vmid: object) -> bool:
        v = _coerce_vmid(vmid)
        if v in self.vmids:
            return True
        if self.vmid_range is not None:
            lo, hi = self.vmid_range
            return lo <= v <= hi
        return False

    def permits_storage(self, storage: str) -> bool:
        return storage in self.storages


def assert_test_target(allowlist: Allowlist, *, vmid: object = None, storage: str | None = None) -> None:
    """Raise SmokeSafetyError unless every provided target is an allowlisted test target.

    Default-deny: with an empty allowlist, any concrete target is refused. The message names
    only the rejected target — never the rest of the (prod) inventory.
    """
    if vmid is not None and not allowlist.permits_vmid(vmid):
        raise SmokeSafetyError(
            f"refusing to operate on VMID {vmid!r}: not an allowlisted test target. "
            f"Set PROXIMO_SMOKE_TEST_VMIDS / PROXIMO_SMOKE_VMID_RANGE to the throwaway test surface."
        )
    if storage is not None and not allowlist.permits_storage(storage):
        raise SmokeSafetyError(
            f"refusing to operate on storage {storage!r}: not an allowlisted test storage. "
            f"Set PROXIMO_SMOKE_TEST_STORAGES to the isolated test storage."
        )


def _csv(value: str) -> list[str]:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


def load_allowlist(env) -> Allowlist:
    """Build an Allowlist from the PROXIMO_SMOKE_* env. Storage defaults to {'test'}."""
    vmids = frozenset(int(x) for x in _csv(env.get("PROXIMO_SMOKE_TEST_VMIDS", "")))
    vmid_range = parse_vmid_range(env.get("PROXIMO_SMOKE_VMID_RANGE", ""))
    storages = frozenset(_csv(env.get("PROXIMO_SMOKE_TEST_STORAGES", ""))) or frozenset({"test"})
    return Allowlist(vmids=vmids, vmid_range=vmid_range, storages=storages)


# --- PBS endpoint guard -------------------------------------------------------
# The PBS plane's catastrophe is a destructive op (prune/gc/snapshot-delete/verify) aimed at the
# PRODUCTION PBS instead of the throwaway test one. Same default-deny allowlist discipline as the
# VMID/storage guard above, applied to the PBS host in PROXIMO_PBS_BASE_URL.


def pbs_host(base_url: str) -> str:
    """Extract the hostname from a PBS base URL (https://host:port/...). Raise if unparseable."""
    host = urlparse(base_url).hostname
    if not host:
        raise SmokeSafetyError(f"cannot parse a host from PBS base_url {base_url!r}")
    return host


def assert_test_pbs(base_url: str, allowed_hosts) -> None:
    """Raise unless base_url points at an allowlisted test PBS host. Default-deny (empty = refuse all)."""
    host = pbs_host(base_url)
    if host not in allowed_hosts:
        raise SmokeSafetyError(
            f"refusing PBS operation against host {host!r}: not an allowlisted test PBS. "
            f"Set PROXIMO_SMOKE_PBS_HOSTS to the throwaway test instance's host."
        )


def load_pbs_allowlist(env) -> frozenset[str]:
    """Allowlisted test PBS hostnames from PROXIMO_SMOKE_PBS_HOSTS (csv). Empty => default-deny."""
    return frozenset(_csv(env.get("PROXIMO_SMOKE_PBS_HOSTS", "")))


# --- access-CRUD identity guard -----------------------------------------------
# Access-management privileges (create/delete users, roles, tokens) CANNOT be ACL-scoped to "test
# identities only" in PVE — a token that can delete a test user can delete ANY user. So for the
# access-CRUD smokes this code guard is the SOLE safety layer: only identities whose name starts with
# an allowlisted test prefix may be touched. Default-deny — every production identity is refused by
# omission, and the prefix must be specific enough not to be a prefix of a prod identity (use
# 'ProximoCISmoke', never 'Proximo' — the latter would match the prod role 'ProximoTest').


def assert_test_identity(name: str, allowed_prefixes, kind: str = "identity") -> None:
    """Raise unless `name` starts with an allowlisted test prefix. Default-deny (empty => refuse all)."""
    if not any(name.startswith(p) for p in allowed_prefixes):
        raise SmokeSafetyError(
            f"refusing to operate on {kind} {name!r}: not an allowlisted test identity. "
            f"Set PROXIMO_SMOKE_IDENTITY_PREFIXES to the test-identity prefix(es)."
        )


def load_identity_allowlist(env) -> frozenset[str]:
    """Allowlisted test-identity prefixes from PROXIMO_SMOKE_IDENTITY_PREFIXES (csv). Empty => deny."""
    return frozenset(_csv(env.get("PROXIMO_SMOKE_IDENTITY_PREFIXES", "")))
