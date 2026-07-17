"""SDN PREFIX-LISTS + ROUTE-MAPS pillar (Wave 7e, full-surface campaign).

Two BGP/OSPF routing-policy primitive families on the SAME staged-pending SDN plane as
`network.py`'s zone/vnet/subnet CRUD and `sdn_objects.py`'s controller/dns/ipam CRUD:
  prefix-lists -> /cluster/sdn/prefix-lists[/{id}][/entries[/{url_seq}]]
  route-maps   -> /cluster/sdn/route-maps[/entries[/{route-map-id}[/entry/{order}]]]

Both are referenced-by-id from controllers/fabrics (a controller's route-map-in/route-map-out,
a fabric's redistribute[].route-map, a fabric's route_filter naming a prefix-list) but neither
family is built there — Wave 7d (fabrics) is sequenced AFTER this chunk specifically so its own
docstrings can name a real, already-built creation path instead of describing a forward
reference (`.scratch/sdd/wave-7-draft-decomposition.md` §5).

Schema truth: `.scratch/api-schemas-2026-07-15/wave7-pve-sdn-schema.json` (49 paths, 90
methods) — the 8 prefix-list/route-map paths read in full field-by-field for this build, not
assumed from the draft's summary.

Both families are PENDING (staged) config, same lifecycle as zone/vnet/subnet/controller/dns/
ipam: inert until `pve_sdn_apply`, recoverable either narrowly (a second CRUD call) or broadly
via `pve_sdn_rollback` (Wave 7a's UNDO-honesty upgrade — discards every pending SDN edit
cluster-wide). Every create/update/delete plan factory states both paths.

Schema-verified facts for THIS build (checked field-by-field, not assumed from the draft):

1. **`url_seq` is a genuinely UNDOCUMENTED path parameter — confirmed, not merely repeated
   from the draft.** ~~All three methods on `/cluster/sdn/prefix-lists/{id}/entries/{url_seq}`
   (GET/PUT/DELETE) declare `id` as their only path-shaped required parameter~~
   **[STRIKE-AND-CORRECT: GET and DELETE declare `id` as required; PUT declares zero required
   parameters and does not list `id` at all — only GET/DELETE require it.]** `url_seq` never
   appears in any of the three methods' own parameter schema, not even as an optional field.
   The path segment is real (it is literally in the URL) — just formally untyped. Treated here
   as an OPAQUE path token (`_check_entry_id`): path-safety validated (no `/`, no whitespace/
   control characters, no `..`), NEVER validated as an integer, captured by the caller from a
   prior `pve_sdn_prefix_list_entries_list`/`pve_sdn_prefix_list_entry_get` read. In practice it
   is almost certainly the entry's own `seq` field (the `entries_list` response's own child
   `links` entry is literally `"href": "{seq}"`) — but that is an inference from adjacent
   schema shape, not a stated contract, so it is never enforced as numeric.
2. **`order` (route-map entries) is the OPPOSITE of `url_seq` — a properly-typed, REQUIRED
   integer (0-65535) on ALL THREE of ITS methods (GET/PUT/DELETE)**, safely validated
   client-side (`_check_order`) the way `url_seq` cannot be. This asymmetry between two
   sibling sub-APIs on the SAME plane is real and load-bearing — the two path parameters are
   NOT handled the same way, and this module does not mirror one onto the other.
3. **Route-maps have NO container-level create/update/delete at all** — verified: no
   `POST /cluster/sdn/route-maps` exists anywhere in this schema. A route-map is defined
   purely by having >=1 entry; `route-map-id` is a free field on
   `POST /cluster/sdn/route-maps/entries` — the FIRST `pve_sdn_route_map_entry_create` call for
   a given id implicitly brings that route-map into existence. Whether deleting the LAST entry
   of a route-map leaves an orphaned empty id or PVE cleans it up automatically is NOT stated
   anywhere in this schema (Smoke-confirm label on `pve_sdn_route_map_entry_delete`'s plan — no
   invented semantics either way, per the coordinator's ruling #5).
4. **`digest` availability is a THREE-WAY asymmetry across this plane, not two-way** — checked
   field-by-field, not assumed from `sdn_objects.py`'s own (controller/dns/ipam) two-way
   split (digest on update only, never create):
   - Prefix-list CONTAINER (`POST`/`PUT /cluster/sdn/prefix-lists[/{id}]`): `digest` IS accepted
     on BOTH create and update — one of only two exceptions on the whole SDN plane (the other
     is fabric create, Wave 7d) to the "digest never on create" convention.
   - Prefix-list ENTRY (`POST`/`PUT .../entries[/{url_seq}]`): `digest` is accepted ONLY on
     update, NOT on create — the more common two-way split.
   - Route-map ENTRY (`POST`/`PUT .../entries[/.../entry/{order}]`): `digest` IS accepted on
     BOTH create and update — matching the prefix-list CONTAINER's own two-create-exception
     shape, not the prefix-list ENTRY's split. Three distinct patterns on one plane; documented
     per-function below rather than papered over with one blanket rule.
   `DELETE` never accepts `digest` anywhere on this plane (matches the universal convention).
5. **`lock-token` is accepted by EVERY mutation on both families** (~~all 15~~ **all 9
   POST/PUT/DELETE methods** checked field-by-field) — forwarded raw to the wire, never written to
   `_audited()`'s `detail=` (mirrors the network.py/sdn_objects.py precedent exactly: a lock
   token is a CAPABILITY HANDLE, not a password, per network.py's own module docstring).
6. **Every mutation on this plane returns `null`** (checked field-by-field: all 6 container +
   entry prefix-list verbs, all 3 route-map entry verbs) — synchronous, callable-outcome idiom,
   `outcome="ok"`, never a UPID (Wave 7 draft Fact #2, re-verified here for this specific
   9-mutation family).
7. **`route-maps` list (bare, container-level) has NO `pending` query param** — checked: only
   `running` (optional bool). Every OTHER list endpoint on this module (prefix-lists list,
   route-map entries-all, route-map entries-for-one-id) accepts both `pending` and `running`.
   A real, isolated asymmetry — not normalized away.
8. **`match`/`set` (route-map entry create/update) are arrays of `{key, value}` composite
   objects, `exit-action` is a SINGLE `{key, value}` composite object** — `key` is enum-typed
   server-side per field (route-type/vni/ip-address-prefix-list/... for match;
   ip-next-hop/local-preference/... for set; on-match-goto/on-match-next/continue for
   exit-action) but this module does NOT hand-enumerate or validate those per-key enums
   client-side (Fact #10's "generic passthrough, PVE validates server-side" guidance, applied
   here to a genuinely variable-shape array/composite rather than a type-conditional field
   set — the same spirit `sdn_objects.py`'s `controllers` `options: dict` passthrough follows
   for its own type-conditional fields). Only a light "is it actually a list/dict" shape guard
   is applied (`_check_list_of_dicts`/`_check_dict`) — not a deep per-item schema.
9. **Prefix-list CONTAINER create/update's own `entries` field is a BULK array of composite
   `{action, prefix, ge?, le?, seq?}` objects** — lets a caller seed/replace a prefix list's
   entire entry set in ONE call, distinct from the per-entry
   `pve_sdn_prefix_list_entry_create/update/delete` granular path. Generic passthrough for the
   same reason as fact #8 (a variable-length array of composite objects, not a fixed field
   set). Whether `PUT`'s own `entries` REPLACES the whole array or MERGES by matching existing
   `seq` values is NOT stated in this schema — documented, not assumed either way.
10. **No secret-shaped field exists anywhere on this plane** (checked: prefix-list/route-map
    container+entry parameters are entirely routing-policy primitives — ids, CIDRs, action
    enums, integers, and the two composite arrays above; no `url`/`key`/`token`/`password`-
    shaped field appears on any of the 8 paths) — UNLIKE `sdn_objects.py`'s dns `key`/ipam
    `token`. No secret-handling ruling is needed here; nothing is redacted.

Validators: prefix-list/route-map ids reuse `network.py`'s existing `_check_sdn_id`
(alnum/_/- up to 64 chars) — the same "the existing looser validator already accepts every
legal input, PVE is the real gate" reasoning `sdn_objects.py`'s own module docstring
established for controller/dns/ipam ids (neither `pve-sdn-prefix-list-id` nor
`pve-sdn-route-map-id` carries a stated regex anywhere in this schema — no formats/definitions
section exists in the schema file at all — so there is no stricter pattern to duplicate).
`delete` (settings-to-unset) reuses `network.py`'s `_sdn_csv`.

Taint: every read on this module (prefix_lists_list/prefix_list_get/prefix_list_entries_list/
prefix_list_entry_get/route_maps_list/route_map_entries_list_all/route_map_entries_list/
route_map_entry_get) is REVIEWED_TRUSTED — operator-authored routing-policy configuration, the
same channel as the already-REVIEWED_TRUSTED zone/vnet/subnet/controller/dns/ipam family; no
field on this plane carries wire-learned/peer-announced/guest-influenced content the way
`pve_sdn_zone_ip_vrf`/`pve_sdn_vnet_mac_vrf`/`pve_sdn_ipam_status` do. All 9 mutations return
`null` (fact #6) — no content channel to classify either way, REVIEWED_TRUSTED regardless.

Risk ratings (coordinator ruling, `.scratch/2026-07-15-full-surface-campaign.md` § Wave 7
ruling block + `.scratch/sdd/wave-7-draft-decomposition.md` §3): container/entry create+update
= LOW (pending, inert until apply); container/entry delete = MEDIUM (staging a removal an
apply would enact). Referential-integrity claims ("PVE refuses to delete a prefix-list still
named by a fabric's route_filter", "a controller's route-map-in/out still naming this
route-map") are asserted BY ANALOGY ONLY, Smoke-confirm labeled per the coordinator's ruling
#4 (prefix-list delete is one of the 5 new DELETE families that ruling explicitly covers) and
by the SAME analogy for route-map entries (not literally one of the named 5, but the identical
reasoning applies — asserted, not re-derived from this schema's own terse delete
descriptions). Route-map's own orphan-after-last-entry-delete question (fact #3) is
additionally Smoke-confirm labeled per ruling #5 — no invented semantics.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import quote, urlencode

from .backends import ProximoError
from .network import _check_sdn_id, _sdn_csv
from .planning import RISK_LOW, RISK_MEDIUM, Plan

# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

_VALID_ACTIONS = frozenset({"permit", "deny"})

# Opaque {url_seq} path token (fact #1): no '/' (blocks path-segment smuggling), no
# whitespace/control characters. NOT an integer-typed check — url_seq has no formal type
# anywhere in the schema.
_OPAQUE_ENTRY_ID_RE = re.compile(r"^[^/\s\x00-\x1f\x7f]+\Z")


def _check_action(value: str) -> str:
    v = str(value).strip()
    if v not in _VALID_ACTIONS:
        raise ProximoError(f"invalid action: {value!r} (expected one of {sorted(_VALID_ACTIONS)})")
    return v


def _check_bounded_int(value, field: str, lo: int, hi: int) -> int:
    """Bare int cast + an explicit schema-stated bound (unlike sdn_objects.py's `_check_int`,
    which deliberately does NOT invent a bound where the schema states none — ge/le/seq/order
    all DO carry an explicit minimum/maximum in this schema, so those bounds are enforced
    client-side, matching the backends.py `_check_ceph_osd_min`/pmg.py port-range precedent)."""
    if isinstance(value, bool):
        raise ProximoError(f"invalid {field}: {value!r} (must be an integer)")
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise ProximoError(f"invalid {field}: {value!r} (must be an integer)") from exc
    if not (lo <= n <= hi):
        raise ProximoError(f"invalid {field}: {value!r} (must be an integer between {lo} and {hi})")
    return n


def _check_order(value) -> int:
    return _check_bounded_int(value, "order", 0, 65535)


def _check_ge_le(value, field: str) -> int:
    return _check_bounded_int(value, field, 0, 128)


def _check_seq(value) -> int:
    return _check_bounded_int(value, "seq", 1, 4294967295)


def _check_prefix_cidr(value: str) -> str:
    """Validate the prefix-list entry's `prefix` (schema format FullRangeCIDR — covers both
    the usual host-bits-zero CIDR AND the "full range" 0.0.0.0/0 / ::/0 forms). Mirrors
    network.py's own `_check_subnet_cidr` mechanism (ipaddress.ip_network, strict=False) —
    a fresh per-module copy, not cross-imported, since the two fields carry different schema
    format names and this module's own docstring/error text differs."""
    v = str(value).strip()
    try:
        ipaddress.ip_network(v, strict=False)
    except ValueError as exc:
        raise ProximoError(
            f"invalid prefix: {value!r} (expected a CIDR network, e.g. 10.0.0.0/8 or ::/0)"
        ) from exc
    return v


