"""SDN vnet-scoped FIREWALL + IP MAPPINGS pillar (Wave 7b, full-surface campaign).

Covers two PVE sub-APIs, both scoped to a single SDN vnet:
  vnet firewall  -> /cluster/sdn/vnets/{vnet}/firewall/{options,rules,rules/{pos}}
  vnet IP maps   -> /cluster/sdn/vnets/{vnet}/ips

*** THE DEFINING FACT (Wave 7 draft decomposition Fact #11, re-verified directly against
`.scratch/api-schemas-2026-07-15/wave7-pve-sdn-schema.json` for this build): the vnet
FIREWALL family is LIVE / IMMEDIATE, NOT staged-pending. Every zone/vnet/subnet object on
the sibling SDN plane (`network.py`) is PENDING until `pve_sdn_apply`; this family's reads
carry NO `pending`/`running` query params at all (checked: zero — unlike every sibling
zone/vnet/subnet/controller/dns/... list on this plane). A confirmed rule/options change
here takes effect on live guest traffic THE INSTANT you confirm, with NO `pve_sdn_apply`
gate to catch a mistake first and NO `pve_sdn_rollback` coverage — `network.py`'s own
module docstring names this family as the ONE explicit exception to its own UNDO-honesty-
upgrade note (rollback only discards the staged-pending config plane; there is no pending
state here for rollback to discard). Every docstring in this module says so plainly. ***

This mirrors the ALREADY-SHIPPED guest/cluster/node firewall family in `firewall.py`
closely in idiom (rule CRUD shapes, options get/set, position-addressed rules, the
immediate-effect/lockout risk ladder) — reused where the shapes genuinely match, diverged
(and documented, not silently) where they don't. Digest handling is the one place this
module does NOT mirror `firewall.py`'s capture-then-pin idiom — see the dedicated
divergence note below (post Wave 7b review Finding 1: the capture-then-pin design cannot
work on this plane at all).

- `action` (ACCEPT/DROP/REJECT) and the freetext/position validators are IMPORTED from
  `firewall.py` (`_check_action`, `_check_freetext`, `_check_pos`) — the schema's own
  action enum is identical, and comment/position semantics are identical. Same limitation
  as the shipped family: a rule referencing a security GROUP by name (the schema's "or
  security group name" clause) is not separately validated — passed through as an
  uppercased action string, which will fail PVE's own check if it isn't ACCEPT/DROP/REJECT.
  Not fixed here; matches the pre-existing shipped behavior verbatim (not relitigated).
- `type` (rule direction) is DIFFERENT and NOT reused: this schema's own `type` enum is
  `{in, out, forward, group}` — richer than firewall.py's guest/node/cluster `direction`
  enum `{in, out}`. A new `_check_vnet_fw_type` validator covers the 4-value set; this
  module calls the field `fw_type` everywhere (plan factory, wire function, tool wrapper)
  to sidestep the KEY-MISMATCH TRAP firewall.py's own `_merged_post_update` has to handle
  specially (PVE's wire key is `type`; firewall.py's own module chose the more expressive
  `direction` as its param name, which then had to be re-mapped against the stored `type`
  field at merge time) — this module never needs that re-mapping.
- `blast_engine.compute_firewall_reach` (the per-rule REACH engine `firewall.py` calls for
  guest/cluster/node rule add/remove/update) is DELIBERATELY NOT reused here: it assumes a
  2-value in/out direction and frames reach around per-HOST management-port lockout
  (SSH/22, PVE UI/8006) — neither assumption holds for a vnet-scoped firewall (traffic can
  be `forward`/`group`-typed, and the object being protected is a network SEGMENT's guest
  traffic, not host management access). This module builds its own vnet-scoped reach
  framing (`_vnet_fw_reach_lines`), reusing only the PURE, direction-agnostic label
  helpers `blast_engine._port_label` / `blast_engine._source_breadth` (module-qualified
  access, matching how `firewall.py` itself calls them — not `from .blast import _x`).
- `vnet`/`zone` id validation reuses `network.py`'s existing `_check_sdn_id` — deliberately
  NOT a new, narrower validator built against this schema's own stated pattern. Wave 7a's
  own adversarial review (Finding 1) found that building a second validator "because this
  schema's stated pattern is narrower" ships dead-weight duplicate code when the existing,
  already-looser validator already accepts every legal input (PVE enforces its own
  tighter server-side limits regardless, which is the real gate). This schema's vnet/zone
  pattern (`[a-zA-Z][a-zA-Z0-9]*[a-zA-Z0-9]`, 2-8 chars) is a STRICT SUBSET of
  `_check_sdn_id`'s accepted set (alnum/_/-, up to 64 chars) — reusing the looser
  validator cannot silently admit anything PVE itself would reject.
- `_parse_delete_keys`/`_enable_flag`-equivalents are small enough to duplicate rather than
  cross-import, mirroring `firewall.py`'s OWN precedent for `_check_freetext` vs the
  access_* modules' copy ("deliberate per-module duplication of the tiny helper").
- **DIGEST DESIGN — deliberately NOT the guest/cluster/node capture-then-pin idiom (Wave 7b
  review Finding 1, post-review redesign).** `firewall.py`'s `_fetch_rules_digest`/
  `_find_rule_at_pos` capture-then-pin idiom depends on GET .../firewall/rules surfacing a
  top-level `digest` field to capture on a plan-time read and pin on confirm; `firewall.py`'s
  own docstring already flags that as an UNCERTAIN shape risk for its family. For THIS
  family the schema gives a CONFIRMED, not uncertain, answer: `GET .../firewall/rules`,
  `GET .../firewall/rules/{pos}`, AND `GET .../firewall/options` all schema-verified to
  return NO `digest` field whatsoever (checked field-by-field against
  `wave7-pve-sdn-schema.json`'s `returns.items.properties`/`returns.properties` for all
  three reads) — `digest` appears ONLY as an optional parameter on the mutation verbs
  (POST/PUT/DELETE on rules; PUT on options). Capture-then-pin is therefore not merely
  unverified here, it is STRUCTURALLY IMPOSSIBLE: there is no read on this plane that could
  ever populate a digest to capture. The original build shipped a `_fetch_vnet_rules_digest`
  op-time re-fetch-or-fail helper anyway (mirrored from `firewall.py` without re-deriving it
  for this plane's own schema facts) — it raised on EVERY confirm call that didn't supply an
  out-of-band digest, since no real read would ever populate one. Fixed: `digest` is now an
  OPTIONAL caller-supplied passthrough on ALL FOUR mutation verbs
  (`rule_add`/`rule_update`/`rule_remove`/`options_set`) — forwarded verbatim when given,
  NEVER required, NEVER derived from a read. The rule_update/rule_remove PLANs still perform
  their one safe read (unchanged) and surface the found rule as identity evidence (the
  "rule at {pos}" snapshot), but state the race plainly instead of promising a digest to
  pin: positions can shift between plan and confirm, and — unlike the guest/cluster/node
  family — optimistic-lock protection on this plane exists ONLY when the caller supplies a
  digest obtained out-of-band (see `_RULE_DIGEST_RACE_LINE`).

Endpoint-shape facts (schema-verified against wave7-pve-sdn-schema.json for THIS chunk,
not assumed from the sibling zone/vnet/subnet precedent):
- `vnet_ips` (create/update/delete) carries NO `digest` at all on ANY of its 3 verbs — the
  only CRUD family on the whole SDN plane with zero optimistic-lock support (Wave 7 draft
  Fact #5). Not an oversight to "fix" — genuinely absent from the schema.
- `vnet_ips` PUT alone accepts an optional `vmid` (associates the mapping with a guest for
  tracking/audit purposes on UPDATE only; POST/DELETE do not accept it at all — Fact #4).
- There is NO GET on `/cluster/sdn/vnets/{vnet}/ips` anywhere in this schema — nothing to
  read back before a mutation. CAPTURE-or-declare: declare honestly in the plan (mirrors
  the Wave 1 apt-refresh "nothing to read back" precedent) rather than fabricate a
  "current" preview.
- Rule CREATE (POST .../firewall/rules) carries an optional `digest` AND an optional `pos`
  — a genuine platform inconsistency vs. the shipped guest/cluster/node
  `firewall_rule_add` (which accepts neither on create; PVE always inserts guest/
  cluster/node rules at position 0, `pos` is not even a parameter there). This endpoint's
  own POST `pos` field description ("Update rule at position <pos>") is copy-pasted from
  the sibling PUT method (matching the 3 CONFIRMED copy-paste bugs elsewhere on this
  plane, Wave 7 draft Fact #15 — trust verb/params/returns, never the description text)
  — its ACTUAL create-time effect (insert at `pos`, append, or silently ignored) is
  UNCONFIRMED. Forwarded when given (schema-declared, not invented), but every docstring
  flags this Smoke-confirm rather than asserting it controls insertion order.
- Rule UPDATE (PUT .../firewall/rules/{pos}) accepts `moveto` — schema-documented as "move
  rule to new position <moveto>; OTHER ARGUMENTS ARE IGNORED" when given. Honored as
  written: passing `moveto` alongside field edits in the same call means PVE ignores the
  field edits (do both in two separate calls if you need both — no client-side attempt to
  model a post-move reach here, since the schema itself says the other fields don't apply).
- Every mutation on this family returns `null` (verified field-by-field against the
  schema) — synchronous, callable-outcome idiom, `outcome="ok"`, never a UPID (Wave 7
  draft Fact #2, re-verified for this specific 10-method family, not assumed from the
  sibling zone/vnet precedent).
- vnet firewall options' `enable` defaults to `0` (schema-declared default) — unlike
  cluster/node/guest firewall options, which `firewall.py` documents as having NO stated
  default. Worth a docstring line: a caller toggling `policy_forward` without setting
  `enable=True` may not get the enforcement they expect yet.

Taint classification (Wave 7b; see `tests/test_taint_classification_complete.py`'s
REVIEWED_TRUSTED set for the authoritative list — none of these 10 tools are in
`taint.ADVERSARIAL_TOOLS`): all 10 are REVIEWED_TRUSTED, following the shipped
`firewall.py` family's OWN precedent exactly — `pve_firewall_rules_list`/
`pve_firewall_options_get`/the rule and options mutations are NONE of them in
`ADVERSARIAL_TOOLS` either. Rule `comment` is operator-typed free text, the SAME class
already accepted REVIEWED_TRUSTED for `pve_firewall_alias_create`'s / `pve_firewall_
ipset_entry_add`'s own comment fields elsewhere in this codebase. This is a deliberate
FOLLOW of the established family ruling (per the task brief's own instruction: state which
way the shipped family classifies and match it) rather than a fresh, independent
relitigation — no reason surfaced during this build to think the shipped ruling is wrong
for this sibling family.

Risk ratings (coordinator ruling, `.scratch/2026-07-15-full-surface-campaign.md` § Wave 7
ruling block + `.scratch/sdd/wave-7-draft-decomposition.md` §3 table):
- `vnet_firewall_options_set`: RISK_HIGH when `enable` or `policy_forward` is touched (set
  OR unset via `delete`), else RISK_MEDIUM. Mirrors `plan_firewall_options_set`'s own
  conditional-HIGH idiom, but UNLIKE that plan, the HIGH here is NEVER softened by any
  "inert until apply" disclaimer — this takes effect immediately (see the LIVE/IMMEDIATE
  note above).
- `vnet_firewall_rule_add/update/remove`: RISK_MEDIUM floor, matching `plan_firewall_
  rule_add`'s own MEDIUM-floor-plus-lockout-warning idiom. Absence of HIGH is NOT a safety
  signal (heuristic only) — a misplaced DROP/REJECT can sever ALL traffic for every guest
  attached to this vnet, immediately, with no apply step to catch it first.
- `vnet_ip_create/update`: RISK_LOW — reserves/updates an address-mapping record; no live
  traffic effect until a guest's NIC actually resolves through it.
- `vnet_ip_delete`: RISK_MEDIUM — frees an address that may be in ACTIVE use by a running
  guest's NIC right now, a real conflict-on-reuse risk one notch above create/update.
"""

