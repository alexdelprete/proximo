"""Storage / ISO / template operations — content listing, status, download, and delete.

This module adds the STORAGE group to Proximo's trust layer. It follows the same idioms
as backends.py (ApiBackend free functions) and planning.py (pure Plan factories).

Endpoint shape note (flagged for live-smoke confirmation):
  The PVE API reference shows DELETE of a specific volume as
    DELETE /nodes/{node}/storage/{storage}/content/{volume}
  i.e. with an explicit /content/ segment before the quoted volid.
  The implementation below uses that full path. Confirm on a live PVE during smoke
  that `content_delete` emits the right URL; the difference is `/content/{volid}` vs
  `/{volid}` (bare). The test matches this implementation; adjust both if the live API
  disagrees.

ASYNC ops (download_url, content_delete) return a UPID string. The server layer adds
confirm-gating + ledger audit before invoking mutations.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from .backends import ProximoError, _check_node
from .planning import RISK_HIGH, RISK_MEDIUM, Plan

# ---------------------------------------------------------------------------
# Validators (module-local)
# ---------------------------------------------------------------------------

_STORAGE_RE = re.compile(r"^[A-Za-z0-9._-]+\Z")

# volid: "storeid:path/component" — colon required; path segment may use letters, digits, dot,
# hyphen, underscore, forward-slash. \Z (not $) to block embedded newlines.
_VOLID_RE = re.compile(r"^[A-Za-z0-9._-]+:[A-Za-z0-9._/-]+\Z")

# Content types for the listing/filter endpoint.
_CONTENT_LIST_TYPES = frozenset({"iso", "vztmpl", "backup"})
# Content types accepted by the download-url endpoint.
_CONTENT_DOWNLOAD_TYPES = frozenset({"iso", "vztmpl"})


def _check_storage(storage: str) -> str:
    if not _STORAGE_RE.match(storage):
        raise ProximoError(f"invalid storage id: {storage!r} (letters/digits/._- only)")
    return storage


def _check_volid(volid: str) -> str:
    """Validate volid shape and reject path traversal, then return the volid unchanged.

    Callers must URL-encode the volid separately (with quote(volid, safe='')) for path segments.
    """
    if not _VOLID_RE.match(volid):
        raise ProximoError(
            f"invalid volid: {volid!r} — expected <storage>:<path> with only safe chars "
            "(letters, digits, ._-/ after the colon; no spaces, quotes, or control chars)"
        )
    # Explicit traversal rejection: quote() passes '.' through (dots are unreserved in RFC 3986).
    # Empty segments ('//') are rejected too — they normalize unpredictably server-side.
    _, _, path = volid.partition(":")
    for segment in path.split("/"):
        if segment in ("", ".."):
            raise ProximoError(f"empty or traversal path segment rejected in volid: {volid!r}")
    return volid


def _check_filename(filename: str) -> str:
    """A download filename must be a bare name — no path separators, no traversal, no leading dot —
    so a remote download can't be steered outside the storage's content directory."""
    f = str(filename)
    if not f or "/" in f or "\\" in f or ".." in f or f.startswith("."):
        raise ProximoError(
            f"invalid filename: {filename!r} (bare name only — no '/', '\\', '..', or leading '.')"
        )
    return f


# ---------------------------------------------------------------------------
# Storage ops (functional — take api as first arg, like diagnose.py)
# ---------------------------------------------------------------------------

def storage_content(api, storage: str, node: str | None = None, content: str | None = None) -> list:
    """List content in a storage pool.

    GET /nodes/{node}/storage/{storage}/content
    Optional: ?content=iso|vztmpl|backup  (filters by content type)

    Returns a list of volume dicts from PVE.
    """
    _check_node(node)
    _check_storage(storage)
    n = node or api.config.node
    path = f"/nodes/{n}/storage/{storage}/content"
    if content is not None:
        if content not in _CONTENT_LIST_TYPES:
            raise ProximoError(
                f"invalid content filter: {content!r} (expected one of {sorted(_CONTENT_LIST_TYPES)})"
            )
        path = f"{path}?content={content}"
    return api._get(path) or []


def storage_status(api, storage: str, node: str | None = None) -> dict:
    """Get storage pool status (total / used / avail / enabled).

    GET /nodes/{node}/storage/{storage}/status

    Returns a dict from PVE.
    """
    _check_node(node)
    _check_storage(storage)
    n = node or api.config.node
    return api._get(f"/nodes/{n}/storage/{storage}/status") or {}


def storage_download_url(
    api,
    storage: str,
    content: str,
    url: str,
    filename: str,
    node: str | None = None,
    checksum: str | None = None,
    checksum_algorithm: str | None = None,
) -> str:
    """Fetch a remote ISO or container template into a storage pool.

    POST /nodes/{node}/storage/{storage}/download-url

    content must be 'iso' or 'vztmpl'.
    Returns a UPID string (async PVE task).

    MUTATION — confirm-gated + audited at the server layer before this is called.
    """
    _check_node(node)
    _check_storage(storage)
    if content not in _CONTENT_DOWNLOAD_TYPES:
        raise ProximoError(
            f"invalid download content type: {content!r} (expected one of {sorted(_CONTENT_DOWNLOAD_TYPES)})"
        )
    filename = _check_filename(filename)
    n = node or api.config.node
    data: dict = {"content": content, "url": url, "filename": filename}
    if checksum is not None:
        data["checksum"] = checksum
    if checksum_algorithm is not None:
        data["checksum-algorithm"] = checksum_algorithm
    return api._post(f"/nodes/{n}/storage/{storage}/download-url", data)


def content_delete(api, storage: str, volid: str, node: str | None = None):
    """Delete a volume from storage (ISO, template, backup, disk image).

    DELETE /nodes/{node}/storage/{storage}/content/{quoted_volid}

    volid shape: "storeid:path/to/file.iso" (colon-separated; validated + URL-encoded).
    Returns a UPID string (async PVE task) or None.

    MUTATION — confirm-gated + audited at the server layer before this is called.

    *** Smoke-confirm: verify the path segment is /content/{volid} (with the /content/
    prefix) and not a bare /{volid} on your live PVE during the first integration test. ***
    """
    _check_node(node)
    _check_storage(storage)
    _check_volid(volid)
    n = node or api.config.node
    quoted = quote(volid, safe="")
    return api._delete(f"/nodes/{n}/storage/{storage}/content/{quoted}")


# ---------------------------------------------------------------------------
# Plan factories (pure — no I/O; no api arg)
# ---------------------------------------------------------------------------

def plan_storage_download(storage: str, content: str, url: str, filename: str) -> Plan:
    """Preview a remote download into storage.

    RISK_MEDIUM: network fetch (operator-supplied URL + filename are NOT validated for safety),
    consumes storage space, and adds an unverified file to the pool.
    """
    return Plan(
        action="pve_storage_download",
        target=f"storage/{storage}",
        change=f"download {content} from {url} into {storage} as {filename}",
        current={},
        blast_radius=[
            f"fetches {url} into {storage} as {filename} ({content}) — network download, consumes space",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "the source URL is operator-trusted — Proximo does not verify what it serves; "
            "trust the source before proceeding",
            "network download into storage: consumes space, file content is unverified by Proximo",
        ],
        note=(
            "The filename is constrained to a bare name (no path separators or traversal), but the "
            "URL and its content are operator-trusted input — Proximo does not inspect or sandbox the "
            "remote content. If checksum/checksum-algorithm are provided they are passed to PVE "
            "verbatim — verify the hash algorithm and value are correct."
        ),
    )


def plan_content_delete(storage: str, volid: str) -> Plan:
    """Preview deletion of a storage volume.

    RISK_MEDIUM by default (ISO / template / disk image removes a boot/deploy resource).
    Escalates to RISK_HIGH if the volid looks like a backup archive (path component contains
    a 'backup' directory segment, or the filename matches the 'vzdump-' prefix pattern) —
    backups cannot be restored after deletion.
    """
    _, _, vol_path = volid.partition(":")
    path_segments = vol_path.split("/")
    is_backup = "backup" in path_segments or any("vzdump-" in seg for seg in path_segments)
    if is_backup:
        risk = RISK_HIGH
        risk_reasons = [
            "removes a backup archive — you cannot restore from it afterward",
            "volid matches backup pattern (backup/ directory or vzdump- filename)",
        ]
    else:
        risk = RISK_MEDIUM
        risk_reasons = [
            "removes a storage volume (ISO / template / image) — it cannot be used after deletion",
        ]
    return Plan(
        action="pve_content_delete",
        target=f"storage/{storage}",
        change=f"delete volume {volid} from {storage}",
        current={},
        blast_radius=[f"permanently removes {volid} from {storage}"],
        risk=risk,
        risk_reasons=risk_reasons,
    )