def _check_entry_id(value) -> str:
    """Path-safety-only validator for the OPAQUE {url_seq} path token (fact #1) — mirrors
    backup.py's `_check_volid` idiom (charset + explicit '..' rejection), NOT integer-typed."""
    v = str(value)
    if ".." in v:
        raise ProximoError(f"invalid entry id: {value!r} (path traversal rejected)")
    if not v or not _OPAQUE_ENTRY_ID_RE.match(v):
        raise ProximoError(
            f"invalid entry id: {value!r} (must not be empty, contain '/', or contain "
            "whitespace/control characters)"
        )
    return v


def _check_list_of_dicts(value, field: str) -> list | None:
    """Light shape guard for a generic-passthrough array param (fact #8/#9) — confirms it IS a
    list before forwarding; does NOT validate each item's own per-key enum (PVE's job)."""
    if value is None:
        return None
    if not isinstance(value, list):
        raise ProximoError(f"{field} must be a list of objects")
    return value


def _check_dict(value, field: str) -> dict | None:
    """Light shape guard for a generic-passthrough single composite param (fact #8's
    `exit-action`) — confirms it IS a dict before forwarding."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ProximoError(f"{field} must be an object")
    return value


def _list_query(**flags: bool | None) -> str:
    """Build an optional query string from named boolean flags, PVE's 1/0 boolean convention
    (a fresh per-module copy of network.py's `_sdn_get_query`, extended to an arbitrary flag
    set since this module's 4 list endpoints vary in which of pending/running/verbose each one
    accepts — fact #7 — unlike network.py's single-shape pending+running pair)."""
    q = {k: (1 if v else 0) for k, v in flags.items() if v is not None}
    return f"?{urlencode(q)}" if q else ""


def _pending_blast(lead: str) -> list[str]:
    """Same shape as network.py's `_sdn_pending_blast` / sdn_objects.py's `_pending_blast` — a
    fresh per-family copy (the exact wording differs by object type)."""
    return [
        lead,
        "INERT until pve_sdn_apply (a separate RISK_HIGH step) — no live network effect yet",
        "no NARROW undo at config level: revert by deleting/re-creating the pending object "
        "before apply, OR call pve_sdn_rollback to discard EVERY pending SDN edit "
        "cluster-wide (broad, all-or-nothing, but a REAL undo primitive)",
    ]


def _kv_parts(fields: dict) -> list[str]:
    """Sorted 'k=v' parts — mirrors network.py's `_sdn_kv_parts` / sdn_objects.py's own copy."""
    return [f"{k}={fields[k]}" for k in sorted(fields)]


def _composite_str(item: dict) -> str:
    """Render a single composite dict as {k=v, k=v, ...} for plan disclosure."""
    if not item:
        return "{}"
    parts = [f"{k}={item[k]}" for k in sorted(item)]
    return "{" + ", ".join(parts) + "}"


def _composite_array_str(items: list[dict]) -> str:
    """Render an array of composite dicts as [{k=v}, {k=v}, ...] for plan disclosure."""
    if not items:
        return "[]"
    rendered = [_composite_str(item) for item in items]
    return "[" + ", ".join(rendered) + "]"


# ===========================================================================
# PREFIX LISTS
# ===========================================================================

def prefix_lists_list(api, pending: bool | None = None, running: bool | None = None,
                       verbose: bool | None = None) -> list[dict]:
    """List SDN prefix lists (cluster-scoped). GET /cluster/sdn/prefix-lists.

    verbose=False (schema: "If 0, only returns id - otherwise returns all properties") returns
    id-only summaries; omit or True for the fuller per-item shape (exact fields uncertain —
    schema declares an empty item shape, `properties: {}`). REVIEWED_TRUSTED."""
    path = f"/cluster/sdn/prefix-lists{_list_query(pending=pending, running=running, verbose=verbose)}"
    return api._get(path) or []


def prefix_list_get(api, prefix_list: str) -> dict:
    """Read a single SDN prefix list's configuration (including its entries).
    GET /cluster/sdn/prefix-lists/{id}. REVIEWED_TRUSTED."""
    pl = _check_sdn_id(prefix_list, "prefix-list")
    return api._get(f"/cluster/sdn/prefix-lists/{pl}") or {}


def prefix_list_create(api, prefix_list: str, entries: list[dict] | None = None,
                        digest: str | None = None, lock_token: str | None = None) -> object:
    """Create an SDN prefix list (PENDING). POST /cluster/sdn/prefix-lists
    {id, entries?, digest?, lock-token?}.

    `entries` optionally seeds this list's entries in the SAME call — a bulk array of
    `{action, prefix, ge?, le?, seq?}` composite objects (generic passthrough, fact #9); PVE
    validates each item server-side. The more granular path is create empty, then add entries
    one at a time via pve_sdn_prefix_list_entry_create.

    `digest` IS accepted on prefix-list CREATE — one of only two exceptions on the whole SDN
    plane (fact #4; the other is fabric create, Wave 7d) to the "digest never on create"
    convention. Inert until pve_sdn_apply."""
    pl = _check_sdn_id(prefix_list, "prefix-list")
    entries = _check_list_of_dicts(entries, "entries")
    data: dict = {"id": pl}
    if entries is not None:
        data["entries"] = entries
    if digest is not None:
        data["digest"] = digest
    if lock_token is not None:
        data["lock-token"] = lock_token
    return api._post("/cluster/sdn/prefix-lists", data)


def prefix_list_update(api, prefix_list: str, entries: list[dict] | None = None,
                        delete: list | str | None = None, digest: str | None = None,
                        lock_token: str | None = None) -> object:
    """Update an SDN prefix list (PENDING). PUT /cluster/sdn/prefix-lists/{id}.

    `entries` (if given) is forwarded as-is (generic passthrough, fact #9) — whether it
    REPLACES or MERGES with the existing entries by `seq` is NOT stated in the schema,
    documented not assumed. `delete` accepts only "entries" (the schema's sole enum value for
    this endpoint's unset list) — clears the whole entries array. `digest` IS accepted here
    (matches create — fact #4). Requires >=1 field to set or delete."""
    pl = _check_sdn_id(prefix_list, "prefix-list")
    entries = _check_list_of_dicts(entries, "entries")
    data: dict = {}
    if entries is not None:
        data["entries"] = entries
    if not data and not delete:
        raise ProximoError("prefix_list_update requires at least one field to set or delete")
    if delete:
        data["delete"] = _sdn_csv(delete)
    if digest is not None:
        data["digest"] = digest
    if lock_token is not None:
        data["lock-token"] = lock_token
    return api._put(f"/cluster/sdn/prefix-lists/{pl}", data)


def prefix_list_delete(api, prefix_list: str, lock_token: str | None = None) -> object:
    """Delete an SDN prefix list (PENDING). DELETE /cluster/sdn/prefix-lists/{id}.

    No `digest` on delete (matches the plane-wide convention). Referential-integrity refusal
    (e.g. a fabric's `route_filter` still naming this list) is asserted BY ANALOGY only —
    Smoke-confirm (coordinator ruling #4)."""
    pl = _check_sdn_id(prefix_list, "prefix-list")
    params: dict = {}
    if lock_token is not None:
        params["lock-token"] = lock_token
    return api._delete(f"/cluster/sdn/prefix-lists/{pl}", params)


def prefix_list_entries_list(api, prefix_list: str) -> list[dict]:
    """List a prefix list's entries. GET /cluster/sdn/prefix-lists/{id}/entries.
    Schema declares an empty per-item shape (undocumented fields) — the entries' own
    action/prefix/ge/le/seq come through in practice per the create/update field schema, just
    not spelled out in the list response's own docs. REVIEWED_TRUSTED."""
    pl = _check_sdn_id(prefix_list, "prefix-list")
    return api._get(f"/cluster/sdn/prefix-lists/{pl}/entries") or []


def prefix_list_entry_get(api, prefix_list: str, entry_id) -> dict:
    """Read a single prefix-list entry. GET /cluster/sdn/prefix-lists/{id}/entries/{url_seq}.

    `entry_id` is the OPAQUE {url_seq} path token (fact #1) — capture it from a prior
    pve_sdn_prefix_list_entries_list/pve_sdn_prefix_list_entry_get read; NOT client-side
    validated as an integer, unlike route-map's own {order}. REVIEWED_TRUSTED."""
    pl = _check_sdn_id(prefix_list, "prefix-list")
    eid = _check_entry_id(entry_id)
    return api._get(f"/cluster/sdn/prefix-lists/{pl}/entries/{quote(eid, safe='')}") or {}


def prefix_list_entry_create(api, prefix_list: str, action: str, prefix: str,
                              ge: int | None = None, le: int | None = None,
                              seq: int | None = None, lock_token: str | None = None) -> object:
    """Create a prefix-list entry (PENDING). POST /cluster/sdn/prefix-lists/{id}/entries
    {action, prefix, ge?, le?, seq?, lock-token?}.

    `action` is permit/deny (required); `prefix` is a CIDR network (required, schema format
    FullRangeCIDR); `ge`/`le` bound the matched prefix length (0-128 each — covers both IPv4
    and IPv6, since IPv6 maxes at /128); `seq` is an explicit sequence number
    (1-4294967295) — omit to let PVE assign one. NO `digest` on this endpoint (fact #4 — a
    real asymmetry vs. both the container create above and this same entry's own UPDATE
    below, both of which DO accept digest)."""
    pl = _check_sdn_id(prefix_list, "prefix-list")
    a = _check_action(action)
    p = _check_prefix_cidr(prefix)
    data: dict = {"action": a, "prefix": p}
    if ge is not None:
        data["ge"] = _check_ge_le(ge, "ge")
    if le is not None:
        data["le"] = _check_ge_le(le, "le")
    if seq is not None:
        data["seq"] = _check_seq(seq)
    if lock_token is not None:
        data["lock-token"] = lock_token
    return api._post(f"/cluster/sdn/prefix-lists/{pl}/entries", data)


def prefix_list_entry_update(api, prefix_list: str, entry_id, action: str | None = None,
                              prefix: str | None = None, ge: int | None = None,
                              le: int | None = None, seq: int | None = None,
                              delete: list | str | None = None, digest: str | None = None,
                              lock_token: str | None = None) -> object:
    """Update a prefix-list entry (PENDING). PUT .../prefix-lists/{id}/entries/{url_seq}.

    `entry_id` is the OPAQUE {url_seq} path token (fact #1). `delete` unsets le/ge/seq only
    (schema enum — NOT action/prefix, which have no unset option). `digest` IS accepted here
    (unlike this same entry's own CREATE above — fact #4). Requires >=1 field to set or
    delete."""
    pl = _check_sdn_id(prefix_list, "prefix-list")
    eid = _check_entry_id(entry_id)
    data: dict = {}
    if action is not None:
        data["action"] = _check_action(action)
    if prefix is not None:
        data["prefix"] = _check_prefix_cidr(prefix)
    if ge is not None:
        data["ge"] = _check_ge_le(ge, "ge")
    if le is not None:
        data["le"] = _check_ge_le(le, "le")
    if seq is not None:
        data["seq"] = _check_seq(seq)
    if not data and not delete:
        raise ProximoError("prefix_list_entry_update requires at least one field to set or delete")
    if delete:
        data["delete"] = _sdn_csv(delete)
    if digest is not None:
        data["digest"] = digest
    if lock_token is not None:
        data["lock-token"] = lock_token
    return api._put(f"/cluster/sdn/prefix-lists/{pl}/entries/{quote(eid, safe='')}", data)


def prefix_list_entry_delete(api, prefix_list: str, entry_id, lock_token: str | None = None) -> object:
    """Delete a prefix-list entry (PENDING). DELETE .../prefix-lists/{id}/entries/{url_seq}.
    `entry_id` is the OPAQUE {url_seq} path token (fact #1)."""
    pl = _check_sdn_id(prefix_list, "prefix-list")
    eid = _check_entry_id(entry_id)
    params: dict = {}
    if lock_token is not None:
        params["lock-token"] = lock_token
    return api._delete(f"/cluster/sdn/prefix-lists/{pl}/entries/{quote(eid, safe='')}", params)


# ===========================================================================
# ROUTE MAPS
# ===========================================================================

def route_maps_list(api, running: bool | None = None) -> list[dict]:
    """List SDN route maps (cluster-scoped, id-only summaries per schema).
    GET /cluster/sdn/route-maps?running=. NOTE: unlike every other list endpoint on this
    module, this one has NO `pending` query param (fact #7 — a real, isolated asymmetry, not
    an oversight). REVIEWED_TRUSTED."""
    return api._get(f"/cluster/sdn/route-maps{_list_query(running=running)}") or []


def route_map_entries_list_all(api, pending: bool | None = None,
                                running: bool | None = None) -> list[dict]:
    """List EVERY route-map entry across ALL route-maps in one call.
    GET /cluster/sdn/route-maps/entries. REVIEWED_TRUSTED."""
    path = f"/cluster/sdn/route-maps/entries{_list_query(pending=pending, running=running)}"
    return api._get(path) or []


def route_map_entries_list(api, route_map_id: str, pending: bool | None = None,
                            running: bool | None = None) -> list[dict]:
    """List every entry belonging to ONE route-map.
    GET /cluster/sdn/route-maps/entries/{route-map-id}. REVIEWED_TRUSTED."""
    rid = _check_sdn_id(route_map_id, "route-map")
    path = f"/cluster/sdn/route-maps/entries/{rid}{_list_query(pending=pending, running=running)}"
    return api._get(path) or []


def route_map_entry_get(api, route_map_id: str, order) -> dict:
    """Read a single route-map entry.
    GET /cluster/sdn/route-maps/entries/{route-map-id}/entry/{order}.

    `order` IS a properly-typed, schema-required integer (0-65535) — unlike prefix-list's
    opaque {url_seq}, safely client-validated here (fact #2). REVIEWED_TRUSTED."""
    rid = _check_sdn_id(route_map_id, "route-map")
    o = _check_order(order)
    return api._get(f"/cluster/sdn/route-maps/entries/{rid}/entry/{o}") or {}


def route_map_entry_create(api, route_map_id: str, order, action: str,
                            match: list[dict] | None = None,
                            set_clauses: list[dict] | None = None,
                            exit_action: dict | None = None, call: str | None = None,
                            digest: str | None = None, lock_token: str | None = None) -> object:
    """Create a route-map entry (PENDING). POST /cluster/sdn/route-maps/entries
    {route-map-id, order, action, match?, set?, exit-action?, call?, digest?, lock-token?}.

    There is NO container-level 'create a route-map' call (fact #3): a route-map is defined
    purely by having >=1 entry — `route_map_id` is a free-form id chosen by the caller; the
    FIRST entry_create for a given id implicitly brings that route-map into existence.

    `order` is REQUIRED (0-65535, the entry's position — fact #2); `action` is permit/deny
    (required). `match`/`set_clauses` are arrays of `{key, value}` composite objects (wire key
    for `set_clauses` is `set` — renamed here to avoid shadowing the `set` builtin, mirroring
    this codebase's `id`/`type` builtin-avoidance convention); `exit_action` is a single
    `{key, value}` composite dict (on-match-goto/on-match-next/continue); none of these three
    are validated against their own per-key enum client-side (fact #8, generic passthrough).
    `call` names ANOTHER route-map id to invoke as a sub-routine. `digest` IS accepted here
    (matches this entry's own UPDATE below — fact #4, a real asymmetry vs. prefix-list's entry
    CREATE, which has none)."""
    rid = _check_sdn_id(route_map_id, "route-map")
    o = _check_order(order)
    a = _check_action(action)
    match = _check_list_of_dicts(match, "match")
    set_clauses = _check_list_of_dicts(set_clauses, "set_clauses")
    exit_action = _check_dict(exit_action, "exit_action")
    data: dict = {"route-map-id": rid, "order": o, "action": a}
    if match is not None:
        data["match"] = match
    if set_clauses is not None:
        data["set"] = set_clauses
    if exit_action is not None:
        data["exit-action"] = exit_action
    if call is not None:
        data["call"] = _check_sdn_id(call, "route-map")
    if digest is not None:
        data["digest"] = digest
    if lock_token is not None:
        data["lock-token"] = lock_token
    return api._post("/cluster/sdn/route-maps/entries", data)


def route_map_entry_update(api, route_map_id: str, order, action: str | None = None,
                            match: list[dict] | None = None,
                            set_clauses: list[dict] | None = None,
                            exit_action: dict | None = None, call: str | None = None,
                            delete: list | str | None = None, digest: str | None = None,
                            lock_token: str | None = None) -> object:
    """Update a route-map entry (PENDING).
    PUT /cluster/sdn/route-maps/entries/{route-map-id}/entry/{order}.

    `delete` unsets set/match/call/exit-action only (schema enum — NOT action or order, which
    have no unset option). `digest` IS accepted here (matches CREATE — fact #4). Requires >=1
    field to set or delete."""
    rid = _check_sdn_id(route_map_id, "route-map")
    o = _check_order(order)
    match = _check_list_of_dicts(match, "match")
    set_clauses = _check_list_of_dicts(set_clauses, "set_clauses")
    exit_action = _check_dict(exit_action, "exit_action")
    data: dict = {}
    if action is not None:
        data["action"] = _check_action(action)
    if match is not None:
        data["match"] = match
    if set_clauses is not None:
        data["set"] = set_clauses
    if exit_action is not None:
        data["exit-action"] = exit_action
    if call is not None:
        data["call"] = _check_sdn_id(call, "route-map")
    if not data and not delete:
        raise ProximoError("route_map_entry_update requires at least one field to set or delete")
    if delete:
        data["delete"] = _sdn_csv(delete)
    if digest is not None:
        data["digest"] = digest
    if lock_token is not None:
        data["lock-token"] = lock_token
    return api._put(f"/cluster/sdn/route-maps/entries/{rid}/entry/{o}", data)


def route_map_entry_delete(api, route_map_id: str, order, lock_token: str | None = None) -> object:
    """Delete a route-map entry (PENDING).
    DELETE /cluster/sdn/route-maps/entries/{route-map-id}/entry/{order}.

    Fact #3/coordinator ruling #5: whether deleting the LAST entry leaves an orphaned empty
    route-map id or PVE cleans it up automatically is UNDOCUMENTED anywhere in this schema —
    Smoke-confirm, no invented semantics asserted here."""
    rid = _check_sdn_id(route_map_id, "route-map")
    o = _check_order(order)
    params: dict = {}
    if lock_token is not None:
        params["lock-token"] = lock_token
    return api._delete(f"/cluster/sdn/route-maps/entries/{rid}/entry/{o}", params)


# ===========================================================================
# Plan factories — prefix lists (container)
# ===========================================================================

def plan_prefix_list_create(prefix_list: str, entries: list[dict] | None = None) -> Plan:
    """Preview creating an SDN prefix list. PURE. RISK_LOW — pending, inert until apply."""
    pl = _check_sdn_id(prefix_list, "prefix-list")
    entries = _check_list_of_dicts(entries, "entries")
    lead = f"stages a PENDING SDN prefix list '{pl}'"
    if entries is not None:
        lead += f", seeded with {len(entries)} entrie(s): {_composite_array_str(entries)}"
    return Plan(
        action="pve_sdn_prefix_list_create", target=f"sdn/prefix-lists/{pl}",
        change=f"create SDN prefix list '{pl}' (pending)", current={},
        blast_radius=_pending_blast(lead),
        risk=RISK_LOW,
        risk_reasons=["SDN object create is a pending config change — inert until apply"],
    )


def plan_prefix_list_update(prefix_list: str, entries: list[dict] | None = None,
                             delete: list | str | None = None) -> Plan:
    """Preview updating an SDN prefix list. PURE. RISK_LOW — pending, inert until apply."""
    pl = _check_sdn_id(prefix_list, "prefix-list")
    entries = _check_list_of_dicts(entries, "entries")
    if entries is None and not delete:
        raise ProximoError("prefix_list_update requires at least one field to set or delete")
    del_keys = delete if isinstance(delete, list) else ([delete] if delete else [])
    parts = ([f"entries={_composite_array_str(entries)}"] if entries is not None else []) + [f"-{k}" for k in del_keys]
    blast = _pending_blast(f"stages a PENDING update to SDN prefix list '{pl}'")
    if entries is not None:
        blast.append(
            "whether 'entries' REPLACES the whole array or MERGES with existing entries by "
            "seq is UNDOCUMENTED in the schema — treat conservatively as a full REPLACE"
        )
    return Plan(
        action="pve_sdn_prefix_list_update", target=f"sdn/prefix-lists/{pl}",
        change=f"update SDN prefix list '{pl}' (pending): {', '.join(parts) or '(none)'}",
        current={},
        blast_radius=blast,
        risk=RISK_LOW,
        risk_reasons=["SDN object update is a pending config change — inert until apply"],
    )


def plan_prefix_list_delete(api, prefix_list: str) -> Plan:
    """Preview deleting an SDN prefix list. Reads current prefix lists (one safe read).
    RISK_MEDIUM — staging a removal an apply would enact."""
    pl = _check_sdn_id(prefix_list, "prefix-list")
    current: dict = {}
    read_failed = False
    try:
        current = next((x for x in (prefix_lists_list(api) or []) if x.get("id") == pl), {})
    except Exception:
        current = {}
        read_failed = True
    blast = [
        f"stages REMOVAL of SDN prefix list '{pl}' (pending)",
        "takes effect on pve_sdn_apply; if the list is live-referenced, applying removes it",
        "referential-integrity refusal (e.g. a fabric's route_filter still naming this list) "
        "is asserted BY ANALOGY to the zone/vnet precedent, NOT independently confirmed "
        "against this endpoint's own schema — Smoke-confirm before relying on it",
        "no NARROW undo at config level: re-create the prefix list (and its entries) to "
        "revert, OR call pve_sdn_rollback to discard EVERY pending SDN edit cluster-wide",
    ]
    if read_failed:
        blast.append("could not read the current SDN prefix list config — prior value UNKNOWN")
    return Plan(
        action="pve_sdn_prefix_list_delete", target=f"sdn/prefix-lists/{pl}",
        change=f"delete SDN prefix list '{pl}' (pending)", current=current,
        blast_radius=blast,
        risk=RISK_MEDIUM,
        risk_reasons=["staging removal of an SDN prefix list — an apply would disrupt "
                      "route filtering that depends on it"],
        complete=not read_failed,
    )


# ===========================================================================
# Plan factories — prefix-list entries
# ===========================================================================

def plan_prefix_list_entry_create(prefix_list: str, action: str, prefix: str,
                                   ge: int | None = None, le: int | None = None,
                                   seq: int | None = None) -> Plan:
    """Preview creating a prefix-list entry. PURE. RISK_LOW."""
    pl = _check_sdn_id(prefix_list, "prefix-list")
    a = _check_action(action)
    p = _check_prefix_cidr(prefix)
    extra: dict = {}
    if ge is not None:
        extra["ge"] = _check_ge_le(ge, "ge")
    if le is not None:
        extra["le"] = _check_ge_le(le, "le")
    if seq is not None:
        extra["seq"] = _check_seq(seq)
    lead = (f"stages a PENDING entry on SDN prefix list '{pl}': action={a}, prefix={p}"
            + (f", {', '.join(_kv_parts(extra))}" if extra else ""))
    return Plan(
        action="pve_sdn_prefix_list_entry_create", target=f"sdn/prefix-lists/{pl}/entries",
        change=f"create entry on SDN prefix list '{pl}' (pending)", current={},
        blast_radius=_pending_blast(lead),
        risk=RISK_LOW,
        risk_reasons=["SDN object create is a pending config change — inert until apply"],
    )


def plan_prefix_list_entry_update(prefix_list: str, entry_id, action: str | None = None,
                                   prefix: str | None = None, ge: int | None = None,
                                   le: int | None = None, seq: int | None = None,
                                   delete: list | str | None = None) -> Plan:
    """Preview updating a prefix-list entry. PURE. RISK_LOW."""
    pl = _check_sdn_id(prefix_list, "prefix-list")
    eid = _check_entry_id(entry_id)
    kw: dict = {}
    if action is not None:
        kw["action"] = _check_action(action)
    if prefix is not None:
        kw["prefix"] = _check_prefix_cidr(prefix)
    if ge is not None:
        kw["ge"] = _check_ge_le(ge, "ge")
    if le is not None:
        kw["le"] = _check_ge_le(le, "le")
    if seq is not None:
        kw["seq"] = _check_seq(seq)
    if not kw and not delete:
        raise ProximoError("prefix_list_entry_update requires at least one field to set or delete")
    del_keys = delete if isinstance(delete, list) else ([delete] if delete else [])
    parts = _kv_parts(kw) + [f"-{k}" for k in del_keys]
    return Plan(
        action="pve_sdn_prefix_list_entry_update",
        target=f"sdn/prefix-lists/{pl}/entries/{eid}",
        change=f"update entry {eid!r} on SDN prefix list '{pl}' (pending): {', '.join(parts) or '(none)'}",
        current={},
        blast_radius=_pending_blast(f"stages a PENDING update to entry {eid!r} on SDN prefix list '{pl}'"),
        risk=RISK_LOW,
        risk_reasons=["SDN object update is a pending config change — inert until apply"],
    )


def plan_prefix_list_entry_delete(api, prefix_list: str, entry_id) -> Plan:
    """Preview deleting a prefix-list entry. CAPTURE: reads the entry (one safe read, may
    fail if entry_id is stale). RISK_MEDIUM."""
    pl = _check_sdn_id(prefix_list, "prefix-list")
    eid = _check_entry_id(entry_id)
    current: dict = {}
    read_failed = False
    try:
        current = prefix_list_entry_get(api, pl, eid)
    except Exception:
        read_failed = True
    blast = [
        f"stages REMOVAL of entry {eid!r} on SDN prefix list '{pl}' (pending)",
        "takes effect on pve_sdn_apply",
        "no NARROW undo at config level: re-create the entry to revert, OR call "
        "pve_sdn_rollback to discard EVERY pending SDN edit cluster-wide",
    ]
    if read_failed:
        blast.append("could not read the current entry — prior value UNKNOWN (entry_id may be stale)")
    return Plan(
        action="pve_sdn_prefix_list_entry_delete",
        target=f"sdn/prefix-lists/{pl}/entries/{eid}",
        change=f"delete entry {eid!r} on SDN prefix list '{pl}' (pending)", current=current,
        blast_radius=blast,
        risk=RISK_MEDIUM,
        risk_reasons=["staging removal of a prefix-list entry — an apply would disrupt route "
                      "filtering that depends on it"],
        complete=not read_failed,
    )


# ===========================================================================
# Plan factories — route-map entries
# ===========================================================================

def plan_route_map_entry_create(route_map_id: str, order, action: str,
                                 match: list[dict] | None = None,
                                 set_clauses: list[dict] | None = None,
                                 exit_action: dict | None = None,
                                 call: str | None = None) -> Plan:
    """Preview creating a route-map entry. PURE. RISK_LOW. Notes fact #3: this may implicitly
    CREATE the route-map itself if `route_map_id` does not already exist."""
    rid = _check_sdn_id(route_map_id, "route-map")
    o = _check_order(order)
    a = _check_action(action)
    match = _check_list_of_dicts(match, "match")
    set_clauses = _check_list_of_dicts(set_clauses, "set_clauses")
    exit_action = _check_dict(exit_action, "exit_action")
    extra: dict = {}
    if match is not None:
        extra["match"] = _composite_array_str(match)
    if set_clauses is not None:
        extra["set"] = _composite_array_str(set_clauses)
    if exit_action is not None:
        extra["exit-action"] = _composite_str(exit_action)
    if call is not None:
        extra["call"] = _check_sdn_id(call, "route-map")
    lead = f"stages a PENDING entry at order={o} on SDN route map '{rid}': action={a}"
    if extra:
        lead += f", {', '.join(_kv_parts(extra))}"
    blast = _pending_blast(lead)
    blast.append(
        f"if route map '{rid}' does not already exist, this call implicitly CREATES it "
        "(fact #3 — no separate container-level create exists on this plane)"
    )
    return Plan(
        action="pve_sdn_route_map_entry_create", target=f"sdn/route-maps/entries/{rid}",
        change=f"create entry at order={o} on SDN route map '{rid}' (pending)", current={},
        blast_radius=blast,
        risk=RISK_LOW,
        risk_reasons=["SDN object create is a pending config change — inert until apply"],
    )


def plan_route_map_entry_update(route_map_id: str, order, action: str | None = None,
                                 match: list[dict] | None = None,
                                 set_clauses: list[dict] | None = None,
                                 exit_action: dict | None = None, call: str | None = None,
                                 delete: list | str | None = None) -> Plan:
    """Preview updating a route-map entry. PURE. RISK_LOW."""
    rid = _check_sdn_id(route_map_id, "route-map")
    o = _check_order(order)
    match = _check_list_of_dicts(match, "match")
    set_clauses = _check_list_of_dicts(set_clauses, "set_clauses")
    exit_action = _check_dict(exit_action, "exit_action")
    kw: dict = {}
    if action is not None:
        kw["action"] = _check_action(action)
    if match is not None:
        kw["match"] = _composite_array_str(match)
    if set_clauses is not None:
        kw["set"] = _composite_array_str(set_clauses)
    if exit_action is not None:
        kw["exit-action"] = _composite_str(exit_action)
    if call is not None:
        kw["call"] = _check_sdn_id(call, "route-map")
    if not kw and not delete:
        raise ProximoError("route_map_entry_update requires at least one field to set or delete")
    del_keys = delete if isinstance(delete, list) else ([delete] if delete else [])
    parts = _kv_parts(kw) + [f"-{k}" for k in del_keys]
    return Plan(
        action="pve_sdn_route_map_entry_update",
        target=f"sdn/route-maps/entries/{rid}/entry/{o}",
        change=f"update entry at order={o} on SDN route map '{rid}' (pending): {', '.join(parts) or '(none)'}",
        current={},
        blast_radius=_pending_blast(f"stages a PENDING update to entry order={o} on SDN route map '{rid}'"),
        risk=RISK_LOW,
        risk_reasons=["SDN object update is a pending config change — inert until apply"],
    )


def plan_route_map_entry_delete(api, route_map_id: str, order) -> Plan:
    """Preview deleting a route-map entry. CAPTURE: reads the entry (one safe read).
    RISK_MEDIUM. Notes fact #3/ruling #5: whether this orphans an empty route-map id (if it
    was the last entry) is UNDOCUMENTED — Smoke-confirm, no invented semantics."""
    rid = _check_sdn_id(route_map_id, "route-map")
    o = _check_order(order)
    current: dict = {}
    read_failed = False
    try:
        current = route_map_entry_get(api, rid, o)
    except Exception:
        read_failed = True
    blast = [
        f"stages REMOVAL of entry order={o} on SDN route map '{rid}' (pending)",
        "takes effect on pve_sdn_apply",
        "if this is the LAST entry on this route-map id, whether PVE leaves an orphaned "
        "empty route-map id or cleans it up automatically is UNDOCUMENTED in the schema — "
        "Smoke-confirm, not asserted either way (coordinator ruling #5)",
        "no NARROW undo at config level: re-create the entry to revert, OR call "
        "pve_sdn_rollback to discard EVERY pending SDN edit cluster-wide",
    ]
    if read_failed:
        blast.append("could not read the current entry — prior value UNKNOWN (may already be gone)")
    return Plan(
        action="pve_sdn_route_map_entry_delete",
        target=f"sdn/route-maps/entries/{rid}/entry/{o}",
        change=f"delete entry at order={o} on SDN route map '{rid}' (pending)", current=current,
        blast_radius=blast,
        risk=RISK_MEDIUM,
        risk_reasons=["staging removal of a route-map entry — an apply would disrupt routing "
                      "policy that depends on it"],
        complete=not read_failed,
    )
