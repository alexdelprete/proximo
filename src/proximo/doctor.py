"""DOCTOR — onboarding preflight: "is my config/token right, and what can this token DO?"

A read-only self-check a stranger runs FIRST, before wiring Proximo into an MCP client. It answers
the question raw 403s don't: *which* capability is missing and *how to grant it*. Same posture as
DIAGNOSE — advisory, never overclaims, surfaces incompleteness rather than implying a clean bill.

Pure-ish: it only does read-only API calls (`version`, `access/permissions`) + reads config. No
mutation, no exec. Routed through the PROVE ledger as a read by the server layer.
"""

from __future__ import annotations

_DOCTOR_NOTE = (
    "DOCTOR is a read-only preflight: it checks API reachability + the token's effective permissions "
    "and reports what this token CAN/CANNOT do. Capability gaps list the privilege + a role to grant. "
    "Absence of a capability is a config signal, not a Proximo error."
)

# (capability, required privs, role hint, match-mode). Translates raw PVE privilege names into
# "what you can actually do" + a fix for each gap. match-mode prevents OVERCLAIM:
#   "all"     — needs EVERY listed priv (most are single-priv; rollback/users are split so each is exact).
#   "any"     — interchangeable privs; any one suffices (the read/audit family).
#   "partial" — any one suffices but the held subset is named (distinct config domains).
# Rollback is its OWN row (NOT folded into snapshot): VM.Snapshot without VM.Snapshot.Rollback can
# create a restore point but CANNOT roll back — never imply the UNDO path works when it doesn't.
_CAPABILITIES: list[tuple[str, list[str], str, str]] = [
    ("Read / inspect — DIAGNOSE, lists, status",
     ["VM.Audit", "Sys.Audit", "Datastore.Audit"], "PVEAuditor", "any"),
    ("Power guests — start / stop / reboot",
     ["VM.PowerMgmt"], "PVEVMAdmin", "all"),
    ("Snapshots — create restore points",
     ["VM.Snapshot"], "PVEVMAdmin", "all"),
    ("Rollback — the UNDO pillar",
     ["VM.Snapshot.Rollback"], "PVEVMAdmin", "all"),
    ("Reconfigure guests — cpu / memory / disk / network",
     ["VM.Config.Memory", "VM.Config.Disk", "VM.Config.Network", "VM.Config.Options", "VM.Config.CPU"],
     "PVEVMAdmin", "partial"),
    ("Create / clone / destroy guests",
     ["VM.Allocate"], "PVEVMAdmin", "all"),
    ("Back up guests",
     ["VM.Backup"], "PVEVMAdmin", "all"),
    ("Define / remove storage",
     ["Datastore.Allocate"], "PVEDatastoreAdmin", "all"),
    ("Firewall + node configuration",
     ["Sys.Modify"], "PVESysAdmin", "all"),
    ("Manage tokens / ACLs",
     ["Permissions.Modify"], "PVEUserAdmin", "all"),
    ("Manage users",
     ["User.Modify"], "PVEUserAdmin", "all"),
]


def _collect_privs(perms: object) -> dict[str, list[str]]:
    """Flatten the PVE /access/permissions map ({path: {priv: 1}}) to {priv: [paths it's held on]}.
    Tolerant of either the full map or a single-path dict; ignores falsy/zero grants."""
    out: dict[str, list[str]] = {}
    if not isinstance(perms, dict):
        return out
    # Single-path shape ({priv: 1}) vs full map ({path: {priv: 1}}): detect nested dict values.
    nested = any(isinstance(v, dict) for v in perms.values())
    items = perms.items() if nested else [("/", perms)]
    for path, pmap in items:
        if not isinstance(pmap, dict):
            continue
        for priv, val in pmap.items():
            if val:
                out.setdefault(priv, []).append(str(path))
    return out


def _scope(paths: list[str]) -> str:
    return "everywhere (/)" if "/" in paths else ", ".join(sorted(set(paths)))


def doctor_check(api) -> dict:
    """Read-only preflight. `api` is an ApiBackend (or a duck-type with version/access_permissions/
    config). Returns an advisory report with reachable, version, token can/cannot, config, flags."""
    report: dict = {"note": _DOCTOR_NOTE}
    flags: list[str] = []
    complete = True
    cfg = getattr(api, "config", None)

    # 1) Connectivity + auth — the single most common stranger failure.
    try:
        ver = api.version()
        report["reachable"] = True
        report["version"] = ver if isinstance(ver, dict) else {"raw": ver}
    except Exception as e:
        report["reachable"] = False
        report["version"] = {"error": type(e).__name__}
        flags.append(
            "cannot reach / authenticate to the Proxmox API — check PROXIMO_API_BASE_URL, the token "
            "file at PROXIMO_TOKEN_PATH, and TLS/CA (PROXIMO_CA_BUNDLE / PROXIMO_VERIFY_TLS). "
            "Preflight cannot evaluate permissions until this connects."
        )
        complete = False

    # 2) Token effective permissions -> capability map (only if we got through the door).
    if report["reachable"]:
        try:
            privs = _collect_privs(api.access_permissions())
            can: list[dict] = []
            cannot: list[dict] = []
            for human, needs, role, mode in _CAPABILITIES:
                held = [p for p in needs if p in privs]
                satisfied = bool(held) if mode in ("any", "partial") else len(held) == len(needs)
                if satisfied:
                    paths = [path for p in held for path in privs[p]]
                    label = human
                    if mode == "partial" and len(held) < len(needs):
                        label = f"{human} [partial — only: {', '.join(held)}]"
                    can.append({"capability": label, "via": held, "scope": _scope(paths)})
                else:
                    missing = [p for p in needs if p not in privs] or needs
                    cannot.append({
                        "capability": human,
                        "needs": missing,
                        "hint": (f"grant {role} (or any role containing {missing[0]}) to your token: "
                                 f"pveum acl modify <path> --tokens '<user@realm!tokenid>' --roles {role} "
                                 f"(privsep tokens: grant the role to the USER too)"),
                    })
            report["token"] = {"can": can, "cannot": cannot}
            if not privs:
                flags.append(
                    "token authenticates but has NO permissions on any path — it cannot read or act. "
                    "Grant it a role (e.g. PVEAuditor to start) via pveum acl modify."
                )
        except Exception as e:
            report["token"] = {"error": type(e).__name__}
            flags.append(
                "could not read token permissions (/access/permissions) — the token likely lacks even "
                "Sys.Audit, or the API rejected it. Capability map unavailable; diagnosis incomplete."
            )
            complete = False

    # 3) Config readiness — the safety/posture signals a stranger needs to see.
    if cfg is not None:
        allow = getattr(cfg, "ct_allowlist", frozenset()) or frozenset()
        report["config"] = {
            "node": getattr(cfg, "node", None),
            "api_base_url": getattr(cfg, "api_base_url", None),
            "exec_enabled": bool(getattr(cfg, "enable_exec", False)),
            "tls_verify": bool(getattr(cfg, "verify_tls", True)),
            "ca_bundle": getattr(cfg, "ca_bundle", None),
            "ct_allowlist": ("none (exec deny-all)" if not allow
                             else "ALL (*)" if "*" in allow else f"{len(allow)} CTID(s)"),
        }
        if not getattr(cfg, "verify_tls", True) and not getattr(cfg, "ca_bundle", None):
            flags.append("TLS verification is OFF with no CA bundle — API traffic is not cert-validated.")
        if getattr(cfg, "enable_exec", False) and not allow:
            flags.append("exec is ENABLED but the CT allowlist is empty (deny-all) — no container is reachable.")

    report["flags"] = flags
    report["complete"] = complete
    return report
