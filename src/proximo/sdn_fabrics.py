"""SDN FABRICS pillar (Wave 7d, full-surface campaign — the FINAL chunk of Wave 7).

Fabric config CRUD + fabric-node sub-family + node-scoped fabric STATUS reads, on the SAME
staged-pending SDN plane as `network.py`'s zone/vnet/subnet CRUD, `sdn_objects.py`'s
controller/dns/ipam CRUD, and `sdn_routing.py`'s prefix-list/route-map CRUD:
  fabrics       -> /cluster/sdn/fabrics/{all,fabric[/{id}],node[/{fabric_id}[/{node_id}]]}
  node status   -> /nodes/{node}/sdn/fabrics/{fabric}/{interfaces,neighbors,routes}

Built AFTER Wave 7e (prefix-lists + route-maps) per the draft's own sequencing note
(`.scratch/sdd/wave-7-draft-decomposition.md` §5): a fabric's `route_filter` names a
prefix-list (`pve_sdn_prefix_list_create`) and its `redistribute[].route-map` /
`route_map_in`/`route_map_out`-style fields name a route-map
(`pve_sdn_route_map_entry_create`) — both already exist by the time this module's docstrings
reference them, rather than describing a forward reference.

Schema truth: `.scratch/api-schemas-2026-07-15/wave7-pve-sdn-schema.json` (49 paths, 90
methods) — all 11 fabric-family paths read in full field-by-field for THIS build, not
assumed from the draft's summary (the draft's own Fact #17 and the campaign's coordinator
ruling block are corroborated below, and in two places corrected/extended where this build's
own field-by-field read found something neither document examined).

Config CRUD (fabric container + fabric-node) is PENDING (staged), same lifecycle as every
other named-object family on this plane: inert until `pve_sdn_apply`, recoverable either
narrowly (a second CRUD call) or broadly via `pve_sdn_rollback` (Wave 7a's UNDO-honesty
upgrade — discards every pending SDN edit cluster-wide). Every create/update/delete plan
factory states both paths, mirroring `sdn_objects.py`'s own `_pending_blast` framing (a fresh,
family-scoped copy lives here rather than importing it — the established per-module
tiny-helper-duplication convention).

Schema-verified facts for THIS build (checked field-by-field, not assumed from the draft):

1. **3 confirmed upstream copy-paste description bugs, all in THIS chunk** (Wave 7 draft
   Fact #15, re-verified here against the raw schema, not merely repeated): `GET
   /cluster/sdn/fabrics/fabric/{id}` says **"Update a fabric"** — it is a plain read (no
   mutation params, returns the full fabric object). `DELETE
   /cluster/sdn/fabrics/fabric/{id}` says **"Add a fabric"** — it deletes (returns `null`,
   only an `id` param, `SDN.Allocate` permission — matches every other delete's shape on this
   plane). `DELETE /cluster/sdn/fabrics/node/{fabric_id}/{node_id}` says **"Add a node"** —
   it deletes (returns `null`, only `fabric_id`+`node_id` params). Trust verb/params/returns
   throughout `fabric_get`/`fabric_delete`/`fabric_node_delete` below — their docstrings do
   NOT copy the upstream prose verbatim (unlike most of this codebase's docstrings, which
   quote upstream text for good reason).
2. **`/cluster/sdn/fabrics/all` vs `/cluster/sdn/fabrics/fabric` vs
   `/cluster/sdn/fabrics/node` vs `/cluster/sdn/fabrics/node/{fabric_id}` — real reads, not
   stubs, genuinely overlapping** (Wave 7 draft Fact #16). `fabrics_all` = `{fabrics: [...full
   fabric objects...], nodes: [...full node objects across EVERY fabric...]}` in ONE call —
   100% reconstructable client-side from `fabrics_list` + `fabric_nodes_list_all` (2 calls).
   `fabric_nodes_list_all` (bare `/node`) lists nodes ACROSS EVERY fabric — NOT scoped to
   one, genuinely different from `fabric_nodes_list(fabric_id)` (which filters, not just
   reshapes) and reconstructable from N calls to the scoped form (one per fabric — genuinely
   more expensive, not just cosmetic). **Coordinator ruling #1 (binding): BUILD both
   aggregates** (`pve_sdn_fabrics_all`, `pve_sdn_fabric_nodes_list_all`) despite the
   redundancy — cheap reads, real N+1-avoidance value; documented here, not silently built as
   if non-redundant.
3. **Node-scoped fabric STATUS reads split cleanly on the wire-learned/local-config line —
   verified per-field against the raw schema, NOT defaulted to "all adversarial."**

   STRIKE-AND-CORRECT NOTE (post-review, 2026-07-17): an earlier version of this fact cited
   "the campaign doc's own Wave 7d chunk listing" as independent corroboration for the
   `interfaces` classification below. That citation was FABRICATED — no such section exists
   in `.scratch/2026-07-15-full-surface-campaign.md`; the quoted text ("§7d — Fabrics" +
   a per-tool listing) exists only in `.scratch/sdd/wave-7-draft-decomposition.md:405-412`,
   already cited separately as "the pinned draft," and the campaign doc's actual Wave 7 ruling
   block (lines 782-784) said the OPPOSITE at the time — it grouped
   "fabric neighbors/interfaces/routes" together as ADVERSARIAL. The correct classification
   was reached only via a **COORDINATOR RE-RULING** (`.scratch/2026-07-15-full-surface-
   campaign.md` lines 853-864, dated 2026-07-17, binding, supersedes the ruling block's coarse
   line): `pve_sdn_fabric_status_interfaces` = REVIEWED_TRUSTED, on the basis that
   `interfaces` returns ONLY locally-authored fields (kernel/FRR local interface state, no
   peer-announced or wire-learned content), unlike `neighbors`/`routes` (explicitly
   "as returned by FRR" peer content, which stay ADVERSARIAL) — the original ruling-block line
   was summarization coarseness, corrected per the draft's own Fact #17. The re-ruling is
   explicit that the classification survives on the schema evidence; the fabricated-citation
   practice used to reach it the first time does not (rulings change by written re-ruling with
   evidence, never by invented authority). The real basis for the classification below is: the
   schema's local-only `{name, state, type}` return shape (verified field-by-field, see below)
   PLUS the 2026-07-17 coordinator re-ruling cited above — not any "chunk listing."
   - `interfaces` (`GET /nodes/{node}/sdn/fabrics/{fabric}/interfaces`): returns
     `{name, state, type}` per entry — "the name of the network interface," "the current
     state of the interface," "the type of this interface in the fabric (e.g.
     Point-to-Point, Broadcast, ..)." Every field describes the FABRIC'S OWN locally-rendered
     network interface — no field is documented as peer-announced, FRR-reported, or
     otherwise wire-learned. **REVIEWED_TRUSTED.**
   - `neighbors` (`GET .../neighbors`): returns `{neighbor, status, uptime}` — `neighbor` is
     "the IP or hostname of the neighbor" (the peer's own self-announced identity string);
     `status`/`uptime` are both explicitly documented **"as returned by FRR"** — the routing
     daemon's report of what a remote peer said. **ADVERSARIAL**: a compromised/malicious
     peer controls these bytes, the same wire-learned-content channel that made
     `pve_sdn_zone_ip_vrf`/`pve_ceph_metadata` ADVERSARIAL.
   - `routes` (`GET .../routes`): returns `{route, via}` — `route` is the destination CIDR
     (locally computed from the fabric's own configuration); `via` is "a list of nexthops for
     that route," each one "the IP address of the nexthop" — nexthops are injected by
     whatever peer announces them over the running routing protocol. **ADVERSARIAL** (the
     `via` field alone is the wire-learned-content channel; `route` riding alongside it in the
     same array entry does not dilute that).
   No plan factory in this module CAPTURES from `fabric_status_neighbors`/
   `fabric_status_routes` (they are pure reads with no plan-embedded lookup), so
   `taint.capture_adversarial_current` is not needed here — `_audited()`'s own marking (keyed
   off `taint.ADVERSARIAL_TOOLS`) is sufficient, exactly like `pve_sdn_zone_ip_vrf`/
   `pve_sdn_vnet_mac_vrf` in Wave 7a.
4. **`pending`/`running` exist on every LIST/aggregate fabric endpoint, but on NEITHER
   single-object GET — the OPPOSITE split from zone/vnet/subnet/controller.** `GET
   /cluster/sdn/fabrics/all`, `GET /cluster/sdn/fabrics/fabric` (bare), `GET
   /cluster/sdn/fabrics/node` (bare), and `GET /cluster/sdn/fabrics/node/{fabric_id}` all
   accept optional `pending`/`running` booleans (schema-verified, all four). `GET
   /cluster/sdn/fabrics/fabric/{id}` and `GET /cluster/sdn/fabrics/node/{fabric_id}/{node_id}`
   accept ONLY their path-identity params — zero query params on either (schema-verified).
   `network.py`'s own zone/vnet/subnet family made the OPPOSITE choice (exposing
   pending/running on the single-object GETs, not the bare lists — `sdn_zones_list`/
   `sdn_vnets_list` take no params at all "despite the schema plausibly supporting filters
   there too," per `network.py`'s own module docstring). Here that asymmetry is NOT a module
   choice — it is a genuine schema absence on the fabric single-object GETs. Exposed
   accordingly: `pending`/`running` on `fabrics_all`/`fabrics_list`/`fabric_nodes_list_all`/
   `fabric_nodes_list`; NOT on `fabric_get`/`fabric_node_get`.
5. **`digest` on CREATE is a THIRD exception on this SDN plane, not the two the Wave 7 draft
   named.** Fact #9 (draft) names fabric CREATE and prefix-list CREATE as the only two
   exceptions to "digest never on create." Checked field-by-field for THIS build: `POST
   /cluster/sdn/fabrics/node/{fabric_id}` (fabric-**node** create) ALSO accepts an optional
   `digest` — a THIRD exception the draft's own Fact #9 did not examine (it only looked at
   the fabric CONTAINER's create, not the fabric-node sub-family's). Documented here as a
   correction, not silently folded into the draft's "two exceptions" framing.
6. **`fabric`/`fabric-node` DELETE accept NEITHER `digest` NOR `lock-token` — the only
   delete family on the WHOLE SDN plane with zero optimistic-lock support of any kind.**
   `DELETE /cluster/sdn/fabrics/fabric/{id}` declares only `id`; `DELETE
   /cluster/sdn/fabrics/node/{fabric_id}/{node_id}` declares only `fabric_id`+`node_id` —
   checked field-by-field, zero hits for either `digest` or `lock-token` on either endpoint.
   Every OTHER delete on this plane (zone/vnet/subnet/controller/dns/ipam/prefix-list/
   route-map-entry) accepts an optional `lock-token` at minimum. `fabric_delete`/
   `fabric_node_delete` below therefore take NO `lock_token` parameter at all — inventing one
   this schema does not support would silently imply a capability that does not exist.
7. **`fabric`/`fabric-node` UPDATE (PUT) require restating `protocol` in the body — a real
   divergence from controller/dns/ipam's own "type is immutable, entirely ABSENT from PUT"
   convention (`sdn_objects.py` Fact #1).** Both `PUT /cluster/sdn/fabrics/fabric/{id}` and
   `PUT /cluster/sdn/fabrics/node/{fabric_id}/{node_id}` list `protocol` with NO `optional`
   flag (required, by this schema's own marking convention — same convention `sdn_objects.py`
   Fact #1 already established). Unlike the object's own path-derivable identity field (`id`/
   `fabric_id`/`node_id` — also marked required-no-optional-flag, but genuinely derivable
   from the URL and, per the ALREADY-SHIPPED zone/vnet/subnet precedent, never re-sent in the
   body: `network.py`'s `sdn_zone_update` does not send `zone` in its PUT body either, despite
   `PUT /cluster/sdn/zones/{zone}`'s own `zone` param carrying the identical
   required-no-optional-flag shape — verified fresh against that endpoint's schema for this
   comparison), `protocol` has NO path representation at all — there is nowhere else PVE
   could get it from, so it must be resent in the body on every update. Plausible engineering
   reason: the OTHER protocol-conditional optional fields (`area`/`csnp_interval`/
   `interfaces`/...) are validated via `type-property: "protocol"`, so PVE needs the caller to
   restate which protocol those fields belong to even when protocol itself isn't changing.
   Whether supplying a DIFFERENT protocol than the fabric's/node's CURRENT one is accepted (a
   genuine re-type) or rejected is NOT stated anywhere in the schema — `fabric_update`/
   `fabric_node_update` below always forward whatever `protocol` value the caller passes,
   verbatim; never assumed unchanged, never validated against a prior read.
8. **`redistribute` (fabric create AND update) is typed REQUIRED at the top level despite
   being protocol-conditional in the response schema** (Wave 7 draft Fact #8, re-verified
   here; MINOR #2 fix, post-review 2026-07-17 — the UPDATE half was schema-verified but not
   originally surfaced in `plan_fabric_update`'s own blast radius). The response's own
   `redistribute` is `oneOf`-gated by `instance-types: [ospf]` / `instance-types: [bgp]` — it
   has no stated meaning for `openfabric`/`wireguard` (neither protocol's own PUT `delete`
   enum lists it as a settable/unsettable key). Yet BOTH the CREATE param schema AND the PUT
   param schema mark it required for every protocol, byte-for-byte the same marking.
   **Coordinator ruling #6 (binding): Smoke-confirm** — untested whether PVE actually rejects
   an openfabric/wireguard create OR update that omits `redistribute`, silently accepts an
   implicit `[]`, or has an undocumented default. `fabric_create`/`fabric_update` below do NOT
   invent a default; `redistribute` (like every other protocol-conditional field) flows
   through the generic `options` passthrough (fact #9) — omitting it simply omits the key
   from the wire payload, and BOTH plan factories state the Smoke-confirm uncertainty
   explicitly whenever a non-ospf/bgp protocol create/update omits it.
9. **Generic `options: dict` passthrough for BOTH fabric and fabric-node CREATE/UPDATE** —
   Wave 7 draft Fact #10 explicitly names "fabrics (openfabric/ospf/wireguard/bgp)" as one of
   the families that should follow this idiom (alongside controllers, which `sdn_objects.py`
   already does), rather than hand-enumerating ~8 protocol-conditional fields per object
   (fabric: `area`/`csnp_interval`/`hello_interval`/`ip6_prefix`/`ip_prefix`/
   `persistent_keepalive`/`redistribute`/`route_filter`; fabric-node:
   `allowed_ips`/`endpoint`/`interfaces`/`ip`/`ip6`/`peers`/`public_key`/`role`) across 4
   protocols with no formal `requires` constraint anywhere in this schema (Wave 7 draft Fact
   #10's own root justification). Structural identity fields (`id`/`fabric_id`/`node_id`/
   `protocol`/`delete`/`digest`/`lock-token`) are reserved keys, blocked from `options` the
   same way `_check_controller_options`/`_check_sdn_options` already block their own
   families' structural keys — smuggling one would silently override the explicit positional
   argument (options is spread AFTER the explicit fields in the outgoing dict).

Validators: fabric/fabric-node ids reuse `network.py`'s existing `_check_sdn_id`
(alnum/_/- up to 64 chars, start with alnum) — a strict SUPERSET of the fabric id's own
schema pattern (`[a-zA-Z0-9][a-zA-Z0-9-]{0,6}[a-zA-Z0-9]`, 2-8 chars, no underscore) — the
same "the existing looser validator already accepts every legal input, PVE is the real gate"
reasoning `sdn_objects.py`/`sdn_routing.py` already established for their own object ids. A
node identifier (schema format `pve-node`, the SAME hostname shape `backends.py`'s
`_check_node` already validates) gets a fresh, PATH-safety-focused wrapper
(`_check_fabric_node_id`) since `_check_node` itself treats `None` as "use the configured
default node" — semantically wrong here, where a fabric node_id is always a REQUIRED
identifier of a (possibly different) cluster member, never an optional default. `delete`
(settings-to-unset) reuses `network.py`'s `_sdn_csv`.

Taint: `fabrics_all`/`fabrics_list`/`fabric_get`/`fabric_nodes_list_all`/
`fabric_nodes_list`/`fabric_node_get`/`fabric_status_interfaces` are REVIEWED_TRUSTED
(operator-authored fabric CONFIG, or — for `interfaces` — the fabric's own locally-rendered
state; see fact #3 above for the full per-field argument, including the deliberate divergence
from this chunk's own dispatch-prompt summary). `fabric_status_neighbors`/
`fabric_status_routes` are ADVERSARIAL (fact #3). All 6 mutations
(fabric_create/update/delete, fabric_node_create/update/delete) return `null`
(schema-verified field-by-field — matches Wave 7 draft Fact #2's "almost entirely
synchronous-null" plane characterization, extended here to every one of this chunk's own 6
mutations) — no content channel to classify either way, REVIEWED_TRUSTED regardless.

Risk ratings (coordinator ruling, `.scratch/2026-07-15-full-surface-campaign.md` § Wave 7
ruling block + `.scratch/sdd/wave-7-draft-decomposition.md` §3): fabric/fabric-node
create+update = LOW (pending, inert until apply — mirrors zone/vnet/subnet/controller/dns/
ipam/prefix-list create+update exactly); fabric/fabric-node delete = MEDIUM (staging a
removal an apply would enact). Referential-integrity claims ("PVE refuses to delete a fabric
still named by a zone's own `fabric` field," "PVE refuses to delete a fabric node still
referenced elsewhere") are asserted BY ANALOGY ONLY, Smoke-confirm labeled per the
coordinator's ruling #4 — this schema's own terse delete descriptions (once corrected for the
copy-paste bug, fact #1) do not themselves state a refusal-on-reference behavior.

*** THE LOCK-TOKEN RULING (MAJOR #2, post-review strike-and-correct, 2026-07-17): `lock-token`
(the live SDN cluster-lock capability secret minted by `pve_sdn_lock_acquire` — see
`network.py`'s own "Lock-token handling" section, "a CAPABILITY HANDLE, not a password") is
schema-documented in the RESPONSE of ALL SIX fabric/fabric-node config-read wire functions
below (`fabrics_all`, `fabrics_list`, `fabric_get`, `fabric_nodes_list_all`,
`fabric_nodes_list`, `fabric_node_get` — verified field-by-field against the raw schema;
zone/vnet/controller GET responses do NOT carry this field — specific to the fabric family).
The original build shipped these six reads unfiltered (`api._get(path) or {}/[]`, raw
passthrough) — an undisclosed leak path a read-only-scoped caller (e.g. `SDN.Audit` without
`SDN.Allocate`) could use to obtain another operator's live lock token and defeat the lock
primitive entirely (release it out from under them, or ride it into their own mutation's
`lock_token` param). Per this wave's own binding "Spine items" ruling ("DNS key / IPAM token =
secrets, redact defensively incl. schema-undocumented GET echoes — the 5b influxdb lesson")
this is a STRONGER case than the ruling was written for: the field isn't merely
schema-undocumented, it's explicitly named and described.

THE FIX, AS SHIPPED: `lock-token` is REMOVED entirely (not masked — a plain read has no
legitimate reason to echo a capability-bearing token at all) at the READ layer, in all six
wire functions below, via `_strip_lock_token`/`_strip_lock_token_rows` — mirrors
`sdn_objects.py`'s `_strip_secrets_at_read` mechanism exactly, applied per-row for the four
functions that return lists (and per-row within EACH of `fabrics_all`'s two nested lists).

ONE layer covers this end to end, not two: unlike `sdn_objects.py`'s `key`/`token` ruling
(which needs a SECOND `_redact_secrets` layer because `dns_create`/`ipam_create`'s plan text
displays FRESH caller-supplied input that never passes through a read), fabric/fabric-node's
own create/update plan factories (`plan_fabric_create`/`_update`/`plan_fabric_node_create`/
`_update`) never accept a `lock_token` parameter at all — it is reserved out of `options`
(`_FABRIC_RESERVED`/`_FABRIC_NODE_RESERVED`) and the plan factories' own signatures don't take
it — so there is no fresh-input display path to protect. The only CAPTURE readers on this
module are `plan_fabric_delete` (via `fabrics_list`) and `plan_fabric_node_delete` (via
`fabric_nodes_list`) — both call the real, already-stripped wire functions directly, so
`Plan.current` inherits the strip for free; no second redaction layer is needed. ***
"""

