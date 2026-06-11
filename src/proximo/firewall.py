"""FIREWALL pillar — cluster / node / guest firewall management.

Covers the three PVE firewall scopes:
  cluster  → /cluster/firewall
  node     → /nodes/{node}/firewall
  guest    → /nodes/{node}/{kind}/{vmid}/firewall

Every mutating function is PLAN-gated at the server layer (no plan → no mutation).
Plans are HONEST: they surface the rule, its position, and its scope before any edit.

Hard rules mirrored from the codebase:
- Firewall edits are SILENT-MISTAKE-PRONE: a misplaced ACCEPT/DROP rule or toggling
  the firewall off can instantly lock you out of the host (SSH/8006). Plans always
  surface scope + position + the full rule so the caller sees exactly what changes.
- No UNDO: PVE firewall config lives in cluster config files, not in guest disk
  snapshots. _auto_undo / snapshot rollback does NOT revert firewall changes.
  Never claim UNDO; the only revert is the inverse op (re-add / re-enable / etc.).
- Firewall writes are assumed SYNCHRONOUS (return null data, not a task UPID).
  The "submitted" outcome pattern does NOT apply here. Flag as shape risk.
- RISK_HIGH for firewall_set_enabled regardless of direction: enabling may instantly
  drop traffic if rules are absent/wrong (default-DROP without ACCEPT for 8006/22);
  disabling strips all firewall protection.
- rule add/remove/update are RISK_MEDIUM floor with a prominent connectivity/lockout
  note. Absence of HIGH is NOT a safety signal (rules are curated heuristics).
- No self-gating: the server layer adds confirm-gating + audit; these functions are
  pure ops.

Endpoint shape / backend dependency notes (flag for live smoke):
- All PUT endpoints (rule_update, set_enabled) call api._put() on ApiBackend.
- Firewall writes assumed synchronous (no UPID). If live PVE returns a UPID, change
  outcome="ok" → outcome="submitted" in the server layer and adjust return shape.
- firewall_rule_remove and firewall_rule_update re-read rules at op time and pass the
  PVE digest in the DELETE params / PUT body for optimistic-locking. Shape risk: it is
  uncertain whether GET …/firewall/rules actually surfaces a top-level 'digest' field on
  all PVE versions. If the live endpoint does not return a digest, these ops will raise
  ProximoError rather than silently proceeding without a lock. Confirm at live smoke.
"""

from __future__ import annotations

from .backends import ProximoError, _check_kind, _check_node, _check_vmid
from .planning import RISK_HIGH, RISK_MEDIUM, Plan

# ---------------------------------------------------------------------------
# Module-level validators
# ---------------------------------------------------------------------------

_VALID_SCOPES = frozenset({"cluster", "node", "guest"})
_VALID_ACTIONS = frozenset({"ACCEPT", "DROP", "REJECT"})
_VALID_DIRECTIONS = frozenset({"in", "out"})


def _check_scope(scope: str) -> str:
    if scope not in _VALID_SCOPES:
        raise ProximoError(
            f"invalid scope: {scope!r} (expected one of {sorted(_VALID_SCOPES)})"
        )
    return scope


def _check_pos(pos) -> int:
    """Firewall rule position — must be a non-negative integer (it goes into the URL path)."""
    try:
        n = int(pos)
    except (TypeError, ValueError) as exc:
        raise ProximoError(f"invalid rule position: {pos!r} (must be a non-negative integer)") from exc
    if n < 0:
        raise ProximoError(f"invalid rule position: {pos!r} (must be >= 0)")
    return n


def _check_action(action: str) -> str:
    a = str(action).upper()
    if a not in _VALID_ACTIONS:
        raise ProximoError(
            f"invalid firewall action: {action!r} (expected one of {sorted(_VALID_ACTIONS)})"
        )
    return a