from __future__ import annotations

import ipaddress
import re

from . import blast as blast_engine
from .backends import ProximoError, _check_vmid
from .firewall import _check_action, _check_freetext, _check_pos
from .network import _check_sdn_id
from .planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM, Plan

# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

_VALID_VNET_FW_TYPES = frozenset({"in", "out", "forward", "group"})


def _check_vnet_fw_type(value: str) -> str:
    """Vnet firewall rule 'type' — {in, out, forward, group}. NOT firewall.py's guest/
    cluster/node direction enum ({in, out} only) — see module docstring."""
    v = str(value).strip().lower()
    if v not in _VALID_VNET_FW_TYPES:
        raise ProximoError(
            f"invalid vnet firewall rule type: {value!r} (expected one of "
            f"{sorted(_VALID_VNET_FW_TYPES)})"
        )
    return v


def _check_vnet_ip(value: str) -> str:
    """A single IP address (schema format 'ip', not a CIDR)."""
    v = str(value).strip()
    try:
        ipaddress.ip_address(v)
    except ValueError as exc:
        raise ProximoError(f"invalid ip: {value!r} (expected a single IP address)") from exc
    return v


_MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}\Z")


def _check_mac(value: str) -> str:
    v = str(value).strip()
    if not _MAC_RE.match(v):
        raise ProximoError(f"invalid mac: {value!r} (expected XX:XX:XX:XX:XX:XX hex octets)")
    return v


