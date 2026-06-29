"""ACME & TLS Certs plane — PVE cluster ACME account and plugin management.

Covers Plane G (PLAN + PROVE; HIGH risk on deletes — TLS cert renewal depends on
registered ACME accounts and DNS challenge plugins):
  - ACME accounts      (/cluster/acme/account)
  - ACME plugins       (/cluster/acme/plugins)

VERIFIED live shapes: None — all endpoint shapes carry "Smoke-confirm:" comments.

Security posture:
  - All path components validated with \\Z-anchored regexes (trailing-newline bypass rejected).
  - RISK_HIGH on deletes: ACME account deletion = IRREVERSIBLE (account key is gone; only a NEW
    registration can be made, not a restore). Plugin deletion breaks auto-renewal for every domain
    using that challenge method — TLS lockout if cert expires and renewal can't run.
  - plan_acme_account_delete and plan_acme_plugin_delete explicitly disclaim undo. Capturing current
    config is for EVIDENCE only — it does NOT enable restore.
"""

from __future__ import annotations

import re

from .backends import ProximoError
from .planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM, Plan

# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

# ACME account name: path segment in /cluster/acme/account/{name}
# Smoke-confirm: exact accepted charset against a live PVE instance.
_ACME_ACCOUNT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")

# ACME plugin ID: path segment in /cluster/acme/plugins/{id}
# Smoke-confirm: exact accepted charset against a live PVE instance.
_ACME_PLUGIN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


def _check_acme_account_name(name: str) -> str:
    # Do NOT strip — stripping defeats \\Z trailing-newline protection.
    s = str(name)
    if not _ACME_ACCOUNT_RE.match(s):
        raise ProximoError(
            f"invalid ACME account name: {name!r} "
            "(must start with alnum, then alnum/_/-, <=64 chars, no slash)"
        )
    return s


def _check_acme_plugin_id(plugin_id: str) -> str:
    s = str(plugin_id)
    if not _ACME_PLUGIN_ID_RE.match(s):
        raise ProximoError(
            f"invalid ACME plugin ID: {plugin_id!r} "
            "(must start with alnum, then alnum/_/-, <=64 chars, no slash)"
        )
    return s


# ---------------------------------------------------------------------------
# ACME account operations
# ---------------------------------------------------------------------------

def acme_account_get(api, name: str) -> dict:
    """Get one ACME account config.

    GET /cluster/acme/account/{name}
    Smoke-confirm: exact response shape (contact, directory, location, tos, ...).
    """
    _check_acme_account_name(name)
    return api._get(f"/cluster/acme/account/{name}") or {}


def acme_account_create(api, name: str, contact: str, **kw) -> None:
    """Register a new ACME account with the CA.

    POST /cluster/acme/account
    Body: {name, contact, directory?, tos_url?, ...}
    Smoke-confirm: name in body vs path + exact accepted body fields.
    MUTATION — confirm-gated + audited at the server layer.
    """
    _check_acme_account_name(name)
    data = {"name": name, "contact": contact, **kw}
    # MUTATION — confirm-gated + audited at the server layer.
    api._post("/cluster/acme/account", {k: v for k, v in data.items() if v is not None})


def acme_account_update(api, name: str, **kw) -> None:
    """Update ACME account contact info.

    PUT /cluster/acme/account/{name}
    Body: {contact?, ...}
    Smoke-confirm: exact accepted body fields.
    MUTATION — confirm-gated + audited at the server layer.
    """
    _check_acme_account_name(name)
    # MUTATION — confirm-gated + audited at the server layer.
    api._put(f"/cluster/acme/account/{name}", {k: v for k, v in kw.items() if v is not None})


def acme_account_delete(api, name: str) -> None:
    """Deactivate and delete an ACME account from the CA.

    DELETE /cluster/acme/account/{name}
    Smoke-confirm: response shape (null or task ID).
    MUTATION — confirm-gated + audited at the server layer.
    """
    _check_acme_account_name(name)
    # MUTATION — confirm-gated + audited at the server layer.
    api._delete(f"/cluster/acme/account/{name}")


# ---------------------------------------------------------------------------
# ACME plugin operations
# ---------------------------------------------------------------------------