def _check_direction(direction: str) -> str:
    d = str(direction).lower()
    if d not in _VALID_DIRECTIONS:
        raise ProximoError(
            f"invalid rule direction: {direction!r} (expected 'in' or 'out')"
        )
    return d


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _fw_base(
    api,
    scope: str,
    node: str | None = None,
    vmid: str | None = None,
    kind: str | None = None,
) -> str:
    """Build the base firewall URL for the given scope.

    cluster → /cluster/firewall
    node    → /nodes/{node}/firewall
    guest   → /nodes/{node}/{kind}/{vmid}/firewall
    """
    _check_scope(scope)
    if scope == "cluster":
        return "/cluster/firewall"
    n = node or api.config.node
    _check_node(n)
    if scope == "node":
        return f"/nodes/{n}/firewall"
    # guest scope
    if vmid is None:
        raise ProximoError("vmid is required for guest scope")
    if kind is None:
        kind = "lxc"
    vmid = _check_vmid(vmid)
    kind = _check_kind(kind)
    return f"/nodes/{n}/{kind}/{vmid}/firewall"


# ---------------------------------------------------------------------------
# READ operations (no confirm-gate; audited at server layer)
# ---------------------------------------------------------------------------

def firewall_rules_list(
    api,
    scope: str = "cluster",
    node: str | None = None,
    vmid: str | None = None,
    kind: str | None = None,
) -> list[dict]:
    """List all firewall rules for the given scope.

    GET /cluster/firewall/rules
    GET /nodes/{node}/firewall/rules
    GET /nodes/{node}/{kind}/{vmid}/firewall/rules

    Returns a list of rule dicts: {pos, action, type, enable, comment, …}.
    Reads are audited at the server layer (no confirm-gate needed).
    """
    base = _fw_base(api, scope, node, vmid, kind)
    return api._get(f"{base}/rules") or []


def firewall_options_get(
    api,
    scope: str = "cluster",
    node: str | None = None,
    vmid: str | None = None,
    kind: str | None = None,
) -> dict:
    """Get firewall options (enable flag, policy, log rate, …) for the given scope.

    GET /cluster/firewall/options
    GET /nodes/{node}/firewall/options
    GET /nodes/{node}/{kind}/{vmid}/firewall/options

    Returns a dict from PVE; fields vary by scope (e.g. 'enable', 'policy_in', 'policy_out').
    Reads are audited at the server layer (no confirm-gate needed).
    """
    base = _fw_base(api, scope, node, vmid, kind)
    return api._get(f"{base}/options") or {}


def security_groups_list(api) -> list[dict]:
    """List cluster-wide security groups.

    GET /cluster/firewall/groups

    Returns a list of group dicts: {group, comment, digest}.
    Cluster-scope only — node/guest scopes do not expose this endpoint.
    Reads are audited at the server layer (no confirm-gate needed).

    Shape risk: only cluster scope is assumed to expose this endpoint; node/guest
    may return 404. Confirm at live smoke.
    """
    return api._get("/cluster/firewall/groups") or []


def ipset_list(
    api,
    scope: str = "cluster",
    node: str | None = None,
    vmid: str | None = None,
    kind: str | None = None,
) -> list[dict]:
    """List IP sets for the given scope.

    GET /cluster/firewall/ipset
    GET /nodes/{node}/firewall/ipset
    GET /nodes/{node}/{kind}/{vmid}/firewall/ipset

    Returns a list of IPSet dicts.

    Shape risk: node/guest scope ipset endpoints may not exist on all PVE versions.
    Confirm at live smoke if using non-cluster scopes.
    """
    base = _fw_base(api, scope, node, vmid, kind)
    return api._get(f"{base}/ipset") or []


# ---------------------------------------------------------------------------
# MUTATION operations — PLAN-gated + audited at the server layer
# ---------------------------------------------------------------------------

def firewall_rule_add(
    api,
    action: str,
    direction: str = "in",
    scope: str = "cluster",
    node: str | None = None,
    vmid: str | None = None,
    kind: str | None = None,
    source: str | None = None,
    dest: str | None = None,
    proto: str | None = None,
    dport: str | None = None,
    sport: str | None = None,
    comment: str | None = None,
    enable: bool = True,
) -> None:
    """Add a new firewall rule. Appends to the end of the rule list.

    POST /cluster/firewall/rules
    POST /nodes/{node}/firewall/rules
    POST /nodes/{node}/{kind}/{vmid}/firewall/rules

    Returns None (synchronous; PVE returns null data on success).

    MUTATION — confirm-gated + audited at the server layer.
    No UNDO: firewall config is not in guest disk snapshots; revert manually.

    Shape risk: PVE uses 'type' internally but callers pass action (ACCEPT/DROP/REJECT).
    The 'type' field (in/out/group) is the direction/type parameter. Confirm param
    names match live API at smoke time.
    """
    action = _check_action(action)
    direction = _check_direction(direction)
    base = _fw_base(api, scope, node, vmid, kind)
    data: dict = {
        "action": action,
        "type": direction,
        "enable": 1 if enable else 0,
    }
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
    if comment is not None:
        data["comment"] = comment
    # MUTATION — confirm-gated + audited at the server layer.
    return api._post(f"{base}/rules", data)