_VNET_FW_OPTION_RESERVED = frozenset({"vnet", "delete", "digest"})


def _check_vnet_fw_option_keys(options: dict) -> None:
    """'vnet'/'delete'/'digest' are reserved (path segment / dedicated params) — reject them
    inside the options bag, mirroring firewall.py's own _check_option_keys guard (prevents a
    delete=[...] smuggled inside options from bypassing the risk classifier)."""
    bad = _VNET_FW_OPTION_RESERVED & set(options)
    if bad:
        raise ProximoError(
            f"reserved key(s) {sorted(bad)} cannot be passed inside options — "
            "use the dedicated vnet/delete/digest parameters instead"
        )


def _parse_delete_keys(delete) -> list[str]:
    """Normalize the `delete` param (list OR comma-separated string) to a list of keys.
    Duplicated from firewall.py's own tiny helper by design — see module docstring."""
    if isinstance(delete, list):
        return [str(k).strip() for k in delete if str(k).strip()]
    if isinstance(delete, str):
        return [k.strip() for k in delete.split(",") if k.strip()]
    return []


def _options_set_is_high(option_keys, delete_keys) -> bool:
    """HIGH iff 'enable' or 'policy_forward' is touched (set OR unset). Only 2 real keys on
    this endpoint (plus log_level_forward, which is not risk-elevating) — no 'policy*'
    wildcard needed the way firewall.py's cluster/node/guest options has multiple policy*
    keys."""
    touched = set(option_keys) | set(delete_keys)
    return bool(touched & {"enable", "policy_forward"})


def _vnet_fw_enable_flag(raw) -> bool:
    """Normalize a vnet firewall rule 'enable' field to bool. Mirrors firewall.py's own
    _enable_flag: None/absent -> True (PVE default-active); over-flag on odd values."""
    if raw is None:
        return True
    if isinstance(raw, bool):
        return raw
    return str(raw).strip() != "0"


_OPTIONS_DIR_TIGHTEN = "tighten"
_OPTIONS_DIR_LOOSEN = "loosen"
_OPTIONS_DIR_MIXED = "mixed"


def _options_set_direction(options: dict, delete_keys: list[str]) -> str:
    """Classify an options_set change touching enable/policy_forward as TIGHTEN (adds or
    strengthens enforcement), LOOSEN (removes or weakens enforcement), or MIXED (conflicting
    directions in the same call, or a value this module can't classify) — read directly off
    the schema's own option semantics (Wave 7b review Finding 2 fix):

    - `enable` (schema: boolean, default 0/disabled): True/truthy -> TIGHTEN, False/falsy ->
      LOOSEN. Deleting/unsetting `enable` reverts to the schema-declared default (0,
      disabled) -> LOOSEN.
    - `policy_forward` (schema: enum ACCEPT/DROP, NO schema-declared default): DROP ->
      TIGHTEN, ACCEPT -> LOOSEN. Any other value (shouldn't happen, but this module doesn't
      enum-validate policy_forward the way it validates rule `action`) -> unclassifiable.
      Deleting/unsetting `policy_forward` has NO schema-declared default to fall back to —
      the resulting behavior is unconfirmed, so this is unclassifiable too. Never guess.

    Only reached when `_options_set_is_high` is True (enable or policy_forward touched at
    all) — log_level_forward never affects direction."""
    signals: set[str] = set()

    if "enable" in options:
        signals.add(_OPTIONS_DIR_TIGHTEN if _vnet_fw_enable_flag(options["enable"]) else _OPTIONS_DIR_LOOSEN)
    elif "enable" in delete_keys:
        signals.add(_OPTIONS_DIR_LOOSEN)  # schema default 0 (disabled) — unsetting removes enforcement

    if "policy_forward" in options:
        pf = str(options["policy_forward"]).strip().upper()
        if pf == "DROP":
            signals.add(_OPTIONS_DIR_TIGHTEN)
        elif pf == "ACCEPT":
            signals.add(_OPTIONS_DIR_LOOSEN)
        else:
            signals.add(_OPTIONS_DIR_MIXED)  # unrecognized value — never silently pick a side
    elif "policy_forward" in delete_keys:
        signals.add(_OPTIONS_DIR_MIXED)  # no schema-declared default — resulting value unconfirmed

    if signals == {_OPTIONS_DIR_TIGHTEN}:
        return _OPTIONS_DIR_TIGHTEN
    if signals == {_OPTIONS_DIR_LOOSEN}:
        return _OPTIONS_DIR_LOOSEN
    return _OPTIONS_DIR_MIXED


# ---------------------------------------------------------------------------
# URL helper
# ---------------------------------------------------------------------------

def _vnet_fw_base(vnet: str) -> str:
    """Build /cluster/sdn/vnets/{vnet}/firewall — validates vnet via network.py's existing
    _check_sdn_id (see module docstring: deliberately not a narrower validator)."""
    v = _check_sdn_id(vnet, "vnet")
    return f"/cluster/sdn/vnets/{v}/firewall"


