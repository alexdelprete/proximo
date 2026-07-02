"""PVE ACME accounts/plugins and cert order/renew/revoke tools.

Split out of proximo.server (2026-07-02) — see proximo/server.py's module
docstring for the funnel these wrappers depend on.
"""
from __future__ import annotations

import proximo.server as _proximo_server
from proximo.acme_certs import (
    acme_account_create,
    acme_account_delete,
    acme_account_update,
    acme_cert_order,
    acme_cert_renew,
    acme_cert_revoke,
    acme_plugin_create,
    acme_plugin_delete,
    acme_plugin_update,
    node_acme_config_set,
    plan_acme_account_create,
    plan_acme_account_delete,
    plan_acme_account_update,
    plan_acme_cert_order,
    plan_acme_cert_renew,
    plan_acme_cert_revoke,
    plan_acme_plugin_create,
    plan_acme_plugin_delete,
    plan_acme_plugin_update,
    plan_node_acme_domains_set,
)
from proximo.server import (
    _audited,
    _plan,
    tool,
)

# ============================================================================
# Plane G — ACME & TLS Certs
# ============================================================================

@tool()
def pve_acme_account_create(name: str, contact: str, tos_url: str | None = None,
                            directory: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: register a new ACME account with the CA. Dry-run by default.
    confirm=True to execute. Smoke-confirm: POST body shape (name in body) against a live PVE instance."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/acme/account/{name}"
    plan = _plan("pve_acme_account_create", tgt,
                 lambda: plan_acme_account_create(name, contact,
                                                   tos_url=tos_url, directory=directory))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_acme_account_create", tgt,
                    lambda: acme_account_create(api, name, contact,
                                                tos_url=tos_url, directory=directory),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_acme_account_update(name: str, contact: str | None = None,
                            confirm: bool = False) -> dict:
    """MUTATION: update ACME account contact info. Dry-run by default.
    confirm=True to execute. LOW risk — metadata update only, no cert impact."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/acme/account/{name}"
    plan = _plan("pve_acme_account_update", tgt,
                 lambda: plan_acme_account_update(api, name, contact=contact))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_acme_account_update", tgt,
                    lambda: acme_account_update(api, name, contact=contact),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_acme_account_delete(name: str, confirm: bool = False) -> dict:
    """MUTATION: IRREVERSIBLE — deactivate and delete an ACME account from the CA. Dry-run by default.
    confirm=True to execute. HIGH risk: TLS lockout at cert expiry if this is the only account."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/acme/account/{name}"
    plan = _plan("pve_acme_account_delete", tgt,
                 lambda: plan_acme_account_delete(api, name))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_acme_account_delete", tgt,
                    lambda: acme_account_delete(api, name),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_acme_plugin_create(plugin_id: str, plugin_type: str, dns_api: str | None = None,
                           data: str | None = None, disable: bool | None = None,
                           confirm: bool = False) -> dict:
    """MUTATION: create an ACME DNS challenge plugin. Dry-run by default.
    confirm=True to execute. dns_api = DNS provider name (e.g. 'cf', 'route53').
    Smoke-confirm: POST body shape (id in body) against a live PVE instance."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/acme/plugins/{plugin_id}"
    # dns_api maps to PVE's 'api' body field; the backend param is named 'backend', so no collision
    kw: dict = {}
    if dns_api is not None:
        kw["api"] = dns_api
    if data is not None:
        kw["data"] = data
    if disable is not None:
        kw["disable"] = disable
    plan = _plan("pve_acme_plugin_create", tgt,
                 lambda: plan_acme_plugin_create(plugin_id, plugin_type, **kw))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_acme_plugin_create", tgt,
                    lambda: acme_plugin_create(api, plugin_id, plugin_type, **kw),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_acme_plugin_update(plugin_id: str, dns_api: str | None = None,
                           data: str | None = None, disable: bool | None = None,
                           digest: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: update an ACME DNS challenge plugin. Dry-run by default.
    confirm=True to execute. MEDIUM risk — invalid credentials break renewal at next attempt."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/acme/plugins/{plugin_id}"
    # dns_api maps to PVE's 'api' field
    kw: dict = {}
    if dns_api is not None:
        kw["api"] = dns_api
    if data is not None:
        kw["data"] = data
    if disable is not None:
        kw["disable"] = disable
    if digest is not None:
        kw["digest"] = digest
    plan = _plan("pve_acme_plugin_update", tgt,
                 lambda: plan_acme_plugin_update(api, plugin_id, **kw))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_acme_plugin_update", tgt,
                    lambda: acme_plugin_update(api, plugin_id, **kw),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_acme_plugin_delete(plugin_id: str, confirm: bool = False) -> dict:
    """MUTATION: delete an ACME DNS challenge plugin. Dry-run by default.
    confirm=True to execute. HIGH risk: cert auto-renewal breaks — TLS lockout at cert expiry."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/acme/plugins/{plugin_id}"
    plan = _plan("pve_acme_plugin_delete", tgt,
                 lambda: plan_acme_plugin_delete(api, plugin_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_acme_plugin_delete", tgt,
                    lambda: acme_plugin_delete(api, plugin_id),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# ---------------------------------------------------------------------------
# ACME cert order plane — the node-side "what to issue" + "do it now"
# (closes the gap: account+plugin existed, but nothing set node ACME domains nor ordered a cert)
# ---------------------------------------------------------------------------

@tool()
def pve_node_acme_domains_set(account: str, domains: list[str], node: str | None = None,
                              plugin: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: set a node's ACME account + domains (PUT /nodes/{node}/config). Dry-run by default.

    The "what to issue" half of an ACME cert: pair with pve_acme_account_create +
    pve_acme_plugin_create, then issue with pve_acme_cert_order. plugin=<id> uses a DNS-01
    challenge (written as acmedomain0..N=domain=...,plugin=...); omit plugin for standalone
    http-01 (domains ride in acme=...,domains=...). REPLACE semantics: stale acmedomainN entries
    are removed, not merged. MEDIUM — config only, no cert is issued by this step. confirm=True
    to execute. Smoke-confirm: node-config body shape against a live PVE instance."""
    cfg, api, _, _ = _proximo_server._svc()
    n = node or cfg.node
    tgt = f"node/{n}/config:acme"
    plan = _plan("pve_node_acme_domains_set", tgt,
                 lambda: plan_node_acme_domains_set(api, n, account, domains, plugin))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_acme_domains_set", tgt,
                    lambda: node_acme_config_set(api, n, account, domains, plugin),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_acme_cert_order(node: str | None = None, force: bool = False,
                        confirm: bool = False) -> dict:
    """MUTATION: order a NEW ACME TLS certificate for the node's configured ACME domains. Dry-run
    by default. Async — returns a task UPID (poll pve_task_status/pve_task_wait).

    MEDIUM (lower than pve_node_cert_upload's HIGH): the cert is CA-validated and installed ONLY on
    a successful challenge — a failed challenge leaves the existing cert untouched, so it cannot
    lock you out. On success PVE reloads pveproxy. force=overwrite an existing custom cert.
    Revert to self-signed with pve_node_cert_delete. confirm=True to execute.
    Smoke-confirm: POST shape + async UPID against a live PVE instance."""
    cfg, api, _, _ = _proximo_server._svc()
    n = node or cfg.node
    tgt = f"node/{n}/certificates/acme/certificate"
    plan = _plan("pve_acme_cert_order", tgt, lambda: plan_acme_cert_order(n, force=force))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_acme_cert_order", tgt,
                    lambda: acme_cert_order(api, n, force=force),
                    mutation=True, outcome="submitted", detail={"confirmed": True, "force": force})


@tool()
def pve_acme_cert_renew(node: str | None = None, force: bool = False,
                        confirm: bool = False) -> dict:
    """MUTATION: renew the node's existing ACME TLS certificate. Dry-run by default. Async — returns
    a UPID. MEDIUM: CA-validated, installed only on success (a failure can't lock you out); reloads
    pveproxy on success. force=renew even if more than 30 days to expiry. confirm=True to execute.
    Smoke-confirm: PUT shape + async UPID against a live PVE instance."""
    cfg, api, _, _ = _proximo_server._svc()
    n = node or cfg.node
    tgt = f"node/{n}/certificates/acme/certificate"
    plan = _plan("pve_acme_cert_renew", tgt, lambda: plan_acme_cert_renew(n, force=force))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_acme_cert_renew", tgt,
                    lambda: acme_cert_renew(api, n, force=force),
                    mutation=True, outcome="submitted", detail={"confirmed": True, "force": force})


@tool()
def pve_acme_cert_revoke(node: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: IRREVERSIBLE — revoke the node's ACME TLS certificate at the CA. Dry-run by default.
    Async — returns a UPID. HIGH: a revoked cert cannot be un-revoked; only a NEW pve_acme_cert_order
    restores trust. To fall back to PVE's self-signed cert WITHOUT revoking at the CA, use
    pve_node_cert_delete instead. confirm=True to execute. Smoke-confirm: DELETE shape against a live
    PVE instance."""
    cfg, api, _, _ = _proximo_server._svc()
    n = node or cfg.node
    tgt = f"node/{n}/certificates/acme/certificate"
    plan = _plan("pve_acme_cert_revoke", tgt, lambda: plan_acme_cert_revoke(api, n))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_acme_cert_revoke", tgt,
                    lambda: acme_cert_revoke(api, n),
                    mutation=True, outcome="submitted", detail={"confirmed": True})