def firewall_rule_remove(
    api,
    pos: int,
    scope: str = "cluster",
    node: str | None = None,
    vmid: str | None = None,
    kind: str | None = None,
) -> None:
    """Delete a firewall rule by position.

    DELETE /cluster/firewall/rules/{pos}
    DELETE /nodes/{node}/firewall/rules/{pos}
    DELETE /nodes/{node}/{kind}/{vmid}/firewall/rules/{pos}

    Returns None (synchronous; PVE returns null on success).

    MUTATION — confirm-gated + audited at the server layer.
    No UNDO: firewall config is not in guest disk snapshots; revert by re-adding.

    WARNING: positions shift after inserts/deletes. Always verify the current rule
    list before removing by position to avoid removing the wrong rule.
    """
    pos = _check_pos(pos)
    base = _fw_base(api, scope, node, vmid, kind)
    # Re-read rules at op time to obtain the PVE digest for optimistic-locking.
    # Shape risk: whether GET …/firewall/rules surfaces a 'digest' field is uncertain until
    # live smoke. If no digest is available, we abort with ProximoError rather than
    # silently proceeding without a lock (fail-closed).
    rules = api._get(f"{base}/rules") or []
    digest = next((r.get("digest") for r in rules if r.get("digest")), None)
    if digest is None:
        raise ProximoError(
            f"firewall_rule_remove: could not obtain a digest from {base}/rules — "
            "aborting to prevent undetected concurrent modification (shape risk: confirm "
            "at live smoke whether this PVE version returns a digest on the rules list)"
        )
    # MUTATION — confirm-gated + audited at the server layer.
    return api._delete(f"{base}/rules/{pos}", {"digest": digest})


def firewall_rule_update(
    api,
    pos: int,
    scope: str = "cluster",
    node: str | None = None,
    vmid: str | None = None,
    kind: str | None = None,
    action: str | None = None,
    direction: str | None = None,
    source: str | None = None,
    dest: str | None = None,
    proto: str | None = None,
    dport: str | None = None,
    sport: str | None = None,
    comment: str | None = None,
    enable: bool | None = None,
) -> None:
    """Update an existing firewall rule at position `pos`.

    PUT /cluster/firewall/rules/{pos}
    PUT /nodes/{node}/firewall/rules/{pos}
    PUT /nodes/{node}/{kind}/{vmid}/firewall/rules/{pos}

    Returns None (synchronous; PVE returns null on success).

    MUTATION — confirm-gated + audited at the server layer.
    No UNDO: firewall config is not in guest disk snapshots.

    WARNING: positions shift after inserts/deletes. Verify the current rule list
    before updating by position to avoid updating the wrong rule.

    Backend dependency: calls api._put() — this method MUST be added to ApiBackend
    before live use (backends.py only has _get/_post/_delete). Add one line mirroring
    _delete to unblock. Tests fake _put on the mock.
    """
    pos = _check_pos(pos)
    base = _fw_base(api, scope, node, vmid, kind)
    data: dict = {}
    if action is not None:
        data["action"] = _check_action(action)
    if direction is not None:
        data["type"] = _check_direction(direction)
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
    if comment is not None:
        data["comment"] = comment
    if enable is not None:
        data["enable"] = 1 if enable else 0
    if not data:
        raise ProximoError("firewall_rule_update requires at least one field to update")
    # Re-read rules at op time to obtain the PVE digest for optimistic-locking.
    # Shape risk: same as firewall_rule_remove — confirm at live smoke.
    # The empty-data guard runs BEFORE we add the digest so that guard stays reliable.
    rules = api._get(f"{base}/rules") or []
    digest = next((r.get("digest") for r in rules if r.get("digest")), None)
    if digest is None:
        raise ProximoError(
            f"firewall_rule_update: could not obtain a digest from {base}/rules — "
            "aborting to prevent undetected concurrent modification (shape risk: confirm "
            "at live smoke whether this PVE version returns a digest on the rules list)"
        )
    data["digest"] = digest
    # MUTATION — confirm-gated + audited at the server layer.
    return api._put(f"{base}/rules/{pos}", data)