from __future__ import annotations

from .backends import ProximoError, _check_node
from .network import _check_sdn_id, _sdn_csv, _sdn_get_query
from .planning import RISK_LOW, RISK_MEDIUM, Plan

# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

_VALID_FABRIC_PROTOCOLS = frozenset({"openfabric", "ospf", "wireguard", "bgp"})
# Only these two protocols give `redistribute` a stated meaning (fact #8) — used to decide
# whether a create's plan factory owes a Smoke-confirm note about omitting it.
_REDISTRIBUTE_PROTOCOLS = frozenset({"ospf", "bgp"})


def _check_protocol(value: str) -> str:
    v = str(value).strip()
    if v not in _VALID_FABRIC_PROTOCOLS:
        raise ProximoError(
            f"invalid SDN fabric protocol: {value!r} (expected one of "
            f"{sorted(_VALID_FABRIC_PROTOCOLS)})"
        )
    return v


def _check_fabric_node_id(value) -> str:
    """Validate a fabric NODE identifier (schema format 'pve-node' — the same hostname-shaped
    charset `backends.py`'s `_check_node` already validates). A fresh wrapper, not a direct
    reuse of `_check_node` itself: that function treats `None` as "skip the check, use the
    configured default node" — semantically wrong here, where a fabric node_id is always a
    REQUIRED identifier (of a cluster member that may or may not be the node Proximo is
    talking to), never an optional default."""
    if value is None or str(value) == "":
        raise ProximoError("fabric node_id is required")
    v = str(value)
    _check_node(v)
    return v


