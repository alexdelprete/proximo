"""PVE observability (node services/rrd/journal/syslog/dns/subscription/certs), notifications & metrics
endpoints, and hardware PCI/USB mappings.

Split out of proximo.server (2026-07-02) — see proximo/server.py's module
docstring for the funnel these wrappers depend on.
"""
from __future__ import annotations

import proximo.server as _proximo_server
from proximo.hw_mappings import (
    hardware_list,
    mapping_pci_create,
    mapping_pci_delete,
    mapping_pci_list,
    mapping_pci_update,
    mapping_usb_create,
    mapping_usb_delete,
    mapping_usb_list,
    mapping_usb_update,
    plan_mapping_pci_create,
    plan_mapping_pci_delete,
    plan_mapping_pci_update,
    plan_mapping_usb_create,
    plan_mapping_usb_delete,
    plan_mapping_usb_update,
)
from proximo.notifications import (
    metrics_server_delete,
    metrics_server_list,
    metrics_server_set,
    notification_endpoint_create,
    notification_endpoint_delete,
    notification_endpoint_list,
    notification_endpoint_update,
    notification_matcher_delete,
    notification_matcher_set,
    plan_metrics_server_delete,
    plan_metrics_server_set,
    plan_notification_endpoint_create,
    plan_notification_endpoint_delete,
    plan_notification_endpoint_update,
    plan_notification_matcher_delete,
    plan_notification_matcher_set,
    plan_notification_test,
)
from proximo.notifications import (
    notification_test as notification_test_op,
)
from proximo.observability import (
    node_certificates_info,
    node_dns_get,
    node_journal,
    node_rrddata,
    node_service_control,
    node_service_status,
    node_services_list,
    node_subscription,
    node_syslog,
    plan_node_service_control,
)
from proximo.server import (
    _audited,
    _plan,
    tool,
)

# --- Observability (REST API, read) ---

@tool()
def pve_node_services_list(node: str | None = None) -> list[dict]:
    """List all services on a PVE node, with state (read)."""
    cfg, api, _, _ = _proximo_server._svc()
    return _audited("pve_node_services_list", node or cfg.node,
                    lambda: node_services_list(api, node))


@tool()
def pve_node_service_status(service: str, node: str | None = None) -> dict:
    """Get the current state of a single service on a PVE node (read)."""
    cfg, api, _, _ = _proximo_server._svc()
    return _audited("pve_node_service_status", f"{node or cfg.node}/services/{service}",
                    lambda: node_service_status(api, service, node))


@tool()
def pve_node_rrddata(node: str | None = None, timeframe: str = "hour",
                     cf: str | None = None) -> list[dict]:
    """Get RRD telemetry (time-series) for a PVE node (read). timeframe: hour/day/week/month/year."""
    cfg, api, _, _ = _proximo_server._svc()
    return _audited("pve_node_rrddata", node or cfg.node,
                    lambda: node_rrddata(api, node, timeframe, cf))


@tool()
def pve_node_journal(node: str | None = None, lastentries: int = 100,
                     since: str | None = None, until: str | None = None) -> list[str]:
    """Fetch journal entries from a PVE node (read; returns log-line strings). lastentries capped at 5000."""
    cfg, api, _, _ = _proximo_server._svc()
    return _audited("pve_node_journal", node or cfg.node,
                    lambda: node_journal(api, node, lastentries, since, until))


@tool()
def pve_node_syslog(node: str | None = None, limit: int = 100) -> list[dict]:
    """Fetch syslog entries from a PVE node (read). limit capped at 5000."""
    cfg, api, _, _ = _proximo_server._svc()
    return _audited("pve_node_syslog", node or cfg.node,
                    lambda: node_syslog(api, node, limit))


@tool()
def pve_node_dns(node: str | None = None) -> dict:
    """Get the DNS configuration of a PVE node (read)."""
    cfg, api, _, _ = _proximo_server._svc()
    return _audited("pve_node_dns", node or cfg.node, lambda: node_dns_get(api, node))