def firewall_set_enabled(
    api,
    enabled: bool,
    scope: str = "cluster",
    node: str | None = None,
    vmid: str | None = None,
    kind: str | None = None,
) -> None:
    """Toggle the firewall on or off for the given scope.

    PUT /cluster/firewall/options    body: {enable: 0|1}
    PUT /nodes/{node}/firewall/options
    PUT /nodes/{node}/{kind}/{vmid}/firewall/options

    Returns None (synchronous; PVE returns null on success).

    MUTATION — confirm-gated + audited at the server layer.
    No UNDO: firewall config is not in guest disk snapshots.

    HIGH-RISK operation (both directions):
    - ENABLING: if no ACCEPT rules exist for SSH (22) or the PVE web UI (8006),
      the default-DROP policy can instantly lock you out of the host.
    - DISABLING: immediately strips all firewall protection from the scope.
    - Cluster scope is the master kill-switch for ALL nodes and guests.

    Backend dependency: calls api._put() — must be added to ApiBackend before live use.
    """
    base = _fw_base(api, scope, node, vmid, kind)
    data = {"enable": 1 if enabled else 0}
    # HIGH-RISK MUTATION — confirm-gated + audited at the server layer.
    return api._put(f"{base}/options", data)


# ---------------------------------------------------------------------------
# PLAN factories — pure functions (no I/O except where noted)
# ---------------------------------------------------------------------------

def _scope_label(scope: str, node: str | None, vmid: str | None, kind: str | None) -> str:
    """Human-readable scope string for blast_radius / change messages."""
    if scope == "cluster":
        return "cluster (all nodes and guests)"
    if scope == "node":
        return f"node/{node or 'default'}"
    return f"{kind or 'lxc'}/{vmid}"


def plan_firewall_rule_add(
    action: str,
    direction: str = "in",
    scope: str = "cluster",
    node: str | None = None,
    vmid: str | None = None,
    kind: str | None = None,
    source: str | None = None,
    dest: str | None = None,
    dport: str | None = None,
) -> Plan:
    """Preview adding a firewall rule. PURE — no API call needed.

    RISK_MEDIUM floor: a misplaced ACCEPT/DROP rule can affect connectivity without
    warning. The plan surfaces scope, direction, action, and key address/port fields
    so the caller can verify the rule before confirming.

    Note: the absence of HIGH is NOT a safety signal — rule classification is heuristic.
    A DROP on port 22 or 8006 can cause a lockout.
    """
    action = _check_action(action)
    direction = _check_direction(direction)
    _check_scope(scope)

    scope_label = _scope_label(scope, node, vmid, kind)
    rule_summary = f"action={action}, type={direction}"
    if source:
        rule_summary += f", source={source}"
    if dest:
        rule_summary += f", dest={dest}"
    if dport:
        rule_summary += f", dport={dport}"

    return Plan(
        action="pve_firewall_rule_add",
        target=f"firewall/{scope}",
        change=f"add firewall rule on {scope_label}: {rule_summary}",
        current={},
        blast_radius=[
            f"adds a firewall rule to {scope_label}: {rule_summary}",
            "rule is appended — positions of existing rules are not shifted",
            "a misplaced DROP/REJECT can interrupt connectivity; a misplaced ACCEPT can open access",
            "no UNDO: firewall config is not in guest snapshots; revert by removing this rule",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "firewall rule changes affect network connectivity — silent-mistake-prone",
            "absence of HIGH is NOT a safety signal (heuristic only)",
        ],
    )