# Reserved keys for the fabric `options` bag (generic passthrough, fact #9) — "id" (not
# "fabric": this family's own wire body key, unlike controller/dns/ipam/zone/vnet, which all
# name their identity field after the object type itself).
_FABRIC_RESERVED = frozenset({"id", "protocol", "delete", "digest", "lock-token", "lock_token"})
# Reserved keys for the fabric-NODE `options` bag — a fresh set (the identity fields here are
# "fabric_id"/"node_id"/"protocol", not "fabric").
_FABRIC_NODE_RESERVED = frozenset(
    {"fabric_id", "node_id", "protocol", "delete", "digest", "lock-token", "lock_token"}
)


def _check_fabric_options(options: dict | None) -> None:
    bad = _FABRIC_RESERVED & set(options or {})
    if bad:
        raise ProximoError(
            f"reserved key(s) {sorted(bad)} cannot be passed inside options — use the "
            "dedicated fabric/protocol/delete/digest/lock_token parameters instead"
        )


def _check_fabric_node_options(options: dict | None) -> None:
    bad = _FABRIC_NODE_RESERVED & set(options or {})
    if bad:
        raise ProximoError(
            f"reserved key(s) {sorted(bad)} cannot be passed inside options — use the "
            "dedicated fabric_id/node_id/protocol/delete/digest/lock_token parameters instead"
        )