@tool()
def pve_node_subscription(node: str | None = None) -> dict:
    """Get the subscription status of a PVE node (read)."""
    cfg, api, _, _ = _proximo_server._svc()
    return _audited("pve_node_subscription", node or cfg.node,
                    lambda: node_subscription(api, node))


@tool()
def pve_node_certificates(node: str | None = None) -> list[dict]:
    """List TLS certificates configured on a PVE node (read)."""
    cfg, api, _, _ = _proximo_server._svc()
    return _audited("pve_node_certificates", node or cfg.node,
                    lambda: node_certificates_info(api, node))


# --- Observability (mutation) ---

@tool()
def pve_node_service_control(service: str, action: str, node: str | None = None,
                             confirm: bool = False) -> dict:
    """MUTATION: start/stop/restart/reload a service on a PVE node. Dry-run by default — the
    PLAN flags lockout-class services (sshd/pveproxy/pvedaemon/pve-cluster/corosync/networking/
    ...) as HIGH because stop/restart can sever the management plane or break quorum. There is
    NO auto-undo for a service control. confirm=True to execute. Async — returns a task UPID.
    """
    cfg, api, _, _ = _proximo_server._svc()
    tgt = f"{node or cfg.node}/services/{service}:{action}"
    plan = _plan("pve_node_service_control", tgt,
                 lambda: plan_node_service_control(service, action, node))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_node_service_control", tgt,
                    lambda: node_service_control(api, service, action, node),
                    mutation=True, outcome="submitted", detail={"confirmed": True})


# --- Notifications & Metrics (Plane E) — PVE notification endpoints, matchers, metrics ---