def plan_firewall_rule_remove(
    api,
    pos: int,
    scope: str = "cluster",
    node: str | None = None,
    vmid: str | None = None,
    kind: str | None = None,
) -> Plan:
    """Preview removing a firewall rule at position `pos`.

    Reads firewall_rules_list (a safe read) to surface what rule is at the given
    position, so the caller sees exactly what will be removed.

    RISK_MEDIUM floor. Removing the wrong rule (e.g. the ACCEPT for SSH/8006) is
    a lockout. Plan discloses the rule at the given position.

    Note: positions SHIFT after every insert or delete. Always re-list rules and
    confirm the position before removing.
    """
    pos = _check_pos(pos)
    _check_scope(scope)

    scope_label = _scope_label(scope, node, vmid, kind)
    current: dict = {}
    rule_desc = f"rule at position {pos}"
    check_error: str | None = None

    try:
        rules = firewall_rules_list(api, scope, node, vmid, kind) or []
        # PVE rule lists include a 'pos' field; find the matching entry.
        found = next((r for r in rules if r.get("pos") == pos), None)
        if found:
            current = {k: found[k] for k in ("pos", "action", "type", "source", "dest",
                                               "dport", "sport", "proto", "enable", "comment")
                       if k in found}
            rule_desc = (
                f"rule at pos={pos}: action={found.get('action', '?')}, "
                f"type={found.get('type', '?')}"
            )
            if found.get("source"):
                rule_desc += f", source={found['source']}"
            if found.get("dest"):
                rule_desc += f", dest={found['dest']}"
            if found.get("dport"):
                rule_desc += f", dport={found['dport']}"
    except Exception as e:
        check_error = type(e).__name__

    if check_error is not None:
        blast = [
            f"rule lookup failed ({check_error}) — could not confirm what rule is at position {pos}; "
            "removal may affect the wrong rule or fail",
            "positions SHIFT after inserts/deletes — re-list rules before confirming",
            "no UNDO: firewall config is not in guest snapshots",
        ]
        reasons = [
            f"rule lookup for position {pos} failed — cannot confirm what is removed",
            "absence of HIGH is NOT a safety signal",
        ]
    else:
        blast = [
            f"removes {rule_desc} from {scope_label}",
            "positions SHIFT after this removal — re-list rules if doing further edits",
            "removing an ACCEPT rule for SSH (22) or PVE UI (8006) can cause a lockout",
            "no UNDO: firewall config is not in guest snapshots; revert by re-adding",
        ]
        reasons = [
            "firewall rule removal affects connectivity — verify the rule before confirming",
            "absence of HIGH is NOT a safety signal (heuristic only)",
        ]

    return Plan(
        action="pve_firewall_rule_remove",
        target=f"firewall/{scope}/rules/{pos}",
        change=f"remove {rule_desc} from {scope_label}",
        current=current,
        blast_radius=blast,
        risk=RISK_MEDIUM,
        risk_reasons=reasons,
    )


def plan_firewall_rule_update(
    api,
    pos: int,
    scope: str = "cluster",
    node: str | None = None,
    vmid: str | None = None,
    kind: str | None = None,
    **new_fields,
) -> Plan:
    """Preview updating a firewall rule at position `pos`.

    Reads firewall_rules_list (a safe read) to surface the rule's current state
    so the caller can compare before/after. RISK_MEDIUM floor (same connectivity risk as add/remove).

    Note: positions SHIFT after inserts/deletes; re-list before updating.
    Backend dependency: calls api._put() at execute time.
    """
    pos = _check_pos(pos)
    _check_scope(scope)
    # Validate action/direction in new_fields before the safe-read, mirroring the op-layer checks.
    if "action" in new_fields:
        new_fields["action"] = _check_action(new_fields["action"])
    if "direction" in new_fields:
        new_fields["direction"] = _check_direction(new_fields["direction"])

    scope_label = _scope_label(scope, node, vmid, kind)
    current: dict = {}
    rule_desc = f"rule at position {pos}"
    check_error: str | None = None

    try:
        rules = firewall_rules_list(api, scope, node, vmid, kind) or []
        found = next((r for r in rules if r.get("pos") == pos), None)
        if found:
            current = {k: found[k] for k in ("pos", "action", "type", "source", "dest",
                                               "dport", "sport", "proto", "enable", "comment")
                       if k in found}
            rule_desc = (
                f"rule at pos={pos}: action={found.get('action', '?')}, "
                f"type={found.get('type', '?')}"
            )
    except Exception as e:
        check_error = type(e).__name__

    changed_fields = ", ".join(f"{k}={v!r}" for k, v in new_fields.items()) if new_fields else "(no fields)"

    if check_error is not None:
        blast = [
            f"rule lookup failed ({check_error}) — could not read current state of {rule_desc}; "
            "update may affect the wrong rule or fail",
            "positions SHIFT after inserts/deletes — re-list rules before confirming",
            "no UNDO: firewall config is not in guest snapshots",
        ]
        reasons = [
            f"rule lookup for position {pos} failed — cannot compare before/after state",
            "absence of HIGH is NOT a safety signal",
        ]
    else:
        blast = [
            f"updates {rule_desc} on {scope_label}: changes → {changed_fields}",
            "positions SHIFT after inserts/deletes; verify position before updating",
            "a changed DROP/REJECT can affect connectivity; a changed ACCEPT can open access",
            "no UNDO: firewall config is not in guest snapshots; revert by re-updating",
        ]
        reasons = [
            "firewall rule update affects connectivity — silent-mistake-prone",
            "absence of HIGH is NOT a safety signal (heuristic only)",
        ]

    return Plan(
        action="pve_firewall_rule_update",
        target=f"firewall/{scope}/rules/{pos}",
        change=f"update {rule_desc} on {scope_label}: {changed_fields}",
        current=current,
        blast_radius=blast,
        risk=RISK_MEDIUM,
        risk_reasons=reasons,
    )