# ---------------------------------------------------------------------------
# READ operations (no confirm-gate; audited at server layer) — all REVIEWED_TRUSTED
# ---------------------------------------------------------------------------

def vnet_firewall_options_get(api, vnet: str) -> dict:
    """Get vnet firewall options (enable, log_level_forward, policy_forward).
    GET /cluster/sdn/vnets/{vnet}/firewall/options. LIVE/IMMEDIATE family (see module
    docstring) — this is a live-config read, not a staged/pending one."""
    base = _vnet_fw_base(vnet)
    return api._get(f"{base}/options") or {}


def vnet_firewall_rules_list(api, vnet: str) -> list[dict]:
    """List vnet firewall rules, in ruleset order. GET /cluster/sdn/vnets/{vnet}/firewall/rules."""
    base = _vnet_fw_base(vnet)
    return api._get(f"{base}/rules") or []


def vnet_firewall_rule_get(api, vnet: str, pos: int) -> dict:
    """Get a single vnet firewall rule by position.
    GET /cluster/sdn/vnets/{vnet}/firewall/rules/{pos}."""
    p = _check_pos(pos)
    base = _vnet_fw_base(vnet)
    return api._get(f"{base}/rules/{p}") or {}


# ---------------------------------------------------------------------------
# MUTATION operations — PLAN-gated + audited at the server layer. LIVE/IMMEDIATE.
# ---------------------------------------------------------------------------

def vnet_firewall_options_set(
    api,
    vnet: str,
    options: dict | None = None,
    delete: list | str | None = None,
    digest: str | None = None,
) -> object:
    """Set vnet firewall options. PUT /cluster/sdn/vnets/{vnet}/firewall/options
    {<option>: <value>, ..., delete?, digest?}. LIVE/IMMEDIATE — see module docstring.
    Requires at least one option to set or delete (a digest alone is not a change).
    """
    if not options and not delete:
        raise ProximoError(
            "vnet_firewall_options_set requires at least one option to set (options=...) "
            "or unset (delete=[...]) — a digest alone is not a change"
        )
    _check_vnet_fw_option_keys(options or {})
    base = _vnet_fw_base(vnet)
    data: dict = dict(options or {})
    delete_keys = _parse_delete_keys(delete)
    if delete_keys:
        data["delete"] = ",".join(delete_keys)
    if digest is not None:
        data["digest"] = digest
    return api._put(f"{base}/options", data)


def vnet_firewall_rule_add(
    api,
    vnet: str,
    action: str,
    fw_type: str = "in",
    source: str | None = None,
    dest: str | None = None,
    proto: str | None = None,
    dport: str | None = None,
    sport: str | None = None,
    icmp_type: str | None = None,
    iface: str | None = None,
    log: str | None = None,
    macro: str | None = None,
    comment: str | None = None,
    enable: bool | None = None,
    pos: int | None = None,
    digest: str | None = None,
) -> object:
    """Add a new vnet firewall rule. POST /cluster/sdn/vnets/{vnet}/firewall/rules.
    LIVE/IMMEDIATE — no apply gate, no rollback coverage (see module docstring).

    `pos`/`digest` are schema-declared on this CREATE endpoint (a platform inconsistency vs.
    the shipped guest/cluster/node pve_firewall_rule_add, which accepts neither — see module
    docstring). Forwarded when given; `pos`'s actual create-time effect is Smoke-confirm, not
    asserted.
    """
    action = _check_action(action)
    fw_type = _check_vnet_fw_type(fw_type)
    base = _vnet_fw_base(vnet)
    data: dict = {"action": action, "type": fw_type}
    if source is not None:
        data["source"] = source
    if dest is not None:
        data["dest"] = dest
    if proto is not None:
        data["proto"] = proto
    if dport is not None:
        data["dport"] = dport
    if sport is not None:
        data["sport"] = sport
    if icmp_type is not None:
        data["icmp-type"] = icmp_type
    if iface is not None:
        data["iface"] = iface
    if log is not None:
        data["log"] = log
    if macro is not None:
        data["macro"] = macro
    if comment is not None:
        data["comment"] = _check_freetext(comment, "comment")
    if enable is not None:
        data["enable"] = 1 if enable else 0
    if pos is not None:
        data["pos"] = _check_pos(pos)
    if digest is not None:
        data["digest"] = digest
    return api._post(f"{base}/rules", data)


def vnet_firewall_rule_remove(api, vnet: str, pos: int, digest: str | None = None) -> object:
    """Delete a vnet firewall rule by position.
    DELETE /cluster/sdn/vnets/{vnet}/firewall/rules/{pos}. LIVE/IMMEDIATE.

    digest: OPTIONAL caller-supplied optimistic-lock passthrough — forwarded verbatim when
    given, NEVER required and NEVER derived. This endpoint's reads (rules list / rule get)
    expose no digest field on this schema at all (schema-verified — see module docstring), so
    there is nothing on this plane to capture-then-pin from. Supply a digest only if you
    obtained one out-of-band; omitting it is the default, supported path.
    """
    p = _check_pos(pos)
    base = _vnet_fw_base(vnet)
    params: dict = {}
    if digest is not None:
        params["digest"] = digest
    return api._delete(f"{base}/rules/{p}", params)