@tool()
def pve_notification_endpoint_list() -> list[dict]:
    """List all PVE notification endpoints (gotify/smtp/sendmail/webhook) (read)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_notification_endpoint_list", "cluster/notifications/endpoints",
                    lambda: notification_endpoint_list(api))


@tool()
def pve_notification_endpoint_create(ep_type: str, name: str,
                                     comment: str | None = None,
                                     options: dict | None = None,
                                     confirm: bool = False) -> dict:
    """MUTATION: create a PVE notification endpoint. ep_type = gotify|smtp|sendmail|webhook.
    Dry-run by default. confirm=True to execute. `options` carries the endpoint-specific config
    (sendmail: {"mailto-user":"root@pam"}; gotify: {"server":..,"token":..}; webhook: {"url":..})."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/notifications/endpoints/{ep_type}/{name}"
    plan = _plan("pve_notification_endpoint_create", tgt,
                 lambda: plan_notification_endpoint_create(ep_type, name, comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_notification_endpoint_create", tgt,
                    lambda: notification_endpoint_create(api, ep_type, name,
                                                         **{"comment": comment, **(options or {})}),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_notification_endpoint_update(ep_type: str, name: str,
                                     comment: str | None = None,
                                     options: dict | None = None,
                                     confirm: bool = False) -> dict:
    """MUTATION: update a PVE notification endpoint. ep_type = gotify|smtp|sendmail|webhook.
    Dry-run by default — captures current config. confirm=True to execute. `options` carries the
    endpoint-specific fields to change (same shape as create)."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/notifications/endpoints/{ep_type}/{name}"
    plan = _plan("pve_notification_endpoint_update", tgt,
                 lambda: plan_notification_endpoint_update(api, ep_type, name,
                                                           comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_notification_endpoint_update", tgt,
                    lambda: notification_endpoint_update(api, ep_type, name,
                                                         **{"comment": comment, **(options or {})}),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_notification_endpoint_delete(ep_type: str, name: str, confirm: bool = False) -> dict:
    """MUTATION: delete a PVE notification endpoint. ep_type = gotify|smtp|sendmail|webhook.
    Dry-run by default — captures current config. confirm=True to execute.
    WARN: matchers referencing this endpoint will silently fail until it is restored."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/notifications/endpoints/{ep_type}/{name}"
    plan = _plan("pve_notification_endpoint_delete", tgt,
                 lambda: plan_notification_endpoint_delete(api, ep_type, name))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_notification_endpoint_delete", tgt,
                    lambda: notification_endpoint_delete(api, ep_type, name),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_notification_matcher_set(name: str, comment: str | None = None,
                                 confirm: bool = False) -> dict:
    """MUTATION: create-or-update a PVE notification matcher (alert routing rule).
    Dry-run by default. confirm=True to execute."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/notifications/matchers/{name}"
    plan = _plan("pve_notification_matcher_set", tgt,
                 lambda: plan_notification_matcher_set(name, comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_notification_matcher_set", tgt,
                    lambda: notification_matcher_set(api, name, comment=comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_notification_matcher_delete(name: str, confirm: bool = False) -> dict:
    """MUTATION: delete a PVE notification matcher. Dry-run by default.
    confirm=True to execute. WARN: alerts matching this filter go un-routed after deletion."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/notifications/matchers/{name}"
    plan = _plan("pve_notification_matcher_delete", tgt,
                 lambda: plan_notification_matcher_delete(name))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_notification_matcher_delete", tgt,
                    lambda: notification_matcher_delete(api, name),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_notification_test(name: str, confirm: bool = False) -> dict:
    """MUTATION: send a test notification to a PVE notification target. Dry-run by default.
    confirm=True to execute. SENDS A REAL NOTIFICATION — recipients will receive it."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/notifications/targets/{name}"
    plan = _plan("pve_notification_test", tgt,
                 lambda: plan_notification_test(name))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_notification_test", tgt,
                    lambda: notification_test_op(api, name),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_metrics_server_list() -> list[dict]:
    """List all PVE metrics server definitions (influxdb, graphite, etc.) (read)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_metrics_server_list", "cluster/metrics/server",
                    lambda: metrics_server_list(api))


@tool()
def pve_metrics_server_set(metrics_id: str, metrics_type: str | None = None,
                           server: str | None = None, port: int | None = None,
                           disable: bool | None = None, comment: str | None = None,
                           confirm: bool = False) -> dict:
    """MUTATION: create-or-update a PVE metrics server definition. Dry-run by default.
    confirm=True to execute. Config-only; metrics forwarding adjusts to new settings."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/metrics/server/{metrics_id}"
    plan = _plan("pve_metrics_server_set", tgt,
                 lambda: plan_metrics_server_set(metrics_id, type=metrics_type,
                                                 server=server, port=port,
                                                 disable=disable, comment=comment))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_metrics_server_set", tgt,
                    lambda: metrics_server_set(api, metrics_id, type=metrics_type,
                                              server=server, port=port,
                                              disable=disable, comment=comment),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_metrics_server_delete(metrics_id: str, confirm: bool = False) -> dict:
    """MUTATION: delete a PVE metrics server definition. Dry-run by default.
    confirm=True to execute. Metrics forwarding to this server ceases; no data loss."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/metrics/server/{metrics_id}"
    plan = _plan("pve_metrics_server_delete", tgt,
                 lambda: plan_metrics_server_delete(metrics_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_metrics_server_delete", tgt,
                    lambda: metrics_server_delete(api, metrics_id),
                    mutation=True, outcome="ok", detail={"confirmed": True})


# ============================================================================
# Plane F — Hardware PCI/USB Mappings
# ============================================================================

@tool()
def pve_hardware_list(node: str, hw_type: str = "pci") -> dict:
    """List physical PCI or USB devices on a PVE node (read).
    hw_type: 'pci' (default) or 'usb'."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_hardware_list", f"nodes/{node}/hardware/{hw_type}",
                    lambda: hardware_list(api, node, hw_type))


@tool()
def pve_mapping_pci_list() -> list[dict]:
    """List all PCI cluster hardware mappings (read)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_mapping_pci_list", "cluster/mapping/pci",
                    lambda: mapping_pci_list(api))


@tool()
def pve_mapping_usb_list() -> list[dict]:
    """List all USB cluster hardware mappings (read)."""
    _, api, _, _ = _proximo_server._svc()
    return _audited("pve_mapping_usb_list", "cluster/mapping/usb",
                    lambda: mapping_usb_list(api))


@tool()
def pve_mapping_pci_create(mapping_id: str, description: str | None = None,
                           map: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create a PCI cluster passthrough mapping. Dry-run by default.
    confirm=True to execute. Smoke-confirm: POST body shape (id in body) against a live PVE instance."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/mapping/pci/{mapping_id}"
    plan = _plan("pve_mapping_pci_create", tgt,
                 lambda: plan_mapping_pci_create(mapping_id, description=description, map=map))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_mapping_pci_create", tgt,
                    lambda: mapping_pci_create(api, mapping_id, description=description, map=map),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_mapping_pci_update(mapping_id: str, description: str | None = None,
                           map: str | None = None, digest: str | None = None,
                           confirm: bool = False) -> dict:
    """MUTATION: update a PCI cluster mapping. Dry-run by default.
    confirm=True to execute. Reads current config for plan honesty."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/mapping/pci/{mapping_id}"
    plan = _plan("pve_mapping_pci_update", tgt,
                 lambda: plan_mapping_pci_update(api, mapping_id,
                                                  description=description, map=map, digest=digest))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_mapping_pci_update", tgt,
                    lambda: mapping_pci_update(api, mapping_id,
                                               description=description, map=map, digest=digest),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_mapping_pci_delete(mapping_id: str, confirm: bool = False) -> dict:
    """MUTATION: delete a PCI cluster mapping. Dry-run by default.
    confirm=True to execute. VMs referencing this mapping lose the device path."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/mapping/pci/{mapping_id}"
    plan = _plan("pve_mapping_pci_delete", tgt,
                 lambda: plan_mapping_pci_delete(api, mapping_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_mapping_pci_delete", tgt,
                    lambda: mapping_pci_delete(api, mapping_id),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_mapping_usb_create(mapping_id: str, description: str | None = None,
                           map: str | None = None, confirm: bool = False) -> dict:
    """MUTATION: create a USB cluster passthrough mapping. Dry-run by default.
    confirm=True to execute. Smoke-confirm: POST body shape (id in body) against a live PVE instance."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/mapping/usb/{mapping_id}"
    plan = _plan("pve_mapping_usb_create", tgt,
                 lambda: plan_mapping_usb_create(mapping_id, description=description, map=map))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_mapping_usb_create", tgt,
                    lambda: mapping_usb_create(api, mapping_id, description=description, map=map),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_mapping_usb_update(mapping_id: str, description: str | None = None,
                           map: str | None = None, digest: str | None = None,
                           confirm: bool = False) -> dict:
    """MUTATION: update a USB cluster mapping. Dry-run by default.
    confirm=True to execute. Reads current config for plan honesty."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/mapping/usb/{mapping_id}"
    plan = _plan("pve_mapping_usb_update", tgt,
                 lambda: plan_mapping_usb_update(api, mapping_id,
                                                  description=description, map=map, digest=digest))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_mapping_usb_update", tgt,
                    lambda: mapping_usb_update(api, mapping_id,
                                               description=description, map=map, digest=digest),
                    mutation=True, outcome="ok", detail={"confirmed": True})


@tool()
def pve_mapping_usb_delete(mapping_id: str, confirm: bool = False) -> dict:
    """MUTATION: delete a USB cluster mapping. Dry-run by default.
    confirm=True to execute. VMs referencing this mapping lose the USB device path."""
    _, api, _, _ = _proximo_server._svc()
    tgt = f"cluster/mapping/usb/{mapping_id}"
    plan = _plan("pve_mapping_usb_delete", tgt,
                 lambda: plan_mapping_usb_delete(api, mapping_id))
    if not confirm:
        return {"status": "plan", **plan.as_dict()}
    return _audited("pve_mapping_usb_delete", tgt,
                    lambda: mapping_usb_delete(api, mapping_id),
                    mutation=True, outcome="ok", detail={"confirmed": True})