def plan_firewall_set_enabled(
    api,
    enabled: bool,
    scope: str = "cluster",
    node: str | None = None,
    vmid: str | None = None,
    kind: str | None = None,
) -> Plan:
    """Preview toggling the firewall on or off.

    Reads firewall_options_get (a safe read) to surface the current enable state.
    RISK_HIGH both directions:
    - ENABLING: default-DROP can lock you out (SSH/8006) if ACCEPT rules are absent.
    - DISABLING: immediately strips all firewall protection from the scope.
    - Cluster scope = master kill-switch for every node and guest.
    """
    _check_scope(scope)

    scope_label = _scope_label(scope, node, vmid, kind)
    current: dict = {}
    check_error: str | None = None

    try:
        opts = firewall_options_get(api, scope, node, vmid, kind) or {}
        if "enable" in opts:
            current = {"enable": opts["enable"]}
    except Exception as e:
        check_error = type(e).__name__

    action_str = "ENABLE" if enabled else "DISABLE"

    if check_error is not None:
        blast = [
            f"could NOT read current firewall state for {scope_label} ({check_error}); "
            f"proceeding would {action_str} the firewall — connectivity impact unknown",
        ]
        reasons = [
            f"current state unknown — cannot confirm whether {action_str} changes anything",
            "RISK_HIGH maintained: uncertainty is not a safety signal",
        ]
    elif enabled:
        blast = [
            f"ENABLES the firewall on {scope_label}",
            "if ACCEPT rules for SSH (22) or PVE web UI (8006) are absent, "
            "the default-DROP policy will IMMEDIATELY block access — potential LOCKOUT",
        ]
        if scope == "cluster":
            blast.append(
                "cluster scope is the master kill-switch — affects ALL nodes and guests"
            )
        reasons = [
            "enabling the firewall can instantly lock you out if ACCEPT rules are incomplete",
            "verify SSH (22) and PVE UI (8006) ACCEPT rules exist before confirming",
        ]
    else:
        blast = [
            f"DISABLES the firewall on {scope_label} — immediately strips ALL firewall protection",
        ]
        if scope == "cluster":
            blast.append(
                "cluster scope is the master kill-switch — disables firewall protection "
                "for ALL nodes and guests simultaneously"
            )
        blast.append(
            "no UNDO: firewall config is not in guest snapshots; re-enable manually"
        )
        reasons = [
            "disabling the firewall removes all protection from the scope — all traffic passes through",
        ]

    return Plan(
        action="pve_firewall_set_enabled",
        target=f"firewall/{scope}/options",
        change=f"{action_str} firewall on {scope_label}",
        current=current,
        blast_radius=blast,
        risk=RISK_HIGH,
        risk_reasons=reasons,
    )