def vnet_firewall_rule_update(
    api,
    vnet: str,
    pos: int,
    action: str | None = None,
    fw_type: str | None = None,
    source: str | None = None,
    dest: str | None = None,
    proto: str | None = None,
    dport: str | None = None,
    sport: str | None = None,
    icmp_type: str | None = None,
    iface: str | None = None,
    log: str | None = None,
    macro: str | None = None,
    comment: str | None = None,
    enable: bool | None = None,
    moveto: int | None = None,
    digest: str | None = None,
) -> object:
    """Update a vnet firewall rule at position `pos`.
    PUT /cluster/sdn/vnets/{vnet}/firewall/rules/{pos}. LIVE/IMMEDIATE.

    `moveto`: schema-documented — if given, PVE ignores every OTHER argument in this SAME
    call (move and edit fields in two separate calls if you need both).
    digest: OPTIONAL caller-supplied optimistic-lock passthrough — forwarded verbatim when
    given, NEVER required and NEVER derived (this endpoint's reads expose no digest field on
    this schema at all — see module docstring). Omitting it is the default, supported path.
    """
    p = _check_pos(pos)
    base = _vnet_fw_base(vnet)
    data: dict = {}
    if action is not None:
        data["action"] = _check_action(action)
    if fw_type is not None:
        data["type"] = _check_vnet_fw_type(fw_type)
    if source is not None:
        data["source"] = source
    if dest is not None:
        data["dest"] = dest
    if proto is not None:
        data["proto"] = proto
    if dport is not None:
        data["dport"] = dport
    if sport is not None:
        data["sport"] = sport
    if icmp_type is not None:
        data["icmp-type"] = icmp_type
    if iface is not None:
        data["iface"] = iface
    if log is not None:
        data["log"] = log
    if macro is not None:
        data["macro"] = macro
    if comment is not None:
        data["comment"] = _check_freetext(comment, "comment")
    if enable is not None:
        data["enable"] = 1 if enable else 0
    if moveto is not None:
        data["moveto"] = _check_pos(moveto)
    if not data:
        raise ProximoError("vnet_firewall_rule_update requires at least one field to update")
    if digest is not None:
        data["digest"] = digest
    return api._put(f"{base}/rules/{p}", data)


def vnet_ip_create(api, vnet: str, zone: str, ip: str, mac: str | None = None) -> object:
    """Create an IP-to-MAC mapping in a vnet (IPAM record).
    POST /cluster/sdn/vnets/{vnet}/ips {ip, vnet, zone, mac?}. NO digest support at all on
    this endpoint (schema-verified — see module docstring)."""
    v = _check_sdn_id(vnet, "vnet")
    z = _check_sdn_id(zone, "zone")
    i = _check_vnet_ip(ip)
    data: dict = {"ip": i, "vnet": v, "zone": z}
    if mac is not None:
        data["mac"] = _check_mac(mac)
    return api._post(f"/cluster/sdn/vnets/{v}/ips", data)


def vnet_ip_update(
    api, vnet: str, zone: str, ip: str, mac: str | None = None, vmid: str | None = None,
) -> object:
    """Update an IP-to-MAC mapping in a vnet.
    PUT /cluster/sdn/vnets/{vnet}/ips {ip, vnet, zone, mac?, vmid?}. `vmid` associates the
    mapping with a guest for tracking/audit purposes — PUT-only (Fact #4). NO digest support
    at all on this endpoint (Fact #5)."""
    v = _check_sdn_id(vnet, "vnet")
    z = _check_sdn_id(zone, "zone")
    i = _check_vnet_ip(ip)
    data: dict = {"ip": i, "vnet": v, "zone": z}
    if mac is not None:
        data["mac"] = _check_mac(mac)
    if vmid is not None:
        data["vmid"] = _check_vmid(vmid)
    return api._put(f"/cluster/sdn/vnets/{v}/ips", data)


def vnet_ip_delete(api, vnet: str, zone: str, ip: str, mac: str | None = None) -> object:
    """Delete an IP-to-MAC mapping from a vnet.
    DELETE /cluster/sdn/vnets/{vnet}/ips {ip, vnet, zone, mac?}. NO digest support at all on
    this endpoint (Fact #5)."""
    v = _check_sdn_id(vnet, "vnet")
    z = _check_sdn_id(zone, "zone")
    i = _check_vnet_ip(ip)
    params: dict = {"ip": i, "vnet": v, "zone": z}
    if mac is not None:
        params["mac"] = _check_mac(mac)
    return api._delete(f"/cluster/sdn/vnets/{v}/ips", params)


# ---------------------------------------------------------------------------
# PLAN factories — pure functions except where a safe read is explicitly noted
# ---------------------------------------------------------------------------

_VNET_FW_TYPE_LABEL = {
    "in": "traffic INTO this vnet (destined for guests attached to it)",
    "out": "traffic OUT of this vnet (originating from guests attached to it)",
    "forward": "traffic FORWARDED/ROUTED through this vnet (transit — not addressed to a local guest)",
    "group": "traffic matched via a referenced security GROUP (rule set defined elsewhere)",
}

_LIVE_IMMEDIATE_LINE = (
    "LIVE/IMMEDIATE: takes effect on live guest traffic THE INSTANT you confirm — no "
    "pve_sdn_apply gate, no pve_sdn_rollback coverage (see module docstring)"
)

_RULE_DIGEST_RACE_LINE = (
    "positions can shift between this plan and your confirm call — unlike the guest/"
    "cluster/node firewall family, this endpoint's reads expose no digest field on this "
    "schema (schema-verified), so optimistic-lock protection exists ONLY if you supply a "
    "digest obtained out-of-band; the rule snapshot captured above is this plan's "
    "best-effort identity evidence, not a guarantee it still holds that position"
)


def _vnet_fw_rule_summary(
    action: str, fw_type: str, source, dest, dport, proto, iface=None, pos=None,
) -> str:
    parts = [f"action={action}", f"type={fw_type}"]
    if source:
        parts.append(f"source={source}")
    if dest:
        parts.append(f"dest={dest}")
    if dport:
        parts.append(f"dport={dport}")
    if proto:
        parts.append(f"proto={proto}")
    if iface:
        parts.append(f"iface={iface}")
    if pos is not None:
        parts.append(f"pos={pos}")
    return ", ".join(parts)


def _vnet_fw_reach_lines(
    vnet: str, action: str, fw_type: str, source, dport, proto, enable: bool = True,
) -> list[str]:
    """PURE vnet-scoped reach framing — see module docstring for why blast_engine.
    compute_firewall_reach is NOT reused here (2-value direction + host-lockout framing
    mismatch). Reuses only the pure, direction-agnostic port/address label helpers."""
    type_label = _VNET_FW_TYPE_LABEL.get(fw_type, fw_type)
    service = blast_engine._port_label(dport, proto)
    _, from_label = blast_engine._source_breadth(source)
    act = (action or "").upper()
    if not enable:
        return [
            f"this rule is DISABLED (enable=0) — STAGED, not active: it would "
            f"{act.lower() or 'apply to'} {type_label} once enabled",
        ]
    if act == "ACCEPT":
        return [f"PERMITS {type_label}: {service} from {from_label}"]
    # DROP / REJECT / a referenced group name (matches firewall.py's own action limitation)
    return [
        f"{act or 'this rule'} matches {type_label}: {service} from {from_label} — if this "
        "is the deciding match, that traffic is BLOCKED",
    ]