def acme_plugin_get(api, plugin_id: str) -> dict:
    """Get one ACME plugin config.

    GET /cluster/acme/plugins/{id}
    Smoke-confirm: exact response shape (type, data, api, ...).
    """
    _check_acme_plugin_id(plugin_id)
    return api._get(f"/cluster/acme/plugins/{plugin_id}") or {}


def acme_plugin_create(api, plugin_id: str, plugin_type: str, **kw) -> None:
    """Create an ACME DNS challenge plugin.

    POST /cluster/acme/plugins
    Body: {id, type, data?, api?, disable?, nodes?, validation-delay?, ...}
    Smoke-confirm: id in body vs path + exact accepted body fields.
    MUTATION — confirm-gated + audited at the server layer.
    """
    _check_acme_plugin_id(plugin_id)
    data = {"id": plugin_id, "type": plugin_type, **kw}
    # MUTATION — confirm-gated + audited at the server layer.
    api._post("/cluster/acme/plugins", {k: v for k, v in data.items() if v is not None})


def acme_plugin_update(api, plugin_id: str, **kw) -> None:
    """Update an ACME DNS challenge plugin.

    PUT /cluster/acme/plugins/{id}
    Body: {type?, data?, api?, disable?, nodes?, validation-delay?, digest?, ...}
    Smoke-confirm: exact accepted body fields.
    MUTATION — confirm-gated + audited at the server layer.
    """
    _check_acme_plugin_id(plugin_id)
    # MUTATION — confirm-gated + audited at the server layer.
    api._put(f"/cluster/acme/plugins/{plugin_id}", {k: v for k, v in kw.items() if v is not None})


def acme_plugin_delete(api, plugin_id: str) -> None:
    """Delete an ACME DNS challenge plugin.

    DELETE /cluster/acme/plugins/{id}
    Smoke-confirm: response shape (null or empty).
    MUTATION — confirm-gated + audited at the server layer.
    """
    _check_acme_plugin_id(plugin_id)
    # MUTATION — confirm-gated + audited at the server layer.
    api._delete(f"/cluster/acme/plugins/{plugin_id}")


# ---------------------------------------------------------------------------
# Plan factories — ACME accounts
# ---------------------------------------------------------------------------

def plan_acme_account_create(name: str, contact: str, **kw) -> Plan:
    """Plan an ACME account registration (additive, MEDIUM risk)."""
    _check_acme_account_name(name)
    return Plan(
        action="pve_acme_account_create",
        target=f"cluster/acme/account/{name}",
        change=f"register ACME account {name!r} (contact: {contact!r}): {kw}",
        current={},
        blast_radius=["registers a new ACME account with the CA (no existing config affected)"],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "sends account registration to the ACME CA directory",
            "depends on correct contact email + TOS acceptance",
        ],
        note=(
            "Additive config. Delete with pve_acme_account_delete to deactivate. "
            "Smoke-confirm: exact POST body shape (name in body vs path) against a live PVE instance."
        ),
    )


def plan_acme_account_update(api, name: str, **kw) -> Plan:
    """Plan an ACME account contact update. Reads current config for honesty."""
    _check_acme_account_name(name)
    current = acme_account_get(api, name)
    return Plan(
        action="pve_acme_account_update",
        target=f"cluster/acme/account/{name}",
        change=f"update ACME account {name!r}: {kw}",
        current=current,
        blast_radius=["updates contact info on the CA side (no cert impact)"],
        risk=RISK_LOW,
        risk_reasons=["contact metadata update — does not affect cert issuance or renewal"],
        note=(
            "No snapshot primitive on this plane. Current config captured above — "
            "re-apply contact via pve_acme_account_update to revert."
        ),
    )


def plan_acme_account_delete(api, name: str) -> Plan:
    """Plan an ACME account deletion. IRREVERSIBLE — see honesty note.

    Captures current config as EVIDENCE ONLY — this does NOT enable restore.
    The account key is gone; only a NEW CA registration can be made.
    """
    _check_acme_account_name(name)
    current = acme_account_get(api, name)
    return Plan(
        action="pve_acme_account_delete",
        target=f"cluster/acme/account/{name}",
        change=f"IRREVERSIBLE: deactivate and delete ACME account {name!r} from the CA",
        current=current,
        blast_radius=[
            "ACME account deactivated at the CA — no new cert orders or renewals possible",
            "any TLS cert using this account will NOT renew — TLS lockout at expiry",
            "domains depending on this account require re-registration with a new account",
        ],
        risk=RISK_HIGH,
        risk_reasons=[
            "IRREVERSIBLE: account key is destroyed; re-registration creates a NEW account, "
            "not a restore of this one",
            "TLS lockout risk: if this is the only ACME account, all auto-renewal stops",
        ],
        note=(
            "IRREVERSIBLE. Current config captured above is for EVIDENCE ONLY — "
            "it does NOT enable restore. The account key is not recoverable. "
            "A new account can be registered with pve_acme_account_create, "
            "but it will be a different CA account, not this one."
        ),
    )