_LOCK_TOKEN_KEY = "lock-token"  # noqa: S105 (a dict key name, not a credential value)


def _strip_lock_token(d: dict) -> dict:
    """Read-layer strip for a single fabric/fabric-node object (THE LOCK-TOKEN RULING, module
    docstring): removes `lock-token` entirely — a plain read has no legitimate reason to echo
    the live SDN cluster-lock capability secret. Mirrors `sdn_objects.py`'s
    `_strip_secrets_at_read` mechanism (plain dict-comprehension exclusion, not masked)."""
    return {k: v for k, v in d.items() if k != _LOCK_TOKEN_KEY}


def _strip_lock_token_rows(rows: list) -> list:
    """Same strip, applied per-row to a list of fabric/fabric-node objects."""
    return [_strip_lock_token(r) for r in rows]


def _pending_blast(lead: str) -> list[str]:
    """Same shape as network.py's `_sdn_pending_blast` / sdn_objects.py's / sdn_routing.py's
    own per-family copies (the exact wording differs by object type)."""
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


# ===========================================================================
# FABRICS (container)
# ===========================================================================

def fabrics_all(api, pending: bool | None = None, running: bool | None = None) -> dict:
    """AGGREGATE read: every fabric's config AND every node across every fabric, in ONE call.
    GET /cluster/sdn/fabrics/all -> {fabrics: [...], nodes: [...]}.

    100% reconstructable from fabrics_list() + fabric_nodes_list_all() (2 calls) — built
    anyway per coordinator ruling #1 (cheap read, real N+1-avoidance value; fact #2).
    `lock-token` is STRIPPED from every row of both nested lists (THE LOCK-TOKEN RULING,
    module docstring — MAJOR #2 fix). REVIEWED_TRUSTED (operator-authored fabric/node
    config)."""
    path = f"/cluster/sdn/fabrics/all{_sdn_get_query(pending, running)}"
    data = api._get(path) or {}
    if not data:
        return data
    out = dict(data)
    out["fabrics"] = _strip_lock_token_rows(out.get("fabrics") or [])
    out["nodes"] = _strip_lock_token_rows(out.get("nodes") or [])
    return out