_OPTIONS_TIGHTEN_LINE = (
    "enabling this firewall or setting policy_forward=DROP can immediately cut ALL "
    "forwarded traffic for guests on this vnet"
)
_OPTIONS_LOOSEN_LINE = (
    "disabling this firewall or setting policy_forward=ACCEPT immediately REMOVES firewall "
    "protection from this vnet's forwarded traffic — traffic that was previously BLOCKED is "
    "now allowed through"
)
_OPTIONS_MIXED_LINE = (
    "this change's direction is not a single clean tighten-or-loosen (either it touches "
    "enable AND policy_forward toward different directions in the same call, or it sets an "
    "unrecognized value this module can't classify) — it may immediately CUT traffic that "
    "was flowing OR immediately ALLOW traffic that was blocked, depending on the actual "
    "resulting values; verify both directions before confirming"
)


def plan_vnet_firewall_options_set(
    api, vnet: str, options: dict | None = None, delete: list | str | None = None,
) -> Plan:
    """Preview a vnet firewall options change. Reads current options (one safe read).
    RISK_HIGH when enable/policy_forward is touched, else RISK_MEDIUM. LIVE/IMMEDIATE — NOT
    softened by any 'inert until apply' language (see module docstring).

    The inserted HIGH-risk blast line is DIRECTION-AWARE (Wave 7b review Finding 2 fix): a
    tightening change (enable=True, policy_forward=DROP) gets the immediate-cut warning; a
    loosening change (enable=False, delete=["enable"] reverting to the schema default of
    disabled, policy_forward=ACCEPT) gets the honest "REMOVES protection" warning instead —
    it does NOT get the cut-traffic line, since it does the opposite; a conflicting or
    unclassifiable combination gets a combined line covering both directions (see
    `_options_set_direction`)."""
    options = options or {}
    _check_vnet_fw_option_keys(options)
    delete_keys = _parse_delete_keys(delete)
    v = _check_sdn_id(vnet, "vnet")

    current: dict = {}
    read_failed = False
    try:
        current = vnet_firewall_options_get(api, v) or {}
        touched = set(options) | set(delete_keys)
        current = {k: val for k, val in current.items() if k in touched}
    except Exception:
        read_failed = True

    high = _options_set_is_high(options.keys(), delete_keys)
    set_summary = ", ".join(f"{k}={options[k]}" for k in options) or "(none)"
    del_summary = ", ".join(delete_keys) or "(none)"

    blast = [
        f"sets vnet firewall options on vnet '{v}': set [{set_summary}], unset [{del_summary}]",
        _LIVE_IMMEDIATE_LINE,
        "no UNDO: revert by setting the prior values back",
    ]
    reasons = ["vnet firewall option changes can affect connectivity for every guest on this vnet"]
    if high:
        direction = _options_set_direction(options, delete_keys)
        if direction == _OPTIONS_DIR_TIGHTEN:
            blast.insert(1, _OPTIONS_TIGHTEN_LINE)
        elif direction == _OPTIONS_DIR_LOOSEN:
            blast.insert(1, _OPTIONS_LOOSEN_LINE)
        else:
            blast.insert(1, _OPTIONS_MIXED_LINE)
        reasons.append("changes the enable flag or the forward policy — immediate blast radius")
    if read_failed:
        blast.append("could not read current options — prior values UNKNOWN, no guided revert baseline")

    return Plan(
        action="pve_sdn_vnet_firewall_options_set",
        target=f"sdn/vnets/{v}/firewall/options",
        change=f"change vnet '{v}' firewall options: set=[{set_summary}], unset=[{del_summary}]",
        current=current,
        blast_radius=blast,
        risk=RISK_HIGH if high else RISK_MEDIUM,
        risk_reasons=reasons,
        complete=not read_failed,
    )


def plan_vnet_firewall_rule_add(
    vnet: str,
    action: str,
    fw_type: str = "in",
    source: str | None = None,
    dest: str | None = None,
    dport: str | None = None,
    proto: str | None = None,
    iface: str | None = None,
    pos: int | None = None,
) -> Plan:
    """Preview adding a vnet firewall rule. PURE — no API call needed (a new rule has no
    'current' state). RISK_MEDIUM floor. LIVE/IMMEDIATE — see module docstring.

    `iface`/`pos` are disclosed in the rule summary (identity-bearing — a caller who pins an
    interface or an insertion position needs to see it echoed before confirming) but do not
    feed into `_vnet_fw_reach_lines` (the reach engine reasons about action/type/source/
    dport/proto only, matching firewall.py's own `compute_firewall_reach` scope)."""
    action = _check_action(action)
    fw_type = _check_vnet_fw_type(fw_type)
    v = _check_sdn_id(vnet, "vnet")
    rule_summary = _vnet_fw_rule_summary(action, fw_type, source, dest, dport, proto, iface, pos)
    reach_lines = _vnet_fw_reach_lines(v, action, fw_type, source, dport, proto)

    return Plan(
        action="pve_sdn_vnet_firewall_rule_add",
        target=f"sdn/vnets/{v}/firewall/rules",
        change=f"add vnet firewall rule on vnet '{v}': {rule_summary}",
        current={},
        blast_radius=[
            *reach_lines,
            f"adds a firewall rule to vnet '{v}': {rule_summary}",
            _LIVE_IMMEDIATE_LINE,
            "a misplaced DROP/REJECT can sever traffic for every guest on this vnet",
            "no UNDO: revert by removing this rule with pve_sdn_vnet_firewall_rule_remove",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "vnet firewall rule changes affect connectivity for every guest attached to this vnet",
            "absence of HIGH is NOT a safety signal (heuristic only)",
        ],
    )