# ---------------------------------------------------------------------------
# Plan factories — ACME plugins
# ---------------------------------------------------------------------------

def _redact_plugin_kw(kw: dict) -> dict:
    """Mask the DNS-provider credential blob before it enters a plan string.

    `data` carries the provider's API secrets (e.g. ``CF_Token=...``, ``AWS_SECRET_ACCESS_KEY=...``).
    plan.change is BOTH returned to the caller AND written to the tamper-evident PROVE ledger, so the
    raw value must never appear there — this is the one credential field that lacked a redaction path.
    """
    return {k: ("[redacted]" if k == "data" else v) for k, v in kw.items()}


def plan_acme_plugin_create(plugin_id: str, plugin_type: str, **kw) -> Plan:
    """Plan an ACME plugin creation (additive, MEDIUM risk)."""
    _check_acme_plugin_id(plugin_id)
    return Plan(
        action="pve_acme_plugin_create",
        target=f"cluster/acme/plugins/{plugin_id}",
        change=f"create ACME plugin {plugin_id!r} (type={plugin_type!r}): {_redact_plugin_kw(kw)}",
        current={},
        blast_radius=["adds a new ACME DNS challenge plugin (no existing config affected)"],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "DNS challenge plugin stores API credentials for the DNS provider",
            "incorrect credentials silently break cert issuance until renewal is attempted",
        ],
        note=(
            "Additive config. Delete with pve_acme_plugin_delete to remove. "
            "Smoke-confirm: exact POST body shape (id in body vs path) against a live PVE instance."
        ),
    )


def plan_acme_plugin_update(api, plugin_id: str, **kw) -> Plan:
    """Plan an ACME plugin update. Reads current config for honesty."""
    _check_acme_plugin_id(plugin_id)
    current = acme_plugin_get(api, plugin_id)
    return Plan(
        action="pve_acme_plugin_update",
        target=f"cluster/acme/plugins/{plugin_id}",
        change=f"update ACME plugin {plugin_id!r}: {_redact_plugin_kw(kw)}",
        current=current,
        blast_radius=[
            "changes challenge credentials for all domains using this plugin",
            "incorrect new credentials break cert renewal for those domains",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "modifies DNS provider credentials — invalid update breaks challenge at next renewal",
        ],
        note=(
            "No snapshot primitive on this plane. Current config captured above — "
            "re-apply it manually to revert."
        ),
    )


def plan_acme_plugin_delete(api, plugin_id: str) -> Plan:
    """Plan an ACME plugin deletion. HIGH risk — cert renewal breaks.

    Captures current config as EVIDENCE ONLY — credentials must be re-supplied on re-create.
    """
    _check_acme_plugin_id(plugin_id)
    current = acme_plugin_get(api, plugin_id)
    return Plan(
        action="pve_acme_plugin_delete",
        target=f"cluster/acme/plugins/{plugin_id}",
        change=f"delete ACME plugin {plugin_id!r}",
        current=current,
        blast_radius=[
            "all domains using this plugin can no longer complete DNS challenges",
            "cert renewal fails at next renewal attempt — TLS lockout at cert expiry",
            "challenge type (http-01 standalone fallback may not cover all domains)",
        ],
        risk=RISK_HIGH,
        risk_reasons=[
            "auto-renewal breaks for all domains referencing this plugin",
            "TLS lockout risk if no fallback challenge method is configured",
        ],
        note=(
            "No UNDO primitive on this plane. Current config captured above — "
            "re-create with pve_acme_plugin_create to restore, but credentials must be "
            "re-supplied; stored secrets are NOT returned by the GET endpoint."
        ),
    )
