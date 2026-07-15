"""Proximo APT plane — PVE patch-visibility + repository governance (Wave 1a, 2026-07-15).

Endpoints (all under /nodes/{node}/apt/...):

  GET  /update                          — pve_apt_updates_list       (read)
  POST /update                          — pve_apt_update_refresh     (MUTATION, LOW)
  GET  /changelog?name=…[&version=…]    — pve_apt_changelog          (read; ADVERSARIAL taint)
  GET  /repositories                    — pve_apt_repositories_get   (read)
  POST /repositories                    — pve_apt_repository_set     (MUTATION, MEDIUM, CAPTURE)
  PUT  /repositories                    — pve_apt_repository_add     (MUTATION, MEDIUM, CAPTURE)
  GET  /versions                        — pve_apt_versions           (read)

Schema truth: .scratch/api-schemas-2026-07-15/methods-pve.json (`/apt`) + the upstream
PVE::API2::APT.pm Perl source (param names/types cross-checked 2026-07-15). NONE of these seven
are live-verified yet — every backend method (backends.py) carries its own Smoke-confirm comment.

HONESTY LINE (ship verbatim in spirit in every pve_apt_* wrapper docstring): Proxmox's API
deliberately does not expose upgrade execution; the upgrade itself happens at your console. This
tool governs visibility and repo config only.

CAPTURE-or-declare: apt_repository_set/apt_repository_add read current repository state via
GET /apt/repositories before planning — best-effort, since the exact nested shape of
files[].repositories[] is not live-verified: a missing/empty match degrades to an honest empty
snapshot (current={}) rather than raising (the read still SUCCEEDED, it just found no matching
entry yet — e.g. a brand-new handle that was never added). Only a raised exception on the read
itself (e.g. a transport error) sets complete=False, matching the node_lifecycle.py
CAPTURE-or-declare idiom.

apt_update_refresh needs no capture: refreshing the index is idempotent and self-reverting
(re-running it any time is always safe), so its plan declares that directly rather than reading
state.

Security posture:
- name (changelog) validated against PVE's own upstream pattern (_check_apt_package_name) —
  in backends.py, since apt_changelog has no plan factory (it is a READ, not gated).
- path (repository_set) validated as an absolute path, no traversal (_check_apt_repo_path).
- index (repository_set) validated as a non-negative integer (_check_apt_index).
- handle (repository_add) is shape-only validated (_check_apt_handle) — the actual valid set of
  standard-repo handles is version/product-dependent, not a fixed enum upstream.
- digest (repository_set/repository_add) validated as a hex string, max 80 chars
  (_check_apt_digest), forwarded for optimistic-concurrency when the caller supplies it — PVE
  documents this the same way PBS does.
"""

from __future__ import annotations

from typing import Any

from .backends import (
    _check_apt_digest,
    _check_apt_handle,
    _check_apt_index,
    _check_apt_repo_path,
    _check_node,
)
from .planning import RISK_LOW, RISK_MEDIUM, Plan


def plan_apt_update_refresh(
    node: str | None = None,
    notify: bool | None = None,
    quiet: bool | None = None,
) -> Plan:
    """Plan for pve_apt_update_refresh — resynchronize the APT package index (apt-get update).

    No CAPTURE: refreshing the index is idempotent (re-running it any time is always safe) —
    there is no meaningful "current index state" to snapshot for revert.
    """
    _check_node(node)
    n = node or "default"
    return Plan(
        action="pve_apt_update_refresh",
        target=f"node/{n}/apt/update",
        change="resynchronize the APT package index from configured sources (apt-get update)",
        current={},
        blast_radius=[
            f"node/{n} APT package index cache — refreshes available-update metadata only; "
            "does NOT install or upgrade any package (Proxmox's API deliberately does not "
            "expose upgrade execution — the upgrade itself happens at your console)"
        ],
        risk=RISK_LOW,
        risk_reasons=["no package state change — only refreshes the local index cache"],
        complete=True,
        note="Idempotent — safe to re-run any time; no revert needed.",
    )


def plan_apt_repository_set(
    api: Any,
    path: str,
    index: int,
    node: str | None = None,
    enabled: bool | None = None,
    digest: str | None = None,
) -> Plan:
    """Plan for pve_apt_repository_set — enable/disable one repository entry by path+index.

    CAPTURE-or-declare: reads current repository state via GET /apt/repositories (reuses
    apt_repositories_get) and looks up the file+index entry's current shape; a successful read
    that simply finds no match degrades to current={} (honest empty snapshot), not a failure —
    only a raised exception on the read itself sets complete=False.
    """
    _check_apt_repo_path(path)
    _check_apt_index(index)
    _check_apt_digest(digest)
    _check_node(node)
    n = node or api.config.node
    current: dict = {}
    complete = True
    note_capture = ""
    try:
        result = api.apt_repositories_get(node) or {}
        for f in result.get("files") or []:
            if f.get("path") == path:
                current["file_digest"] = f.get("digest")
                repos = f.get("repositories") or []
                if 0 <= index < len(repos):
                    current["entry"] = repos[index]
                break
    except Exception:
        complete = False
        note_capture = " Could not capture current repository state — no guided revert available."
    changes = {k: v for k, v in {"enabled": enabled}.items() if v is not None}
    return Plan(
        action="pve_apt_repository_set",
        target=f"node/{n}/apt/repositories:{path}#{index}",
        change=f"change repository entry {index} in {path!r}: {changes}",
        current=current,
        blast_radius=[
            f"node/{n} APT sources — {path!r} entry {index}: changes where packages come from; "
            "the NEXT apt-get upgrade (run at your console — this API does not execute it) "
            "pulls from the new set"
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "changes which repository entry is enabled/disabled — affects package provenance "
            "for the next upgrade"
        ],
        complete=complete,
        note=(
            "Revert by re-applying the captured enabled-state with pve_apt_repository_set."
            + note_capture
        ),
    )


def plan_apt_repository_add(
    api: Any,
    handle: str,
    node: str | None = None,
    digest: str | None = None,
) -> Plan:
    """Plan for pve_apt_repository_add — add a standard repository to the configuration.

    CAPTURE-or-declare: reads current repository state via GET /apt/repositories (reuses
    apt_repositories_get) and looks up the handle's current standard-repo status; a successful
    read that simply finds no match degrades to current={} (honest empty snapshot — the handle
    was never added), not a failure — only a raised exception on the read itself sets
    complete=False.
    """
    _check_apt_handle(handle)
    _check_apt_digest(digest)
    _check_node(node)
    n = node or api.config.node
    current: dict = {}
    complete = True
    note_capture = ""
    try:
        result = api.apt_repositories_get(node) or {}
        standard = result.get("standard-repos") or []
        current = next((r for r in standard if r.get("handle") == handle), {})
    except Exception:
        complete = False
        note_capture = " Could not capture current standard-repo status — no guided revert available."
    return Plan(
        action="pve_apt_repository_add",
        target=f"node/{n}/apt/repositories:{handle}",
        change=f"add standard repository {handle!r} to the configuration",
        current=current,
        blast_radius=[
            f"node/{n} APT sources — adds {handle!r}; the NEXT apt-get upgrade (run at your "
            "console — this API does not execute it) additionally pulls packages from it"
        ],
        risk=RISK_MEDIUM,
        risk_reasons=["adds a new package source — affects package provenance for the next upgrade"],
        complete=complete,
        note=(
            "No automatic revert: removing an added repository requires pve_apt_repository_set "
            "to disable the resulting entry (there is no repository-delete endpoint)."
            + note_capture
        ),
    )