_VNET_RULE_SNAPSHOT_KEYS = (
    "pos", "action", "type", "source", "dest", "dport", "sport", "proto", "enable", "comment",
)


def _find_vnet_rule_at_pos(
    api, vnet: str, pos: int,
) -> tuple[dict | None, dict, str | None]:
    """One safe read of the vnet firewall rules list: return (found_rule_or_None,
    current_snapshot_dict, check_error). Mirrors firewall.py's _find_rule_at_pos in shape,
    but does NOT capture a digest — this schema's reads never expose one (schema-verified,
    see module docstring); the snapshot is identity evidence only, not an optimistic lock."""
    try:
        rules = vnet_firewall_rules_list(api, vnet) or []
        found = next((r for r in rules if r.get("pos") == pos), None)
        current = {k: found[k] for k in _VNET_RULE_SNAPSHOT_KEYS if k in found} if found else {}
        return found, current, None
    except Exception as e:
        return None, {}, type(e).__name__


def plan_vnet_firewall_rule_remove(api, vnet: str, pos: int) -> Plan:
    """Preview removing a vnet firewall rule at position `pos`. Reads the rule list (a safe
    read) to surface what's at that position. RISK_MEDIUM floor. LIVE/IMMEDIATE."""
    p = _check_pos(pos)
    v = _check_sdn_id(vnet, "vnet")
    rule_desc = f"rule at position {p}"

    found, current, check_error = _find_vnet_rule_at_pos(api, v, p)
    if found:
        rule_desc = f"rule at pos={p}: action={found.get('action', '?')}, type={found.get('type', '?')}"
        if found.get("source"):
            rule_desc += f", source={found['source']}"
        if found.get("dport"):
            rule_desc += f", dport={found['dport']}"

    complete = True
    if check_error is not None:
        complete = False
        blast = [
            f"rule lookup failed ({check_error}) — could not confirm what rule is at position {p}; "
            "removal may affect the wrong rule or fail",
            "positions SHIFT after inserts/deletes — re-list rules before confirming",
            _LIVE_IMMEDIATE_LINE,
            "no UNDO: revert by re-adding the rule",
        ]
        reasons = [
            f"rule lookup for position {p} failed — cannot confirm what is removed",
            "absence of HIGH is NOT a safety signal",
        ]
    else:
        reach_lines = (
            _vnet_fw_reach_lines(
                v, found.get("action", ""), found.get("type", "in"), found.get("source"),
                found.get("dport"), found.get("proto"),
                enable=_vnet_fw_enable_flag(found.get("enable", 1)),
            )
            if found else []
        )
        blast = [
            *[f"removing this rule ends: {line}" for line in reach_lines],
            f"removes {rule_desc} from vnet '{v}'",
            "positions SHIFT after this removal — re-list rules if doing further edits",
            _LIVE_IMMEDIATE_LINE,
            _RULE_DIGEST_RACE_LINE,
            "no UNDO: revert by re-adding the rule with pve_sdn_vnet_firewall_rule_add",
        ]
        reasons = [
            "vnet firewall rule removal affects connectivity for every guest on this vnet",
            "absence of HIGH is NOT a safety signal (heuristic only)",
        ]

    return Plan(
        action="pve_sdn_vnet_firewall_rule_remove",
        target=f"sdn/vnets/{v}/firewall/rules/{p}",
        change=f"remove {rule_desc} from vnet '{v}'",
        current=current,
        blast_radius=blast,
        risk=RISK_MEDIUM,
        risk_reasons=reasons,
        complete=complete,
    )


def _vnet_fw_merged_post_update(found: dict, new_fields: dict) -> dict:
    """Resolve POST-UPDATE rule fields for reach classification: new_fields layered over the
    stored rule `found`. Mirrors firewall.py's _merged_post_update, but with NO key-mismatch
    trap: this module names the field `fw_type` consistently at every layer (plan factory,
    wire function, tool wrapper), so no direction/type re-mapping is needed the way
    firewall.py's own `direction` (param) vs. `type` (PVE wire key) split requires."""
    return {
        "action": new_fields.get("action") or found.get("action", ""),
        "fw_type": new_fields.get("fw_type") or found.get("type", "in"),
        "source": new_fields["source"] if "source" in new_fields else found.get("source"),
        "dport": new_fields["dport"] if "dport" in new_fields else found.get("dport"),
        "proto": new_fields["proto"] if "proto" in new_fields else found.get("proto"),
        "enable": (
            _vnet_fw_enable_flag(new_fields["enable"]) if "enable" in new_fields
            else _vnet_fw_enable_flag(found.get("enable", 1))
        ),
    }