def fabrics_list(api, pending: bool | None = None, running: bool | None = None) -> list[dict]:
    """List SDN fabrics (cluster-scoped, full objects — not a directory stub).
    GET /cluster/sdn/fabrics/fabric. `lock-token` is STRIPPED per-row (THE LOCK-TOKEN RULING,
    module docstring — MAJOR #2 fix). REVIEWED_TRUSTED."""
    path = f"/cluster/sdn/fabrics/fabric{_sdn_get_query(pending, running)}"
    return _strip_lock_token_rows(api._get(path) or [])


def fabric_get(api, fabric: str) -> dict:
    """Read a single SDN fabric's configuration. GET /cluster/sdn/fabrics/fabric/{id}.

    Upstream's own description says "Update a fabric" — a confirmed copy-paste bug (fact #1);
    this is a plain read (no mutation params, returns the full fabric object). No
    pending/running on this endpoint (fact #4 — schema-verified absence, unlike the LIST
    tools above). `lock-token` is STRIPPED (THE LOCK-TOKEN RULING, module docstring — MAJOR #2
    fix). REVIEWED_TRUSTED."""
    f = _check_sdn_id(fabric, "fabric")
    return _strip_lock_token(api._get(f"/cluster/sdn/fabrics/fabric/{f}") or {})


def fabric_create(api, fabric: str, protocol: str, options: dict | None = None,
                   digest: str | None = None, lock_token: str | None = None) -> object:
    """Create an SDN fabric (PENDING). POST /cluster/sdn/fabrics/fabric
    {id, protocol, ...options, digest?, lock-token?}.

    `protocol` is openfabric/ospf/wireguard/bgp; `options` carries the protocol-conditional
    fields (area, csnp_interval, hello_interval, ip_prefix, ip6_prefix, persistent_keepalive,
    redistribute, route_filter — fact #9, generic passthrough, PVE validates per protocol
    server-side). `redistribute` is schema-REQUIRED at the top level for every protocol
    despite only having a stated meaning for ospf/bgp (fact #8) — omitting it for
    openfabric/wireguard is UNTESTED (coordinator ruling #6, Smoke-confirm); this function
    does not invent a default. `digest` IS accepted on fabric CREATE — one of THREE
    exceptions on the whole SDN plane to the "digest never on create" convention (fact #5;
    the others are prefix-list container create and fabric-NODE create below). Inert until
    pve_sdn_apply."""
    f = _check_sdn_id(fabric, "fabric")
    p = _check_protocol(protocol)
    _check_fabric_options(options)
    data: dict = {"id": f, "protocol": p, **(options or {})}
    if digest is not None:
        data["digest"] = digest
    if lock_token is not None:
        data["lock-token"] = lock_token
    return api._post("/cluster/sdn/fabrics/fabric", data)


def fabric_update(api, fabric: str, protocol: str, options: dict | None = None,
                   delete: list | str | None = None, digest: str | None = None,
                   lock_token: str | None = None) -> object:
    """Update an SDN fabric (PENDING). PUT /cluster/sdn/fabrics/fabric/{id}.

    `protocol` is REQUIRED here too (fact #7) — a real divergence from controller/dns/ipam,
    where `type` is entirely ABSENT from the PUT schema (immutable). Whether passing a
    DIFFERENT protocol than the fabric's current one is accepted (a re-type) or rejected is
    UNDOCUMENTED; whatever value is passed is forwarded verbatim, never assumed unchanged.
    Requires >=1 option to set or delete (protocol alone restates the type, it is not itself
    a change)."""
    f = _check_sdn_id(fabric, "fabric")
    p = _check_protocol(protocol)
    _check_fabric_options(options)
    if not options and not delete:
        raise ProximoError("fabric_update requires at least one option to set or delete")
    data: dict = {"protocol": p, **(options or {})}
    if delete:
        data["delete"] = _sdn_csv(delete)
    if digest is not None:
        data["digest"] = digest
    if lock_token is not None:
        data["lock-token"] = lock_token
    return api._put(f"/cluster/sdn/fabrics/fabric/{f}", data)


def fabric_delete(api, fabric: str) -> object:
    """Delete an SDN fabric (PENDING). DELETE /cluster/sdn/fabrics/fabric/{id}.

    Upstream's own description says "Add a fabric" — a confirmed copy-paste bug (fact #1);
    this deletes. NO `digest` and NO `lock-token` accepted on this endpoint at all
    (schema-verified: only `id` — fact #6), unlike every other delete on this SDN plane.
    Referential-integrity refusal (e.g. an EVPN zone's own `fabric` field still naming this
    fabric) is asserted BY ANALOGY only — Smoke-confirm."""
    f = _check_sdn_id(fabric, "fabric")
    return api._delete(f"/cluster/sdn/fabrics/fabric/{f}")


