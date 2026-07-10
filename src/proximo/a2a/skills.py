"""The A2A skill registry — Proximo's curated *slice* + the PLAN-by-default guard.

This module is the CONTRACT the rest of the A2A face is built on. It is pure Python with NO
a2a-sdk import, so it is importable everywhere and the trust guard is unit-testable in isolation.

Two load-bearing properties live here, on purpose:

1. THE SLICE (not the whole 145). An external agent gets a deliberately conservative subset:
   reads/diagnostics + bounded, non-lockout mutations (power, snapshot create/delete, config
   set/revert, backup). NB: snapshot *delete* removes a restore point permanently — it is bounded
   (one guest's snapshot), not lockout-class, but it is NOT reversible; the "conservative" property
   here is bounded blast radius, not undoability. The irreversible-AND-lockout / secret-bearing tools
   (delete_guest, rollback,
   template_convert, firewall toggles, token create/revoke, acl_modify, network/sdn apply,
   storage delete, in-container exec/psql, PBS mutations) are NOT exposed over A2A in v1 — they
   stay MCP-only. This is a documented boundary, not a silent omission (see EXCLUDED_FROM_SLICE).

2. PLAN-by-default, enforced in ``validate_and_build``. A mutating skill is executed ONLY when the
   caller *explicitly* passes ``confirm=true``. Otherwise the routed tool is called WITHOUT confirm
   and returns a recorded PLAN — never a mutation. The guard never *injects* confirm and never
   defaults it on. Because the routed ``proximo.server`` tools already enforce "no plan, no mutation",
   this is defense-in-depth: even a future change to a tool's default cannot make an A2A call mutate
   without the caller's explicit confirm reaching it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .. import server

# --- param schema ------------------------------------------------------------------------------

# JSON-shaped types a skill param may take (A2A DataParts arrive already JSON-typed).
_PY_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),          # NB: bool is excluded explicitly in _type_ok (bool is a subclass of int)
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
}


@dataclass(frozen=True)
class A2AParam:
    name: str
    type: str
    required: bool = False
    description: str = ""


@dataclass(frozen=True)
class A2ASkill:
    """One A2A skill = one routed Proximo tool, plus its public param contract.

    ``tool`` is the ``proximo.server`` function the skill calls. ``mutating`` marks skills whose
    routed tool can change state; for those, ``confirm`` is an implicit, optional boolean param
    (PLAN-by-default — see validate_and_build) and is NOT declared in ``params``.
    """

    id: str
    name: str
    description: str
    tool: Callable[..., Any]
    params: tuple[A2AParam, ...] = ()
    mutating: bool = False
    tags: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()

    @property
    def required_params(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.params if p.required)


class A2AParamError(ValueError):
    """Raised when an inbound A2A skill invocation has missing/unknown/mistyped params.

    The executor turns this into a clean failed-task message — it is the input-validation boundary
    between an untrusted calling agent and Proximo's trust core.
    """


def _type_ok(value: Any, type_name: str) -> bool:
    expected = _PY_TYPES.get(type_name)
    if expected is None:  # unknown declared type -> reject rather than wave through (fail-closed)
        return False
    # bool is a subclass of int; never let a bool satisfy "integer" or an int satisfy "boolean".
    if isinstance(value, bool):
        return type_name == "boolean"
    return isinstance(value, expected)


# --- the curated slice -------------------------------------------------------------------------

_KIND = A2AParam("kind", "string", False, "guest kind: 'lxc' or 'qemu'")
_NODE = A2AParam("node", "string", False, "Proxmox node name (defaults to the configured node)")


def _vmid(desc: str = "guest id (VMID/CTID)") -> A2AParam:
    return A2AParam("vmid", "string", True, desc)


SKILLS: tuple[A2ASkill, ...] = (
    # --- reads / diagnostics ---
    A2ASkill(
        "node_status", "Node status", "Health and resource status of a Proxmox node.",
        server.pve_node_status, (_NODE,), mutating=False,
        tags=("pve", "read", "diagnostics"), examples=("What's the status of the node?",),
    ),
    A2ASkill(
        "list_guests", "List guests", "List all VMs and LXC containers on a node, with state.",
        server.pve_list_guests, (_NODE,), mutating=False,
        tags=("pve", "read"), examples=("List the guests.",),
    ),
    A2ASkill(
        "guest_status", "Guest status", "Status/config of one guest.",
        server.pve_guest_status, (_vmid(), _KIND, _NODE), mutating=False,
        tags=("pve", "read"), examples=("What is the status of CT 102?",),
    ),
    A2ASkill(
        "diagnose_node", "Diagnose node",
        "READ-ONLY evidence battery for a node: status, storage usage, recent failed tasks, advisory flags.",
        server.pve_diagnose, (_NODE,), mutating=False,
        tags=("pve", "read", "diagnostics"), examples=("What's wrong with the node?",),
    ),
    A2ASkill(
        "diagnose_container", "Diagnose container",
        "READ-ONLY 'what's broken' evidence for a container (API status + in-container battery if exec is enabled).",
        server.ct_diagnose, (A2AParam("ctid", "string", True, "container id"), _KIND, _NODE), mutating=False,
        tags=("pve", "read", "diagnostics"), examples=("Diagnose container 102.",),
    ),
    A2ASkill(
        "snapshot_list", "List snapshots", "List a guest's snapshots.",
        server.pve_snapshot_list, (_vmid(), _KIND, _NODE), mutating=False,
        tags=("pve", "read", "undo"), examples=("List snapshots for CT 102.",),
    ),
    A2ASkill(
        "storage_status", "Storage status", "Status of a storage (total/used/avail/enabled).",
        server.pve_storage_status, (A2AParam("storage", "string", True, "storage id"), _NODE), mutating=False,
        tags=("pve", "read", "storage"), examples=("How full is local-zfs?",),
    ),
    A2ASkill(
        "backup_list", "List backups", "List backup archives in a storage.",
        server.pve_backup_list, (A2AParam("storage", "string", True, "storage id"), _NODE), mutating=False,
        tags=("pve", "read", "backup"), examples=("List backups on the backup storage.",),
    ),
    A2ASkill(
        "config_get", "Get guest config", "Read a guest's current config.",
        server.pve_guest_config_get, (_vmid(), _KIND, _NODE), mutating=False,
        tags=("pve", "read", "config"), examples=("Show the config of CT 102.",),
    ),
    A2ASkill(
        "audit_verify", "Verify audit ledger",
        "PROVE: verify the tamper-evident audit ledger's hash chain is intact. Pass expected_head "
        "(your off-box-pinned head) to also catch tail truncation / forged append / wipe.",
        server.audit_verify,
        (A2AParam("expected_head", "string", False, "off-box-pinned head() hash; detects tail attacks"),),
        mutating=False,
        tags=("trust", "prove", "read"), examples=("Is the audit log intact?",),
    ),
    # --- reversible mutations (PLAN-by-default; confirm=true to execute) ---
    A2ASkill(
        "guest_power", "Power a guest",
        "MUTATION: start/stop/reboot/shutdown a guest. PLAN-by-default; pass confirm=true to execute.",
        server.pve_guest_power,
        (_vmid(), A2AParam("action", "string", True, "start | stop | reboot | shutdown"), _KIND, _NODE),
        mutating=True, tags=("pve", "mutation", "power"),
        examples=("Plan a reboot of CT 102.", "Stop CT 102 (confirm=true)."),
    ),
    A2ASkill(
        "snapshot_create", "Create snapshot",
        "MUTATION (additive): create a restore point. PLAN-by-default; confirm=true to execute.",
        server.pve_snapshot_create,
        (_vmid(), A2AParam("snapname", "string", True, "snapshot name"), _KIND, _NODE,
         A2AParam("description", "string", False, "optional description")),
        mutating=True, tags=("pve", "mutation", "undo"),
        examples=("Snapshot CT 102 as pre-change (confirm=true).",),
    ),
    A2ASkill(
        "snapshot_delete", "Delete snapshot",
        "MUTATION: delete a snapshot (removes a restore point). PLAN-by-default; confirm=true to execute.",
        server.pve_snapshot_delete,
        (_vmid(), A2AParam("snapname", "string", True, "snapshot name"), _KIND, _NODE,
         A2AParam("force", "boolean", False, "force-delete")),
        mutating=True, tags=("pve", "mutation"),
        examples=("Delete snapshot pre-change on CT 102 (confirm=true).",),
    ),
    A2ASkill(
        "config_set", "Set guest config",
        "MUTATION: edit a guest's config (cores/memory/net/onboot/...). PLAN shows the per-key diff; "
        "the prior config is captured for config_revert. PLAN-by-default; confirm=true to execute.",
        server.pve_guest_config_set,
        (_vmid(), A2AParam("changes", "object", True, "config keys to change"), _KIND, _NODE),
        mutating=True, tags=("pve", "mutation", "config"),
        examples=("Plan setting CT 102 memory to 2048.",),
    ),
    A2ASkill(
        "config_revert", "Revert guest config",
        "MUTATION (UNDO): re-apply a previously captured guest config (the prior_config from config_set). "
        "PLAN-by-default; confirm=true to execute.",
        server.pve_guest_config_revert,
        (_vmid(), A2AParam("prior_config", "object", True, "the prior_config captured by config_set"), _KIND, _NODE),
        mutating=True, tags=("pve", "mutation", "undo", "config"),
        examples=("Revert CT 102 to the prior config (confirm=true).",),
    ),
    A2ASkill(
        "backup", "Back up a guest",
        "MUTATION: vzdump a guest to a storage. PLAN-by-default; confirm=true to execute.",
        server.pve_backup,
        (_vmid(), A2AParam("storage", "string", True, "target storage id"),
         A2AParam("mode", "string", False, "snapshot | suspend | stop"),
         A2AParam("compress", "string", False, "zstd | gzip | lzo"), _KIND, _NODE),
        mutating=True, tags=("pve", "mutation", "backup"),
        examples=("Plan a backup of CT 102 to the backup storage.",),
    ),
)

SKILLS_BY_ID: dict[str, A2ASkill] = {s.id: s for s in SKILLS}

# Documented boundary: tools deliberately NOT exposed over A2A in v1 (irreversible / lockout-class /
# secret-bearing / near-root). They remain available over MCP. This is surfaced for transparency and
# guarded by a test so the slice can't silently grow into the dangerous plane.
EXCLUDED_FROM_SLICE: tuple[str, ...] = (
    "pve_delete_guest", "pve_rollback", "pve_template_convert",
    "pve_firewall_rule_add", "pve_firewall_rule_remove", "pve_firewall_rule_update",
    "pve_firewall_set_enabled", "pve_token_create", "pve_token_revoke", "pve_acl_modify",
    "network_apply", "sdn_apply", "pve_storage_content_delete", "pve_restore",
    "pve_disk_move", "pve_disk_resize", "ct_exec", "ct_psql",
)

CONFIRM_PARAM = "confirm"


def validate_and_build(skill: A2ASkill, raw_params: dict[str, Any] | None) -> dict[str, Any]:
    """Validate an inbound skill invocation and build the kwargs for the routed tool.

    Enforces, in pure testable code:
      * required params present;
      * no unknown params (an unknown key is rejected, not silently dropped);
      * declared params match their type;
      * PLAN-by-default: ``confirm`` is accepted ONLY for mutating skills, ONLY as a real bool, and
        is passed through ONLY when it is exactly ``True``. It is never injected and never defaulted.
        For a non-mutating skill, ``confirm`` is an unknown param (rejected).

    Raises A2AParamError on any violation.
    """
    raw = dict(raw_params or {})
    declared = {p.name: p for p in skill.params}
    kwargs: dict[str, Any] = {}

    # confirm is special-cased and removed from the unknown-key check below.
    confirm_present = CONFIRM_PARAM in raw
    confirm_value = raw.pop(CONFIRM_PARAM, None)

    # unknown params -> reject (fail-closed; don't pass arbitrary kwargs into the tool)
    unknown = set(raw) - set(declared)
    if unknown:
        raise A2AParamError(f"unknown param(s) for skill '{skill.id}': {sorted(unknown)}")

    # required present
    missing = [name for name in skill.required_params if name not in raw]
    if missing:
        raise A2AParamError(f"missing required param(s) for skill '{skill.id}': {missing}")

    # typed copy
    for name, value in raw.items():
        param = declared[name]
        if not _type_ok(value, param.type):
            raise A2AParamError(
                f"param '{name}' for skill '{skill.id}' must be {param.type}, got {type(value).__name__}"
            )
        kwargs[name] = value

    # PLAN-by-default confirm handling
    if confirm_present:
        if not skill.mutating:
            raise A2AParamError(f"skill '{skill.id}' is read-only; 'confirm' is not a valid param")
        if not isinstance(confirm_value, bool):
            raise A2AParamError("'confirm' must be a boolean")
        if confirm_value is True:
            kwargs[CONFIRM_PARAM] = True
        # confirm=false -> do NOT pass it; the tool's own default keeps it a dry-run PLAN.

    return kwargs