def plan_vnet_firewall_rule_update(api, vnet: str, pos: int, **new_fields) -> Plan:
    """Preview updating a vnet firewall rule at position `pos`. Reads the rule list (a safe
    read) for before/after comparison. RISK_MEDIUM floor. LIVE/IMMEDIATE.

    If `moveto` is present in new_fields, the plan does NOT attempt to model a post-move
    reach — the schema itself says PVE ignores every other field when moveto is given (see
    module docstring), so modeling a merged post-update rule would misrepresent what
    actually happens.
    """
    p = _check_pos(pos)
    v = _check_sdn_id(vnet, "vnet")
    if new_fields.get("action") is not None:
        new_fields["action"] = _check_action(new_fields["action"])
    if new_fields.get("fw_type") is not None:
        new_fields["fw_type"] = _check_vnet_fw_type(new_fields["fw_type"])

    found, current, check_error = _find_vnet_rule_at_pos(api, v, p)
    rule_desc = f"rule at position {p}"
    if found:
        rule_desc = f"rule at pos={p}: action={found.get('action', '?')}, type={found.get('type', '?')}"

    changed_fields = ", ".join(f"{k}={val!r}" for k, val in new_fields.items()) or "(no fields)"
    moving = new_fields.get("moveto") is not None

    complete = True
    if check_error is not None:
        complete = False
        blast = [
            f"rule lookup failed ({check_error}) — could not read current state of {rule_desc}",
            "positions SHIFT after inserts/deletes — re-list rules before confirming",
            _LIVE_IMMEDIATE_LINE,
            "no UNDO: revert by updating the rule back to its prior values",
        ]
        reasons = [
            f"rule lookup for position {p} failed — cannot compare before/after state",
            "absence of HIGH is NOT a safety signal",
        ]
    elif moving:
        blast = [
            f"moves {rule_desc} to position {new_fields['moveto']} on vnet '{v}' — PVE ignores "
            "every OTHER argument in this same call when moveto is given (schema-documented)",
            "positions SHIFT for every rule between the old and new position",
            _LIVE_IMMEDIATE_LINE,
            _RULE_DIGEST_RACE_LINE,
            "no UNDO: revert by moving it back",
        ]
        reasons = [
            "moving a rule changes match ORDER (first-match, top-down) — can change which rule "
            "decides a packet's fate even with no field edited",
        ]
    else:
        merged = _vnet_fw_merged_post_update(found or {}, new_fields)
        reach_lines = _vnet_fw_reach_lines(
            v, merged["action"], merged["fw_type"], merged["source"], merged["dport"],
            merged["proto"], enable=merged["enable"],
        )
        blast = [
            *[f"after this update: {line}" for line in reach_lines],
            f"updates {rule_desc} on vnet '{v}': changes -> {changed_fields}",
            "positions SHIFT after inserts/deletes; verify position before updating",
            _LIVE_IMMEDIATE_LINE,
            _RULE_DIGEST_RACE_LINE,
            "no UNDO: revert by updating the rule back to its prior values",
        ]
        reasons = [
            "vnet firewall rule update affects connectivity for every guest on this vnet",
            "absence of HIGH is NOT a safety signal (heuristic only)",
        ]

    return Plan(
        action="pve_sdn_vnet_firewall_rule_update",
        target=f"sdn/vnets/{v}/firewall/rules/{p}",
        change=f"update {rule_desc} on vnet '{v}': {changed_fields}",
        current=current,
        blast_radius=blast,
        risk=RISK_MEDIUM,
        risk_reasons=reasons,
        complete=complete,
    )


def plan_vnet_ip_create(vnet: str, zone: str, ip: str, mac: str | None = None) -> Plan:
    """Preview creating an IP mapping in a vnet. PURE — no read (this endpoint has no GET at
    all, see module docstring). RISK_LOW — reserves a mapping; no live traffic effect until
    a guest's NIC resolves through it."""
    v = _check_sdn_id(vnet, "vnet")
    z = _check_sdn_id(zone, "zone")
    i = _check_vnet_ip(ip)
    mac_part = f", mac={mac}" if mac else ""
    return Plan(
        action="pve_sdn_vnet_ip_create",
        target=f"sdn/vnets/{v}/ips",
        change=f"create IP mapping {i} in vnet '{v}' (zone '{z}'){mac_part}",
        current={},
        blast_radius=[
            f"reserves IP mapping {i}{mac_part} in vnet '{v}' (zone '{z}')",
            "no live traffic effect until a guest's NIC actually resolves through this mapping",
            "no read-back: this endpoint has no GET — nothing to CAPTURE for 'current' "
            "(declared, not fabricated)",
            "no digest support at all on this endpoint (schema-verified) — no optimistic "
            "lock possible on this family",
            "no UNDO: revert by deleting the mapping with pve_sdn_vnet_ip_delete",
        ],
        risk=RISK_LOW,
        risk_reasons=["reserving an address mapping has no live effect until a guest NIC uses it"],
    )


def plan_vnet_ip_update(
    vnet: str, zone: str, ip: str, mac: str | None = None, vmid: str | None = None,
) -> Plan:
    """Preview updating an IP mapping in a vnet. PURE — no read-back possible (no GET on
    this endpoint at all). RISK_LOW."""
    v = _check_sdn_id(vnet, "vnet")
    z = _check_sdn_id(zone, "zone")
    i = _check_vnet_ip(ip)
    parts = []
    if mac:
        parts.append(f"mac={mac}")
    if vmid:
        parts.append(f"vmid={vmid}")
    change_summary = ", ".join(parts) or "(no optional fields)"
    return Plan(
        action="pve_sdn_vnet_ip_update",
        target=f"sdn/vnets/{v}/ips",
        change=f"update IP mapping {i} in vnet '{v}' (zone '{z}'): {change_summary}",
        current={},
        blast_radius=[
            f"updates IP mapping {i} in vnet '{v}' (zone '{z}'): {change_summary}",
            "no live traffic effect until a guest's NIC actually resolves through this mapping",
            "no read-back: this endpoint has no GET — nothing to CAPTURE for 'current'",
            "no digest support at all on this endpoint — no optimistic lock possible",
            "no UNDO: revert by updating it back to its prior mac/vmid",
        ],
        risk=RISK_LOW,
        risk_reasons=[
            "updating an address mapping's mac/vmid association has no live traffic effect by itself",
        ],
    )


def plan_vnet_ip_delete(vnet: str, zone: str, ip: str, mac: str | None = None) -> Plan:
    """Preview deleting an IP mapping from a vnet. PURE — no read-back possible. RISK_MEDIUM:
    frees an address that may be in ACTIVE use by a running guest's NIC right now."""
    v = _check_sdn_id(vnet, "vnet")
    z = _check_sdn_id(zone, "zone")
    i = _check_vnet_ip(ip)
    mac_part = f", mac={mac}" if mac else ""
    return Plan(
        action="pve_sdn_vnet_ip_delete",
        target=f"sdn/vnets/{v}/ips",
        change=f"delete IP mapping {i} from vnet '{v}' (zone '{z}'){mac_part}",
        current={},
        blast_radius=[
            f"frees IP mapping {i}{mac_part} from vnet '{v}' (zone '{z}')",
            "this address may be in ACTIVE use by a running guest's NIC right now — a real "
            "conflict-on-reuse risk if another guest is later assigned the same address",
            "no read-back: this endpoint has no GET — cannot confirm the mapping still exists "
            "before deleting it",
            "no digest support at all on this endpoint — no optimistic lock possible",
            "no UNDO: re-create the mapping with pve_sdn_vnet_ip_create to revert",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=["frees an address that may be actively assigned to a running guest's NIC"],
    )