# ===========================================================================
# FABRIC NODES
# ===========================================================================

def fabric_nodes_list_all(api, pending: bool | None = None,
                           running: bool | None = None) -> list[dict]:
    """List EVERY node across EVERY fabric in one call (NOT scoped to one fabric — the `nodes`
    half of fabrics_all(), standalone). GET /cluster/sdn/fabrics/node.

    Genuinely different from fabric_nodes_list(fabric_id) (which filters, not just reshapes —
    fact #2); reconstructable from N calls to the scoped form (one per fabric — more
    expensive, not just cosmetic). Built per coordinator ruling #1. `lock-token` is STRIPPED
    per-row (THE LOCK-TOKEN RULING, module docstring — MAJOR #2 fix). REVIEWED_TRUSTED."""
    path = f"/cluster/sdn/fabrics/node{_sdn_get_query(pending, running)}"
    return _strip_lock_token_rows(api._get(path) or [])


def fabric_nodes_list(api, fabric_id: str, pending: bool | None = None,
                       running: bool | None = None) -> list[dict]:
    """List the nodes belonging to ONE fabric. GET /cluster/sdn/fabrics/node/{fabric_id}.
    `lock-token` is STRIPPED per-row (THE LOCK-TOKEN RULING, module docstring — MAJOR #2 fix).
    REVIEWED_TRUSTED."""
    fid = _check_sdn_id(fabric_id, "fabric")
    path = f"/cluster/sdn/fabrics/node/{fid}{_sdn_get_query(pending, running)}"
    return _strip_lock_token_rows(api._get(path) or [])


def fabric_node_get(api, fabric_id: str, node_id: str) -> dict:
    """Read a single fabric node's configuration.
    GET /cluster/sdn/fabrics/node/{fabric_id}/{node_id}.

    No pending/running on this endpoint (fact #4 — schema-verified absence, unlike the LIST
    tools above). `lock-token` is STRIPPED (THE LOCK-TOKEN RULING, module docstring — MAJOR #2
    fix). REVIEWED_TRUSTED."""
    fid = _check_sdn_id(fabric_id, "fabric")
    nid = _check_fabric_node_id(node_id)
    return _strip_lock_token(api._get(f"/cluster/sdn/fabrics/node/{fid}/{nid}") or {})


def fabric_node_create(api, fabric_id: str, node_id: str, protocol: str,
                        options: dict | None = None, digest: str | None = None,
                        lock_token: str | None = None) -> object:
    """Add a node to an SDN fabric (PENDING). POST /cluster/sdn/fabrics/node/{fabric_id}
    {node_id, protocol, ...options, digest?, lock-token?}.

    `fabric_id` is path-derivable (PVE reads it from the URL — mirrors the ALREADY-SHIPPED
    zone/vnet/subnet precedent of never re-sending a path-matched identifier in the body,
    even though this schema, like theirs, marks it required-no-optional-flag too — fact #7);
    only `node_id` and `protocol` are sent in the body alongside options. `options` carries
    the protocol-conditional fields (interfaces, ip, ip6, peers, allowed_ips, endpoint,
    public_key, role — fact #9, generic passthrough). `digest` IS accepted here — a THIRD
    exception on this plane's "digest never on create" convention, one the Wave 7 draft's own
    Fact #9 did not examine (fact #5). Inert until pve_sdn_apply."""
    fid = _check_sdn_id(fabric_id, "fabric")
    nid = _check_fabric_node_id(node_id)
    p = _check_protocol(protocol)
    _check_fabric_node_options(options)
    data: dict = {"node_id": nid, "protocol": p, **(options or {})}
    if digest is not None:
        data["digest"] = digest
    if lock_token is not None:
        data["lock-token"] = lock_token
    return api._post(f"/cluster/sdn/fabrics/node/{fid}", data)


def fabric_node_update(api, fabric_id: str, node_id: str, protocol: str,
                        options: dict | None = None, delete: list | str | None = None,
                        digest: str | None = None, lock_token: str | None = None) -> object:
    """Update a fabric node (PENDING). PUT /cluster/sdn/fabrics/node/{fabric_id}/{node_id}.

    `protocol` is REQUIRED here too (fact #7, the same rule as fabric_update). `fabric_id`/
    `node_id` are path-derivable, never re-sent in the body. Requires >=1 option to set or
    delete."""
    fid = _check_sdn_id(fabric_id, "fabric")
    nid = _check_fabric_node_id(node_id)
    p = _check_protocol(protocol)
    _check_fabric_node_options(options)
    if not options and not delete:
        raise ProximoError("fabric_node_update requires at least one option to set or delete")
    data: dict = {"protocol": p, **(options or {})}
    if delete:
        data["delete"] = _sdn_csv(delete)
    if digest is not None:
        data["digest"] = digest
    if lock_token is not None:
        data["lock-token"] = lock_token
    return api._put(f"/cluster/sdn/fabrics/node/{fid}/{nid}", data)


def fabric_node_delete(api, fabric_id: str, node_id: str) -> object:
    """Remove a node from an SDN fabric (PENDING).
    DELETE /cluster/sdn/fabrics/node/{fabric_id}/{node_id}.

    Upstream's own description says "Add a node" — a confirmed copy-paste bug (fact #1); this
    deletes. NO `digest` and NO `lock-token` accepted on this endpoint at all
    (schema-verified: only `fabric_id`+`node_id` — fact #6). Referential-integrity refusal is
    asserted BY ANALOGY only — Smoke-confirm."""
    fid = _check_sdn_id(fabric_id, "fabric")
    nid = _check_fabric_node_id(node_id)
    return api._delete(f"/cluster/sdn/fabrics/node/{fid}/{nid}")


# ===========================================================================
# NODE-SCOPED FABRIC STATUS (read-only)
# ===========================================================================

def fabric_status_interfaces(api, fabric: str, node: str | None = None) -> list[dict]:
    """Get all interfaces for a fabric on one node. GET /nodes/{node}/sdn/fabrics/{fabric}/interfaces.

    Returns {name, state, type} per entry — the fabric's OWN locally-rendered network
    interfaces (name/state/interface-type). REVIEWED_TRUSTED: every field describes local,
    not peer-controlled, state (fact #3) — a deliberate divergence from this chunk's own
    dispatch-prompt summary. Basis, on the record (STRIKE-AND-CORRECT: an earlier version of
    this docstring cited "the pinned draft/campaign rulings, both of which agree" — the
    campaign doc's ruling block did NOT agree at build time, and the citation naming a
    "campaign doc Wave 7d chunk listing" was fabricated, see fact #3 above): the schema's
    local-only {name, state, type} return shape (verified field-by-field) PLUS the
    2026-07-17 COORDINATOR RE-RULING (`.scratch/2026-07-15-full-surface-campaign.md` lines
    853-864, binding)."""
    _check_node(node)
    n = node or api.config.node
    f = _check_sdn_id(fabric, "fabric")
    return api._get(f"/nodes/{n}/sdn/fabrics/{f}/interfaces") or []


def fabric_status_neighbors(api, fabric: str, node: str | None = None) -> list[dict]:
    """Get all neighbors for a fabric on one node. GET /nodes/{node}/sdn/fabrics/{fabric}/neighbors.

    ADVERSARIAL: `neighbor` is the peer's own self-announced IP/hostname; `status`/`uptime`
    are explicitly documented "as returned by FRR" — a compromised peer controls these bytes
    (fact #3)."""
    _check_node(node)
    n = node or api.config.node
    f = _check_sdn_id(fabric, "fabric")
    return api._get(f"/nodes/{n}/sdn/fabrics/{f}/neighbors") or []


def fabric_status_routes(api, fabric: str, node: str | None = None) -> list[dict]:
    """Get all routes for a fabric on one node. GET /nodes/{node}/sdn/fabrics/{fabric}/routes.

    ADVERSARIAL: `via` (the nexthop list) is injected by whatever peer announces it over the
    running routing protocol — the same wire-learned-content channel as `pve_sdn_zone_ip_vrf`
    (fact #3)."""
    _check_node(node)
    n = node or api.config.node
    f = _check_sdn_id(fabric, "fabric")
    return api._get(f"/nodes/{n}/sdn/fabrics/{f}/routes") or []


# ===========================================================================
# Plan factories — fabrics (container)
# ===========================================================================

def plan_fabric_create(fabric: str, protocol: str, options: dict | None = None) -> Plan:
    """Preview creating an SDN fabric. PURE. RISK_LOW — pending, inert until apply."""
    f = _check_sdn_id(fabric, "fabric")
    p = _check_protocol(protocol)
    _check_fabric_options(options)
    lead = f"stages a PENDING SDN fabric '{f}' (protocol={p})"
    if options:
        lead += f", options: {', '.join(_kv_parts(options))}"
    blast = _pending_blast(lead)
    if p not in _REDISTRIBUTE_PROTOCOLS and not (options and "redistribute" in options):
        blast.append(
            "the schema types 'redistribute' REQUIRED at the top level for EVERY protocol, "
            f"though it is only meaningful for ospf/bgp fabrics (protocol={p} here) — "
            "whether PVE actually rejects this create for omitting it, silently accepts an "
            "empty list, or has an undocumented default is UNTESTED (coordinator ruling #6) "
            "— Smoke-confirm before relying on omission being safe"
        )
    return Plan(
        action="pve_sdn_fabric_create", target=f"sdn/fabrics/fabric/{f}",
        change=f"create SDN fabric '{f}' (protocol={p}, pending)", current={},
        blast_radius=blast,
        risk=RISK_LOW, risk_reasons=["SDN object create is a pending config change — inert until apply"],
    )


def plan_fabric_update(fabric: str, protocol: str, options: dict | None = None,
                        delete: list | str | None = None) -> Plan:
    """Preview updating an SDN fabric. PURE. RISK_LOW — pending, inert until apply.

    MINOR #2 fix (post-review, 2026-07-17): the schema types 'redistribute' REQUIRED on
    UPDATE identically to CREATE (byte-for-byte the same marking — coordinator ruling #6,
    fact #8) — the Smoke-confirm note about omitting it for a non-ospf/bgp protocol now fires
    on both plans, not CREATE only."""
    f = _check_sdn_id(fabric, "fabric")
    p = _check_protocol(protocol)
    _check_fabric_options(options)
    if not options and not delete:
        raise ProximoError("fabric_update requires at least one option to set or delete")
    del_keys = delete if isinstance(delete, list) else ([delete] if delete else [])
    parts = _kv_parts(options or {}) + [f"-{k}" for k in del_keys]
    blast = _pending_blast(f"stages a PENDING update to SDN fabric '{f}' (protocol restated as {p})")
    blast.append(
        "the schema requires restating 'protocol' on every update (unlike controller/dns/"
        "ipam, where 'type' is entirely absent from the PUT schema — immutable) — whether "
        "supplying a DIFFERENT protocol than the fabric's current one is accepted (a re-type) "
        "or rejected is UNDOCUMENTED; this call forwards whatever protocol is passed, verbatim"
    )
    if p not in _REDISTRIBUTE_PROTOCOLS and not (options and "redistribute" in options):
        blast.append(
            "the schema types 'redistribute' REQUIRED at the top level for EVERY protocol on "
            f"UPDATE too, identically to CREATE, though it is only meaningful for ospf/bgp "
            f"fabrics (protocol={p} here) — whether PVE actually rejects this update for "
            "omitting it, silently accepts an empty list, or has an undocumented default is "
            "UNTESTED (coordinator ruling #6) — Smoke-confirm before relying on omission "
            "being safe"
        )
    return Plan(
        action="pve_sdn_fabric_update", target=f"sdn/fabrics/fabric/{f}",
        change=f"update SDN fabric '{f}' (pending): {', '.join(parts) or '(none)'}", current={},
        blast_radius=blast,
        risk=RISK_LOW, risk_reasons=["SDN object update is a pending config change — inert until apply"],
    )


def plan_fabric_delete(api, fabric: str) -> Plan:
    """Preview deleting an SDN fabric. Reads current fabrics (one safe read). RISK_MEDIUM —
    staging a removal an apply would enact."""
    f = _check_sdn_id(fabric, "fabric")
    current: dict = {}
    read_failed = False
    try:
        current = next((x for x in (fabrics_list(api) or []) if x.get("id") == f), {})
    except Exception:
        read_failed = True
    blast = [
        f"stages REMOVAL of SDN fabric '{f}' (pending)",
        "takes effect on pve_sdn_apply; if the fabric is live-applied, applying removes its "
        "routing underlay",
        "referential-integrity refusal (e.g. an EVPN zone's own 'fabric' field still naming "
        "this fabric) is asserted BY ANALOGY to the zone/vnet precedent, NOT independently "
        "confirmed against this endpoint's own schema — Smoke-confirm before relying on it",
        "NO digest and NO lock-token accepted on this endpoint at all (schema-verified: only "
        "'id') — unlike every other delete on this SDN plane (zone/vnet/subnet/controller/"
        "dns/ipam/prefix-list/route-map entry all accept an optional lock-token)",
        "no NARROW undo at config level: re-create the fabric to revert, OR call "
        "pve_sdn_rollback to discard EVERY pending SDN edit cluster-wide (broad, "
        "all-or-nothing)",
    ]
    if read_failed:
        blast.append("could not read the current SDN fabric config — prior value UNKNOWN")
    return Plan(
        action="pve_sdn_fabric_delete", target=f"sdn/fabrics/fabric/{f}",
        change=f"delete SDN fabric '{f}' (pending)", current=current,
        blast_radius=blast,
        risk=RISK_MEDIUM,
        risk_reasons=["staging removal of an SDN fabric — an apply would disrupt routing that "
                      "depends on it"],
        complete=not read_failed,
    )


# ===========================================================================
# Plan factories — fabric nodes
# ===========================================================================

def plan_fabric_node_create(fabric_id: str, node_id: str, protocol: str,
                             options: dict | None = None) -> Plan:
    """Preview adding a node to an SDN fabric. PURE. RISK_LOW — pending, inert until apply."""
    fid = _check_sdn_id(fabric_id, "fabric")
    nid = _check_fabric_node_id(node_id)
    p = _check_protocol(protocol)
    _check_fabric_node_options(options)
    lead = f"stages a PENDING SDN fabric node '{nid}' on fabric '{fid}' (protocol={p})"
    if options:
        lead += f", options: {', '.join(_kv_parts(options))}"
    return Plan(
        action="pve_sdn_fabric_node_create", target=f"sdn/fabrics/node/{fid}/{nid}",
        change=f"create SDN fabric node '{nid}' on fabric '{fid}' (protocol={p}, pending)",
        current={},
        blast_radius=_pending_blast(lead),
        risk=RISK_LOW, risk_reasons=["SDN object create is a pending config change — inert until apply"],
    )


def plan_fabric_node_update(fabric_id: str, node_id: str, protocol: str,
                             options: dict | None = None,
                             delete: list | str | None = None) -> Plan:
    """Preview updating a fabric node. PURE. RISK_LOW — pending, inert until apply."""
    fid = _check_sdn_id(fabric_id, "fabric")
    nid = _check_fabric_node_id(node_id)
    p = _check_protocol(protocol)
    _check_fabric_node_options(options)
    if not options and not delete:
        raise ProximoError("fabric_node_update requires at least one option to set or delete")
    del_keys = delete if isinstance(delete, list) else ([delete] if delete else [])
    parts = _kv_parts(options or {}) + [f"-{k}" for k in del_keys]
    blast = _pending_blast(
        f"stages a PENDING update to SDN fabric node '{nid}' on fabric '{fid}' "
        f"(protocol restated as {p})"
    )
    return Plan(
        action="pve_sdn_fabric_node_update", target=f"sdn/fabrics/node/{fid}/{nid}",
        change=(f"update SDN fabric node '{nid}' on fabric '{fid}' (pending): "
                f"{', '.join(parts) or '(none)'}"),
        current={},
        blast_radius=blast,
        risk=RISK_LOW, risk_reasons=["SDN object update is a pending config change — inert until apply"],
    )


def plan_fabric_node_delete(api, fabric_id: str, node_id: str) -> Plan:
    """Preview removing a node from an SDN fabric. Reads current fabric nodes (one safe read,
    scoped to this fabric). RISK_MEDIUM."""
    fid = _check_sdn_id(fabric_id, "fabric")
    nid = _check_fabric_node_id(node_id)
    current: dict = {}
    read_failed = False
    try:
        current = next(
            (x for x in (fabric_nodes_list(api, fid) or []) if x.get("node_id") == nid), {}
        )
    except Exception:
        read_failed = True
    blast = [
        f"stages REMOVAL of SDN fabric node '{nid}' from fabric '{fid}' (pending)",
        "takes effect on pve_sdn_apply; if applied, removes this node's participation in the "
        "fabric's routing underlay",
        "referential-integrity refusal is asserted BY ANALOGY only — Smoke-confirm",
        "NO digest and NO lock-token accepted on this endpoint at all (schema-verified: only "
        "'fabric_id'+'node_id') — unlike every other delete on this SDN plane",
        "no NARROW undo at config level: re-create the node to revert, OR call "
        "pve_sdn_rollback to discard EVERY pending SDN edit cluster-wide",
    ]
    if read_failed:
        blast.append("could not read the current SDN fabric node config — prior value UNKNOWN")
    return Plan(
        action="pve_sdn_fabric_node_delete", target=f"sdn/fabrics/node/{fid}/{nid}",
        change=f"delete SDN fabric node '{nid}' from fabric '{fid}' (pending)", current=current,
        blast_radius=blast,
        risk=RISK_MEDIUM,
        risk_reasons=["staging removal of an SDN fabric node — an apply would disrupt routing "
                      "that depends on it"],
        complete=not read_failed,
    )
